import json
from pathlib import Path

from safecli_radar.models import ReleaseEvent
from safecli_radar.reporter import append_jsonl_record, write_report


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


def test_append_jsonl_record_writes_one_record_per_line(tmp_path: Path):
    log_path = tmp_path / "radar-events.jsonl"

    append_jsonl_record(log_path, {"type": "release_started", "release": {"package": "pkg"}})
    append_jsonl_record(log_path, {"type": "release_processed", "release": {"package": "pkg"}})

    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["type"] == "release_started"
    assert json.loads(lines[1])["type"] == "release_processed"
