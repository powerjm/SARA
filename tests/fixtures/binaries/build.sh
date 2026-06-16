#!/usr/bin/env bash
#
# Reproducibly build the sample_overflow trainer and verify it against the
# pinned SHA-256 in sample_overflow.sha256.
#
# The flags below strip the usual sources of ELF non-determinism so the build
# is byte-identical across runs on the same toolchain:
#
#   -no-pie -fno-pie        fixed load base (0x400000) -> stable gadget addresses
#   -fno-stack-protector    no canary (difficulty tier 1)
#   -fcf-protection=none    no CET endbr64 padding
#   -fno-asynchronous-unwind-tables / -g0   no .eh_frame churn / debug info
#   -fno-ident              drop the ".comment" GCC version string from codegen
#   -Wl,--build-id=none     drop the random-looking .note.gnu.build-id
#   -Wl,-z,noexecstack      NX (matches manifest protections: [nx])
#
# A trailing `objcopy --remove-section .comment` deletes the (non-allocated)
# version-string section that gcc still emits, which is the one remaining
# cross-toolchain-version hazard. Because it is non-allocated, removing it does
# not shift any code address.
#
# Cross-*version* reproducibility is best-effort: a different gcc/binutils may
# legitimately produce a different SHA. The pin records the SHA produced by the
# reference toolchain (the Step 0 lab host: Ubuntu 26.04 / gcc 15.x). On a
# mismatch this script prints both hashes and the local toolchain so the drift
# is visible; pass --update to repin deliberately (and commit the new hash and
# binary together).
#
# Usage:
#   ./build.sh              build, then verify against the pinned SHA-256
#   ./build.sh --update     build, then overwrite the pin with the new SHA-256
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="${HERE}/sample_overflow.c"
OUT="${HERE}/sample_overflow"
SHA_FILE="${HERE}/sample_overflow.sha256"

UPDATE=0
if [[ "${1:-}" == "--update" ]]; then
    UPDATE=1
fi

command -v gcc >/dev/null || { echo "error: gcc not found on PATH" >&2; exit 127; }
command -v objcopy >/dev/null || { echo "error: objcopy not found on PATH" >&2; exit 127; }

echo "building ${OUT}"
gcc -O0 -g0 -no-pie -fno-pie -fno-stack-protector -fcf-protection=none \
    -fno-asynchronous-unwind-tables -fno-ident \
    -Wl,--build-id=none -Wl,-z,noexecstack \
    -o "${OUT}" "${SRC}"

# Drop the non-allocated version-string section (harmless to addresses).
objcopy --remove-section .comment "${OUT}"

actual="$(sha256sum "${OUT}" | cut -d' ' -f1)"

if [[ "${UPDATE}" -eq 1 ]]; then
    printf '%s  sample_overflow\n' "${actual}" > "${SHA_FILE}"
    echo "pinned ${actual} -> ${SHA_FILE}"
    exit 0
fi

if [[ ! -f "${SHA_FILE}" ]]; then
    echo "error: pin file missing: ${SHA_FILE} (run ./build.sh --update to create it)" >&2
    exit 1
fi

expected="$(cut -d' ' -f1 < "${SHA_FILE}")"

if [[ "${actual}" == "${expected}" ]]; then
    echo "OK: ${actual} matches the pinned SHA-256"
    exit 0
fi

{
    echo "SHA-256 MISMATCH"
    echo "  expected: ${expected}"
    echo "  actual:   ${actual}"
    echo "local toolchain:"
    gcc --version | head -1 | sed 's/^/  /'
    objcopy --version | head -1 | sed 's/^/  /'
    echo "If this is an intentional toolchain bump, repin with: ./build.sh --update"
} >&2
exit 1
