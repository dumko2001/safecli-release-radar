from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from safecli_radar.models import ReleaseEvent, SafeCLIResult


def build_release_report(
    *,
    event: ReleaseEvent,
    item: dict[str, Any],
    safecli_result: SafeCLIResult | None,
) -> dict[str, Any]:
    return {
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
        "scan_decision": item.get("scan_decision"),
        "safecli": {
            "exit_code": safecli_result.exit_code if safecli_result else None,
            "command": safecli_result.command if safecli_result else None,
            "parsed_json": safecli_result.parsed_json if safecli_result else None,
            "stderr": safecli_result.stderr if safecli_result else None,
        },
        "metadata": event.metadata,
    }


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
