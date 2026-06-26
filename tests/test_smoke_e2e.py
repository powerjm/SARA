"""
Step 8 end-to-end smoke test: FakeBackend + real ROPgadget + real sandbox.

Unlike ``test_agent_graph_integration.py`` (which uses a canned enumerator and an
injected fake Docker client), this exercises the **real** tool and validator
paths through the production ``run_one`` harness:

* gadget enumeration runs the real ROPgadget CLI against the fixture binary (the
  graph's baseline enumeration dispatches it on the real binary path),
* the candidate payload is executed in the real, locked-down Docker sandbox,
* a real ``{record.json, trace.jsonl, payload.bin}`` triple is persisted.

The done-when (Step 8) is the headline assertion: exactly one ``KNOWN_REDISCOVERY``
record lands on disk. The whole thing runs in well under five minutes.

It is gated so the everyday suite stays green off the lab host: the
``requires_ropgadget`` marker skips it when the ROPgadget CLI is absent, and the
Docker/sandbox-image check skips it when the daemon or image is not present. On
the lab host (where the run-for-record happens) both are present and the test
runs for real — it is the last gate before a real matrix run.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from fakes.backend import FakeBackend, ScriptedTurn

from agent.tools import ToolLayer
from harness import corpus
from harness.persistence import load_record
from harness.record import Outcome
from harness.runner import RunSettings, run_one
from mcp_servers.ropgadget import server as ropgadget

pytestmark = pytest.mark.requires_ropgadget


def _sandbox_image() -> str:
    """The image ``execute`` will use — env override or the runner default."""
    return os.environ.get("VALIDATOR_IMAGE") or "sara-sandbox:latest"


def _require_docker_sandbox_or_skip(image: str) -> None:
    """Skip (don't fail) unless the Docker daemon and the sandbox image are ready."""
    docker = pytest.importorskip("docker", reason="docker SDK not installed")
    try:
        client = docker.from_env()
        client.ping()
    except Exception as exc:  # noqa: BLE001 - any daemon problem -> skip, not fail
        pytest.skip(f"Docker daemon not available: {exc}")
    try:
        client.images.get(image)
    except Exception:  # noqa: BLE001 - ImageNotFound (and friends) -> actionable skip
        pytest.skip(f"sandbox image {image!r} not present; run `make sandbox-build` first")


def test_smoke_e2e_known_rediscovery(
    fixture_corpus: Any,
    documented_exploit: Any,
    tmp_path: Path,
) -> None:
    image = _sandbox_image()
    _require_docker_sandbox_or_skip(image)

    # fixture_corpus points SARA_CORPUS_* at a throwaway corpus exposing the real
    # sample_overflow ELF under the id `sample-overflow`.
    spec = corpus.resolve_binary(fixture_corpus.binary_id)

    # --- real ROPgadget is genuinely in the loop -------------------------- #
    # Enumerate against the real binary with the real CLI and confirm it finds
    # the documented gadgets (include_duplicates surfaces the dedup'd alignment
    # `ret`). Compared by integer value because the parser canonicalises to a
    # zero-padded hex string. The chain's `win` entry is a jump *target*, not a
    # gadget, so we check the chain's documented gadget addresses, not every
    # address in the chain. If ROPgadget were broken this fails here, rather than
    # passing silently on the documented payload alone.
    enumerated = ropgadget.enumerate_gadgets(
        binary_path=str(spec.binary_path), include_duplicates=True
    )
    found = {int(g.address, 16) for g in enumerated.gadgets}
    gadget_addrs = {int(g["address"], 16) for g in documented_exploit.load_chain()["gadgets"]}
    assert gadget_addrs, "fixture chain.json declares no gadgets"
    missing = {hex(a) for a in gadget_addrs - found}
    assert gadget_addrs <= found, f"ROPgadget missed documented gadgets: {missing}"

    # --- end-to-end run through the production harness -------------------- #
    payload = documented_exploit.build_payload()
    addresses = [f"0x{a:x}" for a in spec.documented_gadget_addresses]

    backend = FakeBackend(
        script=[
            ScriptedTurn(
                text="Chain assembled; submitting.",
                tool_calls=[
                    {
                        "id": "submit_1",
                        "name": "submit_payload",
                        "input": {"payload_hex": payload.hex(), "chain_addresses": addresses},
                    }
                ],
                prompt_tokens=200,
                completion_tokens=40,
                cost_usd=0.0,
            )
        ],
        name="fake",
        version="fake-1",
    )
    settings = RunSettings.from_env(output_dir=tmp_path / "runs")

    record = run_one(
        spec,
        backend,
        "zero_shot",
        settings,
        tools=ToolLayer(),  # real ROPgadget enumerator (the default)
        validator_client=None,  # real docker.from_env() -> real sandbox
    )

    assert record.outcome == Outcome.KNOWN_REDISCOVERY
    assert record.failure_mode is None
    assert record.validator is not None
    assert record.validator.succeeded
    assert record.validator.matched_documented_chain

    # Exactly one KNOWN_REDISCOVERY record landed on disk, and it round-trips.
    records = sorted(settings.output_dir.glob("*/record.json"))
    assert len(records) == 1
    persisted = load_record(records[0].parent)
    assert persisted.outcome == Outcome.KNOWN_REDISCOVERY
    assert persisted.payload_path is not None and Path(persisted.payload_path).is_file()
