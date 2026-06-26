"""
Model pricing — single source of truth loader.

Prices live in ``backends/pricing.yaml`` (checked in, versioned). This module
loads that file once and is the *only* import target for rates: the provider
backends compute cost through it, the registry derives its dry-run estimate
through it, and the synthetic generator builds costs through it. Nothing else
hard-codes a price.

Because every run record embeds a :class:`~harness.record.PricingSnapshot` of
the rates used, a recorded cost is auditable and recomputable after the fact —
the whole point of pinning prices in one versioned place rather than fetching
them live (ADR 0007).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

from harness.record import PricingSnapshot

_PRICING_FILE = Path(__file__).with_name("pricing.yaml")


@dataclass(frozen=True)
class ModelPrice:
    """USD per million tokens for one model, with provenance metadata."""

    prompt_per_mtok: float
    completion_per_mtok: float
    as_of: str  # ISO date
    source: str  # URL the rate was taken from


# Backwards-compatible alias: the per-backend modules historically exported a
# ``Pricing`` dataclass with ``prompt_per_mtok`` / ``completion_per_mtok``.
Pricing = ModelPrice


def _load() -> tuple[str, dict[str, ModelPrice]]:
    """Parse ``pricing.yaml`` into (pricing_version, {model: ModelPrice})."""
    data = yaml.safe_load(_PRICING_FILE.read_text(encoding="utf-8")) or {}
    version = str(data.get("pricing_version", "unknown"))
    prices: dict[str, ModelPrice] = {}
    for model, entry in (data.get("models") or {}).items():
        prices[str(model)] = ModelPrice(
            prompt_per_mtok=float(entry["prompt_per_mtok"]),
            completion_per_mtok=float(entry["completion_per_mtok"]),
            as_of=str(entry["as_of"]),
            source=str(entry["source"]),
        )
    return version, prices


PRICING_VERSION, PRICES = _load()


def price_for(model: str) -> ModelPrice | None:
    """The :class:`ModelPrice` for ``model``, or ``None`` if unpriced (local)."""
    return PRICES.get(model)


def tuple_for(model: str) -> tuple[float, float] | None:
    """``(prompt_per_mtok, completion_per_mtok)`` for ``model``, or ``None``.

    The shape the registry's dry-run estimator (``harness.matrix``) consumes.
    """
    price = PRICES.get(model)
    if price is None:
        return None
    return (price.prompt_per_mtok, price.completion_per_mtok)


def snapshot_for(model: str) -> PricingSnapshot | None:
    """The :class:`~harness.record.PricingSnapshot` to embed for ``model``.

    ``None`` for unpriced/local models — the backend records ``usd=0.0`` and a
    ``CostRecord`` with ``pricing=None``.
    """
    price = PRICES.get(model)
    if price is None:
        return None
    return PricingSnapshot(
        prompt_per_mtok=price.prompt_per_mtok,
        completion_per_mtok=price.completion_per_mtok,
        pricing_version=PRICING_VERSION,
        as_of=price.as_of,
    )


def subset(models: list[str]) -> dict[str, ModelPrice]:
    """The price entries for ``models`` that exist (for per-backend ``PRICING``)."""
    return {m: PRICES[m] for m in models if m in PRICES}


def oldest_as_of() -> str:
    """The oldest ``as_of`` date across priced models (ISO string).

    The conservative freshness signal for the pre-run gate: a run for record
    should not use any rate that is too old.
    """
    return min((p.as_of for p in PRICES.values()), default=PRICING_VERSION)


def age_days(today: date) -> int:
    """Days between ``today`` and :func:`oldest_as_of`.

    ``today`` is passed in (not read from the clock) so callers control the
    reference date and the function stays deterministic/testable.
    """
    return (today - date.fromisoformat(oldest_as_of())).days


__all__ = [
    "PRICES",
    "PRICING_VERSION",
    "ModelPrice",
    "Pricing",
    "age_days",
    "oldest_as_of",
    "price_for",
    "snapshot_for",
    "subset",
    "tuple_for",
]
