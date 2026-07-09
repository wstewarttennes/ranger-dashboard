import pytest
from starlette.testclient import TestClient

from src.state.vehicle import VehicleState, FLAG_FORWARD_ACTIVE, FLAG_VEHICLE_RUNNING


@pytest.fixture
def client():
    """Create test client with mock state."""
    from src.main import app
    import src.api.routes as routes_module

    test_state = VehicleState()
    test_state.speed_kmh = 60.0
    test_state.motor_rpm = 2500
    test_state.dc_bus_voltage = 165.0
    test_state.dc_bus_current = 80.0
    test_state.soc_pct = 78.0
    test_state.system_flags = FLAG_FORWARD_ACTIVE | FLAG_VEHICLE_RUNNING

    routes_module.get_state = lambda: test_state

    with TestClient(app) as c:
        yield c


def test_api_state(client):
    resp = client.get("/api/state")
    assert resp.status_code == 200
    data = resp.json()

    assert data["speed_kmh"] == 60.0
    assert data["motor_rpm"] == 2500
    assert data["dc_bus_voltage"] == 165.0
    assert data["gear"] == "D"
    assert data["vehicle_running"] is True
    assert data["soc_pct"] == 78.0
    assert "timestamp" in data


def test_api_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()

    assert "status" in data
    assert data["status"] == "ok"
    assert "ws_clients" in data


def test_index_page(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Ranger EV" in resp.text
    assert "dashboard" in resp.text
