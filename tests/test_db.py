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
