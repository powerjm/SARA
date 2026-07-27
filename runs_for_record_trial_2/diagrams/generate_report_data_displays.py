"""Create a meaningful graph or structured data display for every report table."""

from __future__ import annotations

from html import escape
import importlib.util
import math
from pathlib import Path
import re
import sys
import textwrap
from typing import Callable


HERE = Path(__file__).resolve().parent
TABLE_GENERATOR = HERE / "generate_report_table_diagrams.py"
OUTPUT_ROOT = HERE / "report_charts"
WIDTH = 1600

NAVY = "#172554"
BLUE = "#2563eb"
TEAL = "#0f766e"
PURPLE = "#7c3aed"
GREEN = "#16a34a"
ORANGE = "#f59e0b"
RED = "#dc2626"
SLATE = "#94a3b8"
LIGHT = "#e2e8f0"
INK = "#1e293b"
MUTED = "#64748b"
TIER_COLORS = (LIGHT, BLUE, ORANGE, GREEN)


def load_table_generator():
    spec = importlib.util.spec_from_file_location("trial2_table_generator", TABLE_GENERATOR)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {TABLE_GENERATOR}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


tables_module = load_table_generator()


def number(value: str) -> float:
    text = value.replace(",", "").replace("$", "").strip().lower()
    multiplier = 1000 if text.endswith("k") else 1
    text = text.rstrip("k").rstrip("s").rstrip("%").strip()
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(match.group()) * multiplier if match else 0.0


def fraction(value: str) -> tuple[float, float]:
    match = re.search(r"(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)", value)
    if not match:
        return (0.0, 0.0)
    return (float(match.group(1)), float(match.group(2)))


def percent(value: str) -> float:
    return number(value)


def interval(value: str) -> tuple[float, float]:
    values = [float(item) for item in re.findall(r"\d+(?:\.\d+)?", value)]
    if len(values) < 2:
        return (0.0, 0.0)
    return values[0], values[1]


def tiers(value: str) -> list[float]:
    return [number(item) for item in re.split(r"\s*/\s*", value)]


def short_label(value: str) -> str:
    replacements = {
        "claude-sonnet-4-6": "Claude Sonnet",
        "claude-sonnet": "Claude Sonnet",
        "gpt-5": "GPT-5",
        "gpt-oss-20b": "GPT-OSS 20B",
        "qwen3-coder-30b": "Qwen3 Coder 30B",
        "whiterabbitneo-v3-7b": "WhiteRabbitNeo 7B",
        "qwen3-30b-abliterated": "Qwen3 Abliterated",
        "ropbench-synth-ex005 (tier-0 synthetic)": "ROPBench ex005",
        "ret2win-baseline (tier −1 floor)": "ret2win baseline",
        "broncoctf2026-proper-pwning (low-leakage CTF)": "BroncoCTF 2026",
        "cgc-cadet-00001 (high-leakage, two-stage)": "CGC CADET 00001",
        "broncoctf2026-proper-pwning": "BroncoCTF 2026",
        "ropbench-synth-ex005": "ROPBench ex005",
        "ret2win-baseline": "ret2win baseline",
        "cgc-cadet-00001": "CGC CADET 00001",
        "chain_of_thought": "Chain of thought",
        "zero_shot": "Zero-shot",
        "react": "ReAct",
        "chain-of-thought": "Chain of thought",
        "zero-shot": "Zero-shot",
    }
    return replacements.get(value, value)


def text_lines(
    value: str,
    x: float,
    y: float,
    css: str,
    *,
    width: int = 32,
    anchor: str = "start",
    line_height: int = 22,
) -> str:
    lines = textwrap.wrap(value, width=width, break_long_words=False) or [value]
    spans = [
        f'<tspan x="{x:.1f}" dy="{0 if index == 0 else line_height}">{escape(line)}</tspan>'
        for index, line in enumerate(lines)
    ]
    return (
        f'<text class="{css}" x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}">'
        + "".join(spans)
        + "</text>"
    )


