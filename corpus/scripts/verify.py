"""
Verify corpus-truth.

For each binary in the manifest, reproduce its documented **shell** exploit and
confirm the universal marker ``HELLO SANS`` appears on stdout — produced by a
spawned ``/bin/sh`` rather than echoed from the payload (the anti-echo guard).
This is the gate that locks the corpus before any agent runs happen (ADR 0009).

The "documented exploit" for a binary is a small Python module stored alongside
it at ``corpus/exploits/<id>.py`` exposing ``build_payload()`` / ``load_chain()``
(``corpus/exploits/cgc-cadet-00001.py`` is the worked example). This script is a
thin driver over :func:`harness.runner.verify_binary`, so it shares the single
execution path — the validator sandbox (ADR 0002) — with ``sara run`` and
``sara verify``; it does not execute payloads itself.

Not every manifest entry has a reference shell PoC. ADR 0009 is explicit that
higher-tier binaries may be *measured failures* with no known-good exploit, and
that ``verify`` "can only gate the binaries that have a known-good shell PoC".
Such entries are therefore reported as ``SKIP`` (not gated), never as failures.
A binary that *does* ship a PoC which no longer reproduces is a hard ``FAIL``:
the corpus is broken and the run harness must refuse to start.

Usage::

    python -m corpus.scripts.verify            # verify every manifest entry
    python -m corpus.scripts.verify --id cgc-cromu-00004
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from harness import corpus
from harness.runner import verify_binary


class VerifyStatus(StrEnum):
    """Per-binary verification outcome."""

    PASS = "PASS"  # noqa: S105 - status label, not a secret; sandbox spawned a shell w/ marker
    FAIL = "FAIL"  # PoC + binary present, but the exploit no longer reproduces — corpus broken
    SKIP = "SKIP"  # no reference shell PoC — a measured failure per ADR 0009, not gated
    ERROR = "ERROR"  # a PoC exists but could not be run (e.g. its binary is missing)


@dataclass(frozen=True)
class VerifyResult:
    """One row of the verification table."""

    binary_id: str
    status: VerifyStatus
    detail: str


@dataclass(frozen=True)
class VerifyReport:
    """The full verification run; ``ok`` is False iff any binary FAILed/ERRORed."""

    results: list[VerifyResult]

    @property
    def ok(self) -> bool:
        return all(r.status not in (VerifyStatus.FAIL, VerifyStatus.ERROR) for r in self.results)

    def counts(self) -> dict[VerifyStatus, int]:
        counts = dict.fromkeys(VerifyStatus, 0)
        for result in self.results:
            counts[result.status] += 1
        return counts


def _verify_one(binary_id: str, *, validator_client: Any = None) -> VerifyResult:
    """Verify a single binary, classifying it into a :class:`VerifyResult`.

    A binary with no ``corpus/exploits/<id>.py`` is a ``SKIP`` (ADR 0009 permits
    ungated measured-failure targets). A PoC whose binary is missing is an
    ``ERROR``. Otherwise the exploit is reproduced in the sandbox: the marker
    must fire (``succeeded``) — which already encodes the anti-echo guard, since
    ``execute`` only sets ``succeeded`` when the marker is absent from the
    payload bytes.
    """
    exploit_path = corpus.exploits_dir() / f"{binary_id}.py"
    binary_path = corpus.binaries_dir() / binary_id

    if not exploit_path.is_file():
        return VerifyResult(
            binary_id, VerifyStatus.SKIP, "no reference PoC (measured failure — not gated)"
        )
    if not binary_path.is_file():
        return VerifyResult(
            binary_id, VerifyStatus.ERROR, f"PoC present but binary missing at {binary_path}"
        )

    try:
        output = verify_binary(binary_id, validator_client=validator_client)
    except Exception as exc:  # noqa: BLE001 - report any failure as a table row, never abort
        return VerifyResult(binary_id, VerifyStatus.ERROR, f"{type(exc).__name__}: {exc}")

    if output.succeeded and output.stdout_marker_found:
        return VerifyResult(
            binary_id,
            VerifyStatus.PASS,
            f"shell marker fired (rc={output.return_code}, {output.elapsed_seconds:.2f}s)",
        )
    if output.marker_in_payload:
        detail = "marker present in payload — anti-echo guard tripped (not a real shell)"
    else:
        detail = (
            f"marker did not fire (found={output.stdout_marker_found}, rc={output.return_code})"
        )
    return VerifyResult(binary_id, VerifyStatus.FAIL, detail)


def verify_all(only: str | None = None, *, validator_client: Any = None) -> VerifyReport:
    """Verify every manifest binary (or just ``only``) and return a report."""
    results: list[VerifyResult] = []
    for entry in corpus.load_manifest():
        binary_id = str(entry.get("id"))
        if only is not None and binary_id != only:
            continue
        results.append(_verify_one(binary_id, validator_client=validator_client))
    return VerifyReport(results)


def _render(report: VerifyReport) -> str:
    lines = [
        "Corpus-truth verification (ADR 0009: success == spawned /bin/sh prints HELLO SANS)",
        "",
        f"  {'binary':30s}  {'status':6s}  detail",
    ]
    for result in report.results:
        lines.append(f"  {result.binary_id:30s}  {result.status.value:6s}  {result.detail}")
    counts = report.counts()
    lines.append("")
    lines.append(
        f"{counts[VerifyStatus.PASS]} verified, "
        f"{counts[VerifyStatus.SKIP]} skipped, "
        f"{counts[VerifyStatus.FAIL] + counts[VerifyStatus.ERROR]} failed."
    )
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    only: str | None = None
    if "--id" in argv:
        idx = argv.index("--id")
        only = argv[idx + 1]

    report = verify_all(only)
    print(_render(report))
    return 0 if report.ok else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
