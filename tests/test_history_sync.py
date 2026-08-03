"""Durable history log + HA statistics backfill (pure logic, no network)."""
from src.state.history_db import HistoryDB
from src.ha.stats_sync import build_messages


def _mk(tmp_path):
    return HistoryDB(str(tmp_path / "history.db"))


def test_insert_and_hourly_aggregation(tmp_path):
    db = _mk(tmp_path)
    base = 1_700_000_000
    hour = (base // 3600) * 3600
    # three samples in the same hour
    db.insert(hour + 10, {"soc_pct": 80.0, "power_kw": 10.0})
    db.insert(hour + 20, {"soc_pct": 78.0, "power_kw": 30.0})
    db.insert(hour + 30, {"soc_pct": 76.0, "power_kw": 20.0})

    hourly = db.hourly(hour, hour + 3600)
    assert hourly["soc"] == [{"start": hour, "mean": 78.0, "min": 76.0, "max": 80.0}]
    assert hourly["power_kw"][0]["mean"] == 20.0
    assert hourly["power_kw"][0]["max"] == 30.0
    db.close()


def test_null_metric_hours_are_omitted(tmp_path):
    db = _mk(tmp_path)
    hour = (1_700_000_000 // 3600) * 3600
    # only soc present; motor temp never reported -> should not appear
    db.insert(hour + 5, {"soc_pct": 50.0})
    hourly = db.hourly(hour, hour + 3600)
    assert "soc" in hourly
    assert "motor_c" not in hourly
    db.close()


def test_watermark_roundtrip_and_earliest(tmp_path):
    db = _mk(tmp_path)
    assert db.get_hwm() is None
    hour = (1_700_000_000 // 3600) * 3600
    db.insert(hour + 5, {"soc_pct": 50.0})
    assert db.earliest_hour() == hour
    db.set_hwm(hour + 3600)
    assert db.get_hwm() == hour + 3600
    db.close()


def test_build_messages_payload_shape(tmp_path):
    db = _mk(tmp_path)
    hour = (1_700_000_000 // 3600) * 3600
    db.insert(hour + 5, {"soc_pct": 55.0, "power_kw": 12.0})
    msgs = build_messages(db.hourly(hour, hour + 3600), source="ranger")

    by_id = {m["metadata"]["statistic_id"]: m for m in msgs}
    soc = by_id["ranger:soc"]
    assert soc["type"] == "recorder/import_statistics"
    assert soc["metadata"]["has_mean"] is True
    assert soc["metadata"]["has_sum"] is False
    assert soc["metadata"]["source"] == "ranger"
    assert soc["metadata"]["unit_of_measurement"] == "%"
    # hour-aligned, timezone-aware UTC ISO
    assert soc["stats"][0]["start"].endswith("+00:00")
    assert soc["stats"][0]["mean"] == 55.0
    db.close()


def test_reimport_same_hour_is_stable(tmp_path):
    """Re-aggregating an already-synced hour yields identical payloads
    (import_statistics is idempotent on the HA side)."""
    db = _mk(tmp_path)
    hour = (1_700_000_000 // 3600) * 3600
    db.insert(hour + 5, {"soc_pct": 55.0})
    a = build_messages(db.hourly(hour, hour + 3600), source="ranger")
    b = build_messages(db.hourly(hour, hour + 3600), source="ranger")
    assert a == b
    db.close()
