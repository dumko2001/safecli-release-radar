.PHONY: install lint test

install:
	python3 -m venv .venv
	./.venv/bin/python -m pip install --upgrade pip
	./.venv/bin/python -m pip install -e .[dev]
	mkdir -p "$(HOME)/.local/bin"
	ln -sf "$(PWD)/.venv/bin/safecli-radar" "$(HOME)/.local/bin/safecli-radar"

lint:
	./.venv/bin/ruff check .

test:
	./.venv/bin/python -m pytest -q
