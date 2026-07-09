"""CAN bus simulator for desktop development without hardware.

Generates realistic Hyper9 motor controller messages.
Simulates acceleration, cruising, regen braking, and temperature changes.

Usage:
  # In-process (virtual mode):
  simulator = CANSimulator(on_message_callback)
  await simulator.start()

  # On Linux with vcan:
  python -m src.can.simulator --interface vcan0
"""

import asyncio
import logging
import math
import random
import struct
import time

from src.can.hyper9 import (
    HYPER9_EXTENDED_ID,
    HYPER9_MOTOR_ID,
    HYPER9_POWER_ID,
    HYPER9_STATUS_ID,
)
from src.state.vehicle import (
    FLAG_FORWARD_ACTIVE,
    FLAG_POWERING_ENABLED,
    FLAG_POWERING_READY,
    FLAG_TRACTION_ENABLED,
    FLAG_VEHICLE_RUNNING,
)

logger = logging.getLogger(__name__)


class CANSimulator:
    """Generates simulated Hyper9 CAN messages in-process."""

    def __init__(self, on_message, on_bms_update=None):
        self.on_message = on_message
        self.on_bms_update = on_bms_update
        self._task: asyncio.Task | None = None
        self._running = False

        # Simulated vehicle state
        self._speed = 0.0
        self._rpm = 0
        self._throttle = 0.0
        self._voltage = 162.0
        self._current = 0.0
        self._motor_temp = 35.0
        self._inverter_temp = 32.0
        self._soc = 85.0
        self._time = 0.0

        # Simulated BMS state (42 cells, 14 temp sensors)
        self._cell_voltages = [3.78 + random.uniform(-0.03, 0.03) for _ in range(42)]
        self._cell_temps = [25.0 + random.uniform(-2, 2) for _ in range(14)]

    async def start(self):
        self._running = True
        self._task = asyncio.create_task(self._sim_loop())
        logger.info("CAN simulator started (virtual mode)")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _sim_loop(self):
        while self._running:
            self._time += 0.02  # 20ms tick
            self._update_physics()

            # TPDO 1: Status at 50Hz (20ms)
            self._send_status()

            # TPDO 3: Motor at 20Hz (50ms)
            if int(self._time * 1000) % 50 < 20:
                self._send_motor()

            # TPDO 2: Power at 10Hz (100ms)
            if int(self._time * 1000) % 100 < 20:
                self._send_power()

            # TPDO 4: Extended at 5Hz (200ms)
            if int(self._time * 1000) % 200 < 20:
                self._send_extended()

            # BMS: update at 2Hz (500ms)
            if int(self._time * 1000) % 500 < 20 and self.on_bms_update:
                self.on_bms_update(self._cell_voltages, self._cell_temps)

            await asyncio.sleep(0.02)

    def _update_physics(self):
        """Simulate realistic driving behavior."""
        # Sinusoidal throttle pattern: accelerate, cruise, regen
        cycle = math.sin(self._time * 0.3)  # ~20 second cycle
        self._throttle = max(-30, min(80, cycle * 60))

        # Speed responds to throttle with inertia
        accel = self._throttle * 0.5  # simplified
        self._speed += accel * 0.02
        self._speed = max(0, min(120, self._speed))

        # RPM proportional to speed (gear ratio ~50:1 with 26" tire)
        self._rpm = int(self._speed * 45)

        # Current proportional to throttle
        self._current = self._throttle * 2.5 + random.uniform(-1, 1)

        # Voltage sags under load
        self._voltage = 168.0 - abs(self._current) * 0.02

        # Temps: strong cooling toward ambient, mild heating from current
        # Keeps temps in realistic 30-65C range
        ambient = 30.0
        heat = abs(self._current) * 0.0002
        self._motor_temp += (heat - (self._motor_temp - ambient) * 0.002) * 0.5
        self._inverter_temp += (heat * 0.7 - (self._inverter_temp - ambient) * 0.002) * 0.5
        self._motor_temp = max(ambient, min(85, self._motor_temp))
        self._inverter_temp = max(ambient, min(75, self._inverter_temp))

        # SOC decreases very slowly
        self._soc -= abs(self._current) * 0.00001
        self._soc = max(5, self._soc)

        # BMS: cell voltages drift slightly, track SOC
        base_v = 3.2 + (self._soc / 100.0) * 0.9  # 3.2V at 0%, 4.1V at 100%
        for i in range(42):
            drift = random.uniform(-0.001, 0.001)
            self._cell_voltages[i] += drift
            # Gently pull toward base voltage
            self._cell_voltages[i] += (base_v - self._cell_voltages[i]) * 0.01
            self._cell_voltages[i] = max(3.0, min(4.2, self._cell_voltages[i]))

        # Cell temps drift with motor load
        for i in range(14):
            self._cell_temps[i] += random.uniform(-0.02, 0.02)
            self._cell_temps[i] += (ambient - self._cell_temps[i]) * 0.001

    def _send_status(self):
        """TPDO 1: HYPER9_STATUS (0x181)"""
        flags = FLAG_VEHICLE_RUNNING | FLAG_TRACTION_ENABLED | FLAG_FORWARD_ACTIVE
        flags |= FLAG_POWERING_ENABLED | FLAG_POWERING_READY

        speed_raw = int(self._speed * 10)  # 0.1 km/h resolution
        soc_raw = int(self._soc)
        fault = 0

        # Pack: speed(i16) + soc(u8) + flags(u16) + fault(u8) + pad(2)
        data = struct.pack("<hBHBxx", speed_raw, soc_raw, flags, fault)
        self.on_message(HYPER9_STATUS_ID, data, time.time())

    def _send_power(self):
        """TPDO 2: HYPER9_POWER (0x182)"""
        voltage_raw = int(self._voltage * 10)
        current_raw = int(self._current * 10)
        motor_current_raw = int(self._current * 1.2 * 10)

        data = struct.pack("<hhhxx", voltage_raw, current_raw, motor_current_raw)
        self.on_message(HYPER9_POWER_ID, data, time.time())

    def _send_motor(self):
        """TPDO 3: HYPER9_MOTOR (0x183)"""
        rpm_raw = int(self._rpm)
        motor_temp_raw = int(self._motor_temp + 40)  # offset -40
        inverter_temp_raw = int(self._inverter_temp + 40)
        throttle_raw = int(self._throttle)
        torque_raw = int(self._throttle * 0.8)

        data = struct.pack("<hBBbhx", rpm_raw, motor_temp_raw, inverter_temp_raw,
                           throttle_raw, torque_raw)
        self.on_message(HYPER9_MOTOR_ID, data, time.time())

    def _send_extended(self):
        """TPDO 4: HYPER9_EXTENDED (0x184)"""
        fault_level = 0
        motor_flags = 0
        data = struct.pack("<BHxxxxx", fault_level, motor_flags)
        self.on_message(HYPER9_EXTENDED_ID, data, time.time())


async def run_vcan_simulator(interface: str = "vcan0"):
    """Send simulated CAN messages to a SocketCAN interface (Linux only)."""
    import can

    bus = can.Bus(interface="socketcan", channel=interface, bitrate=500000)

    def send_to_bus(arbitration_id: int, data: bytes, timestamp: float):
        msg = can.Message(arbitration_id=arbitration_id, data=data, is_extended_id=False)
        bus.send(msg)

    sim = CANSimulator(on_message=send_to_bus)
    logger.info(f"Sending simulated CAN data on {interface}")

    try:
        await sim.start()
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        await sim.stop()
        bus.shutdown()


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Hyper9 CAN simulator")
    parser.add_argument("--interface", default="vcan0", help="SocketCAN interface")
    args = parser.parse_args()

    asyncio.run(run_vcan_simulator(args.interface))