def base_svg(title: str, subtitle: str, height: int, body: list[str]) -> str:
    title_lines = textwrap.wrap(title, width=74, break_long_words=False) or [title]
    body_offset = 42 * (len(title_lines) - 1)
    final_height = height + body_offset
    title_y = 56
    title_block = [
        f'<text class="title" x="60" y="{title_y + index * 42}">{escape(line)}</text>'
        for index, line in enumerate(title_lines)
    ]
    subtitle_y = title_y + len(title_lines) * 42 + 5
    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{final_height}" viewBox="0 0 {WIDTH} {final_height}" role="img">',
            f"<title>{escape(title)}</title>",
            """<style>
    .title { font: 700 34px system-ui, sans-serif; fill: #172554; }
    .sub { font: 17px system-ui, sans-serif; fill: #475569; }
    .label { font: 650 17px system-ui, sans-serif; fill: #1e293b; }
    .small { font: 15px system-ui, sans-serif; fill: #64748b; }
    .value { font: 700 15px system-ui, sans-serif; fill: #172554; }
    .legend { font: 15px system-ui, sans-serif; fill: #334155; }
    .axis { font: 14px system-ui, sans-serif; fill: #64748b; }
    .cell { font: 650 16px system-ui, sans-serif; fill: #172554; }
    .white { font: 700 15px system-ui, sans-serif; fill: #fff; }
  </style>""",
            f'<rect width="{WIDTH}" height="{final_height}" fill="#f8fafc"/>',
            *title_block,
            f'<text class="sub" x="60" y="{subtitle_y}">{escape(subtitle)}</text>',
            f'<g transform="translate(0,{body_offset})">',
            *body,
            "</g>",
            "</svg>",
            "",
        ]
    )


def legend(items: list[tuple[str, str]], y: int = 132, x: int = 700) -> list[str]:
    parts = []
    cursor = x
    for label, color in items:
        parts.append(
            f'<rect x="{cursor}" y="{y - 15}" width="18" height="18" rx="3" fill="{color}"/>'
        )
        parts.append(f'<text class="legend" x="{cursor + 27}" y="{y}">{escape(label)}</text>')
        cursor += 48 + len(label) * 9
    return parts


def horizontal_bars(
    title: str,
    subtitle: str,
    labels: list[str],
    series: list[tuple[str, list[float], str]],
    *,
    maximum: float | None = None,
    suffix: str = "",
    value_labels: list[list[str]] | None = None,
    note: str = "",
) -> str:
    maximum = maximum or max(max(values) for _, values, _ in series) or 1
    row_gap = 78 if len(series) <= 2 else 92
    chart_top = 205
    height = chart_top + len(labels) * row_gap + (95 if note else 55)
    plot_x, plot_width = 400, 1080
    body = legend([(name, color) for name, _, color in series], y=137, x=650)
    for tick_index in range(5):
        value = maximum * tick_index / 4
        x = plot_x + plot_width * tick_index / 4
        body.extend(
            [
                f'<line x1="{x:.1f}" y1="175" x2="{x:.1f}" y2="{chart_top + len(labels) * row_gap - 28}" stroke="#e2e8f0"/>',
                f'<text class="axis" x="{x:.1f}" y="166" text-anchor="middle">{value:g}{suffix}</text>',
            ]
        )
    group_height = 42
    bar_height = min(22, group_height / len(series))
    for row_index, label in enumerate(labels):
        center_y = chart_top + row_index * row_gap
        body.append(text_lines(short_label(label), 60, center_y + 3, "label", width=31))
        start_y = center_y - group_height / 2
        for series_index, (_, values, color) in enumerate(series):
            value = values[row_index]
            y = start_y + series_index * bar_height
            width = plot_width * value / maximum
            body.append(
                f'<rect x="{plot_x}" y="{y:.1f}" width="{width:.1f}" height="{bar_height - 2:.1f}" rx="4" fill="{color}"/>'
            )
            display = (
                value_labels[series_index][row_index]
                if value_labels
                else f"{value:g}{suffix}"
            )
            body.append(
                f'<text class="value" x="{min(plot_x + width + 10, 1490):.1f}" y="{y + bar_height - 6:.1f}">{escape(display)}</text>'
            )
    if note:
        note_y = chart_top + len(labels) * row_gap + 12
        body.extend(
            [
                f'<rect x="60" y="{note_y}" width="1420" height="54" rx="12" fill="#e0f2fe"/>',
                f'<text class="small" x="84" y="{note_y + 33}">{escape(note)}</text>',
            ]
        )
    return base_svg(title, subtitle, height, body)


