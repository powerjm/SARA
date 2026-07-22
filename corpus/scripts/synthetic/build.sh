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
# build.sh — build the SARA synthetic ROP corpus (re-authored from ISP RAS
# rop-benchmark) and pin+install each ELF into the corpus.
#
# One reproducible command, no host toolchain install beyond gcc/binutils:
#   corpus/scripts/synthetic/build.sh
#
# For each binary it compiles the shared freestanding stdin harness (harness.c)
# with exactly one gadget donor (gadgets_ex0NN.S) into a static, non-PIE,
# NX-enforced, no-canary x86-64 ELF, then hands the ELF to
# `python -m corpus.scripts.build --id <id> --from <elf> --update`, which pins
# the sha256 in manifest.yaml and installs the binary to corpus/binaries/<id>.
#
# The sha256 pins THIS lab host's toolchain build (like the cb-multios and
# BroncoCTF entries). If you rebuild on a different gcc and the addresses shift,
# `corpus.scripts.build` will re-pin the sha with --update, but the reference
# PoCs in corpus/exploits/ hardcode gadget addresses pinned to this build — see
# corpus/scripts/synthetic/README.md for how to re-derive them (they are exported
# symbols; the ELF is not stripped).
#
# See harness.c / gadgets_ex0NN.S for the "Cite us" attribution to the ISP RAS
# authors whose synthetic curriculum this is re-authored from.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../../.." && pwd)"
BUILD_DIR="$(mktemp -d "${TMPDIR:-/tmp}/sara-synth-build.XXXXXX")"
trap 'rm -rf "$BUILD_DIR"' EXIT

# Freestanding, static, non-PIE, NX-on, no-canary — a clean fixed-address ROP
# target whose only attacker-reachable executable code is the linked donor's
# .gadgets.text (no libc gadget haystack; that is the point of the synthetic set).
CFLAGS=(
  -no-pie -static -nostdlib -nostartfiles
  -fno-stack-protector -fcf-protection=none -fno-pic -O0
  -Wl,-z,noexecstack -Wl,--build-id=none
)

# binary id  <->  gadget donor
declare -A DONOR=(
  [ropbench-synth-ex005]=gadgets_ex005.S
  [ropbench-synth-ex002]=gadgets_ex002.S
  [ropbench-synth-ex020]=gadgets_ex020.S
  [ropbench-synth-ex010]=gadgets_ex010.S
  [ropbench-synth-ex101]=gadgets_ex101.S
)

echo "Building synthetic ROP corpus into $BUILD_DIR"
cd "$REPO_ROOT"
for id in ropbench-synth-ex005 ropbench-synth-ex002 ropbench-synth-ex020 \
          ropbench-synth-ex010 ropbench-synth-ex101; do
  donor="${DONOR[$id]}"
  elf="$BUILD_DIR/$id"
  echo "  cc   $donor + harness.c -> $id"
  gcc "${CFLAGS[@]}" "$HERE/harness.c" "$HERE/$donor" -o "$elf"
  python -m corpus.scripts.build --id "$id" --from "$elf" --update
done

echo "Done. Verify with: python -m corpus.scripts.verify"
