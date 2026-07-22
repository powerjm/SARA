#!/usr/bin/env bash
# SARA — Sans Agentic Rop Analysis
# Copyright (c) 2026 Jeff Powers. MIT License — see LICENSE.
# SPDX-License-Identifier: MIT
#
# Research instrument for a SANS.edu thesis on LLM agents that build ROP
# exploit chains. The ethical scope in README.md is non-negotiable and binds
# all copies, forks, and derived works: educational/CTF targets only,
# proof-of-concept payloads only. Use against systems you do not own or are
# not authorized to test is prohibited.

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
echo "LM Studio (open-weight / unrestricted backends):"
# Endpoint from .env (grepped, not sourced — matching the Credentials check),
# else the backend's own default. In the reference setup this points at a
# separate LAN host; the probe just confirms it answers.
lmstudio_url="$(grep -E '^LMSTUDIO_BASE_URL=..+' .env 2>/dev/null | tail -n1 | cut -d= -f2- | tr -d '[:space:]')"
lmstudio_url="${lmstudio_url:-http://127.0.0.1:1234/v1}"
if command -v curl >/dev/null 2>&1; then
    models_json="$(curl -fsS --max-time 5 "${lmstudio_url%/}/models" 2>/dev/null)"
    if [[ -n "$models_json" ]]; then
        py=""
        if [[ -x .venv/bin/python ]]; then py=".venv/bin/python"
        elif command -v python3.14 >/dev/null 2>&1; then py="python3.14"
        elif command -v python3 >/dev/null 2>&1; then py="python3"
        fi
        summary=""
        if [[ -n "$py" ]]; then
            summary="$(printf '%s' "$models_json" | "$py" -c 'import json,sys; d=json.load(sys.stdin); ids=[m.get("id","?") for m in d.get("data", [])]; print((str(len(ids))+" model(s): "+", ".join(ids)) if ids else "none loaded")' 2>/dev/null)"
        fi
        ok "reachable at $lmstudio_url${summary:+ — $summary}"
    else
        warn "not reachable at $lmstudio_url — start LM Studio (enable Serve on Local Network for a LAN host) or fix LMSTUDIO_BASE_URL; only needed for the open-weight/unrestricted backends"
    fi
else
    warn "curl not on PATH — cannot probe LM Studio at $lmstudio_url"
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
