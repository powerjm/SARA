"""Generate Trial 3 token-metric diagrams parallel to the Trial 2 suite.

Only finalized ``runs/*/record.json`` metadata is opened. The generator does
not open conversations, traces, exploit source, payloads, or target binaries,
and it does not execute a submission.
"""

from __future__ import annotations

import collections
from html import escape
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import statistics
import sys
import tarfile
import textwrap
from typing import Any


TRIAL_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = TRIAL_ROOT.parent
ARCHIVE = TRIAL_ROOT / "runs.tgz"
OUTPUT = Path(__file__).resolve().parent / "token_metrics"
TRIAL2_GENERATOR = (
    REPO_ROOT
    / "runs_for_record_trial_2"
    / "diagrams"
    / "generate_token_metric_diagrams.py"
)
CORE_GENERATOR = Path(__file__).resolve().parent / "generate_trial_3_diagrams.py"

BACKENDS = (
    "claude-sonnet",
    "claude-opus",
    "gpt-5",
    "gpt-oss-20b",
    "qwen3-30b-abliterated",
    "whiterabbitneo-v3-7b",
)
BACKEND_LABELS = {
    "claude-sonnet": "Claude Sonnet",
    "claude-opus": "Claude Opus",
    "gpt-5": "GPT-5",
    "gpt-oss-20b": "GPT-OSS 20B",
    "qwen3-30b-abliterated": "Qwen3 Abliterated",
    "whiterabbitneo-v3-7b": "WhiteRabbitNeo 7B",
}
TARGETS = (
    "ret2win-baseline",
    "cgc-cromu-00004",
    "cgc-eagle-00005",
    "cgc-nrfin-00056",
    "broncoctf2026-proper-pwning",
    "ropbench-synth-ex005",
    "ropbench-synth-ex002",
    "ropbench-synth-ex020",
    "ropbench-synth-ex101",
)
TARGET_LABELS = {
    "ret2win-baseline": "ret2win",
    "cgc-cromu-00004": "CROMU",
    "cgc-eagle-00005": "EAGLE",
    "cgc-nrfin-00056": "NRFIN",
    "broncoctf2026-proper-pwning": "BroncoCTF",
    "ropbench-synth-ex005": "ex005",
    "ropbench-synth-ex002": "ex002",
    "ropbench-synth-ex020": "ex020",
    "ropbench-synth-ex101": "ex101",
}
STRATEGIES = ("template_backward", "recon_first")
STRATEGY_LABELS = {
    "template_backward": "Template backward",
    "recon_first": "Recon first",
}

NAVY = "#172554"
BLUE = "#2563eb"
TEAL = "#0f766e"
GREEN = "#16a34a"
ORANGE = "#f59e0b"
RED = "#dc2626"
PURPLE = "#7c3aed"
SLATE = "#64748b"
LIGHT = "#e2e8f0"
MAXIMUM = 1_100_000
SOFT_CAP = 1_000_000


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


trial2 = load_module("trial2_token_metrics_shared", TRIAL2_GENERATOR)
core = load_module("trial3_core_for_token_metrics", CORE_GENERATOR)
TRIAL2_BASE_SVG = trial2.base_svg


def load_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with tarfile.open(ARCHIVE, "r:gz") as archive:
        for member in archive:
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
    assert len(records) == 146
    assert sum(record["outcome"] == "success" for record in records) == 43
    assert all(
        r["tokens"]["prompt"] + r["tokens"]["completion"] == r["tokens"]["total"]
        for r in records
    )
    return records


def termination(record: dict[str, Any]) -> str:
    if record["outcome"] == "success":
        return "success"
    if record["outcome"] == "safeguard_refusal":
        return "safeguard_refusal"
    return str(record.get("failure_mode") or "other")


def base_svg(title: str, subtitle: str, height: int, body: list[str]) -> str:
    return TRIAL2_BASE_SVG(
        title,
        subtitle,
        height,
        body,
        source="Source: Trial 3 finalized record.json metadata (n=146)",
    )


def write_svg(name: str, content: str) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT / name
    path.write_text(content, encoding="utf-8")
    core.render_png(path)


def vertical_axis(x0: float, y0: float, width: float, height: float) -> list[str]:
    body: list[str] = []
    for index in range(6):
        value = MAXIMUM * index / 5
        y = y0 + height * (1 - value / MAXIMUM)
        body.extend(
            [
                f'<line x1="{x0}" y1="{y:.1f}" x2="{x0+width}" y2="{y:.1f}" stroke="#e2e8f0"/>',
                f'<text class="axis" x="{x0-12}" y="{y+5:.1f}" text-anchor="end">{trial2.format_tokens(value)}</text>',
            ]
        )
    cap_y = y0 + height * (1 - SOFT_CAP / MAXIMUM)
    body.extend(
        [
            f'<line x1="{x0}" y1="{cap_y:.1f}" x2="{x0+width}" y2="{cap_y:.1f}" stroke="{RED}" stroke-width="2" stroke-dasharray="8 7"/>',
            f'<text class="axis" x="{x0+width-4}" y="{cap_y-8:.1f}" text-anchor="end">soft cap: 1.0M</text>',
        ]
    )
    return body


