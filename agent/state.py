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
Agent state.

The dataclass below is what flows between LangGraph nodes. Keep it small and
serializable; large per-iteration artifacts (full tool outputs, intermediate
gadget lists) belong in the trace JSONL written by the harness, not in this
in-memory state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from harness.record import ValidatorOutput


@dataclass(slots=True)
class BinaryContext:
    """Static, per-binary context loaded at the start of a run."""

    binary_id: str
    binary_path: Path
    architecture: str
    protections: list[str]
    notes: str = ""


@dataclass(slots=True)
class Message:
    """Single message in the agent's conversation log."""

    role: str  # "system" | "user" | "assistant" | "tool"
    content: str
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None


@dataclass(slots=True)
class ToolObservation:
    """Result of one tool call. Truncated to a token budget."""

    tool_name: str
    arguments: dict[str, Any]
    output: str
    truncated: bool
    elapsed_seconds: float


@dataclass
class AgentState:
    """Mutable state threaded through the LangGraph.

    Kept small and (re)constructable from its own fields: LangGraph rebuilds the
    dataclass from channel values between supersteps, so every field carries a
    default and the whole state round-trips through ``AgentState(**fields)``.
    """

    binary: BinaryContext
    messages: list[Message] = field(default_factory=list)
    observations: list[ToolObservation] = field(default_factory=list)
    iteration: int = 0

    # Run-scoped scratchpad / store (ADR 0022): the context-engineering substrate,
    # strictly WITHIN-RUN — a fresh state starts empty, so a second run/thread can
    # never see another's store (the independence the paired stats assume, Trial 3
    # §1). Holds the pinned C1 plan (key ``"plan"``) and anything else the
    # send-time compaction pins into the stable prefix. ``messages`` stays the full
    # append-only log (trace/replay unaffected); compaction happens only in what is
    # *sent* to the backend, reading this store for the facts it pins.
    scratchpad: dict[str, str] = field(default_factory=dict)

    # Token + cost accumulators, summed across reason rounds for the RunRecord.
    tokens_used: int = 0  # prompt + completion, running total (budget check)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0

    # Filled in when the agent commits to a candidate.
    candidate_payload_path: Path | None = None
    # The ordered gadget/target addresses the proposer committed to, fed to the
    # validator for chain-fingerprint matching (ADR 0003).
    candidate_chain: list[int] | None = None
    # Script mode (ADR 0016): set by propose when the agent commits an exploit.py
    # via run_exploit_script; validate runs it through the sandbox's execute_script
    # path. ``pending_kind`` records which artifact the pending validation runs
    # ("payload" or "script"), so a run that mixes hex submits and script runs
    # across iterations validates the right one each time.
    candidate_script_path: Path | None = None
    pending_kind: str | None = None

    # Set by the validate node from the sandbox result; read at classification.
    validator_output: ValidatorOutput | None = None

    # Wall-clock anchor: monotonic timestamp set by ``node_ingest`` so later
    # nodes can enforce the wall-clock budget. ``None`` until ingest runs.
    started_monotonic: float | None = None

    # Count of "you must call a tool" nudges issued after a reason turn produced
    # no tool call (bounded by AgentConfig.max_nudges; ADR 0012).
    nudge_count: int = 0

    # Count of reason turns re-issued because the model's reply hit the output
    # -token cap and was truncated mid-tool-call (bounded by
    # AgentConfig.max_truncation_retries; ADR 0013).
    truncation_retries: int = 0

    # Iterative validation (ADR 0014): the agent may execute candidate payloads
    # repeatedly, each result fed back so it can revise. ``pending_validation`` is
    # set by ``propose`` when it decodes a fresh candidate and consumed by
    # ``validate``; ``validation_attempts`` counts executions for the trace.
    pending_validation: bool = False
    validation_attempts: int = 0

    # Terminal state markers (set by graph nodes; harness reads them on exit).
    terminated: bool = False
    termination_reason: str | None = None
    # one of: "success" | "refusal" | "truncated" | "agent_gave_up"
    #       | "token_budget" | "wall_clock" | "iteration_cap" | "context_overflow"
    # (schema v5 split the old coarse "budget" into the three resource limits plus
    #  "context_overflow" for a provider context-window rejection)


__all__ = ["AgentState", "BinaryContext", "Message", "ToolObservation"]
