from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.api.websocket import WebSocketManager
from src.state.vehicle import VehicleState

router = APIRouter()
ws_manager = WebSocketManager()


def get_state() -> VehicleState:
    """Overridden by main.py to return the live vehicle state."""
    return VehicleState()


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


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep connection alive, listen for client messages
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