def termination_distribution(records: list[dict[str, Any]]) -> str:
    categories = [
        ("success", "Success"),
        ("wall_clock", "Wall-clock"),
        ("iteration_cap", "Iteration cap"),
        ("token_budget", "Token budget"),
        ("safeguard_refusal", "Safeguard refusal"),
    ]
    colors = {
        "success": GREEN,
        "wall_clock": ORANGE,
        "iteration_cap": TEAL,
        "token_budget": RED,
        "safeguard_refusal": PURPLE,
    }
    x0, y0, plot_width, plot_height = 150, 190, 1380, 570
    body = vertical_axis(x0, y0, plot_width, plot_height)
    spacing = plot_width / len(categories)
    for index, (key, label) in enumerate(categories):
        subset = [record for record in records if termination(record) == key]
        values = [record["tokens"]["total"] for record in subset]
        centre = x0 + spacing * (index + 0.5)
        q1 = trial2.percentile(values, 0.25)
        median = statistics.median(values)
        q3 = trial2.percentile(values, 0.75)
        scale_y = lambda value: y0 + plot_height * (
            1 - min(value, MAXIMUM) / MAXIMUM
        )
        body.extend(
            [
                f'<line x1="{centre}" y1="{scale_y(min(values)):.1f}" x2="{centre}" y2="{scale_y(max(values)):.1f}" stroke="{SLATE}" stroke-width="3"/>',
                f'<rect x="{centre-52}" y="{scale_y(q3):.1f}" width="104" height="{max(2,scale_y(q1)-scale_y(q3)):.1f}" rx="8" fill="#dbeafe" stroke="{BLUE}" stroke-width="3"/>',
                f'<line x1="{centre-52}" y1="{scale_y(median):.1f}" x2="{centre+52}" y2="{scale_y(median):.1f}" stroke="{NAVY}" stroke-width="5"/>',
            ]
        )
        for record in subset:
            x = centre + trial2.stable_jitter(record["run_id"], 63)
            y = scale_y(record["tokens"]["total"])
            body.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{colors[key]}" fill-opacity="0.70"/>'
            )
        body.extend(
            [
                f'<text class="label" x="{centre}" y="805" text-anchor="middle">{label}</text>',
                f'<text class="small" x="{centre}" y="831" text-anchor="middle">n={len(values)} · median {trial2.format_tokens(median)}</text>',
            ]
        )
    return base_svg(
        "Total-token distribution by termination mode",
        "Individual finalized records with median and interquartile range",
        890,
        body,
    )


def horizontal_distribution(
    records: list[dict[str, Any]],
    dimension: str,
    values: tuple[str, ...],
    labels: dict[str, str],
    title: str,
    subtitle: str,
) -> str:
    x0, plot_width = 370, 1090
    top, row_height = 205, 105 if len(values) > 3 else 150
    body = [
        f'<rect x="900" y="125" width="18" height="18" fill="{GREEN}"/><text class="legend" x="928" y="140">success</text>',
        f'<rect x="1055" y="125" width="18" height="18" fill="{RED}"/><text class="legend" x="1083" y="140">nonsuccess</text>',
    ]
    for tick in range(6):
        x = x0 + plot_width * tick / 5
        body.extend(
            [
                f'<line x1="{x}" y1="170" x2="{x}" y2="{top+len(values)*row_height-30}" stroke="#e2e8f0"/>',
                f'<text class="axis" x="{x}" y="160" text-anchor="middle">{trial2.format_tokens(MAXIMUM*tick/5)}</text>',
            ]
        )
    cap_x = x0 + plot_width * SOFT_CAP / MAXIMUM
    body.append(
        f'<line x1="{cap_x}" y1="170" x2="{cap_x}" y2="{top+len(values)*row_height-30}" stroke="{RED}" stroke-width="2" stroke-dasharray="8 7"/>'
    )
    for row, value in enumerate(values):
        subset = [r for r in records if r[dimension] == value]
        totals = [r["tokens"]["total"] for r in subset]
        q1 = trial2.percentile(totals, 0.25)
        median = statistics.median(totals)
        q3 = trial2.percentile(totals, 0.75)
        y = top + row * row_height
        scale = lambda token: x0 + plot_width * min(token, MAXIMUM) / MAXIMUM
        body.extend(
            [
                f'<text class="label" x="60" y="{y+7}">{escape(labels[value])}</text>',
                f'<line x1="{scale(min(totals)):.1f}" y1="{y}" x2="{scale(max(totals)):.1f}" y2="{y}" stroke="{SLATE}" stroke-width="4"/>',
                f'<rect x="{scale(q1):.1f}" y="{y-18}" width="{max(2,scale(q3)-scale(q1)):.1f}" height="36" rx="7" fill="#dbeafe" stroke="{BLUE}" stroke-width="3"/>',
                f'<line x1="{scale(median):.1f}" y1="{y-23}" x2="{scale(median):.1f}" y2="{y+23}" stroke="{NAVY}" stroke-width="5"/>',
            ]
        )
        for record in subset:
            color = GREEN if record["outcome"] == "success" else RED
            body.append(
                f'<circle cx="{scale(record["tokens"]["total"]):.1f}" cy="{y+trial2.stable_jitter(record["run_id"],13):.1f}" r="5" fill="{color}" fill-opacity="0.74"/>'
            )
        body.append(
            f'<text class="small" x="60" y="{y+31}">n={len(subset)} · median {trial2.format_tokens(median)}</text>'
        )
    return base_svg(
        title,
        subtitle,
        top + len(values) * row_height + 25,
        body,
    )


