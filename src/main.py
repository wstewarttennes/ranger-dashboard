import asyncio
import logging
import os
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
from src.can.charger import is_charger_message, update_vehicle_state as update_charger_state
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

from src.state.can_monitor import CanMonitor
can_monitor = CanMonitor()

from src.state.telemetry import Telemetry
from src.state.history_db import HistoryDB

# Durable full-res log (offline buffer + HA-statistics backfill source). Created
# when telemetry is on OR the HA-stats sync is enabled (the sync reads from it).
history_db = (
    HistoryDB(config.telemetry.history_db)
    if (config.telemetry.enabled or config.ha_stats.enabled)
    else None
)
telemetry = Telemetry(
    data_dir=config.telemetry.data_dir,
    electricity_rate=config.telemetry.electricity_rate,
    history_interval_s=config.telemetry.history_interval_s,
    history_max_points=config.telemetry.history_max_points,
    db=history_db,
) if config.telemetry.enabled else None

# Apply the configurable RPM->speed factor (tunable via config.yaml, no rebuild)
import src.can.hyper9 as _hyper9
_hyper9.RPM_TO_KMH = config.display.rpm_to_kmh

# F/R selector bit masks for the switch-states word (tunable via config.yaml)
import src.state.vehicle as _vehicle
_vehicle.SWITCH_FWD_MASK = config.display.switch_fwd_mask
_vehicle.SWITCH_REV_MASK = config.display.switch_rev_mask

# Template and static dirs
BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "web" / "templates"))


def on_can_message(arbitration_id: int, data: bytes, timestamp: float):
    """Callback for all CAN messages (from reader or simulator)."""
    # Charger frames are extended IDs not in the DBC — decode them directly.
    if is_charger_message(arbitration_id):
        update_charger_state(vehicle_state, arbitration_id, data)
        return
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
        payload = vehicle_state.to_dict()
        if telemetry is not None:
            payload["telemetry"] = telemetry.to_dict()
        await ws_manager.broadcast(payload)
        await asyncio.sleep(interval)


async def telemetry_loop():
    """Integrate trip/energy, log charge sessions, and sample history."""
    interval = max(config.telemetry.sample_interval_s, 0.2)
    while True:
        await asyncio.sleep(interval)
        try:
            telemetry.tick(vehicle_state, interval)
        except Exception:
            logger.debug("telemetry tick error", exc_info=True)


async def mqtt_publish_loop(publisher):
    """Push retained vehicle state to Home Assistant at the configured rate."""
    interval = 1.0 / max(config.mqtt.publish_rate, 0.1)
    while True:
        try:
            payload = vehicle_state.to_dict()
            if telemetry is not None:
                t = telemetry.to_dict()
                payload.update({
                    "trip_miles": t["trip"]["miles"],
                    "trip_kwh": t["trip"]["kwh"],
                    "trip_efficiency": t["trip"]["efficiency"],
                    "since_charge_miles": t["since_charge"]["miles"],
                    "since_charge_kwh": t["since_charge"]["kwh"],
                    "charge_session_kwh": (t["current_charge"] or {}).get("kwh", 0.0),
                })
            publisher.publish(payload)
        except Exception:
            logger.debug("MQTT publish error", exc_info=True)
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    def on_bms_update(cell_voltages, cell_temps):
        vehicle_state.cell_voltages = list(cell_voltages)
        vehicle_state.cell_temps = list(cell_temps)

    # Start CAN reader(s) or simulator
    simulator: CANSimulator | None = None
    readers: list[CANReader] = []
    def bus_callback(bus_name):
        """Wrap on_can_message so every frame is also logged (with its bus) to
        the raw CAN monitor before it's routed/decoded."""
        def cb(arbitration_id, data, timestamp):
            can_monitor.record(bus_name, arbitration_id, data, timestamp)
            on_can_message(arbitration_id, data, timestamp)
        return cb

    if config.can.interface == "virtual":
        simulator = CANSimulator(on_message=bus_callback("sim"), on_bms_update=on_bms_update)
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
                on_message=bus_callback(bus.channel),
            )
            await reader.start()
            readers.append(reader)

    # Start WebSocket broadcast
    broadcast_task = asyncio.create_task(broadcast_loop())

    # Start telemetry (trip/energy/charge/history) tick loop
    telemetry_task = asyncio.create_task(telemetry_loop()) if telemetry is not None else None

    # Start MQTT publisher (-> Home Assistant), if enabled
    mqtt_publisher = None
    mqtt_task = None
    if config.mqtt.enabled:
        from src.mqtt.publisher import MqttPublisher
        password = config.mqtt.password or os.environ.get("RANGER_MQTT_PASSWORD", "")
        mqtt_publisher = MqttPublisher(
            host=config.mqtt.host,
            port=config.mqtt.port,
            username=config.mqtt.username,
            password=password,
            base_topic=config.mqtt.base_topic,
            discovery_prefix=config.mqtt.discovery_prefix,
            device_name=config.mqtt.device_name,
        )
        mqtt_publisher.start()
        mqtt_task = asyncio.create_task(mqtt_publish_loop(mqtt_publisher))
        logger.info("MQTT publisher enabled -> %s:%s", config.mqtt.host, config.mqtt.port)

    # Start HA long-term statistics backfill, if enabled
    ha_stats_task = None
    if config.ha_stats.enabled and history_db is not None:
        token = config.ha_stats.token or os.environ.get("RANGER_HA_TOKEN", "")
        if not token:
            logger.warning("ha_stats enabled but no token (set RANGER_HA_TOKEN) — skipping")
        else:
            from src.ha.stats_sync import HaStatsSync
            ha_sync = HaStatsSync(
                url=config.ha_stats.url,
                token=token,
                db=history_db,
                source=config.ha_stats.source,
                interval_s=config.ha_stats.sync_interval_s,
                retention_days=config.ha_stats.retention_days,
            )
            ha_stats_task = asyncio.create_task(ha_sync.run())
            logger.info("HA stats backfill enabled -> %s", config.ha_stats.url)

    logger.info(f"Dashboard running on http://{config.server.host}:{config.server.port}")
    yield

    # Shutdown
    broadcast_task.cancel()
    if telemetry_task is not None:
        telemetry_task.cancel()
    if telemetry is not None:
        telemetry._save(force=True)
    if mqtt_task is not None:
        mqtt_task.cancel()
    if mqtt_publisher is not None:
        mqtt_publisher.stop()
    if ha_stats_task is not None:
        ha_stats_task.cancel()
    if history_db is not None:
        history_db.close()
    if simulator is not None:
        await simulator.stop()
    for reader in readers:
        await reader.stop()


# Override route's get_state / get_can_monitor to return our live objects
import src.api.routes as routes_module
routes_module.get_state = lambda: vehicle_state
routes_module.get_can_monitor = lambda: can_monitor
routes_module.get_telemetry = lambda: telemetry

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
