"""Unit tests for validator.runner (Step 3).

Two surfaces:

* ``chain_fingerprint`` — the ADR 0003 ordered-sequence fingerprint. The key
  property is order-sensitivity: ``[A, B, C]`` and a reordering of it must hash
  differently, which is what separates KNOWN_REDISCOVERY from NEW_DISCOVERY.
* ``execute`` — driven against a ``FakeDockerClient`` so the suite needs no
  Docker daemon (no Docker-in-Docker in CI). The fakes raise the real timeout /
  docker exception types the runner catches.

The fixture's documented chain is ``[0x4011ad, 0x4011ae, 0x401166]`` — the
``pop rdi ; ret`` gadget, the alignment ``ret``, and ``win`` (chain.json's
``documented_gadget_addresses``).
"""

from __future__ import annotations

import shutil
import stat
from pathlib import Path

import pytest

from agent.state import AgentState, BinaryContext
from harness.record import FailureMode, Outcome
from validator.classifier import classify
from validator.runner import _stage_workdir, chain_fingerprint, execute
from validator.runner_test_helpers import (
    FakeDockerClient,
    failing_to_start_client,
    succeeding_client,
    timing_out_client,
)

MARKER = "Hello World"
DOCUMENTED_CHAIN = [0x4011AD, 0x4011AE, 0x401166]


@pytest.fixture
def binary_and_payload(tmp_path: Path) -> tuple[Path, Path]:
    """A throwaway binary + payload pair on disk (contents are irrelevant; the
    fake client never reads them, but ``execute`` checks they exist and copies
    them into the sandbox workdir)."""
    binary = tmp_path / "sample_overflow"
    payload = tmp_path / "payload.bin"
    binary.write_bytes(b"\x7fELF fake binary")
    payload.write_bytes(b"A" * 72 + b"\xad\x11\x40\x00\x00\x00\x00\x00")
    return binary, payload


def test_stage_workdir_is_readable_by_nonroot_sandbox(
    binary_and_payload: tuple[Path, Path],
) -> None:
    """The staged dir must be traversable (o+rx) by the uid-1500 sandbox user.

    Regression for the real-sandbox bug the Step 8 smoke test surfaced: a
    ``0o700`` temp dir owned by the host user made the non-root container fail
    with ``cannot open /work/payload: Permission denied``, collapsing every
    outcome to FAILURE regardless of the chain. The directory must grant others
    read+execute; the files must be readable but never group/other-writable.
    """
    binary, payload = binary_and_payload
    workdir = _stage_workdir(binary, payload)
    try:
        dir_mode = stat.S_IMODE(workdir.stat().st_mode)
        assert dir_mode & stat.S_IROTH and dir_mode & stat.S_IXOTH, oct(dir_mode)

        target = workdir / "target"
        staged_payload = workdir / "payload"
        assert target.is_file() and staged_payload.is_file()

        target_mode = stat.S_IMODE(target.stat().st_mode)
        payload_mode = stat.S_IMODE(staged_payload.stat().st_mode)
        assert target_mode & stat.S_IROTH and target_mode & stat.S_IXOTH  # read+exec
        assert payload_mode & stat.S_IROTH  # readable
        # Nothing staged is writable by group or other (defence in depth).
        assert not (target_mode & (stat.S_IWGRP | stat.S_IWOTH))
        assert not (payload_mode & (stat.S_IWGRP | stat.S_IWOTH))
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _state() -> AgentState:
    return AgentState(
        binary=BinaryContext(
            binary_id="sample-overflow",
            binary_path=Path("/tmp/fake"),
            architecture="x86_64",
            protections=["nx"],
        )
    )


# --------------------------------------------------------------------------- #
# chain_fingerprint — ADR 0003 ordered sequence
# --------------------------------------------------------------------------- #


def test_chain_fingerprint_is_deterministic() -> None:
    assert chain_fingerprint(DOCUMENTED_CHAIN) == chain_fingerprint(DOCUMENTED_CHAIN)


