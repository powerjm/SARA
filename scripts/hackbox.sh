#!/usr/bin/env bash
# Launch the sara-hackbox exploit-development container with the repo mounted
# read-write and the permissions gdb/strace/pwntools need.
#
# This is a DEV bench, not the validator sandbox: it is intentionally permissive
# (ptrace, unconfined seccomp, network, sudo). It never scores runs — ADR 0002
# keeps the validator (Dockerfile.sandbox) as the sole payload-execution path.
# Anything you prove here you then commit as corpus/exploits/<id>.py and gate
# with `python -m corpus.scripts.verify --id <id>`.
#
# Usage:
#   scripts/hackbox.sh                 # interactive shell in the container
#   scripts/hackbox.sh <cmd> [args…]   # run one command, then exit
#
# Env:
#   IMAGE   image tag to run           (default: sara-hackbox:latest)
#   NETWORK docker --network value     (default: bridge; set to "none" to isolate)

set -euo pipefail

cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd)"

IMAGE="${IMAGE:-sara-hackbox:latest}"
NETWORK="${NETWORK:-bridge}"

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
    echo "error: image '$IMAGE' not found — build it first:" >&2
    echo "    make hackbox-build   # or: docker build -f Dockerfile.hackbox -t $IMAGE ." >&2
    exit 1
fi

# --cap-add=SYS_PTRACE + seccomp=unconfined  -> gdb/strace/ltrace can attach.
# --security-opt apparmor=unconfined         -> ptrace not blocked by AppArmor.
# The repo is bind-mounted read-write at /sara so PoCs authored inside land in
# corpus/exploits/ on the host; corpus/binaries/ is visible via the same mount.
DOCKER_ARGS=(
    --rm -it
    --name sara-hackbox
    --hostname hackbox
    --network "$NETWORK"
    --cap-add=SYS_PTRACE
    --security-opt seccomp=unconfined
    --security-opt apparmor=unconfined
    -v "$REPO_ROOT":/sara
    -w /sara
)

if [ "$#" -eq 0 ]; then
    # Interactive login shell (the image's default CMD).
    exec docker run "${DOCKER_ARGS[@]}" "$IMAGE"
fi

# One-shot: run the given command in a login shell with argument boundaries
# preserved ($0=hackbox so "$@" is exactly the user's argv).
exec docker run "${DOCKER_ARGS[@]}" "$IMAGE" -lc 'exec "$@"' hackbox "$@"
