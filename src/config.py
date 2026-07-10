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


class AppConfig(BaseModel):
    server: ServerConfig = ServerConfig()
    can: CANConfig = CANConfig()
    comma: CommaConfig = CommaConfig()
    display: DisplayConfig = DisplayConfig()


def load_config(config_path: Path | None = None) -> AppConfig:
    if config_path is None:
        config_path = Path(__file__).parent.parent / "config.yaml"

    if config_path.exists():
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}
        return AppConfig(**data)

    return AppConfig()
