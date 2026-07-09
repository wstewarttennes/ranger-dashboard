from src.state.vehicle import (
    VehicleState,
    FLAG_FORWARD_ACTIVE,
    FLAG_REVERSE_ACTIVE,
    FLAG_VEHICLE_RUNNING,
    FLAG_TRACTION_ENABLED,
    FLAG_OVERTEMP,
    FLAG_PARK_BRAKE,
)


def test_initial_state():
    state = VehicleState()
    assert state.speed_kmh == 0.0
    assert state.motor_rpm == 0
    assert state.gear == "N"
    assert state.vehicle_running is False
    assert state.power_kw == 0.0


def test_gear_forward(vehicle_state):
    vehicle_state.system_flags = FLAG_FORWARD_ACTIVE
    assert vehicle_state.gear == "D"


def test_gear_reverse(vehicle_state):
    vehicle_state.system_flags = FLAG_REVERSE_ACTIVE
    assert vehicle_state.gear == "R"


def test_gear_neutral(vehicle_state):
    vehicle_state.system_flags = 0
    assert vehicle_state.gear == "N"


def test_vehicle_running(vehicle_state):
    vehicle_state.system_flags = FLAG_VEHICLE_RUNNING | FLAG_TRACTION_ENABLED
    assert vehicle_state.vehicle_running is True
    assert vehicle_state.traction_enabled is True


def test_overtemp(vehicle_state):
    vehicle_state.system_flags = FLAG_OVERTEMP
    assert vehicle_state.overtemp is True


def test_park_brake(vehicle_state):
    vehicle_state.system_flags = FLAG_PARK_BRAKE
    assert vehicle_state.park_brake is True


def test_power_kw(vehicle_state):
    vehicle_state.dc_bus_voltage = 165.0
    vehicle_state.dc_bus_current = 100.0
    assert vehicle_state.power_kw == 16.5


def test_power_kw_regen(vehicle_state):
    vehicle_state.dc_bus_voltage = 168.0
    vehicle_state.dc_bus_current = -20.0
    assert vehicle_state.power_kw == pytest.approx(-3.36)


def test_speed_mph(vehicle_state):
    vehicle_state.speed_kmh = 100.0
    assert vehicle_state.speed_mph == pytest.approx(62.1371, rel=1e-3)


def test_cell_voltage_stats(vehicle_state):
    # Set some cells
    vehicle_state.cell_voltages = [3.8] * 42
    vehicle_state.cell_voltages[0] = 3.75
    vehicle_state.cell_voltages[41] = 3.85

    assert vehicle_state.min_cell_v == 3.75
    assert vehicle_state.max_cell_v == 3.85
    assert vehicle_state.cell_delta_mv == pytest.approx(100.0, abs=0.1)


def test_cell_voltage_stats_empty(vehicle_state):
    # All zeros (no data)
    assert vehicle_state.min_cell_v == 0.0
    assert vehicle_state.max_cell_v == 0.0
    assert vehicle_state.cell_delta_mv == 0.0


def test_to_dict(vehicle_state):
    vehicle_state.speed_kmh = 50.0
    vehicle_state.motor_rpm = 2000
    vehicle_state.dc_bus_voltage = 165.0
    vehicle_state.dc_bus_current = 50.0
    vehicle_state.system_flags = FLAG_FORWARD_ACTIVE | FLAG_VEHICLE_RUNNING

    d = vehicle_state.to_dict()
    assert d["speed_kmh"] == 50.0
    assert d["speed_mph"] == pytest.approx(31.07, abs=0.1)
    assert d["motor_rpm"] == 2000
    assert d["power_kw"] == 8.25
    assert d["gear"] == "D"
    assert d["vehicle_running"] is True
    assert "timestamp" in d


def test_fault_level_str(vehicle_state):
    vehicle_state.fault_level = 0
    assert vehicle_state.fault_level_str == "Ready"
    vehicle_state.fault_level = 1
    assert vehicle_state.fault_level_str == "Blocking"
    vehicle_state.fault_level = 4
    assert vehicle_state.fault_level_str == "Warning"


import pytest
