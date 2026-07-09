import asyncio
import logging
import time
from typing import Callable

logger = logging.getLogger(__name__)


class CANReader:
    """Async CAN bus reader using python-can with SocketCAN backend."""

    def __init__(self, interface: str, bitrate: int, on_message: Callable):
        self.interface = interface
        self.bitrate = bitrate
        self.on_message = on_message
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self):
        if self.interface == "virtual":
            logger.info("CAN interface set to 'virtual' - using in-process simulator")
            return

        try:
            import can
            self._bus = can.Bus(
                interface="socketcan",
                channel=self.interface,
                bitrate=self.bitrate,
            )
            self._running = True
            self._task = asyncio.create_task(self._read_loop())
            logger.info(f"CAN reader started on {self.interface} at {self.bitrate} bps")
        except Exception as e:
            logger.error(f"Failed to open CAN interface '{self.interface}': {e}")
            logger.info("Falling back to virtual mode (no CAN data)")

    async def _read_loop(self):
        loop = asyncio.get_event_loop()
        while self._running:
            try:
                msg = await loop.run_in_executor(None, self._bus.recv, 0.1)
                if msg is not None:
                    self.on_message(msg.arbitration_id, msg.data, time.time())
            except Exception as e:
                if self._running:
                    logger.error(f"CAN read error: {e}")
                    await asyncio.sleep(0.1)

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if hasattr(self, "_bus"):
            self._bus.shutdown()
            logger.info("CAN reader stopped")
