# SARA — Sans Agentic Rop Analysis
# Copyright (c) 2026 Jeff Powers. MIT License — see LICENSE.
# SPDX-License-Identifier: MIT
#
# Research instrument for a SANS.edu thesis on LLM agents that build ROP
# exploit chains. The ethical scope in README.md is non-negotiable and binds
# all copies, forks, and derived works: educational/CTF targets only,
# proof-of-concept payloads only. Use against systems you do not own or are
# not authorized to test is prohibited.

"""Tests for Trial-3 context engineering (ADR 0022): send-time compaction, the
superseding digest, the pinned C1 plan, and the within-run store.

The compaction shapes only the wire payload — ``state.messages`` stays the full
append-only log — so these assert the *sent* messages while proving the log is
untouched and the store is run-scoped.
"""

from __future__ import annotations

from pathlib import Path

from agent.graph import AgentConfig, _build_backend_messages, _established_facts
from agent.state import AgentState, BinaryContext, Message, ToolObservation
from agent.tools import ToolLayer


def _binary() -> BinaryContext:
    return BinaryContext(
        binary_id="sample-overflow",
        binary_path=Path("/tmp/fake"),
        architecture="x86_64",
        protections=["nx"],
    )


def _config(**over: object) -> AgentConfig:
    # strategy is unused by the message-building path; None is fine here.
    params: dict[str, object] = {"strategy": None, "tools": ToolLayer()}
    params.update(over)
    return AgentConfig(**params)  # type: ignore[arg-type]


def _long_state(rounds: int = 12) -> AgentState:
    """A run with `rounds` assistant turns, each a find_gadget call + tool result."""
    state = AgentState(binary=_binary())
    state.messages.append(Message(role="system", content="SYSTEM PROMPT"))
    state.messages.append(Message(role="user", content="TASK: pop a shell on sample-overflow"))
    for i in range(rounds):
        state.messages.append(
            Message(
                role="assistant",
                content=f"reasoning turn {i}",
                tool_calls=[{"id": f"c{i}", "name": "find_gadget", "input": {"query": "pop rdi"}}],
            )
        )
        state.messages.append(
            Message(role="tool", content=f"find_gadget result {i}", tool_call_id=f"c{i}")
        )
        # Same tool + args every round -> the superseding digest keeps ONE line.
        state.observations.append(
            ToolObservation(
                tool_name="find_gadget",
                arguments={"query": "pop rdi"},
                output=f"0x4011ad: pop rdi ; ret  (round {i})",
                truncated=False,
                elapsed_seconds=0.1,
            )
        )
    state.scratchpad["plan"] = "PLAN: ret2syscall; need pop rdi/rsi/rdx, syscall; ret."
    return state


def test_short_run_sends_full_log_unchanged() -> None:
    state = AgentState(binary=_binary())
    state.messages = [
        Message(role="system", content="s"),
        Message(role="user", content="u"),
        Message(role="assistant", content="a"),
    ]
    sent = _build_backend_messages(state, _config())
    assert [m.role for m in sent] == ["system", "user", "assistant"]


def test_compaction_shrinks_the_sent_payload() -> None:
    state = _long_state(rounds=12)
    sent = _build_backend_messages(state, _config())
    # The full log is 2 + 12*2 = 26 messages; the compacted send is far smaller.
    assert len(state.messages) == 26
    assert len(sent) < len(state.messages)
    # ...but the on-disk/replay log is untouched.
    assert len(state.messages) == 26


def test_compaction_keeps_system_head_and_pins_task_and_plan() -> None:
    sent = _build_backend_messages(_long_state(), _config())
    assert sent[0].role == "system"
    joined = "\n".join(m.content for m in sent)
    assert "TASK: pop a shell" in joined  # the original task is pinned
    assert "PLAN: ret2syscall" in joined  # the C1 plan survives compaction
    assert "ESTABLISHED CONTEXT" in joined  # the deterministic facts block


def test_superseding_collapses_duplicate_tool_calls_to_one_line() -> None:
    # Twelve identical find_gadget calls -> exactly one digest line in the facts.
    facts = _established_facts(_long_state(rounds=12))
    assert facts.count("- find_gadget:") == 1


def test_superseding_keeps_distinct_calls_separate() -> None:
    state = _long_state(rounds=0)
    for query, out in [("pop rdi", "0x1"), ("pop rsi", "0x2"), ("pop rdi", "0x3")]:
        state.observations.append(
            ToolObservation(
                tool_name="find_gadget",
                arguments={"query": query},
                output=out,
                truncated=False,
                elapsed_seconds=0.1,
            )
        )
    facts = _established_facts(state)
    # Two distinct (tool,args) keys -> two lines; the repeated 'pop rdi' keeps only
    # its LATEST output (0x3), not the stale 0x1.
    assert facts.count("- find_gadget:") == 2
    assert "0x3" in facts
    assert "0x1" not in facts


def test_compacted_tail_has_no_leading_orphan_tool_result() -> None:
    # Wire-format integrity (ADR 0011): the verbatim tail must not start with a
    # tool_result whose tool_use fell before the cut.
    state = _long_state(rounds=12)
    sent = _build_backend_messages(state, _config(keep_recent_messages=5))
    # Find where the pinned prefix ends (the last consecutive user message) and
    # assert the first message after it is not an orphan tool result.
    non_system = [m for m in sent if m.role != "system"]
    # The tail (everything after the pinned user block) starts on assistant/user.
    tail_start = next(m for m in non_system if m.role not in ("user",))
    assert tail_start.role == "assistant"


def test_context_engineering_off_sends_full_log() -> None:
    state = _long_state(rounds=12)
    sent = _build_backend_messages(state, _config(context_engineering=False))
    assert len(sent) == len(state.messages)


def test_store_is_run_scoped_fresh_state_is_empty() -> None:
    # Within-run only: a new run/thread starts with an empty scratchpad, so no plan
    # or facts leak across the paired-stats independence boundary (Trial 3 §1).
    assert AgentState(binary=_binary()).scratchpad == {}
