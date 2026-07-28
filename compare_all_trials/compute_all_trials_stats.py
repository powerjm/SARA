#!/usr/bin/env python3
"""Metadata-only comparison of formal Trials 1, 2, and 3.

The archive reader opens only finalized ``runs/*/record.json`` members. It does
not open or extract submissions, payloads, conversations, traces, or binaries.
"""

from __future__ import annotations

import collections
import json
import math
from pathlib import Path
import statistics
import tarfile
from typing import Any, Callable


ROOT = Path(__file__).resolve().parent.parent
ARCHIVES = {
    1: ROOT / "runs_for_record_trial_1" / "runs.tgz",
    2: ROOT / "runs_for_record_trial_2" / "runz.tgz",
    3: ROOT / "runs_for_record_trial_3" / "runs.tgz",
}
PLANNED = {1: 2200, 2: 144, 3: 216}
PREMIUM = {
    1: {"claude-sonnet", "claude-opus", "gpt-5", "gemini-pro-latest"},
    2: {"claude-sonnet", "gpt-5"},
    3: {"claude-sonnet", "claude-opus", "gpt-5"},
}
SHARED_PREMIUM = {"claude-sonnet", "gpt-5"}
SHARED_TARGETS = {
    "broncoctf2026-proper-pwning",
    "ropbench-synth-ex005",
}


def load_records(path: Path) -> tuple[list[dict[str, Any]], int]:
    records: list[dict[str, Any]] = []
    partials: set[str] = set()
    with tarfile.open(path, "r:gz") as archive:
        for member in archive:
            if member.name.startswith("runs/.partial-"):
                partials.add(member.name.split("/")[1])
            if (
                member.isfile()
                and member.name.startswith("runs/")
                and member.name.endswith("/record.json")
                and "/.partial-" not in member.name
            ):
                handle = archive.extractfile(member)
                if handle is None:
                    raise RuntimeError(member.name)
                records.append(json.load(handle))
    return records, len(partials)


def backend(record: dict[str, Any]) -> str:
    return record.get("backend_handle") or record["backend"]["name"]


def success(record: dict[str, Any]) -> bool:
    return record["outcome"] == "success"


def validator(record: dict[str, Any]) -> bool:
    return record.get("validator") is not None


def tool_calls(record: dict[str, Any]) -> int | None:
    counts = record.get("tool_call_counts")
    return sum(counts.values()) if counts is not None else None


def wilson(k: int, n: int, z: float = 1.95996398454) -> tuple[float, float]:
    if not n:
        return (math.nan, math.nan)
    denominator = 1 + z * z / n
    centre = (k / n + z * z / (2 * n)) / denominator
    spread = (
        z
        * math.sqrt(k * (n - k) / n**3 + z * z / (4 * n * n))
        / denominator
    )
    return max(0.0, centre - spread), min(1.0, centre + spread)


def median(
    records: list[dict[str, Any]],
    getter: Callable[[dict[str, Any]], float],
) -> float | None:
    values = [
        value
        for record in records
        if (value := getter(record)) is not None
    ]
    return statistics.median(values) if values else None


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(records)
    successes = sum(success(record) for record in records)
    validators = sum(validator(record) for record in records)
    return {
        "n": n,
        "success": successes,
        "success_rate": successes / n if n else None,
        "success_wilson95": wilson(successes, n),
        "validator": validators,
        "validator_rate": validators / n if n else None,
        "success_given_validator": successes / validators if validators else None,
        "outcomes": dict(collections.Counter(r["outcome"] for r in records)),
        "median_total_tokens": median(records, lambda r: r["tokens"]["total"]),
        "median_wall_seconds": median(records, lambda r: r["wall_clock_seconds"]),
        "median_iterations": median(records, lambda r: r["iterations"]),
        "median_tool_calls": median(records, tool_calls),
        "total_tokens": sum(r["tokens"]["total"] for r in records),
        "total_cost_usd": sum(r["cost"]["usd"] for r in records),
        "total_tool_calls": (
            sum(value for r in records if (value := tool_calls(r)) is not None)
            if any(tool_calls(r) is not None for r in records)
            else None
        ),
    }


def grouped(
    records: list[dict[str, Any]], getter: Callable[[dict[str, Any]], str]
) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for record in records:
        groups[getter(record)].append(record)
    return {name: summarize(group) for name, group in sorted(groups.items())}


def main() -> None:
    output: dict[str, Any] = {"trials": {}}
    expected_finalized = {1: 1755, 2: 92, 3: 146}
    expected_success = {1: 0, 2: 34, 3: 43}
    for trial, path in ARCHIVES.items():
        records, partials = load_records(path)
        assert len(records) == expected_finalized[trial]
        assert sum(success(record) for record in records) == expected_success[trial]
        premium = [r for r in records if backend(r) in PREMIUM[trial]]
        aligned = [
            r
            for r in records
            if backend(r) in SHARED_PREMIUM and r["binary_id"] in SHARED_TARGETS
        ]
        output["trials"][str(trial)] = {
            "planned": PLANNED[trial],
            "partial_directories": partials,
            "never_started": PLANNED[trial] - len(records) - partials,
            "full_matrix": summarize(records),
            "full_by_backend": grouped(records, backend),
            "full_by_target": grouped(records, lambda r: r["binary_id"]),
            "premium_class": summarize(premium),
            "premium_by_backend": grouped(premium, backend),
            "premium_by_target": grouped(premium, lambda r: r["binary_id"]),
            "aligned_premium_core": summarize(aligned),
            "aligned_by_backend": grouped(aligned, backend),
            "aligned_by_target": grouped(aligned, lambda r: r["binary_id"]),
            "success_resources": summarize([r for r in records if success(r)]),
            "nonsuccess_resources": summarize([r for r in records if not success(r)]),
            "premium_success_resources": summarize(
                [r for r in premium if success(r)]
            ),
            "premium_nonsuccess_resources": summarize(
                [r for r in premium if not success(r)]
            ),
        }
    output["definitions"] = {
        "premium_backends": {
            str(trial): sorted(backends) for trial, backends in PREMIUM.items()
        },
        "aligned_premium_backends": sorted(SHARED_PREMIUM),
        "aligned_targets": sorted(SHARED_TARGETS),
        "shared_prompting_strategy_across_all_trials": [],
    }
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
