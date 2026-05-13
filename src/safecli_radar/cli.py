from __future__ import annotations

import argparse
import json
import os
import time
from collections import Counter
from pathlib import Path

from safecli_radar.artifact_triage import triage_artifact
from safecli_radar.db import RadarDB
from safecli_radar.enrichment import enrich_release
from safecli_radar.history import annotate_history
from safecli_radar.models import CandidateScore, ReleaseEvent
from safecli_radar.npm_watcher import NpmWatcher
from safecli_radar.pypi_watcher import PyPIWatcher
from safecli_radar.reporter import append_jsonl_record, build_release_report
from safecli_radar.resolver import resolve_package
from safecli_radar.safecli_runner import run_safecli
from safecli_radar.scan_policy import decide_scan
from safecli_radar.scorer import score_release

DEFAULT_DB_PATH = os.environ.get("SAFECLI_RADAR_DB_PATH", "./data/radar.db")
DEFAULT_JSONL_LOG_PATH = os.environ.get("SAFECLI_RADAR_JSONL_LOG", "./data/radar-events.jsonl")
DEFAULT_USER_AGENT = os.environ.get(
    "SAFECLI_RADAR_USER_AGENT",
    "SafeCLI-Release-Radar/0.1 (+https://github.com/dumko2001/safecli-release-radar)",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="safecli-radar",
        description="Watch npm and PyPI releases and send high-signal candidates to SafeCLI.",
    )
    parser.add_argument("--db", default=DEFAULT_DB_PATH, help="SQLite DB path")
    parser.add_argument(
        "--jsonl-log",
        default=DEFAULT_JSONL_LOG_PATH,
        help="Append-only JSONL output path; pass an empty string to disable",
    )
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT, help="Registry User-Agent")
    parser.add_argument("--safecli-command", default="safecli", help="SafeCLI command name/path")
    parser.add_argument("--safecli-config", default=None, help="Path to SafeCLI config JSON")
    parser.add_argument("--safecli-db", default=None, help="Path to SafeCLI SQLite DB")
    parser.add_argument(
        "--safecli-artifacts-dir",
        default=None,
        help="Path for SafeCLI scan artifacts",
    )
    parser.add_argument(
        "--safecli-provider",
        default=None,
        help="SafeCLI provider override, e.g. opencode",
    )
    parser.add_argument(
        "--safecli-cwd",
        default=None,
        help="Working directory for SafeCLI subprocesses",
    )
    parser.add_argument(
        "--pypi-changelog-interval",
        type=int,
        default=int(os.environ.get("SAFECLI_RADAR_PYPI_CHANGELOG_INTERVAL", "300")),
        help="Seconds between PyPI XML-RPC changelog catch-up calls; 0 checks every cycle",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    once = sub.add_parser("once", help="Poll release feeds once")
    _add_common_poll_args(once)

    check = sub.add_parser("check", help="Resolve and scan one exact package through Radar")
    check.add_argument("ecosystem", choices=["npm", "pypi"])
    check.add_argument("package", help="Package spec, e.g. is-number or requests==2.32.3")
    _add_scan_args(check)

    watch = sub.add_parser("watch", help="Poll release feeds continuously")
    _add_common_poll_args(watch)
    watch.add_argument("--interval", type=int, default=60, help="Seconds between poll cycles")
    watch.add_argument(
        "--max-cycles",
        type=int,
        default=0,
        help="Stop after this many poll cycles; 0 means run forever",
    )
    watch.add_argument(
        "--output",
        choices=["summary", "json"],
        default="summary",
        help="Watch output mode",
    )

    return parser


def _add_common_poll_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--ecosystem",
        choices=["all", "npm", "pypi"],
        default="all",
        help="Registry ecosystem to watch",
    )
    parser.add_argument("--npm-limit", type=int, default=100, help="npm changes per cycle")
    _add_scan_args(parser)


