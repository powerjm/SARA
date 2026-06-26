#!/usr/bin/env bash
# Packer provisioner 2/3 — binary-analysis tools + the apparatus itself.
# Clones the repo at the pinned ref into /opt/sara, bootstraps the venv, installs
# the Python-based tools (ROPgadget, ropper), optionally installs Ghidra, and
# builds the validator sandbox image so a provisioned instance can run the matrix
# without any further setup.

set -euo pipefail

REPO_URL="${SARA_REPO_URL:?SARA_REPO_URL not set}"
REPO_REF="${SARA_REPO_REF:-main}"
SARA_DIR="/opt/sara"
GHIDRA_VERSION="${GHIDRA_VERSION:-11.4.3}"
# The public release asset carries a build-date suffix; override GHIDRA_URL to pin
# an exact asset. Ghidra is optional (Step 7) — its tests skip when it is absent.
GHIDRA_URL="${GHIDRA_URL:-}"

echo ">> cloning ${REPO_URL} @ ${REPO_REF} into ${SARA_DIR}"
sudo git clone "${REPO_URL}" "${SARA_DIR}"
sudo git -C "${SARA_DIR}" checkout "${REPO_REF}"

echo ">> bootstrapping the apparatus (venv + pinned deps)"
sudo make -C "${SARA_DIR}" bootstrap

echo ">> installing Python binary tools (ROPgadget, ropper)"
sudo "${SARA_DIR}/.venv/bin/pip" install ROPgadget ropper

echo ">> building the validator sandbox image (sara-sandbox:latest)"
sudo make -C "${SARA_DIR}" sandbox-build

# --- Ghidra (optional) ----------------------------------------------------- #
if [[ -n "${GHIDRA_URL}" ]]; then
    echo ">> installing Ghidra ${GHIDRA_VERSION}"
    tmp="$(mktemp -d)"
    if curl -fsSL "${GHIDRA_URL}" -o "${tmp}/ghidra.zip"; then
        sudo unzip -q "${tmp}/ghidra.zip" -d /opt
        sudo ln -sfn "$(find /opt -maxdepth 1 -type d -name 'ghidra_*' | head -1)" /opt/ghidra
        echo "GHIDRA_INSTALL_DIR=/opt/ghidra" | sudo tee -a /etc/environment >/dev/null
    else
        echo "!! Ghidra download failed; continuing without it (its tests skip when absent)" >&2
    fi
    rm -rf "${tmp}"
else
    echo "!! GHIDRA_URL not set; skipping Ghidra (set it to the pinned ${GHIDRA_VERSION} asset to include it)" >&2
fi

echo ">> verifying the suite passes on the baked image"
sudo make -C "${SARA_DIR}" test

echo ">> tools install complete"
