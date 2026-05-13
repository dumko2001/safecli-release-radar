from pathlib import Path

from safecli_radar.models import ReleaseEvent
from safecli_radar.reporter import write_report


def test_write_report_creates_json_only(tmp_path: Path):
    event = ReleaseEvent(
        ecosystem="npm",
        package_name="@scope/pkg",
        version="1.0.0",
        source="test",
        cursor="1",
        seen_at="2026-05-13T00:00:00+00:00",
    )

    paths = write_report(
        reports_dir=tmp_path,
        event=event,
        item={
            "risk_score": 0,
            "impact_score": 80,
            "reasons": ["downloads_last_week 10000 >= 10000"],
        },
        scan_decision={"should_scan": True, "reasons": ["impact"], "budget_deferred": False},
        safecli_result=None,
    )

    assert Path(paths["json"]).exists()
    assert set(paths) == {"json"}
    assert not list(tmp_path.rglob("*.md"))
