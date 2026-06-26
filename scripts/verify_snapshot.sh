#!/usr/bin/env bash
# Re-validate a replication snapshot: re-execute every stored payload in the
# real validator sandbox and confirm each run's recorded outcome reproduces.
#
# This is the trust check behind the thesis data: a reviewer with the snapshot,
# this repo (bootstrapped), and Docker can re-run every payload and confirm the
# successes still fire — without paying for a single LLM token.
#
# What it checks, per run directory that has a payload.bin:
#   1. payload bytes match payloads.sha256 (integrity), when that file is present;
#   2. re-executing the payload reproduces the recorded validator.succeeded and
#      validator.stdout_marker_found (the exploit still behaves as recorded).
# Runs without a payload (e.g. refusals) are reported and skipped. The chain
# fingerprint is not re-derived here (it is a property of the proposer's chain,
# already recorded) — this verifies *execution*, which is the reproducible part.
#
# Requires: Docker + the validator image, and a bootstrapped repo (.venv). The
# snapshot's own corpus binaries are used when present; otherwise point
# SARA_CORPUS_BINARIES_DIR at a binaries dir you fetched from the manifest.
#
# Usage:
#   scripts/verify_snapshot.sh <snapshot.tar.zst | unpacked-snapshot-dir>
#
# Exit code: 0 iff every payload reproduced; non-zero on any mismatch/error.

set -euo pipefail

cd "$(dirname "$0")/.."

note() { printf '>> %s\n' "$*"; }
die()  { printf 'error: %s\n' "$*" >&2; exit 1; }

[[ $# -eq 1 ]] || die "usage: scripts/verify_snapshot.sh <snapshot.tar.zst | dir>"
TARGET="$1"

PY=".venv/bin/python"
[[ -x "$PY" ]] || die "no .venv — run make bootstrap first (verify uses the apparatus code)"

WORK=""
cleanup() { [[ -n "$WORK" ]] && rm -rf "$WORK"; }
trap cleanup EXIT

# --- resolve the snapshot to an unpacked directory ------------------------- #
if [[ -d "$TARGET" ]]; then
    SNAPDIR="$TARGET"
elif [[ -f "$TARGET" ]]; then
    command -v zstd >/dev/null 2>&1 || die "zstd not found (apt install zstd)"
    WORK="$(mktemp -d)"
    note "unpacking $TARGET"
    tar --use-compress-program 'zstd -d' -xf "$TARGET" -C "$WORK"
    SNAPDIR="$(find "$WORK" -maxdepth 1 -type d -name 'sara-snapshot-*' | head -n1)"
    [[ -n "$SNAPDIR" ]] || die "no sara-snapshot-* directory inside $TARGET"
else
    die "not found: $TARGET"
fi

note "verifying snapshot at $SNAPDIR"
if [[ ! -d "$SNAPDIR/runs" ]] || [[ -z "$(find "$SNAPDIR/runs" -name record.json 2>/dev/null)" ]]; then
    note "no run records in snapshot — nothing to verify (apparatus-only snapshot)"
    exit 0
fi

# Point the apparatus's corpus resolver at the snapshot's manifest + binaries.
[[ -f "$SNAPDIR/manifest.yaml" ]] && export SARA_CORPUS_MANIFEST="$SNAPDIR/manifest.yaml"
[[ -d "$SNAPDIR/corpus-binaries" ]] && export SARA_CORPUS_BINARIES_DIR="$SNAPDIR/corpus-binaries"

# --- optional payload integrity check -------------------------------------- #
if [[ -f "$SNAPDIR/payloads.sha256" ]] && [[ -s "$SNAPDIR/payloads.sha256" ]]; then
    note "checking payload checksums"
    ( cd "$SNAPDIR/runs" && sha256sum -c --quiet "$SNAPDIR/payloads.sha256" ) \
        || die "payload checksum mismatch — snapshot is corrupt or tampered"
fi

# --- re-validate every payload --------------------------------------------- #
# The heavy lifting is in Python: it loads each record, re-runs the snapshot's
# payload.bin through the real validator, and compares to the recorded result.
"$PY" - "$SNAPDIR" <<'PYEOF'
import sys
from pathlib import Path

# Establish import order before importing validator.runner (avoids the
# validator<->agent circular import when validator is imported first).
import agent.graph  # noqa: F401
from harness import corpus, persistence
from validator.runner import execute

snapdir = Path(sys.argv[1])
runs = sorted(p for p in (snapdir / "runs").iterdir() if (p / "record.json").is_file())

checked = reproduced = skipped = failed = 0
for run_dir in runs:
    record = persistence.load_record(run_dir)
    payload = run_dir / "payload.bin"
    if not payload.is_file() or record.validator is None:
        skipped += 1
        print(f"  - {run_dir.name}: no payload/validator output (outcome={record.outcome.value}) — skipped")
        continue
    try:
        spec = corpus.resolve_binary(record.binary_id)
    except corpus.CorpusError as exc:
        failed += 1
        print(f"  ! {run_dir.name}: cannot resolve binary {record.binary_id!r}: {exc}")
        continue

    checked += 1
    out = execute(
        spec.binary_path,
        payload,
        success_marker=spec.success_marker,
        documented_chain_fingerprint=spec.documented_chain_fingerprint,
    )
    same_success = out.succeeded == record.validator.succeeded
    same_marker = out.stdout_marker_found == record.validator.stdout_marker_found
    if same_success and same_marker:
        reproduced += 1
        print(f"  ok {run_dir.name}: succeeded={out.succeeded} (matches recorded)")
    else:
        failed += 1
        print(
            f"  X  {run_dir.name}: MISMATCH "
            f"recorded(succeeded={record.validator.succeeded},marker={record.validator.stdout_marker_found}) "
            f"now(succeeded={out.succeeded},marker={out.stdout_marker_found})"
        )

print()
print(f"verified {reproduced}/{checked} payload(s) reproduced; {skipped} skipped; {failed} failed")
sys.exit(1 if failed else 0)
PYEOF
rc=$?

echo
if [[ "$rc" -eq 0 ]]; then
    note "SNAPSHOT VERIFIED — every payload reproduced its recorded outcome"
else
    printf '!! SNAPSHOT VERIFICATION FAILED\n' >&2
fi
exit "$rc"
