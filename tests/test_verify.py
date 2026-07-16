"""Tests for corpus/scripts/verify.py (the corpus-truth gate over the sandbox).

Drives the real manifest resolver + ``harness.runner.verify_binary`` against the
throwaway ``fixture_corpus`` with a fake Docker client, so the whole verify path
is exercised without a daemon. Covers the four classifications ADR 0009 needs:
PASS (shell marker fired), SKIP (no PoC — ungated measured failure), FAIL (a
committed PoC that no longer fires), and ERROR (a PoC whose binary is missing).
"""

from __future__ import annotations

from typing import Any

from corpus.scripts import verify
from corpus.scripts.verify import VerifyReport, VerifyResult, VerifyStatus
from harness import corpus
from validator.runner_test_helpers import succeeding_client


def _marker_client(fixture_corpus: Any) -> Any:
    """A sandbox that prints the fixture's success marker on stdout."""
    return succeeding_client((fixture_corpus.marker + "\n").encode())


def test_verify_all_passes_when_exploit_reproduces(fixture_corpus: Any) -> None:
    report = verify.verify_all(validator_client=_marker_client(fixture_corpus))

    assert report.ok
    row = next(r for r in report.results if r.binary_id == fixture_corpus.binary_id)
    assert row.status is VerifyStatus.PASS
    assert report.counts()[VerifyStatus.PASS] == 1


def test_verify_all_skips_binary_without_poc(fixture_corpus: Any) -> None:
    # Retire the reference PoC: an ungated measured-failure target (ADR 0009).
    (corpus.exploits_dir() / f"{fixture_corpus.binary_id}.py").unlink()

    report = verify.verify_all(validator_client=_marker_client(fixture_corpus))

    row = next(r for r in report.results if r.binary_id == fixture_corpus.binary_id)
    assert row.status is VerifyStatus.SKIP
    assert report.ok  # a SKIP never gates the corpus


def test_verify_all_fails_when_marker_absent(fixture_corpus: Any) -> None:
    # The committed PoC exists but the sandbox never prints the marker.
    report = verify.verify_all(validator_client=succeeding_client(b"not the marker\n"))

    row = next(r for r in report.results if r.binary_id == fixture_corpus.binary_id)
    assert row.status is VerifyStatus.FAIL
    assert not report.ok


def test_verify_all_errors_when_binary_missing(fixture_corpus: Any) -> None:
    # A PoC with no binary to run it against cannot be verified — a hard error.
    (corpus.binaries_dir() / fixture_corpus.binary_id).unlink()

    report = verify.verify_all(validator_client=_marker_client(fixture_corpus))

    row = next(r for r in report.results if r.binary_id == fixture_corpus.binary_id)
    assert row.status is VerifyStatus.ERROR
    assert not report.ok


def test_verify_only_filters_to_one_binary(fixture_corpus: Any) -> None:
    report = verify.verify_all("does-not-exist", validator_client=_marker_client(fixture_corpus))
    assert report.results == []
    assert report.ok  # no binaries checked -> nothing failed

    report = verify.verify_all(
        fixture_corpus.binary_id, validator_client=_marker_client(fixture_corpus)
    )
    assert [r.binary_id for r in report.results] == [fixture_corpus.binary_id]


def test_main_returns_nonzero_on_failure(monkeypatch: Any, capsys: Any) -> None:
    failing = VerifyReport([VerifyResult("cgc-x", VerifyStatus.FAIL, "marker did not fire")])
    monkeypatch.setattr(verify, "verify_all", lambda only=None: failing)

    assert verify.main([]) == 1
    assert "FAIL" in capsys.readouterr().out


def test_main_returns_zero_when_all_ok(monkeypatch: Any, capsys: Any) -> None:
    passing = VerifyReport(
        [
            VerifyResult("cgc-x", VerifyStatus.PASS, "shell marker fired"),
            VerifyResult("cgc-y", VerifyStatus.SKIP, "no reference PoC"),
        ]
    )
    monkeypatch.setattr(verify, "verify_all", lambda only=None: passing)

    assert verify.main([]) == 0
    out = capsys.readouterr().out
    assert "1 verified, 1 skipped, 0 failed." in out
