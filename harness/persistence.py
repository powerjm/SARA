"""
Run persistence.

Every run produces exactly one directory ``<output_dir>/<run_id>/`` holding the
canonical triple:

  * ``record.json``  — the :class:`~harness.record.RunRecord` (the contract).
  * ``trace.jsonl``  — one JSON object per node transition.
  * ``payload.bin``  — the candidate payload bytes (absent if none was committed).

Writes are **atomic**: the run is assembled inside a sibling ``.partial-<run_id>``
directory and ``os.replace``-renamed into place only once ``record.json`` is
written, so a crashed or Ctrl-C'd run never leaves a half-written run directory
that the batch resumer would mistake for a completed cell. The resumer
(:func:`iter_records`) only sees finalized directories because a partial dir has
no ``record.json`` and its name is dotted out of the ``*/record.json`` glob.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

from harness.record import RunRecord

RECORD_NAME = "record.json"
TRACE_NAME = "trace.jsonl"
PAYLOAD_NAME = "payload.bin"

_PARTIAL_PREFIX = ".partial-"


def partial_dir(output_dir: Path, run_id: str) -> Path:
    """The staging directory a run is assembled in before it is finalized."""
    return output_dir / f"{_PARTIAL_PREFIX}{run_id}"


def final_dir(output_dir: Path, run_id: str) -> Path:
    """The finalized run directory."""
    return output_dir / run_id


def begin_run(output_dir: Path, run_id: str) -> Path:
    """Create (or reset) the partial directory for ``run_id`` and return it.

    A leftover partial dir from a crashed run is cleared so the new attempt
    starts clean; a finalized run with the same id is a programming error.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    final = final_dir(output_dir, run_id)
    if final.exists():
        raise FileExistsError(f"run directory already exists: {final}")
    partial = partial_dir(output_dir, run_id)
    if partial.exists():
        _rmtree(partial)
    partial.mkdir(parents=True)
    return partial


def write_record(directory: Path, record: RunRecord) -> Path:
    """Write ``record.json`` into ``directory`` and return its path."""
    path = directory / RECORD_NAME
    path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
    return path


def finalize_run(output_dir: Path, run_id: str) -> Path:
    """Atomically rename the partial dir to the final run dir; return it."""
    partial = partial_dir(output_dir, run_id)
    final = final_dir(output_dir, run_id)
    os.replace(partial, final)
    return final


def load_record(path: Path) -> RunRecord:
    """Deserialize a ``record.json`` (accepts a file or a run directory)."""
    if path.is_dir():
        path = path / RECORD_NAME
    return RunRecord.model_validate_json(path.read_text(encoding="utf-8"))


def iter_records(output_dir: Path) -> Iterator[RunRecord]:
    """Yield every finalized run record under ``output_dir`` (skips partials)."""
    if not output_dir.is_dir():
        return
    for record_file in sorted(output_dir.glob(f"*/{RECORD_NAME}")):
        if record_file.parent.name.startswith(_PARTIAL_PREFIX):
            continue
        yield load_record(record_file)


def _rmtree(path: Path) -> None:
    """Recursively remove a directory (used to clear a stale partial run)."""
    import shutil

    shutil.rmtree(path, ignore_errors=True)


__all__ = [
    "PAYLOAD_NAME",
    "RECORD_NAME",
    "TRACE_NAME",
    "begin_run",
    "final_dir",
    "finalize_run",
    "iter_records",
    "load_record",
    "partial_dir",
    "write_record",
]
