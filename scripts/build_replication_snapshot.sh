#!/usr/bin/env bash
# Build a replication snapshot: a self-contained, reproducible bundle of the
# apparatus + environment + data behind the thesis's reported results.
#
# Produces  dist/sara-snapshot-<commit>.tar.zst  containing:
#   source-<commit>.tar.gz   the repo tree at the chosen ref (git archive)
#   pip-freeze.txt           exact installed Python versions
#   validator-image.txt      the sandbox Docker image id + repo digest
#   manifest.yaml            the corpus metadata catalog
#   corpus-binaries/         the corpus binaries (unless --no-binaries)
#   corpus-binaries.sha256   their checksums (always, even with --no-binaries)
#   runs/                    every run directory (record.json/trace.jsonl/payload.bin)
#   payloads.sha256          checksums of every stored payload (for verify)
#   notebooks-html/          executed analysis notebooks rendered to HTML
#   environment.txt          host/OS/CPU/Docker summary + local-vs-cloud
#   SNAPSHOT.json            machine-readable index of the above
#
# Re-validate it with scripts/verify_snapshot.sh.
#
# Usage:
#   scripts/build_replication_snapshot.sh [--ref REF] [--out DIR] [--no-binaries]
#                                         [--runs DIR] [--no-notebooks]
#
# Env: RUN_OUTPUT_DIR (default ./runs), VALIDATOR_IMAGE (default from .env or
# sara-sandbox:latest), SARA_RUN_ENV (local|cloud; recorded verbatim if set).

set -euo pipefail

cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd)"

# --- defaults / args -------------------------------------------------------- #
REF="HEAD"
OUT_DIR="dist"
INCLUDE_BINARIES=1
INCLUDE_NOTEBOOKS=1
RUNS_DIR="${RUN_OUTPUT_DIR:-./runs}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --ref) REF="$2"; shift 2 ;;
        --out) OUT_DIR="$2"; shift 2 ;;
        --runs) RUNS_DIR="$2"; shift 2 ;;
        --no-binaries) INCLUDE_BINARIES=0; shift ;;
        --no-notebooks) INCLUDE_NOTEBOOKS=0; shift ;;
        -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "error: unknown argument '$1'" >&2; exit 2 ;;
    esac
done

note() { printf '>> %s\n' "$*"; }
warn() { printf '!! %s\n' "$*" >&2; }
die()  { printf 'error: %s\n' "$*" >&2; exit 1; }

command -v git  >/dev/null 2>&1 || die "git not found"
command -v zstd >/dev/null 2>&1 || die "zstd not found (apt install zstd) — needed for .tar.zst"

PY=".venv/bin/python"
[[ -x "$PY" ]] || PY="$(command -v python3.14 || command -v python3 || true)"
[[ -n "$PY" ]] || die "no Python interpreter (run make bootstrap)"

VALIDATOR_IMAGE="${VALIDATOR_IMAGE:-sara-sandbox:latest}"
COMMIT="$(git rev-parse --short "$REF")"
COMMIT_FULL="$(git rev-parse "$REF")"
GIT_DIRTY="clean"
git diff --quiet 2>/dev/null && git diff --cached --quiet 2>/dev/null || GIT_DIRTY="DIRTY (uncommitted changes present)"

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
SNAP="sara-snapshot-$COMMIT"
SNAPDIR="$STAGE/$SNAP"
mkdir -p "$SNAPDIR"

note "snapshot $SNAP  (commit $COMMIT_FULL, $GIT_DIRTY)"

# 1. repo source at the ref ------------------------------------------------- #
note "archiving repo source at $REF"
git archive --format=tar.gz --prefix="sara-$COMMIT/" -o "$SNAPDIR/source-$COMMIT.tar.gz" "$REF"

# 2. exact installed versions ----------------------------------------------- #
note "recording pip freeze"
"$PY" -m pip freeze > "$SNAPDIR/pip-freeze.txt" 2>/dev/null || warn "pip freeze failed"

