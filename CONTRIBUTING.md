# Contributing

Thanks for contributing to SafeCLI Release Radar.

## Development Setup

```bash
make install
make lint
make test
```

Run a one-package check:

```bash
safecli-radar check npm is-number --no-scan
```

Run continuously:

```bash
safecli-radar watch
```

## Branch and PR Guidelines

- Keep pull requests focused and small.
- Add or update tests when behavior changes.
- Keep docs in sync with implementation.
- Ensure `make lint` and `make test` pass before opening a PR.
- Do not commit generated runtime data from `./data/`.

## Commit Style

Use clear, imperative commit messages.

Examples:

- `feat: add pypi release reconciliation`
- `fix: dedupe exact package versions`
- `docs: clarify safecli handoff`

## Reporting Bugs

When opening an issue, include:

- What you expected to happen.
- What actually happened.
- Reproduction steps.
- The command you ran.
- Relevant JSON report snippets if available.

## Security Issues

Do not open public issues for sensitive vulnerabilities.
Use the process described in [SECURITY.md](./SECURITY.md).
