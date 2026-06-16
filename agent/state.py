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

    # Set by the validate node from the sandbox result; read at classification.
    validator_output: ValidatorOutput | None = None

    # Wall-clock anchor: monotonic timestamp set by ``node_ingest`` so later
    # nodes can enforce the wall-clock budget. ``None`` until ingest runs.
    started_monotonic: float | None = None

    # Terminal state markers (set by graph nodes; harness reads them on exit).
    terminated: bool = False
    termination_reason: str | None = None
    # one of: "success" | "budget" | "refusal" | "tool_use_malformed" | "agent_gave_up"


__all__ = ["AgentState", "BinaryContext", "Message", "ToolObservation"]
