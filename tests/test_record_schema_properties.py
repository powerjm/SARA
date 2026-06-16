"""
Property-based tests for the RunRecord schema.

Complements the example-based tests in `tests/test_record_schema.py`: instead of
a handful of hand-written cases, these drive the schema with Hypothesis over a
wide space of inputs to confirm the round-trip and the three construction-time
invariants hold universally.

Kept fast (<5 s): modest `max_examples`, cheap strategies, no per-example
deadline. See `tests/strategies.py` for the generators.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from strategies import (
    failure_without_mode,
    refusal_with_bad_mode,
    run_record_kwargs,
    run_records,
    success_with_mode,
)

from harness.record import FailureMode, Outcome, RunRecord

# One settings profile shared across the module.
SETTINGS = settings(max_examples=150, deadline=None)


@SETTINGS
@given(run_records())
def test_valid_record_roundtrips(record: RunRecord) -> None:
    """Any valid record survives JSON dump -> load byte-for-byte."""
    dumped = record.model_dump_json()
    restored = RunRecord.model_validate_json(dumped)
    assert restored.model_dump_json() == dumped


@SETTINGS
@given(run_records())
def test_valid_record_satisfies_invariants(record: RunRecord) -> None:
    """The three outcome/failure-mode invariants hold for every valid record."""
    if record.outcome == Outcome.FAILURE:
        assert record.failure_mode is not None
    elif record.outcome in (Outcome.KNOWN_REDISCOVERY, Outcome.NEW_DISCOVERY):
        assert record.failure_mode is None
    elif record.outcome == Outcome.SAFEGUARD_REFUSAL:
        assert record.failure_mode in (None, FailureMode.REFUSAL)


@SETTINGS
@given(run_record_kwargs(failure_without_mode()))
def test_failure_requires_failure_mode(kwargs: dict[str, object]) -> None:
    """Invariant 1: FAILURE with no failure_mode is rejected."""
    with pytest.raises(ValueError, match="failure_mode"):
        RunRecord(**kwargs)


@SETTINGS
@given(run_record_kwargs(success_with_mode()))
def test_success_forbids_failure_mode(kwargs: dict[str, object]) -> None:
    """Invariant 3: a success outcome with a failure_mode is rejected."""
    with pytest.raises(ValueError, match="Success outcomes"):
        RunRecord(**kwargs)


@SETTINGS
@given(run_record_kwargs(refusal_with_bad_mode()))
def test_refusal_restricts_failure_mode(kwargs: dict[str, object]) -> None:
    """Invariant 2: SAFEGUARD_REFUSAL accepts only None or REFUSAL."""
    with pytest.raises(ValueError, match="SAFEGUARD_REFUSAL"):
        RunRecord(**kwargs)
