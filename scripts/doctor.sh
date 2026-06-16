#!/usr/bin/env bash
# Print a readiness report for the apparatus.
# Doesn't change anything; useful as a first thing to run on a fresh machine
# and as the first step of a troubleshooting session.

set -uo pipefail

ok() { printf '  \033[32m✓\033[0m %s\n' "$*"; }
bad() { printf '  \033[31m✗\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }

cd "$(dirname "$0")/.."

echo "doctor sara (SANS Agentic Return-Oriented Programming (ROP) Analysis)"
echo "=================="
echo

echo "Python:"
if command -v python3.14 >/dev/null 2>&1; then
    ok "python3.14 found: $(python3.14 --version)"
else
    bad "python3.14 not on PATH"
fi

echo
echo "Venv:"
if [[ -d .venv ]]; then
    ok ".venv exists"
    if [[ -x .venv/bin/python ]]; then
        ok ".venv interpreter present"
    fi
else
    warn "no .venv yet — run scripts/bootstrap.sh"
fi

echo
echo "Backend tools:"
for tool in ROPgadget ropper r2 gdb; do
    if command -v "$tool" >/dev/null 2>&1; then
        ok "$tool on PATH"
    else
        warn "$tool not on PATH (needed for Phase 1+)"
    fi
done

echo
echo "Docker:"
if command -v docker >/dev/null 2>&1; then
    if docker info >/dev/null 2>&1; then
        ok "docker daemon reachable"
    else
        warn "docker installed but daemon not reachable (start it, or check rootless config)"
    fi
else
    warn "docker not installed (needed for the validator sandbox)"
fi

echo
echo "Credentials:"
if [[ -f .env ]]; then
    ok ".env present"
    if grep -E '^ANTHROPIC_API_KEY=..+' .env >/dev/null 2>&1; then
        ok "ANTHROPIC_API_KEY set"
    else
        warn "ANTHROPIC_API_KEY not set in .env"
    fi
else
    warn ".env not present (cp .env.example .env)"
fi

echo
echo "Corpus:"
if [[ -f corpus/manifest.yaml ]]; then
    n=$(grep -cE '^  - id:' corpus/manifest.yaml || echo 0)
    ok "manifest has $n entries"
fi
if [[ -d corpus/binaries ]] && [[ -n "$(ls -A corpus/binaries 2>/dev/null | grep -v gitkeep)" ]]; then
    ok "corpus/binaries populated"
else
    warn "corpus/binaries empty — run python -m corpus.scripts.fetch"
fi

echo
echo "Done."