def test_chain_fingerprint_is_order_sensitive() -> None:
    """Reordering the same addresses must change the fingerprint (the whole
    reason the decision was 'ordered', not 'sorted')."""
    forward = chain_fingerprint([0x4011AD, 0x4011AE, 0x401166])
    reversed_ = chain_fingerprint([0x401166, 0x4011AE, 0x4011AD])
    assert forward != reversed_


def test_chain_fingerprint_canonical_encoding() -> None:
    """The digest is sha256 of the zero-padded, comma-joined hex encoding."""
    import hashlib

    expected = hashlib.sha256(b"00000000004011ad,00000000004011ae,0000000000401166").hexdigest()
    assert chain_fingerprint(DOCUMENTED_CHAIN) == expected


def test_chain_fingerprint_empty_chain() -> None:
    import hashlib

    assert chain_fingerprint([]) == hashlib.sha256(b"").hexdigest()


# --------------------------------------------------------------------------- #
# execute — success path and the hardening contract
# --------------------------------------------------------------------------- #


def test_execute_success_runs_hardened_container(
    binary_and_payload: tuple[Path, Path],
) -> None:
    binary, payload = binary_and_payload
    client = succeeding_client(stdout=f"some output {MARKER} more".encode())

    out = execute(binary, payload, success_marker=MARKER, client=client)

    assert out.succeeded is True
    assert out.return_code == 0
    assert out.stdout_marker_found is True

    # The container was launched exactly once, with every required hardening flag.
    assert len(client.containers.run_calls) == 1
    kwargs = client.containers.run_calls[0]
    assert kwargs["network_disabled"] is True
    assert kwargs["read_only"] is True
    assert kwargs["user"] == "1500:1500"
    assert kwargs["mem_limit"] == "256m"
    assert kwargs["pids_limit"] == 64
    assert kwargs["cap_drop"] == ["ALL"]
    assert kwargs["security_opt"] == ["no-new-privileges"]
    assert kwargs["detach"] is True
    # Read-only bind mount of a single workdir.
    assert list(kwargs["volumes"].values()) == [{"bind": "/work", "mode": "ro"}]

    # And it was removed (force) afterward.
    assert client.container.removed is True
    assert client.container.remove_force is True


def test_execute_passes_timeout_to_wait(binary_and_payload: tuple[Path, Path]) -> None:
    binary, payload = binary_and_payload
    client = succeeding_client(stdout=MARKER.encode())

    execute(binary, payload, success_marker=MARKER, timeout_seconds=7, client=client)

    assert client.container.wait_calls == [7]


def test_execute_marker_missing_is_not_success(
    binary_and_payload: tuple[Path, Path],
) -> None:
    """Return code 0 alone is not success — the marker must be on stdout."""
    binary, payload = binary_and_payload
    client = succeeding_client(stdout=b"clean exit, no marker here")

    out = execute(binary, payload, success_marker=MARKER, client=client)

    assert out.succeeded is False
    assert out.return_code == 0
    assert out.stdout_marker_found is False
    assert client.container.removed is True


def test_execute_nonzero_exit_is_not_success(
    binary_and_payload: tuple[Path, Path],
) -> None:
    """Marker present but non-zero exit is still not a success."""
    binary, payload = binary_and_payload
    client = succeeding_client(stdout=MARKER.encode(), status_code=139)

    out = execute(binary, payload, success_marker=MARKER, client=client)

    assert out.succeeded is False
    assert out.return_code == 139
    assert out.stdout_marker_found is True


def test_execute_timeout_kills_and_reports(
    binary_and_payload: tuple[Path, Path],
) -> None:
    binary, payload = binary_and_payload
    client = timing_out_client()

    out = execute(binary, payload, success_marker=MARKER, timeout_seconds=2, client=client)

    assert out.succeeded is False
    assert "timeout" in out.stderr_excerpt
    assert client.container.killed is True
    # Removed in the finally even though wait raised.
    assert client.container.removed is True


