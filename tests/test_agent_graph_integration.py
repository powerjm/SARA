# SARA — Sans Agentic Rop Analysis
# Copyright (c) 2026 Jeff Powers. MIT License — see LICENSE.
# SPDX-License-Identifier: MIT
#
# Research instrument for a SANS.edu thesis on LLM agents that build ROP
# exploit chains. The ethical scope in README.md is non-negotiable and binds
# all copies, forks, and derived works: educational/CTF targets only,
# proof-of-concept payloads only. Use against systems you do not own or are
# not authorized to test is prohibited.

"""
End-to-end integration tests for the agent loop on a FakeBackend.

These exercise the whole spine — ingest -> enumerate -> reason -> propose ->
validate — with no API key, no network, no ROPgadget on PATH, and no Docker
daemon: the backend is scripted, the gadget enumerator is a canned callable, and
the validator runs against an injected fake Docker client. The headline case
(done-when) is a scripted submission of the documented chain for `sample_overflow`
yielding a RunRecord whose outcome is SUCCESS (ADR 0009).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fakes.backend import FakeBackend, ScriptedTurn

from agent import prompts
from agent.graph import (
    AgentConfig,
    _to_backend_messages,
    build_graph,
    build_run_record,
    node_propose,
    node_validate,
    run_agent,
)
from agent.state import AgentState, BinaryContext, Message
from agent.tools import ToolLayer
from backends.anthropic_backend import _to_anthropic_messages
from harness.record import FailureMode, MaxTier, Outcome, PromptingStrategy, RunRecord
from mcp_servers.ropgadget.parser import Gadget
from mcp_servers.ropgadget.server import EnumerateResult
from validator.runner import chain_fingerprint
from validator.runner_test_helpers import FakeContainer, succeeding_client

# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _fake_enumerator(**_: object) -> EnumerateResult:
    """A canned ROPgadget result containing the documented gadgets."""
    return EnumerateResult(
        binary_path="sample_overflow",
        total_found=3,
        returned=3,
        truncated=False,
        gadgets=[
            Gadget("0x4011ad", "pop rdi ; ret", 2),
            Gadget("0x4011ae", "ret", 1),
            Gadget("0x401166", "win", 1),
        ],
    )


def _documented_addresses(documented_exploit: Any) -> list[int]:
    chain = documented_exploit.load_chain()
    return [int(addr, 16) for addr in chain["documented_gadget_addresses"]]


def _binary(sample_overflow_path: Path) -> BinaryContext:
    return BinaryContext(
        binary_id="sample-overflow",
        binary_path=sample_overflow_path,
        architecture="x86_64",
        protections=["nx"],
    )


def _config(tmp_path: Path, **overrides: Any) -> AgentConfig:
    base: dict[str, Any] = {
        "strategy": prompts.get("zero_shot"),
        "tools": ToolLayer(enumerate_fn=_fake_enumerator),
        "success_marker": "Hello World",
        "validator_client": succeeding_client(b"Hello World\n"),
        "runs_dir": tmp_path / "runs",
    }
    base.update(overrides)
    return AgentConfig(**base)


def _submit_turn(payload_hex: str, addresses: list[str]) -> ScriptedTurn:
    return ScriptedTurn(
        text="I have a complete chain; submitting.",
        tool_calls=[
            {
                "id": "submit_1",
                "name": "submit_payload",
                "input": {"payload_hex": payload_hex, "chain_addresses": addresses},
            }
        ],
        prompt_tokens=200,
        completion_tokens=40,
        cost_usd=0.0012,
    )


# --------------------------------------------------------------------------- #
# Done-when #3: build_graph(backend) compiles and invokes                     #
# --------------------------------------------------------------------------- #


def test_build_graph_compiles_and_invokes_with_only_a_backend() -> None:
    # A model that reasons without acting is bounded by the real token budget
    # (ADR 0015), not a give-up: the huge token count trips it after one call.
    backend = FakeBackend(
        script=[ScriptedTurn(text="No viable chain; giving up.", completion_tokens=10_000_000)]
    )
    config = AgentConfig(strategy=prompts.get("zero_shot"), tools=ToolLayer())
    app = build_graph(backend, config).compile()
    # A nonexistent binary makes the baseline enumeration fail-soft (no ROPgadget
    # needed); the run still completes and terminates.
    state = AgentState(binary=BinaryContext("b", Path("/nonexistent/binary"), "x86_64", ["nx"]))
    result = app.invoke(state, {"recursion_limit": 32})
    assert result["terminated"] is True
    assert result["termination_reason"] == "token_budget"  # 10M completion tokens trip it
    assert backend.calls_made == 1


# --------------------------------------------------------------------------- #
# Done-when #4: scripted documented chain -> SUCCESS (ADR 0009)                #
# --------------------------------------------------------------------------- #


def test_documented_chain_yields_success_record(
    sample_overflow_path: Path, documented_exploit: Any, tmp_path: Path
) -> None:
    payload = documented_exploit.build_payload()
    addresses = _documented_addresses(documented_exploit)
    fingerprint = chain_fingerprint(addresses)

    backend = FakeBackend(
        script=[_submit_turn(payload.hex(), [f"0x{a:x}" for a in addresses])],
        name="fake",
        version="fake-1",
    )
    config = _config(tmp_path)

    result = run_agent(backend, _binary(sample_overflow_path), config)

    assert result.outcome == Outcome.SUCCESS
    assert result.failure_mode is None
    assert result.validator_output is not None
    assert result.validator_output.succeeded
    # The candidate chain's fingerprint is recorded for uniqueness analysis.
    assert result.validator_output.chain_fingerprint == fingerprint
    assert result.state.candidate_chain == addresses

    record = build_run_record(
        result,
        config,
        binary_id="sample-overflow",
        backend=backend,
        trace_path=tmp_path / "trace.jsonl",
    )
    assert isinstance(record, RunRecord)
    assert record.outcome == Outcome.SUCCESS
    assert record.failure_mode is None
    assert record.prompting_strategy == PromptingStrategy.ZERO_SHOT
    assert record.iterations == 1
    assert record.tokens.total == 240
    assert record.cost.usd == pytest.approx(0.0012)
    # The FakeBackend's model ("fake") is unpriced, so no snapshot is attached
    # (the usd above comes from the scripted turns, not the pricing table).
    assert record.cost.pricing is None
    assert record.payload_path is not None
    # The record round-trips through the schema (the analysis-side contract).
    assert RunRecord.model_validate_json(record.model_dump_json()).outcome == record.outcome


def test_propose_writes_payload_bin(
    sample_overflow_path: Path, documented_exploit: Any, tmp_path: Path
) -> None:
    payload = documented_exploit.build_payload()
    addresses = _documented_addresses(documented_exploit)
    backend = FakeBackend(script=[_submit_turn(payload.hex(), [f"0x{a:x}" for a in addresses])])
    config = _config(tmp_path)

    result = run_agent(backend, _binary(sample_overflow_path), config)

    written = config.runs_dir / config.run_id / "payload.bin"
    assert written.is_file()
    assert written.read_bytes() == payload
    assert result.state.candidate_payload_path == written


# --------------------------------------------------------------------------- #
# ADR 0016: run_exploit_script routes through the same sandbox                 #
# --------------------------------------------------------------------------- #


def _script_turn(source: str, *, call_id: str = "script_1") -> ScriptedTurn:
    return ScriptedTurn(
        text="Running my exploit script.",
        tool_calls=[{"id": call_id, "name": "run_exploit_script", "input": {"script": source}}],
        prompt_tokens=200,
        completion_tokens=40,
        cost_usd=0.0,
    )


# A script that drives the target and does NOT contain the marker literal, so the
# anti-echo guard does not trip and the (fake) sandbox's marker stdout is a success.
_GOOD_SCRIPT = (
    "from pwn import *\nio = process('/work/target')\nio.sendline(b'A' * 72)\nio.interactive()\n"
)


def test_run_exploit_script_yields_success_and_persists_exploit_py(
    sample_overflow_path: Path, tmp_path: Path
) -> None:
    backend = FakeBackend(script=[_script_turn(_GOOD_SCRIPT)], name="fake", version="fake-1")
    config = _config(tmp_path)  # validator_client returns the marker on stdout

    result = run_agent(backend, _binary(sample_overflow_path), config)

    assert result.outcome == Outcome.SUCCESS
    assert result.validator_output is not None and result.validator_output.succeeded
    assert result.state.pending_kind == "script"
    # exploit.py is persisted in the run dir (audit/repro) and state points at it.
    written = config.runs_dir / config.run_id / "exploit.py"
    assert written.is_file()
    assert written.read_text() == _GOOD_SCRIPT
    assert result.state.candidate_script_path == written
    # No hex payload was staged for a pure-script run.
    assert result.state.candidate_payload_path is None


def test_empty_script_is_fed_back_then_recovered(
    sample_overflow_path: Path, tmp_path: Path
) -> None:
    backend = FakeBackend(
        script=[_script_turn("   ", call_id="s0"), _script_turn(_GOOD_SCRIPT, call_id="s1")]
    )
    config = _config(tmp_path)

    result = run_agent(backend, _binary(sample_overflow_path), config)

    # The empty submission was not terminal: it was fed back and the model recovered.
    assert result.outcome == Outcome.SUCCESS
    tool_msgs = [m for m in result.state.messages if m.role == "tool"]
    assert any("non-empty 'script'" in m.content for m in tool_msgs)
    assert (config.runs_dir / config.run_id / "exploit.py").read_text() == _GOOD_SCRIPT


# --------------------------------------------------------------------------- #
# schema v5: context-overflow detection + record telemetry                    #
# --------------------------------------------------------------------------- #


def test_context_overflow_error_ends_run_as_context_overflow(
    sample_overflow_path: Path, tmp_path: Path
) -> None:
    """A provider context-window error is caught and classified, not crashed.

    Trial 1 lost 35 runs to uncaught context-size errors; schema v5 turns them
    into a clean CONTEXT_OVERFLOW failure record.
    """

    class _ContextOverflowBackend(FakeBackend):
        def chat(self, *args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("This model's maximum context length is 8192 tokens")

    backend = _ContextOverflowBackend(script=[ScriptedTurn(text="unused")])
    result = run_agent(backend, _binary(sample_overflow_path), _config(tmp_path))

    assert result.state.termination_reason == "context_overflow"
    assert result.outcome == Outcome.FAILURE
    assert result.failure_mode == FailureMode.CONTEXT_OVERFLOW


def test_non_context_backend_error_is_not_swallowed(
    sample_overflow_path: Path, tmp_path: Path
) -> None:
    """Only context-overflow is caught; a genuine error still surfaces."""

    class _BoomBackend(FakeBackend):
        def chat(self, *args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("some other provider outage")

    backend = _BoomBackend(script=[ScriptedTurn(text="unused")])
    with pytest.raises(RuntimeError, match="some other provider outage"):
        run_agent(backend, _binary(sample_overflow_path), _config(tmp_path))


def test_build_run_record_populates_v5_telemetry(
    sample_overflow_path: Path, documented_exploit: Any, tmp_path: Path
) -> None:
    payload = documented_exploit.build_payload()
    addresses = _documented_addresses(documented_exploit)
    backend = FakeBackend(
        script=[_submit_turn(payload.hex(), [f"0x{a:x}" for a in addresses])],
        name="fake",
        version="fake-1",
    )
    config = _config(tmp_path)
    result = run_agent(backend, _binary(sample_overflow_path), config)
    record = build_run_record(
        result,
        config,
        binary_id="sample-overflow",
        backend=backend,
        trace_path=tmp_path / "t.jsonl",
    )
    # tools_offered captures the advertised set (closing the Trial-1 blind spot);
    # tool_call_counts records what the agent actually called; a success is MARKER.
    assert "submit_payload" in record.tools_offered
    assert "enumerate_gadgets" in record.tools_offered
    assert record.tool_call_counts.get("submit_payload") == 1
    assert record.max_tier_reached == MaxTier.MARKER


def test_novel_chain_still_succeeds(
    sample_overflow_path: Path, documented_exploit: Any, tmp_path: Path
) -> None:
    payload = documented_exploit.build_payload()
    # A different (reordered) chain: still a SUCCESS, with a distinct fingerprint
    # the analysis can count as a separate working chain (ADR 0009).
    backend = FakeBackend(script=[_submit_turn(payload.hex(), ["0x401166", "0x4011ad"])])
    config = _config(tmp_path)

    result = run_agent(backend, _binary(sample_overflow_path), config)

    assert result.validator_output is not None
    assert result.validator_output.succeeded
    assert result.validator_output.chain_fingerprint != chain_fingerprint(
        [0x4011AD, 0x4011AE, 0x401166]
    )
    assert result.outcome == Outcome.SUCCESS


# --------------------------------------------------------------------------- #
# Loop, refusal, and budget paths                                             #
# --------------------------------------------------------------------------- #


def test_enumerate_loop_then_submit(
    sample_overflow_path: Path, documented_exploit: Any, tmp_path: Path
) -> None:
    payload = documented_exploit.build_payload()
    addresses = _documented_addresses(documented_exploit)
    backend = FakeBackend(
        script=[
            ScriptedTurn(
                text="First, enumerate gadgets.",
                tool_calls=[
                    {"id": "e1", "name": "enumerate_gadgets", "input": {"binary_path": "x"}}
                ],
            ),
            _submit_turn(payload.hex(), [f"0x{a:x}" for a in addresses]),
        ]
    )
    config = _config(tmp_path)

    result = run_agent(backend, _binary(sample_overflow_path), config)

    assert backend.calls_made == 2
    assert result.outcome == Outcome.SUCCESS
    # Tool results now: the model's explicit enumerate call, plus the execution
    # feedback from validate (ADR 0014). The gadgets come only from the model's
    # own enumerate call — Trial 2 removed the free baseline dump (hand-holding
    # decision, 2026-07-26), so no "Baseline gadget enumeration:" context exists.
    tool_msgs = [m for m in result.state.messages if m.role == "tool"]
    assert len(tool_msgs) == 2
    assert any("ROP gadgets" in m.content for m in tool_msgs)  # explicit enumerate result
    assert any("EXECUTION SUCCEEDED" in m.content for m in tool_msgs)  # validate feedback
    assert not any(
        m.role == "user" and m.content.startswith("Baseline gadget enumeration:")
        for m in result.state.messages
    )


def test_refusal_via_metadata_yields_safeguard_refusal(
    sample_overflow_path: Path, tmp_path: Path
) -> None:
    backend = FakeBackend(script=[ScriptedTurn(text="No.", stop_reason="refusal")])
    result = run_agent(backend, _binary(sample_overflow_path), _config(tmp_path))
    assert result.outcome == Outcome.SAFEGUARD_REFUSAL
    assert result.failure_mode == FailureMode.REFUSAL
    assert result.validator_output is None  # validator never ran


def test_iteration_cap_yields_iteration_cap_failure(
    sample_overflow_path: Path, tmp_path: Path
) -> None:
    # The backend would loop forever asking for tools; max_iterations cuts it.
    looping = [
        ScriptedTurn(tool_calls=[{"id": "e", "name": "enumerate_gadgets", "input": {}}])
        for _ in range(20)
    ]
    backend = FakeBackend(script=looping)
    result = run_agent(backend, _binary(sample_overflow_path), _config(tmp_path, max_iterations=2))
    assert result.outcome == Outcome.FAILURE
    assert result.failure_mode == FailureMode.ITERATION_CAP  # schema v5 granular mode
    assert backend.calls_made == 2


def test_token_budget_halts_before_overspending(sample_overflow_path: Path, tmp_path: Path) -> None:
    backend = FakeBackend(
        script=[
            ScriptedTurn(
                tool_calls=[{"id": "e", "name": "enumerate_gadgets", "input": {}}],
                prompt_tokens=500,
                completion_tokens=500,
            )
            for _ in range(20)
        ]
    )
    result = run_agent(backend, _binary(sample_overflow_path), _config(tmp_path, token_budget=1500))
    assert result.outcome == Outcome.FAILURE
    assert result.failure_mode == FailureMode.TOKEN_BUDGET  # schema v5 granular mode
    # Two rounds spend 2000 tokens (> 1500), so the third is refused.
    assert backend.calls_made == 2


# --------------------------------------------------------------------------- #
# Iterative validation (ADR 0014): run -> observe -> revise                    #
# --------------------------------------------------------------------------- #


class _SequencedContainers:
    """``client.containers`` returning a different container per ``run`` call, so
    a test can script fail-then-succeed executions. The last entry repeats."""

    def __init__(self, containers: list[Any]) -> None:
        self._containers = list(containers)
        self.run_calls: list[dict[str, Any]] = []

    def run(self, image: str, **kwargs: Any) -> Any:
        self.run_calls.append({"image": image, **kwargs})
        return self._containers.pop(0) if len(self._containers) > 1 else self._containers[0]


class _SequencedClient:
    def __init__(self, containers: list[Any]) -> None:
        self.containers = _SequencedContainers(containers)


def _fail() -> FakeContainer:
    return FakeContainer(status_code=139, stdout=b"")  # segfault, marker absent


def _succeed() -> FakeContainer:
    return FakeContainer(status_code=0, stdout=b"Hello World\n")  # marker present


def test_failed_execution_feeds_back_and_retries_to_success(
    sample_overflow_path: Path, documented_exploit: Any, tmp_path: Path
) -> None:
    """A non-marker execution loops back to reason; the next submit succeeds."""
    payload = documented_exploit.build_payload()
    addrs = [f"0x{a:x}" for a in _documented_addresses(documented_exploit)]
    backend = FakeBackend(
        script=[_submit_turn(payload.hex(), addrs), _submit_turn(payload.hex(), addrs)]
    )
    client = _SequencedClient([_fail(), _succeed()])

    result = run_agent(
        backend, _binary(sample_overflow_path), _config(tmp_path, validator_client=client)
    )

    assert backend.calls_made == 2  # first submit failed, model tried again
    assert result.state.validation_attempts == 2
    assert result.outcome == Outcome.SUCCESS
    # The failed execution was reported back to the model as a tool result.
    assert any(m.role == "tool" and "did NOT succeed" in m.content for m in result.state.messages)


def test_all_executions_fail_hits_iteration_ceiling(
    sample_overflow_path: Path, documented_exploit: Any, tmp_path: Path
) -> None:
    """Repeated failing executions loop until the iteration ceiling, not forever."""
    payload = documented_exploit.build_payload()
    addrs = [f"0x{a:x}" for a in _documented_addresses(documented_exploit)]
    backend = FakeBackend(script=[_submit_turn(payload.hex(), addrs) for _ in range(6)])
    client = _SequencedClient([_fail()])  # always fails

    result = run_agent(
        backend,
        _binary(sample_overflow_path),
        _config(tmp_path, validator_client=client, max_iterations=3),
    )

    assert result.outcome == Outcome.FAILURE
    assert result.failure_mode == FailureMode.ITERATION_CAP  # schema v5 granular mode
    assert backend.calls_made == 3  # bounded by max_iterations, not the 6 scripted
    assert result.state.validation_attempts == 3


def test_malformed_payload_is_now_retryable_not_terminal(
    sample_overflow_path: Path, documented_exploit: Any, tmp_path: Path
) -> None:
    """An undecodable payload_hex is fed back for correction, not a dead end."""
    payload = documented_exploit.build_payload()
    addrs = [f"0x{a:x}" for a in _documented_addresses(documented_exploit)]
    bad = ScriptedTurn(
        text="submitting",
        tool_calls=[{"id": "s0", "name": "submit_payload", "input": {"payload_hex": "nothex!!"}}],
    )
    backend = FakeBackend(script=[bad, _submit_turn(payload.hex(), addrs)])

    result = run_agent(
        backend,
        _binary(sample_overflow_path),
        _config(tmp_path, validator_client=succeeding_client(b"Hello World\n")),
    )

    assert backend.calls_made == 2
    assert result.state.validation_attempts == 1  # only the valid payload ran
    assert result.outcome == Outcome.SUCCESS
    assert any(m.role == "tool" and "Could not decode" in m.content for m in result.state.messages)


# --------------------------------------------------------------------------- #
# Regression (ADR 0011): a turn that mixes an analysis call with a terminal    #
# call routes straight to propose, skipping enumerate — both tool_use blocks   #
# must still be answered, or the next reason request is rejected by a strict    #
# provider API (Anthropic 400: `tool_use` ids ... without `tool_result`).      #
# --------------------------------------------------------------------------- #


def _assert_every_tool_use_answered(api_messages: list[dict[str, Any]]) -> None:
    """Assert every ``tool_use`` block is immediately followed by a user turn
    carrying its matching ``tool_result`` — the pairing the Anthropic Messages
    API enforces (a violation is the 400 that killed run 46a2fec7)."""
    for i, msg in enumerate(api_messages):
        use_ids = [
            b["id"] for b in msg["content"] if isinstance(b, dict) and b.get("type") == "tool_use"
        ]
        if not use_ids:
            continue
        nxt = api_messages[i + 1] if i + 1 < len(api_messages) else {"content": []}
        result_ids = {
            b.get("tool_use_id")
            for b in nxt["content"]
            if isinstance(b, dict) and b.get("type") == "tool_result"
        }
        missing = [uid for uid in use_ids if uid not in result_ids]
        assert not missing, f"orphaned tool_use id(s) after message {i}: {missing}"


def test_mixed_analysis_and_terminal_turn_answers_every_tool_use(
    sample_overflow_path: Path, tmp_path: Path
) -> None:
    config = _config(tmp_path)
    state = AgentState(binary=_binary(sample_overflow_path))
    state.messages.extend(
        [
            Message(role="user", content="Analyze then exploit."),
            Message(
                role="assistant",
                content="Disassembling, and running my exploit in the same turn.",
                tool_calls=[
                    {"id": "toolu_enum", "name": "enumerate_gadgets", "input": {}},
                    {
                        "id": "toolu_script",
                        "name": "run_exploit_script",
                        "input": {"script": "print('marker')"},
                    },
                ],
            ),
        ]
    )

    # This turn routes reason -> propose -> validate (never enumerate); both nodes
    # together must answer both tool_use blocks.
    node_propose(state, config)
    node_validate(state, config)

    # The analysis call got a tool_result (not just the terminal call).
    answered = {m.tool_call_id for m in state.messages if m.role == "tool"}
    assert {"toolu_enum", "toolu_script"} <= answered

    # And the serialized Anthropic stream is valid — the exact invariant the API
    # rejected in the failing run.
    api_messages, _ = _to_anthropic_messages(_to_backend_messages(state.messages))
    _assert_every_tool_use_answered(api_messages)
