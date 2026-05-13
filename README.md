# SafeCLI Release Radar

![License](https://img.shields.io/badge/license-Apache--2.0-1f6feb)
![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)
![Ecosystems](https://img.shields.io/badge/ecosystems-npm%20%7C%20PyPI-CB3837)
![Interface](https://img.shields.io/badge/interface-CLI-0A7EA4)
![Mode](https://img.shields.io/badge/mode-local%20radar-2ea44f)

**SafeCLI tells you whether to trust a package. Release Radar finds the new
packages worth checking first.**

Near-realtime release discovery for SafeCLI.

Radar watches npm and PyPI, resolves exact package versions, ranks releases by
risk and blast radius, and sends high-signal candidates to your local `safecli`
command.

SafeCLI remains the scanner. Radar is the discovery layer.

## Quick Start

Install SafeCLI first and make sure the `safecli` command works:

```bash
safecli check npm is-number@7.0.0
```

Then install Radar:

```bash
make install
safecli-radar check npm is-number
safecli-radar watch
```

That is the main workflow.

## Why Radar Exists

Package registries like npm and PyPI move faster than manual review.

Most malicious-package discoveries happen after a package has already been
published, installed, or copied into build systems. Scanning every single
release is noisy and expensive, but waiting for takedowns and advisories is too
late.

Radar is built for the decision in the middle:

- which fresh releases should SafeCLI inspect now
- which exact version was published
- which low-risk-looking package has enough blast radius to scan anyway
- which package was skipped, and why

## What It Does

- Watches npm and PyPI release feeds.
- Resolves every candidate to an exact package version.
- Deduplicates releases in a local SQLite database.
- Enriches candidates with downloads and dependent-package signals.
- Performs lightweight static archive triage before spending a SafeCLI scan.
- Runs `safecli check ...` for high-risk or high-impact candidates.
- Writes one JSON report per release under `./data/reports/YYYY-MM-DD/`.

## Commands

Check one package through the Radar pipeline:

```bash
safecli-radar check npm is-number
safecli-radar check pypi requests==2.32.3
```

Poll npm and PyPI once:

```bash
safecli-radar once
```

Run continuously:

```bash
safecli-radar watch
```

Smoke-test one watch cycle and exit:

```bash
safecli-radar watch --max-cycles 1 --no-scan
```

Print the full machine-readable watch payload:

```bash
safecli-radar watch --output json
```

Discovery only, without spending SafeCLI scans:

```bash
safecli-radar once --no-scan
```

Tune scan policy:

```bash
safecli-radar watch --scan-threshold 70 --impact-scan-threshold 80
```

Use a specific SafeCLI provider/config:

```bash
safecli-radar \
  --safecli-provider opencode \
  --safecli-config ./data/safecli-config.json \
  check npm is-number
```

## Scan Policy

Radar scans when static risk is high or impact is high.

High-impact packages can be scanned even when static risk is low. This matters
because a package with many users or dependents can be dangerous even when the
first-pass risk score looks quiet.

Current always-scan impact triggers include:

- at least 10,000 npm downloads in the last week
- at least 10 direct dependents
- at least 100 indirect dependents
- at least 100 total dependents
- strong name similarity to a popular package

## How It Works

```mermaid
flowchart LR
    A["Registry release feed"] --> B["Resolve exact version"]
    B --> C["Deduplicate in radar.db"]
    C --> D["Enrich blast radius"]
    D --> E["Score risk and impact"]
    E --> F{"Scan policy match?"}
    F -- "No" --> G["Write JSON report"]
    F -- "Yes" --> H["safecli check"]
    H --> G
```

Radar calls SafeCLI externally. It does not replace SafeCLI's graph builder,
provider configuration, verdict cache, or scan artifacts.

The SafeCLI commands Radar runs look like:

```bash
safecli check npm package@version
safecli check pypi package==version
```

## Registry Sources

- npm: public registry change cursor at
  `https://replicate.npmjs.com/registry/_changes?since=<seq>`
- PyPI: RSS for fast recent updates plus XML-RPC changelog serials for
  cursor-based reconciliation
- deps.dev: dependent-package enrichment when available
- npm downloads API: last-week download enrichment for npm packages

## Local Files

Local runtime files are written under `./data/`:

- `radar.db` for release events, cursors, scores, reports, and SafeCLI results
- `reports/` for JSON reports explaining scan decisions
- optional SafeCLI DB and artifacts when passed through Radar flags

The package archives Radar downloads for triage are temporary. They are not
kept in the repository.

## Development

```bash
make install
make lint
make test
```

## Project Standards

- [Code of Conduct](./CODE_OF_CONDUCT.md)
- [Contributing](./CONTRIBUTING.md)
- [Security](./SECURITY.md)
- [Apache-2.0 License](./LICENSE)
