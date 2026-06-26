#!/usr/bin/env bash
#
# One-shot, host-side reproducible build of the CGC (cb-multios) corpus binaries.
#
# Does the whole recipe with no host toolchain install (everything compiles
# inside a Docker container):
#
#   1. ensure a cb-multios checkout at the commit pinned in corpus/manifest.yaml
#   2. build the toolchain image (this dir's Dockerfile)
#   3. build the 5 challenge targets in-container as static non-PIE / NX targets
#      (this dir's build_targets.sh)
#   4. hash, pin (--update), and install the ELFs into corpus/binaries/
#
# Requires: docker, git, python (the repo .venv). Produces i386 ELFs that are
# EXEC (non-PIE) / NX-on / no-canary / no-RELRO / statically linked, matching
# `protections: [nx]`.
#
# Usage:
#   corpus/scripts/cb-multios/build.sh [CB_CHECKOUT_DIR]
#
# CB_CHECKOUT_DIR defaults to ~/src/cb-multios.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${HERE}/../../.." && pwd)"
CB_DIR="${1:-${HOME}/src/cb-multios}"
IMAGE="sara-cbtoolchain:22.04"
MANIFEST="${REPO_ROOT}/corpus/manifest.yaml"

note() { printf '>> %s\n' "$*"; }
die()  { printf 'error: %s\n' "$*" >&2; exit 1; }

command -v docker >/dev/null || die "docker not found"
command -v git    >/dev/null || die "git not found"

# Commit to pin = the one recorded in the manifest's first git+ source_url.
COMMIT="$(grep -oE 'cb-multios@[0-9a-f]{40}' "${MANIFEST}" | head -1 | cut -d@ -f2)"
[ -n "${COMMIT}" ] || die "no pinned cb-multios commit found in ${MANIFEST}"
note "pinned cb-multios commit: ${COMMIT}"

# 1. checkout at the pinned commit -----------------------------------------
if [ ! -d "${CB_DIR}/.git" ]; then
    note "cloning cb-multios into ${CB_DIR}"
    mkdir -p "$(dirname "${CB_DIR}")"
    git clone https://github.com/trailofbits/cb-multios.git "${CB_DIR}"
fi
( cd "${CB_DIR}" && git fetch --depth 1 origin "${COMMIT}" 2>/dev/null \
    && git checkout -q "${COMMIT}" ) \
    || ( cd "${CB_DIR}" && git checkout -q "${COMMIT}" ) \
    || die "could not check out ${COMMIT} in ${CB_DIR}"
HEAD_NOW="$(cd "${CB_DIR}" && git rev-parse HEAD)"
[ "${HEAD_NOW}" = "${COMMIT}" ] || die "checkout HEAD ${HEAD_NOW} != pinned ${COMMIT}"

# 2. toolchain image --------------------------------------------------------
note "building toolchain image ${IMAGE}"
docker build -f "${HERE}/Dockerfile" -t "${IMAGE}" "${HERE}"

# 3. build the targets in-container -----------------------------------------
note "building corpus targets in-container"
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
    -v "${CB_DIR}:/cb-multios" \
    -v "${HERE}/build_targets.sh:/build_targets.sh:ro" \
    "${IMAGE}" /build_targets.sh

# 4. hash, pin, install -----------------------------------------------------
PY="${REPO_ROOT}/.venv/bin/python"
[ -x "${PY}" ] || PY="$(command -v python3)"
note "pinning + installing via corpus.scripts.build"
( cd "${REPO_ROOT}" && "${PY}" -m corpus.scripts.build --all --cb-multios "${CB_DIR}" --update )

note "done. corpus/binaries/ now holds the CGC ELFs; SHA-256s pinned in the manifest."