# 3. validator image digest -------------------------------------------------- #
if command -v docker >/dev/null 2>&1 && docker image inspect "$VALIDATOR_IMAGE" >/dev/null 2>&1; then
    note "recording validator image digest for $VALIDATOR_IMAGE"
    {
        echo "image: $VALIDATOR_IMAGE"
        echo "id: $(docker image inspect "$VALIDATOR_IMAGE" --format '{{.Id}}')"
        echo "repo_digests: $(docker image inspect "$VALIDATOR_IMAGE" --format '{{json .RepoDigests}}')"
        echo "created: $(docker image inspect "$VALIDATOR_IMAGE" --format '{{.Created}}')"
    } > "$SNAPDIR/validator-image.txt"
else
    warn "validator image '$VALIDATOR_IMAGE' not inspectable (docker missing or image not built) — recording name only"
    echo "image: $VALIDATOR_IMAGE (not present at snapshot time)" > "$SNAPDIR/validator-image.txt"
fi

# 4. corpus manifest + binaries --------------------------------------------- #
# Snapshot the *active* corpus, honoring the same SARA_CORPUS_* overrides the
# harness uses (so a snapshot reflects exactly what the runs resolved against).
MANIFEST_SRC="${SARA_CORPUS_MANIFEST:-corpus/manifest.yaml}"
BINARIES_SRC="${SARA_CORPUS_BINARIES_DIR:-corpus/binaries}"

if [[ -f "$MANIFEST_SRC" ]]; then
    cp "$MANIFEST_SRC" "$SNAPDIR/manifest.yaml"
else
    warn "corpus manifest missing at $MANIFEST_SRC"
fi

: > "$SNAPDIR/corpus-binaries.sha256"
if [[ -d "$BINARIES_SRC" ]]; then
    # Checksums always; the bytes only when redistribution is intended.
    ( cd "$BINARIES_SRC" && find . -type f ! -name '.gitkeep' -print0 \
        | xargs -0 -r sha256sum ) > "$SNAPDIR/corpus-binaries.sha256" || true
    if [[ "$INCLUDE_BINARIES" -eq 1 ]]; then
        if [[ -n "$(find "$BINARIES_SRC" -type f ! -name '.gitkeep' 2>/dev/null)" ]]; then
            note "including corpus binaries (honor each entry's license before public distribution)"
            mkdir -p "$SNAPDIR/corpus-binaries"
            find "$BINARIES_SRC" -type f ! -name '.gitkeep' -exec cp {} "$SNAPDIR/corpus-binaries/" \;
        else
            warn "$BINARIES_SRC is empty — fetch/build the corpus before a results snapshot"
        fi
    else
        note "--no-binaries: recording corpus checksums only (verify must re-fetch binaries)"
    fi
fi

# 5. run records + payload checksums ---------------------------------------- #
: > "$SNAPDIR/payloads.sha256"
RUN_COUNT=0
mkdir -p "$SNAPDIR/runs"  # always present, even for an apparatus-only snapshot
if [[ -d "$RUNS_DIR" ]]; then
    note "copying run records from $RUNS_DIR"
    # Only finalized runs (a record.json present); skip dotted .partial-* dirs.
    while IFS= read -r -d '' rec; do
        rundir="$(dirname "$rec")"
        cp -r "$rundir" "$SNAPDIR/runs/"
        RUN_COUNT=$((RUN_COUNT + 1))
    done < <(find "$RUNS_DIR" -maxdepth 2 -name record.json -not -path '*/.partial*' -print0)
    if [[ -d "$SNAPDIR/runs" ]]; then
        ( cd "$SNAPDIR/runs" && find . -name payload.bin -print0 | xargs -0 -r sha256sum ) \
            > "$SNAPDIR/payloads.sha256" || true
    fi
fi
[[ "$RUN_COUNT" -gt 0 ]] || warn "no finalized run records found in $RUNS_DIR (apparatus-only snapshot)"
note "captured $RUN_COUNT run record(s)"

