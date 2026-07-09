import logging
import time

from src.state.vehicle import VehicleState

logger = logging.getLogger(__name__)

# Hyper 9 TPDO message IDs (from hyper9.dbc)
HYPER9_STATUS_ID = 0x181     # 385
HYPER9_POWER_ID = 0x182      # 386
HYPER9_MOTOR_ID = 0x183      # 387
HYPER9_EXTENDED_ID = 0x184   # 388

HYPER9_IDS = {HYPER9_STATUS_ID, HYPER9_POWER_ID, HYPER9_MOTOR_ID, HYPER9_EXTENDED_ID}


def is_hyper9_message(arbitration_id: int) -> bool:
    return arbitration_id in HYPER9_IDS


def update_vehicle_state(state: VehicleState, arbitration_id: int, signals: dict):
    """Update vehicle state from decoded Hyper9 signals."""

    if arbitration_id == HYPER9_STATUS_ID:
        state.speed_kmh = signals.get("VEHICLE_SPEED", 0.0)
        state.soc_pct = signals.get("BATTERY_SOC", 0.0)
        state.system_flags = int(signals.get("SYSTEM_FLAGS", 0))
        state.fault_code = int(signals.get("FAULT_CODE", 0))
        state.last_can_update = time.time()

    elif arbitration_id == HYPER9_POWER_ID:
        state.dc_bus_voltage = signals.get("DC_BUS_VOLTAGE", 0.0)
        state.dc_bus_current = signals.get("DC_BUS_CURRENT", 0.0)
        state.motor_current = signals.get("MOTOR_CURRENT", 0.0)
        state.last_can_update = time.time()

    elif arbitration_id == HYPER9_MOTOR_ID:
        state.motor_rpm = int(signals.get("MOTOR_RPM", 0))
        state.motor_temp_c = signals.get("MOTOR_TEMP", 0.0)
        state.inverter_temp_c = signals.get("INVERTER_TEMP", 0.0)
        state.throttle_pct = signals.get("THROTTLE_REQUEST", 0.0)
        state.motor_torque_pct = signals.get("MOTOR_TORQUE", 0.0)
        state.last_can_update = time.time()

    elif arbitration_id == HYPER9_EXTENDED_ID:
        state.fault_level = int(signals.get("FAULT_LEVEL", 0))
        state.motor_flags = int(signals.get("MOTOR_FLAGS", 0))
        state.last_can_update = time.time()
