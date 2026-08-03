from pathlib import Path
from pydantic import BaseModel
import yaml


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8088


class BusConfig(BaseModel):
    """One physical CAN bus (one channel on the 2-CH HAT)."""
    channel: str
    bitrate: int = 250000


class CANConfig(BaseModel):
    # interface: "virtual" = in-process simulator (dev); "socketcan" = real HAT.
    # (A raw channel name like "can0" is still accepted for backward compat.)
    interface: str = "virtual"
    bitrate: int = 500000  # legacy single-bus fallback bitrate
    # Preferred: one entry per physical CAN bus. The Ranger runs two:
    #   can0 @ 250k = Thunderstruck battery/charge bus (MCU + TSM2500)
    #   can1 @ ???  = X1 / Hyper9 motor bus (verify baud in SmartView)
    buses: list[BusConfig] = []
    dbc_files: list[str] = ["dbc/hyper9.dbc", "dbc/thunderstruck_mcu.dbc"]

    def resolved_buses(self) -> list[BusConfig]:
        """SocketCAN buses to open. Prefers `buses`; else falls back to a single
        bus from {interface, bitrate} when interface names a real channel."""
        if self.buses:
            return self.buses
        if self.interface not in ("virtual", "socketcan"):
            return [BusConfig(channel=self.interface, bitrate=self.bitrate)]
        return []


class CommaConfig(BaseModel):
    host: str = "192.168.1.100"
    port: int = 5001
    cameras: list[str] = ["road"]
    services: list[str] = ["carState", "selfdriveState", "deviceState"]


class DisplayConfig(BaseModel):
    update_rate: int = 20
    units: str = "imperial"
    # Motor RPM -> road speed factor (km/h per rpm). Tune against GPS: if the
    # dash reads high by X%, multiply this by (actual/displayed). Restart the
    # container after changing (config.yaml is a mounted volume — no rebuild).
    rpm_to_kmh: float = 0.0167
    # F/R selector bit masks within the X1 switch-states word (0x485 slot 2).
    # 0 = uncalibrated (gear falls back to signed RPM). Calibrate by flipping
    # the selector and watching switch_states_raw in /api/state.
    switch_fwd_mask: int = 0
    switch_rev_mask: int = 0


class MqttConfig(BaseModel):
    """Publish vehicle state to Home Assistant over MQTT (retained, auto-discovered).

    Password is read from config OR the RANGER_MQTT_PASSWORD env var (preferred,
    so it stays out of git). Host is the HA/Mosquitto broker address on the LAN.
    """
    enabled: bool = False
    host: str = "192.168.1.153"      # HA host running the Mosquitto add-on
    port: int = 1883
    username: str = "ranger"
    password: str = ""               # prefer env RANGER_MQTT_PASSWORD
    base_topic: str = "ranger"
    discovery_prefix: str = "homeassistant"
    device_name: str = "Ranger EV"
    publish_rate: float = 1.0        # Hz — retained state pushes to the broker


class TelemetryConfig(BaseModel):
    """Trip/energy tracking, charge logging, and time-series history."""
    enabled: bool = True
    data_dir: str = "data"               # persisted under /app/data (mounted volume)
    electricity_rate: float = 0.30       # $/kWh for charge-session cost estimates
    history_interval_s: float = 10.0     # seconds between time-series samples
    history_max_points: int = 8640       # ~24h at 10s spacing (live Graphs view)
    sample_interval_s: float = 1.0       # trip/energy integration tick
    # Durable, full-resolution log (SQLite) — offline buffer + HA backfill source.
    # Written every history_interval_s; never rolls off (see ha_stats.retention_days).
    history_db: str = "data/history.db"


class HaStatsConfig(BaseModel):
    """Backfill the Pi's durable history into Home Assistant long-term statistics.

    Lets a drive with no wifi land in HA (correctly time-stamped) once you're
    home. Token comes from config OR the RANGER_HA_TOKEN env var (preferred).
    Create a long-lived token in HA: profile → Security → Long-lived access tokens.
    """
    enabled: bool = False
    url: str = "http://192.168.1.153:8123"   # HA base URL on the LAN
    token: str = ""                          # prefer env RANGER_HA_TOKEN
    source: str = "ranger"                   # external statistic_id prefix -> ranger:<metric>
    sync_interval_s: float = 600.0           # how often to push complete hours
    retention_days: int = 0                  # prune SQLite older than N days (0 = keep forever)


class AppConfig(BaseModel):
    server: ServerConfig = ServerConfig()
    can: CANConfig = CANConfig()
    comma: CommaConfig = CommaConfig()
    display: DisplayConfig = DisplayConfig()
    mqtt: MqttConfig = MqttConfig()
    telemetry: TelemetryConfig = TelemetryConfig()
    ha_stats: HaStatsConfig = HaStatsConfig()


def load_config(config_path: Path | None = None) -> AppConfig:
    if config_path is None:
        config_path = Path(__file__).parent.parent / "config.yaml"

    if config_path.exists():
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}
        return AppConfig(**data)

    return AppConfig()
