import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request

from src.config import load_config
from src.state.vehicle import VehicleState
from src.can.parser import CANParser
from src.can.hyper9 import is_hyper9_message, update_vehicle_state as update_hyper9_state
from src.can.bms import is_bms_message, update_vehicle_state as update_bms_state
from src.can.reader import CANReader
from src.can.simulator import CANSimulator
from src.api.routes import router, ws_manager, get_state as _unused
from src.comma.proxy import comma_router
from src.api.terminal import terminal_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Global state
config = load_config()
vehicle_state = VehicleState()
can_parser = CANParser(config.can.dbc_files)

# Template and static dirs
BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "web" / "templates"))


def on_can_message(arbitration_id: int, data: bytes, timestamp: float):
    """Callback for all CAN messages (from reader or simulator)."""
    signals = can_parser.decode(arbitration_id, data)
    if signals is None:
        return
    if is_hyper9_message(arbitration_id):
        update_hyper9_state(vehicle_state, arbitration_id, signals)
    elif is_bms_message(arbitration_id):
        update_bms_state(vehicle_state, arbitration_id, signals)


async def broadcast_loop():
    """Push vehicle state to all WebSocket clients at configured rate."""
    interval = 1.0 / config.display.update_rate
    while True:
        await ws_manager.broadcast(vehicle_state.to_dict())
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    def on_bms_update(cell_voltages, cell_temps):
        vehicle_state.cell_voltages = list(cell_voltages)
        vehicle_state.cell_temps = list(cell_temps)

    # Start CAN reader(s) or simulator
    simulator: CANSimulator | None = None
    readers: list[CANReader] = []
    if config.can.interface == "virtual":
        simulator = CANSimulator(on_message=on_can_message, on_bms_update=on_bms_update)
        await simulator.start()
    else:
        buses = config.can.resolved_buses()
        if not buses:
            logger.warning("No CAN buses configured (can.buses is empty) — no live data")
        for bus in buses:
            # All buses feed the same callback; on_can_message routes by
            # arbitration ID (Hyper9 0x181-0x184 vs BMS 0x351-0x35B don't overlap),
            # so a frame is handled correctly regardless of which bus it arrived on.
            reader = CANReader(
                interface=bus.channel,
                bitrate=bus.bitrate,
                on_message=on_can_message,
            )
            await reader.start()
            readers.append(reader)

    # Start WebSocket broadcast
    broadcast_task = asyncio.create_task(broadcast_loop())

    logger.info(f"Dashboard running on http://{config.server.host}:{config.server.port}")
    yield

    # Shutdown
    broadcast_task.cancel()
    if simulator is not None:
        await simulator.stop()
    for reader in readers:
        await reader.stop()


# Override route's get_state to return our live state
import src.api.routes as routes_module
routes_module.get_state = lambda: vehicle_state

app = FastAPI(title="Ranger Dashboard", lifespan=lifespan)
app.include_router(router)
app.include_router(comma_router)
app.include_router(terminal_router)

# Serve static files
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "web" / "static")), name="static")


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        context={
            "units": config.display.units,
            "comma_host": config.comma.host,
        },
    )


def main():
    import uvicorn
    uvicorn.run(
        "src.main:app",
        host=config.server.host,
        port=config.server.port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