def _add_scan_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--scan-threshold",
        type=int,
        default=70,
        help="Risk score threshold for running SafeCLI",
    )
    parser.add_argument(
        "--impact-scan-threshold",
        type=int,
        default=80,
        help="Impact score threshold for running SafeCLI even when static risk is low",
    )
    parser.add_argument(
        "--max-safecli-per-cycle",
        type=int,
        default=0,
        help="Maximum SafeCLI scans per polling cycle; 0 means no per-cycle cap",
    )
    parser.add_argument(
        "--no-scan",
        action="store_true",
        help="Only discover and score releases; do not run SafeCLI",
    )
    parser.add_argument(
        "--no-enrich",
        action="store_true",
        help="Skip blast-radius enrichment APIs",
    )
    parser.add_argument(
        "--no-artifact-triage",
        action="store_true",
        help="Skip static archive inspection before SafeCLI scanning",
    )
    parser.add_argument(
        "--artifact-threshold",
        type=int,
        default=25,
        help="Risk score threshold for downloading and statically inspecting archives",
    )


def cmd_once(args: argparse.Namespace) -> int:
    db = _open_db(args.db)
    events = poll_once(
        db,
        ecosystem=args.ecosystem,
        npm_limit=args.npm_limit,
        user_agent=args.user_agent,
        pypi_changelog_interval=args.pypi_changelog_interval,
    )
    results = score_and_scan(
        db,
        events,
        scan=not args.no_scan,
        enrich=not args.no_enrich,
        artifact_triage=not args.no_artifact_triage,
        user_agent=args.user_agent,
        scan_threshold=args.scan_threshold,
        impact_scan_threshold=args.impact_scan_threshold,
        artifact_threshold=args.artifact_threshold,
        max_safecli=args.max_safecli_per_cycle,
        force_scan=False,
        safecli_command=args.safecli_command,
        safecli_config=args.safecli_config,
        safecli_db=args.safecli_db,
        safecli_artifacts_dir=args.safecli_artifacts_dir,
        safecli_provider=args.safecli_provider,
        safecli_cwd=args.safecli_cwd,
        jsonl_log=args.jsonl_log,
    )
    print(json.dumps(results, ensure_ascii=True, indent=2))
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    db = _open_db(args.db)
    event = resolve_package(args.ecosystem, args.package, user_agent=args.user_agent)
    db.record_release(event)
    results = score_and_scan(
        db,
        [event],
        scan=not args.no_scan,
        enrich=not args.no_enrich,
        artifact_triage=not args.no_artifact_triage,
        user_agent=args.user_agent,
        scan_threshold=args.scan_threshold,
        impact_scan_threshold=args.impact_scan_threshold,
        artifact_threshold=args.artifact_threshold,
        max_safecli=1,
        force_scan=True,
        safecli_command=args.safecli_command,
        safecli_config=args.safecli_config,
        safecli_db=args.safecli_db,
        safecli_artifacts_dir=args.safecli_artifacts_dir,
        safecli_provider=args.safecli_provider,
        safecli_cwd=args.safecli_cwd,
        jsonl_log=args.jsonl_log,
    )
    print(json.dumps(results, ensure_ascii=True, indent=2))
    return 0


