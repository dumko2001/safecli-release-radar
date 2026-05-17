.PHONY: install lint test

PYTHON ?= python3

define require_python_310
	@$(PYTHON) -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' || \
		(echo "SafeCLI Release Radar requires Python 3.10+." && \
		 echo "Current interpreter: $$($(PYTHON) --version 2>&1)" && \
		 echo "Use a newer interpreter, for example: make PYTHON=/opt/homebrew/bin/python3.12 install" && \
		 exit 1)
endef

install:
	$(call require_python_310)
	$(PYTHON) -m venv .venv
	./.venv/bin/python -m pip install --upgrade pip
	./.venv/bin/python -m pip install -e .[dev]
	mkdir -p "$(HOME)/.local/bin"
	ln -sf "$(PWD)/.venv/bin/safecli-radar" "$(HOME)/.local/bin/safecli-radar"

lint:
	./.venv/bin/ruff check .

test:
	./.venv/bin/python -m pytest -q
