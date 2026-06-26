#!/usr/bin/env bash
#
# Build the sara CGC corpus binaries as clean static-address ROP targets.
#
# Runs INSIDE the toolchain container (this dir's Dockerfile), with a cb-multios
# checkout bind-mounted read-write at /cb-multios. Builds only the handful of
# challenges the corpus uses, each as:
#
#   i386, non-PIE (ET_EXEC), NX enforced, no stack canary, no RELRO,
#   statically linked (self-contained: the validator sandbox mounts only the
#   ELF, so it must carry libcgc/libc itself).
#
# This matches `protections: [nx]` in corpus/manifest.yaml and the fixture
# build.sh house style. After this finishes, run on the HOST:
#
#   python -m corpus.scripts.build --all --cb-multios <checkout> --update
#
# to hash, pin, and install the ELFs into corpus/binaries/.
#
# See ./README.md for the one-shot host wrapper and the full recipe.
set -uo pipefail

CB=/cb-multios

# cb-multios builds challenges with `-z execstack -z norelro` (to mimic DECREE's
# lack of protections); that re-enables an executable stack AFTER our linker
# flags, so NX never sticks. Flip execstack -> noexecstack at the source. The
# sed is idempotent (a no-op once patched) and touches only that one line.
sed -i 's/-z execstack -z norelro/-z noexecstack -z norelro/' "${CB}/CMakeLists.txt"

cd "${CB}"
echo "### wiping stale build/ ###"
rm -rf build
mkdir -p build && cd build

echo "### configure (i386 / 32.cmake, STATIC, non-PIE, NX, no-canary) ###"
cmake -DCMAKE_EXPORT_COMPILE_COMMANDS=ON \
      -DCMAKE_TOOLCHAIN_FILE=../cmake/32.cmake \
      -DBUILD_SHARED_LIBS=OFF -DBUILD_STATIC_LIBS=ON \
      -DCMAKE_C_FLAGS="-m32 -fno-pie -fno-stack-protector" \
      -DCMAKE_CXX_FLAGS="-m32 -fno-pie -fno-stack-protector" \
      -DCMAKE_EXE_LINKER_FLAGS="-m32 -no-pie -Wl,-z,noexecstack" \
      .. 2>&1 | tail -20
cfg=${PIPESTATUS[0]}
echo "### configure exit: ${cfg} ###"
[ "${cfg}" -eq 0 ] || exit "${cfg}"

# The cb-multios challenge dirs backing each manifest entry (build.challenge).
TARGETS=(Palindrome PCM_Message_decoder basic_messaging router_simulator Particle_Simulator)
rc=0
for t in "${TARGETS[@]}"; do
  echo "### build target: ${t} ###"
  cmake --build . --target "${t}" -- -j"$(nproc)" 2>&1 | tail -6
  ex=${PIPESTATUS[0]}
  echo "### ${t} build exit: ${ex} ###"
  [ "${ex}" -eq 0 ] || rc=1
done

echo "### built ELFs ###"
for t in "${TARGETS[@]}"; do
  f="${CB}/build/challenges/${t}/${t}"
  [ -f "${f}" ] && ls -la "${f}" || echo "MISSING: ${f}"
done
exit "${rc}"
