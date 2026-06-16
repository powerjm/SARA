"""Tests for the experiment-matrix batch runner (harness.matrix)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fakes.backend import FakeBackend, ScriptedTurn

from agent.tools import ToolLayer
from harness import persistence
from harness.matrix import (
    BatchConfig,
    Cell,
    completed_counts,
    estimate_cost,
    plan,
    run_batch,
    spend_by_backend,
)
from harness.record import Outcome
from harness.runner import RunSettings, run_one
from mcp_servers.ropgadget.parser import Gadget
from mcp_servers.ropgadget.server import EnumerateResult

# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _canned_enumerator(**_: object) -> EnumerateResult:
    return EnumerateResult(
        binary_path="b",
        total_found=1,
        returned=1,
        truncated=False,
        gadgets=[Gadget("0x4011ad", "pop rdi ; ret", 2)],
    )


def _giveup_resolver(cost_usd: float = 0.0) -> Any:
    """A backend resolver returning a fresh give-up FakeBackend named for the cell."""

    def resolve(name: str) -> FakeBackend:
        return FakeBackend(
            script=[ScriptedTurn(text="giving up", cost_usd=cost_usd)],
            name=name,
        )

    return resolve


def _batch_run_one(spec: Any, backend: Any, strategy: str, settings: RunSettings, **kw: Any) -> Any:
    # Inject the canned enumerator so no ROPgadget CLI is needed.
    return run_one(
        spec, backend, strategy, settings, tools=ToolLayer(enumerate_fn=_canned_enumerator)
    )


def _write_config(tmp_path: Path, **over: Any) -> Path:
    import yaml

    data: dict[str, Any] = {
        "replicates": over.get("replicates", 2),
        "binaries": over.get("binaries", ["sample-overflow"]),
        "backends": over.get("backends", ["claude-sonnet", "claude-opus"]),
        "strategies": over.get("strategies", ["zero_shot", "react"]),
        "output_dir": str(over.get("output_dir", tmp_path / "runs")),
        "limits": over.get("limits", {"tokens": 200000, "wall_clock_seconds": 1800}),
    }
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "experiments.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# Config + planning                                                           #
# --------------------------------------------------------------------------- #


def test_from_yaml_parses_shape(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        replicates=5,
        limits={
            "tokens": 1000,
            "wall_clock_seconds": 60,
            "usd_per_backend": {"claude-opus": 50.0},
        },
    )
    cfg = BatchConfig.from_yaml(path)
    assert cfg.replicates == 5
    assert cfg.token_cap == 1000
    assert cfg.cap_for("claude-opus") == 50.0
    assert cfg.cap_for("claude-sonnet") == 0.0  # absent -> unlimited


def test_example_config_parses() -> None:
    cfg = BatchConfig.from_yaml(Path("experiments.example.yaml"))
    assert cfg.replicates == 5
    assert cfg.cap_for("claude-sonnet") > 0


def test_plan_is_full_product(tmp_path: Path) -> None:
    cfg = BatchConfig.from_yaml(_write_config(tmp_path))
    cells = plan(cfg)
    assert len(cells) == 1 * 2 * 2
    assert Cell("sample-overflow", "claude-sonnet", "zero_shot") in cells


# --------------------------------------------------------------------------- #
# Cost estimate                                                               #
# --------------------------------------------------------------------------- #


def test_estimate_cost_uses_registry_pricing(tmp_path: Path) -> None:
    cfg = BatchConfig.from_yaml(_write_config(tmp_path, replicates=2))
    est = estimate_cost(cfg)
    # opus is pricier than sonnet; both positive; total is their sum.
    assert est["claude-opus"] > est["claude-sonnet"] > 0
    assert est["__total__"] == pytest.approx(est["claude-sonnet"] + est["claude-opus"])


# --------------------------------------------------------------------------- #
# Execution + resume                                                          #
# --------------------------------------------------------------------------- #


def test_run_batch_dry_run_executes_nothing(tmp_path: Path) -> None:
    cfg = BatchConfig.from_yaml(_write_config(tmp_path))
    result = run_batch(cfg, dry_run=True)
    assert result.executed == []


def test_run_batch_executes_full_matrix(fixture_corpus: Any, tmp_path: Path) -> None:
    cfg = BatchConfig.from_yaml(_write_config(tmp_path, output_dir=tmp_path / "runs"))
    result = run_batch(cfg, backend_resolver=_giveup_resolver(), run_one_fn=_batch_run_one)
    # 1 binary × 2 backends × 2 strategies × 2 replicates = 8 runs.
    assert len(result.executed) == 8
    assert all(r.outcome == Outcome.FAILURE for r in result.executed)
    assert len(list(persistence.iter_records(cfg.output_dir))) == 8


def test_run_batch_resumes_without_redoing(fixture_corpus: Any, tmp_path: Path) -> None:
    cfg = BatchConfig.from_yaml(_write_config(tmp_path, output_dir=tmp_path / "runs"))
    # First pass: run everything.
    first = run_batch(cfg, backend_resolver=_giveup_resolver(), run_one_fn=_batch_run_one)
    assert len(first.executed) == 8
    # Second pass: every cell is complete -> nothing re-run.
    second = run_batch(cfg, backend_resolver=_giveup_resolver(), run_one_fn=_batch_run_one)
    assert second.executed == []
    assert len(list(persistence.iter_records(cfg.output_dir))) == 8


def test_run_batch_partial_resume(fixture_corpus: Any, tmp_path: Path) -> None:
    cfg = BatchConfig.from_yaml(_write_config(tmp_path, output_dir=tmp_path / "runs", replicates=3))
    # Pre-run only the first replicate of every cell by faking replicates=1.
    cfg1 = BatchConfig.from_yaml(
        _write_config(tmp_path / "a", output_dir=tmp_path / "runs", replicates=1)
    )
    run_batch(cfg1, backend_resolver=_giveup_resolver(), run_one_fn=_batch_run_one)
    assert len(list(persistence.iter_records(cfg.output_dir))) == 4  # 2x2 cells x1

    # Now run with replicates=3: each cell needs 2 more.
    result = run_batch(cfg, backend_resolver=_giveup_resolver(), run_one_fn=_batch_run_one)
    assert len(result.executed) == 8  # 4 cells x 2 remaining
    assert len(list(persistence.iter_records(cfg.output_dir))) == 12


# --------------------------------------------------------------------------- #
# Cost cap halts a backend                                                    #
# --------------------------------------------------------------------------- #


def test_cost_cap_halts_backend(fixture_corpus: Any, tmp_path: Path) -> None:
    cfg = BatchConfig.from_yaml(
        _write_config(
            tmp_path,
            output_dir=tmp_path / "runs",
            replicates=5,
            backends=["claude-sonnet"],
            strategies=["zero_shot"],
            limits={
                "tokens": 200000,
                "wall_clock_seconds": 1800,
                "usd_per_backend": {"claude-sonnet": 0.025},
            },
        )
    )
    # Each run costs 0.01; cap 0.025 allows 3 runs (0.00, 0.01, 0.02 < 0.025),
    # then the 4th is halted (spend 0.03 >= 0.025).
    result = run_batch(
        cfg, backend_resolver=_giveup_resolver(cost_usd=0.01), run_one_fn=_batch_run_one
    )
    assert "claude-sonnet" in result.halted_backends
    assert len(result.executed) == 3


# --------------------------------------------------------------------------- #
# Spend accounting                                                            #
# --------------------------------------------------------------------------- #


def test_spend_by_backend_sums_records(fixture_corpus: Any, tmp_path: Path) -> None:
    cfg = BatchConfig.from_yaml(
        _write_config(
            tmp_path,
            output_dir=tmp_path / "runs",
            backends=["claude-sonnet"],
            strategies=["zero_shot"],
            replicates=2,
        )
    )
    run_batch(cfg, backend_resolver=_giveup_resolver(cost_usd=0.01), run_one_fn=_batch_run_one)
    spend = spend_by_backend(cfg.output_dir)
    assert spend["claude-sonnet"] == pytest.approx(0.02)
    assert completed_counts(cfg.output_dir)[("sample-overflow", "claude-sonnet", "zero_shot")] == 2