def stacked_bars(
    title: str,
    subtitle: str,
    labels: list[str],
    values: list[list[float]],
    segment_names: list[str],
    colors: list[str],
    *,
    normalized: bool = True,
    note: str = "",
) -> str:
    chart_top, row_gap = 210, 74
    height = chart_top + len(labels) * row_gap + (95 if note else 55)
    plot_x, plot_width = 400, 1080
    body = legend(list(zip(segment_names, colors)), y=137, x=560)
    for tick in range(5):
        x = plot_x + plot_width * tick / 4
        body.extend(
            [
                f'<line x1="{x}" y1="175" x2="{x}" y2="{chart_top + len(labels) * row_gap - 30}" stroke="#e2e8f0"/>',
                f'<text class="axis" x="{x}" y="166" text-anchor="middle">{tick * 25 if normalized else ""}{"%" if normalized else ""}</text>',
            ]
        )
    for row_index, (label, row) in enumerate(zip(labels, values)):
        y = chart_top + row_index * row_gap - 20
        total = sum(row) or 1
        cursor = plot_x
        for value, color in zip(row, colors):
            fraction_value = value / total if normalized else value / max(sum(v) for v in values)
            width = plot_width * fraction_value
            if width:
                body.append(
                    f'<rect x="{cursor:.1f}" y="{y}" width="{width:.1f}" height="38" rx="3" fill="{color}"/>'
                )
                if width > 42:
                    body.append(
                        f'<text class="{"white" if color not in (LIGHT,) else "value"}" x="{cursor + width / 2:.1f}" y="{y + 25}" text-anchor="middle">{value:g}</text>'
                    )
            cursor += width
        body.append(text_lines(short_label(label), 60, y + 25, "label", width=31))
    if note:
        note_y = chart_top + len(labels) * row_gap + 6
        body.extend(
            [
                f'<rect x="60" y="{note_y}" width="1420" height="54" rx="12" fill="#e0f2fe"/>',
                f'<text class="small" x="84" y="{note_y + 33}">{escape(note)}</text>',
            ]
        )
    return base_svg(title, subtitle, height, body)


def heatmap(
    title: str,
    subtitle: str,
    row_labels: list[str],
    col_labels: list[str],
    matrix: list[list[float]],
    annotations: list[list[str]],
) -> str:
    left, top = 355, 205
    cell_width = 265 if len(col_labels) <= 4 else 210
    cell_height = 68
    height = top + len(row_labels) * cell_height + 75
    body = []
    for column, label in enumerate(col_labels):
        x = left + column * cell_width + cell_width / 2
        body.append(text_lines(short_label(label), x, top - 28, "label", width=21, anchor="middle"))
    for row_index, label in enumerate(row_labels):
        y = top + row_index * cell_height
        body.append(text_lines(short_label(label), 60, y + 38, "label", width=29))
        for column_index, value in enumerate(matrix[row_index]):
            x = left + column_index * cell_width
            intensity = max(0.0, min(1.0, value / 100))
            red = round(241 + (22 - 241) * intensity)
            green = round(245 + (163 - 245) * intensity)
            blue = round(249 + (74 - 249) * intensity)
            color = f"rgb({red},{green},{blue})"
            body.append(
                f'<rect x="{x}" y="{y}" width="{cell_width - 8}" height="{cell_height - 8}" rx="9" fill="{color}"/>'
            )
            css = "white" if intensity > 0.48 else "cell"
            body.append(
                f'<text class="{css}" x="{x + (cell_width - 8) / 2}" y="{y + 28}" text-anchor="middle">{value:.1f}%</text>'
            )
            body.append(
                f'<text class="{"white" if intensity > 0.48 else "small"}" x="{x + (cell_width - 8) / 2}" y="{y + 50}" text-anchor="middle">{escape(annotations[row_index][column_index])}</text>'
            )
    body.extend(
        [
            f'<rect x="60" y="{height - 54}" width="18" height="18" rx="3" fill="#f1f5f9"/>',
            f'<text class="small" x="88" y="{height - 39}">0%</text>',
            f'<rect x="135" y="{height - 54}" width="18" height="18" rx="3" fill="#16a34a"/>',
            f'<text class="small" x="163" y="{height - 39}">100% success</text>',
        ]
    )
    return base_svg(title, subtitle, height, body)


