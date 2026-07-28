"""Generate two cross-trial token-metric packages.

Outputs are produced for (1) all finalized models and (2) each trial's
configured premium-model class. Only finalized ``runs/*/record.json`` archive
members are opened; no submission artifact, conversation, trace, or binary is
opened or executed.
"""

from __future__ import annotations

import collections
import csv
import hashlib
from html import escape
import math
from pathlib import Path
import statistics
from typing import Any, Callable

from generate_all_trials_diagrams import (
    ARCHIVES,
    BACKEND_LABEL,
    BLUE,
    GREEN,
    LIGHT,
    NAVY,
    ORANGE,
    PREMIUM,
    PURPLE,
    RED,
    SLATE,
    TARGET_LABEL,
    TEAL,
    TRIAL_COLOR,
    backend,
    base_svg,
    load_records,
    render_png,
    success,
    svg_text,
)


ROOT = Path(__file__).resolve().parent
OUTPUT_ROOT = ROOT / "token_metrics"
COHORTS = {
    "all_models": lambda trial, record: True,
    "premium_models": lambda trial, record: backend(record) in PREMIUM[trial],
}
TRIAL_LABEL = {1: "Trial 1", 2: "Trial 2", 3: "Trial 3"}
STRATEGY_LABEL = {
    "zero_shot": "Zero-shot",
    "chain_of_thought": "Chain of thought",
    "react": "ReAct",
    "majorca": "MAJORCA",
    "template_backward": "Template backward",
    "recon_first": "Recon first",
}


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = fraction * (len(ordered) - 1)
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def pearson(xs: list[float], ys: list[float]) -> float:
    xmean, ymean = statistics.mean(xs), statistics.mean(ys)
    numerator = sum((x - xmean) * (y - ymean) for x, y in zip(xs, ys))
    denominator = math.sqrt(
        sum((x - xmean) ** 2 for x in xs) * sum((y - ymean) ** 2 for y in ys)
    )
    return numerator / denominator if denominator else math.nan


def format_tokens(value: float | None) -> str:
    if value is None:
        return "undefined"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    return f"{value / 1_000:.1f}k"


def stable_jitter(identifier: str, amplitude: float) -> float:
    digest = hashlib.sha256(identifier.encode()).digest()
    unit = int.from_bytes(digest[:4], "big") / (2**32 - 1)
    return (unit * 2 - 1) * amplitude


def termination(record: dict[str, Any]) -> str:
    if success(record):
        return "success"
    if record["outcome"] == "safeguard_refusal":
        return "safeguard_refusal"
    return str(record.get("failure_mode") or "other_failure")


def summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    totals = [record["tokens"]["total"] for record in records]
    prompts = [record["tokens"]["prompt"] for record in records]
    completions = [record["tokens"]["completion"] for record in records]
    successes = sum(success(record) for record in records)
    aggregate = sum(totals)
    return {
        "n": len(records),
        "success": successes,
        "prompt_tokens": sum(prompts),
        "completion_tokens": sum(completions),
        "total_tokens": aggregate,
        "prompt_share": sum(prompts) / aggregate if aggregate else None,
        "median_prompt_tokens": statistics.median(prompts),
        "median_completion_tokens": statistics.median(completions),
        "median_total_tokens": statistics.median(totals),
        "mean_total_tokens": statistics.mean(totals),
        "p25_total_tokens": percentile(totals, 0.25),
        "p75_total_tokens": percentile(totals, 0.75),
        "min_total_tokens": min(totals),
        "max_total_tokens": max(totals),
        "tokens_per_success": aggregate / successes if successes else None,
        "iteration_token_correlation": pearson(
            [record["iterations"] for record in records], totals
        )
        if len(records) > 1
        else None,
    }


