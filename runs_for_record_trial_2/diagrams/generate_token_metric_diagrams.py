"""Generate token-metric diagrams for the Trial 2 runs for record.

The generator reads only finalized record.json metadata. It does not open
conversation logs, exploit source, payloads, target binaries, or trace files.
"""

from __future__ import annotations

import collections
import hashlib
from html import escape
import json
import math
from pathlib import Path
import statistics
from typing import Any, Callable


TRIAL_DIR = Path(__file__).resolve().parent.parent
RUNS_DIR = TRIAL_DIR / "runs"
OUTPUT_DIR = Path(__file__).resolve().parent / "token_metrics"

WIDTH = 1600
NAVY = "#172554"
BLUE = "#2563eb"
TEAL = "#0f766e"
GREEN = "#16a34a"
ORANGE = "#f59e0b"
RED = "#dc2626"
PURPLE = "#7c3aed"
PINK = "#db2777"
SLATE = "#64748b"
LIGHT = "#e2e8f0"
INK = "#1e293b"

BACKENDS = (
    "claude-sonnet",
    "gpt-5",
    "gpt-oss-20b",
    "qwen3-coder-30b",
    "whiterabbitneo-v3-7b",
    "qwen3-30b-abliterated",
)
BACKEND_LABELS = {
    "claude-sonnet": "Claude Sonnet",
    "gpt-5": "GPT-5",
    "gpt-oss-20b": "GPT-OSS 20B",
    "qwen3-coder-30b": "Qwen3 Coder",
    "whiterabbitneo-v3-7b": "WhiteRabbitNeo",
    "qwen3-30b-abliterated": "Qwen3 Abliterated",
}
TARGETS = (
    "ret2win-baseline",
    "cgc-cadet-00001",
    "broncoctf2026-proper-pwning",
    "ropbench-synth-ex005",
)
TARGET_LABELS = {
    "ret2win-baseline": "ret2win",
    "cgc-cadet-00001": "CGC CADET",
    "broncoctf2026-proper-pwning": "BroncoCTF",
    "ropbench-synth-ex005": "ROPBench ex005",
}
STRATEGIES = ("zero_shot", "chain_of_thought", "react")
STRATEGY_LABELS = {
    "zero_shot": "Zero-shot",
    "chain_of_thought": "Chain of thought",
    "react": "ReAct",
}
TERMINATION_COLORS = {
    "success": GREEN,
    "token_budget": RED,
    "wall_clock": ORANGE,
    "truncated": PURPLE,
}


def load_records() -> list[dict[str, Any]]:
    records = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(RUNS_DIR.glob("*/record.json"))
    ]
    assert len(records) == 92
    assert sum(record["outcome"] == "success" for record in records) == 34
    return records


def termination(record: dict[str, Any]) -> str:
    return "success" if record["outcome"] == "success" else record["failure_mode"]


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = fraction * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def stable_jitter(identifier: str, amplitude: float) -> float:
    digest = hashlib.sha256(identifier.encode("utf-8")).digest()
    unit = int.from_bytes(digest[:4], "big") / (2**32 - 1)
    return (unit * 2 - 1) * amplitude


def format_tokens(value: float) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    return f"{value / 1_000:.0f}k"


