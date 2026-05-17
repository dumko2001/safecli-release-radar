---
name: safecli-release-radar
description: This skill should be used when working in the SafeCLI Release Radar repository to install Radar, verify the local SafeCLI dependency, run `safecli-radar check`, `once`, or `watch`, validate latest-version discovery from npm or PyPI, and debug Radar-to-SafeCLI handoff behavior.
---

# SafeCLI Release Radar

## Overview

Use this skill when the current repository is the release-watcher and triage layer that feeds SafeCLI. Follow it to install Radar correctly, verify that SafeCLI exists, run real Radar commands, and validate discovery plus handoff behavior without reading the whole repo first.

## Use This Skill When

- Asked to install or bootstrap the Radar repo from a fresh clone
- Asked to run `safecli-radar check`, `safecli-radar once`, or `safecli-radar watch`
- Asked to verify whether Radar is finding latest or exact versions correctly
- Asked to debug why Radar did or did not call SafeCLI
- Asked to validate first-run npm/PyPI watch behavior in this repo

## Dependency Check: SafeCLI First

Radar is supposed to call a working local `safecli` command. Verify that first:

```bash
which safecli
safecli --help
safecli check npm is-number@7.0.0
```

If `safecli` is not found on `PATH`, check the standard local install location before assuming it is missing:

```bash
~/.local/bin/safecli --help
~/.local/bin/safecli check npm is-number@7.0.0
```

If `safecli` is missing, prefer an existing local checkout first. If no working SafeCLI repo is present and the task requires installation, clone the exact SafeCLI branch that this Radar repo is meant to use:

```bash
git clone --branch codex/oss-selfhost-v1 --single-branch https://github.com/hilling-cybersec/package_manager.git
```

Then install SafeCLI from that clone using its repo workflow. Do not substitute another branch unless the user explicitly asks for it.

## Install Radar

Radar also requires `python3 >= 3.10`.

Standard install flow:

```bash
make install
safecli-radar check npm is-number
```

If the default `python3` is too old:

```bash
make PYTHON=/opt/homebrew/bin/python3.12 install
```

If `safecli-radar` is not on `PATH`, use `~/.local/bin/safecli-radar` or add `~/.local/bin` to `PATH`.

## Core Workflows

### Manual Check

Use:

```bash
safecli-radar check npm is-number
safecli-radar check pypi requests==2.32.3
```

Important behavior:

- `check` without a version resolves latest
- `check` with an explicit version preserves the pin

Use this path when the user wants a one-off resolution and scan through Radar.

### Poll Once

Use:

```bash
safecli-radar once
safecli-radar once --no-scan
safecli-radar once --ecosystem npm
safecli-radar once --ecosystem pypi
```

Use `--no-scan` when validating discovery only.

### Watch Continuously

Use:

```bash
safecli-radar watch
safecli-radar watch --max-cycles 1 --no-scan
safecli-radar watch --output json
```

Use `--max-cycles 1 --no-scan` for a smoke test. Use plain `watch` for the real long-running workflow.

## Validating Discovery Properly

When proving that Radar found a live latest version:

1. Let Radar discover the package/version first.
2. Record the exact ecosystem, package, and version Radar found.
3. Then verify live registry state with a direct registry request.
4. Then confirm whether SafeCLI ran automatically for that candidate.

Do not invert that order when the goal is to prove watch behavior.

Interpret timestamps carefully:

- `release.seen_at` means "first seen by this Radar DB"
- `report.metadata.time` or `report.metadata.created` is closer to the registry publish timestamp
- on a fresh DB, the first watch cycle may ingest recent registry events immediately, so a package can be published shortly before `watch` starts and still appear in cycle 1

Do not describe `seen_at` as the package publish time.

## SafeCLI Handoff

When Radar should scan, it normally shells out to:

- `safecli check npm package@version`
- `safecli check pypi package==version`

If the user wants a specific provider or config, use the supported flags:

```bash
safecli-radar --safecli-provider opencode --safecli-config ./data/safecli-config.json check npm is-number
```

## Important Local Files

Inspect these first when debugging:

- `./data/radar.db`
- `./data/radar-events.jsonl`

Useful repo entry points:

- `src/safecli_radar/cli.py` for `check`, `once`, and `watch`
- `src/safecli_radar/resolver.py` for manual package resolution
- `src/safecli_radar/npm_watcher.py` and `src/safecli_radar/pypi_watcher.py` for feed behavior
- `src/safecli_radar/safecli_runner.py` for the SafeCLI subprocess handoff
- `src/safecli_radar/reporter.py` and `src/safecli_radar/db.py` for persisted results and event logging

## Repo-Specific Guardrails

- Do not describe Radar as a standalone scanner. It depends on SafeCLI for actual package scans.
- Do not assume SafeCLI is installed just because Radar installed cleanly. Verify `safecli`.
- Do not hardcode package versions unless the user explicitly asks for a pinned historical check.
- When explaining watch behavior, distinguish:
  - discovery only
  - scoring/triage
  - SafeCLI handoff
  - final SafeCLI result
- Do not treat `should_scan: false` as missing observability. That is a real logged outcome: Radar discovered the release, scored it, and decided not to launch SafeCLI in that cycle.
- If validating latest-version behavior, verify with the live registry after Radar discovery, not before.

## Final Checks Before Completion

Before finishing:

1. State whether SafeCLI was available locally or how it was obtained.
2. State the exact Radar command(s) run.
3. State whether Radar discovered a package/version or returned no events.
4. State whether Radar called SafeCLI automatically.
5. If validating latest behavior, include the registry cross-check result.
