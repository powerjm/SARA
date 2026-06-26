# Toolchain image for building the CGC (cb-multios) corpus binaries as clean
# static-address ROP targets. Produces the i386 ELFs whose SHA-256s are pinned
# in corpus/manifest.yaml.
#
# Why not upstream's own Dockerfile? It pins ubuntu:18.04, but cb-multios HEAD
# (810d7b24) uses CMake's add_compile_definitions() (CMake >= 3.12), which
# 18.04's cmake 3.10 lacks. 22.04 ships cmake 3.22 + clang 14 + gcc-multilib,
# which satisfies the i386 `clang -m32` toolchain that cmake/32.cmake selects.
#
# The resulting binary SHAs are this lab host's build (the manifest/README treat
# the pin as toolchain-specific, re-pinned deliberately with build.py --update).
FROM ubuntu:22.04

RUN set -eux; \
    apt-get update; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      build-essential libc6-dev libc6-dev-i386 gcc-multilib g++-multilib \
      clang cmake make python3 python3-pip ca-certificates; \
    ln -sf /usr/bin/python3 /usr/local/bin/python; \
    rm -rf /var/lib/apt/lists/*

# Optional Python helpers cb-multios's CMake/poll generation may import.
# Building the unpatched binary targets doesn't need polls, so this is
# best-effort and must not fail the image.
RUN pip3 install --no-cache-dir xlsxwriter defusedxml pyyaml matplotlib pycryptodome \
      || echo "warning: optional python build deps failed to install (continuing)"

WORKDIR /cb-multios
ENTRYPOINT ["/bin/bash"]