def base_svg(
    title: str,
    subtitle: str,
    height: int,
    body: list[str],
    source: str = "Source: Trial 2 finalized record.json metadata (n=92)",
) -> str:
    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" viewBox="0 0 {WIDTH} {height}" role="img">',
            f"<title>{escape(title)}</title>",
            """<style>
  .title { font: 700 34px system-ui, sans-serif; fill: #172554; }
  .sub { font: 17px system-ui, sans-serif; fill: #475569; }
  .label { font: 650 17px system-ui, sans-serif; fill: #1e293b; }
  .small { font: 15px system-ui, sans-serif; fill: #64748b; }
  .value { font: 700 15px system-ui, sans-serif; fill: #172554; }
  .axis { font: 14px system-ui, sans-serif; fill: #64748b; }
  .legend { font: 15px system-ui, sans-serif; fill: #334155; }
  .white { font: 700 15px system-ui, sans-serif; fill: #fff; }
  .source { font: 14px system-ui, sans-serif; fill: #64748b; }
</style>""",
            f'<rect width="{WIDTH}" height="{height}" fill="#f8fafc"/>',
            f'<text class="title" x="60" y="58">{escape(title)}</text>',
            f'<text class="sub" x="60" y="103">{escape(subtitle)}</text>',
            *body,
            f'<text class="source" x="60" y="{height - 22}">{escape(source)}</text>',
            "</svg>",
            "",
        ]
    )


def write_svg(name: str, content: str) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / name).write_text(content, encoding="utf-8")


def vertical_axis(
    *,
    x0: float,
    y0: float,
    plot_width: float,
    plot_height: float,
    maximum: float = 650_000,
) -> list[str]:
    body = []
    for index in range(6):
        value = maximum * index / 5
        y = y0 + plot_height * (1 - value / maximum)
        body.extend(
            [
                f'<line x1="{x0}" y1="{y:.1f}" x2="{x0 + plot_width}" y2="{y:.1f}" stroke="#e2e8f0"/>',
                f'<text class="axis" x="{x0 - 12}" y="{y + 5:.1f}" text-anchor="end">{format_tokens(value)}</text>',
            ]
        )
    body.append(
        f'<line x1="{x0}" y1="{y0 + plot_height}" x2="{x0 + plot_width}" y2="{y0 + plot_height}" stroke="#94a3b8"/>'
    )
    budget_y = y0 + plot_height * (1 - 500_000 / maximum)
    body.extend(
        [
            f'<line x1="{x0}" y1="{budget_y:.1f}" x2="{x0 + plot_width}" y2="{budget_y:.1f}" stroke="{RED}" stroke-width="2" stroke-dasharray="8 7"/>',
            f'<text class="axis" x="{x0 + plot_width - 4}" y="{budget_y - 8:.1f}" text-anchor="end">soft cap: 500k</text>',
        ]
    )
    return body


def termination_distribution(records: list[dict[str, Any]]) -> str:
    categories = (
        ("success", "Success"),
        ("token_budget", "Token budget"),
        ("wall_clock", "Wall-clock"),
        ("truncated", "Truncated"),
    )
    x0, y0, plot_width, plot_height = 150, 190, 1380, 520
    body = vertical_axis(
        x0=x0, y0=y0, plot_width=plot_width, plot_height=plot_height
    )
    spacing = plot_width / len(categories)
    for index, (key, label) in enumerate(categories):
        subset = [record for record in records if termination(record) == key]
        values = [record["tokens"]["total"] for record in subset]
        centre = x0 + spacing * (index + 0.5)
        q1, median, q3 = (
            percentile(values, 0.25),
            percentile(values, 0.5),
            percentile(values, 0.75),
        )
        scale_y = lambda value: y0 + plot_height * (1 - min(value, 650_000) / 650_000)
        body.extend(
            [
                f'<line x1="{centre}" y1="{scale_y(min(values)):.1f}" x2="{centre}" y2="{scale_y(max(values)):.1f}" stroke="{SLATE}" stroke-width="3"/>',
                f'<rect x="{centre - 62}" y="{scale_y(q3):.1f}" width="124" height="{scale_y(q1) - scale_y(q3):.1f}" rx="8" fill="#dbeafe" stroke="{BLUE}" stroke-width="3"/>',
                f'<line x1="{centre - 62}" y1="{scale_y(median):.1f}" x2="{centre + 62}" y2="{scale_y(median):.1f}" stroke="{NAVY}" stroke-width="5"/>',
            ]
        )
        for record in subset:
            x = centre + stable_jitter(record["run_id"], 82)
            y = scale_y(record["tokens"]["total"])
            body.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{TERMINATION_COLORS[key]}" fill-opacity="0.72"/>'
            )
        body.extend(
            [
                f'<text class="label" x="{centre}" y="752" text-anchor="middle">{label}</text>',
                f'<text class="small" x="{centre}" y="778" text-anchor="middle">n={len(values)} · median {format_tokens(median)}</text>',
            ]
        )
    return base_svg(
        "Total-token distribution by termination mode",
        "Individual runs with median and interquartile range; totals may exceed the soft cap during a final iteration",
        835,
        body,
    )


