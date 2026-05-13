from pathlib import Path

from safecli_radar.db import RadarDB
from safecli_radar.models import ReleaseEvent


def test_records_exact_release_once(tmp_path: Path):
    db = RadarDB(tmp_path / "radar.db")
    db.init()
    event = ReleaseEvent(
        ecosystem="pypi",
        package_name="requests",
        version="2.32.3",
        source="test",
        cursor="1",
        seen_at="now",
    )

    assert db.record_release(event) is True
    assert db.record_release(event) is False
    assert db.release_exists("pypi", "requests", "2.32.3") is True


def test_records_event_log_path(tmp_path: Path):
    db = RadarDB(tmp_path / "radar.db")
    db.init()
    event = ReleaseEvent(
        ecosystem="npm",
        package_name="is-number",
        version="7.0.0",
        source="test",
        cursor="1",
        seen_at="now",
    )
    db.record_release(event)

    db.record_event_log_path(event, jsonl_path="./data/radar-events.jsonl")

    row = db.conn.execute(
        """
        SELECT event_log_path
        FROM releases
        WHERE ecosystem=? AND package_name=? AND version=?
        """,
        ("npm", "is-number", "7.0.0"),
    ).fetchone()
    assert row["event_log_path"] == "./data/radar-events.jsonl"
