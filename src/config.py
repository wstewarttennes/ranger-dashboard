from pathlib import Path
from pydantic import BaseModel
import yaml


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8088


class CANConfig(BaseModel):
    interface: str = "virtual"
    bitrate: int = 500000
    dbc_files: list[str] = ["dbc/hyper9.dbc", "dbc/thunderstruck_mcu.dbc"]


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