def horizontal_distribution(
    records: list[dict[str, Any]],
    *,
    dimension: str,
    values: tuple[str, ...],
    labels: dict[str, str],
    title: str,
    subtitle: str,
    filename: str,
) -> None:
    x0, plot_width = 370, 1090
    top, row_height = 205, 100 if len(values) > 3 else 155
    body = [
        f'<rect x="860" y="125" width="18" height="18" rx="3" fill="{GREEN}"/><text class="legend" x="888" y="140">success</text>',
        f'<rect x="1010" y="125" width="18" height="18" rx="3" fill="{RED}"/><text class="legend" x="1038" y="140">failure</text>',
    ]
    for tick in range(6):
        x = x0 + plot_width * tick / 5
        body.extend(
            [
                f'<line x1="{x}" y1="170" x2="{x}" y2="{top + len(values) * row_height - 30}" stroke="#e2e8f0"/>',
                f'<text class="axis" x="{x}" y="160" text-anchor="middle">{tick * 130}k</text>',
            ]
        )
    budget_x = x0 + plot_width * 500_000 / 650_000
    body.extend(
        [
            f'<line x1="{budget_x:.1f}" y1="170" x2="{budget_x:.1f}" y2="{top + len(values) * row_height - 30}" stroke="{RED}" stroke-width="2" stroke-dasharray="8 7"/>',
            f'<text class="axis" x="{budget_x - 8:.1f}" y="184" text-anchor="end">500k budget</text>',
        ]
    )
    for row, value in enumerate(values):
        subset = [record for record in records if record[dimension] == value]
        totals = [record["tokens"]["total"] for record in subset]
        q1, median, q3 = (
            percentile(totals, 0.25),
            percentile(totals, 0.5),
            percentile(totals, 0.75),
        )
        y = top + row * row_height
        scale_x = lambda token_count: x0 + plot_width * min(token_count, 650_000) / 650_000
        body.extend(
            [
                f'<text class="label" x="60" y="{y + 7}">{escape(labels[value])}</text>',
                f'<line x1="{scale_x(min(totals)):.1f}" y1="{y}" x2="{scale_x(max(totals)):.1f}" y2="{y}" stroke="{SLATE}" stroke-width="4"/>',
                f'<rect x="{scale_x(q1):.1f}" y="{y - 18}" width="{max(2, scale_x(q3) - scale_x(q1)):.1f}" height="36" rx="7" fill="#dbeafe" stroke="{BLUE}" stroke-width="3"/>',
                f'<line x1="{scale_x(median):.1f}" y1="{y - 23}" x2="{scale_x(median):.1f}" y2="{y + 23}" stroke="{NAVY}" stroke-width="5"/>',
            ]
        )
        for record in subset:
            x = scale_x(record["tokens"]["total"])
            point_y = y + stable_jitter(record["run_id"], 13)
            color = GREEN if record["outcome"] == "success" else RED
            body.append(
                f'<circle cx="{x:.1f}" cy="{point_y:.1f}" r="5" fill="{color}" fill-opacity="0.78"/>'
            )
        body.append(
            f'<text class="small" x="60" y="{y + 31}">n={len(subset)} · median {format_tokens(median)}</text>'
        )
    height = top + len(values) * row_height + 25
    write_svg(filename, base_svg(title, subtitle, height, body))


