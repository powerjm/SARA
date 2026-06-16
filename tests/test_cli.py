"""Tests for the harness CLI (harness.cli).

These exercise the real command surface: a single ``run`` against the fixture
corpus with the scripted ``fake`` backend, ``batch --dry-run`` planning, and the
presentation/exit logic of ``verify`` / ``replay`` (with their Docker-touching
inner functions stubbed). No network, no API key, no Docker daemon.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

import harness.cli as cli_mod
from harness.cli import cli
from harness.record import ValidatorOutput


def _giveup_cassette(tmp_path: Path) -> Path:
    path = tmp_path / "giveup.jsonl"
    path.write_text('{"text": "no viable chain; giving up"}\n', encoding="utf-8")
    return path


def test_cli_help_shows_subcommands() -> None:
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    for sub in ("run", "batch", "verify", "replay"):
        assert sub in result.output


def test_run_command_requires_binary_and_backend() -> None:
    result = CliRunner().invoke(cli, ["run"])
    assert result.exit_code != 0
    assert "Missing option" in result.output or "Error" in result.output


def test_run_command_rejects_unknown_strategy() -> None:
    result = CliRunner().invoke(
        cli, ["run", "--binary", "x", "--backend", "y", "--strategy", "wishful_thinking"]
    )
    assert result.exit_code != 0


def test_run_command_unknown_binary_errors(fixture_corpus: Any, tmp_path: Path) -> None:
    result = CliRunner().invoke(
        cli,
        [
            "run",
            "--binary",
            "does-not-exist",
            "--backend",
            "fake",
            "--output-dir",
            str(tmp_path / "runs"),
        ],
    )
    assert result.exit_code != 0
    assert "unknown binary_id" in result.output


def test_run_command_end_to_end_with_fake(
    fixture_corpus: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_BACKEND_CASSETTE", str(_giveup_cassette(tmp_path)))
    out_dir = tmp_path / "runs"
    result = CliRunner().invoke(
        cli,
        ["run", "--binary", "sample-overflow", "--backend", "fake", "--output-dir", str(out_dir)],
    )
    assert result.exit_code == 0, result.output
    assert "outcome=" in result.output
    # Exactly one finalized run directory was written.
    run_dirs = [p for p in out_dir.iterdir() if not p.name.startswith(".partial-")]
    assert len(run_dirs) == 1
    assert (run_dirs[0] / "record.json").is_file()


def test_batch_dry_run_prints_plan_and_estimate(tmp_path: Path) -> None:
    result = CliRunner().invoke(cli, ["batch", "--config", "experiments.example.yaml", "--dry-run"])
    assert result.exit_code == 0
    assert "Experiment matrix" in result.output
    assert "est. cost" in result.output
    assert "dry run" in result.output


def test_verify_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cli_mod,
        "verify_binary",
        lambda binary: ValidatorOutput(
            succeeded=True,
            return_code=0,
            stdout_marker_found=True,
            matched_documented_chain=True,
        ),
    )
    result = CliRunner().invoke(cli, ["verify", "--binary", "sample-overflow"])
    assert result.exit_code == 0
    assert "PASS" in result.output


def test_verify_fail_exits_nonzero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cli_mod,
        "verify_binary",
        lambda binary: ValidatorOutput(
            succeeded=False,
            return_code=1,
            stdout_marker_found=False,
            matched_documented_chain=False,
            stderr_excerpt="boom",
        ),
    )
    result = CliRunner().invoke(cli, ["verify", "--binary", "sample-overflow"])
    assert result.exit_code != 0
    assert "FAIL" in result.output


def test_replay_prints_result(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    output = ValidatorOutput(
        succeeded=True,
        return_code=0,
        stdout_marker_found=True,
        matched_documented_chain=False,
    )
    monkeypatch.setattr(cli_mod, "replay_run", lambda run_id, **kw: (None, output))
    result = CliRunner().invoke(cli, ["replay", "--run-id", "abc", "--output-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "replayed" in result.output
