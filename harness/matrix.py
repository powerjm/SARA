"""
Experiment matrix runner (``sara batch``).

A batch config (see ``experiments.example.yaml``) declares the matrix: the
cartesian product of ``binaries × backends × strategies``, each cell run
``replicates`` times. :func:`run_batch` executes the plan one replicate at a
time, persisting each run atomically, so it is **resumable**: a re-run scans the
output directory and only runs the replicates still missing for each cell.

Cost is capped **per backend** (the Step-5 decision): each backend gets its own
USD budget, and once a backend's cumulative spend — counting both this batch and
any spend already on disk — reaches its cap, its remaining cells are halted while
the cheaper backends keep going. ``--dry-run`` prints the plan and a rough cost
estimate without executing anything.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from backends import registry
from harness import persistence
from harness.corpus import resolve_binary
from harness.record import RunRecord
from harness.runner import RunSettings, run_one

# A coarse per-run token assumption for the dry-run estimate, split prompt-heavy.
# Deliberately conservative; the real cost is recorded per run from API usage.
_ASSUMED_PROMPT_TOKENS = 16_000
_ASSUMED_COMPLETION_TOKENS = 4_000


# --------------------------------------------------------------------------- #
# Config                                                                       #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Cell:
    """One matrix cell: a (binary, backend, strategy) triple."""

    binary_id: str
    backend: str
    strategy: str

    def key(self) -> tuple[str, str, str]:
        return (self.binary_id, self.backend, self.strategy)


@dataclass(frozen=True)
class BatchConfig:
    """Parsed ``experiments.yaml``."""

    replicates: int
    binaries: list[str]
    backends: list[str]
    strategies: list[str]
    output_dir: Path
    token_cap: int
    wall_clock_cap_seconds: int
    # Per-backend USD cap. Absent/0 means "no cap for this backend".
    usd_per_backend: dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_yaml(cls, path: Path) -> BatchConfig:
        with path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        limits = data.get("limits") or {}
        usd = limits.get("usd_per_backend") or {}
        return cls(
            replicates=int(data.get("replicates", 5)),
            binaries=list(data.get("binaries") or []),
            backends=list(data.get("backends") or []),
            strategies=list(data.get("strategies") or []),
            output_dir=Path(data.get("output_dir", "./runs")),
            token_cap=int(limits.get("tokens", 200_000)),
            wall_clock_cap_seconds=int(limits.get("wall_clock_seconds", 1800)),
            usd_per_backend={str(k): float(v) for k, v in usd.items()},
        )

    def settings(self) -> RunSettings:
        return RunSettings.from_env(
            output_dir=self.output_dir,
            token_cap=self.token_cap,
            wall_clock_cap_seconds=self.wall_clock_cap_seconds,
        )

    def cap_for(self, backend: str) -> float:
        """The USD cap for a backend; ``0.0`` (returned) means unlimited."""
        return self.usd_per_backend.get(backend, 0.0)


def plan(config: BatchConfig) -> list[Cell]:
    """The full cartesian product of the matrix (one Cell per triple)."""
    return [
        Cell(binary_id=b, backend=k, strategy=s)
        for b in config.binaries
        for k in config.backends
        for s in config.strategies
    ]


# --------------------------------------------------------------------------- #
# Cost estimate (dry-run)                                                      #
# --------------------------------------------------------------------------- #


def _per_run_usd(backend: str) -> float:
    """A rough USD estimate for one run on ``backend`` (0.0 if untracked)."""
    price = registry.pricing(backend)
    if price is None:
        return 0.0
    prompt_rate, completion_rate = price
    return (
        _ASSUMED_PROMPT_TOKENS * prompt_rate + _ASSUMED_COMPLETION_TOKENS * completion_rate
    ) / 1_000_000


def estimate_cost(config: BatchConfig) -> dict[str, float]:
    """Rough per-backend USD estimate for the whole batch, plus a ``__total__``.

    Uses fixed per-run token assumptions and the registry's pinned pricing; it is
    an upper-bound planning aid, not a billing figure.
    """
    runs_per_backend = len(config.binaries) * len(config.strategies) * config.replicates
    out: dict[str, float] = {}
    total = 0.0
    for backend in config.backends:
        usd = _per_run_usd(backend) * runs_per_backend
        out[backend] = usd
        total += usd
    out["__total__"] = total
    return out


# --------------------------------------------------------------------------- #
# Resume bookkeeping                                                           #
# --------------------------------------------------------------------------- #


def completed_counts(output_dir: Path) -> dict[tuple[str, str, str], int]:
    """Count finalized runs per cell already on disk (for resume)."""
    counts: dict[tuple[str, str, str], int] = {}
    for record in persistence.iter_records(output_dir):
        key = (record.binary_id, record.backend.name, record.prompting_strategy.value)
        counts[key] = counts.get(key, 0) + 1
    return counts


def spend_by_backend(output_dir: Path) -> dict[str, float]:
    """Sum recorded USD cost per backend already on disk."""
    spend: dict[str, float] = {}
    for record in persistence.iter_records(output_dir):
        spend[record.backend.name] = spend.get(record.backend.name, 0.0) + record.cost.usd
    return spend


# --------------------------------------------------------------------------- #
# Execution                                                                    #
# --------------------------------------------------------------------------- #


@dataclass
class BatchResult:
    """Summary of a batch run."""

    executed: list[RunRecord] = field(default_factory=list)
    skipped_existing: int = 0
    halted_backends: set[str] = field(default_factory=set)
    interrupted: bool = False


# A factory mapping a backend *cell name* to the registry name used to resolve it
# and to attribute spend. Defaults to identity; the fake-backend tests override
# it so a whole matrix runs against scripted backends.
BackendResolver = Callable[[str], Any]


def run_batch(
    config: BatchConfig,
    *,
    dry_run: bool = False,
    backend_resolver: BackendResolver = registry.get,
    run_one_fn: Callable[..., RunRecord] = run_one,
    validator_client: Any = None,
    on_event: Callable[[str], None] | None = None,
) -> BatchResult:
    """Execute (or, with ``dry_run``, only plan) the matrix.

    ``backend_resolver`` and ``run_one_fn`` are injection seams: the test suite
    passes scripted backends and a no-Docker ``run_one`` so a whole matrix runs
    without network or a daemon.
    """
    result = BatchResult()
    emit = on_event or (lambda _msg: None)
    cells = plan(config)

    if dry_run:
        return result

    settings = config.settings()
    counts = completed_counts(config.output_dir)
    spend = spend_by_backend(config.output_dir)

    try:
        for cell in cells:
            cap = config.cap_for(cell.backend)
            already = counts.get(cell.key(), 0)
            for replicate in range(already, config.replicates):
                if cap > 0 and spend.get(cell.backend, 0.0) >= cap:
                    result.halted_backends.add(cell.backend)
                    emit(f"HALT  {cell.backend}: cost cap ${cap:.2f} reached")
                    break
                spec = resolve_binary(cell.binary_id)
                backend = backend_resolver(cell.backend)
                record = run_one_fn(
                    spec,
                    backend,
                    cell.strategy,
                    settings,
                    validator_client=validator_client,
                )
                result.executed.append(record)
                spend[cell.backend] = spend.get(cell.backend, 0.0) + record.cost.usd
                emit(
                    f"RUN   {cell.binary_id} / {cell.backend} / {cell.strategy} "
                    f"[{replicate + 1}/{config.replicates}] -> {record.outcome.value}"
                )
            result.skipped_existing += min(already, config.replicates)
    except KeyboardInterrupt:  # pragma: no cover - exercised via injected raise
        result.interrupted = True
        emit("INTERRUPTED: finished cells are persisted; re-run to resume")

    return result


__all__ = [
    "BatchConfig",
    "BatchResult",
    "Cell",
    "completed_counts",
    "estimate_cost",
    "plan",
    "run_batch",
    "spend_by_backend",
]
