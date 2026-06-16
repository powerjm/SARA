"""Tests for the deterministic synthetic run-record generator."""

from __future__ import annotations

from pathlib import Path

import pytest

from analysis.synthetic import (
    DEFAULT_BACKENDS,
    DEFAULT_STRATEGIES,
    generate,
    write_jsonl,
)
from harness.record import BackendCategory, FailureMode, Outcome, RunRecord


def _dump(records: list[RunRecord]) -> list[str]:
    return [r.model_dump_json() for r in records]


def test_generate_is_byte_identical_across_calls() -> None:
    assert _dump(generate(seed=0)) == _dump(generate(seed=0))


def test_generate_matrix_size() -> None:
    expected = 8 * len(DEFAULT_BACKENDS) * len(DEFAULT_STRATEGIES) * 3
    assert len(generate(seed=0)) == expected


def test_generate_covers_every_outcome() -> None:
    assert {r.outcome for r in generate(seed=0)} == set(Outcome)


def test_generate_covers_every_failure_mode() -> None:
    modes = {r.failure_mode for r in generate(seed=0) if r.failure_mode is not None}
    assert modes == set(FailureMode)


def test_different_seed_produces_different_data() -> None:
    assert _dump(generate(seed=0)) != _dump(generate(seed=1))


def test_records_revalidate() -> None:
    for r in generate(seed=0):
        # Construction enforced the invariants; confirm a clean JSON round trip.
        RunRecord.model_validate_json(r.model_dump_json())


def test_premium_costs_usd_local_costs_hardware() -> None:
    by_category = {b.name: b.category for b in DEFAULT_BACKENDS}
    for r in generate(seed=0):
        category = by_category[r.backend.name]
        if category == BackendCategory.PREMIUM:
            assert r.cost.usd > 0.0
            assert r.cost.hardware_usd_estimate == 0.0
        else:
            assert r.cost.usd == 0.0
            assert r.cost.hardware_usd_estimate > 0.0


def test_successes_have_validator_refusals_do_not() -> None:
    for r in generate(seed=0):
        if r.outcome in (Outcome.KNOWN_REDISCOVERY, Outcome.NEW_DISCOVERY):
            assert r.validator is not None and r.validator.succeeded
            assert r.payload_path is not None
            assert r.validator.matched_documented_chain == (r.outcome == Outcome.KNOWN_REDISCOVERY)
        if r.outcome == Outcome.SAFEGUARD_REFUSAL:
            assert r.validator is None
            assert r.payload_path is None


def test_small_matrix_still_covers_all_enums() -> None:
    runs = generate(seed=0, n_binaries=2, replicates=1)
    assert {r.outcome for r in runs} == set(Outcome)
    assert {r.failure_mode for r in runs if r.failure_mode} == set(FailureMode)


def test_matrix_too_small_to_cover_raises() -> None:
    with pytest.raises(ValueError, match="cover"):
        generate(
            seed=0,
            n_binaries=1,
            backends=[DEFAULT_BACKENDS[0]],
            strategies=[DEFAULT_STRATEGIES[0]],
            replicates=1,
        )


def test_invalid_config_raises() -> None:
    with pytest.raises(ValueError):
        generate(seed=0, n_binaries=0)
    with pytest.raises(ValueError):
        generate(seed=0, replicates=0)


def test_write_jsonl_roundtrips(tmp_path: Path) -> None:
    runs = generate(seed=0, n_binaries=2, replicates=1)
    out = write_jsonl(runs, tmp_path / "synthetic.jsonl")
    lines = out.read_text().splitlines()
    assert len(lines) == len(runs)
    restored = [RunRecord.model_validate_json(line) for line in lines]
    assert _dump(restored) == _dump(runs)