def forest_plot(
    title: str,
    subtitle: str,
    labels: list[str],
    rates: list[float],
    intervals: list[tuple[float, float]],
    *,
    tier_values: list[list[float]] | None = None,
) -> str:
    top, row_gap = 210, 72
    height = top + len(labels) * row_gap + 60
    plot_x = 390
    plot_width = 700 if tier_values else 1030
    body = []
    for tick in range(5):
        x = plot_x + plot_width * tick / 4
        body.extend(
            [
                f'<line x1="{x}" y1="170" x2="{x}" y2="{top + len(labels) * row_gap - 25}" stroke="#e2e8f0"/>',
                f'<text class="axis" x="{x}" y="161" text-anchor="middle">{tick * 25}%</text>',
            ]
        )
    if tier_values:
        body.extend(legend(list(zip(("none", "ran", "control", "marker"), TIER_COLORS)), y=142, x=1020))
    for index, label in enumerate(labels):
        y = top + index * row_gap
        lo, hi = intervals[index]
        lo_x = plot_x + plot_width * lo / 100
        hi_x = plot_x + plot_width * hi / 100
        rate_x = plot_x + plot_width * rates[index] / 100
        body.extend(
            [
                text_lines(short_label(label), 60, y + 4, "label", width=30),
                f'<line x1="{lo_x:.1f}" y1="{y}" x2="{hi_x:.1f}" y2="{y}" stroke="{BLUE}" stroke-width="5"/>',
                f'<circle cx="{rate_x:.1f}" cy="{y}" r="9" fill="{NAVY}"/>',
                f'<text class="value" x="{min(hi_x + 12, plot_x + plot_width + 10):.1f}" y="{y + 5}">{rates[index]:g}%</text>',
            ]
        )
        if tier_values:
            x = 1130
            total = sum(tier_values[index]) or 1
            for value, color in zip(tier_values[index], TIER_COLORS):
                width = 350 * value / total
                if width:
                    body.append(
                        f'<rect x="{x:.1f}" y="{y - 14}" width="{width:.1f}" height="28" fill="{color}"/>'
                    )
                x += width
    return base_svg(title, subtitle, height, body)


def small_multiples(
    title: str,
    subtitle: str,
    metrics: list[str],
    first_name: str,
    first: list[float],
    second_name: str,
    second: list[float],
    displays: list[tuple[str, str]],
    note: str = "",
) -> str:
    top, row_gap = 205, 84
    height = top + len(metrics) * row_gap + (95 if note else 55)
    plot_x, plot_width = 500, 900
    body = legend([(first_name, GREEN), (second_name, RED)], y=137, x=920)
    for index, metric in enumerate(metrics):
        y = top + index * row_gap
        maximum = max(first[index], second[index], 1)
        widths = (plot_width * first[index] / maximum, plot_width * second[index] / maximum)
        body.extend(
            [
                text_lines(metric, 60, y + 14, "label", width=36),
                f'<rect x="{plot_x}" y="{y - 13}" width="{widths[0]:.1f}" height="22" rx="4" fill="{GREEN}"/>',
                f'<rect x="{plot_x}" y="{y + 17}" width="{widths[1]:.1f}" height="22" rx="4" fill="{RED}"/>',
                f'<text class="value" x="{plot_x + widths[0] + 10:.1f}" y="{y + 3}">{escape(displays[index][0])}</text>',
                f'<text class="value" x="{plot_x + widths[1] + 10:.1f}" y="{y + 34}">{escape(displays[index][1])}</text>',
            ]
        )
    if note:
        y = top + len(metrics) * row_gap + 5
        body.extend(
            [
                f'<rect x="60" y="{y}" width="1420" height="54" rx="12" fill="#fef3c7"/>',
                f'<text class="small" x="84" y="{y + 33}">{escape(note)}</text>',
            ]
        )
    return base_svg(title, subtitle, height, body)


