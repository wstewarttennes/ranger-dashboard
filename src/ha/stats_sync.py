"""Backfill the Pi's durable history into Home Assistant long-term statistics.

Home Assistant will not accept back-dated *state* over MQTT (it stamps every
message with receive time). The only supported way to land correctly-timed
history is the recorder's statistics import. So we:

  1. keep a full-resolution log on the Pi (history_db, offline-safe), then
  2. aggregate it to hourly mean/min/max and push it via the
     `recorder/import_statistics` websocket command as *external* statistics
     (statistic_id `ranger:<metric>`, source `ranger`).

The import is idempotent — re-importing an hour overwrites it — so we simply
advance a high-water mark on success and any gap (a drive with no wifi) is
filled the next time HA is reachable. External statistics don't collide with
the live `sensor.ranger_*` entities HA builds from MQTT; they show up in the
Statistics graph card and the Energy dashboard.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time

import websockets

from src.state.history_db import HistoryDB, METRICS

logger = logging.getLogger(__name__)

# col -> (friendly, unit) for building statistic metadata
_META = {col: (friendly, unit) for col, _dkey, friendly, unit in METRICS}


def _ws_url(http_url: str) -> str:
    url = http_url.rstrip("/")
    if url.startswith("https"):
        url = "wss" + url[len("https"):]
    elif url.startswith("http"):
        url = "ws" + url[len("http"):]
    return url + "/api/websocket"


def build_messages(hourly: dict[str, list[dict]], source: str) -> list[dict]:
    """Turn {col: [{start, mean, min, max}...]} into import_statistics payloads.

    `start` epoch hours are rendered as timezone-aware UTC ISO strings, which
    HA requires (and must be hour-aligned, which the aggregation guarantees).
    """
    from datetime import datetime, timezone

    messages: list[dict] = []
    for col, rows in hourly.items():
        if not rows:
            continue
        friendly, unit = _META.get(col, (col, None))
        stats = [
            {
                "start": datetime.fromtimestamp(r["start"], tz=timezone.utc).isoformat(),
                "mean": round(r["mean"], 3),
                "min": round(r["min"], 3),
                "max": round(r["max"], 3),
            }
            for r in rows
        ]
        meta = {
            "has_mean": True,
            "has_sum": False,
            "name": f"Ranger {friendly}",
            "source": source,
            "statistic_id": f"{source}:{col}",
        }
        if unit:
            meta["unit_of_measurement"] = unit
        messages.append({"type": "recorder/import_statistics",
                         "metadata": meta, "stats": stats})
    return messages


class HaStatsSync:
    def __init__(self, url: str, token: str, db: HistoryDB,
                 source: str = "ranger", interval_s: float = 600.0,
                 retention_days: int = 0):
        self.url = url
        self.token = token
        self.db = db
        self.source = source
        self.interval_s = interval_s
        self.retention_days = retention_days

    async def _import(self, messages: list[dict]) -> bool:
        """Open a websocket, auth, and send each import command. Returns True
        only if all commands were accepted."""
        try:
            async with websockets.connect(_ws_url(self.url),
                                          open_timeout=10, close_timeout=5) as ws:
                # auth handshake
                await asyncio.wait_for(ws.recv(), timeout=10)  # auth_required
                await ws.send(json.dumps({"type": "auth", "access_token": self.token}))
                auth = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
                if auth.get("type") != "auth_ok":
                    logger.error("HA stats: auth failed (%s)", auth.get("type"))
                    return False
                ok = True
                for i, msg in enumerate(messages, start=1):
                    msg = {**msg, "id": i}
                    await ws.send(json.dumps(msg))
                    res = json.loads(await asyncio.wait_for(ws.recv(), timeout=15))
                    if not res.get("success"):
                        ok = False
                        logger.warning("HA stats: import failed for %s: %s",
                                       msg["metadata"]["statistic_id"],
                                       res.get("error"))
                return ok
        except Exception as e:
            # Offline / HA down / token bad — stay quiet-ish and retry later.
            logger.info("HA stats: sync deferred (%s)", e)
            return False

    async def sync_once(self) -> int:
        """Push all complete hours since the high-water mark. Returns the number
        of hours synced (0 if nothing to do or HA unreachable)."""
        now_hour = (int(time.time()) // 3600) * 3600   # exclude in-progress hour
        hwm = self.db.get_hwm()
        if hwm is None:
            earliest = self.db.earliest_hour()
            if earliest is None:
                return 0
            hwm = earliest
        if hwm >= now_hour:
            return 0

        hourly = self.db.hourly(hwm, now_hour)
        if not hourly:
            # No samples in the window, but time advanced — move the mark so we
            # don't re-scan an empty range forever.
            self.db.set_hwm(now_hour)
            return 0

        messages = build_messages(hourly, self.source)
        if not await self._import(messages):
            return 0

        self.db.set_hwm(now_hour)
        if self.retention_days:
            self.db.prune(self.retention_days)
        n_hours = (now_hour - hwm) // 3600
        logger.info("HA stats: synced ~%d h across %d metrics", n_hours, len(messages))
        return n_hours

    async def run(self) -> None:
        # small startup delay so CAN/telemetry are up first
        await asyncio.sleep(15)
        while True:
            try:
                await self.sync_once()
            except Exception:
                logger.debug("HA stats: sync_once error", exc_info=True)
            await asyncio.sleep(self.interval_s)
