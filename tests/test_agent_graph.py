# SARA — Sans Agentic Rop Analysis
# Copyright (c) 2026 Jeff Powers. MIT License — see LICENSE.
# SPDX-License-Identifier: MIT
#
# Research instrument for a SANS.edu thesis on LLM agents that build ROP
# exploit chains. The ethical scope in README.md is non-negotiable and binds
# all copies, forks, and derived works: educational/CTF targets only,
# proof-of-concept payloads only. Use against systems you do not own or are
# not authorized to test is prohibited.

"""Tests for the agent state machine.

Exercises the pure-function node behaviour and the router. The LangGraph
build step is not exercised here because importing langgraph at test time
brings in heavy optional dependencies; an integration test covers it
when the dev extras are installed.
"""

from __future__ import annotations

from pathlib import Path

from fakes.backend import FakeBackend, ScriptedTurn

from agent import prompts
from agent.graph import (
    AgentConfig,
    classify_outcome,
    node_enumerate,
    node_ingest,
    node_propose,
    node_reason,
    node_validate,
    route_after_reason,
)
from agent.state import AgentState, BinaryContext, Message
from agent.tools import ToolLayer
from harness.record import FailureMode, Outcome

STRATEGY = prompts.get("zero_shot")


def _state() -> AgentState:
    return AgentState(
        binary=BinaryContext(
            binary_id="sample-overflow",
            binary_path=Path("/tmp/fake"),
            architecture="x86_64",
            protections=["nx"],
        )
    )


def test_ingest_advances_iteration() -> None:
    s = _state()
    out = node_ingest(s)
    assert out.iteration == 1


def test_enumerate_advances_iteration() -> None:
    s = _state()
    out = node_enumerate(s)
    assert out.iteration == 1


def test_propose_advances_iteration() -> None:
    s = _state()
    out = node_propose(s)
    assert out.iteration == 1


def test_validate_terminates_state() -> None:
    s = _state()
    out = node_validate(s)
    assert out.terminated is True
    assert out.termination_reason is not None


def test_route_when_terminated_goes_to_validate() -> None:
    s = _state()
    s.terminated = True
    assert route_after_reason(s) == "validate"


def test_route_when_assistant_has_tool_calls_loops_to_enumerate() -> None:
    s = _state()
    s.messages.append(
        Message(role="assistant", content="...", tool_calls=[{"name": "enumerate_gadgets"}])
    )
    assert route_after_reason(s) == "enumerate"


def test_route_when_candidate_payload_present_goes_to_validate() -> None:
    s = _state()
    s.candidate_payload_path = Path("/tmp/payload.bin")
    assert route_after_reason(s) == "validate"


def test_route_no_tool_call_nudges_then_gives_up() -> None:
    # A no-tool-call turn loops back for bounded nudges (ADR 0012), then gives up
    # via propose once the nudge budget is spent.
    s = _state()
    s.messages.append(Message(role="assistant", content="final answer"))
    assert route_after_reason(s) == "reason"  # nudge_count 0 < default max_nudges
    s.nudge_count = 2  # default max_nudges
    assert route_after_reason(s) == "propose"


def test_route_no_tool_call_gives_up_when_nudges_disabled() -> None:
    s = _state()
    s.messages.append(Message(role="assistant", content="final answer"))
    assert route_after_reason(
        s, AgentConfig(strategy=STRATEGY, tools=ToolLayer(), max_nudges=0)
    ) == ("propose")


def test_classify_success_returns_success() -> None:
    s = _state()
    s.termination_reason = "success"
    outcome, fm = classify_outcome(s)
    assert outcome == Outcome.SUCCESS
    assert fm is None


def test_classify_refusal_returns_safeguard_refusal() -> None:
    s = _state()
    s.termination_reason = "refusal"
    outcome, fm = classify_outcome(s)
    assert outcome == Outcome.SAFEGUARD_REFUSAL
    assert fm == FailureMode.REFUSAL


def test_classify_budget_returns_failure_with_budget_exhausted() -> None:
    s = _state()
    s.termination_reason = "budget"
    outcome, fm = classify_outcome(s)
    assert outcome == Outcome.FAILURE
    assert fm == FailureMode.BUDGET_EXHAUSTED


def test_classify_unknown_returns_failure_other() -> None:
    s = _state()
    s.termination_reason = "agent_gave_up"
    outcome, fm = classify_outcome(s)
    assert outcome == Outcome.FAILURE
    assert fm == FailureMode.OTHER


# --- node_reason: text-format action recovery (ADR 0010) ------------------- #


def test_reason_recovers_text_action_and_loops_to_enumerate() -> None:
    backend = FakeBackend(
        script=[
            ScriptedTurn(text='Thought: look.\nAction: enumerate_gadgets({"binary_path": "/x"})')
        ]
    )
    out = node_reason(_state(), backend)
    last = out.messages[-1]
    assert last.role == "assistant"
    assert last.tool_calls is not None
    assert last.tool_calls[0]["name"] == "enumerate_gadgets"
    assert route_after_reason(out) == "enumerate"


def test_reason_recovers_text_submit_and_routes_to_propose() -> None:
    backend = FakeBackend(
        script=[ScriptedTurn(text='ACTION: submit_payload({"payload_hex": "41"})')]
    )
    out = node_reason(_state(), backend)
    assert route_after_reason(out) == "propose"


def test_reason_prefers_native_tool_call_over_text_action() -> None:
    backend = FakeBackend(
        script=[
            ScriptedTurn(
                text='Action: enumerate_gadgets({"binary_path": "/x"})',
                tool_calls=[{"name": "submit_payload", "input": {"payload_hex": "41"}}],
            )
        ]
    )
    out = node_reason(_state(), backend)
    assert [tc.get("name") for tc in out.messages[-1].tool_calls or []] == ["submit_payload"]
    assert route_after_reason(out) == "propose"


def test_reason_plain_prose_yields_no_tool_calls() -> None:
    # No native call and no Action: line -> nothing to dispatch (nudge/give-up is
    # decided by route_after_reason, covered separately).
    backend = FakeBackend(script=[ScriptedTurn(text="Here is my analysis of the gadgets.")])
    out = node_reason(_state(), backend)
    assert out.messages[-1].tool_calls is None


# --- node_reason: retry-nudge injection (ADR 0012) ------------------------- #


def test_reason_injects_nudge_after_no_tool_call_turn() -> None:
    # Re-entering reason after an assistant turn with no tool call appends a
    # "call a tool" nudge and bumps the counter before the next backend call.
    s = _state()
    s.messages.append(Message(role="assistant", content="just thinking out loud"))
    backend = FakeBackend(script=[ScriptedTurn(text="still thinking")])
    out = node_reason(s, backend)
    assert out.nudge_count == 1
    nudges = [m for m in out.messages if m.role == "user" and "did not call a tool" in m.content]
    assert len(nudges) == 1


def test_reason_does_not_nudge_on_first_entry() -> None:
    # Entered from enumerate (last message is the user-context baseline), not a
    # no-tool-call assistant turn -> no nudge.
    s = _state()
    s.messages.append(Message(role="user", content="Baseline gadget enumeration:\n..."))
    backend = FakeBackend(script=[ScriptedTurn(text="analysis")])
    out = node_reason(s, backend)
    assert out.nudge_count == 0
    assert not any("did not call a tool" in m.content for m in out.messages)
