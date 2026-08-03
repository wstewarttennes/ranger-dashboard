"""Durable, full-resolution telemetry log (SQLite) + hourly aggregation.

This is the *offline buffer and source of truth*. Every history sample is
appended here regardless of network state, so a drive with no wifi is never
lost. Retention is effectively unlimited (optional day-based prune); the old
bounded `history.json` deque still backs the live Graphs view, but the durable
record lives here and is what gets backfilled into Home Assistant.

The same METRICS list drives three things so they can't drift apart:
  1. the SQLite columns,
  2. what we sample each tick,
  3. what we export to HA long-term statistics.
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

# col        -> VehicleState.to_dict() key   friendly (HA)      unit
# All are "measurement" metrics: HA statistics get mean/min/max (has_mean).
METRICS: list[tuple[str, str, str, str]] = [
    ("soc",        "soc_pct",           "SoC",            "%"),
    ("power_kw",   "power_kw",          "Power",          "kW"),
    ("pack_v",     "pack_voltage",      "Pack Voltage",   "V"),
    ("pack_a",     "pack_current",      "Pack Current",   "A"),
    ("bus_v",      "dc_bus_voltage",    "Bus Voltage",    "V"),
    ("bus_a",      "dc_bus_current",    "Bus Current",    "A"),
    ("speed",      "speed_mph",         "Speed",          "mph"),
    ("motor_rpm",  "motor_rpm",         "Motor RPM",      "rpm"),
    ("motor_c",    "motor_temp_c",      "Motor Temp",     "°C"),
    ("inv_c",      "inverter_temp_c",   "Inverter Temp",  "°C"),
    ("chg_c",      "charger_temp_c",    "Charger Temp",   "°C"),
    ("pack_c",     "pack_temperature",  "Pack Temp",      "°C"),
    ("min_cell",   "min_cell_v",        "Min Cell",       "V"),
    ("max_cell",   "max_cell_v",        "Max Cell",       "V"),
    ("cell_delta", "cell_delta_mv",     "Cell Delta",     "mV"),
    ("charge_w",   "charge_watts",      "Charge Power",   "W"),
    ("throttle",   "throttle_pct",      "Throttle",       "%"),
    ("key_v",      "key_switch_voltage","12V Supply",     "V"),
]

_COLS = [m[0] for m in METRICS]
_HWM_KEY = "stats_hwm"   # highest hour (epoch, hour-aligned) already synced to HA


class HistoryDB:
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: written from the asyncio telemetry loop and
        # read from the sync task; guard writes with the connection's own lock.
        self._db = sqlite3.connect(str(self.path), check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()

    def _init_schema(self) -> None:
        cols_ddl = ", ".join(f"{c} REAL" for c in _COLS)
        self._db.execute(
            f"CREATE TABLE IF NOT EXISTS samples ("
            f"ts INTEGER NOT NULL, {cols_ddl})"
        )
        self._db.execute("CREATE INDEX IF NOT EXISTS idx_samples_ts ON samples(ts)")
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS sync_state (k TEXT PRIMARY KEY, v INTEGER)"
        )
        # Additive migration: add any METRICS column missing from an older DB.
        existing = {row[1] for row in self._db.execute("PRAGMA table_info(samples)")}
        for c in _COLS:
            if c not in existing:
                self._db.execute(f"ALTER TABLE samples ADD COLUMN {c} REAL")
        self._db.commit()

    # ---- write -------------------------------------------------------
    def insert(self, ts: int, values: dict) -> None:
        """Append one sample. `values` is keyed by VehicleState.to_dict() keys;
        missing/None values are stored as NULL."""
        row = [ts] + [values.get(dkey) for _, dkey, _, _ in METRICS]
        placeholders = ",".join("?" * (len(_COLS) + 1))
        self._db.execute(
            f"INSERT INTO samples (ts, {','.join(_COLS)}) VALUES ({placeholders})",
            row,
        )
        self._db.commit()

    def prune(self, older_than_days: int) -> None:
        if older_than_days <= 0:
            return
        cutoff = int(time.time()) - older_than_days * 86400
        self._db.execute("DELETE FROM samples WHERE ts < ?", (cutoff,))
        self._db.commit()

    # ---- sync watermark ---------------------------------------------
    def get_hwm(self) -> int | None:
        r = self._db.execute(
            "SELECT v FROM sync_state WHERE k=?", (_HWM_KEY,)
        ).fetchone()
        return r[0] if r else None

    def set_hwm(self, hour_epoch: int) -> None:
        self._db.execute(
            "INSERT INTO sync_state (k, v) VALUES (?, ?) "
            "ON CONFLICT(k) DO UPDATE SET v=excluded.v",
            (_HWM_KEY, hour_epoch),
        )
        self._db.commit()

    def earliest_hour(self) -> int | None:
        r = self._db.execute("SELECT MIN(ts) FROM samples").fetchone()
        if not r or r[0] is None:
            return None
        return (int(r[0]) // 3600) * 3600

    # ---- read: hourly aggregation for HA statistics ------------------
    def hourly(self, start_hour: int, end_hour: int) -> dict[str, list[dict]]:
        """Aggregate [start_hour, end_hour) into hourly mean/min/max per metric.

        Returns {col: [{"start": epoch_hour, "mean", "min", "max"}, ...]}.
        Hours where a metric is entirely NULL are omitted for that metric.
        """
        if end_hour <= start_hour:
            return {}
        aggs = ", ".join(
            f"AVG({c}), MIN({c}), MAX({c})" for c in _COLS
        )
        sql = (
            f"SELECT (ts/3600) AS hr, {aggs} FROM samples "
            f"WHERE ts >= ? AND ts < ? GROUP BY hr ORDER BY hr"
        )
        out: dict[str, list[dict]] = {c: [] for c in _COLS}
        for row in self._db.execute(sql, (start_hour, end_hour)):
            hr = int(row[0]) * 3600
            for i, c in enumerate(_COLS):
                mean, mn, mx = row[1 + i * 3], row[2 + i * 3], row[3 + i * 3]
                if mean is None:
                    continue
                out[c].append({"start": hr, "mean": mean, "min": mn, "max": mx})
        return {c: v for c, v in out.items() if v}

    def close(self) -> None:
        try:
            self._db.close()
        except Exception:
            pass
