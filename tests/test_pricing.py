"""Tests for the centralized pricing source (backends/pricing.yaml + loader).

These guard the single-source-of-truth invariant: the registry's dry-run
estimate and each backend's recorded cost must derive from the same file, so a
rate can never drift between them. They also pin the corrected Opus price (the
bug that motivated this change) and exercise the freshness helpers.
"""

from __future__ import annotations

from datetime import date

import pytest
from fakes.backend import FakeBackend

from backends import pricing, registry
from harness.record import PricingSnapshot


def test_pricing_version_present() -> None:
    assert pricing.PRICING_VERSION
    assert pricing.PRICES  # at least one model priced


def test_price_for_known_and_unknown() -> None:
    sonnet = pricing.price_for("claude-sonnet-4-6")
    assert sonnet is not None
    assert sonnet.prompt_per_mtok == 3.0
    assert sonnet.completion_per_mtok == 15.0
    assert pricing.price_for("llama-3.3-70b-instruct") is None  # local, unpriced


def test_opus_price_is_corrected() -> None:
    # Regression guard: Opus 4.7 was wrongly pinned at $15/$75 (3x too high).
    assert pricing.tuple_for("claude-opus-4-7") == (5.0, 25.0)


def test_tuple_for_matches_price_for() -> None:
    for model, price in pricing.PRICES.items():
        assert pricing.tuple_for(model) == (price.prompt_per_mtok, price.completion_per_mtok)


def test_snapshot_for_known_and_unknown() -> None:
    snap = pricing.snapshot_for("gpt-5")
    assert isinstance(snap, PricingSnapshot)
    assert snap.prompt_per_mtok == 1.25
    assert snap.completion_per_mtok == 10.0
    assert snap.pricing_version == pricing.PRICING_VERSION
    assert pricing.snapshot_for("nonexistent-model") is None


@pytest.mark.parametrize(
    ("cell", "model"),
    [
        ("claude-sonnet", "claude-sonnet-4-6"),
        ("claude-opus", "claude-opus-4-7"),
        ("gpt-5", "gpt-5"),
        ("gemini-2.5-pro", "gemini-2.5-pro"),
    ],
)
def test_registry_pricing_derives_from_single_source(cell: str, model: str) -> None:
    # The registry must not carry its own copy of the rates: what it reports for
    # a cell must equal what backends.pricing says for that cell's model.
    assert registry.pricing(cell) == pricing.tuple_for(model)


def test_registry_pricing_none_for_local_backends() -> None:
    for local in ("llama-3.3-70b", "qwen2.5-coder-32b", "dolphin-mixtral-8x7b"):
        assert registry.pricing(local) is None


def test_backend_pricing_snapshot_priced_vs_unpriced() -> None:
    priced = FakeBackend(name="claude-sonnet-4-6").pricing_snapshot()
    assert priced is not None
    assert priced.prompt_per_mtok == 3.0
    # A model absent from pricing.yaml yields no snapshot (local/unknown).
    assert FakeBackend(name="fake").pricing_snapshot() is None


def test_freshness_helpers() -> None:
    oldest = pricing.oldest_as_of()
    parsed = date.fromisoformat(oldest)  # must be a valid ISO date
    # age relative to the file's own oldest date is zero; a year later is ~365.
    assert pricing.age_days(parsed) == 0
    assert pricing.age_days(date(parsed.year + 1, parsed.month, parsed.day)) >= 365