def pvalue_plot(title: str, subtitle: str, labels: list[str], values: list[float]) -> str:
    top, row_gap = 210, 70
    height = top + len(labels) * row_gap + 60
    x0, width = 500, 920
    body = []
    for tick in (0, 0.05, 0.25, 0.5, 0.75, 1.0):
        x = x0 + width * tick
        color = RED if tick == 0.05 else LIGHT
        body.extend(
            [
                f'<line x1="{x:.1f}" y1="170" x2="{x:.1f}" y2="{top + len(labels) * row_gap - 25}" stroke="{color}" stroke-width="{3 if tick == 0.05 else 1}"/>',
                f'<text class="axis" x="{x:.1f}" y="160" text-anchor="middle">{tick:g}</text>',
            ]
        )
    for index, (label, value) in enumerate(zip(labels, values)):
        y = top + index * row_gap
        x = x0 + width * value
        body.extend(
            [
                text_lines(label, 60, y + 4, "label", width=42),
                f'<line x1="{x0}" y1="{y}" x2="{x:.1f}" y2="{y}" stroke="{SLATE}" stroke-width="4"/>',
                f'<circle cx="{x:.1f}" cy="{y}" r="10" fill="{PURPLE}"/>',
                f'<text class="value" x="{x + 15:.1f}" y="{y + 5}">p={value:.3f}</text>',
            ]
        )
    body.append('<text class="small" x="548" y="190">α = 0.05</text>')
    return base_svg(title, subtitle, height, body)


def partial_timeline(title: str, subtitle: str, rows: list[list[str]]) -> str:
    height = 590
    stages = {"initialization": 0, "enumeration": 1, "validation": 2}
    x_positions = (520, 890, 1260)
    body = [
        '<line x1="520" y1="190" x2="1260" y2="190" stroke="#cbd5e1" stroke-width="5"/>',
    ]
    for stage, x in zip(("initialization", "enumeration", "validation"), x_positions):
        body.extend(
            [
                f'<circle cx="{x}" cy="190" r="12" fill="{NAVY}"/>',
                f'<text class="label" x="{x}" y="160" text-anchor="middle">{stage}</text>',
            ]
        )
    for index, row in enumerate(rows):
        y = 255 + index * 76
        state = row[1].split()[0].lower()
        x = x_positions[stages.get(state, 0)]
        tokens = int(number(row[2]))
        radius = 9 + 13 * math.sqrt(tokens / 250000) if tokens else 9
        terminal_stage = x == x_positions[-1]
        usage_x = x - radius - 12 if terminal_stage else x + radius + 12
        usage_anchor = "end" if terminal_stage else "start"
        body.extend(
            [
                text_lines(row[0], 60, y + 4, "label", width=42),
                f'<line x1="500" y1="{y}" x2="1280" y2="{y}" stroke="#e2e8f0"/>',
                f'<circle cx="{x}" cy="{y}" r="{radius:.1f}" fill="{ORANGE}" opacity="0.9"/>',
                f'<text class="value" x="{usage_x:.1f}" y="{y + 5}" text-anchor="{usage_anchor}">{escape(row[2])}</text>',
                text_lines(row[3], 1310, y - 7, "small", width=25),
            ]
        )
    body.append('<text class="small" x="520" y="565">Circle area scales with recorded token usage; zero-token attempts remain at initialization.</text>')
    return base_svg(title, subtitle, height, body)


