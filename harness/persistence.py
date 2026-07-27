# SARA — Sans Agentic Rop Analysis
# Copyright (c) 2026 Jeff Powers. MIT License — see LICENSE.
# SPDX-License-Identifier: MIT
#
# Research instrument for a SANS.edu thesis on LLM agents that build ROP
# exploit chains. The ethical scope in README.md is non-negotiable and binds
# all copies, forks, and derived works: educational/CTF targets only,
# proof-of-concept payloads only. Use against systems you do not own or are
# not authorized to test is prohibited.

"""
Run persistence.

Every run produces exactly one directory ``<output_dir>/<run_id>/`` holding the
canonical artifacts:

  * ``record.json``       — the :class:`~harness.record.RunRecord` (the contract).
  * ``trace.jsonl``       — one JSON object per node transition (a lightweight,
    replayable index: node, tool-call names, token/cost counters).
  * ``conversation.jsonl`` — the full agent↔LLM↔MCP conversation: one JSON object
    per message (role, content, tool_calls, tool_call_id), i.e. every system /
    user / assistant turn, tool call, and tool result the agent actually saw.
    This is the artifact for post-hoc analysis of *why* a run behaved as it did.
  * ``payload.bin``       — the candidate payload bytes (absent if none committed).

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
CONVERSATION_NAME = "conversation.jsonl"
PAYLOAD_NAME = "payload.bin"
# The agent's exploit.py for a script-mode run (ADR 0016); persisted in the run
# dir for audit/repro alongside the payload. Not referenced by the schema.
SCRIPT_NAME = "exploit.py"

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
    "CONVERSATION_NAME",
    "PAYLOAD_NAME",
    "SCRIPT_NAME",
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