# 6. notebook HTML ----------------------------------------------------------- #
if [[ "$INCLUDE_NOTEBOOKS" -eq 1 ]] && [[ -d analysis/notebooks ]]; then
    if "$PY" -c "import jupyter" >/dev/null 2>&1 || command -v jupyter >/dev/null 2>&1; then
        note "rendering analysis notebooks to HTML"
        mkdir -p "$SNAPDIR/notebooks-html"
        if ! "$PY" -m jupyter nbconvert --to html --execute \
                --ExecutePreprocessor.timeout=600 \
                --output-dir "$SNAPDIR/notebooks-html" \
                analysis/notebooks/*.ipynb >/dev/null 2>&1; then
            warn "notebook execution failed; falling back to non-executed render"
            "$PY" -m jupyter nbconvert --to html \
                --output-dir "$SNAPDIR/notebooks-html" \
                analysis/notebooks/*.ipynb >/dev/null 2>&1 || warn "notebook render failed entirely"
        fi
    else
        warn "jupyter not installed — skipping notebook HTML"
    fi
fi

# 7. environment summary ----------------------------------------------------- #
note "writing environment summary"
os_pretty="$( ( . /etc/os-release 2>/dev/null && echo "$PRETTY_NAME" ) || echo unknown )"
cpu_model="$(grep -m1 'model name' /proc/cpuinfo 2>/dev/null | cut -d: -f2- | sed 's/^ //' || echo unknown)"
cpu_count="$(nproc 2>/dev/null || echo '?')"
mem_total="$(grep -m1 MemTotal /proc/meminfo 2>/dev/null | awk '{print $2" "$3}' || echo unknown)"
docker_ver="$(docker --version 2>/dev/null || echo 'docker not present')"
py_ver="$("$PY" --version 2>&1)"
run_env="${SARA_RUN_ENV:-unspecified}"
# Best-effort cloud hint from DMI product name.
cloud_hint="$(cat /sys/class/dmi/id/product_name 2>/dev/null || echo unknown)"

cat > "$SNAPDIR/environment.txt" <<EOF
SARA replication snapshot — environment summary
================================================
snapshot          : $SNAP
git commit        : $COMMIT_FULL
git worktree      : $GIT_DIRTY
built (UTC)       : $(date -u '+%Y-%m-%dT%H:%M:%SZ')
hostname          : $(hostname 2>/dev/null || echo unknown)

run environment   : $run_env   (SARA_RUN_ENV; 'local' = lab host, 'cloud' = infra/ VM)
cloud/DMI hint    : $cloud_hint

OS                : $os_pretty
kernel            : $(uname -srm 2>/dev/null || echo unknown)
CPU               : $cpu_model ($cpu_count threads)
memory            : $mem_total
python            : $py_ver
docker            : $docker_ver
validator image   : $VALIDATOR_IMAGE

corpus binaries   : $([[ "$INCLUDE_BINARIES" -eq 1 ]] && echo included || echo "checksums only (--no-binaries)")
run records        : $RUN_COUNT
EOF

# 8. machine-readable index -------------------------------------------------- #
"$PY" - "$SNAPDIR" "$COMMIT_FULL" "$run_env" "$RUN_COUNT" "$VALIDATOR_IMAGE" <<'PYEOF' > "$SNAPDIR/SNAPSHOT.json"
import json, sys
snapdir, commit, run_env, run_count, image = sys.argv[1:6]
print(json.dumps({
    "schema": "sara-snapshot/1",
    "commit": commit,
    "run_environment": run_env,
    "run_records": int(run_count),
    "validator_image": image,
    "contents": [
        "source-*.tar.gz", "pip-freeze.txt", "validator-image.txt",
        "manifest.yaml", "corpus-binaries/", "corpus-binaries.sha256",
        "runs/", "payloads.sha256", "notebooks-html/", "environment.txt",
    ],
}, indent=2))
PYEOF

# 9. package ----------------------------------------------------------------- #
mkdir -p "$OUT_DIR"
OUT_DIR_ABS="$(cd "$OUT_DIR" && pwd)"
TARBALL="$OUT_DIR_ABS/$SNAP.tar.zst"
note "packing $TARBALL"
tar --use-compress-program 'zstd -19 -T0' -cf "$TARBALL" -C "$STAGE" "$SNAP"
( cd "$OUT_DIR_ABS" && sha256sum "$SNAP.tar.zst" > "$SNAP.tar.zst.sha256" )

note "done."
echo
echo "  snapshot : $TARBALL"
echo "  size     : $(du -h "$TARBALL" | cut -f1)"
echo "  sha256   : $(cut -d' ' -f1 "$OUT_DIR_ABS/$SNAP.tar.zst.sha256")"
echo "  verify   : scripts/verify_snapshot.sh $TARBALL"