def tool_signature(title: str, subtitle: str, rows: list[list[str]]) -> str:
    panels = []
    height = 650
    for panel_index, row in enumerate(rows):
        denominator = number(row[0])
        pairs = re.findall(r"([A-Za-z0-9_]+)\s+(\d+)", row[1])
        values = [(tool, int(count) / denominator) for tool, count in pairs]
        x0 = 80 + panel_index * 760
        panels.extend(
            [
                f'<rect x="{x0}" y="165" width="700" height="420" rx="16" fill="#fff" stroke="#cbd5e1" stroke-width="2"/>',
                f'<text class="label" x="{x0 + 25}" y="203">{escape(row[0])} — calls per run</text>',
            ]
        )
        max_value = max(value for _, value in values)
        for index, (tool, value) in enumerate(values):
            y = 245 + index * 64
            width = 330 * value / max_value
            panels.extend(
                [
                    text_lines(tool, x0 + 25, y + 6, "small", width=27),
                    f'<rect x="{x0 + 310}" y="{y - 13}" width="{width:.1f}" height="25" rx="4" fill="{GREEN if panel_index == 0 else RED}"/>',
                    f'<text class="value" x="{x0 + 320 + width:.1f}" y="{y + 5}">{value:.2f}</text>',
                ]
            )
    return base_svg(title, subtitle, height, panels)


