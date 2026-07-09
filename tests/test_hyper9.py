import struct
from pathlib import Path

import pytest

from src.can.parser import CANParser
from src.can.hyper9 import (
    HYPER9_STATUS_ID,
    HYPER9_POWER_ID,
    HYPER9_MOTOR_ID,
    HYPER9_EXTENDED_ID,
    update_vehicle_state,
)
from src.state.vehicle import VehicleState


@pytest.fixture
def parser():
    base_dir = Path(__file__).parent.parent
    return CANParser(["dbc/hyper9.dbc"], base_dir=base_dir)


def test_update_status(parser, vehicle_state, hyper9_status_data):
    signals = parser.decode(HYPER9_STATUS_ID, hyper9_status_data)
    update_vehicle_state(vehicle_state, HYPER9_STATUS_ID, signals)

    assert vehicle_state.speed_kmh == pytest.approx(45.2, abs=0.1)
    assert vehicle_state.soc_pct == 82.0
    assert vehicle_state.gear == "D"
    assert vehicle_state.vehicle_running is True
    assert vehicle_state.traction_enabled is True
    assert vehicle_state.fault_code == 0
    assert vehicle_state.last_can_update > 0


def test_update_power(parser, vehicle_state, hyper9_power_data):
    signals = parser.decode(HYPER9_POWER_ID, hyper9_power_data)
    update_vehicle_state(vehicle_state, HYPER9_POWER_ID, signals)

    assert vehicle_state.dc_bus_voltage == pytest.approx(165.3, abs=0.1)
    assert vehicle_state.dc_bus_current == pytest.approx(74.2, abs=0.1)
    assert vehicle_state.motor_current == pytest.approx(89.0, abs=0.1)
    assert vehicle_state.power_kw == pytest.approx(12.27, abs=0.1)


def test_update_motor(parser, vehicle_state, hyper9_motor_data):
    signals = parser.decode(HYPER9_MOTOR_ID, hyper9_motor_data)
    update_vehicle_state(vehicle_state, HYPER9_MOTOR_ID, signals)

    assert vehicle_state.motor_rpm == 2100
    assert vehicle_state.motor_temp_c == 52.0
    assert vehicle_state.inverter_temp_c == 45.0
    assert vehicle_state.throttle_pct == 35.0
    assert vehicle_state.motor_torque_pct == 28.0


def test_update_extended(parser, vehicle_state, hyper9_extended_data):
    signals = parser.decode(HYPER9_EXTENDED_ID, hyper9_extended_data)
    update_vehicle_state(vehicle_state, HYPER9_EXTENDED_ID, signals)

    assert vehicle_state.fault_level == 0
    assert vehicle_state.motor_flags == 0


def test_regen_braking(parser, vehicle_state):
    """Test negative current (regen) shows negative power."""
    voltage_raw = int(168.0 * 10)
    current_raw = int(-25.0 * 10)  # regen
    motor_current_raw = int(-30.0 * 10)
    data = struct.pack("<hhhxx", voltage_raw, current_raw, motor_current_raw)

    signals = parser.decode(HYPER9_POWER_ID, data)
    update_vehicle_state(vehicle_state, HYPER9_POWER_ID, signals)

    assert vehicle_state.dc_bus_current == pytest.approx(-25.0, abs=0.1)
    assert vehicle_state.power_kw < 0


def test_fault_state(parser, vehicle_state):
    """Test fault detection from extended message."""
    data = struct.pack("<BHxxxxx", 1, 0x0008)  # fault_level=1 (Blocking), motor overtemp flag
    signals = parser.decode(HYPER9_EXTENDED_ID, data)
    update_vehicle_state(vehicle_state, HYPER9_EXTENDED_ID, signals)

    assert vehicle_state.fault_level == 1
    assert vehicle_state.fault_level_str == "Blocking"
    assert vehicle_state.motor_flags == 0x0008
