"""Generate Trial 1 versus Trial 2 comparison diagrams.

The archive reader opens only record.json metadata. It never opens exploit.py,
payload.bin, target binaries, or any other submitted artifact.
"""

from __future__ import annotations

import collections
import json
import math
import statistics
import tarfile
import textwrap
from html import escape
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = Path(__file__).resolve().parent / "diagrams"
TRIALS = {
    1: {
        "archive": ROOT / "runs_for_record_trial_1" / "runs.tgz",
        "config": ROOT / "runs_for_record_trial_1" / "experiments.yaml",
    },
    2: {
        "archive": ROOT / "runs_for_record_trial_2" / "runz.tgz",
        "config": ROOT / "runs_for_record_trial_2" / "experiments.yaml",
    },
}

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
MUTED = "#64748b"
INK = "#1e293b"

SHARED_BACKENDS = ("claude-sonnet", "gpt-5", "gpt-oss-20b")
SHARED_STRATEGIES = ("zero_shot", "chain_of_thought", "react")
SHARED_TARGETS = (
    "broncoctf2026-proper-pwning",
    "cgc-cadet-00001",
    "ropbench-synth-ex005",
)

BACKEND_LABELS = {
    "claude-sonnet": "Claude Sonnet",
    "claude-opus": "Claude Opus",
    "gpt-5": "GPT-5",
    "gemini-pro-latest": "Gemini Pro",
    "qwen2.5-coder-32b": "Qwen2.5 Coder",
    "qwen3-coder-30b": "Qwen3 Coder",
    "gpt-oss-20b": "GPT-OSS 20B",
    "devstral-small": "Devstral Small",
    "whiterabbitneo-v3-7b": "WhiteRabbitNeo",
    "qwen3-30b-abliterated": "Qwen3 Abliterated",
    "dolphin-3.0-mistral-24b": "Dolphin Mistral",
}
TARGET_LABELS = {
    "broncoctf2026-proper-pwning": "BroncoCTF 2026",
    "cgc-cadet-00001": "CGC CADET 00001",
    "cgc-cromu-00004": "CGC CROMU 00004",
    "cgc-eagle-00005": "CGC EAGLE 00005",
    "cgc-nrfin-00056": "CGC NRFIN 00056",
    "ropbench-synth-ex005": "ROPBench ex005",
    "ropbench-synth-ex002": "ROPBench ex002",
    "ropbench-synth-ex020": "ROPBench ex020",
    "ropbench-synth-ex010": "ROPBench ex010",
    "ropbench-synth-ex101": "ROPBench ex101",
    "ret2win-baseline": "ret2win baseline",
}
MOSAIC_TARGET_LABELS = {
    "cgc-cadet-00001": "CADET",
    "cgc-cromu-00004": "CROMU",
    "cgc-eagle-00005": "EAGLE",
    "cgc-nrfin-00056": "NRFIN",
    "broncoctf2026-proper-pwning": "Bronco",
    "ropbench-synth-ex005": "ex005",
    "ropbench-synth-ex002": "ex002",
    "ropbench-synth-ex020": "ex020",
    "ropbench-synth-ex010": "ex010",
    "ropbench-synth-ex101": "ex101",
    "ret2win-baseline": "ret2win",
}
STRATEGY_LABELS = {
    "zero_shot": "Zero-shot",
    "chain_of_thought": "Chain of thought",
    "react": "ReAct",
}


def load_records(path: Path) -> list[dict[str, Any]]:
    with tarfile.open(path, "r:gz") as archive:
        records = []
        for member in archive.getmembers():
            if (
                member.name.startswith("runs/")
                and member.name.endswith("/record.json")
                and "/.partial-" not in member.name
            ):
                handle = archive.extractfile(member)
                if handle is None:
                    raise RuntimeError(f"cannot read {member.name}")
                records.append(json.load(handle))
    return records


def wilson(successes: int, total: int, z: float = 1.95996398454) -> tuple[float, float]:
    denominator = 1 + z * z / total
    centre = (successes / total + z * z / (2 * total)) / denominator
    spread = (
        z
        * math.sqrt(successes * (total - successes) / total**3 + z * z / (4 * total * total))
        / denominator
    )
    return centre - spread, centre + spread


