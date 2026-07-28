#!/usr/bin/env python3
"""Metadata-only Trial 2 versus Trial 3 comparison.

Only archive members named ``runs/*/record.json`` are opened.  Submitted
artifacts, conversations, and traces are neither opened nor extracted.
"""

from __future__ import annotations

import collections
import json
import math
import statistics
import tarfile
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parent.parent
ARCHIVES = {
    2: ROOT / "runs_for_record_trial_2" / "runz.tgz",
    3: ROOT / "runs_for_record_trial_3" / "runs.tgz",
}
PLAN = {
    2: {
        "replicates": 2,
        "backends": [
            "claude-sonnet",
            "gpt-5",
            "qwen3-coder-30b",
            "gpt-oss-20b",
            "whiterabbitneo-v3-7b",
            "qwen3-30b-abliterated",
        ],
        "strategies": ["zero_shot", "chain_of_thought", "react"],
        "targets": [
            "ret2win-baseline",
            "cgc-cadet-00001",
            "broncoctf2026-proper-pwning",
            "ropbench-synth-ex005",
        ],
    },
    3: {
        "replicates": 2,
        "backends": [
            "claude-sonnet",
            "claude-opus",
            "gpt-5",
            "gpt-oss-20b",
            "qwen3-30b-abliterated",
            "whiterabbitneo-v3-7b",
        ],
        "strategies": ["template_backward", "recon_first"],
        "targets": [
            "ret2win-baseline",
            "cgc-cromu-00004",
            "cgc-eagle-00005",
            "cgc-nrfin-00056",
            "broncoctf2026-proper-pwning",
            "ropbench-synth-ex005",
            "ropbench-synth-ex002",
            "ropbench-synth-ex020",
            "ropbench-synth-ex101",
        ],
    },
}
TIER = {"none": 0, "ran": 1, "control": 2, "marker": 3}


def records_and_partial_count(path: Path) -> tuple[list[dict[str, Any]], int]:
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


def succeeded(record: dict[str, Any]) -> bool:
    return record["outcome"] == "success"


def validator_reached(record: dict[str, Any]) -> bool:
    return record.get("validator") is not None


def wilson(successes: int, total: int) -> tuple[float, float]:
    if total == 0:
        return (math.nan, math.nan)
    z = 1.959963984540054
    p = successes / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    halfwidth = (
        z
        * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total))
        / denominator
    )
    return (centre - halfwidth, centre + halfwidth)


def median(records: list[dict[str, Any]], fn: Callable[[dict[str, Any]], float]) -> float | None:
    values = [fn(record) for record in records]
    return statistics.median(values) if values else None


