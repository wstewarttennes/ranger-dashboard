import struct
from pathlib import Path

import pytest

from src.can.parser import CANParser
from src.can.hyper9 import (
    HYPER9_STATUS_ID,
    HYPER9_POWER_ID,
    HYPER9_MOTOR_ID,
    HYPER9_EXTENDED_ID,
    is_hyper9_message,
)


@pytest.fixture
def parser():
    base_dir = Path(__file__).parent.parent
    return CANParser(["dbc/hyper9.dbc"], base_dir=base_dir)


def test_parser_loads_dbc(parser):
    assert parser.get_message_name(HYPER9_STATUS_ID) == "HYPER9_STATUS"
    assert parser.get_message_name(HYPER9_POWER_ID) == "HYPER9_POWER"
    assert parser.get_message_name(HYPER9_MOTOR_ID) == "HYPER9_MOTOR"
    assert parser.get_message_name(HYPER9_EXTENDED_ID) == "HYPER9_EXTENDED"


def test_parser_unknown_id(parser):
    assert parser.get_message_name(0x999) is None
    assert parser.decode(0x999, b"\x00" * 8) is None


def test_decode_status(parser, hyper9_status_data):
    signals = parser.decode(HYPER9_STATUS_ID, hyper9_status_data)
    assert signals is not None
    assert signals["VEHICLE_SPEED"] == pytest.approx(45.2, abs=0.1)
    assert signals["BATTERY_SOC"] == 82
    assert signals["FAULT_CODE"] == 0


def test_decode_power(parser, hyper9_power_data):
    signals = parser.decode(HYPER9_POWER_ID, hyper9_power_data)
    assert signals is not None
    assert signals["DC_BUS_VOLTAGE"] == pytest.approx(165.3, abs=0.1)
    assert signals["DC_BUS_CURRENT"] == pytest.approx(74.2, abs=0.1)
    assert signals["MOTOR_CURRENT"] == pytest.approx(89.0, abs=0.1)


def test_decode_motor(parser, hyper9_motor_data):
    signals = parser.decode(HYPER9_MOTOR_ID, hyper9_motor_data)
    assert signals is not None
    assert signals["MOTOR_RPM"] == 2100
    assert signals["MOTOR_TEMP"] == 52.0
    assert signals["INVERTER_TEMP"] == 45.0
    assert signals["THROTTLE_REQUEST"] == 35
    assert signals["MOTOR_TORQUE"] == 28


def test_decode_extended(parser, hyper9_extended_data):
    signals = parser.decode(HYPER9_EXTENDED_ID, hyper9_extended_data)
    assert signals is not None
    assert signals["FAULT_LEVEL"] == 0
    assert signals["MOTOR_FLAGS"] == 0


def test_is_hyper9_message():
    assert is_hyper9_message(0x181) is True
    assert is_hyper9_message(0x182) is True
    assert is_hyper9_message(0x183) is True
    assert is_hyper9_message(0x184) is True
    assert is_hyper9_message(0x100) is False
    assert is_hyper9_message(0x200) is False
