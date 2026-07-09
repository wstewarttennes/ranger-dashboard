import logging
import time

from src.state.vehicle import VehicleState

logger = logging.getLogger(__name__)

# Thunderstruck MCU ZEVCCS message IDs
MCU_BMS_LIMITS_ID = 0x351    # 849
MCU_BMS_SOC_ID = 0x355       # 853
MCU_BMS_STATUS_ID = 0x356    # 854
MCU_BMS_ERRORS_ID = 0x35A    # 858
MCU_BMS_STATUS2_ID = 0x35B   # 859

BMS_IDS = {
    MCU_BMS_LIMITS_ID,
    MCU_BMS_SOC_ID,
    MCU_BMS_STATUS_ID,
    MCU_BMS_ERRORS_ID,
    MCU_BMS_STATUS2_ID,
}


def is_bms_message(arbitration_id: int) -> bool:
    return arbitration_id in BMS_IDS


def update_vehicle_state(state: VehicleState, arbitration_id: int, signals: dict):
    """Update vehicle state from decoded Thunderstruck MCU BMS signals."""

    if arbitration_id == MCU_BMS_SOC_ID:
        state.soc_pct = signals.get("BATTERY_SOC", state.soc_pct)
        state.last_can_update = time.time()

    elif arbitration_id == MCU_BMS_STATUS_ID:
        state.pack_voltage = signals.get("PACK_VOLTAGE", state.pack_voltage)
        state.pack_current = signals.get("PACK_CURRENT", state.pack_current)
        state.pack_temperature = signals.get("PACK_TEMPERATURE", state.pack_temperature)
        state.last_can_update = time.time()

    elif arbitration_id == MCU_BMS_LIMITS_ID:
        state.charge_voltage_limit = signals.get("CHARGE_VOLTAGE_LIMIT", 0.0)
        state.charge_current_limit = signals.get("CHARGE_CURRENT_LIMIT", 0.0)
        state.discharge_current_limit = signals.get("DISCHARGE_CURRENT_LIMIT", 0.0)
        state.discharge_voltage_limit = signals.get("DISCHARGE_VOLTAGE_LIMIT", 0.0)
        state.last_can_update = time.time()

    elif arbitration_id == MCU_BMS_ERRORS_ID:
        state.bms_fault_flags = int(signals.get("FAULT_FLAGS", 0))
        state.bms_status_flags = int(signals.get("STATUS_FLAGS", 0))
        state.last_can_update = time.time()

    elif arbitration_id == MCU_BMS_STATUS2_ID:
        state.bms_fault_flags_2 = int(signals.get("STATUS2_FAULT_FLAGS", 0))
        state.bms_status_flags_2 = int(signals.get("STATUS2_STATUS_FLAGS", 0))
        state.last_can_update = time.time()