def label_backend(value: str) -> str:
    return BACKEND_LABELS.get(value, value)


def label_target(value: str) -> str:
    return TARGET_LABELS.get(value, value)


def label_strategy(value: str) -> str:
    return STRATEGY_LABELS.get(value, value)


def svg_text(
    value: str,
    x: float,
    y: float,
    css: str,
    *,
    width: int = 32,
    anchor: str = "start",
    line_height: int = 21,
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


def base_svg(title: str, subtitle: str, height: int, body: list[str], source: str) -> str:
    title_lines = textwrap.wrap(title, width=76, break_long_words=False) or [title]
    offset = 42 * (len(title_lines) - 1)
    final_height = height + offset
    title_markup = [
        f'<text class="title" x="60" y="{57 + index * 42}">{escape(line)}</text>'
        for index, line in enumerate(title_lines)
    ]
    subtitle_y = 57 + len(title_lines) * 42 + 4
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
    .white { font: 700 15px system-ui, sans-serif; fill: #fff; }
    .source { font: 14px system-ui, sans-serif; fill: #64748b; }
  </style>""",
            f'<rect width="{WIDTH}" height="{final_height}" fill="#f8fafc"/>',
            *title_markup,
            f'<text class="sub" x="60" y="{subtitle_y}">{escape(subtitle)}</text>',
            f'<g transform="translate(0,{offset})">',
            *body,
            f'<text class="source" x="60" y="{height - 22}">{escape(source)}</text>',
            "</g>",
            "</svg>",
            "",
        ]
    )


def write(name: str, content: str) -> None:
    (OUTPUT / name).write_text(content, encoding="utf-8")


def primary_endpoint(records: dict[int, list[dict[str, Any]]]) -> str:
    rows = []
    for trial in (1, 2):
        subset = records[trial]
        successes = sum(record["outcome"] == "success" for record in subset)
        low, high = wilson(successes, len(subset))
        rows.append(
            (trial, successes, len(subset), 100 * successes / len(subset), 100 * low, 100 * high)
        )
    plot_x, plot_width = 380, 1040
    body = []
    maximum = 50
    for tick in range(6):
        value = maximum * tick / 5
        x = plot_x + plot_width * value / maximum
        body.extend(
            [
                f'<line x1="{x:.1f}" y1="175" x2="{x:.1f}" y2="440" stroke="#e2e8f0"/>',
                f'<text class="axis" x="{x:.1f}" y="164" text-anchor="middle">{value:g}%</text>',
            ]
        )
    for index, (trial, successes, total, rate, low, high) in enumerate(rows):
        y = 245 + index * 140
        lo_x = plot_x + plot_width * low / maximum
        hi_x = plot_x + plot_width * high / maximum
        rate_x = plot_x + plot_width * rate / maximum
        body.extend(
            [
                f'<text class="label" x="60" y="{y + 5}">Trial {trial}</text>',
                f'<line x1="{lo_x:.1f}" y1="{y}" x2="{hi_x:.1f}" y2="{y}" stroke="{BLUE if trial == 1 else GREEN}" stroke-width="7"/>',
                f'<circle cx="{rate_x:.1f}" cy="{y}" r="11" fill="{NAVY}"/>',
                f'<text class="value" x="{max(hi_x + 16, rate_x + 16):.1f}" y="{y + 5}">{successes}/{total} = {rate:.1f}% [{low:.2f}, {high:.2f}]</text>',
            ]
        )
    body.extend(
        [
            '<rect x="60" y="485" width="1420" height="65" rx="12" fill="#fef3c7"/>',
            '<text class="small" x="84" y="512">Wilson intervals are descriptive. The trials changed tools, targets, budgets, models, prompts, replication,</text>',
            '<text class="small" x="84" y="536">and scoring schema, so the rate difference is not an isolated treatment effect.</text>',
        ]
    )
    return base_svg(
        "Primary endpoint: validator-confirmed success",
        "Finalized-run rate with descriptive Wilson 95% intervals",
        610,
        body,
        "Source: Trial 1 and Trial 2 finalized RunRecord metadata",
    )


def progress_ladders() -> str:
    trial1 = [
        ("Refused", 200, RED),
        ("Never submitted", 964, LIGHT),
        ("Undecodable", 86, SLATE),
        ("Ran, no win", 345, BLUE),
        ("Crash proxy", 153, ORANGE),
        ("Progress gate", 7, PURPLE),
        ("MARKER", 0, GREEN),
    ]
    trial2 = [
        ("NONE", 23, LIGHT),
        ("RAN", 34, BLUE),
        ("CONTROL", 1, ORANGE),
        ("MARKER", 34, GREEN),
    ]
    body = []
    panels = ((100, "Trial 1 · schema v4", trial1, 1755), (835, "Trial 2 · schema v5", trial2, 92))
    for x, heading, rows, total in panels:
        body.extend(
            [
                f'<rect x="{x}" y="160" width="665" height="650" rx="18" fill="#fff" stroke="#cbd5e1" stroke-width="2"/>',
                f'<text class="label" x="{x + 28}" y="202">{heading}</text>',
            ]
        )
        row_height = 70 if len(rows) > 4 else 105
        for index, (label, count, color) in enumerate(rows):
            y = 235 + index * row_height
            width = 450 * count / max(value for _, value, _ in rows) if count else 0
            body.extend(
                [
                    f'<text class="label" x="{x + 28}" y="{y + 22}">{label}</text>',
                    f'<rect x="{x + 190}" y="{y}" width="{width:.1f}" height="32" rx="5" fill="{color}"/>',
                    f'<text class="value" x="{x + 205 + width:.1f}" y="{y + 22}">{count} · {count / total:.1%}</text>',
                ]
            )
    body.extend(
        [
            '<line x1="775" y1="160" x2="825" y2="810" stroke="#dc2626" stroke-width="2" stroke-dasharray="8 8"/>',
            '<text class="small" x="800" y="842" text-anchor="middle">Dashed boundary: the intermediate-stage constructs and scoring schema changed.</text>',
        ]
    )
    return base_svg(
        "Side-by-side progress ladders",
        "Within-trial mutually exclusive terminal classifications; middle stages are not identical constructs",
        900,
        body,
        "Source: Trial 1 progress-ladder report and Trial 2 max_tier_reached metadata",
    )


def filtered(
    records: list[dict[str, Any]],
    *,
    backend: str | None = None,
    target: str | None = None,
    strategy: str | None = None,
) -> list[dict[str, Any]]:
    return [
        record
        for record in records
        if record["backend_handle"] in SHARED_BACKENDS
        and record["binary_id"] in SHARED_TARGETS
        and record["prompting_strategy"] in SHARED_STRATEGIES
        and (backend is None or record["backend_handle"] == backend)
        and (target is None or record["binary_id"] == target)
        and (strategy is None or record["prompting_strategy"] == strategy)
    ]


def rates(subset: list[dict[str, Any]]) -> tuple[float, float]:
    reached = sum(record.get("validator") is not None for record in subset)
    success = sum(record["outcome"] == "success" for record in subset)
    return 100 * reached / len(subset), 100 * success / len(subset)


def dumbbell(
    records: dict[int, list[dict[str, Any]]],
    *,
    dimension: str,
    values: tuple[str, ...],
    title: str,
) -> str:
    plot_x, plot_width = 390, 1030
    body = [
        f'<rect x="770" y="120" width="18" height="18" rx="3" fill="{BLUE}"/><text class="legend" x="798" y="135">Trial 1 reached validator</text>',
        f'<rect x="1000" y="120" width="18" height="18" rx="3" fill="{TEAL}"/><text class="legend" x="1028" y="135">Trial 2 reached validator</text>',
        f'<rect x="1240" y="120" width="18" height="18" rx="3" fill="{GREEN}"/><text class="legend" x="1268" y="135">Trial 2 success</text>',
    ]
    for tick in range(5):
        x = plot_x + plot_width * tick / 4
        body.extend(
            [
                f'<line x1="{x}" y1="170" x2="{x}" y2="{225 + len(values) * 105}" stroke="#e2e8f0"/>',
                f'<text class="axis" x="{x}" y="160" text-anchor="middle">{tick * 25}%</text>',
            ]
        )
    for index, value in enumerate(values):
        kwargs = {dimension: value}
        one = filtered(records[1], **kwargs)
        two = filtered(records[2], **kwargs)
        t1_reach, _ = rates(one)
        t2_reach, t2_success = rates(two)
        y = 230 + index * 105
        xs = [
            plot_x + plot_width * t1_reach / 100,
            plot_x + plot_width * t2_reach / 100,
            plot_x + plot_width * t2_success / 100,
        ]
        label = (
            label_backend(value)
            if dimension == "backend"
            else label_target(value)
            if dimension == "target"
            else label_strategy(value)
        )
        body.extend(
            [
                svg_text(label, 60, y + 5, "label", width=30),
                f'<line x1="{min(xs):.1f}" y1="{y}" x2="{max(xs):.1f}" y2="{y}" stroke="#cbd5e1" stroke-width="5"/>',
                f'<circle cx="{xs[0]:.1f}" cy="{y}" r="10" fill="{BLUE}"/>',
                f'<circle cx="{xs[1]:.1f}" cy="{y}" r="10" fill="{TEAL}"/>',
                f'<circle cx="{xs[2]:.1f}" cy="{y}" r="10" fill="{GREEN}"/>',
                f'<text class="small" x="{xs[0]:.1f}" y="{y + 30}" text-anchor="middle">{t1_reach:.1f}%</text>',
                f'<text class="small" x="{xs[1]:.1f}" y="{y - 18}" text-anchor="middle">{t2_reach:.1f}%</text>',
                f'<text class="small" x="{xs[2]:.1f}" y="{y + 52}" text-anchor="middle">{t2_success:.1f}%</text>',
            ]
        )
    height = 300 + len(values) * 105
    return base_svg(
        title,
        "Observed finalized runs in the common-coverage subset: 3 targets × 3 backends × 3 strategies",
        height,
        body,
        "Source: record.json metadata; Trial 1 used five replicates and Trial 2 used two",
    )


def delta_heatmap(records: dict[int, list[dict[str, Any]]]) -> str:
    left, top = 405, 230
    cell_w, cell_h = 330, 105
    body = []
    for column, strategy in enumerate(SHARED_STRATEGIES):
        body.append(
            f'<text class="label" x="{left + column * cell_w + (cell_w - 10) / 2}" y="195" text-anchor="middle">{label_strategy(strategy)}</text>'
        )
    for row_index, backend in enumerate(SHARED_BACKENDS):
        y = top + row_index * cell_h
        body.append(f'<text class="label" x="60" y="{y + 55}">{label_backend(backend)}</text>')
        for column_index, strategy in enumerate(SHARED_STRATEGIES):
            one = filtered(records[1], backend=backend, strategy=strategy)
            two = filtered(records[2], backend=backend, strategy=strategy)
            t1_reach, _ = rates(one)
            t2_reach, t2_success = rates(two)
            delta = t2_reach - t1_reach
            intensity = max(-50, min(75, delta))
            if intensity >= 0:
                ratio = intensity / 75
                r, g, b = (
                    round(241 + (22 - 241) * ratio),
                    round(245 + (163 - 245) * ratio),
                    round(249 + (74 - 249) * ratio),
                )
            else:
                ratio = -intensity / 50
                r, g, b = (
                    round(241 + (220 - 241) * ratio),
                    round(245 + (38 - 245) * ratio),
                    round(249 + (38 - 249) * ratio),
                )
            color = f"rgb({r},{g},{b})"
            x = left + column_index * cell_w
            body.extend(
                [
                    f'<rect x="{x}" y="{y}" width="{cell_w - 10}" height="{cell_h - 10}" rx="12" fill="{color}"/>',
                    f'<text class="{"white" if ratio > 0.48 else "value"}" x="{x + (cell_w - 10) / 2}" y="{y + 42}" text-anchor="middle">{delta:+.1f} pp validator reach</text>',
                    f'<text class="{"white" if ratio > 0.48 else "small"}" x="{x + (cell_w - 10) / 2}" y="{y + 70}" text-anchor="middle">Trial 2 success {t2_success:.1f}%</text>',
                ]
            )
    body.extend(
        [
            '<rect x="405" y="565" width="18" height="18" rx="3" fill="#dc2626"/><text class="small" x="433" y="580">−50 pp</text>',
            '<rect x="520" y="565" width="18" height="18" rx="3" fill="#f1f5f9"/><text class="small" x="548" y="580">no change</text>',
            '<rect x="665" y="565" width="18" height="18" rx="3" fill="#16a34a"/><text class="small" x="693" y="580">+75 pp or more</text>',
        ]
    )
    return base_svg(
        "Backend × strategy change in validator engagement",
        "Cell color is Trial 2 minus Trial 1 validator-reaching rate; annotation gives Trial 2 success",
        650,
        body,
        "Source: common-coverage record.json metadata aggregated across three shared targets",
    )


def tool_composition(records: dict[int, list[dict[str, Any]]]) -> str:
    trial1_counts = {"enumerate": 25406, "submit": 6664}
    trial2_raw = collections.Counter()
    for record in records[2]:
        trial2_raw.update(record.get("tool_call_counts", {}))
    trial2_counts = collections.Counter()
    for tool, count in trial2_raw.items():
        if tool == "enumerate_gadgets":
            group = "enumerate"
        elif tool == "run_exploit_script":
            group = "run script"
        elif tool.startswith("radare2_"):
            group = "radare2"
        elif tool.startswith("ropper_"):
            group = "ropper"
        elif tool.startswith("ghidra_"):
            group = "ghidra"
        elif tool.startswith("gdb_"):
            group = "gdb"
        elif tool.startswith("pwntools_"):
            group = "pwntools"
        elif tool == "submit_payload":
            group = "submit"
        else:
            group = "other"
        trial2_counts[group] += count
    groups = (
        "enumerate",
        "submit",
        "run script",
        "radare2",
        "ropper",
        "ghidra",
        "gdb",
        "pwntools",
        "other",
    )
    colors = (BLUE, ORANGE, GREEN, TEAL, PURPLE, "#0891b2", "#64748b", "#db2777", LIGHT)
    body = []
    legend_positions = []
    for index, (group, color) in enumerate(zip(groups, colors)):
        row, column = divmod(index, 5)
        x, y = 310 + column * 245, 145 + row * 34
        legend_positions.extend(
            [
                f'<rect x="{x}" y="{y - 15}" width="18" height="18" rx="3" fill="{color}"/>',
                f'<text class="legend" x="{x + 27}" y="{y}">{group}</text>',
            ]
        )
    body.extend(legend_positions)
    for row_index, (trial, counts) in enumerate(((1, trial1_counts), (2, trial2_counts))):
        y = 280 + row_index * 165
        total = sum(counts.values())
        cursor = 300.0
        body.append(f'<text class="label" x="60" y="{y + 35}">Trial {trial}</text>')
        for group, color in zip(groups, colors):
            count = counts.get(group, 0)
            width = 1180 * count / total
            if width:
                body.append(
                    f'<rect x="{cursor:.1f}" y="{y}" width="{width:.1f}" height="62" fill="{color}"/>'
                )
                share = 100 * count / total
                if width > 70:
                    body.append(
                        f'<text class="{"white" if color != LIGHT else "value"}" x="{cursor + width / 2:.1f}" y="{y + 28}" text-anchor="middle">{group}</text>'
                    )
                    body.append(
                        f'<text class="{"white" if color != LIGHT else "value"}" x="{cursor + width / 2:.1f}" y="{y + 49}" text-anchor="middle">{share:.1f}%</text>'
                    )
            cursor += width
        body.append(
            f'<text class="small" x="300" y="{y + 88}">{total:,} recorded tool calls</text>'
        )
    body.extend(
        [
            '<rect x="60" y="585" width="1420" height="65" rx="12" fill="#e0f2fe"/>',
            '<text class="small" x="84" y="613">Trial 1 exposed only enumerate_gadgets and submit_payload. Trial 2 redistributed calls across analysis,</text>',
            '<text class="small" x="84" y="637">script execution, disassembly, gadget search, decompilation, and debugging tools.</text>',
        ]
    )
    return base_svg(
        "Tool-use composition changed from submission to iteration",
        "Normalized shares of recorded tool calls",
        710,
        body,
        "Source: Trial 1 tool-use report and Trial 2 RunRecord tool_call_counts",
    )


def conditional_conversion(records: dict[int, list[dict[str, Any]]]) -> str:
    common = {trial: filtered(records[trial]) for trial in (1, 2)}
    groups = [
        ("All finalized", records[1], records[2]),
        ("Common coverage", common[1], common[2]),
    ]
    body = [
        f'<rect x="850" y="120" width="18" height="18" rx="3" fill="{BLUE}"/><text class="legend" x="878" y="135">Trial 1</text>',
        f'<rect x="1030" y="120" width="18" height="18" rx="3" fill="{GREEN}"/><text class="legend" x="1058" y="135">Trial 2</text>',
    ]
    x0, plot_width = 450, 970
    for tick in range(6):
        x = x0 + plot_width * tick / 5
        body.extend(
            [
                f'<line x1="{x}" y1="170" x2="{x}" y2="470" stroke="#e2e8f0"/>',
                f'<text class="axis" x="{x}" y="160" text-anchor="middle">{tick * 10}%</text>',
            ]
        )
    for index, (label, one, two) in enumerate(groups):
        y = 245 + index * 155
        values = []
        displays = []
        for subset in (one, two):
            reached = sum(record.get("validator") is not None for record in subset)
            success = sum(record["outcome"] == "success" for record in subset)
            values.append(100 * success / reached if reached else 0)
            displays.append(f"{success}/{reached}")
        body.extend(
            [
                f'<text class="label" x="60" y="{y + 30}">{label}</text>',
                f'<rect x="{x0}" y="{y}" width="{plot_width * values[0] / 50:.1f}" height="38" rx="6" fill="{BLUE}"/>',
                f'<rect x="{x0}" y="{y + 52}" width="{plot_width * values[1] / 50:.1f}" height="38" rx="6" fill="{GREEN}"/>',
                f'<text class="value" x="{x0 + plot_width * values[0] / 50 + 12:.1f}" y="{y + 25}">{displays[0]} = {values[0]:.1f}%</text>',
                f'<text class="value" x="{x0 + plot_width * values[1] / 50 + 12:.1f}" y="{y + 77}">{displays[1]} = {values[1]:.1f}%</text>',
            ]
        )
    return base_svg(
        "Conditional conversion after reaching the validator",
        "Success divided by records with a validator object",
        550,
        body,
        "Source: record.json metadata; common coverage uses three shared targets, backends, and strategies",
    )


def ecdf_path(
    values: list[float], x0: float, y0: float, width: float, height: float, maximum: float
) -> str:
    sorted_values = sorted(min(value, maximum) for value in values)
    points = [(x0, y0 + height)]
    for index, value in enumerate(sorted_values, 1):
        x = x0 + width * value / maximum
        y = y0 + height * (1 - index / len(sorted_values))
        points.append((x, y))
    return "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in points)


def resource_ecdfs(records: dict[int, list[dict[str, Any]]]) -> str:
    series = [
        ("Trial 1 failures", records[1], BLUE),
        ("Trial 2 successes", [r for r in records[2] if r["outcome"] == "success"], GREEN),
        ("Trial 2 failures", [r for r in records[2] if r["outcome"] != "success"], RED),
    ]
    panels = [
        ("Total tokens", lambda r: r["tokens"]["total"], 650000, "tokens"),
        ("Iterations", lambda r: r["iterations"], 100, "turns"),
        ("Wall time", lambda r: r["wall_clock_seconds"], 750, "seconds"),
    ]
    body = []
    for index, (label, _, color) in enumerate(series):
        x = 690 + index * 250
        body.extend(
            [
                f'<rect x="{x}" y="120" width="18" height="18" rx="3" fill="{color}"/>',
                f'<text class="legend" x="{x + 27}" y="135">{label}</text>',
            ]
        )
    for panel_index, (panel_title, getter, maximum, unit) in enumerate(panels):
        x0 = 85 + panel_index * 510
        y0, panel_w, panel_h = 225, 430, 390
        body.extend(
            [
                f'<rect x="{x0 - 20}" y="180" width="470" height="545" rx="14" fill="#fff" stroke="#cbd5e1" stroke-width="2"/>',
                f'<text class="label" x="{x0}" y="212">{panel_title}</text>',
                f'<line x1="{x0}" y1="{y0 + panel_h}" x2="{x0 + panel_w}" y2="{y0 + panel_h}" stroke="#94a3b8"/>',
                f'<line x1="{x0}" y1="{y0}" x2="{x0}" y2="{y0 + panel_h}" stroke="#94a3b8"/>',
            ]
        )
        for tick in range(5):
            x = x0 + panel_w * tick / 4
            value = maximum * tick / 4
            body.extend(
                [
                    f'<line x1="{x}" y1="{y0}" x2="{x}" y2="{y0 + panel_h}" stroke="#e2e8f0"/>',
                    f'<text class="axis" x="{x}" y="{y0 + panel_h + 25}" text-anchor="middle">{value:g}</text>',
                ]
            )
        for q in (0, 0.5, 1):
            y = y0 + panel_h * (1 - q)
            body.append(
                f'<text class="axis" x="{x0 - 12}" y="{y + 5}" text-anchor="end">{q:.0%}</text>'
            )
        for series_label, subset, color in series:
            values = [float(getter(record)) for record in subset]
            body.append(
                f'<path d="{ecdf_path(values, x0, y0, panel_w, panel_h, maximum)}" fill="none" stroke="{color}" stroke-width="4"/>'
            )
            median = statistics.median(values)
            body.append(
                f'<text class="small" x="{x0}" y="{655 + series.index((series_label, subset, color)) * 18}">{series_label}: median {median:,.1f} {unit}</text>'
            )
    return base_svg(
        "Resource-use distributions by trial and outcome",
        "Empirical cumulative distributions; values above each panel maximum are clipped at the right edge",
        810,
        body,
        "Source: finalized RunRecord token, iteration, and wall-clock metadata",
    )


def coverage_color(rate: float) -> str:
    ratio = max(0, min(1, rate))
    r = round(241 + (37 - 241) * ratio)
    g = round(245 + (99 - 245) * ratio)
    b = round(249 + (235 - 249) * ratio)
    return f"rgb({r},{g},{b})"


def coverage_mosaic(
    records: dict[int, list[dict[str, Any]]], configs: dict[int, dict[str, Any]]
) -> str:
    body = []
    panels = ((1, 220, 82), (2, 720, 150))
    for trial, top, cell_w in panels:
        backends = configs[trial]["backends"]
        targets = configs[trial]["binaries"]
        planned_per_cell = configs[trial]["replicates"] * len(configs[trial]["strategies"])
        counts = collections.Counter(
            (record["backend_handle"], record["binary_id"]) for record in records[trial]
        )
        left, cell_h = 315, 38 if trial == 1 else 45
        body.append(
            f'<text class="label" x="60" y="{top - 55}">Trial {trial} · {planned_per_cell} planned runs per backend-target cell</text>'
        )
        for column, target in enumerate(targets):
            x = left + column * cell_w + (cell_w - 4) / 2
            body.append(
                f'<text class="axis" x="{x}" y="{top - 12}" text-anchor="middle">{escape(MOSAIC_TARGET_LABELS[target])}</text>'
            )
        for row, backend in enumerate(backends):
            y = top + row * cell_h
            body.append(f'<text class="small" x="60" y="{y + 25}">{label_backend(backend)}</text>')
            for column, target in enumerate(targets):
                count = counts[(backend, target)]
                rate = count / planned_per_cell
                x = left + column * cell_w
                body.extend(
                    [
                        f'<rect x="{x}" y="{y}" width="{cell_w - 4}" height="{cell_h - 4}" rx="4" fill="{coverage_color(rate)}"/>',
                        f'<text class="{"white" if rate > 0.55 else "value"}" x="{x + (cell_w - 4) / 2}" y="{y + 24}" text-anchor="middle">{count}/{planned_per_cell}</text>',
                    ]
                )
    body.extend(
        [
            '<rect x="1110" y="1020" width="18" height="18" rx="3" fill="#f1f5f9"/><text class="small" x="1138" y="1035">0%</text>',
            '<rect x="1200" y="1020" width="18" height="18" rx="3" fill="#2563eb"/><text class="small" x="1228" y="1035">100% finalized</text>',
        ]
    )
    return base_svg(
        "Matrix coverage was structured, not random",
        "Finalized records divided by planned runs for each backend-target block",
        1090,
        body,
        "Source: experiments.yaml and finalized RunRecord counts",
    )


def bronco_milestones() -> str:
    milestones = ("Gate 1+", "Later gate+", "MARKER")
    trial1_counts = (12, 4, 0)
    trial2_counts = (11, 10, 8)
    totals = (195, 18)
    values = (
        [100 * count / totals[0] for count in trial1_counts],
        [100 * count / totals[1] for count in trial2_counts],
    )
    body = [
        f'<rect x="900" y="120" width="18" height="18" rx="3" fill="{BLUE}"/><text class="legend" x="928" y="135">Trial 1</text>',
        f'<rect x="1070" y="120" width="18" height="18" rx="3" fill="{GREEN}"/><text class="legend" x="1098" y="135">Trial 2</text>',
    ]
    x0, plot_width = 380, 1030
    for tick in range(6):
        x = x0 + plot_width * tick / 5
        body.extend(
            [
                f'<line x1="{x}" y1="175" x2="{x}" y2="510" stroke="#e2e8f0"/>',
                f'<text class="axis" x="{x}" y="165" text-anchor="middle">{tick * 20}%</text>',
            ]
        )
    for index, milestone in enumerate(milestones):
        y = 235 + index * 110
        body.extend(
            [
                f'<text class="label" x="60" y="{y + 28}">{milestone}</text>',
                f'<rect x="{x0}" y="{y}" width="{plot_width * values[0][index] / 100:.1f}" height="32" rx="5" fill="{BLUE}"/>',
                f'<rect x="{x0}" y="{y + 44}" width="{plot_width * values[1][index] / 100:.1f}" height="32" rx="5" fill="{GREEN}"/>',
                f'<text class="value" x="{x0 + plot_width * values[0][index] / 100 + 10:.1f}" y="{y + 22}">{trial1_counts[index]}/{totals[0]} = {values[0][index]:.1f}%</text>',
                f'<text class="value" x="{x0 + plot_width * values[1][index] / 100 + 10:.1f}" y="{y + 66}">{trial2_counts[index]}/{totals[1]} = {values[1][index]:.1f}%</text>',
            ]
        )
    body.extend(
        [
            '<rect x="60" y="555" width="1420" height="82" rx="12" fill="#fef3c7"/>',
            '<text class="small" x="84" y="584">Trial 1 milestones use within-run trajectory evidence (Gate 1 any=12; clean Gate 2 path=4).</text>',
            '<text class="small" x="84" y="609">Trial 2 uses retained final-record stdout (Gate 1+=11; Gate 3+=10; marker=8). The rates are descriptive,</text>',
            '<text class="small" x="84" y="632">not a measurement-identical longitudinal series.</text>',
        ]
    )
    return base_svg(
        "BroncoCTF milestone progression",
        "Cumulative milestone shares within each trial’s finalized BroncoCTF runs",
        700,
        body,
        "Source: Trial 1 trajectory analysis and Trial 2 retained validator stdout",
    )


def main() -> None:
    records = {trial: load_records(settings["archive"]) for trial, settings in TRIALS.items()}
    configs = {
        trial: yaml.safe_load(settings["config"].read_text(encoding="utf-8"))
        for trial, settings in TRIALS.items()
    }
    assert len(records[1]) == 1755
    assert len(records[2]) == 92
    assert sum(record["outcome"] == "success" for record in records[1]) == 0
    assert sum(record["outcome"] == "success" for record in records[2]) == 34

    write("01_primary_endpoint_forest.svg", primary_endpoint(records))
    write("02_progress_ladders.svg", progress_ladders())
    write(
        "03_shared_backend_dumbbell.svg",
        dumbbell(
            records,
            dimension="backend",
            values=SHARED_BACKENDS,
            title="Shared-backend engagement and success",
        ),
    )
    write(
        "04_shared_target_conversion.svg",
        dumbbell(
            records,
            dimension="target",
            values=SHARED_TARGETS,
            title="Shared-target engagement and success",
        ),
    )
    write("05_backend_strategy_delta_heatmap.svg", delta_heatmap(records))
    write("06_tool_use_composition.svg", tool_composition(records))
    write("07_conditional_conversion.svg", conditional_conversion(records))
    write("08_resource_ecdfs.svg", resource_ecdfs(records))
    write("09_matrix_coverage_mosaic.svg", coverage_mosaic(records, configs))
    write("10_bronco_milestones.svg", bronco_milestones())


if __name__ == "__main__":
    main()