def render(report_key: str, table) -> str:
    title = tables_module.title_for(table)
    subtitle = f"{report_key.upper()} report • source table {table.number:02d}, line {table.source_line}"
    rows = table.rows

    if report_key == "opus5":
        if table.number == 1:
            labels = [r[0] for r in rows[:-1]]
            return stacked_bars(title, subtitle, labels, [[number(r[2]), number(r[3])] for r in rows[:-1]], ["attempted", "skipped"], [BLUE, LIGHT], note="Every backend had 24 planned runs; curtailed local arms account for almost all skipped slots.")
        if table.number == 2:
            return horizontal_bars(title, subtitle, [r[0] for r in rows], [("runs", [number(r[2]) for r in rows], BLUE)], maximum=40, note="MARKER and RAN each contain 34 runs; only one finalized run stopped at CONTROL.")
        if table.number == 3:
            return stacked_bars(title, subtitle, [r[0] for r in rows], [[number(v) for v in r[2:6]] for r in rows], ["none", "ran", "control", "marker"], list(TIER_COLORS))
        if table.number == 4:
            labels = [r[0] for r in rows]
            ns = [number(r[1]) for r in rows]
            vals = [[100 * number(r[c]) / ns[i] for i, r in enumerate(rows)] for c in (2, 3, 4)]
            return horizontal_bars(title, subtitle, labels, [("RAN+", vals[0], BLUE), ("CONTROL+", vals[1], ORANGE), ("MARKER", vals[2], GREEN)], maximum=100, suffix="%")
        if table.number == 5:
            return horizontal_bars(title, subtitle, [r[0] for r in rows], [("runs", [number(r[1]) for r in rows], TEAL)], maximum=8)
        if table.number == 6:
            matrix, notes = [], []
            for row in rows:
                values, annotations = [], []
                for cell in row[1:4]:
                    success, n = fraction(cell)
                    ran_match = re.search(r"\((\d+)\)", cell)
                    values.append(100 * success / n if n else 0)
                    annotations.append(f"{int(success)}/{int(n)} • RAN+ {ran_match.group(1) if ran_match else '?'}")
                matrix.append(values)
                notes.append(annotations)
            return heatmap(title, subtitle, [r[0] for r in rows], table.headers[1:4], matrix, notes)
        if table.number == 7:
            labels = [r[0] for r in rows]
            tier_rows = [tiers(r[3]) for r in rows]
            return stacked_bars(title, subtitle, labels, tier_rows, ["none", "ran", "control", "marker"], list(TIER_COLORS), note="Median total tokens: " + " • ".join(f"{short_label(r[0])} {r[4]}" for r in rows))
        if table.number == 8:
            return horizontal_bars(title, subtitle, [r[0] for r in rows], [("tool sequences", [number(r[2]) for r in rows], BLUE), ("payloads", [number(r[3]) for r in rows], PURPLE)], maximum=2, note="Maximum diversity is 2.00 because each complete cell contains two replicates.")
        if table.number == 9:
            tools, calls, call_labels = [], [], []
            for row in rows:
                tools.extend([row[0], row[4]])
                calls.extend([number(row[1]), number(row[5].split("–")[0].split("/")[0])])
                call_labels.extend([row[1], row[5]])
            order = sorted(range(len(tools)), key=lambda i: calls[i], reverse=True)
            return horizontal_bars(
                title,
                subtitle,
                [tools[i] for i in order],
                [("calls", [calls[i] for i in order], BLUE)],
                maximum=500,
                value_labels=[[call_labels[i] for i in order]],
            )
        if table.number == 10:
            return tool_signature(title, subtitle, rows)
        if table.number == 11:
            metrics = ["Median iterations", "Median prompt tokens", "Median completion tokens", "Median total tokens"]
            first = [number(rows[0][2]), number(rows[0][3]), number(rows[0][4]), number(rows[0][5])]
            second = [number(rows[1][2]), number(rows[1][3]), number(rows[1][4]), number(rows[1][5])]
            displays = [(rows[0][i], rows[1][i]) for i in range(2, 6)]
            return small_multiples(title, subtitle, metrics, "success", first, "failure", second, displays, "Each metric is scaled independently; compare bar lengths only within a row.")
        if table.number == 12:
            return pvalue_plot(title, subtitle, [r[0] for r in rows], [number(r[2]) for r in rows])
        if table.number == 13:
            return forest_plot(title, subtitle, [r[0] for r in rows], [percent(r[2]) for r in rows], [interval(r[3]) for r in rows])
        if table.number == 14:
            labels = [r[0] for r in rows]
            return horizontal_bars(title, subtitle, labels, [("median wall", [number(r[1]) for r in rows], BLUE), ("maximum wall", [number(r[2]) for r in rows], ORANGE)], maximum=750, suffix=" s", note="The nominal wall-clock cap was 600 seconds; overshoot reflects between-call enforcement.")

    if report_key == "sol56":
        if table.number == 1:
            labels = [r[0] for r in rows[:-1]]
            finalized = [number(r[2]) for r in rows[:-1]]
            successes = [number(r[5]) for r in rows[:-1]]
            return horizontal_bars(title, subtitle, labels, [("finalized", finalized, BLUE), ("success", successes, GREEN)], maximum=24, note="All backends had 24 planned runs; the success bar is a subset of finalized coverage.")
        if table.number == 2:
            return partial_timeline(title, subtitle, rows)
        if table.number == 3:
            return horizontal_bars(title, subtitle, [r[0] for r in rows], [("records", [number(r[1]) for r in rows], TEAL)], maximum=40)
        if table.number == 4:
            return horizontal_bars(title, subtitle, [r[0] for r in rows], [("runs", [number(r[2]) for r in rows], BLUE)], maximum=40)
        if table.number == 5:
            return horizontal_bars("Final validator return codes", subtitle, [r[0] for r in rows], [("records", [number(r[1]) for r in rows], PURPLE)], maximum=65)
        if table.number == 6:
            return forest_plot(title, subtitle, [r[0] for r in rows], [percent(r[3]) for r in rows], [interval(r[4]) for r in rows], tier_values=[tiers(r[5]) for r in rows])
        if table.number == 7:
            labels = [r[0] for r in rows]
            ns = [number(r[1]) for r in rows]
            vals = [[100 * number(r[c]) / ns[i] for i, r in enumerate(rows)] for c in (2, 3, 4)]
            return horizontal_bars(title, subtitle, labels, [("RAN+", vals[0], BLUE), ("CONTROL+", vals[1], ORANGE), ("MARKER", vals[2], GREEN)], maximum=100, suffix="%")
        if table.number == 8:
            return horizontal_bars(title, subtitle, [r[0] for r in rows], [("runs", [number(r[1]) for r in rows], TEAL)], maximum=8)
        if table.number == 9:
            return forest_plot(title, subtitle, [r[0] for r in rows], [percent(r[3]) for r in rows], [interval(r[4]) for r in rows], tier_values=[tiers(r[5]) for r in rows])
        if table.number == 10:
            matrix, annotations = [], []
            for row in rows:
                values, notes = [], []
                for cell in row[1:4]:
                    success, n = fraction(cell)
                    values.append(100 * success / n if n else 0)
                    notes.append(cell)
                matrix.append(values)
                annotations.append(notes)
            return heatmap(title, subtitle, [r[0] for r in rows], table.headers[1:4], matrix, annotations)
        if table.number == 11:
            metrics = ["Median iterations", "Median prompt tokens", "Median completion tokens", "Median total tokens", "Median wall time"]
            first = [number(rows[0][i]) for i in range(2, 7)]
            second = [number(rows[1][i]) for i in range(2, 7)]
            displays = [(rows[0][i], rows[1][i]) for i in range(2, 7)]
            return small_multiples(title, subtitle, metrics, "success", first, "failure", second, displays, "Each metric is scaled independently; compare bar lengths only within a row.")
        if table.number == 12:
            return horizontal_bars(title, subtitle, [r[0] for r in rows], [("runs", [number(r[1]) for r in rows], BLUE)], maximum=40)
        if table.number == 13:
            return horizontal_bars(title, subtitle, [r[0] for r in rows], [("calls", [number(r[1]) for r in rows], BLUE)], maximum=500)
        if table.number == 14:
            metrics = [r[0] for r in rows]
            first = [number(r[1]) for r in rows]
            second = [number(r[2]) for r in rows]
            displays = [(r[1], r[2]) for r in rows]
            return small_multiples("Winning versus losing tool behavior", subtitle, metrics, "successes", first, "failures", second, displays, "Each measure is scaled independently; totals reflect unequal group sizes (34 successes, 58 failures).")
        if table.number == 15:
            return horizontal_bars(title, subtitle, [r[0] for r in rows], [("scripts present", [number(r[2]) for r in rows], BLUE), ("distinct digests", [number(r[3]) for r in rows], PURPLE)], maximum=2, note="Both measures have a theoretical maximum of 2 scripts per complete replicate cell.")

    raise RuntimeError(f"no chart mapping for {report_key} table {table.number}")


def main() -> None:
    index_lines = [
        "# Trial 2 report data-display index",
        "",
        "Each Markdown table has a corresponding graph or structured data display.",
        "",
    ]
    total = 0
    for report_key, report_path in tables_module.REPORTS:
        output_dir = OUTPUT_ROOT / report_key
        output_dir.mkdir(parents=True, exist_ok=True)
        index_lines.extend([f"## {report_path.name}", ""])
        for table in tables_module.parse_tables(report_path):
            title = tables_module.title_for(table)
            stem = f"{table.number:02d}_{tables_module.slugify(title)}_chart"
            svg_path = output_dir / f"{stem}.svg"
            svg_path.write_text(render(report_key, table), encoding="utf-8")
            index_lines.append(
                f"- {table.number:02d}. [{title}]({report_key}/{stem}.png) "
                f"([SVG]({report_key}/{stem}.svg))"
            )
            total += 1
        index_lines.append("")
    index_lines.extend([f"Total displays rendered: **{total}**.", ""])
    (OUTPUT_ROOT / "INDEX.md").write_text("\n".join(index_lines), encoding="utf-8")


if __name__ == "__main__":
    main()
