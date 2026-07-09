import asyncio
import json
import logging

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Manages WebSocket connections and broadcasts vehicle state."""

    def __init__(self):
        self._connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self._connections.append(websocket)
        logger.info(f"WebSocket connected ({len(self._connections)} total)")

    def disconnect(self, websocket: WebSocket):
        self._connections.remove(websocket)
        logger.info(f"WebSocket disconnected ({len(self._connections)} total)")

    async def broadcast(self, data: dict):
        """Send JSON data to all connected clients."""
        if not self._connections:
            return

        message = json.dumps(data)
        disconnected = []

        for ws in self._connections:
            try:
                await ws.send_text(message)
            except Exception:
                disconnected.append(ws)

        for ws in disconnected:
            self._connections.remove(ws)

    @property
    def connection_count(self) -> int:
        return len(self._connections)
