import logging
import time

from src.state.vehicle import VehicleState

logger = logging.getLogger(__name__)

# Hyper 9 TPDO message IDs (from hyper9.dbc)
HYPER9_STATUS_ID = 0x181     # 385
HYPER9_POWER_ID = 0x182      # 386
HYPER9_MOTOR_ID = 0x183      # 387
HYPER9_EXTENDED_ID = 0x184   # 388
HYPER9_KEYVOLT_ID = 0x485    # 1157 — configurable TPDO1: Key Switch (12V) Voltage
HYPER9_LIFE_ID = 0x482       # 1154 — configurable TPDO: odometer + service life
HYPER9_MOTOR2_ID = 0x483     # 1155 — configurable TPDO: motor op hours + extras
HYPER9_ANALOG_ID = 0x281     # 641 — CANopen TPDO2: analog inputs (REAL throttle pedal)

HYPER9_IDS = {HYPER9_STATUS_ID, HYPER9_POWER_ID, HYPER9_MOTOR_ID,
              HYPER9_EXTENDED_ID, HYPER9_KEYVOLT_ID, HYPER9_LIFE_ID, HYPER9_MOTOR2_ID,
              HYPER9_ANALOG_ID}

# Motor RPM -> road speed (km/h). The X1's own Vehicle Speed output is
# uncalibrated, so we compute speed from RPM instead. Default assumes the
# transmission is in the loop (~7.5:1 total) with 26" tires. Overridden at
# startup from config.yaml (display.rpm_to_kmh) — tune against GPS.
RPM_TO_KMH = 0.0167


def is_hyper9_message(arbitration_id: int) -> bool:
    return arbitration_id in HYPER9_IDS


def update_vehicle_state(state: VehicleState, arbitration_id: int, signals: dict):
    """Update vehicle state from decoded Hyper9 signals."""

    if arbitration_id == HYPER9_STATUS_ID:
        # NOTE: speed_kmh is NOT taken from the X1 here. The X1's Vehicle Speed
        # is uncalibrated (no gear ratio / tire size set) and reads a phantom
        # value while parked. We derive speed from motor RPM instead (below,
        # in HYPER9_MOTOR). SOC is likewise owned by the MCU BMS (0x355) — both
        # left out of this handler on purpose.
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
        # Derive road speed from motor RPM (the X1's own Vehicle Speed is
        # uncalibrated). speed_kmh = |rpm| * RPM_TO_KMH. This reads exactly 0
        # when parked; the magnitude needs calibration once the truck moves —
        # see RPM_TO_KMH note at top of file.
        state.speed_kmh = round(abs(state.motor_rpm) * RPM_TO_KMH, 1)
        state.motor_temp_c = signals.get("MOTOR_TEMP", 0.0)
        state.inverter_temp_c = signals.get("INVERTER_TEMP", 0.0)
        # NOTE: throttle is NOT taken here. This message's THROTTLE_REQUEST byte
        # is only ever 0 or 80 (a quantized flag), not the analog pedal. Real
        # throttle comes from HYPER9_ANALOG (0x281), handled below.
        state.motor_torque_pct = signals.get("MOTOR_TORQUE", 0.0)
        state.last_can_update = time.time()

    elif arbitration_id == HYPER9_EXTENDED_ID:
        state.fault_level = int(signals.get("FAULT_LEVEL", 0))
        state.motor_flags = int(signals.get("MOTOR_FLAGS", 0))
        state.last_can_update = time.time()

    elif arbitration_id == HYPER9_KEYVOLT_ID:
        # Configurable TPDO mapping the X1's Key Switch (12V supply) Voltage
        # (slot 1) and the digital-input/switch states word (slot 2, carries
        # the F/R selector position). Only present once mapped in SmartView;
        # until then this frame never arrives and both stay 0.
        state.key_switch_voltage = signals.get("KEY_SWITCH_VOLTAGE", 0.0)
        state.last_key_voltage_update = time.time()
        state.switch_states = int(signals.get("SWITCH_STATES", 0))
        state.last_switch_update = time.time()
        state.last_can_update = time.time()

    elif arbitration_id == HYPER9_LIFE_ID:
        # Odometer is a 32-bit value split across two words (Dam = dekameters).
        hi = int(signals.get("ODO_HIGH", 0))
        lo = int(signals.get("ODO_LOW", 0))
        odo_dam = (hi << 16) | lo          # dekameters (10 m units)
        state.odometer_km = round(odo_dam / 100.0, 1)   # 1 Dam = 0.01 km
        state.key_on_hours = int(signals.get("KEY_ON_HOURS", 0))
        state.service_hours = int(signals.get("SERVICE_HOURS", 0))
        state.last_can_update = time.time()

    elif arbitration_id == HYPER9_MOTOR2_ID:
        state.motor_op_hours = int(signals.get("MOTOR_OP_HOURS", 0))
        state.motor_iq = signals.get("MOTOR_IQ", 0.0)
        state.motor_speed_ref = int(signals.get("MOTOR_SPEED_REF", 0))
        state.node_dc_current = signals.get("NODE_DC_CURRENT", 0.0)
        state.last_can_update = time.time()

    elif arbitration_id == HYPER9_ANALOG_ID:
        # Real analog throttle pedal (0x281 byte 4). It's a SIGNED direct percent:
        # positive = throttle (0..~100), negative = coast/regen overrun (0xFF=-1).
        # Clamp to 0..100 so coasting reads 0% instead of wrapping to 100%.
        # (The X1's 0x183 THROTTLE_REQUEST byte is only ever 0/80 — a quantized
        # flag — so this analog input is the true pedal position.)
        throttle = signals.get("THROTTLE_POT", 0.0)
        state.throttle_pct = max(0, min(100, round(throttle)))
        state.last_can_update = time.time()
