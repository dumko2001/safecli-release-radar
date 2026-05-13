from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from safecli_radar.models import ReleaseEvent, SafeCLIResult


def package_spec(event: ReleaseEvent) -> str:
    if event.ecosystem == "npm":
        return f"{event.package_name}@{event.version}"
    if event.ecosystem == "pypi":
        return f"{event.package_name}=={event.version}"
    raise ValueError(f"unsupported ecosystem: {event.ecosystem}")


def run_safecli(
    event: ReleaseEvent,
    *,
    command_name: str = "safecli",
    config_path: str | None = None,
    db_path: str | None = None,
    artifacts_dir: str | None = None,
    provider: str | None = None,
    cwd: str | None = None,
    timeout_sec: int = 300,
) -> SafeCLIResult:
    safecli_path = shutil.which(command_name)
    if not safecli_path:
        raise RuntimeError(f"{command_name} command not found; install and set up SafeCLI first")

    command = [safecli_path, "check", event.ecosystem, package_spec(event)]
    env = os.environ.copy()
    if config_path:
        env["SAFECLI_CONFIG_PATH"] = str(Path(config_path).expanduser())
    if db_path:
        env["SAFECLI_DB_PATH"] = str(Path(db_path).expanduser())
    if artifacts_dir:
        env["SAFECLI_SCAN_ARTIFACTS_DIR"] = str(Path(artifacts_dir).expanduser())
    if provider:
        env["SAFECLI_AGENT_PROVIDER"] = provider

    completed = subprocess.run(
        command,
        capture_output=True,
        check=False,
        cwd=str(Path(cwd).expanduser()) if cwd else None,
        env=env,
        text=True,
        timeout=timeout_sec,
    )

    parsed = None
    try:
        parsed = json.loads(completed.stdout)
    except json.JSONDecodeError:
        parsed = None

    return SafeCLIResult(
        command=command,
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        parsed_json=parsed,
    )
