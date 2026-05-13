from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from safecli_radar.models import ReleaseEvent, SafeCLIResult


def write_report(
    *,
    reports_dir: str | Path,
    event: ReleaseEvent,
    item: dict[str, Any],
    scan_decision: dict[str, Any],
    safecli_result: SafeCLIResult | None,
) -> dict[str, str]:
    base = Path(reports_dir).expanduser()
    day = event.seen_at[:10] or "unknown-date"
    target_dir = base / day
    target_dir.mkdir(parents=True, exist_ok=True)

    stem = _safe_stem(f"{event.ecosystem}-{event.package_name}-{event.version}")
    json_path = target_dir / f"{stem}.json"

    payload = {
        "release": {
            "ecosystem": event.ecosystem,
            "package_name": event.package_name,
            "version": event.version,
            "source": event.source,
            "cursor": event.cursor,
            "seen_at": event.seen_at,
        },
        "scores": {
            "risk_score": item.get("risk_score"),
            "impact_score": item.get("impact_score"),
            "reasons": item.get("reasons", []),
        },
        "scan_decision": scan_decision,
        "safecli": {
            "exit_code": safecli_result.exit_code if safecli_result else None,
            "command": safecli_result.command if safecli_result else None,
            "parsed_json": safecli_result.parsed_json if safecli_result else None,
            "stderr": safecli_result.stderr if safecli_result else None,
        },
        "metadata": event.metadata,
    }

    json_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    return {"json": str(json_path)}


def append_jsonl_record(jsonl_path: str | Path | None, record: dict[str, Any]) -> str | None:
    if not jsonl_path:
        return None

    path = Path(jsonl_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "logged_at": datetime.now(UTC).isoformat(),
        **record,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=True, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return str(path)


def _safe_stem(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")[:180]
