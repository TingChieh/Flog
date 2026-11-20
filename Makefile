PYTHON := .venv/bin/python
RUFF := .venv/bin/ruff
MYPY := .venv/bin/mypy
PYTEST := $(PYTHON) -m pytest

.PHONY: help lint typecheck test-js test-py test-browser test check verify

help:
	@echo "Targets:"
	@echo "  make lint          Run Ruff lint and JS syntax checks"
	@echo "  make typecheck     Run mypy static type checks"
	@echo "  make test-js       Run Node.js frontend tests"
	@echo "  make test-py       Run Python unit and integration tests"
	@echo "  make test-browser  Run Playwright Chromium browser tests"
	@echo "  make test          Run JS and Python tests (excluding browser)"
	@echo "  make check         Fast gate: lint + typecheck + test-js"
	@echo "  make verify        Full gate: lint + typecheck + test + test-browser"

lint:
	$(RUFF) check app config.py flog.py gunicorn.conf.py scripts tests
	@for f in app/static/*.js; do node --check "$$f" || exit 1; done

typecheck:
	$(MYPY)

test-js:
	node --test tests/*.test.js

test-py:
	$(PYTEST) tests -q -m "not browser"

test-browser:
	$(PYTEST) tests -q -m browser

test: test-js test-py

check: lint typecheck test-js

verify: lint typecheck test test-browser
