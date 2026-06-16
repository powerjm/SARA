#!/usr/bin/env bash
# Bootstrap a development environment.
#
# Idempotent. Safe to run repeatedly. Targets a Linux host with Python 3.14+
# already available (Ubuntu 26.04 ships it; pyenv works for other distros).

set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python3.14}"
VENV_DIR="${VENV_DIR:-.venv}"

cd "$(dirname "$0")/.."

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "error: $PYTHON_BIN not found on PATH" >&2
    echo "       install Python 3.14 (pyenv install 3.14 / apt install python3.14 on Ubuntu 26.04)" >&2
    exit 1
fi

if [[ ! -d "$VENV_DIR" ]]; then
    echo ">> creating venv at $VENV_DIR"
    "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

echo ">> upgrading pip"
pip install --upgrade pip >/dev/null

echo ">> installing project (dev + analysis extras)"
pip install -e ".[dev,analysis]"

if command -v pre-commit >/dev/null 2>&1; then
    echo ">> installing pre-commit hooks"
    pre-commit install
fi

if [[ ! -f .env ]]; then
    echo ">> seeding .env from .env.example"
    cp .env.example .env
    echo "   edit .env to add API keys before running the harness"
fi

echo ""
echo "Bootstrap complete. Activate the venv with:"
echo "    source $VENV_DIR/bin/activate"
echo ""
echo "Run the test suite with:"
echo "    make test"
