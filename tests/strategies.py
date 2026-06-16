"""
Hypothesis strategies for the RunRecord schema.

These build valid sub-records and full `RunRecord`s, plus the *invalid*
(outcome, failure_mode) pairings the schema is supposed to reject. The property
tests in `tests/test_record_schema_properties.py` use them to assert the
round-trip and invariant guarantees over a wide input space.

Text and floats are deliberately restricted to JSON-round-trippable values
(printable ASCII, finite floats) so a generated valid record always survives
`model_dump_json` -> `model_validate_json` unchanged.
"""

from __future__ import annotations

from typing import Any

import hypothesis.strategies as st

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

# --------------------------------------------------------------------------- #
# Leaf strategies (JSON-round-trip-safe)                                      #
# --------------------------------------------------------------------------- #

# Printable ASCII only: excludes control chars, NULs (illegal in Path), and
# surrogates (illegal in UTF-8/JSON).
safe_text = st.text(
    alphabet=st.characters(min_codepoint=32, max_codepoint=126),
    max_size=40,
)
safe_segment = st.text(
    alphabet=st.characters(min_codepoint=97, max_codepoint=122),
    min_size=1,
    max_size=12,
)
nonneg_ints = st.integers(min_value=0, max_value=10_000_000)
nonneg_floats = st.floats(min_value=0.0, max_value=1e6, allow_nan=False, allow_infinity=False)
return_codes = st.integers(min_value=-255, max_value=255)


def relative_paths(leaf: str) -> st.SearchStrategy[Any]:
    """A `runs/<seg>/<leaf>` Path."""
    from pathlib import Path

    return st.builds(lambda seg: Path("runs") / seg / leaf, safe_segment)


# --------------------------------------------------------------------------- #
# Sub-record strategies                                                       #
# --------------------------------------------------------------------------- #


def backend_infos() -> st.SearchStrategy[BackendInfo]:
    return st.builds(
        BackendInfo,
        category=st.sampled_from(list(BackendCategory)),
        name=safe_text,
        version=safe_text,
        temperature=st.floats(min_value=0.0, max_value=2.0, allow_nan=False, allow_infinity=False),
        seed=st.none() | st.integers(min_value=0, max_value=2**31 - 1),
    )


def token_usages() -> st.SearchStrategy[TokenUsage]:
    return st.builds(TokenUsage, prompt=nonneg_ints, completion=nonneg_ints)


def cost_records() -> st.SearchStrategy[CostRecord]:
    return st.builds(CostRecord, usd=nonneg_floats, hardware_usd_estimate=nonneg_floats)


def validator_outputs() -> st.SearchStrategy[ValidatorOutput]:
    return st.builds(
        ValidatorOutput,
        succeeded=st.booleans(),
        return_code=return_codes,
        stdout_marker_found=st.booleans(),
        matched_documented_chain=st.booleans(),
        stdout_excerpt=safe_text,
        stderr_excerpt=safe_text,
        elapsed_seconds=nonneg_floats,
    )


# --------------------------------------------------------------------------- #
# Outcome / failure-mode pairings                                             #
# --------------------------------------------------------------------------- #


def valid_outcome_failure() -> st.SearchStrategy[tuple[Outcome, FailureMode | None]]:
    """Every (outcome, failure_mode) pairing the schema accepts."""
    return st.one_of(
        st.tuples(
            st.sampled_from([Outcome.KNOWN_REDISCOVERY, Outcome.NEW_DISCOVERY]),
            st.none(),
        ),
        st.tuples(st.just(Outcome.FAILURE), st.sampled_from(list(FailureMode))),
        st.tuples(
            st.just(Outcome.SAFEGUARD_REFUSAL),
            st.none() | st.just(FailureMode.REFUSAL),
        ),
    )


def failure_without_mode() -> st.SearchStrategy[tuple[Outcome, None]]:
    """Invalid: FAILURE must carry a failure_mode."""
    return st.tuples(st.just(Outcome.FAILURE), st.none())


def success_with_mode() -> st.SearchStrategy[tuple[Outcome, FailureMode]]:
    """Invalid: success outcomes must not carry a failure_mode."""
    return st.tuples(
        st.sampled_from([Outcome.KNOWN_REDISCOVERY, Outcome.NEW_DISCOVERY]),
        st.sampled_from(list(FailureMode)),
    )


def refusal_with_bad_mode() -> st.SearchStrategy[tuple[Outcome, FailureMode]]:
    """Invalid: SAFEGUARD_REFUSAL allows only None or REFUSAL."""
    return st.tuples(
        st.just(Outcome.SAFEGUARD_REFUSAL),
        st.sampled_from([fm for fm in FailureMode if fm != FailureMode.REFUSAL]),
    )


# --------------------------------------------------------------------------- #
# RunRecord strategies                                                        #
# --------------------------------------------------------------------------- #


@st.composite
def run_record_kwargs(
    draw: st.DrawFn,
    outcome_failure: st.SearchStrategy[tuple[Outcome, FailureMode | None]] | None = None,
) -> dict[str, Any]:
    """Construction kwargs for a RunRecord.

    `outcome_failure` defaults to the valid pairings; pass an invalid-pairing
    strategy to build kwargs the schema should reject.
    """
    outcome, failure_mode = draw(
        outcome_failure if outcome_failure is not None else valid_outcome_failure()
    )
    return {
        "run_id": draw(st.uuids()),
        "binary_id": draw(safe_segment),
        "backend": draw(backend_infos()),
        "prompting_strategy": draw(st.sampled_from(list(PromptingStrategy))),
        "started_at": draw(st.datetimes()),
        "ended_at": draw(st.datetimes()),
        "wall_clock_seconds": draw(nonneg_floats),
        "outcome": outcome,
        "failure_mode": failure_mode,
        "iterations": draw(nonneg_ints),
        "tokens": draw(token_usages()),
        "cost": draw(cost_records()),
        "trace_path": draw(relative_paths("trace.jsonl")),
        "payload_path": draw(st.none() | relative_paths("payload.bin")),
        "validator": draw(st.none() | validator_outputs()),
        "notes": draw(safe_text),
    }


@st.composite
def run_records(draw: st.DrawFn) -> RunRecord:
    """A valid RunRecord."""
    return RunRecord(**draw(run_record_kwargs()))


__all__ = [
    "backend_infos",
    "cost_records",
    "failure_without_mode",
    "refusal_with_bad_mode",
    "run_record_kwargs",
    "run_records",
    "success_with_mode",
    "token_usages",
    "valid_outcome_failure",
    "validator_outputs",
]
