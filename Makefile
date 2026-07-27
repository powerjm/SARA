# SARA — Sans Agentic Rop Analysis
# Copyright (c) 2026 Jeff Powers. MIT License — see LICENSE.
# SPDX-License-Identifier: MIT
#
# Research instrument for a SANS.edu thesis on LLM agents that build ROP
# exploit chains. The ethical scope in README.md is non-negotiable and binds
# all copies, forks, and derived works: educational/CTF targets only,
# proof-of-concept payloads only. Use against systems you do not own or are
# not authorized to test is prohibited.

.PHONY: help bootstrap install dev test lint typecheck format notebooks preflight clean sandbox-build sandbox-clean hackbox-build hackbox hackbox-clean

PYTHON   ?= python3.14
VENV     ?= .venv
PIP       = $(VENV)/bin/pip
PY        = $(VENV)/bin/python
NB_BUILD ?= build/notebooks
# The run-for-record matrix `make preflight` dry-runs and gates on. Override with
# `make preflight CONFIG=experiments.majorca.yaml` for the side-comparison.
CONFIG   ?= experiments.yaml

help:
	@echo "Common targets:"
	@echo "  bootstrap     Create venv, install deps, install pre-commit hooks."
	@echo "  test          Run pytest with coverage."
	@echo "  lint          Run ruff."
	@echo "  typecheck     Run mypy."
	@echo "  format        Auto-format with ruff."
	@echo "  preflight     Run the pre-launch gate (lint, tests, dry-run, verify) before a run-for-record."
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

# Pre-flight gate (TRIAL_2_PLAN.md §7) — the checklist that prevents another
# Trial 1. Runs the automatable checks (any of which fails the target) and then
# prints the lab-host steps the operator must confirm by hand. Run it ON THE LAB
# HOST before a run-for-record: the `verify` step needs Docker + the fetched
# corpus, so it will fail off-host (as intended — that host is not launch-ready).
preflight: bootstrap
	@echo "== SARA pre-flight gate (CONFIG=$(CONFIG)) =="
	@echo "-- [1/4] lint --------------------------------------------------------"
	$(VENV)/bin/ruff check .
	@echo "-- [2/4] test suite (incl. tool-exposure premise + smoke-trace gate) -"
	$(PY) -m pytest -q
	@echo "-- [3/4] dry-run plan + cost estimate --------------------------------"
	$(PY) -m harness.cli batch --config $(CONFIG) --dry-run
	@echo "-- [4/4] validator regression: sara verify on >=2 corpus-truth PoCs --"
	$(PY) -m harness.cli verify --binary ret2win-baseline
	$(PY) -m harness.cli verify --binary cgc-cadet-00001
	@echo
	@echo "== MANUAL lab-host gates (confirm before launch; not automatable here) =="
	@echo "  [ ] each backend completes a 1-cell smoke run with no transport/context/credit/moderation error"
	@echo "  [ ] every LM Studio model advertises n_ctx >= 32768 (GET /v1/models)"
	@echo "  [ ] API credits topped up AND the dry-run estimate above is <= the approved budget"
	@echo "  No box unchecked -> no launch."

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
