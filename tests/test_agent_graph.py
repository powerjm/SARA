"""Tests for the agent state machine.

Exercises the pure-function node behaviour and the router. The LangGraph
build step is not exercised here because importing langgraph at test time
brings in heavy optional dependencies; an integration test covers it
when the dev extras are installed.
"""

from __future__ import annotations

from pathlib import Path

from agent.graph import (
    classify_outcome,
    node_enumerate,
    node_ingest,
    node_propose,
    node_validate,
    route_after_reason,
)
from agent.state import AgentState, BinaryContext, Message
from harness.record import FailureMode, Outcome


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


def test_route_default_goes_to_propose() -> None:
    s = _state()
    s.messages.append(Message(role="assistant", content="final answer"))
    assert route_after_reason(s) == "propose"


def test_classify_success_returns_known_rediscovery() -> None:
    s = _state()
    s.termination_reason = "success"
    outcome, fm = classify_outcome(s)
    assert outcome == Outcome.KNOWN_REDISCOVERY
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
