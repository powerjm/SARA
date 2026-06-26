#!/usr/bin/env bash
# Packer provisioner 1/3 — base OS for the SARA experiment host.
# Installs the C toolchain, Python 3.14, Docker, JDK 21, and the small extras the
# apparatus needs (zstd for snapshots, 32-bit libs for i386 corpus targets).
# Mirrors the "System packages" block in docs/REPRODUCTION.md.

set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

echo ">> apt update + base packages"
sudo apt-get update -y
sudo apt-get install -y --no-install-recommends \
    build-essential curl ca-certificates git unzip zstd \
    python3.14 python3.14-venv python3-pip \
    gdb gdbserver radare2 \
    openjdk-21-jdk \
    docker.io docker-buildx \
    gcc-multilib libc6-i386

echo ">> enabling docker"
sudo systemctl enable --now docker

# Pin Java to 21 (Ghidra 11.4.3 requires it; see docs/adr/0004-ghidra-bridge.md).
if update-alternatives --list java 2>/dev/null | grep -q 'java-21'; then
    sudo update-alternatives --set java "$(update-alternatives --list java | grep 'java-21' | head -1)"
fi

echo ">> base install complete: $(python3.14 --version), $(docker --version)"
