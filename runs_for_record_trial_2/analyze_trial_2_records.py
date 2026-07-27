#!/usr/bin/env python3
"""Read-only, metadata-only audit of the Trial 2 run archive.

This script never extracts or executes submitted artifacts.  It reads RunRecord
JSON, trace JSONL, and conversation JSONL directly from the tar archive.  The
only operation performed on exploit.py members is a SHA-256 digest for
replicate-diversity accounting; their contents are not parsed or emitted.
"""

from __future__ import annotations

import collections
import hashlib
import json
import math
import statistics
import tarfile
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parent
ARCHIVE = ROOT / "runz.tgz"
TIER_ORDER = {"none": 0, "ran": 1, "control": 2, "marker": 3}


def read_json(member: tarfile.TarInfo, archive: tarfile.TarFile) -> dict[str, Any]:
    handle = archive.extractfile(member)
    if handle is None:
        raise RuntimeError(f"Cannot read {member.name}")
    return json.load(handle)


def read_jsonl(member: tarfile.TarInfo, archive: tarfile.TarFile) -> list[dict[str, Any]]:
    handle = archive.extractfile(member)
    if handle is None:
        raise RuntimeError(f"Cannot read {member.name}")
    return [json.loads(line) for line in handle if line.strip()]


def median(values: Iterable[float]) -> float | None:
    seq = list(values)
    return statistics.median(seq) if seq else None


