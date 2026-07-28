#!/usr/bin/env python3
"""Reproduce the Trial-3 run-for-record numbers from the archived RunRecords.

Usage:  python analyze_trial_3_records.py [runs_dir]   (default: ./runs)

Emits the headline, per-backend ladder, per-binary difficulty, strategy split,
tool-use totals, efficiency table, wall-clock envelope, and the paired premium
matrix used in RUN_FOR_RECORD_ANALYSIS.Opus5.md. Pure stdlib, no deps.
"""

from __future__ import annotations

import glob
import json
import math
import statistics as st
import sys
from collections import Counter, defaultdict

TIER = {"none": 0, "ran": 1, "control": 2, "marker": 3}
PREMIUM = ["claude-sonnet", "claude-opus", "gpt-5"]
ORDER = PREMIUM + ["gpt-oss-20b", "qwen3-30b-abliterated", "whiterabbitneo-v3-7b"]
BINARIES = [
    "ret2win-baseline",
    "ropbench-synth-ex005",
    "ropbench-synth-ex002",
    "ropbench-synth-ex020",
    "ropbench-synth-ex101",
    "broncoctf2026-proper-pwning",
    "cgc-cromu-00004",
    "cgc-eagle-00005",
    "cgc-nrfin-00056",
]


def med(xs: list[float]) -> int:
    return round(st.median(xs)) if xs else 0


def wilson(s: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = s / n
    d = 1 + z * z / n
    c = (p + z * z / 2 / n) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / 4 / n / n) / d
    return (100 * (c - h), 100 * (c + h))


def load(runs_dir: str) -> list[dict]:
    recs = []
    for f in glob.glob(f"{runs_dir}/*/record.json"):
        with open(f) as fh:
            recs.append(json.load(fh))
    return recs


def main() -> None:
    runs_dir = sys.argv[1] if len(sys.argv) > 1 else "./runs"
    recs = load(runs_dir)
    n = len(recs)
    succ = sum(1 for r in recs if r["outcome"] == "success")
    print(f"HEADLINE: {succ}/{n} success ({100 * succ / n:.0f}%)")

    prem = [r for r in recs if r["backend"]["category"] == "premium"]
    loc = [r for r in recs if r["backend"]["category"] != "premium"]
    print(
        f"  premium {sum(1 for r in prem if r['outcome'] == 'success')}/{len(prem)}"
        f" · local {sum(1 for r in loc if r['outcome'] == 'success')}/{len(loc)}"
    )

    by = defaultdict(list)
    for r in recs:
        by[r["backend_handle"]].append(r)

    print("\n=== LADDER per backend (none/ran/control/marker) ===")
    for b in ORDER:
        rs = by.get(b, [])
        if not rs:
            continue
        t = Counter(r["max_tier_reached"] for r in rs)
        s = sum(1 for r in rs if r["outcome"] == "success")
        print(
            f"{b:24s} n={len(rs):3d} none={t.get('none', 0):2d} ran={t.get('ran', 0):2d}"
            f" control={t.get('control', 0):2d} marker={t.get('marker', 0):2d}"
            f"  succ={s} cost=${sum(r['cost']['usd'] for r in rs):.2f}"
        )

    print("\n=== PER BINARY (ran+/control+/marker) ===")
    for bin_ in BINARIES:
        rs = [r for r in recs if r["binary_id"] == bin_]
        rp = sum(1 for r in rs if TIER[r["max_tier_reached"]] >= 1)
        cp = sum(1 for r in rs if TIER[r["max_tier_reached"]] >= 2)
        mk = sum(1 for r in rs if r["max_tier_reached"] == "marker")
        print(f"{bin_:30s} n={len(rs):2d} ran+={rp:2d} control+={cp:2d} marker={mk:2d}")

    print("\n=== STRATEGY (all / premium) ===")
    for s in ("template_backward", "recon_first"):
        rs = [r for r in recs if r["prompting_strategy"] == s]
        ps = [r for r in rs if r["backend"]["category"] == "premium"]
        print(
            f"{s:20s} all={sum(1 for r in rs if r['outcome'] == 'success')}/{len(rs)}"
            f"  premium={sum(1 for r in ps if r['outcome'] == 'success')}/{len(ps)}"
        )

    print("\n=== TOOL CALLS ===")
    tc: Counter = Counter()
    for r in recs:
        tc.update(r.get("tool_call_counts", {}))
    tot = sum(tc.values())
    for k, v in tc.most_common(10):
        print(f"{k:26s} {v:5d} {100 * v / tot:.1f}%")

    print("\n=== EFFICIENCY (median) ===")
    for lbl, g in (
        ("SUCCESS", [r for r in recs if r["outcome"] == "success"]),
        ("FAILURE", [r for r in recs if r["outcome"] == "failure"]),
    ):
        print(
            f"{lbl}: n={len(g)} iters={med([r['iterations'] for r in g])}"
            f" prompt={med([r['tokens']['prompt'] for r in g])}"
            f" total={med([r['tokens']['total'] for r in g])}"
        )
    tp = sum(r["tokens"]["prompt"] for r in recs)
    tt = sum(r["tokens"]["total"] for r in recs)
    print(
        f"total tokens {tt / 1e6:.1f}M ({100 * tp / tt:.0f}% prompt) · cost ${sum(r['cost']['usd'] for r in recs):.2f}"
    )

    print("\n=== WALL-CLOCK (premium: success vs failure median) ===")
    for b in PREMIUM:
        rs = by.get(b, [])
        sm = med([r["wall_clock_seconds"] for r in rs if r["outcome"] == "success"])
        fm = med([r["wall_clock_seconds"] for r in rs if r["outcome"] == "failure"])
        wc = sum(1 for r in rs if r.get("failure_mode") == "wall_clock")
        print(f"{b:16s} succ_med={sm:4d}s fail_med={fm:4d}s wall_clock_fails={wc}")

    print("\n=== PAIRED PREMIUM MATRIX (any-success; rows binaries, cols sonnet/opus/gpt-5) ===")
    cell = defaultdict(lambda: defaultdict(int))
    for r in recs:
        if r["backend_handle"] in PREMIUM and r["outcome"] == "success":
            cell[r["binary_id"]][r["backend_handle"]] = 1
    M = [[cell[b].get(k, 0) for k in PREMIUM] for b in BINARIES]
    for b, row in zip(BINARIES, M):
        print(f"  {b:30s} {row}")
    N, k = len(M), len(PREMIUM)
    col = [sum(M[i][j] for i in range(N)) for j in range(k)]
    rowsum = [sum(M[i]) for i in range(N)]
    G = sum(col)
    den = k * G - sum(x * x for x in rowsum)
    Q = ((k - 1) * (k * sum(c * c for c in col) - G * G) / den) if den else float("nan")
    print(f"Cochran's Q = {Q:.3f}, df={k - 1}, p(df=2) = {math.exp(-Q / 2):.4f}")

    print("\n=== WILSON 95% CI (all attempted) ===")
    for b in ORDER:
        rs = by.get(b, [])
        if not rs:
            continue
        s = sum(1 for r in rs if r["outcome"] == "success")
        lo, hi = wilson(s, len(rs))
        print(f"{b:24s} {s}/{len(rs)} = {100 * s / len(rs):4.1f}%  CI[{lo:.1f}, {hi:.1f}]")


if __name__ == "__main__":
    main()