def five_number(values: list[float]) -> dict[str, float] | None:
    if not values:
        return None
    ordered = sorted(values)
    return {
        "min": ordered[0],
        "q1_empirical": ordered[len(ordered) // 4],
        "median": statistics.median(ordered),
        "q3_empirical": ordered[(3 * len(ordered)) // 4],
        "max": ordered[-1],
    }


def summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(records)
    successes = sum(succeeded(record) for record in records)
    validators = sum(validator_reached(record) for record in records)
    return {
        "n": n,
        "success": successes,
        "success_rate": successes / n if n else None,
        "success_wilson95": wilson(successes, n),
        "validator": validators,
        "validator_rate": validators / n if n else None,
        "success_given_validator": successes / validators if validators else None,
        "tiers": dict(
            sorted(
                collections.Counter(
                    record["max_tier_reached"] for record in records
                ).items(),
                key=lambda item: TIER[item[0]],
            )
        ),
        "failure_modes": dict(
            sorted(
                collections.Counter(
                    str(record.get("failure_mode")) for record in records
                ).items()
            )
        ),
        "median_total_tokens": median(
            records, lambda record: record["tokens"]["total"]
        ),
        "median_prompt_tokens": median(
            records, lambda record: record["tokens"]["prompt"]
        ),
        "median_completion_tokens": median(
            records, lambda record: record["tokens"]["completion"]
        ),
        "median_iterations": median(records, lambda record: record["iterations"]),
        "median_wall_seconds": median(
            records, lambda record: record["wall_clock_seconds"]
        ),
        "total_tokens": sum(record["tokens"]["total"] for record in records),
        "total_cost_usd": sum(record["cost"]["usd"] for record in records),
        "distributions": {
            "total_tokens": five_number(
                [record["tokens"]["total"] for record in records]
            ),
            "iterations": five_number(
                [record["iterations"] for record in records]
            ),
            "wall_seconds": five_number(
                [record["wall_clock_seconds"] for record in records]
            ),
            "tool_calls": five_number(
                [
                    sum((record.get("tool_call_counts") or {}).values())
                    for record in records
                ]
            ),
        },
    }


def grouped(
    records: list[dict[str, Any]], key: Callable[[dict[str, Any]], str]
) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for record in records:
        groups[key(record)].append(record)
    return {name: summary(subset) for name, subset in sorted(groups.items())}


def tool_totals(records: list[dict[str, Any]]) -> dict[str, Any]:
    calls: collections.Counter[str] = collections.Counter()
    success_calls: collections.Counter[str] = collections.Counter()
    failure_calls: collections.Counter[str] = collections.Counter()
    for record in records:
        calls.update(record.get("tool_call_counts") or {})
        (success_calls if succeeded(record) else failure_calls).update(
            record.get("tool_call_counts") or {}
        )
    return {
        "offered": sorted(
            {
                tool
                for record in records
                for tool in (record.get("tools_offered") or [])
            }
        ),
        "all": dict(calls.most_common()),
        "success": dict(success_calls.most_common()),
        "failure": dict(failure_calls.most_common()),
        "total": sum(calls.values()),
    }


def coverage(records: list[dict[str, Any]], trial: int) -> dict[str, Any]:
    plan = PLAN[trial]
    expected_per_backend_target = (
        len(plan["strategies"]) * int(plan["replicates"])
    )
    counts = collections.Counter(
        (backend(record), record["binary_id"]) for record in records
    )
    matrix = {
        f"{backend_name}|{target}": counts[(backend_name, target)]
        for backend_name in plan["backends"]
        for target in plan["targets"]
    }
    cell_counts = collections.Counter(
        (
            backend(record),
            record["binary_id"],
            record["prompting_strategy"],
        )
        for record in records
    )
    planned_cells = (
        len(plan["backends"]) * len(plan["targets"]) * len(plan["strategies"])
    )
    return {
        "planned_runs": planned_cells * int(plan["replicates"]),
        "finalized_runs": len(records),
        "coverage_rate": len(records)
        / (planned_cells * int(plan["replicates"])),
        "partial_directories": PARTIALS[trial],
        "backend_target_expected": expected_per_backend_target,
        "backend_target_matrix": matrix,
        "observed_factor_cells": len(cell_counts),
        "complete_factor_cells": sum(
            count == int(plan["replicates"]) for count in cell_counts.values()
        ),
        "singleton_factor_cells": sum(count == 1 for count in cell_counts.values()),
        "missing_factor_cells": planned_cells - len(cell_counts),
    }


def bronco_progress(records: list[dict[str, Any]]) -> dict[str, int]:
    terminal: collections.Counter[str] = collections.Counter()
    for record in records:
        if record["binary_id"] != "broncoctf2026-proper-pwning":
            continue
        if succeeded(record):
            terminal["marker"] += 1
            continue
        stdout = ((record.get("validator") or {}).get("stdout_excerpt") or "")
        if "Gate 3 opens" in stdout:
            terminal["gate_3"] += 1
        elif "Gate 2 opens" in stdout:
            terminal["gate_2"] += 1
        elif "Gate 1 opens" in stdout:
            terminal["gate_1"] += 1
        else:
            terminal["no_recorded_gate"] += 1
    cumulative = {
        "gate1_or_later": sum(
            terminal[key] for key in ("gate_1", "gate_2", "gate_3", "marker")
        ),
        "gate2_or_later": sum(
            terminal[key] for key in ("gate_2", "gate_3", "marker")
        ),
        "gate3_or_later": sum(terminal[key] for key in ("gate_3", "marker")),
        "marker": terminal["marker"],
    }
    return {"terminal": dict(terminal), "cumulative": cumulative}


RECORDS: dict[int, list[dict[str, Any]]] = {}
PARTIALS: dict[int, int] = {}
for trial, archive_path in ARCHIVES.items():
    RECORDS[trial], PARTIALS[trial] = records_and_partial_count(archive_path)


def main() -> None:
    common_backends = set(PLAN[2]["backends"]) & set(PLAN[3]["backends"])
    common_targets = set(PLAN[2]["targets"]) & set(PLAN[3]["targets"])
    common_strategies = set(PLAN[2]["strategies"]) & set(PLAN[3]["strategies"])
    balanced_premium_backends = {"claude-sonnet", "gpt-5"}
    output: dict[str, Any] = {
        "shared_factors": {
            "backends": sorted(common_backends),
            "targets": sorted(common_targets),
            "strategies": sorted(common_strategies),
        }
    }
    for trial in (2, 3):
        records = RECORDS[trial]
        successes = [record for record in records if succeeded(record)]
        failures = [record for record in records if not succeeded(record)]
        shared = [
            record
            for record in records
            if backend(record) in common_backends
            and record["binary_id"] in common_targets
        ]
        balanced_premium = [
            record
            for record in records
            if backend(record) in balanced_premium_backends
            and record["binary_id"] in common_targets
        ]
        output[f"trial_{trial}"] = {
            "overall": summary(records),
            "success_resources": summary(successes),
            "failure_resources": summary(failures),
            "by_backend": grouped(records, backend),
            "by_target": grouped(records, lambda record: record["binary_id"]),
            "by_strategy": grouped(
                records, lambda record: record["prompting_strategy"]
            ),
            "by_category": grouped(
                records, lambda record: record["backend"]["category"]
            ),
            "tools": tool_totals(records),
            "coverage": coverage(records, trial),
            "shared_backend_target_subset": {
                "overall": summary(shared),
                "by_backend": grouped(shared, backend),
                "by_target": grouped(shared, lambda record: record["binary_id"]),
            },
            "balanced_common_premium_subset": {
                "overall": summary(balanced_premium),
                "by_backend": grouped(balanced_premium, backend),
                "by_target": grouped(
                    balanced_premium, lambda record: record["binary_id"]
                ),
            },
            "bronco": bronco_progress(records),
            "consistency": dict(
                collections.Counter(
                    str(
                        (
                            record["outcome"],
                            record["max_tier_reached"],
                            None
                            if record.get("validator") is None
                            else record["validator"].get("succeeded"),
                        )
                    )
                    for record in records
                )
            ),
        }
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
