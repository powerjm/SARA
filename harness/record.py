"""
Run record schema.

A run record is one row in the experiment matrix:
(binary, backend, prompting_strategy) -> outcome + telemetry.

This module is the canonical schema. Every component that emits run data
serializes through these Pydantic models. The analysis pipeline deserializes
through them. If you change a field, you change the experiment.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, NonNegativeFloat, NonNegativeInt, computed_field

# --------------------------------------------------------------------------- #
# Enums                                                                       #
# --------------------------------------------------------------------------- #


class BackendCategory(StrEnum):
    """Three backend categories defined by the experimental design."""

    PREMIUM = "premium"
    OPEN_WEIGHT = "open_weight"
    UNRESTRICTED = "unrestricted"


class PromptingStrategy(StrEnum):
    """Named prompting strategies. Add new ones here (and add tests)."""

    ZERO_SHOT = "zero_shot"
    CHAIN_OF_THOUGHT = "chain_of_thought"
    REACT = "react"


class Outcome(StrEnum):
    """
    Four-way outcome classification.

    KNOWN_REDISCOVERY  Agent reproduced the documented exploit chain.
    NEW_DISCOVERY      Agent produced a working chain distinct from the doc.
    FAILURE            Agent failed to produce a working chain (see failure_mode).
    SAFEGUARD_REFUSAL  Backend refused to perform the task on policy grounds.
    """

    KNOWN_REDISCOVERY = "known_rediscovery"
    NEW_DISCOVERY = "new_discovery"
    FAILURE = "failure"
    SAFEGUARD_REFUSAL = "safeguard_refusal"


class FailureMode(StrEnum):
    """
    Why a non-successful run ended. Populated on FAILURE and SAFEGUARD_REFUSAL.

    Codes are deliberately coarse; finer-grained taxonomy lives in qualitative
    coding done at analysis time and stored in the trace, not the record.
    """

    HALLUCINATED_GADGET = "hallucinated_gadget"  # cited addr not present in binary
    WRONG_REGISTER_REASONING = "wrong_register_reasoning"
    BAD_CHAIN_ORDERING = "bad_chain_ordering"
    CONSTRAINT_VIOLATION = "constraint_violation"  # bad bytes / alignment / etc.
    TOOL_USE_MALFORMED = "tool_use_malformed"  # backend emitted invalid tool calls
    BUDGET_EXHAUSTED = "budget_exhausted"  # tokens or wall-clock cap
    TIMEOUT = "timeout"  # validator-side
    REFUSAL = "refusal"  # policy refusal
    OTHER = "other"


# --------------------------------------------------------------------------- #
# Sub-records                                                                  #
# --------------------------------------------------------------------------- #


class BackendInfo(BaseModel):
    """Provider-agnostic backend descriptor."""

    category: BackendCategory
    name: str  # human-friendly: "claude-sonnet-4-6"
    version: str  # exact API model string
    temperature: float = 0.2
    seed: int | None = 0


class TokenUsage(BaseModel):
    """Token counts as reported by the provider. Both sides if available."""

    prompt: NonNegativeInt = 0
    completion: NonNegativeInt = 0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total(self) -> int:
        return self.prompt + self.completion


class CostRecord(BaseModel):
    """USD cost. Local models record 0.0 and rely on hardware_utilization fields."""

    usd: NonNegativeFloat = 0.0
    # Approximate hardware cost for local runs, computed from wall_clock_seconds
    # and a configured $/hour rate. Populated by the harness, not the backend.
    hardware_usd_estimate: NonNegativeFloat = 0.0


class ValidatorOutput(BaseModel):
    """Validator sandbox output for one payload execution."""

    succeeded: bool
    return_code: int
    stdout_marker_found: bool
    matched_documented_chain: bool  # True iff outcome should be KNOWN_REDISCOVERY
    stdout_excerpt: str = ""
    stderr_excerpt: str = ""
    elapsed_seconds: NonNegativeFloat = 0.0


# --------------------------------------------------------------------------- #
# Top-level run record                                                        #
# --------------------------------------------------------------------------- #


class RunRecord(BaseModel):
    """
    Top-level run record. One file per run.

    Invariants enforced at construction time:
      - Outcome.FAILURE requires a failure_mode.
      - Outcome.SAFEGUARD_REFUSAL implies failure_mode in {None, REFUSAL}.
      - Success outcomes (KNOWN_REDISCOVERY, NEW_DISCOVERY) forbid failure_mode.

    Persistence: a run produces exactly one RunRecord file at
    `runs/<run_id>/record.json`, plus an associated trace JSONL at
    `runs/<run_id>/trace.jsonl` and a payload at `runs/<run_id>/payload.bin`.
    """

    schema_version: Literal["1"] = "1"

    run_id: UUID = Field(default_factory=uuid4)
    binary_id: str  # foreign key into corpus/manifest.yaml
    backend: BackendInfo
    prompting_strategy: PromptingStrategy

    started_at: datetime
    ended_at: datetime
    wall_clock_seconds: NonNegativeFloat

    outcome: Outcome
    failure_mode: FailureMode | None = None

    iterations: NonNegativeInt
    tokens: TokenUsage
    cost: CostRecord

    trace_path: Path
    payload_path: Path | None = None
    validator: ValidatorOutput | None = None

    # Free-form notes the operator can attach (e.g., environment anomalies).
    notes: str = ""

    def __init__(self, **data: object) -> None:
        super().__init__(**data)
        self._invariants()

    def _invariants(self) -> None:
        # Failure mode must accompany a failure outcome.
        if self.outcome == Outcome.FAILURE and self.failure_mode is None:
            raise ValueError("FAILURE outcome requires a failure_mode")
        if self.outcome == Outcome.SAFEGUARD_REFUSAL and self.failure_mode not in (
            None,
            FailureMode.REFUSAL,
        ):
            raise ValueError("SAFEGUARD_REFUSAL implies failure_mode=REFUSAL or None")
        # Successful outcomes do not carry failure modes.
        if self.outcome in (Outcome.KNOWN_REDISCOVERY, Outcome.NEW_DISCOVERY) and (
            self.failure_mode is not None
        ):
            raise ValueError("Success outcomes must not have a failure_mode")


__all__ = [
    "BackendCategory",
    "BackendInfo",
    "CostRecord",
    "FailureMode",
    "Outcome",
    "PromptingStrategy",
    "RunRecord",
    "TokenUsage",
    "ValidatorOutput",
]
