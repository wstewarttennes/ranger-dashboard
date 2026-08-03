"""Trip/energy tracking, charge-session logging, and time-series history.

All three are driven by a single ~1 Hz tick() from the main loop and persisted
to the mounted /app/data volume so they survive restarts:

  data/trip.json            -> trip + since-charge distance/energy accumulators
  data/charge_sessions.json -> list of completed charge sessions
  data/history.json         -> downsampled time-series for the graphs view

Distance integrates speed (mph -> miles); energy integrates DC-bus power
(kW -> kWh, positive = discharge). Efficiency is miles / net kWh discharged.
"""
from __future__ import annotations

import json
import time
from collections import deque
from pathlib import Path


class Telemetry:
    def __init__(self, data_dir: str, electricity_rate: float,
                 history_interval_s: float, history_max_points: int,
                 db=None):
        self.dir = Path(data_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.rate = electricity_rate
        self.history_interval_s = history_interval_s
        # Durable, full-res SQLite log (offline buffer + HA backfill source).
        # Optional so the trip/charge logic keeps working without it.
        self.db = db

        # Distance/energy accumulators. "trip" is user-resettable; "since_charge"
        # auto-resets whenever a charge session completes.
        self.trip = {"miles": 0.0, "kwh": 0.0, "regen_kwh": 0.0, "seconds": 0.0}
        self.since_charge = {"miles": 0.0, "kwh": 0.0, "regen_kwh": 0.0, "seconds": 0.0}

        self.sessions: list[dict] = []
        self.history: deque = deque(maxlen=history_max_points)

        self._charging = False
        self._session: dict | None = None   # in-progress charge session
        self._last_history_t = 0.0
        self._last_save_t = 0.0

        self._load()

    # ---- persistence -------------------------------------------------
    def _load(self):
        try:
            t = json.loads((self.dir / "trip.json").read_text())
            self.trip = t.get("trip", self.trip)
            self.since_charge = t.get("since_charge", self.since_charge)
        except Exception:
            pass
        try:
            self.sessions = json.loads((self.dir / "charge_sessions.json").read_text())
        except Exception:
            self.sessions = []
        try:
            for s in json.loads((self.dir / "history.json").read_text()):
                self.history.append(s)
        except Exception:
            pass

    def _save(self, force=False):
        now = time.time()
        if not force and (now - self._last_save_t) < 30.0:
            return
        self._last_save_t = now
        try:
            (self.dir / "trip.json").write_text(json.dumps(
                {"trip": self.trip, "since_charge": self.since_charge}))
            (self.dir / "history.json").write_text(json.dumps(list(self.history)))
        except Exception:
            pass

    def _save_sessions(self):
        try:
            (self.dir / "charge_sessions.json").write_text(json.dumps(self.sessions))
        except Exception:
            pass

    # ---- main tick ---------------------------------------------------
    def tick(self, state, dt: float):
        now = time.time()

        # Charge session edge detection
        charging = bool(state.charging)
        if charging and not self._charging:
            self._start_session(state, now)
        elif not charging and self._charging:
            self._end_session(state, now)
        self._charging = charging

        if charging and self._session is not None:
            # integrate energy INTO the pack (charger watts -> kWh)
            self._session["kwh"] += (state.charge_watts / 1000.0) * (dt / 3600.0)
            self._session["end_soc"] = round(state.soc_pct, 1)
            self._session["peak_w"] = max(self._session["peak_w"], round(state.charge_watts))
            self._session["max_temp"] = max(self._session["max_temp"], round(state.charger_temp_c, 1))
        else:
            # Driving: integrate distance + energy out of the pack
            miles = state.speed_mph * (dt / 3600.0)
            kwh = state.power_kw * (dt / 3600.0)   # + = discharge, - = regen
            for acc in (self.trip, self.since_charge):
                acc["miles"] += miles
                acc["seconds"] += dt
                if kwh >= 0:
                    acc["kwh"] += kwh
                else:
                    acc["regen_kwh"] += -kwh

        # History sampling
        if now - self._last_history_t >= self.history_interval_s:
            self._last_history_t = now
            self.history.append({
                "t": round(now),
                "soc": round(state.soc_pct, 1),
                "pack_v": round(state.pack_voltage or state.dc_bus_voltage, 1),
                "charge_v": round(state.charge_voltage, 1),
                "power_kw": round(state.power_kw, 2),
                "motor_c": round(state.motor_temp_c, 1),
                "inv_c": round(state.inverter_temp_c, 1),
                "chg_c": round(state.charger_temp_c, 1),
                "charging": charging,
            })
            # Durable full-res append (never rolls off) for the HA backfill.
            if self.db is not None:
                try:
                    self.db.insert(round(now), state.to_dict())
                except Exception:
                    pass

        self._save()

    def _start_session(self, state, now):
        self._session = {
            "start": round(now), "end": None,
            "start_soc": round(state.soc_pct, 1), "end_soc": round(state.soc_pct, 1),
            "kwh": 0.0, "peak_w": 0, "max_temp": 0.0,
        }

    def _end_session(self, state, now):
        s = self._session
        if s is None:
            return
        s["end"] = round(now)
        s["kwh"] = round(s["kwh"], 3)
        s["cost"] = round(s["kwh"] * self.rate, 2)
        s["minutes"] = round((s["end"] - s["start"]) / 60.0, 1)
        # keep only real sessions (filter out blips)
        if s["kwh"] > 0.01 or s["minutes"] > 1:
            self.sessions.insert(0, s)      # newest first
            self.sessions = self.sessions[:100]
            self._save_sessions()
        self._session = None
        # A completed charge resets the "since charge" trip counters
        self.since_charge = {"miles": 0.0, "kwh": 0.0, "regen_kwh": 0.0, "seconds": 0.0}
        self._save(force=True)

    def reset_trip(self):
        self.trip = {"miles": 0.0, "kwh": 0.0, "regen_kwh": 0.0, "seconds": 0.0}
        self._save(force=True)

    # ---- read models -------------------------------------------------
    @staticmethod
    def _scope(acc):
        eff = (acc["miles"] / acc["kwh"]) if acc["kwh"] > 0.05 else 0.0
        return {
            "miles": round(acc["miles"], 1),
            "kwh": round(acc["kwh"], 2),
            "regen_kwh": round(acc["regen_kwh"], 2),
            "efficiency": round(eff, 1),          # mi/kWh
            "hours": round(acc["seconds"] / 3600.0, 2),
        }

    def to_dict(self) -> dict:
        cur = None
        if self._session is not None:
            cur = {"kwh": round(self._session["kwh"], 2),
                   "start_soc": self._session["start_soc"],
                   "minutes": round((time.time() - self._session["start"]) / 60.0, 1)}
        return {
            "trip": self._scope(self.trip),
            "since_charge": self._scope(self.since_charge),
            "current_charge": cur,
        }