def backend_target_heatmap(records: list[dict[str, Any]]) -> str:
    left, top, cell_w, cell_h = 335, 225, 134, 90
    body: list[str] = []
    for col, target in enumerate(TARGETS):
        lines = textwrap.wrap(TARGET_LABELS[target], width=11)
        for line_index, line in enumerate(lines):
            body.append(
                f'<text class="axis" x="{left+col*cell_w+(cell_w-6)/2}" y="{183+line_index*17}" text-anchor="middle">{escape(line)}</text>'
            )
    medians = []
    for model in BACKENDS:
        for target in TARGETS:
            subset = [
                r
                for r in records
                if r["backend_handle"] == model and r["binary_id"] == target
            ]
            if subset:
                medians.append(statistics.median(r["tokens"]["total"] for r in subset))
    maximum = max(medians)
    for row, model in enumerate(BACKENDS):
        y = top + row * cell_h
        body.append(
            f'<text class="label" x="60" y="{y+47}">{escape(BACKEND_LABELS[model])}</text>'
        )
        for col, target in enumerate(TARGETS):
            x = left + col * cell_w
            subset = [
                r
                for r in records
                if r["backend_handle"] == model and r["binary_id"] == target
            ]
            if not subset:
                body.append(
                    f'<rect x="{x}" y="{y}" width="{cell_w-6}" height="{cell_h-10}" rx="8" fill="{LIGHT}"/>'
                )
                continue
            median = statistics.median(r["tokens"]["total"] for r in subset)
            ratio = median / maximum
            red = round(241 + (220 - 241) * ratio)
            green = round(245 + (38 - 245) * ratio)
            blue = round(249 + (38 - 249) * ratio)
            css = "white" if ratio > 0.5 else "value"
            wins = sum(r["outcome"] == "success" for r in subset)
            body.extend(
                [
                    f'<rect x="{x}" y="{y}" width="{cell_w-6}" height="{cell_h-10}" rx="8" fill="rgb({red},{green},{blue})"/>',
                    f'<text class="{css}" x="{x+(cell_w-6)/2}" y="{y+34}" text-anchor="middle">{trial2.format_tokens(median)}</text>',
                    f'<text class="{css}" x="{x+(cell_w-6)/2}" y="{y+59}" text-anchor="middle">{wins}/{len(subset)}</text>',
                ]
            )
    return base_svg(
        "Median total tokens by backend and target",
        "Cells show median total tokens and observed successes / finalized records",
        825,
        body,
    )


def tokens_vs_iterations(records: list[dict[str, Any]]) -> str:
    x0, y0, width, height = 145, 195, 1360, 570
    body = vertical_axis(x0, y0, width, height)
    colors = {
        "success": GREEN,
        "wall_clock": ORANGE,
        "iteration_cap": TEAL,
        "token_budget": RED,
        "safeguard_refusal": PURPLE,
    }
    for tick in range(6):
        x = x0 + width * tick / 5
        body.extend(
            [
                f'<line x1="{x}" y1="{y0}" x2="{x}" y2="{y0+height}" stroke="#e2e8f0"/>',
                f'<text class="axis" x="{x}" y="{y0+height+27}" text-anchor="middle">{tick*20}</text>',
            ]
        )
    for record in records:
        x = x0 + width * min(record["iterations"], 100) / 100
        y = y0 + height * (
            1 - min(record["tokens"]["total"], MAXIMUM) / MAXIMUM
        )
        body.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="{colors[termination(record)]}" fill-opacity="0.62" stroke="#fff"/>'
        )
    correlation = trial2.pearson(
        [r["iterations"] for r in records],
        [r["tokens"]["total"] for r in records],
    )
    body.extend(
        [
            '<text class="label" x="825" y="825" text-anchor="middle">Iterations</text>',
            f'<rect x="60" y="800" width="430" height="58" rx="11" fill="#e0f2fe"/>',
            f'<text class="value" x="82" y="835">Pearson r = {correlation:.3f} (descriptive)</text>',
        ]
    )
    return base_svg(
        "Total tokens increase strongly with iteration count",
        "Each point is one finalized record; colors represent termination modes",
        910,
        body,
    )


