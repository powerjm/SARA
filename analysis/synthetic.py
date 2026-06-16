"""
Deterministic synthetic run-record generator.

The analysis pipeline (aggregation, statistics, notebooks) needs a realistic
dataset to run against before any real agent runs exist. `generate()` produces
a list of `RunRecord`s that:

  * is **byte-identical across calls** for a fixed `seed` and configuration —
    no `uuid4()`, no `datetime.now()`; every random draw comes from a single
    seeded `random.Random`, and UUIDs/timestamps are derived from it. This lets
    notebooks pin a seed and get reproducible figures (Step 6).
  * **exercises every `Outcome` and every `FailureMode`**, so analysis code that
    branches on outcome class is covered by the synthetic data alone.

The dataset is shaped like the real experiment matrix: the cartesian product of
(binary, backend, strategy) run `replicates` times, with per-backend success
propensities and per-binary difficulty so the nonparametric tests in
`analysis.stats` see plausible structure. A small, evenly-spaced subset of cells
is overridden with a fixed coverage set so that all enum members appear
regardless of the random draw.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

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

# Fixed epoch so timestamps are deterministic (never datetime.now()).
_EPOCH = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)

# Default backends: one per category, mirroring the experimental design.
DEFAULT_BACKENDS: tuple[BackendInfo, ...] = (
    BackendInfo(
        category=BackendCategory.PREMIUM,
        name="claude-sonnet-4-6",
        version="claude-sonnet-4-6",
        temperature=0.2,
        seed=0,
    ),
    BackendInfo(
        category=BackendCategory.OPEN_WEIGHT,
        name="qwen2.5-coder-32b",
        version="qwen2.5-coder-32b-instruct",
        temperature=0.2,
        seed=0,
    ),
    BackendInfo(
        category=BackendCategory.UNRESTRICTED,
        name="dolphin-mixtral-8x7b",
        version="dolphin-2.7-mixtral-8x7b",
        temperature=0.2,
        seed=0,
    ),
)

DEFAULT_STRATEGIES: tuple[PromptingStrategy, ...] = tuple(PromptingStrategy)

# Per-category base success rate, before per-binary difficulty is applied.
_BASE_SUCCESS_RATE: dict[BackendCategory, float] = {
    BackendCategory.PREMIUM: 0.72,
    BackendCategory.OPEN_WEIGHT: 0.45,
    BackendCategory.UNRESTRICTED: 0.30,
}

# Failure modes that mean "no payload reached the validator".
_NO_PAYLOAD_MODES: frozenset[FailureMode] = frozenset(
    {FailureMode.BUDGET_EXHAUSTED, FailureMode.TOOL_USE_MALFORMED, FailureMode.REFUSAL}
)

# Mechanical failure modes that *do* produce a (bad) payload the validator runs.
_MECHANICAL_FAILURE_MODES: tuple[FailureMode, ...] = (
    FailureMode.HALLUCINATED_GADGET,
    FailureMode.WRONG_REGISTER_REASONING,
    FailureMode.BAD_CHAIN_ORDERING,
    FailureMode.CONSTRAINT_VIOLATION,
    FailureMode.OTHER,
)

# Per-million-token USD prices for premium (cloud-API) backends. Local backends
# record usd=0.0 and rely on hardware_usd_estimate instead.
_PREMIUM_PROMPT_USD_PER_MTOK = 3.0
_PREMIUM_COMPLETION_USD_PER_MTOK = 15.0
# Hardware amortisation for local runs, in USD per wall-clock hour.
_LOCAL_USD_PER_HOUR = 1.5


def _coverage_combos() -> list[tuple[Outcome, FailureMode | None]]:
    """The (outcome, failure_mode) combos that together touch every enum member.

    REFUSAL is exercised via SAFEGUARD_REFUSAL; the remaining failure modes via
    FAILURE. Every Outcome appears at least once.
    """
    combos: list[tuple[Outcome, FailureMode | None]] = [
        (Outcome.KNOWN_REDISCOVERY, None),
        (Outcome.NEW_DISCOVERY, None),
        (Outcome.SAFEGUARD_REFUSAL, None),
        (Outcome.SAFEGUARD_REFUSAL, FailureMode.REFUSAL),
    ]
    combos += [(Outcome.FAILURE, fm) for fm in FailureMode if fm != FailureMode.REFUSAL]
    return combos


def _sample_outcome(
    rng: random.Random,
    category: BackendCategory,
    difficulty: int,
) -> tuple[Outcome, FailureMode | None]:
    """Draw a plausible (outcome, failure_mode) for one run."""
    # Difficulty 0..3 shaves the base rate down.
    success_rate = max(0.05, _BASE_SUCCESS_RATE[category] - 0.12 * difficulty)
    roll = rng.random()
    if roll < success_rate:
        # Mostly rediscover the documented chain; occasionally find a new one.
        if rng.random() < 0.8:
            return Outcome.KNOWN_REDISCOVERY, None
        return Outcome.NEW_DISCOVERY, None
    # Non-success: a minority are policy refusals; the rest mechanical failures.
    if rng.random() < 0.12:
        return Outcome.SAFEGUARD_REFUSAL, FailureMode.REFUSAL
    return Outcome.FAILURE, rng.choice(
        (*_MECHANICAL_FAILURE_MODES, FailureMode.TIMEOUT, FailureMode.BUDGET_EXHAUSTED)
    )


def _make_validator(
    rng: random.Random,
    outcome: Outcome,
    failure_mode: FailureMode | None,
) -> ValidatorOutput | None:
    """Build a plausible validator result, or None when no payload was run."""
    if outcome in (Outcome.KNOWN_REDISCOVERY, Outcome.NEW_DISCOVERY):
        return ValidatorOutput(
            succeeded=True,
            return_code=0,
            stdout_marker_found=True,
            matched_documented_chain=(outcome == Outcome.KNOWN_REDISCOVERY),
            stdout_excerpt="Hello World\n",
            elapsed_seconds=round(rng.uniform(0.1, 0.6), 3),
        )
    if outcome == Outcome.FAILURE:
        if failure_mode in _NO_PAYLOAD_MODES:
            return None
        if failure_mode == FailureMode.TIMEOUT:
            return ValidatorOutput(
                succeeded=False,
                return_code=124,
                stdout_marker_found=False,
                matched_documented_chain=False,
                stderr_excerpt="timeout",
                elapsed_seconds=round(rng.uniform(8.0, 10.0), 3),
            )
        # A mechanical failure that produced a payload the validator rejected.
        return ValidatorOutput(
            succeeded=False,
            return_code=-11,
            stdout_marker_found=False,
            matched_documented_chain=False,
            stderr_excerpt="Segmentation fault",
            elapsed_seconds=round(rng.uniform(0.05, 0.3), 3),
        )
    # SAFEGUARD_REFUSAL: nothing ran.
    return None


def _make_cost(
    category: BackendCategory,
    tokens: TokenUsage,
    wall_clock_seconds: float,
) -> CostRecord:
    """USD for premium backends; hardware estimate for local backends."""
    if category == BackendCategory.PREMIUM:
        usd = (
            tokens.prompt * _PREMIUM_PROMPT_USD_PER_MTOK
            + tokens.completion * _PREMIUM_COMPLETION_USD_PER_MTOK
        ) / 1_000_000
        return CostRecord(usd=round(usd, 6))
    return CostRecord(
        usd=0.0,
        hardware_usd_estimate=round(wall_clock_seconds / 3600.0 * _LOCAL_USD_PER_HOUR, 6),
    )


def _make_record(
    rng: random.Random,
    *,
    binary_id: str,
    backend: BackendInfo,
    strategy: PromptingStrategy,
    outcome: Outcome,
    failure_mode: FailureMode | None,
    started_at: datetime,
) -> RunRecord:
    """Assemble one RunRecord with telemetry correlated to its outcome."""
    # Iterations / tokens / wall-clock vary by how the run ended.
    if outcome == Outcome.SAFEGUARD_REFUSAL:
        iterations = rng.randint(1, 2)
        wall_clock = round(rng.uniform(2.0, 20.0), 1)
    elif failure_mode == FailureMode.BUDGET_EXHAUSTED:
        iterations = rng.randint(20, 30)
        wall_clock = round(rng.uniform(400.0, 600.0), 1)
    else:
        iterations = rng.randint(4, 18)
        wall_clock = round(rng.uniform(30.0, 360.0), 1)

    prompt_tokens = iterations * rng.randint(700, 1500)
    completion_tokens = iterations * rng.randint(150, 400)
    tokens = TokenUsage(prompt=prompt_tokens, completion=completion_tokens)

    validator = _make_validator(rng, outcome, failure_mode)
    run_id = UUID(bytes=rng.randbytes(16))
    payload_path = Path(f"runs/{run_id}/payload.bin") if validator is not None else None

    return RunRecord(
        run_id=run_id,
        binary_id=binary_id,
        backend=backend,
        prompting_strategy=strategy,
        started_at=started_at,
        ended_at=started_at + timedelta(seconds=wall_clock),
        wall_clock_seconds=wall_clock,
        outcome=outcome,
        failure_mode=failure_mode,
        iterations=iterations,
        tokens=tokens,
        cost=_make_cost(backend.category, tokens, wall_clock),
        trace_path=Path(f"runs/{run_id}/trace.jsonl"),
        payload_path=payload_path,
        validator=validator,
        notes="synthetic",
    )


def generate(
    *,
    seed: int = 0,
    n_binaries: int = 8,
    backends: Sequence[BackendInfo] | None = None,
    strategies: Sequence[PromptingStrategy] | None = None,
    replicates: int = 3,
    base_time: datetime | None = None,
) -> list[RunRecord]:
    """Generate a deterministic synthetic dataset.

    The result is byte-identical across calls for the same arguments. The full
    (binary x backend x strategy x replicate) matrix is generated, then an
    evenly-spaced subset of cells is overridden so every `Outcome` and every
    `FailureMode` is present.

    Raises ValueError if the matrix is too small to hold the coverage set.
    """
    if n_binaries < 1 or replicates < 1:
        raise ValueError("n_binaries and replicates must be >= 1")

    # Non-cryptographic by design: reproducibility is the whole point, so a
    # seeded Mersenne-Twister is exactly what we want here.
    rng = random.Random(seed)  # noqa: S311
    backends = tuple(backends) if backends is not None else DEFAULT_BACKENDS
    strategies = tuple(strategies) if strategies is not None else DEFAULT_STRATEGIES
    if not backends or not strategies:
        raise ValueError("backends and strategies must be non-empty")

    base = base_time if base_time is not None else _EPOCH

    binaries = [f"syn-bin-{i:02d}" for i in range(n_binaries)]
    difficulty = {b: i % 4 for i, b in enumerate(binaries)}

    # Flat, fixed-order list of cells (one entry per run).
    cells: list[tuple[str, BackendInfo, PromptingStrategy]] = [
        (binary, backend, strategy)
        for binary in binaries
        for backend in backends
        for strategy in strategies
        for _ in range(replicates)
    ]

    combos = _coverage_combos()
    if len(cells) < len(combos):
        raise ValueError(
            f"matrix has {len(cells)} runs but needs >= {len(combos)} to cover "
            "every outcome/failure-mode; increase n_binaries/replicates"
        )

    # Pre-assign outcomes, then override an evenly-spaced subset with the
    # coverage combos so all enum members appear deterministically.
    assignments: list[tuple[Outcome, FailureMode | None]] = []
    for _binary, backend, _strategy in cells:
        assignments.append(_sample_outcome(rng, backend.category, difficulty[_binary]))

    last = len(cells) - 1
    span = len(combos) - 1
    for k, combo in enumerate(combos):
        idx = round(k * last / span) if span else 0
        assignments[idx] = combo

    records: list[RunRecord] = []
    clock = base
    for (binary, backend, strategy), (outcome, failure_mode) in zip(
        cells, assignments, strict=True
    ):
        records.append(
            _make_record(
                rng,
                binary_id=binary,
                backend=backend,
                strategy=strategy,
                outcome=outcome,
                failure_mode=failure_mode,
                started_at=clock,
            )
        )
        # Stagger start times deterministically so records are ordered in time.
        clock += timedelta(seconds=records[-1].wall_clock_seconds)

    return records


def write_jsonl(records: Sequence[RunRecord], path: Path) -> Path:
    """Write records as newline-delimited JSON (one RunRecord per line)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for r in records:
            f.write(r.model_dump_json())
            f.write("\n")
    return path


__all__ = [
    "DEFAULT_BACKENDS",
    "DEFAULT_STRATEGIES",
    "generate",
    "write_jsonl",
]