def cmd_watch(args: argparse.Namespace) -> int:
    db = _open_db(args.db)
    print(
        "safecli-radar watching"
        f" ecosystem={args.ecosystem}"
        f" interval={args.interval}s"
        f" db={Path(args.db).expanduser()}",
        flush=True,
    )
    cycles = 0
    try:
        while True:
            cycles += 1
            cycle_started = time.time()
            print(f"safecli-radar cycle={cycles} polling", flush=True)
            append_jsonl_record(
                args.jsonl_log,
                {
                    "type": "cycle_started",
                    "cycle": cycles,
                    "ecosystem": args.ecosystem,
                },
            )
            try:
                events = poll_once(
                    db,
                    ecosystem=args.ecosystem,
                    npm_limit=args.npm_limit,
                    user_agent=args.user_agent,
                    pypi_changelog_interval=args.pypi_changelog_interval,
                )
                pending_events = []
                if not args.no_scan:
                    pending_events = _pending_scan_events(
                        db,
                        risk_threshold=args.scan_threshold,
                        impact_threshold=args.impact_scan_threshold,
                        exclude=events,
                    )
                if pending_events:
                    append_jsonl_record(
                        args.jsonl_log,
                        {
                            "type": "pending_scans_loaded",
                            "cycle": cycles,
                            "count": len(pending_events),
                        },
                    )
                results = score_and_scan(
                    db,
                    [*pending_events, *events],
                    scan=not args.no_scan,
                    enrich=not args.no_enrich,
                    artifact_triage=not args.no_artifact_triage,
                    user_agent=args.user_agent,
                    scan_threshold=args.scan_threshold,
                    impact_scan_threshold=args.impact_scan_threshold,
                    artifact_threshold=args.artifact_threshold,
                    max_safecli=args.max_safecli_per_cycle,
                    force_scan=False,
                    safecli_command=args.safecli_command,
                    safecli_config=args.safecli_config,
                    safecli_db=args.safecli_db,
                    safecli_artifacts_dir=args.safecli_artifacts_dir,
                    safecli_provider=args.safecli_provider,
                    safecli_cwd=args.safecli_cwd,
                    jsonl_log=args.jsonl_log,
                )
                cycle_summary = _cycle_summary(
                    cycle=cycles,
                    events=events,
                    results=results,
                    elapsed_sec=time.time() - cycle_started,
                    pending_scan_candidates=len(pending_events),
                )
                append_jsonl_record(args.jsonl_log, {"type": "cycle_completed", **cycle_summary})
                print(
                    json.dumps(cycle_summary, ensure_ascii=True),
                    flush=True,
                )
                if results:
                    if args.output == "json":
                        print(json.dumps(results, ensure_ascii=True), flush=True)
                    else:
                        _print_watch_summary(results)
            except Exception as exc:
                cycle_error = {
                    "cycle": cycles,
                    "error": str(exc),
                    "elapsed_sec": round(time.time() - cycle_started, 2),
                }
                append_jsonl_record(args.jsonl_log, {"type": "cycle_error", **cycle_error})
                print(
                    json.dumps(cycle_error, ensure_ascii=True),
                    flush=True,
                )
            if args.max_cycles > 0 and cycles >= args.max_cycles:
                print("safecli-radar max cycles reached; exiting", flush=True)
                return 0
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("safecli-radar stopped", flush=True)
        return 0


def _print_watch_summary(results: list[dict]) -> None:
    selected = [
        item
        for item in results
        if (item.get("scan_decision") or {}).get("should_scan")
    ]
    print(
        "safecli-radar processed="
        f"{len(results)} scan_candidates={len(selected)}"
        " use --output json for full cycle payload",
        flush=True,
    )
    for item in selected[:20]:
        decision = item.get("scan_decision") or {}
        reasons = ", ".join(decision.get("reasons") or [])
        print(
            "candidate "
            f"{item.get('ecosystem')} {_display_spec(item)} "
            f"risk={item.get('risk_score')} impact={item.get('impact_score')} "
            f"reasons={reasons or 'n/a'} "
            f"log={(item.get('log') or {}).get('jsonl')}",
            flush=True,
        )
    if len(selected) > 20:
        print(f"safecli-radar omitted {len(selected) - 20} additional candidates", flush=True)


def _cycle_summary(
    *,
    cycle: int,
    events: list[ReleaseEvent],
    results: list[dict],
    elapsed_sec: float,
    pending_scan_candidates: int = 0,
) -> dict:
    return {
        "cycle": cycle,
        "new_exact_versions": len(events),
        "pending_scan_candidates": pending_scan_candidates,
        "processed": len(results),
        "source_counts": dict(sorted(Counter(event.source for event in events).items())),
        "elapsed_sec": round(elapsed_sec, 2),
    }


