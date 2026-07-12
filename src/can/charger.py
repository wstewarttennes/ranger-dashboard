"""Decode Thunderstruck TSM2500 charger CAN frames.

The MCU commands the charger on 0x18E54024 (extended) and the charger replies
on 0x18EB2440 (extended). Byte layout of the reply was reverse-engineered live
against the MCU's `trace charger` output:

  0x18EB2440:  [00 00] [VV VV] [cnt] [AA] [TT] [FF]
    bytes 2-3  little-endian /10  -> charge voltage (V)   e.g. 0x051F = 131.1 V
    byte  5                        -> charge current (A)   (~setpoint, ≈actual)
    byte  6    minus 40            -> charger temperature (°C)  e.g. 81 -> 41 C
    byte  4                        -> rolling message counter (ignored)

Verified: reply 00 00 1F 05 15 0C 51 FF <-> trace "V=131.1 A=11 TMP=41".
"""
from __future__ import annotations

import time

from src.state.vehicle import VehicleState

CHARGER_REPLY_ID = 0x18EB2440   # charger -> MCU (status)
CHARGER_CMD_ID = 0x18E54024     # MCU -> charger (command)

CHARGER_IDS = {CHARGER_REPLY_ID, CHARGER_CMD_ID}


def is_charger_message(arbitration_id: int) -> bool:
    return arbitration_id in CHARGER_IDS


def update_vehicle_state(state: VehicleState, arbitration_id: int, data: bytes):
    """Update charge fields from a TSM2500 charger reply frame."""
    if arbitration_id != CHARGER_REPLY_ID or len(data) < 7:
        return
    state.charge_voltage = ((data[3] << 8) | data[2]) / 10.0
    state.charge_current = float(data[5])
    state.charger_temp_c = float(data[6]) - 40.0
    state.last_charge_update = time.time()  # `charging` property uses this to auto-clear
    state.last_can_update = time.time()
