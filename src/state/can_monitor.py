"""Live raw-CAN frame monitor.

Tracks every arbitration ID seen on every bus — decoded or not — with its
last payload, total count, refresh rate (Hz) and staleness. This is the data
behind the Diagnostics -> "CAN Raw" sniffer view, and it's the single most
useful tool for debugging the car: you can see *any* frame on the wire, even
ones the dashboard doesn't decode.
"""
from __future__ import annotations

import time


class CanMonitor:
    def __init__(self) -> None:
        # key: (bus, arbitration_id) -> stats dict
        self._frames: dict[tuple[str, int], dict] = {}

    def record(self, bus: str, arbitration_id: int, data: bytes, ts: float) -> None:
        key = (bus, arbitration_id)
        entry = self._frames.get(key)
        if entry is None:
            self._frames[key] = {
                "bus": bus,
                "id": arbitration_id,
                "count": 1,
                "last_ts": ts,
                "hz": 0.0,
                "data": bytes(data),
            }
            return
        dt = ts - entry["last_ts"]
        if dt > 0:
            inst_hz = 1.0 / dt
            # Exponential moving average smooths the per-frame jitter.
            entry["hz"] = 0.7 * entry["hz"] + 0.3 * inst_hz
        entry["count"] += 1
        entry["last_ts"] = ts
        entry["data"] = bytes(data)

    def snapshot(self) -> list[dict]:
        """Current table, sorted by bus then ID, JSON-ready for the UI."""
        now = time.time()
        rows = []
        for entry in self._frames.values():
            age = now - entry["last_ts"]
            stale = age > 2.0
            rows.append({
                "bus": entry["bus"],
                "id_hex": f"{entry['id']:X}",
                "id": entry["id"],
                "extended": entry["id"] > 0x7FF,
                "dlc": len(entry["data"]),
                "data": entry["data"].hex(" ").upper(),
                "count": entry["count"],
                "hz": 0.0 if stale else round(entry["hz"], 1),
                "age_ms": round(age * 1000),
                "stale": stale,
            })
        rows.sort(key=lambda r: (r["bus"], r["id"]))
        return rows

    def stats(self) -> dict:
        """Per-bus summary: unique IDs and total Hz (aggregate frame rate)."""
        now = time.time()
        buses: dict[str, dict] = {}
        for entry in self._frames.values():
            age = now - entry["last_ts"]
            b = buses.setdefault(entry["bus"], {"ids": 0, "hz": 0.0, "live": 0})
            b["ids"] += 1
            if age <= 2.0:
                b["hz"] += entry["hz"]
                b["live"] += 1
        for b in buses.values():
            b["hz"] = round(b["hz"], 1)
        return buses
