import struct
import pytest

from src.state.vehicle import VehicleState


@pytest.fixture
def vehicle_state():
    return VehicleState()


@pytest.fixture
def hyper9_status_data():
    """HYPER9_STATUS (0x181): speed=45.2 km/h, soc=82%, flags=running+forward+traction, fault=0"""
    from src.state.vehicle import FLAG_VEHICLE_RUNNING, FLAG_FORWARD_ACTIVE, FLAG_TRACTION_ENABLED
    speed_raw = int(45.2 * 10)  # 452
    soc = 82
    flags = FLAG_VEHICLE_RUNNING | FLAG_FORWARD_ACTIVE | FLAG_TRACTION_ENABLED
    fault = 0
    return struct.pack("<hBHBxx", speed_raw, soc, flags, fault)


@pytest.fixture
def hyper9_power_data():
    """HYPER9_POWER (0x182): voltage=165.3V, current=74.2A, motor_current=89.0A"""
    voltage_raw = int(165.3 * 10)
    current_raw = int(74.2 * 10)
    motor_current_raw = int(89.0 * 10)
    return struct.pack("<hhhxx", voltage_raw, current_raw, motor_current_raw)


@pytest.fixture
def hyper9_motor_data():
    """HYPER9_MOTOR (0x183): rpm=2100, motor_temp=52C, inverter_temp=45C, throttle=35%, torque=28%"""
    rpm = 2100
    motor_temp = 52 + 40  # offset
    inverter_temp = 45 + 40
    throttle = 35
    torque = 28
    return struct.pack("<hBBbhx", rpm, motor_temp, inverter_temp, throttle, torque)


@pytest.fixture
def hyper9_extended_data():
    """HYPER9_EXTENDED (0x184): fault_level=0, motor_flags=0"""
    return struct.pack("<BHxxxxx", 0, 0)