def heat_color(value: float, minimum: float = 100_000, maximum: float = 550_000) -> str:
    ratio = max(0, min(1, (value - minimum) / (maximum - minimum)))
    r = round(37 + (220 - 37) * ratio)
    g = round(99 + (38 - 99) * ratio)
    b = round(235 + (38 - 235) * ratio)
    return f"rgb({r},{g},{b})"


def backend_target_heatmap(records: list[dict[str, Any]]) -> str:
    left, top = 355, 225
    cell_w, cell_h = 285, 90
    body = []
    for column, target in enumerate(TARGETS):
        body.append(
            f'<text class="label" x="{left + column * cell_w + 137}" y="188" text-anchor="middle">{TARGET_LABELS[target]}</text>'
        )
    for row, backend in enumerate(BACKENDS):
        y = top + row * cell_h
        body.append(
            f'<text class="label" x="60" y="{y + 48}">{BACKEND_LABELS[backend]}</text>'
        )
        for column, target in enumerate(TARGETS):
            subset = [
                record
                for record in records
                if record["backend_handle"] == backend
                and record["binary_id"] == target
            ]
            x = left + column * cell_w
            if subset:
                median = statistics.median(
                    record["tokens"]["total"] for record in subset
                )
                successes = sum(record["outcome"] == "success" for record in subset)
                color = heat_color(median)
                body.extend(
                    [
                        f'<rect x="{x}" y="{y}" width="{cell_w - 10}" height="{cell_h - 10}" rx="12" fill="{color}"/>',
                        f'<text class="white" x="{x + 137}" y="{y + 36}" text-anchor="middle">median {format_tokens(median)}</text>',
                        f'<text class="white" x="{x + 137}" y="{y + 62}" text-anchor="middle">{successes}/{len(subset)} successes</text>',
                    ]
                )
            else:
                body.extend(
                    [
                        f'<rect x="{x}" y="{y}" width="{cell_w - 10}" height="{cell_h - 10}" rx="12" fill="#f1f5f9" stroke="#cbd5e1"/>',
                        f'<text class="small" x="{x + 137}" y="{y + 48}" text-anchor="middle">no finalized record</text>',
                    ]
                )
    body.extend(
        [
            '<rect x="1050" y="785" width="18" height="18" rx="3" fill="#2563eb"/><text class="small" x="1078" y="800">≈100k</text>',
            '<rect x="1180" y="785" width="18" height="18" rx="3" fill="#dc2626"/><text class="small" x="1208" y="800">≈550k median total tokens</text>',
        ]
    )
    return base_svg(
        "Median total tokens by backend and target",
        "Cell annotation combines token demand with observed success count; blank cells reflect incomplete finalized coverage",
        850,
        body,
    )


