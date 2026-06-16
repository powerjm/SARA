.PHONY: help bootstrap install dev test lint typecheck format notebooks clean sandbox-build sandbox-clean

PYTHON   ?= python3.14
VENV     ?= .venv
PIP       = $(VENV)/bin/pip
PY        = $(VENV)/bin/python
NB_BUILD ?= build/notebooks

help:
	@echo "Common targets:"
	@echo "  bootstrap     Create venv, install deps, install pre-commit hooks."
	@echo "  test          Run pytest with coverage."
	@echo "  lint          Run ruff."
	@echo "  typecheck     Run mypy."
	@echo "  format        Auto-format with ruff."
	@echo "  sandbox-build Build the validator sandbox image."
	@echo "  clean         Remove caches and build artifacts."

bootstrap: $(VENV)/.bootstrapped

$(VENV)/.bootstrapped: pyproject.toml
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev,analysis]"
	$(VENV)/bin/pre-commit install || true
	touch $@

install: bootstrap

dev: bootstrap

test: bootstrap
	$(PY) -m pytest -q --cov=. --cov-report=term-missing

lint: bootstrap
	$(VENV)/bin/ruff check .

typecheck: bootstrap
	$(VENV)/bin/mypy .

format: bootstrap
	$(VENV)/bin/ruff format .
	$(VENV)/bin/ruff check . --fix

notebooks: bootstrap
	mkdir -p $(NB_BUILD)
	$(VENV)/bin/jupyter nbconvert --to notebook --execute \
		--ExecutePreprocessor.timeout=300 \
		--output-dir $(NB_BUILD) analysis/notebooks/*.ipynb

sandbox-build:
	docker build -f Dockerfile.sandbox -t sara-sandbox:latest .

sandbox-clean:
	-docker rmi sara-sandbox:latest

clean:
	rm -rf $(VENV) .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage build dist *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
