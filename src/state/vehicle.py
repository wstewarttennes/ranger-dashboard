from dataclasses import dataclass, field
import time


# System flag bit positions (from hyper9.dbc)
FLAG_SOC_LOW_TRACTION = 1 << 0
FLAG_SOC_LOW_HYDRAULIC = 1 << 1
# NOTE: bits confirmed empirically on the truck — driving FORWARD sets 1<<2
# (earlier decode had these two swapped, which showed "R" while driving forward).
FLAG_FORWARD_ACTIVE = 1 << 2
FLAG_REVERSE_ACTIVE = 1 << 3
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

# F/R selector bit masks within the switch-states word (0x485 slot 2).
# 0 = uncalibrated: gear falls back to signed-RPM detection. Calibrate live —
# flip the selector while watching switch_states_raw in /api/state, then set
# display.switch_fwd_mask / display.switch_rev_mask in config.yaml (patched
# in at startup by main.py, same pattern as RPM_TO_KMH).
SWITCH_FWD_MASK = 0
SWITCH_REV_MASK = 0

# Fault level descriptions
FAULT_LEVELS = {
    0: "Ready",
    1: "Blocking",
    2: "Stopping",
    3: "Limiting",
    4: "Warning",
}

# (bitmask, key, label, severity) for every system flag bit.
# severity drives the chip color in the Diagnostics UI:
#   good = green (healthy/active), info = blue (neutral state), warn = red (attention)
SYSTEM_FLAG_DEFS = [
    (FLAG_VEHICLE_RUNNING,   "running",           "Running",            "good"),
    (FLAG_FORWARD_ACTIVE,    "forward",           "Forward",            "good"),
    (FLAG_REVERSE_ACTIVE,    "reverse",           "Reverse",            "good"),
    (FLAG_TRACTION_ENABLED,  "traction_enabled",  "Traction Enabled",   "good"),
    (FLAG_HYDRAULIC_ENABLED, "hydraulic_enabled", "Hydraulic Enabled",  "good"),
    (FLAG_POWERING_ENABLED,  "powering_enabled",  "Powering Enabled",   "good"),
    (FLAG_POWERING_READY,    "powering_ready",    "Powering Ready",     "good"),
    (FLAG_PRECHARGING,       "precharging",       "Precharging",        "info"),
    (FLAG_CONTACTOR_CLOSING, "contactor_closing", "Contactor Closing",  "info"),
    (FLAG_PARK_BRAKE,        "park_brake",        "Park Brake",         "info"),
    (FLAG_PEDAL_BRAKE,       "pedal_brake",       "Pedal Brake",        "info"),
    (FLAG_SOC_LOW_TRACTION,  "soc_low_traction",  "SoC Low (Traction)", "warn"),
    (FLAG_SOC_LOW_HYDRAULIC, "soc_low_hydraulic", "SoC Low (Hydraulic)", "warn"),
    (FLAG_OVERTEMP,          "overtemp",          "Overtemp",           "warn"),
    (FLAG_KEY_OVERVOLTAGE,   "key_overvoltage",   "Key Overvoltage",    "warn"),
    (FLAG_KEY_UNDERVOLTAGE,  "key_undervoltage",  "Key Undervoltage",   "warn"),
]


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

    # GPS speed from the comma (gear-independent). Set via POST /api/gps by the
    # comma-side pusher (tools/comma_gps_pub.py). Preferred over speed_kmh, which
    # is rpm-derived and only correct in ONE gear on the manual gearbox.
    gps_speed_kmh: float = 0.0
    gps_speed_ts: float = 0.0   # epoch of last GPS update
    gps_fix: bool = False

    # Computed
    @property
    def power_kw(self) -> float:
        return self.dc_bus_voltage * self.dc_bus_current / 1000.0

    @property
    def gps_fresh(self) -> bool:
        """True when we have a recent GPS fix to trust over the rpm estimate."""
        return self.gps_fix and (time.time() - self.gps_speed_ts) < 3.0

    @property
    def display_speed_kmh(self) -> float:
        """Gear-independent GPS speed when fresh; else the rpm-derived fallback."""
        return self.gps_speed_kmh if self.gps_fresh else self.speed_kmh

    @property
    def speed_mph(self) -> float:
        return self.display_speed_kmh * 0.621371

    # Direction/state from system flags
    system_flags: int = 0
    fault_code: int = 0
    fault_level: int = 0
    motor_flags: int = 0

    @property
    def gear(self) -> str:
        # Preferred source: the actual F/R selector position from the
        # switch-states word (0x485 slot 2) — shows R/D the moment the switch
        # moves, throttle or not. Only used once the TPDO is mapped in
        # SmartView AND the bit masks are calibrated (see SWITCH_*_MASK above);
        # requires fresh frames so a dead TPDO can't freeze the display.
        if ((SWITCH_FWD_MASK or SWITCH_REV_MASK)
                and (time.time() - self.last_switch_update) < 2.0):
            if self.switch_states & SWITCH_REV_MASK:
                return "R"
            if self.switch_states & SWITCH_FWD_MASK:
                return "D"
            return "N"
        # Fallback: SIGNED motor RPM, not the SYSTEM_FLAGS forward/reverse
        # bits. On this firmware the 0x181 flag word is unreliable: its
        # direction/state bits (BIT2 Reverse, BIT3 Forward, BIT9 Running,
        # BIT14 Precharging) sit frozen and do not track the F/R selector —
        # verified live through a full D/R/N cycle, bytes 3-4 never moved.
        # MOTOR_RPM (0x183) is signed: >0 forward, <0 reverse. A small
        # deadband avoids flicker at a standstill, where direction is unknown
        # and we honestly report N.
        if self.motor_rpm > 20:
            return "D"
        if self.motor_rpm < -20:
            return "R"
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
    def key_undervoltage(self) -> bool:
        return bool(self.system_flags & FLAG_KEY_UNDERVOLTAGE)

    @property
    def has_fault(self) -> bool:
        return self.fault_level > 0 or self.bms_fault_flags != 0

    @property
    def fault_level_str(self) -> str:
        return FAULT_LEVELS.get(self.fault_level, "Unknown")

    @property
    def system_flags_decoded(self) -> list[dict]:
        """Every system-flag bit as {key,label,active,severity} for the UI."""
        return [
            {"key": key, "label": label,
             "active": bool(self.system_flags & mask), "severity": sev}
            for (mask, key, label, sev) in SYSTEM_FLAG_DEFS
        ]

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

    # X1 Key Switch (12V supply) voltage — from a configurable TPDO (0x481).
    # 0 until the TPDO is mapped in SmartView.
    key_switch_voltage: float = 0.0
    last_key_voltage_update: float = 0.0

    # X1 digital-input/switch states word (0x485 slot 2) — F/R selector lives
    # here. 0 until the TPDO is mapped in SmartView.
    switch_states: int = 0
    last_switch_update: float = 0.0

    # X1 life/odometer (configurable TPDO 0x482) + motor extras (0x483).
    # All 0 until the TPDOs are mapped in SmartView.
    odometer_km: float = 0.0
    key_on_hours: int = 0
    service_hours: int = 0
    motor_op_hours: int = 0
    motor_iq: float = 0.0
    motor_speed_ref: int = 0
    node_dc_current: float = 0.0

    @property
    def odometer_mi(self) -> float:
        return self.odometer_km * 0.621371

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
            "speed_kmh": round(self.display_speed_kmh, 1),
            "speed_mph": round(self.speed_mph, 1),
            "speed_source": "gps" if self.gps_fresh else "motor",
            "gps_speed_mph": round(self.gps_speed_kmh * 0.621371, 1),
            "motor_speed_mph": round(self.speed_kmh * 0.621371, 1),
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
            "key_undervoltage": self.key_undervoltage,
            "has_fault": self.has_fault,
            "key_switch_voltage": round(self.key_switch_voltage, 2),
            "key_voltage_live": (time.time() - self.last_key_voltage_update) < 5.0,
            "switch_states_raw": self.switch_states,
            "switch_states_live": (time.time() - self.last_switch_update) < 5.0,
            "odometer_km": round(self.odometer_km, 1),
            "odometer_mi": round(self.odometer_mi, 1),
            "key_on_hours": self.key_on_hours,
            "service_hours": self.service_hours,
            "motor_op_hours": self.motor_op_hours,
            "motor_iq": round(self.motor_iq, 1),
            "motor_speed_ref": self.motor_speed_ref,
            "node_dc_current": round(self.node_dc_current, 1),
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
            "bms_fault_flags_2": self.bms_fault_flags_2,
            "bms_status_flags_2": self.bms_status_flags_2,
            # Diagnostics: raw + decoded flag words
            "system_flags_raw": self.system_flags,
            "system_flags_decoded": self.system_flags_decoded,
            "motor_flags": self.motor_flags,
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
