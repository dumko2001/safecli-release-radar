import json
from pathlib import Path

from safecli_radar.models import ReleaseEvent
from safecli_radar.reporter import append_jsonl_record, build_release_report


def test_build_release_report_returns_agent_readable_payload():
    event = ReleaseEvent(
        ecosystem="npm",
        package_name="@scope/pkg",
        version="1.0.0",
        source="test",
        cursor="1",
        seen_at="2026-05-13T00:00:00+00:00",
    )

    report = build_release_report(
        event=event,
        item={
            "risk_score": 0,
            "impact_score": 80,
            "reasons": ["downloads_last_week 10000 >= 10000"],
            "scan_decision": {
                "should_scan": True,
                "reasons": ["impact"],
                "budget_deferred": False,
            },
        },
        safecli_result=None,
    )

    assert report["release"]["package_name"] == "@scope/pkg"
    assert report["scores"]["impact_score"] == 80
    assert report["scan_decision"]["should_scan"] is True


def test_append_jsonl_record_writes_one_record_per_line(tmp_path: Path):
    log_path = tmp_path / "radar-events.jsonl"

    append_jsonl_record(log_path, {"type": "release_started", "release": {"package": "pkg"}})
    append_jsonl_record(log_path, {"type": "release_processed", "release": {"package": "pkg"}})

    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["type"] == "release_started"
    assert json.loads(lines[1])["type"] == "release_processed"
