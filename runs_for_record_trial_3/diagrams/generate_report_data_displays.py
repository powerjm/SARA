"""Create a chart or structured data display for every Trial 3 report table.

The generator reads only the two Markdown reports. It does not open the run
archive or any submitted artifact.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import sys


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
TRIAL2_CHARTS = (
    REPO_ROOT
    / "runs_for_record_trial_2"
    / "diagrams"
    / "generate_report_data_displays.py"
)
TABLE_GENERATOR = HERE / "generate_report_table_diagrams.py"
CORE_GENERATOR = HERE / "generate_trial_3_diagrams.py"
OUTPUT_ROOT = HERE / "report_charts"
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


charts = load_module("trial2_chart_helpers_for_trial3", TRIAL2_CHARTS)
tables = load_module("trial3_table_parser_for_charts", TABLE_GENERATOR)
core = load_module("trial3_core_for_report_charts", CORE_GENERATOR)

BLUE = charts.BLUE
TEAL = charts.TEAL
PURPLE = charts.PURPLE
GREEN = charts.GREEN
ORANGE = charts.ORANGE
LIGHT = charts.LIGHT
TIER_COLORS = charts.TIER_COLORS


ORIGINAL_SHORT_LABEL = charts.short_label


def trial3_short_label(value: str) -> str:
    replacements = {
        "claude-opus": "Claude Opus",
        "cgc-cromu-00004": "CGC CROMU",
        "cgc-eagle-00005": "CGC EAGLE",
        "cgc-nrfin-00056": "CGC NRFIN",
        "ropbench-synth-ex002": "ROPBench ex002",
        "ropbench-synth-ex020": "ROPBench ex020",
        "ropbench-synth-ex101": "ROPBench ex101",
        "template_backward": "Template backward",
        "recon_first": "Recon first",
        "qwen3-30b-abliterated": "Qwen3 Abliterated",
    }
    return replacements.get(value, ORIGINAL_SHORT_LABEL(value))


charts.short_label = trial3_short_label


def number(value: str) -> float:
    return charts.number(value)


def success_rate(cell: str) -> tuple[float, str]:
    k, n = charts.fraction(cell)
    return (100 * k / n if n else 0.0, f"{int(k)}/{int(n)}")


def render_opus(table) -> str:
    title = tables.title_for(table)
    subtitle = f"OPUS5 report • source table {table.number:02d}, line {table.source_line}"
    rows = table.rows
    if table.number == 1:
        data = rows[:-1] if rows[-1][0].lower() == "total" else rows
        return charts.stacked_bars(
            title,
            subtitle,
            [r[0] for r in data],
            [[number(r[2]), number(r[3])] for r in data],
            ["attempted", "not run"],
            [BLUE, LIGHT],
            note="Each backend had 36 planned runs; local coverage stopped in target order.",
        )
    if table.number == 2:
        return charts.horizontal_bars(
            title,
            subtitle,
            [r[0] for r in rows],
            [("records", [number(r[2]) for r in rows], BLUE)],
            maximum=65,
            note="Refusal is an outcome overlay, not a fifth exclusive progress rung.",
        )
    if table.number == 3:
        return charts.stacked_bars(
            title,
            subtitle,
            [r[0] for r in rows],
            [[number(v) for v in r[2:6]] for r in rows],
            ["none", "ran", "control", "marker"],
            list(TIER_COLORS),
        )
    if table.number == 4:
        ns = [number(r[2]) for r in rows]
        values = [
            [100 * number(r[col]) / ns[i] for i, r in enumerate(rows)]
            for col in (3, 4, 5)
        ]
        return charts.horizontal_bars(
            title,
            subtitle,
            [r[0] for r in rows],
            [
                ("RAN+", values[0], BLUE),
                ("CONTROL+", values[1], ORANGE),
                ("MARKER", values[2], GREEN),
            ],
            maximum=100,
            suffix="%",
        )
    if table.number == 5:
        matrix, annotations = [], []
        for row in rows:
            values, notes = [], []
            for cell in row[1:3]:
                rate, note = success_rate(cell)
                values.append(rate)
                notes.append(note)
            matrix.append(values)
            annotations.append(notes)
        return charts.heatmap(
            title,
            subtitle,
            [r[0] for r in rows],
            table.headers[1:3],
            matrix,
            annotations,
        )
    if table.number == 6:
        return charts.stacked_bars(
            title,
            subtitle,
            [r[0] for r in rows],
            [charts.tiers(r[3]) for r in rows],
            ["none", "ran", "control", "marker"],
            list(TIER_COLORS),
            note="Median total tokens: "
            + " • ".join(f"{trial3_short_label(r[0])} {r[4]}" for r in rows),
        )
    if table.number == 7:
        return charts.horizontal_bars(
            title,
            subtitle,
            [r[0] for r in rows],
            [
                ("tool sequences", [number(r[2]) for r in rows], BLUE),
                ("trajectories", [number(r[3]) for r in rows], PURPLE),
            ],
            maximum=2,
            note="Each complete factor cell contains two replicates.",
        )
    if table.number == 8:
        tools, calls, displays = [], [], []
        for row in rows:
            for name_col, call_col in ((0, 1), (4, 5)):
                if row[name_col]:
                    tools.append(row[name_col])
                    calls.append(number(row[call_col]))
                    displays.append(row[call_col])
        order = sorted(range(len(tools)), key=lambda i: calls[i], reverse=True)
        return charts.horizontal_bars(
            title,
            subtitle,
            [tools[i] for i in order],
            [("calls", [calls[i] for i in order], BLUE)],
            maximum=max(calls),
            value_labels=[[displays[i] for i in order]],
        )
    if table.number == 9:
        return charts.tool_signature(title, subtitle, rows)
    if table.number == 10:
        metrics = [
            "Median iterations",
            "Median prompt tokens",
            "Median completion tokens",
            "Median total tokens",
        ]
        first = [number(rows[0][i]) for i in range(2, 6)]
        second = [number(rows[1][i]) for i in range(2, 6)]
        displays = [(rows[0][i], rows[1][i]) for i in range(2, 6)]
        return charts.small_multiples(
            title,
            subtitle,
            metrics,
            "success",
            first,
            "nonsuccess",
            second,
            displays,
            "Metrics are independently scaled; compare bar lengths only within a row.",
        )
    if table.number == 11:
        return charts.pvalue_plot(
            title,
            subtitle,
            [r[0] for r in rows],
            [number(r[2]) for r in rows],
        )
    if table.number == 12:
        return charts.forest_plot(
            title,
            subtitle,
            [r[0] for r in rows],
            [charts.percent(r[2]) for r in rows],
            [charts.interval(r[3]) for r in rows],
        )
    if table.number == 13:
        return charts.horizontal_bars(
            title,
            subtitle,
            [r[0] for r in rows],
            [
                ("cap", [number(r[1]) for r in rows], LIGHT),
                ("median wall", [number(r[2]) for r in rows], BLUE),
                ("failure median", [number(r[3]) for r in rows], ORANGE),
                ("success median", [number(r[5]) for r in rows], GREEN),
            ],
            maximum=1700,
            suffix=" s",
            value_labels=[
                [r[1] for r in rows],
                [r[2] for r in rows],
                [r[3] for r in rows],
                [r[5] for r in rows],
            ],
            note="Caps are checkpointed thresholds; observed wall times can exceed them.",
        )
    raise RuntimeError(f"no Opus chart mapping for table {table.number}")


def render_codex(table) -> str:
    title = tables.title_for(table)
    subtitle = f"CODEX report • source table {table.number:02d}, line {table.source_line}"
    rows = table.rows
    if table.number in (1, 2):
        return charts.horizontal_bars(
            title,
            subtitle,
            [r[0] for r in rows],
            [("records", [number(r[1]) for r in rows], BLUE)],
            maximum=105 if table.number == 1 else 65,
        )
    if table.number == 3:
        rates = [number(r[3]) for r in rows]
        return charts.forest_plot(
            title,
            subtitle,
            [r[0] for r in rows],
            rates,
            [(rate, rate) for rate in rates],
            tier_values=[[number(v) for v in r[4:8]] for r in rows],
        )
    if table.number == 4:
        ns = [number(r[1]) for r in rows]
        values = [
            [100 * number(r[col]) / ns[i] for i, r in enumerate(rows)]
            for col in (2, 3, 4)
        ]
        return charts.horizontal_bars(
            title,
            subtitle,
            [r[0] for r in rows],
            [
                ("RAN+", values[0], BLUE),
                ("CONTROL+", values[1], ORANGE),
                ("success", values[2], GREEN),
            ],
            maximum=100,
            suffix="%",
        )
    if table.number == 5:
        return charts.horizontal_bars(
            title,
            subtitle,
            [r[0] for r in rows],
            [
                ("success rate", [number(r[3]) for r in rows], GREEN),
                ("success count", [number(r[2]) for r in rows], BLUE),
            ],
            maximum=45,
            note="The two series use different units; labels preserve the original values.",
        )
    if table.number == 6:
        return charts.horizontal_bars(
            title,
            subtitle,
            [r[0] for r in rows],
            [("records", [number(r[1]) for r in rows], ORANGE)],
            maximum=80,
        )
    if table.number == 7:
        costs = " • ".join(f"{trial3_short_label(r[0])}: {r[3]}" for r in rows)
        token_label = lambda value: (
            f"{number(value)/1_000_000:.2f}M"
            if number(value) >= 1_000_000
            else f"{number(value)/1_000:.0f}k"
        )
        return charts.horizontal_bars(
            title,
            subtitle,
            [r[0] for r in rows],
            [
                ("prompt", [number(r[1]) for r in rows], BLUE),
                ("completion", [number(r[2]) for r in rows], ORANGE),
            ],
            maximum=10_000_000,
            value_labels=[
                [token_label(r[1]) for r in rows],
                [token_label(r[2]) for r in rows],
            ],
            note=f"Recorded costs: {costs}",
        )
    raise RuntimeError(f"no Codex chart mapping for table {table.number}")


def render(report_key: str, table) -> str:
    return render_opus(table) if report_key == "opus5" else render_codex(table)


def main() -> None:
    index = [
        "# Trial 3 report data-display index",
        "",
        "Each Markdown table has a corresponding graph or structured data display.",
        "",
    ]
    total = 0
    for report_key, report_path in tables.REPORTS:
        output_dir = OUTPUT_ROOT / report_key
        output_dir.mkdir(parents=True, exist_ok=True)
        index.extend([f"## {report_path.name}", ""])
        for table in tables.parse_tables(report_path):
            title = tables.title_for(table)
            stem = f"{table.number:02d}_{tables.slugify(title)}_chart"
            svg_path = output_dir / f"{stem}.svg"
            svg_path.write_text(render(report_key, table), encoding="utf-8")
            core.render_png(svg_path)
            index.append(
                f"- {table.number:02d}. [{title}]({report_key}/{stem}.png) "
                f"([SVG]({report_key}/{stem}.svg))"
            )
            total += 1
        index.append("")
    index.extend([f"Total displays rendered: **{total}**.", ""])
    (OUTPUT_ROOT / "INDEX.md").write_text("\n".join(index), encoding="utf-8")


if __name__ == "__main__":
    main()
