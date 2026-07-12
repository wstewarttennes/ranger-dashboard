from dataclasses import dataclass, field
import time


# System flag bit positions (from hyper9.dbc)
FLAG_SOC_LOW_TRACTION = 1 << 0
FLAG_SOC_LOW_HYDRAULIC = 1 << 1
FLAG_REVERSE_ACTIVE = 1 << 2
FLAG_FORWARD_ACTIVE = 1 << 3
FLAG_PARK_BRAKE = 1 << 4
FLAG_PEDAL_BRAKE = 1 << 5
FLAG_OVERTEMP = 1 << 6
FLAG_KEY_OVERVOLTAGE = 1 << 7
FLAG_KEY_UNDERVOLTAGE = 1 << 8
FLAG_VEHICLE_RUNNING = 1 << 9
FLAG_TRACTION_ENABLED = 1 << 10
FLAG_HYDRAULIC_ENABLED = 1 << 11
FLAG_POWERING_ENABLED = 1 << 12
FLAG_POWERING_READY = 1 << 13
FLAG_PRECHARGING = 1 << 14
FLAG_CONTACTOR_CLOSING = 1 << 15

# Fault level descriptions
FAULT_LEVELS = {
    0: "Ready",
    1: "Blocking",
    2: "Stopping",
    3: "Limiting",
    4: "Warning",
}