def prompt_completion_composition(records: list[dict[str, Any]]) -> str:
    trial2.BACKENDS = BACKENDS
    trial2.BACKEND_LABELS = BACKEND_LABELS
    original = trial2.base_svg
    trial2.base_svg = base_svg
    try:
        return trial2.prompt_completion_composition(records)
    finally:
        trial2.base_svg = original


def token_yield(records: list[dict[str, Any]]) -> str:
    trial2.BACKENDS = BACKENDS
    trial2.BACKEND_LABELS = BACKEND_LABELS
    original = trial2.base_svg
    trial2.base_svg = base_svg
    try:
        return trial2.token_yield(records)
    finally:
        trial2.base_svg = original


def index_markdown(records: list[dict[str, Any]]) -> str:
    totals = sum(r["tokens"]["total"] for r in records)
    prompts = sum(r["tokens"]["prompt"] for r in records)
    successes = [r for r in records if r["outcome"] == "success"]
    nonsuccesses = [r for r in records if r["outcome"] != "success"]
    correlation = trial2.pearson(
        [r["iterations"] for r in records],
        [r["tokens"]["total"] for r in records],
    )
    return f"""# Trial 3 token-metric diagrams

These figures use only the 146 finalized `record.json` files. No conversations,
traces, exploit source, payloads, target binaries, or submissions are opened.

## Headline token accounting

- Aggregate total tokens: {totals:,}.
- Aggregate prompt tokens: {prompts:,} ({prompts/totals:.1%}).
- Aggregate completion tokens: {totals-prompts:,} ({(totals-prompts)/totals:.1%}).
- Median total tokens for successes: {statistics.median(r["tokens"]["total"] for r in successes):,.0f}.
- Median total tokens for nonsuccesses: {statistics.median(r["tokens"]["total"] for r in nonsuccesses):,.0f}.
- Pearson correlation between iterations and total tokens: {correlation:.3f}.

High token use must not be interpreted as causing failure. Difficult or stalled
trajectories both run longer and are more likely to reach resource limits.

## Figures

1. ![Tokens by termination](01_tokens_by_termination.png)
2. ![Tokens by backend](02_tokens_by_backend.png)
3. ![Tokens by strategy](03_tokens_by_strategy.png)
4. ![Backend-target heatmap](04_backend_target_token_heatmap.png)
5. ![Prompt-completion composition](05_prompt_completion_composition.png)
6. ![Tokens versus iterations](06_tokens_vs_iterations.png)
7. ![Token expenditure and yield](07_token_expenditure_and_yield.png)

The 1,000,000-token line is a soft/checkpointed threshold. Ten finalized records
exceeded it. Backend and target summaries retain Trial 3's structured local
coverage and should not be read as composition-adjusted model efficiency.

## Reproduction

Run `python3 runs_for_record_trial_3/diagrams/generate_token_metric_diagrams.py`
from the repository root.
"""


def main() -> None:
    records = load_records()
    write_svg("01_tokens_by_termination.svg", termination_distribution(records))
    write_svg(
        "02_tokens_by_backend.svg",
        horizontal_distribution(
            records,
            "backend_handle",
            BACKENDS,
            BACKEND_LABELS,
            "Total-token distribution by backend",
            "Individual finalized records with median and interquartile range",
        ),
    )
    write_svg(
        "03_tokens_by_strategy.svg",
        horizontal_distribution(
            records,
            "prompting_strategy",
            STRATEGIES,
            STRATEGY_LABELS,
            "Total-token distribution by prompting strategy",
            "Unadjusted distributions combine different backend and target mixtures",
        ),
    )
    write_svg(
        "04_backend_target_token_heatmap.svg",
        backend_target_heatmap(records),
    )
    write_svg(
        "05_prompt_completion_composition.svg",
        prompt_completion_composition(records),
    )
    write_svg("06_tokens_vs_iterations.svg", tokens_vs_iterations(records))
    write_svg("07_token_expenditure_and_yield.svg", token_yield(records))
    (OUTPUT / "INDEX.md").write_text(index_markdown(records), encoding="utf-8")


if __name__ == "__main__":
    main()