def prompt_completion_composition(records: list[dict[str, Any]]) -> str:
    x0, plot_width = 355, 1080
    body = [
        f'<rect x="970" y="125" width="18" height="18" rx="3" fill="{BLUE}"/><text class="legend" x="998" y="140">prompt</text>',
        f'<rect x="1120" y="125" width="18" height="18" rx="3" fill="{ORANGE}"/><text class="legend" x="1148" y="140">completion</text>',
    ]
    for tick in range(6):
        x = x0 + plot_width * tick / 5
        body.extend(
            [
                f'<line x1="{x}" y1="175" x2="{x}" y2="725" stroke="#e2e8f0"/>',
                f'<text class="axis" x="{x}" y="165" text-anchor="middle">{tick * 20}%</text>',
            ]
        )
    for row, backend in enumerate(BACKENDS):
        subset = [record for record in records if record["backend_handle"] == backend]
        prompt = sum(record["tokens"]["prompt"] for record in subset)
        completion = sum(record["tokens"]["completion"] for record in subset)
        total = prompt + completion
        prompt_share = prompt / total
        y = 215 + row * 90
        prompt_width = plot_width * prompt_share
        body.extend(
            [
                f'<text class="label" x="60" y="{y + 25}">{BACKEND_LABELS[backend]}</text>',
                f'<rect x="{x0}" y="{y}" width="{prompt_width:.1f}" height="42" rx="5" fill="{BLUE}"/>',
                f'<rect x="{x0 + prompt_width:.1f}" y="{y}" width="{plot_width - prompt_width:.1f}" height="42" rx="5" fill="{ORANGE}"/>',
                f'<text class="white" x="{x0 + prompt_width / 2:.1f}" y="{y + 27}" text-anchor="middle">{prompt_share:.1%} prompt</text>',
                f'<text class="small" x="{x0}" y="{y + 66}">{format_tokens(total)} aggregate tokens · {format_tokens(completion)} completion</text>',
            ]
        )
    return base_svg(
        "Prompt tokens dominate every backend’s recorded usage",
        "Aggregate prompt and completion shares; repeated context and tool output are charged as prompt tokens",
        825,
        body,
    )


def pearson(xs: list[float], ys: list[float]) -> float:
    mean_x, mean_y = statistics.mean(xs), statistics.mean(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    denominator = math.sqrt(
        sum((x - mean_x) ** 2 for x in xs)
        * sum((y - mean_y) ** 2 for y in ys)
    )
    return numerator / denominator


def tokens_vs_iterations(records: list[dict[str, Any]]) -> str:
    x0, y0, plot_width, plot_height = 145, 195, 1360, 520
    body = vertical_axis(
        x0=x0, y0=y0, plot_width=plot_width, plot_height=plot_height
    )
    for tick in range(6):
        x = x0 + plot_width * tick / 5
        body.extend(
            [
                f'<line x1="{x}" y1="{y0}" x2="{x}" y2="{y0 + plot_height}" stroke="#e2e8f0"/>',
                f'<text class="axis" x="{x}" y="{y0 + plot_height + 27}" text-anchor="middle">{tick * 20}</text>',
            ]
        )
    for record in records:
        x = x0 + plot_width * min(record["iterations"], 100) / 100
        y = y0 + plot_height * (
            1 - min(record["tokens"]["total"], 650_000) / 650_000
        )
        color = TERMINATION_COLORS[termination(record)]
        body.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="7" fill="{color}" fill-opacity="0.72" stroke="#fff" stroke-width="1.5"/>'
        )

    # Scale a k*n^2 reference to the uncapped observations. Excluding records
    # at or above 490k avoids treating the soft-budget pileup as unconstrained
    # quadratic growth.
    uncapped = [record for record in records if record["tokens"]["total"] < 490_000]
    coefficient = sum(
        record["iterations"] ** 2 * record["tokens"]["total"]
        for record in uncapped
    ) / sum(record["iterations"] ** 4 for record in uncapped)
    curve_points = []
    for iterations in range(0, 101):
        token_count = coefficient * iterations**2
        if token_count > 650_000:
            break
        x = x0 + plot_width * iterations / 100
        y = y0 + plot_height * (1 - token_count / 650_000)
        curve_points.append(f"{x:.1f},{y:.1f}")
    body.append(
        f'<polyline points="{" ".join(curve_points)}" fill="none" stroke="{NAVY}" stroke-width="5" stroke-dasharray="11 8"/>'
    )
    legend = (
        ("success", GREEN),
        ("token budget", RED),
        ("wall-clock", ORANGE),
        ("truncated", PURPLE),
    )
    for index, (label, color) in enumerate(legend):
        x = 500 + index * 205
        body.extend(
            [
                f'<circle cx="{x}" cy="140" r="8" fill="{color}"/>',
                f'<text class="legend" x="{x + 17}" y="145">{label}</text>',
            ]
        )
    body.extend(
        [
            f'<line x1="1320" y1="140" x2="1360" y2="140" stroke="{NAVY}" stroke-width="5" stroke-dasharray="10 7"/>',
            '<text class="legend" x="1372" y="145">O(n²)</text>',
        ]
    )
    correlation = pearson(
        [record["iterations"] for record in records],
        [record["tokens"]["total"] for record in records],
    )
    body.extend(
        [
            '<text class="label" x="825" y="785" text-anchor="middle">Iterations</text>',
            f'<rect x="60" y="752" width="430" height="58" rx="11" fill="#e0f2fe"/>',
            f'<text class="value" x="82" y="786">Pearson r = {correlation:.3f} (descriptive)</text>',
            f'<rect x="1080" y="752" width="425" height="58" rx="11" fill="#ede9fe"/>',
            f'<text class="value" x="1102" y="786">Reference fit: tokens ≈ {coefficient:.0f} × iterations²</text>',
        ]
    )
    return base_svg(
        "Total tokens increase strongly with iteration count",
        "Each point is one finalized run; dashed O(n²) reference is scaled to observations below 490k tokens",
        850,
        body,
    )


