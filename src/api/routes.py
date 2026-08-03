from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.api.websocket import WebSocketManager
from src.state.vehicle import VehicleState

router = APIRouter()
ws_manager = WebSocketManager()


def get_state() -> VehicleState:
    """Overridden by main.py to return the live vehicle state."""
    return VehicleState()


def get_can_monitor():
    """Overridden by main.py to return the live CanMonitor."""
    return None


def get_telemetry():
    """Overridden by main.py to return the live Telemetry."""
    return None


@router.get("/api/state")
async def api_state():
    return get_state().to_dict()


@router.get("/api/health")
async def api_health():
    state = get_state()
    return {
        "status": "ok",
        "can_active": state.last_can_update > 0,
        "comma_connected": state.comma_connected,
        "ws_clients": ws_manager.connection_count,
    }


@router.get("/api/can/raw")
async def api_can_raw():
    """Live raw-CAN sniffer table for the Diagnostics view."""
    mon = get_can_monitor()
    if mon is None:
        return {"frames": [], "buses": {}}
    return {"frames": mon.snapshot(), "buses": mon.stats()}


@router.get("/api/telemetry")
async def api_telemetry():
    t = get_telemetry()
    return t.to_dict() if t else {}


@router.get("/api/charge_sessions")
async def api_charge_sessions():
    t = get_telemetry()
    return {"sessions": t.sessions if t else []}


@router.get("/api/history")
async def api_history():
    t = get_telemetry()
    return {"history": list(t.history) if t else []}


@router.post("/api/trip/reset")
async def api_trip_reset():
    t = get_telemetry()
    if t:
        t.reset_trip()
    return {"ok": True}


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep connection alive, listen for client messages
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
