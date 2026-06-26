"""
Validator sandbox runner.

The validator is the **only** component in the system that executes candidate
ROP payloads (ADR 0002). It runs a payload against a corpus binary inside a
locked-down Docker container:

  - no network (``network_disabled=True``)
  - read-only root filesystem (``read_only=True``)
  - non-root user (uid:gid 1500:1500)
  - capped memory and pids, all capabilities dropped, no privilege escalation
  - a single read-only bind mount holding *only* the target binary and payload
  - a host-side wall-clock cap, with the sandbox image's ``timeout`` entrypoint
    as defence in depth

``execute`` returns a ``ValidatorOutput`` (see ``harness.record``) that the
harness folds into the ``RunRecord``. The container is always removed in a
``finally:`` block, even on timeout.

The chain fingerprint (``chain_fingerprint``) is the SHA-256 of the *ordered*
gadget-address sequence — see ADR 0003. It is defined here, once, and used both
by the harness (to fingerprint the documented chain) and by ``execute`` (to
fingerprint the candidate chain the proposer committed to).
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import time
from collections.abc import Iterable, Sequence
from contextlib import suppress
from pathlib import Path
from typing import Any

from harness.record import ValidatorOutput

DEFAULT_TIMEOUT_SECONDS = 30

# Container-side layout. The binary and payload are copied into a private temp
# dir mounted read-only at _WORK_MOUNT under fixed names, so the run command is
# a constant with no host-controlled strings (no shell-injection surface) and
# the sandbox sees nothing but these two files.
_WORK_MOUNT = "/work"
_TARGET_NAME = "target"
_PAYLOAD_NAME = "payload"
_RUN_COMMAND = [
    "/bin/sh",
    "-c",
    f"{_WORK_MOUNT}/{_TARGET_NAME} < {_WORK_MOUNT}/{_PAYLOAD_NAME}",
]

# stdout/stderr are stored as bounded excerpts on the record, not in full; the
# complete logs are not retained (the marker decision is made on the full text
# before truncation).
_EXCERPT_LIMIT = 4_000


def chain_fingerprint(addresses: Iterable[int]) -> str:
    """SHA-256 over the **ordered** gadget-address sequence (ADR 0003).

    Each address is encoded as a zero-padded 16-digit lowercase hex string
    (64-bit), the sequence is joined in order with commas, and the digest is the
    hex SHA-256 of that ASCII encoding. Order is significant — the sequence is
    not sorted — so a reordered chain produces a different fingerprint.
    """
    encoded = ",".join(f"{int(addr):016x}" for addr in addresses)
    return hashlib.sha256(encoded.encode("ascii")).hexdigest()


def _matches_documented(
    candidate_chain: Sequence[int] | None,
    documented_chain_fingerprint: str | None,
) -> bool:
    """True iff a documented fingerprint was supplied and the candidate matches."""
    if documented_chain_fingerprint is None or candidate_chain is None:
        return False
    return chain_fingerprint(candidate_chain) == documented_chain_fingerprint


def _excerpt(text: str, limit: int = _EXCERPT_LIMIT) -> str:
    """Bound a captured stream to ``limit`` chars, noting how much was dropped."""
    if len(text) <= limit:
        return text
    return f"{text[:limit]}... [truncated {len(text) - limit} chars]"


def _stage_workdir(binary_path: Path, payload_path: Path) -> Path:
    """Copy the target + payload into a private temp dir for the read-only mount.

    Permissions matter for correctness, not just hygiene: the sandbox container
    runs as a **non-root** user (uid 1500) that is a *different* uid than the
    host user which created this directory. ``mkdtemp`` makes the directory mode
    ``0o700`` (owner-only), so without widening it the container cannot even
    traverse ``/work`` to open the payload — the run fails with
    ``cannot open /work/payload: Permission denied`` and every outcome collapses
    to FAILURE regardless of the chain. The directory is therefore made
    world-traversable (``0o755``) and the files world-readable / read-exec. This
    is safe: the mount is read-only, nothing inside is writable, and the dir
    holds only these two already-world-readable files.
    """
    workdir = Path(tempfile.mkdtemp(prefix="sara-validator-"))
    target = workdir / _TARGET_NAME
    payload = workdir / _PAYLOAD_NAME
    shutil.copy(binary_path, target)
    shutil.copy(payload_path, payload)
    target.chmod(0o555)
    payload.chmod(0o444)
    workdir.chmod(0o755)
    return workdir


def execute(
    binary_path: Path,
    payload_path: Path,
    *,
    success_marker: str,
    candidate_chain: Sequence[int] | None = None,
    documented_chain_fingerprint: str | None = None,
    image: str | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    client: Any = None,
) -> ValidatorOutput:
    """Run ``payload_path`` against ``binary_path`` in the validator sandbox.

    Parameters
    ----------
    binary_path
        Host path to the corpus binary. Copied into the sandbox; never mounted
        from its original directory.
    payload_path
        Host path to the candidate payload bytes, fed to the binary on stdin.
    success_marker
        String that must appear on stdout for the run to count as successful.
        Defined in ``corpus/manifest.yaml`` (mirrored in the fixture's
        ``chain.json``).
    candidate_chain
        The ordered gadget/target addresses the proposer committed to. Used —
        together with ``documented_chain_fingerprint`` — to decide
        ``matched_documented_chain`` (ADR 0003). ``None`` when the chain is
        unknown (the run can still succeed, it just won't match).
    documented_chain_fingerprint
        ``chain_fingerprint`` of the documented exploit's chain. When supplied
        and equal to the candidate chain's fingerprint, ``matched_documented_chain``
        is set — the signal the classifier turns into ``KNOWN_REDISCOVERY``.
    image
        Sandbox image. Defaults to ``$VALIDATOR_IMAGE`` or ``sara-sandbox:latest``.
    timeout_seconds
        Host-side wall-clock cap. On expiry the container is killed, the run is
        not successful, and ``"timeout"`` appears in ``stderr_excerpt``.
    client
        Docker client (anything exposing ``containers.run`` returning a
        detached container). Defaults to ``docker.from_env()``. Injected by
        tests so the unit suite needs no Docker daemon.

    Returns
    -------
    ValidatorOutput
        Never raises on container/daemon failure: a failed launch is reported as
        an unsuccessful ``ValidatorOutput`` so one bad container cannot abort a
        batch. Only a missing binary/payload (a caller bug) raises.
    """
    image = image or os.environ.get("VALIDATOR_IMAGE", "sara-sandbox:latest")

    if not binary_path.is_file():
        raise FileNotFoundError(f"binary not found: {binary_path}")
    if not payload_path.is_file():
        raise FileNotFoundError(f"payload not found: {payload_path}")

    matched = _matches_documented(candidate_chain, documented_chain_fingerprint)

    import requests
    from docker.errors import DockerException

    timeout_exc = (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError)

    if client is None:
        import docker

        client = docker.from_env()

    workdir = _stage_workdir(binary_path, payload_path)
    try:
        started = time.monotonic()
        try:
            container = client.containers.run(
                image,
                command=_RUN_COMMAND,
                volumes={str(workdir): {"bind": _WORK_MOUNT, "mode": "ro"}},
                network_disabled=True,
                read_only=True,
                user="1500:1500",
                mem_limit="256m",
                pids_limit=64,
                cap_drop=["ALL"],
                security_opt=["no-new-privileges"],
                detach=True,
            )
        except DockerException as exc:
            return ValidatorOutput(
                succeeded=False,
                return_code=-1,
                stdout_marker_found=False,
                matched_documented_chain=matched,
                stderr_excerpt=_excerpt(f"container failed to start: {exc}"),
                elapsed_seconds=time.monotonic() - started,
            )

        timed_out = False
        status_code = -1
        stdout_text = ""
        stderr_text = ""
        error_text = ""
        try:
            try:
                result = container.wait(timeout=timeout_seconds)
                status_code = int(result.get("StatusCode", -1))
            except timeout_exc:
                timed_out = True
                with suppress(Exception):
                    container.kill()
            except DockerException as exc:
                error_text = f"wait failed: {exc}"
            with suppress(Exception):
                stdout_text = container.logs(stdout=True, stderr=False).decode("utf-8", "replace")
            with suppress(Exception):
                stderr_text = container.logs(stdout=False, stderr=True).decode("utf-8", "replace")
        finally:
            with suppress(Exception):
                container.remove(force=True)

        elapsed = time.monotonic() - started
        marker_found = success_marker in stdout_text
        succeeded = (not timed_out) and (not error_text) and status_code == 0 and marker_found

        stderr_parts = [part for part in (stderr_text, error_text) if part]
        if timed_out:
            stderr_parts.append("timeout")

        return ValidatorOutput(
            succeeded=succeeded,
            return_code=status_code,
            stdout_marker_found=marker_found,
            matched_documented_chain=matched,
            stdout_excerpt=_excerpt(stdout_text),
            stderr_excerpt=_excerpt("\n".join(stderr_parts)),
            elapsed_seconds=elapsed,
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


__all__ = ["DEFAULT_TIMEOUT_SECONDS", "chain_fingerprint", "execute"]
