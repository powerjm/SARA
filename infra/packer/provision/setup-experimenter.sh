#!/usr/bin/env bash
# Packer provisioner 3/3 — the non-root researcher user + provenance records.
# Creates `experimenter` (docker group), hands it the apparatus, seeds .env,
# pins the validator image, and records the baked-in commit + image digest. The
# image hash is treated as a dependent variable of the experiment — its provenance
# is what the replication snapshot's environment summary points at.

set -euo pipefail

SARA_DIR="/opt/sara"
REPO_REF="${SARA_REPO_REF:-main}"

echo ">> creating experimenter user"
if ! id experimenter >/dev/null 2>&1; then
    sudo useradd --create-home --shell /bin/bash experimenter
fi
sudo usermod -aG docker experimenter

echo ">> handing the apparatus to experimenter"
sudo chown -R experimenter:experimenter "${SARA_DIR}"
sudo -u experimenter ln -sfn "${SARA_DIR}" /home/experimenter/sara

# Seed .env (blank keys — filled per run) and pin the validator image name to
# match `make sandbox-build` (sara-sandbox:latest). See ADR-adjacent note in .env.example.
if [[ ! -f "${SARA_DIR}/.env" ]]; then
    sudo -u experimenter cp "${SARA_DIR}/.env.example" "${SARA_DIR}/.env"
fi

echo ">> recording provenance"
COMMIT="$(git -C "${SARA_DIR}" rev-parse HEAD)"
IMAGE_ID="$(sudo docker image inspect sara-sandbox:latest --format '{{.Id}}' 2>/dev/null || echo 'unknown')"
{
    echo "repo_ref=${REPO_REF}"
    echo "commit=${COMMIT}"
    echo "validator_image=sara-sandbox:latest"
    echo "validator_image_id=${IMAGE_ID}"
    echo "built_utc=$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
} | sudo tee /etc/sara-version >/dev/null

# Make the validator image name available to all login shells (the harness reads
# $VALIDATOR_IMAGE; the run-for-record should pin by digest here).
echo "VALIDATOR_IMAGE=sara-sandbox:latest" | sudo tee -a /etc/environment >/dev/null

echo ">> experimenter setup complete (commit ${COMMIT}, image ${IMAGE_ID})"
