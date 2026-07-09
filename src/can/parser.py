import logging
from pathlib import Path

import cantools.database

logger = logging.getLogger(__name__)


class CANParser:
    """Loads DBC files and decodes CAN messages."""

    def __init__(self, dbc_paths: list[str], base_dir: Path | None = None):
        self.db = cantools.database.Database()
        if base_dir is None:
            base_dir = Path(__file__).parent.parent.parent

        for dbc_path in dbc_paths:
            full_path = base_dir / dbc_path
            if full_path.exists():
                self.db.add_dbc_file(str(full_path))
                logger.info(f"Loaded DBC: {full_path}")
            else:
                logger.warning(f"DBC file not found: {full_path}")

        self._id_to_message = {}
        for msg in self.db.messages:
            self._id_to_message[msg.frame_id] = msg

    def decode(self, arbitration_id: int, data: bytes) -> dict | None:
        """Decode a CAN message. Returns signal dict or None if unknown ID."""
        msg = self._id_to_message.get(arbitration_id)
        if msg is None:
            return None

        try:
            return self.db.decode_message(arbitration_id, data, decode_choices=False)
        except Exception as e:
            logger.debug(f"Failed to decode 0x{arbitration_id:03X}: {e}")
            return None

    def get_message_name(self, arbitration_id: int) -> str | None:
        msg = self._id_to_message.get(arbitration_id)
        return msg.name if msg else None
