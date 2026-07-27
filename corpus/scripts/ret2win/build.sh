#!/usr/bin/env bash
# SARA — Sans Agentic Rop Analysis
# Copyright (c) 2026 Jeff Powers. MIT License — see LICENSE.
# SPDX-License-Identifier: MIT
#
# Build the tier-(-1) ret2win baseline target (Trial 2, D4).
#
#   -static -no-pie : every address (win, gadget_ret) is fixed at link time, so
#                     the reference chain in corpus/exploits/ret2win-baseline.py
#                     is stable and reproducible.
#   -fno-stack-protector : no canary, so the overflow reaches the saved return
#                          address (the whole point of the trainer).
#   -z noexecstack  : NX on (data pages non-executable) — this is a ROP target,
#                     not a shellcode target.
#   -O0 -g0         : predictable, un-optimised prologue/epilogue; no debug info.
#
# Usage:  build.sh [output_path]        (default: ./ret2win-baseline)
# The built binary is the corpus artifact; drop it at
# corpus/binaries/ret2win-baseline and record its sha256 in corpus/manifest.yaml.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
src="${here}/ret2win.c"
out="${1:-ret2win-baseline}"

gcc -static -no-pie -fno-stack-protector -z noexecstack -O0 -g0 -o "${out}" "${src}"

echo "built ${out}"
sha256sum "${out}"
