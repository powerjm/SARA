"""Tests for the RunRecord schema.

The schema is the central data structure of the experiment. If these tests
break, run records produced before the break are no longer comparable to
ones produced after. Treat any change here as a versioning event.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from harness.record import (
    BackendCategory,
    BackendInfo,
    CostRecord,
    FailureMode,
    Outcome,
    PromptingStrategy,
    RunRecord,
    TokenUsage,
    ValidatorOutput,
)


def _base_kwargs() -> dict[str, object]:
    return {
        "run_id": uuid4(),
        "binary_id": "sample-overflow",
        "backend": BackendInfo(
            category=BackendCategory.PREMIUM,
            name="claude-sonnet-4-6",
            version="claude-sonnet-4-6",
            temperature=0.2,
        ),
        "prompting_strategy": PromptingStrategy.ZERO_SHOT,
        "started_at": datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC),
        "ended_at": datetime(2026, 5, 1, 12, 6, 52, tzinfo=UTC),
        "wall_clock_seconds": 412.3,
        "iterations": 17,
        "tokens": TokenUsage(prompt=12450, completion=3120),
        "cost": CostRecord(usd=0.42),
        "trace_path": Path("runs/x/trace.jsonl"),
    }


def test_failure_outcome_requires_failure_mode() -> None:
    kwargs = _base_kwargs()
    kwargs["outcome"] = Outcome.FAILURE
    with pytest.raises(ValueError, match="failure_mode"):
        RunRecord(**kwargs)


def test_success_outcome_forbids_failure_mode() -> None:
    kwargs = _base_kwargs()
    kwargs["outcome"] = Outcome.KNOWN_REDISCOVERY
    kwargs["failure_mode"] = FailureMode.OTHER
    with pytest.raises(ValueError, match="Success outcomes"):
        RunRecord(**kwargs)


def test_safeguard_refusal_implies_refusal_mode() -> None:
    kwargs = _base_kwargs()
    kwargs["outcome"] = Outcome.SAFEGUARD_REFUSAL
    kwargs["failure_mode"] = FailureMode.TIMEOUT
    with pytest.raises(ValueError, match="SAFEGUARD_REFUSAL"):
        RunRecord(**kwargs)


def test_safeguard_refusal_allows_no_failure_mode() -> None:
    kwargs = _base_kwargs()
    kwargs["outcome"] = Outcome.SAFEGUARD_REFUSAL
    # No failure_mode key -> defaults to None.
    record = RunRecord(**kwargs)
    assert record.outcome == Outcome.SAFEGUARD_REFUSAL
    assert record.failure_mode is None


def test_safeguard_refusal_with_refusal_mode_is_valid() -> None:
    kwargs = _base_kwargs()
    kwargs["outcome"] = Outcome.SAFEGUARD_REFUSAL
    kwargs["failure_mode"] = FailureMode.REFUSAL
    record = RunRecord(**kwargs)
    assert record.failure_mode == FailureMode.REFUSAL


def test_valid_success_record_roundtrips() -> None:
    kwargs = _base_kwargs()
    kwargs["outcome"] = Outcome.KNOWN_REDISCOVERY
    record = RunRecord(**kwargs)

    payload = record.model_dump_json()
    restored = RunRecord.model_validate_json(payload)
    assert restored.outcome == Outcome.KNOWN_REDISCOVERY
    assert restored.tokens.total == 12450 + 3120
    assert restored.cost.usd == 0.42


def test_valid_failure_record_roundtrips() -> None:
    kwargs = _base_kwargs()
    kwargs["outcome"] = Outcome.FAILURE
    kwargs["failure_mode"] = FailureMode.HALLUCINATED_GADGET
    record = RunRecord(**kwargs)

    payload = record.model_dump_json()
    restored = RunRecord.model_validate_json(payload)
    assert restored.outcome == Outcome.FAILURE
    assert restored.failure_mode == FailureMode.HALLUCINATED_GADGET


def test_token_usage_total_is_computed() -> None:
    t = TokenUsage(prompt=100, completion=50)
    assert t.total == 150


def test_validator_output_attaches_to_record() -> None:
    kwargs = _base_kwargs()
    kwargs["outcome"] = Outcome.KNOWN_REDISCOVERY
    kwargs["validator"] = ValidatorOutput(
        succeeded=True,
        return_code=0,
        stdout_marker_found=True,
        matched_documented_chain=True,
        stdout_excerpt="Hello World\n",
        elapsed_seconds=0.4,
    )
    record = RunRecord(**kwargs)
    assert record.validator is not None
    assert record.validator.matched_documented_chain