@dataclass
class VehicleState:
    # Hyper 9 motor data
    speed_kmh: float = 0.0
    motor_rpm: int = 0
    motor_temp_c: float = 0.0
    inverter_temp_c: float = 0.0
    throttle_pct: float = 0.0
    motor_torque_pct: float = 0.0
    dc_bus_voltage: float = 0.0
    dc_bus_current: float = 0.0
    motor_current: float = 0.0

    # Computed
    @property
    def power_kw(self) -> float:
        return self.dc_bus_voltage * self.dc_bus_current / 1000.0

    @property
    def speed_mph(self) -> float:
        return self.speed_kmh * 0.621371

    # Direction/state from system flags
    system_flags: int = 0
    fault_code: int = 0
    fault_level: int = 0
    motor_flags: int = 0

    @property
    def gear(self) -> str:
        if self.system_flags & FLAG_REVERSE_ACTIVE:
            return "R"
        elif self.system_flags & FLAG_FORWARD_ACTIVE:
            return "D"
        return "N"

    @property
    def vehicle_running(self) -> bool:
        return bool(self.system_flags & FLAG_VEHICLE_RUNNING)

    @property
    def traction_enabled(self) -> bool:
        return bool(self.system_flags & FLAG_TRACTION_ENABLED)

    @property
    def precharging(self) -> bool:
        return bool(self.system_flags & FLAG_PRECHARGING)

    @property
    def overtemp(self) -> bool:
        return bool(self.system_flags & FLAG_OVERTEMP)

    @property
    def park_brake(self) -> bool:
        return bool(self.system_flags & FLAG_PARK_BRAKE)

    @property
    def fault_level_str(self) -> str:
        return FAULT_LEVELS.get(self.fault_level, "Unknown")

    # BMS data
    soc_pct: float = 0.0
    pack_voltage: float = 0.0
    pack_current: float = 0.0
    pack_temperature: float = 0.0
    cell_voltages: list[float] = field(default_factory=lambda: [0.0] * 42)
    cell_temps: list[float] = field(default_factory=lambda: [0.0] * 14)

    # BMS limits (from ZEVCCS 0x351)
    charge_voltage_limit: float = 0.0
    charge_current_limit: float = 0.0
    discharge_current_limit: float = 0.0
    discharge_voltage_limit: float = 0.0

    # BMS fault/status flags (from ZEVCCS 0x35a/0x35b)
    bms_fault_flags: int = 0
    bms_status_flags: int = 0
    bms_fault_flags_2: int = 0
    bms_status_flags_2: int = 0

    # Onboard charger (TSM2500, decoded from CAN 0x18EB2440 while charging)
    charge_voltage: float = 0.0
    charge_current: float = 0.0
    charger_temp_c: float = 0.0
    last_charge_update: float = 0.0

    @property
    def charging(self) -> bool:
        # Only "charging" if a live charger frame arrived in the last few seconds
        # AND current is flowing — so it auto-clears when you unplug.
        return (time.time() - self.last_charge_update) < 3.0 and self.charge_current > 0.5

    @property
    def charge_watts(self) -> float:
        return self.charge_voltage * self.charge_current

    @property
    def min_cell_v(self) -> float:
        active = [v for v in self.cell_voltages if v > 0]
        return min(active) if active else 0.0

    @property
    def max_cell_v(self) -> float:
        active = [v for v in self.cell_voltages if v > 0]
        return max(active) if active else 0.0

    @property
    def cell_delta_mv(self) -> float:
        return (self.max_cell_v - self.min_cell_v) * 1000.0

    # Comma/openpilot state (from WebRTC data channel)
    openpilot_enabled: bool = False
    openpilot_state: str = "offline"
    comma_connected: bool = False

    # Timestamps
    last_can_update: float = 0.0
    last_comma_update: float = 0.0

    def to_dict(self) -> dict:
        """Serialize to JSON-friendly dict for WebSocket broadcast."""
        return {
            # Motor
            "speed_kmh": round(self.speed_kmh, 1),
            "speed_mph": round(self.speed_mph, 1),
            "motor_rpm": self.motor_rpm,
            "motor_temp_c": round(self.motor_temp_c, 1),
            "inverter_temp_c": round(self.inverter_temp_c, 1),
            "throttle_pct": round(self.throttle_pct, 1),
            "motor_torque_pct": round(self.motor_torque_pct, 1),
            "dc_bus_voltage": round(self.dc_bus_voltage, 1),
            "dc_bus_current": round(self.dc_bus_current, 1),
            "motor_current": round(self.motor_current, 1),
            "power_kw": round(self.power_kw, 2),
            # State
            "gear": self.gear,
            "vehicle_running": self.vehicle_running,
            "traction_enabled": self.traction_enabled,
            "precharging": self.precharging,
            "overtemp": self.overtemp,
            "park_brake": self.park_brake,
            "fault_code": self.fault_code,
            "fault_level": self.fault_level,
            "fault_level_str": self.fault_level_str,
            # BMS
            "soc_pct": round(self.soc_pct, 1),
            "pack_voltage": round(self.pack_voltage, 1),
            "pack_current": round(self.pack_current, 1),
            "pack_temperature": round(self.pack_temperature, 1),
            "charge_voltage_limit": round(self.charge_voltage_limit, 1),
            "charge_current_limit": round(self.charge_current_limit, 1),
            "discharge_current_limit": round(self.discharge_current_limit, 1),
            "discharge_voltage_limit": round(self.discharge_voltage_limit, 1),
            "bms_fault_flags": self.bms_fault_flags,
            "bms_status_flags": self.bms_status_flags,
            # Charger (TSM2500)
            "charge_voltage": round(self.charge_voltage, 1),
            "charge_current": round(self.charge_current, 1),
            "charge_watts": round(self.charge_watts),
            "charger_temp_c": round(self.charger_temp_c, 1),
            "charging": self.charging,
            "cell_voltages": [round(v, 3) for v in self.cell_voltages],
            "cell_temps": [round(t, 1) for t in self.cell_temps],
            "min_cell_v": round(self.min_cell_v, 3),
            "max_cell_v": round(self.max_cell_v, 3),
            "cell_delta_mv": round(self.cell_delta_mv, 1),
            # Comma
            "openpilot_enabled": self.openpilot_enabled,
            "openpilot_state": self.openpilot_state,
            "comma_connected": self.comma_connected,
            # Meta
            "last_can_update": self.last_can_update,
            "last_comma_update": self.last_comma_update,
            "timestamp": time.time(),
        }
