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
#
# ---------------------------------------------------------------------------
# STATIC analysis helper for the tier-4 realism target (cxxfilt-cve-2016-4487).
# It speeds up steps 3-4 of the activation checklist (README.md): protections +
# candidate gadgets for a hand-authored reference chain.
#
# STATIC ONLY — this NEVER executes the target. It parses the ELF (checksec /
# readelf) and searches gadgets (ROPgadget / ropper), nothing more. Executing a
# payload is the validator sandbox's job and ITS ALONE (ADR 0002); crash-offset
# derivation is done via `cyclic` + the gdb *inspect* path, not from here. This
# script deliberately has no way to run the binary.
#
# Usage:
#   corpus/scripts/binutils-cxxfilt/analyze.sh [binary_path]
#     default: corpus/binaries/cxxfilt-cve-2016-4487  (build it first: build.sh)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${HERE}/../../.." && pwd)"
BIN="${1:-${REPO_ROOT}/corpus/binaries/cxxfilt-cve-2016-4487}"

sec() { printf '\n=== %s ===\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }

[ -f "${BIN}" ] || { printf 'error: no binary at %s — run build.sh first.\n' "${BIN}" >&2; exit 1; }

sec "target"
printf '%s\n' "${BIN}"
sha256sum "${BIN}"

sec "protections (want: non-PIE / NX / no canary / static -> clean ret2syscall)"
if have checksec; then checksec --file="${BIN}" || true
else
    readelf -h "${BIN}" | grep -Ei 'Type:'      # EXEC = non-PIE, DYN = PIE
    readelf -lW "${BIN}" | grep -Ei 'GNU_STACK'  # RWE vs RW  (RW = NX on)
    echo "(install 'checksec' for canary/RELRO/PIE at a glance)"
fi

sec "/bin/sh string (static libc should embed one)"
if have ROPgadget; then ROPgadget --binary "${BIN}" --string '/bin/sh' || true
else strings -a -t x "${BIN}" | grep -F '/bin/sh' || echo "  (none found by strings)"; fi

# Canonical execve("/bin/sh", 0, 0) building blocks. Static libc = plenty.
if have ROPgadget; then
    dump() { ROPgadget --binary "${BIN}" 2>/dev/null | grep -Ei "$1" | head -"${2:-8}"; }
    sec "pop rdi ; ret            (arg1 = &\"/bin/sh\")";        dump ': pop rdi ; ret$'
    sec "pop rsi ; ret            (arg2 = 0)";                   dump ': pop rsi ;( pop [a-z0-9]+ ;)? ret$'
    sec "pop rdx ; ret            (arg3 = 0)";                   dump ': pop rdx ;( pop [a-z0-9]+ ;)? ret$'
    sec "pop rax ; ret            (syscall no. = 59 execve)";    dump ': pop rax ; ret$'
    sec "syscall ; ret / syscall";                              dump ': syscall'
    sec "bare ret                 (movaps stack realignment)";  dump ': ret$' 4
    sec "mov [reg], reg ; ret     (store gadgets, if planting)"; dump ': mov qword ptr \[r[a-z0-9]+\], r[a-z0-9]+ ; ret$'
elif have ropper; then
    sec "gadgets (ropper)"
    ropper --file "${BIN}" --search 'pop rdi; ret' || true
    ropper --file "${BIN}" --search 'pop rsi; ret' || true
    ropper --file "${BIN}" --search 'pop rdx; ret' || true
    ropper --file "${BIN}" --search 'pop rax; ret' || true
    ropper --file "${BIN}" --search 'syscall'      || true
else
    sec "gadget search UNAVAILABLE"
    echo "  install the binary-tools extra on the lab host: ROPgadget / ropper"
    echo "  (pip install -e '.[binary-tools]')"
fi

cat <<'NOTE'

=== next: crash offset (done via inspect, not here) ===
  This helper does not run the target. To find the saved-RIP offset, feed a
  De Bruijn pattern and read the faulting value under the gdb *inspect* path:
      python -c "from pwn import *; print(cyclic(600).decode())" > /tmp/pat
      # inspect the crash (gdb MCP server / your own gdb) and note the rip bytes
      python -c "from pwn import *; print(cyclic_find(0x6161...))"
  Put that number in RIP_OFFSET in the PoC skeleton
  (corpus/scripts/binutils-cxxfilt/cxxfilt-cve-2016-4487.poc-skeleton.py),
  fill the gadget addresses above, verify with `sara verify`, then activate.
NOTE