def token_yield(records: list[dict[str, Any]]) -> str:
    x0, plot_width = 410, 1000
    maximum = 12_000_000
    body = []
    for tick in range(7):
        x = x0 + plot_width * tick / 6
        value = maximum * tick / 6
        body.extend(
            [
                f'<line x1="{x}" y1="180" x2="{x}" y2="735" stroke="#e2e8f0"/>',
                f'<text class="axis" x="{x}" y="165" text-anchor="middle">{value / 1_000_000:.0f}M</text>',
            ]
        )
    for row, backend in enumerate(BACKENDS):
        subset = [record for record in records if record["backend_handle"] == backend]
        total = sum(record["tokens"]["total"] for record in subset)
        successes = sum(record["outcome"] == "success" for record in subset)
        y = 215 + row * 90
        bar_width = plot_width * total / maximum
        per_success = total / successes if successes else None
        body.extend(
            [
                f'<text class="label" x="60" y="{y + 25}">{BACKEND_LABELS[backend]}</text>',
                f'<rect x="{x0}" y="{y}" width="{bar_width:.1f}" height="42" rx="6" fill="{BLUE}"/>',
                f'<text class="value" x="{x0 + bar_width + 12:.1f}" y="{y + 26}">{total / 1_000_000:.2f}M</text>',
                f'<text class="small" x="{x0}" y="{y + 66}">{successes}/{len(subset)} successes · '
                + (
                    f'{format_tokens(per_success)} aggregate tokens per observed success'
                    if per_success
                    else "no observed success; ratio undefined"
                )
                + "</text>",
            ]
        )
    body.extend(
        [
            '<rect x="60" y="755" width="1420" height="60" rx="11" fill="#fef3c7"/>',
            '<text class="small" x="84" y="791">Aggregate tokens per success is descriptive workload yield, not a model-intrinsic efficiency estimate; backend coverage and task difficulty differ.</text>',
        ]
    )
    return base_svg(
        "Aggregate token expenditure and observed success yield",
        "Total finalized-run tokens by backend, with success counts and aggregate tokens per observed success",
        865,
        body,
    )


