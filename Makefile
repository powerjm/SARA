# SARA — Sans Agentic Rop Analysis
# Copyright (c) 2026 Jeff Powers. MIT License — see LICENSE.
# SPDX-License-Identifier: MIT
#
# Research instrument for a SANS.edu thesis on LLM agents that build ROP
# exploit chains. The ethical scope in README.md is non-negotiable and binds
# all copies, forks, and derived works: educational/CTF targets only,
# proof-of-concept payloads only. Use against systems you do not own or are
# not authorized to test is prohibited.

.PHONY: help bootstrap install dev test lint typecheck format notebooks clean sandbox-build sandbox-clean hackbox-build hackbox hackbox-clean

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
	@echo "  hackbox-build Build the exploit-dev workbench image."
	@echo "  hackbox       Drop into the exploit-dev workbench (repo mounted rw)."
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

# Exploit-development workbench (NOT the scoring path — see Dockerfile.hackbox).
# Pass the host uid/gid so files written to the bind-mounted repo stay owned by
# the invoking user rather than root.
hackbox-build:
	docker build -f Dockerfile.hackbox -t sara-hackbox:latest \
		--build-arg HOST_UID=$(shell id -u) \
		--build-arg HOST_GID=$(shell id -g) .

hackbox: hackbox-build
	scripts/hackbox.sh

hackbox-clean:
	-docker rmi sara-hackbox:latest

clean:
	rm -rf $(VENV) .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage build dist *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
