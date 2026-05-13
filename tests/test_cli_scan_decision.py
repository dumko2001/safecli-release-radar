import json

from safecli_radar.cli import _cycle_summary, score_and_scan
from safecli_radar.db import RadarDB
from safecli_radar.models import ReleaseEvent


def test_manual_check_force_scan_runs_safecli_for_low_score(monkeypatch, tmp_path):
    db = RadarDB(tmp_path / "radar.db")
    db.init()
    event = ReleaseEvent(
        ecosystem="npm",
        package_name="tiny-package",
        version="1.0.0",
        source="manual_check",
        cursor="manual",
        seen_at="now",
    )
    db.record_release(event)
    calls = []

    def fake_run_safecli(event, **_kwargs):
        calls.append(event)
        from safecli_radar.models import SafeCLIResult

        return SafeCLIResult(
            command=["safecli", "check", event.ecosystem, event.package_name],
            exit_code=0,
            stdout="{}",
            stderr="",
            parsed_json={},
        )

    monkeypatch.setattr("safecli_radar.cli.run_safecli", fake_run_safecli)

    score_and_scan(
        db,
        [event],
        scan=True,
        enrich=False,
        artifact_triage=False,
        user_agent="test",
        scan_threshold=70,
        impact_scan_threshold=80,
        artifact_threshold=25,
        max_safecli=1,
        force_scan=True,
    )

    assert len(calls) == 1


def test_score_and_scan_appends_release_progress_jsonl(tmp_path):
    db = RadarDB(tmp_path / "radar.db")
    db.init()
    event = ReleaseEvent(
        ecosystem="npm",
        package_name="tiny-package",
        version="1.0.0",
        source="test",
        cursor="1",
        seen_at="2026-05-13T00:00:00+00:00",
    )
    db.record_release(event)
    jsonl_log = tmp_path / "radar-events.jsonl"

    results = score_and_scan(
        db,
        [event],
        scan=False,
        enrich=False,
        artifact_triage=False,
        user_agent="test",
        scan_threshold=70,
        impact_scan_threshold=80,
        artifact_threshold=25,
        max_safecli=1,
        jsonl_log=str(jsonl_log),
    )

    records = [json.loads(line) for line in jsonl_log.read_text(encoding="utf-8").splitlines()]
    assert [record["type"] for record in records] == ["release_started", "release_processed"]
    assert records[1]["report"]["release"]["package_name"] == "tiny-package"
    assert records[1]["report"]["scores"]["risk_score"] == 5
    assert results[0]["log"]["jsonl"] == str(jsonl_log)


def test_cycle_summary_names_new_exact_versions_and_sources():
    events = [
        ReleaseEvent(
            ecosystem="pypi",
            package_name="a",
            version="1.0.0",
            source="pypi_updates",
            cursor="1",
            seen_at="now",
        ),
        ReleaseEvent(
            ecosystem="pypi",
            package_name="b",
            version="1.0.0",
            source="pypi_changelog",
            cursor="2",
            seen_at="now",
        ),
    ]

    summary = _cycle_summary(cycle=1, events=events, results=[{}, {}], elapsed_sec=1.234)

    assert summary["new_exact_versions"] == 2
    assert summary["processed"] == 2
    assert summary["source_counts"] == {"pypi_changelog": 1, "pypi_updates": 1}
    assert "feed_candidates" not in summary