def index_markdown(records: list[dict[str, Any]]) -> str:
    totals = sum(record["tokens"]["total"] for record in records)
    prompts = sum(record["tokens"]["prompt"] for record in records)
    successes = [record for record in records if record["outcome"] == "success"]
    failures = [record for record in records if record["outcome"] != "success"]
    return f"""# Trial 2 token-metric diagrams

These figures use only the 92 finalized `record.json` files. The generator does
not read conversation logs, traces, exploit source, payloads, or target
binaries, and it does not execute any submission.

## Headline token accounting

- Aggregate total tokens: {totals:,}.
- Aggregate prompt tokens: {prompts:,} ({prompts / totals:.1%}).
- Aggregate completion tokens: {totals - prompts:,} ({(totals - prompts) / totals:.1%}).
- Median total tokens for successes: {statistics.median(record["tokens"]["total"] for record in successes):,.0f}.
- Median total tokens for failures: {statistics.median(record["tokens"]["total"] for record in failures):,.0f}.
- Pearson correlation between iterations and total tokens: {pearson([record["iterations"] for record in records], [record["tokens"]["total"] for record in records]):.3f}.

The association between high token use and failure must not be interpreted as
showing that tokens cause failure. Hard or stalled trajectories both consume
more iterations and are more likely to exhaust the budget.

## Figures

1. **Termination modes** — successful trajectories generally terminate well
   below the budget, while token-budget failures cluster at and just beyond it.

   ![Total-token distribution by termination mode](01_tokens_by_termination.png)

2. **Backend distributions** — the individual-run overlay exposes within-model
   heterogeneity and budget pileups hidden by a median alone.

   ![Total-token distribution by backend](02_tokens_by_backend.png)

3. **Strategy distributions** — ReAct has the largest unadjusted median, but the
   three distributions overlap substantially and combine different backend and
   target mixtures.

   ![Total-token distribution by prompting strategy](03_tokens_by_strategy.png)

4. **Backend × target heatmap** — median demand and success should be read
   together because a high median may indicate a difficult or unresolved cell.

   ![Median total tokens by backend and target](04_backend_target_token_heatmap.png)

5. **Prompt/completion composition** — prompt tokens dominate every backend,
   consistent with repeated context and tool output rather than unusually long
   model completions being the principal token cost.

   ![Prompt and completion composition](05_prompt_completion_composition.png)

6. **Tokens versus iterations** — total tokens rise strongly with turn count.
   The dashed quadratic reference is a least-squares `k × iterations²` curve
   scaled on observations below 490k tokens; it is illustrative rather than a
   formal complexity estimate. The relationship is partly mechanical because
   accumulated context is reintroduced across iterations.

   ![Total tokens versus iterations](06_tokens_vs_iterations.png)

7. **Aggregate expenditure and yield** — GPT-OSS consumed the most aggregate
   tokens despite only three successes. Ratios are workload-level summaries and
   are undefined for backends with no observed success.

   ![Aggregate token expenditure and success yield](07_token_expenditure_and_yield.png)

## Reproduction

Run `python3 ../generate_token_metric_diagrams.py` from this directory, or run
the generator from the repository root. It creates the editable SVG sources;
the PNG files are rendered counterparts for document use.
"""


def main() -> None:
    records = load_records()
    write_svg(
        "01_tokens_by_termination.svg",
        termination_distribution(records),
    )
    horizontal_distribution(
        records,
        dimension="backend_handle",
        values=BACKENDS,
        labels=BACKEND_LABELS,
        title="Total-token distribution by backend",
        subtitle="Individual finalized runs with median and interquartile range; point color indicates outcome",
        filename="02_tokens_by_backend.svg",
    )
    horizontal_distribution(
        records,
        dimension="prompting_strategy",
        values=STRATEGIES,
        labels=STRATEGY_LABELS,
        title="Total-token distribution by prompting strategy",
        subtitle="Unadjusted distributions combine different backend, target, and finalized-coverage mixtures",
        filename="03_tokens_by_strategy.svg",
    )
    write_svg(
        "04_backend_target_token_heatmap.svg",
        backend_target_heatmap(records),
    )
    write_svg(
        "05_prompt_completion_composition.svg",
        prompt_completion_composition(records),
    )
    write_svg(
        "06_tokens_vs_iterations.svg",
        tokens_vs_iterations(records),
    )
    write_svg(
        "07_token_expenditure_and_yield.svg",
        token_yield(records),
    )
    (OUTPUT_DIR / "INDEX.md").write_text(
        index_markdown(records),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