def grouped_rows(
    records_by_trial: dict[int, list[dict[str, Any]]],
    getter: Callable[[dict[str, Any]], str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for trial, records in records_by_trial.items():
        groups: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
        for record in records:
            groups[getter(record)].append(record)
        for name, subset in sorted(groups.items()):
            rows.append({"trial": trial, "group": name, **summary(subset)})
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_svg(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    render_png(path)


def quantile_body(
    values: list[float],
    *,
    y: float,
    x0: float,
    width: float,
    maximum: float,
    color: str,
) -> list[str]:
    q1 = percentile(values, 0.25)
    med = statistics.median(values)
    q3 = percentile(values, 0.75)
    low, high = min(values), max(values)
    scale = lambda value: x0 + width * min(value, maximum) / maximum
    return [
        f'<line x1="{scale(low):.1f}" y1="{y}" x2="{scale(high):.1f}" y2="{y}" stroke="#94a3b8" stroke-width="3"/>',
        f'<rect x="{scale(q1):.1f}" y="{y-13}" width="{max(2,scale(q3)-scale(q1)):.1f}" height="26" rx="5" fill="{color}" opacity="0.72"/>',
        f'<line x1="{scale(med):.1f}" y1="{y-17}" x2="{scale(med):.1f}" y2="{y+17}" stroke="{NAVY}" stroke-width="4"/>',
    ]


def termination_figure(records_by_trial: dict[int, list[dict[str, Any]]]) -> str:
    maximum = max(
        record["tokens"]["total"]
        for records in records_by_trial.values()
        for record in records
    )
    maximum = math.ceil(maximum / 100_000) * 100_000
    x0, width = 470, 960
    body: list[str] = []
    for tick in range(6):
        x = x0 + width * tick / 5
        body.extend(
            [
                f'<line x1="{x}" y1="165" x2="{x}" y2="1065" stroke="#e2e8f0"/>',
                f'<text class="axis" x="{x}" y="153" text-anchor="middle">{format_tokens(maximum*tick/5)}</text>',
            ]
        )
    y = 200
    colors = {
        "success": GREEN,
        "safeguard_refusal": PURPLE,
        "token_budget": RED,
        "budget_exhausted": RED,
        "wall_clock": ORANGE,
        "truncated": PURPLE,
        "iteration_cap": TEAL,
    }
    for trial in (1, 2, 3):
        groups: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
        for record in records_by_trial[trial]:
            groups[termination(record)].append(record)
        ordered = sorted(
            groups,
            key=lambda name: (
                name != "success",
                -len(groups[name]),
                name,
            ),
        )
        body.append(f'<text class="label" x="60" y="{y+8}">Trial {trial}</text>')
        for name in ordered:
            values = [r["tokens"]["total"] for r in groups[name]]
            body.extend(
                quantile_body(
                    values,
                    y=y,
                    x0=x0,
                    width=width,
                    maximum=maximum,
                    color=colors.get(name, SLATE),
                )
            )
            body.extend(
                [
                    svg_text(name.replace("_", " "), 150, y + 5, "small", width=25),
                    f'<text class="small" x="{x0}" y="{y+28}">n={len(values)} · median {format_tokens(statistics.median(values))}</text>',
                ]
            )
            y += 63
        y += 35
    return base_svg(
        "Total-token distributions by termination mode",
        "Whisker = observed range; box = interquartile range; dark line = median",
        max(1140, int(y + 55)),
        body,
        "Source: finalized record.json token and termination metadata",
    )


def heat_color(value: float, maximum: float) -> str:
    ratio = max(0, min(1, value / maximum))
    red = round(241 + (220 - 241) * ratio)
    green = round(245 + (38 - 245) * ratio)
    blue = round(249 + (38 - 249) * ratio)
    return f"rgb({red},{green},{blue})"


def group_heatmap(
    records_by_trial: dict[int, list[dict[str, Any]]],
    getter: Callable[[dict[str, Any]], str],
    labels: dict[str, str],
    *,
    title: str,
    subtitle: str,
) -> str:
    groups = sorted(
        {
            getter(record)
            for records in records_by_trial.values()
            for record in records
        },
        key=lambda name: labels.get(name, name),
    )
    medians = [
        statistics.median(
            r["tokens"]["total"]
            for r in records_by_trial[trial]
            if getter(r) == name
        )
        for trial in (1, 2, 3)
        for name in groups
        if any(getter(r) == name for r in records_by_trial[trial])
    ]
    maximum = max(medians)
    left, top, cell_w, cell_h = 610, 200, 285, 66
    body: list[str] = []
    for col, trial in enumerate((1, 2, 3)):
        body.append(
            f'<text class="label" x="{left+col*cell_w+(cell_w-10)/2}" y="165" text-anchor="middle">Trial {trial}</text>'
        )
    for row, name in enumerate(groups):
        y = top + row * cell_h
        body.append(svg_text(labels.get(name, name), 60, y + 36, "label", width=32))
        for col, trial in enumerate((1, 2, 3)):
            subset = [r for r in records_by_trial[trial] if getter(r) == name]
            x = left + col * cell_w
            if not subset:
                body.extend(
                    [
                        f'<rect x="{x}" y="{y}" width="{cell_w-10}" height="{cell_h-7}" rx="8" fill="{LIGHT}"/>',
                        f'<text class="small" x="{x+(cell_w-10)/2}" y="{y+36}" text-anchor="middle">not represented</text>',
                    ]
                )
                continue
            value = statistics.median(r["tokens"]["total"] for r in subset)
            color = heat_color(value, maximum)
            css = "white" if value / maximum > 0.52 else "value"
            body.extend(
                [
                    f'<rect x="{x}" y="{y}" width="{cell_w-10}" height="{cell_h-7}" rx="8" fill="{color}"/>',
                    f'<text class="{css}" x="{x+(cell_w-10)/2}" y="{y+27}" text-anchor="middle">{format_tokens(value)}</text>',
                    f'<text class="{css}" x="{x+(cell_w-10)/2}" y="{y+48}" text-anchor="middle">n={len(subset)}</text>',
                ]
            )
    return base_svg(
        title,
        subtitle,
        285 + len(groups) * cell_h,
        body,
        "Source: finalized record.json total-token metadata",
    )


def backend_target_figure(records_by_trial: dict[int, list[dict[str, Any]]]) -> str:
    body: list[str] = []
    top = 165
    for trial in (1, 2, 3):
        records = records_by_trial[trial]
        backends = sorted({backend(r) for r in records}, key=lambda x: BACKEND_LABEL[x])
        targets = sorted(
            {r["binary_id"] for r in records}, key=lambda x: TARGET_LABEL.get(x, x)
        )
        cell_w = min(122, 1140 / len(targets))
        cell_h = 48
        left = 340
        body.append(
            f'<text class="label" x="60" y="{top}">Trial {trial} · median total tokens (successes / n)</text>'
        )
        for col, target in enumerate(targets):
            body.append(
                svg_text(
                    TARGET_LABEL.get(target, target),
                    left + col * cell_w + (cell_w - 4) / 2,
                    top + 38,
                    "axis",
                    width=13,
                    anchor="middle",
                    line_height=16,
                )
            )
        panel_values: list[float] = []
        for model in backends:
            for target in targets:
                subset = [
                    r
                    for r in records
                    if backend(r) == model and r["binary_id"] == target
                ]
                if subset:
                    panel_values.append(
                        statistics.median(r["tokens"]["total"] for r in subset)
                    )
        maximum = max(panel_values)
        row_top = top + 78
        for row, model in enumerate(backends):
            y = row_top + row * cell_h
            body.append(
                svg_text(BACKEND_LABEL[model], 60, y + 29, "small", width=28)
            )
            for col, target in enumerate(targets):
                x = left + col * cell_w
                subset = [
                    r
                    for r in records
                    if backend(r) == model and r["binary_id"] == target
                ]
                if not subset:
                    body.append(
                        f'<rect x="{x}" y="{y}" width="{cell_w-4}" height="{cell_h-4}" rx="5" fill="{LIGHT}"/>'
                    )
                    continue
                med = statistics.median(r["tokens"]["total"] for r in subset)
                wins = sum(success(r) for r in subset)
                color = heat_color(med, maximum)
                css = "white" if med / maximum > 0.52 else "value"
                body.extend(
                    [
                        f'<rect x="{x}" y="{y}" width="{cell_w-4}" height="{cell_h-4}" rx="5" fill="{color}"/>',
                        f'<text class="{css}" x="{x+(cell_w-4)/2}" y="{y+20}" text-anchor="middle">{format_tokens(med)}</text>',
                        f'<text class="{css}" x="{x+(cell_w-4)/2}" y="{y+38}" text-anchor="middle">{wins}/{len(subset)}</text>',
                    ]
                )
        top = row_top + len(backends) * cell_h + 65
    return base_svg(
        "Backend × target token heatmaps",
        "Each trial is independently color-scaled; cells show median total tokens and successes / finalized n",
        int(top + 50),
        body,
        "Source: finalized record.json token and outcome metadata; blank cells are unrealized",
    )


def composition_figure(records_by_trial: dict[int, list[dict[str, Any]]]) -> str:
    body: list[str] = [
        f'<rect x="1000" y="120" width="18" height="18" fill="{BLUE}"/><text class="legend" x="1028" y="135">Prompt</text>',
        f'<rect x="1160" y="120" width="18" height="18" fill="{ORANGE}"/><text class="legend" x="1188" y="135">Completion</text>',
    ]
    y = 180
    left, width = 430, 990
    for trial in (1, 2, 3):
        body.append(f'<text class="label" x="60" y="{y+25}">Trial {trial}</text>')
        models = sorted(
            {backend(r) for r in records_by_trial[trial]}, key=lambda x: BACKEND_LABEL[x]
        )
        for model in models:
            subset = [r for r in records_by_trial[trial] if backend(r) == model]
            prompt = sum(r["tokens"]["prompt"] for r in subset)
            completion = sum(r["tokens"]["completion"] for r in subset)
            total = prompt + completion
            body.extend(
                [
                    svg_text(BACKEND_LABEL[model], 150, y + 22, "small", width=25),
                    f'<rect x="{left}" y="{y}" width="{width*prompt/total:.1f}" height="30" fill="{BLUE}"/>',
                    f'<rect x="{left+width*prompt/total:.1f}" y="{y}" width="{width*completion/total:.1f}" height="30" fill="{ORANGE}"/>',
                    f'<text class="small" x="{left}" y="{y+52}">{prompt/total:.1%} prompt · {format_tokens(total)} total</text>',
                ]
            )
            y += 67
        y += 35
    return base_svg(
        "Prompt and completion token composition",
        "Aggregate shares by backend within trial",
        int(y + 50),
        body,
        "Source: finalized record.json prompt and completion token metadata",
    )


def scatter_figure(records_by_trial: dict[int, list[dict[str, Any]]]) -> str:
    all_records = [r for records in records_by_trial.values() for r in records]
    maximum = math.ceil(max(r["tokens"]["total"] for r in all_records) / 100_000) * 100_000
    x0, y0, width, height = 170, 180, 1240, 650
    body: list[str] = []
    for tick in range(6):
        x = x0 + width * tick / 5
        y = y0 + height * (1 - tick / 5)
        body.extend(
            [
                f'<line x1="{x}" y1="{y0}" x2="{x}" y2="{y0+height}" stroke="#e2e8f0"/>',
                f'<text class="axis" x="{x}" y="{y0+height+26}" text-anchor="middle">{tick*20}</text>',
                f'<line x1="{x0}" y1="{y}" x2="{x0+width}" y2="{y}" stroke="#e2e8f0"/>',
                f'<text class="axis" x="{x0-12}" y="{y+5}" text-anchor="end">{format_tokens(maximum*tick/5)}</text>',
            ]
        )
    for trial in (1, 2, 3):
        for record in records_by_trial[trial]:
            x = x0 + width * min(record["iterations"], 100) / 100
            y = y0 + height * (1 - min(record["tokens"]["total"], maximum) / maximum)
            body.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.2" fill="{TRIAL_COLOR[trial]}" opacity="0.38"/>'
            )
    for i, trial in enumerate((1, 2, 3)):
        x = 900 + i * 170
        body.extend(
            [
                f'<circle cx="{x}" cy="130" r="7" fill="{TRIAL_COLOR[trial]}"/>',
                f'<text class="legend" x="{x+15}" y="135">Trial {trial}</text>',
            ]
        )
    body.extend(
        [
            f'<text class="label" x="{x0+width/2}" y="{y0+height+62}" text-anchor="middle">Iterations</text>',
            f'<text class="label" x="38" y="{y0+height/2}" transform="rotate(-90 38 {y0+height/2})" text-anchor="middle">Total tokens</text>',
        ]
    )
    correlations = " · ".join(
        f"T{trial} r={pearson([r['iterations'] for r in records_by_trial[trial]], [r['tokens']['total'] for r in records_by_trial[trial]]):.3f}"
        for trial in (1, 2, 3)
    )
    body.append(f'<text class="small" x="{x0}" y="930">{correlations}</text>')
    return base_svg(
        "Total tokens versus iterations",
        "Each point is one finalized record; colors identify trials",
        1000,
        body,
        "Source: finalized record.json token and iteration metadata; correlations are descriptive",
    )


def premium_termination_class(record: dict[str, Any]) -> str:
    if success(record):
        return "success"
    failure_mode = str(record.get("failure_mode") or "")
    if failure_mode in {"token_budget", "budget_exhausted"}:
        return "token budget"
    if failure_mode == "wall_clock":
        return "wall-clock"
    if failure_mode == "truncated":
        return "truncated"
    return "refusal / other"


def premium_marker(
    trial: int,
    x: float,
    y: float,
    color: str,
    *,
    size: float = 5.4,
    opacity: float = 0.62,
) -> str:
    common = (
        f'fill="{color}" fill-opacity="{opacity}" stroke="#fff" '
        'stroke-width="1.15"'
    )
    if trial == 1:
        return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{size:.1f}" {common}/>'
    if trial == 2:
        return (
            f'<rect x="{x-size:.1f}" y="{y-size:.1f}" '
            f'width="{2*size:.1f}" height="{2*size:.1f}" rx="1.2" {common}/>'
        )
    points = (
        f"{x:.1f},{y-size-1:.1f} "
        f"{x-size-0.8:.1f},{y+size:.1f} "
        f"{x+size+0.8:.1f},{y+size:.1f}"
    )
    return f'<polygon points="{points}" {common}/>'


def premium_scatter_figure(
    records_by_trial: dict[int, list[dict[str, Any]]]
) -> str:
    """Premium-only scatter with independent color and shape encodings."""
    x0, y0, width, height = 155, 220, 1350, 590
    max_iterations = 80
    max_tokens = 650_000
    colors = {
        "success": GREEN,
        "token budget": RED,
        "wall-clock": ORANGE,
        "truncated": PURPLE,
        "refusal / other": SLATE,
    }
    body: list[str] = []

    # Five labels per axis: x = 0,20,40,60,80 and y = 0..650k.
    for tick in range(5):
        x = x0 + width * tick / 4
        y = y0 + height * (1 - tick / 4)
        x_value = max_iterations * tick / 4
        y_value = max_tokens * tick / 4
        body.extend(
            [
                f'<line x1="{x}" y1="{y0}" x2="{x}" y2="{y0+height}" stroke="#e2e8f0"/>',
                f'<text class="axis" x="{x}" y="{y0+height+27}" text-anchor="middle">{x_value:.0f}</text>',
                f'<line x1="{x0}" y1="{y}" x2="{x0+width}" y2="{y}" stroke="#e2e8f0"/>',
                f'<text class="axis" x="{x0-12}" y="{y+5}" text-anchor="end">{format_tokens(y_value)}</text>',
            ]
        )

    # Outcome color legend follows the Trial 2 palette exactly for the four
    # shared terminal classes. Slate preserves refusal/other records.
    legend_x = 280
    for index, (label, color) in enumerate(colors.items()):
        x = legend_x + index * 230
        body.extend(
            [
                f'<circle cx="{x}" cy="132" r="7" fill="{color}"/>',
                f'<text class="legend" x="{x+15}" y="137">{label}</text>',
            ]
        )

    # Trial shape legend is deliberately monochrome so shape and color remain
    # separable visual channels.
    shape_items = ((1, "Trial 1 · circle"), (2, "Trial 2 · square"), (3, "Trial 3 · triangle"))
    for index, (trial, label) in enumerate(shape_items):
        x = 460 + index * 220
        body.extend(
            [
                premium_marker(trial, x, 172, NAVY, size=6.2, opacity=1.0),
                f'<text class="legend" x="{x+16}" y="177">{label}</text>',
            ]
        )
    body.extend(
        [
            f'<line x1="1165" y1="172" x2="1210" y2="172" stroke="{NAVY}" stroke-width="4" stroke-dasharray="10 7"/>',
            '<text class="legend" x="1222" y="177">fitted O(n²)</text>',
        ]
    )

    for trial in (1, 2, 3):
        for record in records_by_trial[trial]:
            x = x0 + width * min(record["iterations"], max_iterations) / max_iterations
            y = y0 + height * (
                1 - min(record["tokens"]["total"], max_tokens) / max_tokens
            )
            body.append(
                premium_marker(
                    trial,
                    x,
                    y,
                    colors[premium_termination_class(record)],
                )
            )

    # Fit k*n² to non-refusal observations below 90% of the trial-specific
    # token envelope. This is an illustrative reference, not a complexity law.
    trial_caps = {1: 200_000, 2: 500_000, 3: 1_000_000}
    fit_records = [
        record
        for trial in (1, 2, 3)
        for record in records_by_trial[trial]
        if premium_termination_class(record) != "refusal / other"
        and record["tokens"]["total"] < 0.9 * trial_caps[trial]
        and record["iterations"] > 0
    ]
    coefficient = sum(
        record["iterations"] ** 2 * record["tokens"]["total"]
        for record in fit_records
    ) / sum(record["iterations"] ** 4 for record in fit_records)
    curve: list[str] = []
    for iterations in range(max_iterations + 1):
        token_count = coefficient * iterations**2
        if token_count > max_tokens:
            break
        x = x0 + width * iterations / max_iterations
        y = y0 + height * (1 - token_count / max_tokens)
        curve.append(f"{x:.1f},{y:.1f}")
    body.append(
        f'<polyline points="{" ".join(curve)}" fill="none" stroke="{NAVY}" '
        'stroke-width="4.5" stroke-dasharray="11 8"/>'
    )

    all_records = [
        record for records in records_by_trial.values() for record in records
    ]
    correlation = pearson(
        [record["iterations"] for record in all_records],
        [record["tokens"]["total"] for record in all_records],
    )
    body.extend(
        [
            f'<text class="label" x="{x0+width/2}" y="{y0+height+65}" text-anchor="middle">Iterations</text>',
            f'<text class="label" x="38" y="{y0+height/2}" transform="rotate(-90 38 {y0+height/2})" text-anchor="middle">Total tokens</text>',
            '<rect x="60" y="872" width="470" height="55" rx="11" fill="#e0f2fe"/>',
            f'<text class="value" x="82" y="906">Pearson r = {correlation:.3f} (descriptive)</text>',
            '<rect x="1000" y="872" width="500" height="55" rx="11" fill="#ede9fe"/>',
            f'<text class="value" x="1022" y="906">Reference: tokens ≈ {coefficient:.0f} × iterations²</text>',
        ]
    )
    return base_svg(
        "Premium-model tokens versus iterations",
        "Color encodes termination; marker shape encodes trial; slate retains refusal/other outcomes",
        970,
        body,
        "Source: finalized premium-model record.json metadata; O(n²) curve is an illustrative least-squares reference",
    )


def yield_figure(records_by_trial: dict[int, list[dict[str, Any]]]) -> str:
    stats = {trial: summary(records) for trial, records in records_by_trial.items()}
    aggregate_max = max(value["total_tokens"] for value in stats.values())
    yield_max = max(
        value["tokens_per_success"] or 0 for value in stats.values()
    )
    body: list[str] = []
    panels = [
        ("Aggregate finalized tokens", "total_tokens", aggregate_max, format_tokens),
        ("Tokens per observed success", "tokens_per_success", yield_max, format_tokens),
    ]
    for panel, (title, key, maximum, formatter) in enumerate(panels):
        left = 80 + panel * 760
        body.extend(
            [
                f'<rect x="{left-20}" y="165" width="700" height="470" rx="14" fill="#fff" stroke="#cbd5e1" stroke-width="2"/>',
                f'<text class="label" x="{left}" y="205">{title}</text>',
            ]
        )
        for i, trial in enumerate((1, 2, 3)):
            value = stats[trial][key]
            y = 260 + i * 110
            body.append(f'<text class="label" x="{left}" y="{y+24}">T{trial}</text>')
            if value is None:
                body.append(
                    f'<text class="small" x="{left+90}" y="{y+24}">undefined (no observed success)</text>'
                )
                continue
            bar = 480 * value / maximum
            body.extend(
                [
                    f'<rect x="{left+70}" y="{y}" width="{bar:.1f}" height="34" rx="5" fill="{TRIAL_COLOR[trial]}"/>',
                    f'<text class="value" x="{left+80+bar:.1f}" y="{y+23}">{formatter(value)}</text>',
                ]
            )
    return base_svg(
        "Aggregate token expenditure and observed yield",
        "Tokens per success is a workload-level ratio, not a model-intrinsic efficiency estimate",
        700,
        body,
        "Source: finalized record.json tokens and outcomes",
    )


def table_svg(title: str, headers: list[str], rows: list[list[str]]) -> str:
    width = 1480
    col_width = width / len(headers)
    row_h = 52
    top = 175
    height = top + row_h * (len(rows) + 1) + 80
    body: list[str] = [
        f'<rect x="60" y="{top}" width="{width}" height="{row_h}" rx="10" fill="{NAVY}"/>'
    ]
    for col, header in enumerate(headers):
        body.append(
            svg_text(
                header,
                60 + col * col_width + col_width / 2,
                top + 31,
                "white",
                width=max(10, int(col_width / 11)),
                anchor="middle",
                line_height=16,
            )
        )
    for row_index, row in enumerate(rows):
        y = top + row_h * (row_index + 1)
        body.append(
            f'<rect x="60" y="{y}" width="{width}" height="{row_h}" fill="{"#fff" if row_index%2==0 else "#f1f5f9"}"/>'
        )
        for col, value in enumerate(row):
            body.append(
                svg_text(
                    value,
                    60 + col * col_width + col_width / 2,
                    y + 31,
                    "small" if col else "label",
                    width=max(10, int(col_width / 11)),
                    anchor="middle",
                    line_height=16,
                )
            )
    return base_svg(
        title,
        "Publication-ready table derived from finalized record metadata",
        int(height),
        body,
        "Source: generated cohort token-metric tables",
    )


def table_outputs(
    output: Path,
    records_by_trial: dict[int, list[dict[str, Any]]],
    headline: list[dict[str, Any]],
    backend_rows: list[dict[str, Any]],
    strategy_rows: list[dict[str, Any]],
) -> None:
    table_dir = output / "table_diagrams"
    tables: list[tuple[str, str, list[str], list[list[str]]]] = []
    tables.append(
        (
            "01_headline_token_accounting",
            "Headline token accounting by trial",
            ["Trial", "n", "Prompt", "Completion", "Total", "Prompt share", "Median", "Iter-token r"],
            [
                [
                    f"Trial {r['trial']}",
                    f"{r['n']:,}",
                    format_tokens(r["prompt_tokens"]),
                    format_tokens(r["completion_tokens"]),
                    format_tokens(r["total_tokens"]),
                    f"{r['prompt_share']:.1%}",
                    format_tokens(r["median_total_tokens"]),
                    f"{r['iteration_token_correlation']:.3f}",
                ]
                for r in headline
            ],
        )
    )
    outcome_rows = grouped_rows(records_by_trial, termination)
    tables.append(
        (
            "02_termination_token_summary",
            "Termination-mode token summary",
            ["Trial", "Termination", "n", "Median", "IQR", "Aggregate"],
            [
                [
                    f"T{r['trial']}",
                    r["group"].replace("_", " "),
                    str(r["n"]),
                    format_tokens(r["median_total_tokens"]),
                    f"{format_tokens(r['p25_total_tokens'])}–{format_tokens(r['p75_total_tokens'])}",
                    format_tokens(r["total_tokens"]),
                ]
                for r in outcome_rows
            ],
        )
    )
    tables.append(
        (
            "03_backend_token_summary",
            "Backend token summary",
            ["Trial", "Backend", "n", "Success", "Median", "IQR", "Tokens / success"],
            [
                [
                    f"T{r['trial']}",
                    BACKEND_LABEL[r["group"]],
                    str(r["n"]),
                    str(r["success"]),
                    format_tokens(r["median_total_tokens"]),
                    f"{format_tokens(r['p25_total_tokens'])}–{format_tokens(r['p75_total_tokens'])}",
                    format_tokens(r["tokens_per_success"]),
                ]
                for r in backend_rows
            ],
        )
    )
    tables.append(
        (
            "04_strategy_token_summary",
            "Prompting-strategy token summary",
            ["Trial", "Strategy", "n", "Success", "Median", "IQR", "Tokens / success"],
            [
                [
                    f"T{r['trial']}",
                    STRATEGY_LABEL.get(r["group"], r["group"]),
                    str(r["n"]),
                    str(r["success"]),
                    format_tokens(r["median_total_tokens"]),
                    f"{format_tokens(r['p25_total_tokens'])}–{format_tokens(r['p75_total_tokens'])}",
                    format_tokens(r["tokens_per_success"]),
                ]
                for r in strategy_rows
            ],
        )
    )
    tables.append(
        (
            "05_success_nonsuccess_tokens",
            "Success and nonsuccess token profiles",
            ["Trial", "Outcome", "n", "Median prompt", "Median completion", "Median total", "Aggregate"],
            [
                [
                    f"T{trial}",
                    label,
                    str(len(subset)),
                    format_tokens(statistics.median(r["tokens"]["prompt"] for r in subset)),
                    format_tokens(statistics.median(r["tokens"]["completion"] for r in subset)),
                    format_tokens(statistics.median(r["tokens"]["total"] for r in subset)),
                    format_tokens(sum(r["tokens"]["total"] for r in subset)),
                ]
                for trial, records in records_by_trial.items()
                for label, subset in (
                    ("Success", [r for r in records if success(r)]),
                    ("Nonsuccess", [r for r in records if not success(r)]),
                )
                if subset
            ],
        )
    )
    for stem, title, headers, rows in tables:
        write_svg(table_dir / f"{stem}.svg", table_svg(title, headers, rows))
    index = [
        "# Token-metric table diagrams",
        "",
        "Each table is available as PNG and editable SVG.",
        "",
    ]
    for stem, title, _, _ in tables:
        index.append(
            f"- [{title}]({stem}.png) ([SVG]({stem}.svg))"
        )
    (table_dir / "INDEX.md").write_text("\n".join(index) + "\n", encoding="utf-8")


def markdown_tables(
    output: Path,
    headline: list[dict[str, Any]],
    backend_rows: list[dict[str, Any]],
    strategy_rows: list[dict[str, Any]],
) -> None:
    lines = [
        "# Token metric tables",
        "",
        "## Headline accounting",
        "",
        "| Trial | n | Prompt tokens | Completion tokens | Total tokens | Prompt share | Median total | Iteration-token r |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in headline:
        lines.append(
            f"| Trial {r['trial']} | {r['n']:,} | {r['prompt_tokens']:,} | {r['completion_tokens']:,} | {r['total_tokens']:,} | {r['prompt_share']:.1%} | {r['median_total_tokens']:,.1f} | {r['iteration_token_correlation']:.3f} |"
        )
    lines.extend(
        [
            "",
            "## Backend metrics",
            "",
            "| Trial | Backend | n | Success | Median total | IQR | Aggregate tokens | Tokens/success |",
            "|---|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for r in backend_rows:
        yield_value = (
            f"{r['tokens_per_success']:,.1f}"
            if r["tokens_per_success"] is not None
            else "undefined"
        )
        lines.append(
            f"| {r['trial']} | {BACKEND_LABEL[r['group']]} | {r['n']} | {r['success']} | {r['median_total_tokens']:,.1f} | {r['p25_total_tokens']:,.1f}–{r['p75_total_tokens']:,.1f} | {r['total_tokens']:,} | {yield_value} |"
        )
    lines.extend(
        [
            "",
            "## Strategy metrics",
            "",
            "| Trial | Strategy | n | Success | Median total | IQR | Aggregate tokens | Tokens/success |",
            "|---|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for r in strategy_rows:
        yield_value = (
            f"{r['tokens_per_success']:,.1f}"
            if r["tokens_per_success"] is not None
            else "undefined"
        )
        lines.append(
            f"| {r['trial']} | {STRATEGY_LABEL.get(r['group'],r['group'])} | {r['n']} | {r['success']} | {r['median_total_tokens']:,.1f} | {r['p25_total_tokens']:,.1f}–{r['p75_total_tokens']:,.1f} | {r['total_tokens']:,} | {yield_value} |"
        )
    (output / "TOKEN_TABLES.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def package_index(
    output: Path,
    cohort_name: str,
    headline: list[dict[str, Any]],
) -> None:
    label = "all finalized models" if cohort_name == "all_models" else "trial-specific premium models"
    lines = [
        f"# Cross-trial token metrics — {label}",
        "",
        "Only finalized `record.json` metadata is used. The trials have different",
        "model, target, prompting, tool, and resource compositions; these are",
        "descriptive workload metrics rather than isolated efficiency effects.",
        "",
        "## Headline accounting",
        "",
    ]
    for row in headline:
        lines.append(
            f"- Trial {row['trial']}: n={row['n']:,}; total={row['total_tokens']:,}; "
            f"prompt share={row['prompt_share']:.1%}; median={row['median_total_tokens']:,.0f}; "
            f"iteration-token r={row['iteration_token_correlation']:.3f}."
        )
    lines.extend(
        [
            "",
            "## Figures",
            "",
            "1. ![Tokens by termination](01_tokens_by_termination.png)",
            "2. ![Tokens by backend](02_tokens_by_backend.png)",
            "3. ![Tokens by strategy](03_tokens_by_strategy.png)",
            "4. ![Backend target token heatmap](04_backend_target_token_heatmap.png)",
            "5. ![Prompt completion composition](05_prompt_completion_composition.png)",
            "6. ![Tokens versus iterations](06_tokens_vs_iterations.png)",
            "7. ![Token expenditure and yield](07_token_expenditure_and_yield.png)",
            "",
            *(
                [
                    "Figure 6 uses Trial 1 circles, Trial 2 squares, and Trial 3",
                    "triangles. Success, token-budget, wall-clock, and truncated",
                    "records retain the Trial 2 color palette; refusal/other records",
                    "are slate so that every premium run remains represented. The",
                    "dashed quadratic curve is an illustrative least-squares reference.",
                    "",
                ]
                if cohort_name == "premium_models"
                else []
            ),
            "## Tables",
            "",
            "- [Markdown tables](TOKEN_TABLES.md)",
            "- [Rendered table diagrams](table_diagrams/INDEX.md)",
            "- CSV tables are in [`tables/`](tables/).",
            "",
            "## Reproduction",
            "",
            "Run `python3 compare_all_trials/generate_token_metric_packages.py` from",
            "the repository root.",
        ]
    )
    (output / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def generate_package(
    cohort_name: str,
    all_records: dict[int, list[dict[str, Any]]],
) -> None:
    predicate = COHORTS[cohort_name]
    records_by_trial = {
        trial: [record for record in records if predicate(trial, record)]
        for trial, records in all_records.items()
    }
    output = OUTPUT_ROOT / cohort_name
    output.mkdir(parents=True, exist_ok=True)
    headline = [
        {"trial": trial, **summary(records)}
        for trial, records in records_by_trial.items()
    ]
    backend_rows = grouped_rows(records_by_trial, backend)
    strategy_rows = grouped_rows(
        records_by_trial, lambda record: record["prompting_strategy"]
    )
    target_rows = grouped_rows(records_by_trial, lambda record: record["binary_id"])
    termination_rows = grouped_rows(records_by_trial, termination)
    backend_target_rows: list[dict[str, Any]] = []
    for trial, records in records_by_trial.items():
        groups: dict[tuple[str, str], list[dict[str, Any]]] = collections.defaultdict(list)
        for record in records:
            groups[(backend(record), record["binary_id"])].append(record)
        for (model, target), subset in sorted(groups.items()):
            backend_target_rows.append(
                {
                    "trial": trial,
                    "backend": model,
                    "target": target,
                    **summary(subset),
                }
            )
    write_csv(output / "tables" / "01_headline_by_trial.csv", headline)
    write_csv(output / "tables" / "02_termination_by_trial.csv", termination_rows)
    write_csv(output / "tables" / "03_backend_by_trial.csv", backend_rows)
    write_csv(output / "tables" / "04_strategy_by_trial.csv", strategy_rows)
    write_csv(output / "tables" / "05_target_by_trial.csv", target_rows)
    write_csv(output / "tables" / "06_backend_target_by_trial.csv", backend_target_rows)
    markdown_tables(output, headline, backend_rows, strategy_rows)
    table_outputs(output, records_by_trial, headline, backend_rows, strategy_rows)
    write_svg(
        output / "01_tokens_by_termination.svg",
        termination_figure(records_by_trial),
    )
    write_svg(
        output / "02_tokens_by_backend.svg",
        group_heatmap(
            records_by_trial,
            backend,
            BACKEND_LABEL,
            title="Median total tokens by backend",
            subtitle="Within-trial finalized records; grey denotes no representation",
        ),
    )
    write_svg(
        output / "03_tokens_by_strategy.svg",
        group_heatmap(
            records_by_trial,
            lambda record: record["prompting_strategy"],
            STRATEGY_LABEL,
            title="Median total tokens by prompting strategy",
            subtitle="Trial-specific prompt arms; no strategy is shared across all three trials",
        ),
    )
    write_svg(
        output / "04_backend_target_token_heatmap.svg",
        backend_target_figure(records_by_trial),
    )
    write_svg(
        output / "05_prompt_completion_composition.svg",
        composition_figure(records_by_trial),
    )
    write_svg(
        output / "06_tokens_vs_iterations.svg",
        (
            premium_scatter_figure(records_by_trial)
            if cohort_name == "premium_models"
            else scatter_figure(records_by_trial)
        ),
    )
    write_svg(
        output / "07_token_expenditure_and_yield.svg",
        yield_figure(records_by_trial),
    )
    package_index(output, cohort_name, headline)


def main() -> None:
    all_records = {trial: load_records(path) for trial, path in ARCHIVES.items()}
    assert {trial: len(records) for trial, records in all_records.items()} == {
        1: 1755,
        2: 92,
        3: 146,
    }
    assert all(
        record["tokens"]["prompt"] + record["tokens"]["completion"]
        == record["tokens"]["total"]
        for records in all_records.values()
        for record in records
    )
    for cohort_name in COHORTS:
        generate_package(cohort_name, all_records)
    premium_counts = {
        trial: sum(backend(record) in PREMIUM[trial] for record in records)
        for trial, records in all_records.items()
    }
    assert premium_counts == {1: 553, 2: 46, 3: 108}
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    (OUTPUT_ROOT / "INDEX.md").write_text(
        """# Cross-trial token-metric packages

Two parallel packages use identical metrics, tables, and figure designs:

- [All finalized models](all_models/INDEX.md)
- [Trial-specific premium models](premium_models/INDEX.md)

Each package contains seven diagrams in PNG and editable SVG, six CSV tables,
a Markdown table collection, and five publication-ready table diagrams.

The generator reads only finalized `record.json` metadata and does not open or
execute submitted artifacts.
""",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