def _pending_scan_events(
    db: RadarDB,
    *,
    risk_threshold: int,
    impact_threshold: int,
    exclude: list[ReleaseEvent],
    limit: int = 500,
) -> list[ReleaseEvent]:
    excluded = {(event.ecosystem, event.package_name, event.version) for event in exclude}
    pending: list[ReleaseEvent] = []

    for row in db.recent_unscanned(limit=limit):
        key = (str(row["ecosystem"]), str(row["package_name"]), str(row["version"]))
        if key in excluded:
            continue
        if row["risk_score"] is None or row["impact_score"] is None:
            continue

        event = ReleaseEvent(
            ecosystem=key[0],
            package_name=key[1],
            version=key[2],
            source=str(row["source"]),
            cursor=str(row["cursor"]),
            seen_at=str(row["seen_at"]),
            metadata=_decode_json_object(row["metadata_json"]),
        )
        score = CandidateScore(
            risk_score=int(row["risk_score"]),
            impact_score=int(row["impact_score"]),
            reasons=_decode_json_list(row["reasons_json"]),
        )
        if decide_scan(
            event,
            score,
            risk_threshold=risk_threshold,
            impact_threshold=impact_threshold,
        ).should_scan:
            pending.append(event)

    return pending


def _decode_json_object(value: str | None) -> dict:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _decode_json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed]


def _display_spec(item: dict) -> str:
    package_name = item.get("package_name")
    version = item.get("version")
    if item.get("ecosystem") == "pypi":
        return f"{package_name}=={version}"
    return f"{package_name}@{version}"


def poll_once(
    db: RadarDB,
    *,
    ecosystem: str,
    npm_limit: int,
    user_agent: str,
    pypi_changelog_interval: int,
) -> list[ReleaseEvent]:
    events: list[ReleaseEvent] = []
    if ecosystem in {"all", "npm"}:
        events.extend(NpmWatcher(db, user_agent=user_agent).poll(limit=npm_limit))
    if ecosystem in {"all", "pypi"}:
        events.extend(
            PyPIWatcher(
                db,
                user_agent=user_agent,
                changelog_interval_sec=pypi_changelog_interval,
            ).poll()
        )
    return events


def score_and_scan(
    db: RadarDB,
    events: list[ReleaseEvent],
    *,
    scan: bool,
    enrich: bool,
    artifact_triage: bool,
    user_agent: str,
    scan_threshold: int,
    impact_scan_threshold: int,
    artifact_threshold: int,
    max_safecli: int,
    force_scan: bool = False,
    safecli_command: str = "safecli",
    safecli_config: str | None = None,
    safecli_db: str | None = None,
    safecli_artifacts_dir: str | None = None,
    safecli_provider: str | None = None,
    safecli_cwd: str | None = None,
    jsonl_log: str | None = None,
) -> list[dict]:
    output: list[dict] = []
    safecli_count = 0
    for event in events:
        append_jsonl_record(
            jsonl_log,
            {
                "type": "release_started",
                "release": _release_ref(event),
            },
        )
        try:
            item, safecli_ran, report, scored_event = _score_and_scan_one(
                db,
                event,
                scan=scan,
                enrich=enrich,
                artifact_triage=artifact_triage,
                user_agent=user_agent,
                scan_threshold=scan_threshold,
                impact_scan_threshold=impact_scan_threshold,
                artifact_threshold=artifact_threshold,
                max_safecli=max_safecli,
                safecli_count=safecli_count,
                force_scan=force_scan,
                safecli_command=safecli_command,
                safecli_config=safecli_config,
                safecli_db=safecli_db,
                safecli_artifacts_dir=safecli_artifacts_dir,
                safecli_provider=safecli_provider,
                safecli_cwd=safecli_cwd,
            )
            if safecli_ran:
                safecli_count += 1
            log_path = append_jsonl_record(
                jsonl_log,
                {
                    "type": "release_processed",
                    "release": _release_ref(scored_event),
                    "report": report,
                },
            )
            if log_path:
                db.record_event_log_path(scored_event, jsonl_path=log_path)
                item["log"] = {"jsonl": log_path}
            output.append(item)
        except Exception as exc:
            item = {
                **_release_ref(event),
                "error": str(exc),
                "safecli": "not_run",
                "scan_decision": {
                    "should_scan": False,
                    "reasons": ["release processing failed before scan decision"],
                    "budget_deferred": False,
                },
            }
            output.append(item)
            append_jsonl_record(
                jsonl_log,
                {
                    "type": "release_error",
                    "release": _release_ref(event),
                    "error": str(exc),
                },
            )
    return output