def test_execute_container_start_failure_is_reported(
    binary_and_payload: tuple[Path, Path],
) -> None:
    """A docker error launching the container yields a failed ValidatorOutput,
    not an exception — one bad container must not abort a batch."""
    binary, payload = binary_and_payload
    client = failing_to_start_client("no such image: sara-sandbox:latest")

    out = execute(binary, payload, success_marker=MARKER, client=client)

    assert out.succeeded is False
    assert out.return_code == -1
    assert "container failed to start" in out.stderr_excerpt


def test_execute_missing_binary_raises(tmp_path: Path) -> None:
    payload = tmp_path / "payload.bin"
    payload.write_bytes(b"x")
    with pytest.raises(FileNotFoundError):
        execute(
            tmp_path / "nope",
            payload,
            success_marker=MARKER,
            client=FakeDockerClient(),
        )


def test_execute_missing_payload_raises(tmp_path: Path) -> None:
    binary = tmp_path / "bin"
    binary.write_bytes(b"x")
    with pytest.raises(FileNotFoundError):
        execute(
            binary,
            tmp_path / "nope",
            success_marker=MARKER,
            client=FakeDockerClient(),
        )


# --------------------------------------------------------------------------- #
# execute — chain fingerprint -> matched_documented_chain -> classifier
# --------------------------------------------------------------------------- #


def test_execute_matching_chain_is_known_rediscovery(
    binary_and_payload: tuple[Path, Path],
) -> None:
    binary, payload = binary_and_payload
    client = succeeding_client(stdout=MARKER.encode())

    out = execute(
        binary,
        payload,
        success_marker=MARKER,
        candidate_chain=DOCUMENTED_CHAIN,
        documented_chain_fingerprint=chain_fingerprint(DOCUMENTED_CHAIN),
        client=client,
    )

    assert out.matched_documented_chain is True
    assert classify(_state(), out) == (Outcome.KNOWN_REDISCOVERY, None)


def test_execute_reordered_chain_is_new_discovery(
    binary_and_payload: tuple[Path, Path],
) -> None:
    """Same gadgets, different order: a successful but distinct chain. Ordered
    fingerprint -> no match -> NEW_DISCOVERY (the point of ADR 0003)."""
    binary, payload = binary_and_payload
    client = succeeding_client(stdout=MARKER.encode())

    out = execute(
        binary,
        payload,
        success_marker=MARKER,
        candidate_chain=list(reversed(DOCUMENTED_CHAIN)),
        documented_chain_fingerprint=chain_fingerprint(DOCUMENTED_CHAIN),
        client=client,
    )

    assert out.matched_documented_chain is False
    assert classify(_state(), out) == (Outcome.NEW_DISCOVERY, None)


def test_execute_no_documented_fingerprint_never_matches(
    binary_and_payload: tuple[Path, Path],
) -> None:
    binary, payload = binary_and_payload
    client = succeeding_client(stdout=MARKER.encode())

    out = execute(
        binary,
        payload,
        success_marker=MARKER,
        candidate_chain=DOCUMENTED_CHAIN,
        client=client,
    )

    assert out.matched_documented_chain is False
    assert classify(_state(), out) == (Outcome.NEW_DISCOVERY, None)


def test_execute_match_is_independent_of_execution_failure(
    binary_and_payload: tuple[Path, Path],
) -> None:
    """The fingerprint comparison is computed even when the container fails to
    start — though a non-success run never classifies as a rediscovery."""
    binary, payload = binary_and_payload
    client = failing_to_start_client()

    out = execute(
        binary,
        payload,
        success_marker=MARKER,
        candidate_chain=DOCUMENTED_CHAIN,
        documented_chain_fingerprint=chain_fingerprint(DOCUMENTED_CHAIN),
        client=client,
    )

    assert out.matched_documented_chain is True
    assert out.succeeded is False
    assert classify(_state(), out) == (Outcome.FAILURE, FailureMode.OTHER)