def wilson(successes: int, total: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if total == 0:
        return (math.nan, math.nan)
    proportion = successes / total
    denominator = 1 + z * z / total
    centre = proportion + z * z / (2 * total)
    spread = z * math.sqrt(
        proportion * (1 - proportion) / total + z * z / (4 * total * total)
    )
    return ((centre - spread) / denominator, (centre + spread) / denominator)


def group_rows(records: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for record in records:
        if key == "backend":
            value = record["backend_handle"]
        else:
            value = record[key]
        grouped[value].append(record)

    rows = []
    for value, subset in sorted(grouped.items()):
        successes = sum(record["outcome"] == "success" for record in subset)
        low, high = wilson(successes, len(subset))
        tiers = collections.Counter(record["max_tier_reached"] for record in subset)
        rows.append(
            {
                key: value,
                "n": len(subset),
                "success": successes,
                "rate": successes / len(subset),
                "wilson95": [low, high],
                "tiers": dict(sorted(tiers.items(), key=lambda item: TIER_ORDER[item[0]])),
                "failure_modes": dict(
                    sorted(
                        collections.Counter(
                            str(record["failure_mode"]) for record in subset
                        ).items()
                    )
                ),
                "median_iterations": median(record["iterations"] for record in subset),
                "median_wall_seconds": median(record["wall_clock_seconds"] for record in subset),
                "median_prompt_tokens": median(record["tokens"]["prompt"] for record in subset),
                "median_completion_tokens": median(
                    record["tokens"]["completion"] for record in subset
                ),
                "median_total_tokens": median(record["tokens"]["total"] for record in subset),
                "cost_usd": sum(record["cost"]["usd"] for record in subset),
            }
        )
    return rows


def main() -> None:
    with tarfile.open(ARCHIVE, "r:gz") as archive:
        members = {member.name: member for member in archive.getmembers()}
        record_members = [
            member
            for member in members.values()
            if member.name.startswith("runs/")
            and member.name.endswith("/record.json")
            and "/.partial-" not in member.name
        ]
        records = [read_json(member, archive) for member in record_members]

        trace_by_run: dict[str, list[dict[str, Any]]] = {}
        tool_sequence_by_run: dict[str, tuple[str, ...]] = {}
        exploit_digest_by_run: dict[str, str] = {}
        for record in records:
            run_id = record["run_id"]
            trace_name = f"runs/{run_id}/trace.jsonl"
            conversation_name = f"runs/{run_id}/conversation.jsonl"
            trace_by_run[run_id] = read_jsonl(members[trace_name], archive)
            conversation = read_jsonl(members[conversation_name], archive)
            tool_sequence_by_run[run_id] = tuple(
                call["name"]
                for message in conversation
                for call in (message.get("tool_calls") or [])
            )
            exploit_name = f"runs/{run_id}/exploit.py"
            if exploit_name in members:
                handle = archive.extractfile(members[exploit_name])
                if handle is not None:
                    exploit_digest_by_run[run_id] = hashlib.sha256(handle.read()).hexdigest()

        partial_members = [
            member
            for member in members.values()
            if member.name.startswith("runs/.partial-") and member.name.endswith("/trace.jsonl")
        ]
        partials = {}
        for member in partial_members:
            events = read_jsonl(member, archive)
            partials[member.name.split("/")[1]] = {
                "events": len(events),
                "last": events[-1] if events else None,
            }

    tiers = collections.Counter(record["max_tier_reached"] for record in records)
    outcomes = collections.Counter(record["outcome"] for record in records)
    failure_modes = collections.Counter(str(record["failure_mode"]) for record in records)
    tool_totals = collections.Counter()
    tool_success = collections.Counter()
    tool_failure = collections.Counter()
    for record in records:
        tool_totals.update(record["tool_call_counts"])
        (tool_success if record["outcome"] == "success" else tool_failure).update(
            record["tool_call_counts"]
        )

    termination_reasons = collections.Counter()
    for record in records:
        terminated = [
            event
            for event in trace_by_run[record["run_id"]]
            if event.get("terminated")
        ]
        termination_reasons.update(
            [terminated[-1].get("termination_reason") if terminated else "<missing>"]
        )

    return_codes = collections.Counter()
    validator_count = 0
    marker_found = 0
    anti_echo = 0
    validator_success = 0
    chain_fingerprints = 0
    for record in records:
        validator = record.get("validator")
        if validator is None:
            continue
        validator_count += 1
        return_codes.update([str(validator.get("return_code"))])
        marker_found += bool(validator.get("stdout_marker_found"))
        anti_echo += bool(validator.get("marker_in_payload"))
        validator_success += bool(validator.get("succeeded"))
        chain_fingerprints += validator.get("chain_fingerprint") is not None

    cells: dict[tuple[str, str, str], list[dict[str, Any]]] = collections.defaultdict(list)
    for record in records:
        cells[
            (
                record["binary_id"],
                record["backend_handle"],
                record["prompting_strategy"],
            )
        ].append(record)
    replicate_counts = collections.Counter(len(subset) for subset in cells.values())

    diversity_by_backend: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for (_, backend, _), subset in cells.items():
        if len(subset) != 2:
            continue
        sequences = {
            tool_sequence_by_run[record["run_id"]]
            for record in subset
        }
        digests = {
            exploit_digest_by_run[record["run_id"]]
            for record in subset
            if record["run_id"] in exploit_digest_by_run
        }
        diversity_by_backend[backend].append(
            {
                "distinct_tool_sequences": len(sequences),
                "distinct_exploit_digests": len(digests),
                "scripts_present": sum(
                    record["run_id"] in exploit_digest_by_run for record in subset
                ),
            }
        )

    diversity_summary = {}
    for backend, rows in sorted(diversity_by_backend.items()):
        diversity_summary[backend] = {
            "complete_cells": len(rows),
            "mean_distinct_tool_sequences": statistics.mean(
                row["distinct_tool_sequences"] for row in rows
            ),
            "mean_distinct_exploit_digests": statistics.mean(
                row["distinct_exploit_digests"] for row in rows
            ),
            "mean_scripts_present": statistics.mean(
                row["scripts_present"] for row in rows
            ),
        }

    success_records = [record for record in records if record["outcome"] == "success"]
    failure_records = [record for record in records if record["outcome"] != "success"]

    bronco_progress = collections.Counter()
    for record in records:
        if record["binary_id"] != "broncoctf2026-proper-pwning":
            continue
        if record["outcome"] == "success":
            bronco_progress["marker"] += 1
            continue
        stdout = ((record.get("validator") or {}).get("stdout_excerpt") or "")
        if "Gate 3 opens" in stdout:
            bronco_progress["gate_3"] += 1
        elif "Gate 2 opens" in stdout:
            bronco_progress["gate_2"] += 1
        elif "Gate 1 opens" in stdout:
            bronco_progress["gate_1"] += 1
        else:
            bronco_progress["no_recorded_gate"] += 1

    output = {
        "archive": {
            "record_count": len(records),
            "partial_trace_count": len(partials),
            "partials": partials,
            "schema_versions": dict(
                sorted(collections.Counter(record["schema_version"] for record in records).items())
            ),
            "cell_count_observed": len(cells),
            "replicate_counts_per_observed_cell": dict(sorted(replicate_counts.items())),
        },
        "overall": {
            "outcomes": dict(sorted(outcomes.items())),
            "tiers": dict(sorted(tiers.items(), key=lambda item: TIER_ORDER[item[0]])),
            "failure_modes": dict(sorted(failure_modes.items())),
            "trace_termination_reasons": dict(sorted(termination_reasons.items())),
            "tokens": {
                "prompt": sum(record["tokens"]["prompt"] for record in records),
                "completion": sum(record["tokens"]["completion"] for record in records),
                "total": sum(record["tokens"]["total"] for record in records),
            },
            "cost_usd": sum(record["cost"]["usd"] for record in records),
            "validator": {
                "records_with_validator": validator_count,
                "succeeded": validator_success,
                "stdout_marker_found": marker_found,
                "marker_in_payload": anti_echo,
                "chain_fingerprint_present": chain_fingerprints,
                "return_codes": dict(sorted(return_codes.items())),
            },
        },
        "by_backend": group_rows(records, "backend"),
        "by_binary": group_rows(records, "binary_id"),
        "by_strategy": group_rows(records, "prompting_strategy"),
        "success_vs_failure": {
            "success": {
                "n": len(success_records),
                "median_iterations": median(record["iterations"] for record in success_records),
                "median_wall_seconds": median(
                    record["wall_clock_seconds"] for record in success_records
                ),
                "median_prompt_tokens": median(
                    record["tokens"]["prompt"] for record in success_records
                ),
                "median_completion_tokens": median(
                    record["tokens"]["completion"] for record in success_records
                ),
                "median_total_tokens": median(
                    record["tokens"]["total"] for record in success_records
                ),
            },
            "failure": {
                "n": len(failure_records),
                "median_iterations": median(record["iterations"] for record in failure_records),
                "median_wall_seconds": median(
                    record["wall_clock_seconds"] for record in failure_records
                ),
                "median_prompt_tokens": median(
                    record["tokens"]["prompt"] for record in failure_records
                ),
                "median_completion_tokens": median(
                    record["tokens"]["completion"] for record in failure_records
                ),
                "median_total_tokens": median(
                    record["tokens"]["total"] for record in failure_records
                ),
            },
        },
        "tool_calls": {
            "all": dict(tool_totals.most_common()),
            "success": dict(tool_success.most_common()),
            "failure": dict(tool_failure.most_common()),
        },
        "replicate_diversity": diversity_summary,
        "broncoctf_recorded_progress": dict(sorted(bronco_progress.items())),
    }
    print(json.dumps(output, indent=2, sort_keys=False))


if __name__ == "__main__":
    main()