def _score_and_scan_one(
    db: RadarDB,
    event: ReleaseEvent,
    *,
    scan: bool,
    enrich: bool,
    artifact_triage: bool,
    user_agent: str,
    scan_threshold: int,
    impact_scan_threshold: int,
    artifact_threshold: int,
    max_safecli: int,
    safecli_count: int,
    force_scan: bool,
    safecli_command: str,
    safecli_config: str | None,
    safecli_db: str | None,
    safecli_artifacts_dir: str | None,
    safecli_provider: str | None,
    safecli_cwd: str | None,
) -> tuple[dict, bool, dict, ReleaseEvent]:
    event = annotate_history(event, db)
    db.update_metadata(event)

    if enrich:
        event = enrich_release(event, user_agent=user_agent)
        db.update_metadata(event)

    score = score_release(event)

    if artifact_triage and (score.risk_score >= artifact_threshold or score.impact_score >= 80):
        event = triage_artifact(event, user_agent=user_agent)
        db.update_metadata(event)
        score = score_release(event)

    db.update_score(event, score)

    item = {
        "ecosystem": event.ecosystem,
        "package_name": event.package_name,
        "version": event.version,
        "source": event.source,
        "risk_score": score.risk_score,
        "impact_score": score.impact_score,
        "reasons": score.reasons,
        "safecli": "not_run",
    }

    decision = decide_scan(
        event,
        score,
        risk_threshold=scan_threshold,
        impact_threshold=impact_scan_threshold,
        force_scan=force_scan,
    )
    item["scan_decision"] = {
        "should_scan": decision.should_scan,
        "reasons": decision.reasons,
        "budget_deferred": False,
    }
    safecli_result = None
    safecli_ran = False

    within_budget = max_safecli <= 0 or safecli_count < max_safecli
    if scan and decision.should_scan and within_budget:
        result = run_safecli(
            event,
            command_name=safecli_command,
            config_path=safecli_config,
            db_path=safecli_db,
            artifacts_dir=safecli_artifacts_dir,
            provider=safecli_provider,
            cwd=safecli_cwd,
        )
        db.record_safecli_result(event, result)
        safecli_result = result
        safecli_ran = True
        item["safecli"] = {
            "exit_code": result.exit_code,
            "trust_state": (result.parsed_json or {}).get("trust_state"),
            "aggregate_state": (result.parsed_json or {}).get("aggregate_state"),
        }
    elif scan and decision.should_scan and max_safecli > 0 and safecli_count >= max_safecli:
        item["scan_decision"]["budget_deferred"] = True

    report = build_release_report(
        event=event,
        item=item,
        safecli_result=safecli_result,
    )

    return item, safecli_ran, report, event


def _release_ref(event: ReleaseEvent) -> dict[str, str]:
    return {
        "ecosystem": event.ecosystem,
        "package_name": event.package_name,
        "version": event.version,
        "source": event.source,
        "cursor": event.cursor,
    }


def _open_db(path: str) -> RadarDB:
    db = RadarDB(Path(path).expanduser())
    db.init()
    return db


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "once":
        code = cmd_once(args)
    elif args.command == "check":
        code = cmd_check(args)
    elif args.command == "watch":
        code = cmd_watch(args)
    else:
        parser.print_help()
        code = 1
    raise SystemExit(code)


if __name__ == "__main__":
    main()
