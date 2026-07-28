"""Generate Trial 2 versus Trial 3 comparison diagrams.

The archive reader opens only finalized record.json metadata. It never opens
exploit.py, payload.bin, conversation content, target binaries, or any other
submitted artifact.
"""

from __future__ import annotations

import collections
import ctypes
from html import escape
import json
import math
from pathlib import Path
import statistics
import tarfile
import textwrap
from typing import Any, Callable


ROOT = Path(__file__).resolve().parent.parent
OUTPUT = Path(__file__).resolve().parent / "diagrams"
TRIALS = {
    2: ROOT / "runs_for_record_trial_2" / "runz.tgz",
    3: ROOT / "runs_for_record_trial_3" / "runs.tgz",
}
PLANNED = {2: 144, 3: 216}
PARTIALS = {2: 4, 3: 3}
TRIAL_BACKENDS = {
    2: (
        "claude-sonnet",
        "gpt-5",
        "qwen3-coder-30b",
        "gpt-oss-20b",
        "whiterabbitneo-v3-7b",
        "qwen3-30b-abliterated",
    ),
    3: (
        "claude-sonnet",
        "claude-opus",
        "gpt-5",
        "gpt-oss-20b",
        "qwen3-30b-abliterated",
        "whiterabbitneo-v3-7b",
    ),
}
TRIAL_TARGETS = {
    2: (
        "ret2win-baseline",
        "cgc-cadet-00001",
        "broncoctf2026-proper-pwning",
        "ropbench-synth-ex005",
    ),
    3: (
        "ret2win-baseline",
        "cgc-cromu-00004",
        "cgc-eagle-00005",
        "cgc-nrfin-00056",
        "broncoctf2026-proper-pwning",
        "ropbench-synth-ex005",
        "ropbench-synth-ex002",
        "ropbench-synth-ex020",
        "ropbench-synth-ex101",
    ),
}
TRIAL_STRATEGIES = {
    2: ("zero_shot", "chain_of_thought", "react"),
    3: ("template_backward", "recon_first"),
}
REPLICATES = {2: 2, 3: 2}

SHARED_BACKENDS = (
    "claude-sonnet",
    "gpt-5",
    "gpt-oss-20b",
    "qwen3-30b-abliterated",
    "whiterabbitneo-v3-7b",
)
SHARED_TARGETS = (
    "ret2win-baseline",
    "broncoctf2026-proper-pwning",
    "ropbench-synth-ex005",
)
SHARED_PREMIUM = ("claude-sonnet", "gpt-5")

BACKEND_LABELS = {
    "claude-sonnet": "Claude Sonnet",
    "claude-opus": "Claude Opus",
    "gpt-5": "GPT-5",
    "gpt-oss-20b": "GPT-OSS 20B",
    "qwen3-coder-30b": "Qwen3 Coder 30B",
    "qwen3-30b-abliterated": "Qwen3 Abliterated",
    "whiterabbitneo-v3-7b": "WhiteRabbitNeo 7B",
}
TARGET_LABELS = {
    "ret2win-baseline": "ret2win baseline",
    "cgc-cadet-00001": "CGC CADET",
    "cgc-cromu-00004": "CGC CROMU",
    "cgc-eagle-00005": "CGC EAGLE",
    "cgc-nrfin-00056": "CGC NRFIN",
    "broncoctf2026-proper-pwning": "BroncoCTF 2026",
    "ropbench-synth-ex005": "ROPBench ex005",
    "ropbench-synth-ex002": "ROPBench ex002",
    "ropbench-synth-ex020": "ROPBench ex020",
    "ropbench-synth-ex101": "ROPBench ex101",
}
SHORT_TARGET_LABELS = {
    "ret2win-baseline": "ret2win",
    "cgc-cadet-00001": "CADET",
    "cgc-cromu-00004": "CROMU",
    "cgc-eagle-00005": "EAGLE",
    "cgc-nrfin-00056": "NRFIN",
    "broncoctf2026-proper-pwning": "Bronco",
    "ropbench-synth-ex005": "ex005",
    "ropbench-synth-ex002": "ex002",
    "ropbench-synth-ex020": "ex020",
    "ropbench-synth-ex101": "ex101",
}
STRATEGY_LABELS = {
    "zero_shot": "T2 · Zero-shot",
    "chain_of_thought": "T2 · Chain of thought",
    "react": "T2 · ReAct",
    "template_backward": "T3 · Template backward",
    "recon_first": "T3 · Recon first",
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


def load_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with tarfile.open(path, "r:gz") as archive:
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
        * math.sqrt(
            successes * (total - successes) / total**3
            + z * z / (4 * total * total)
        )
        / denominator
    )
    return centre - spread, centre + spread


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


def base_svg(
    title: str,
    subtitle: str,
    height: int,
    body: list[str],
    source: str,
) -> str:
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


class RsvgRectangle(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_double),
        ("y", ctypes.c_double),
        ("width", ctypes.c_double),
        ("height", ctypes.c_double),
    ]


def render_png(svg_path: Path) -> None:
    rsvg = ctypes.CDLL("librsvg-2.so.2")
    cairo = ctypes.CDLL("libcairo.so.2")
    gobject = ctypes.CDLL("libgobject-2.0.so.0")
    rsvg.rsvg_handle_new_from_file.argtypes = [
        ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    rsvg.rsvg_handle_new_from_file.restype = ctypes.c_void_p
    rsvg.rsvg_handle_get_intrinsic_size_in_pixels.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_double),
        ctypes.POINTER(ctypes.c_double),
    ]
    rsvg.rsvg_handle_get_intrinsic_size_in_pixels.restype = ctypes.c_bool
    rsvg.rsvg_handle_render_document.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(RsvgRectangle),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    rsvg.rsvg_handle_render_document.restype = ctypes.c_bool
    cairo.cairo_image_surface_create.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int]
    cairo.cairo_image_surface_create.restype = ctypes.c_void_p
    cairo.cairo_create.argtypes = [ctypes.c_void_p]
    cairo.cairo_create.restype = ctypes.c_void_p
    cairo.cairo_surface_write_to_png.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    cairo.cairo_surface_write_to_png.restype = ctypes.c_int
    cairo.cairo_destroy.argtypes = [ctypes.c_void_p]
    cairo.cairo_surface_destroy.argtypes = [ctypes.c_void_p]
    gobject.g_object_unref.argtypes = [ctypes.c_void_p]

    error = ctypes.c_void_p()
    handle = rsvg.rsvg_handle_new_from_file(str(svg_path).encode(), ctypes.byref(error))
    if not handle:
        raise RuntimeError(f"cannot open {svg_path}")
    width, height = ctypes.c_double(), ctypes.c_double()
    if not rsvg.rsvg_handle_get_intrinsic_size_in_pixels(
        handle, ctypes.byref(width), ctypes.byref(height)
    ):
        raise RuntimeError(f"no intrinsic size for {svg_path}")
    surface = cairo.cairo_image_surface_create(0, round(width.value), round(height.value))
    context = cairo.cairo_create(surface)
    viewport = RsvgRectangle(0.0, 0.0, width.value, height.value)
    if not rsvg.rsvg_handle_render_document(
        handle, context, ctypes.byref(viewport), ctypes.byref(error)
    ):
        raise RuntimeError(f"cannot render {svg_path}")
    png_path = svg_path.with_suffix(".png")
    status = cairo.cairo_surface_write_to_png(surface, str(png_path).encode())
    cairo.cairo_destroy(context)
    cairo.cairo_surface_destroy(surface)
    gobject.g_object_unref(handle)
    if status:
        raise RuntimeError(f"cannot write {png_path}: cairo status {status}")


def write(name: str, content: str) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT / name
    path.write_text(content, encoding="utf-8")
    render_png(path)


def validator_reached(record: dict[str, Any]) -> bool:
    return record.get("validator") is not None


def subset_shared(
    records: list[dict[str, Any]],
    *,
    backend: str | None = None,
    target: str | None = None,
    premium_only: bool = False,
) -> list[dict[str, Any]]:
    return [
        record
        for record in records
        if record["backend_handle"] in SHARED_BACKENDS
        and record["binary_id"] in SHARED_TARGETS
        and (not premium_only or record["backend_handle"] in SHARED_PREMIUM)
        and (backend is None or record["backend_handle"] == backend)
        and (target is None or record["binary_id"] == target)
    ]


def rate_pair(subset: list[dict[str, Any]]) -> tuple[int, int, int]:
    reached = sum(validator_reached(record) for record in subset)
    success = sum(record["outcome"] == "success" for record in subset)
    return len(subset), reached, success


def primary_endpoint(records: dict[int, list[dict[str, Any]]]) -> str:
    rows = []
    for trial in (2, 3):
        subset = records[trial]
        successes = sum(record["outcome"] == "success" for record in subset)
        low, high = wilson(successes, len(subset))
        rows.append(
            (
                trial,
                successes,
                len(subset),
                100 * successes / len(subset),
                100 * low,
                100 * high,
            )
        )
    plot_x, plot_width, maximum = 380, 1040, 55
    body: list[str] = []
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
        color = BLUE if trial == 2 else GREEN
        lo_x = plot_x + plot_width * low / maximum
        hi_x = plot_x + plot_width * high / maximum
        rate_x = plot_x + plot_width * rate / maximum
        body.extend(
            [
                f'<text class="label" x="60" y="{y + 5}">Trial {trial}</text>',
                f'<line x1="{lo_x:.1f}" y1="{y}" x2="{hi_x:.1f}" y2="{y}" stroke="{color}" stroke-width="7"/>',
                f'<circle cx="{rate_x:.1f}" cy="{y}" r="11" fill="{NAVY}"/>',
                f'<text class="value" x="{hi_x + 16:.1f}" y="{y + 5}">{successes}/{total} = {rate:.1f}% [{low:.2f}, {high:.2f}]</text>',
            ]
        )
    body.extend(
        [
            '<rect x="60" y="485" width="1420" height="72" rx="12" fill="#fef3c7"/>',
            '<text class="small" x="84" y="513">The observed endpoint declined by 7.5 percentage points. Descriptive Fisher exact p≈0.256.</text>',
            '<text class="small" x="84" y="539">Intervals and p-values quantify run-level sampling only; they do not adjust the compound design changes or clustered replicates.</text>',
        ]
    )
    return base_svg(
        "Primary endpoint: validator-confirmed success",
        "Finalized-run rate with descriptive Wilson 95% intervals",
        620,
        body,
        "Source: Trial 2 and Trial 3 finalized record.json metadata",
    )


def progress_ladders(records: dict[int, list[dict[str, Any]]]) -> str:
    tiers = ("none", "ran", "control", "marker")
    labels = ("NONE", "RAN", "CONTROL", "MARKER")
    colors = (LIGHT, BLUE, ORANGE, GREEN)
    body: list[str] = []
    for row, trial in enumerate((2, 3)):
        counts = collections.Counter(r["max_tier_reached"] for r in records[trial])
        total = len(records[trial])
        y = 235 + row * 190
        cursor = 340.0
        body.append(f'<text class="label" x="60" y="{y + 37}">Trial {trial} · n={total}</text>')
        for tier, label, color in zip(tiers, labels, colors):
            width = 1120 * counts[tier] / total
            body.append(
                f'<rect x="{cursor:.1f}" y="{y}" width="{width:.1f}" height="64" fill="{color}"/>'
            )
            if width > 75:
                css = "white" if tier not in ("none",) else "value"
                body.append(
                    f'<text class="{css}" x="{cursor + width / 2:.1f}" y="{y + 29}" text-anchor="middle">{label}</text>'
                )
                body.append(
                    f'<text class="{css}" x="{cursor + width / 2:.1f}" y="{y + 50}" text-anchor="middle">{counts[tier]} · {counts[tier] / total:.1%}</text>'
                )
            cursor += width
        validator = sum(validator_reached(r) for r in records[trial])
        success = sum(r["outcome"] == "success" for r in records[trial])
        body.append(
            f'<text class="small" x="340" y="{y + 91}">Validator/RAN+ {validator}/{total} ({validator / total:.1%}) · marker {success}/{total} ({success / total:.1%})</text>'
        )
    body.extend(
        [
            '<rect x="60" y="590" width="1420" height="78" rx="12" fill="#e0f2fe"/>',
            '<text class="small" x="84" y="620">Validator reach was nearly unchanged (75.0% → 76.0%), while marker success fell (37.0% → 29.5%).</text>',
            '<text class="small" x="84" y="646">Trial 3 has four refusal outcomes overlaid on 2 NONE and 2 RAN tiers; they are not a fifth tier.</text>',
        ]
    )
    return base_svg(
        "Progress ladders remained comparable, but conversion weakened",
        "Mutually exclusive maximum tiers in schema v5 (Trial 2) and v6 (Trial 3)",
        730,
        body,
        "Source: finalized max_tier_reached and validator fields",
    )


def dumbbell(
    records: dict[int, list[dict[str, Any]]],
    *,
    dimension: str,
    values: tuple[str, ...],
    title: str,
    premium_only: bool = False,
) -> str:
    plot_x, plot_width = 410, 1010
    body = [
        f'<rect x="690" y="120" width="18" height="18" rx="3" fill="{BLUE}"/><text class="legend" x="718" y="135">T2 validator</text>',
        f'<rect x="880" y="120" width="18" height="18" rx="3" fill="{TEAL}"/><text class="legend" x="908" y="135">T3 validator</text>',
        f'<rect x="1070" y="120" width="18" height="18" rx="3" fill="{PURPLE}"/><text class="legend" x="1098" y="135">T2 success</text>',
        f'<rect x="1245" y="120" width="18" height="18" rx="3" fill="{GREEN}"/><text class="legend" x="1273" y="135">T3 success</text>',
    ]
    for tick in range(5):
        x = plot_x + plot_width * tick / 4
        body.extend(
            [
                f'<line x1="{x}" y1="170" x2="{x}" y2="{230 + len(values) * 118}" stroke="#e2e8f0"/>',
                f'<text class="axis" x="{x}" y="160" text-anchor="middle">{tick * 25}%</text>',
            ]
        )
    for index, value in enumerate(values):
        kwargs = {dimension: value}
        groups = {
            trial: subset_shared(records[trial], **kwargs) for trial in (2, 3)
        }
        if premium_only:
            groups = {
                trial: [
                    record
                    for record in groups[trial]
                    if record["backend_handle"] in SHARED_PREMIUM
                ]
                for trial in (2, 3)
            }
        stats = {trial: rate_pair(groups[trial]) for trial in (2, 3)}
        y = 235 + index * 118
        rates = [
            100 * stats[2][1] / stats[2][0],
            100 * stats[3][1] / stats[3][0],
            100 * stats[2][2] / stats[2][0],
            100 * stats[3][2] / stats[3][0],
        ]
        xs = [plot_x + plot_width * rate / 100 for rate in rates]
        label = (
            BACKEND_LABELS[value] if dimension == "backend" else TARGET_LABELS[value]
        )
        body.extend(
            [
                svg_text(label, 60, y + 5, "label", width=28),
                f'<line x1="{min(xs):.1f}" y1="{y}" x2="{max(xs):.1f}" y2="{y}" stroke="#cbd5e1" stroke-width="5"/>',
            ]
        )
        for x, color in zip(xs, (BLUE, TEAL, PURPLE, GREEN)):
            body.append(f'<circle cx="{x:.1f}" cy="{y}" r="10" fill="{color}"/>')
        body.extend(
            [
                f'<text class="small" x="{plot_x}" y="{y + 37}">T2 n={stats[2][0]}: validator {stats[2][1]}, success {stats[2][2]}</text>',
                f'<text class="small" x="{plot_x + 470}" y="{y + 37}">T3 n={stats[3][0]}: validator {stats[3][1]}, success {stats[3][2]}</text>',
            ]
        )
    height = 320 + len(values) * 118
    return base_svg(
        title,
        (
            "Balanced Sonnet + GPT-5 cohort, collapsed over each trial’s nonmatching prompt arms"
            if premium_only
            else "Shared backend and target levels, collapsed over each trial’s nonmatching prompt arms"
        ),
        height,
        body,
        (
            "Source: finalized Sonnet and GPT-5 records on the three shared targets"
            if premium_only
            else "Source: finalized records; local rows have unequal target coverage and small n"
        ),
    )


def strategy_heatmap(records: dict[int, list[dict[str, Any]]]) -> str:
    strategies = TRIAL_STRATEGIES[2] + TRIAL_STRATEGIES[3]
    left, top, cell_w, cell_h = 325, 245, 245, 92
    body: list[str] = []
    for column, strategy in enumerate(strategies):
        body.append(
            svg_text(
                STRATEGY_LABELS[strategy],
                left + column * cell_w + (cell_w - 8) / 2,
                190,
                "label",
                width=19,
                anchor="middle",
            )
        )
    for row, backend in enumerate(SHARED_BACKENDS):
        y = top + row * cell_h
        body.append(
            svg_text(BACKEND_LABELS[backend], 60, y + 42, "label", width=24)
        )
        for column, strategy in enumerate(strategies):
            trial = 2 if strategy in TRIAL_STRATEGIES[2] else 3
            subset = [
                r
                for r in records[trial]
                if r["backend_handle"] == backend
                and r["binary_id"] in SHARED_TARGETS
                and r["prompting_strategy"] == strategy
            ]
            x = left + column * cell_w
            if not subset:
                body.extend(
                    [
                        f'<rect x="{x}" y="{y}" width="{cell_w - 8}" height="{cell_h - 8}" rx="10" fill="#f1f5f9"/>',
                        f'<text class="small" x="{x + (cell_w - 8) / 2}" y="{y + 48}" text-anchor="middle">not finalized</text>',
                    ]
                )
                continue
            successes = sum(r["outcome"] == "success" for r in subset)
            rate = successes / len(subset)
            red = round(241 + (22 - 241) * rate)
            green = round(245 + (163 - 245) * rate)
            blue = round(249 + (74 - 249) * rate)
            color = f"rgb({red},{green},{blue})"
            css = "white" if rate > 0.48 else "value"
            body.extend(
                [
                    f'<rect x="{x}" y="{y}" width="{cell_w - 8}" height="{cell_h - 8}" rx="10" fill="{color}"/>',
                    f'<text class="{css}" x="{x + (cell_w - 8) / 2}" y="{y + 36}" text-anchor="middle">{rate:.1%}</text>',
                    f'<text class="{css}" x="{x + (cell_w - 8) / 2}" y="{y + 61}" text-anchor="middle">{successes}/{len(subset)}</text>',
                ]
            )
    body.extend(
        [
            '<rect x="60" y="735" width="1420" height="82" rx="12" fill="#fef3c7"/>',
            '<text class="small" x="84" y="765">There is no shared prompting strategy between Trials 2 and 3. Columns are trial-specific arms, not matched treatments.</text>',
            '<text class="small" x="84" y="791">Rates use the three shared targets; missing Trial 3 local target blocks remain visibly unfilled.</text>',
        ]
    )
    return base_svg(
        "Backend × trial-specific prompting strategy",
        "Success rate on shared targets; this display replaces an invalid cross-trial strategy delta",
        880,
        body,
        "Source: finalized record.json metadata on ret2win, BroncoCTF, and ROPBench ex005",
    )


def grouped_tools(records: list[dict[str, Any]], trial: int) -> collections.Counter[str]:
    raw: collections.Counter[str] = collections.Counter()
    for record in records:
        raw.update(record.get("tool_call_counts", {}))
    grouped: collections.Counter[str] = collections.Counter()
    for tool, count in raw.items():
        if tool in ("enumerate_gadgets", "find_gadget"):
            group = "gadget search"
        elif tool == "run_exploit_script":
            group = "run script"
        elif tool == "submit_payload":
            group = "raw submit"
        elif tool.startswith("radare2_") or tool.startswith(("radace2_", "radae2_", "radale2_")):
            group = "radare2"
        elif tool.startswith("ropper_"):
            group = "ropper"
        elif tool.startswith("ghidra_"):
            group = "ghidra"
        elif tool.startswith("gdb_"):
            group = "gdb"
        elif tool.startswith("pwntools_"):
            group = "pwntools"
        else:
            group = "other"
        grouped[group] += count
    return grouped


def tool_composition(records: dict[int, list[dict[str, Any]]]) -> str:
    groups = (
        "gadget search",
        "run script",
        "raw submit",
        "radare2",
        "ropper",
        "ghidra",
        "gdb",
        "pwntools",
        "other",
    )
    colors = (BLUE, GREEN, ORANGE, TEAL, PURPLE, "#0891b2", SLATE, "#db2777", LIGHT)
    counts = {trial: grouped_tools(records[trial], trial) for trial in (2, 3)}
    body: list[str] = []
    for index, (group, color) in enumerate(zip(groups, colors)):
        row, column = divmod(index, 5)
        x, y = 280 + column * 250, 145 + row * 34
        body.extend(
            [
                f'<rect x="{x}" y="{y - 15}" width="18" height="18" rx="3" fill="{color}"/>',
                f'<text class="legend" x="{x + 27}" y="{y}">{group}</text>',
            ]
        )
    for row, trial in enumerate((2, 3)):
        y = 280 + row * 165
        total = sum(counts[trial].values())
        cursor = 300.0
        body.append(f'<text class="label" x="60" y="{y + 35}">Trial {trial}</text>')
        for group, color in zip(groups, colors):
            count = counts[trial].get(group, 0)
            width = 1180 * count / total
            if width:
                body.append(
                    f'<rect x="{cursor:.1f}" y="{y}" width="{width:.1f}" height="62" fill="{color}"/>'
                )
                share = count / total
                if width > 82:
                    css = "white" if color != LIGHT else "value"
                    body.extend(
                        [
                            f'<text class="{css}" x="{cursor + width / 2:.1f}" y="{y + 27}" text-anchor="middle">{group}</text>',
                            f'<text class="{css}" x="{cursor + width / 2:.1f}" y="{y + 49}" text-anchor="middle">{share:.1%}</text>',
                        ]
                    )
            cursor += width
        body.append(
            f'<text class="small" x="300" y="{y + 88}">{total:,} recorded calls · {total / len(records[trial]):.1f} per finalized record</text>'
        )
    body.extend(
        [
            '<rect x="60" y="585" width="1420" height="82" rx="12" fill="#e0f2fe"/>',
            '<text class="small" x="84" y="615">Trial 3 reduced the advertised surface from 22 to 8 tools and concentrated behavior in gadget search, script execution,</text>',
            '<text class="small" x="84" y="641">and radare2. Two WhiteRabbit outliers alone contributed 603 Trial 3 calls, so aggregate composition is not a typical-run profile.</text>',
        ]
    )
    return base_svg(
        "Tool use became narrower but more intensive",
        "Normalized shares of recorded tool calls",
        730,
        body,
        "Source: finalized RunRecord tool_call_counts; misspelled radare2 calls grouped with radare2",
    )


def conditional_conversion(records: dict[int, list[dict[str, Any]]]) -> str:
    groups = [
        ("All finalized", records[2], records[3]),
        (
            "Shared factor levels",
            subset_shared(records[2]),
            subset_shared(records[3]),
        ),
        (
            "Shared premium blocks",
            subset_shared(records[2], premium_only=True),
            subset_shared(records[3], premium_only=True),
        ),
    ]
    body = [
        f'<rect x="900" y="120" width="18" height="18" rx="3" fill="{BLUE}"/><text class="legend" x="928" y="135">Trial 2</text>',
        f'<rect x="1070" y="120" width="18" height="18" rx="3" fill="{GREEN}"/><text class="legend" x="1098" y="135">Trial 3</text>',
    ]
    x0, plot_width = 450, 970
    for tick in range(6):
        x = x0 + plot_width * tick / 5
        body.extend(
            [
                f'<line x1="{x}" y1="170" x2="{x}" y2="635" stroke="#e2e8f0"/>',
                f'<text class="axis" x="{x}" y="160" text-anchor="middle">{tick * 20}%</text>',
            ]
        )
    for index, (label, two, three) in enumerate(groups):
        y = 225 + index * 150
        values, displays = [], []
        for subset in (two, three):
            _, reached, success = rate_pair(subset)
            values.append(100 * success / reached if reached else 0)
            displays.append(f"{success}/{reached}")
        body.extend(
            [
                f'<text class="label" x="60" y="{y + 30}">{label}</text>',
                f'<rect x="{x0}" y="{y}" width="{plot_width * values[0] / 100:.1f}" height="36" rx="6" fill="{BLUE}"/>',
                f'<rect x="{x0}" y="{y + 48}" width="{plot_width * values[1] / 100:.1f}" height="36" rx="6" fill="{GREEN}"/>',
                f'<text class="value" x="{x0 + plot_width * values[0] / 100 + 12:.1f}" y="{y + 24}">{displays[0]} = {values[0]:.1f}%</text>',
                f'<text class="value" x="{x0 + plot_width * values[1] / 100 + 12:.1f}" y="{y + 72}">{displays[1]} = {values[1]:.1f}%</text>',
            ]
        )
    return base_svg(
        "Conditional conversion after reaching the validator",
        "Success divided by records with a validator object",
        710,
        body,
        "Source: finalized record metadata; shared blocks collapse nonmatching prompt arms",
    )


def ecdf_path(
    values: list[float],
    x0: float,
    y0: float,
    width: float,
    height: float,
    maximum: float,
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
        ("T2 success", [r for r in records[2] if r["outcome"] == "success"], BLUE),
        ("T2 failure", [r for r in records[2] if r["outcome"] != "success"], PURPLE),
        ("T3 success", [r for r in records[3] if r["outcome"] == "success"], GREEN),
        ("T3 nonsuccess", [r for r in records[3] if r["outcome"] != "success"], RED),
    ]
    panels: list[tuple[str, Callable[[dict[str, Any]], float], float, str]] = [
        ("Total tokens", lambda r: float(r["tokens"]["total"]), 1_000_000, "tokens"),
        ("Iterations", lambda r: float(r["iterations"]), 100, "turns"),
        ("Wall time", lambda r: float(r["wall_clock_seconds"]), 1_300, "seconds"),
    ]
    body: list[str] = []
    for index, (label, _, color) in enumerate(series):
        x = 560 + index * 220
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
                f'<rect x="{x0 - 20}" y="180" width="470" height="575" rx="14" fill="#fff" stroke="#cbd5e1" stroke-width="2"/>',
                f'<text class="label" x="{x0}" y="212">{panel_title}</text>',
                f'<line x1="{x0}" y1="{y0 + panel_h}" x2="{x0 + panel_w}" y2="{y0 + panel_h}" stroke="#94a3b8"/>',
                f'<line x1="{x0}" y1="{y0}" x2="{x0}" y2="{y0 + panel_h}" stroke="#94a3b8"/>',
            ]
        )
        for tick in range(5):
            x = x0 + panel_w * tick / 4
            value = maximum * tick / 4
            display = f"{value/1000:.0f}k" if panel_title == "Total tokens" else f"{value:g}"
            body.extend(
                [
                    f'<line x1="{x}" y1="{y0}" x2="{x}" y2="{y0 + panel_h}" stroke="#e2e8f0"/>',
                    f'<text class="axis" x="{x}" y="{y0 + panel_h + 25}" text-anchor="middle">{display}</text>',
                ]
            )
        for q in (0, 0.5, 1):
            y = y0 + panel_h * (1 - q)
            body.append(
                f'<text class="axis" x="{x0 - 12}" y="{y + 5}" text-anchor="end">{q:.0%}</text>'
            )
        for series_index, (label, subset, color) in enumerate(series):
            values = [getter(record) for record in subset]
            body.append(
                f'<path d="{ecdf_path(values, x0, y0, panel_w, panel_h, maximum)}" fill="none" stroke="{color}" stroke-width="4"/>'
            )
            median = statistics.median(values)
            body.append(
                f'<text class="small" x="{x0}" y="{657 + series_index * 19}">{label}: {median:,.1f} {unit}</text>'
            )
    return base_svg(
        "Resource-use distributions by trial and outcome",
        "Empirical cumulative distributions; values above panel maxima are clipped at the right edge",
        840,
        body,
        "Source: finalized RunRecord token, iteration, and wall-clock metadata",
    )


def coverage_color(rate: float) -> str:
    ratio = max(0, min(1, rate))
    r = round(241 + (37 - 241) * ratio)
    g = round(245 + (99 - 245) * ratio)
    b = round(249 + (235 - 249) * ratio)
    return f"rgb({r},{g},{b})"


def coverage_mosaic(records: dict[int, list[dict[str, Any]]]) -> str:
    body: list[str] = []
    panels = ((2, 215, 270), (3, 690, 122))
    for trial, top, cell_w in panels:
        backends = TRIAL_BACKENDS[trial]
        targets = TRIAL_TARGETS[trial]
        planned_per_cell = REPLICATES[trial] * len(TRIAL_STRATEGIES[trial])
        counts = collections.Counter(
            (r["backend_handle"], r["binary_id"]) for r in records[trial]
        )
        left, cell_h = 315, 46
        body.append(
            f'<text class="label" x="60" y="{top - 57}">Trial {trial} · {planned_per_cell} planned runs per backend-target block</text>'
        )
        for column, target in enumerate(targets):
            x = left + column * cell_w + (cell_w - 4) / 2
            body.append(
                f'<text class="axis" x="{x}" y="{top - 14}" text-anchor="middle">{SHORT_TARGET_LABELS[target]}</text>'
            )
        for row, backend in enumerate(backends):
            y = top + row * cell_h
            body.append(
                f'<text class="small" x="60" y="{y + 28}">{BACKEND_LABELS[backend]}</text>'
            )
            for column, target in enumerate(targets):
                count = counts[(backend, target)]
                rate = count / planned_per_cell
                x = left + column * cell_w
                body.extend(
                    [
                        f'<rect x="{x}" y="{y}" width="{cell_w - 4}" height="{cell_h - 4}" rx="4" fill="{coverage_color(rate)}"/>',
                        f'<text class="{"white" if rate > 0.55 else "value"}" x="{x + (cell_w - 4) / 2}" y="{y + 27}" text-anchor="middle">{count}/{planned_per_cell}</text>',
                    ]
                )
    body.extend(
        [
            '<rect x="1150" y="1005" width="18" height="18" rx="3" fill="#f1f5f9"/><text class="small" x="1178" y="1020">0%</text>',
            '<rect x="1240" y="1005" width="18" height="18" rx="3" fill="#2563eb"/><text class="small" x="1268" y="1020">100% finalized</text>',
        ]
    )
    return base_svg(
        "Matrix coverage remained structured and trial-specific",
        "Finalized records divided by planned runs for each backend-target block",
        1080,
        body,
        "Source: Trial 2 experiments.yaml; Trial 3 matrix reconstructed from launcher logs and records",
    )


def bronco_milestones(records: dict[int, list[dict[str, Any]]]) -> str:
    milestones = ("Gate 1+", "Gate 3+", "MARKER")
    counts: dict[int, tuple[int, int, int]] = {}
    totals: dict[int, int] = {}
    for trial in (2, 3):
        subset = [
            r for r in records[trial] if r["binary_id"] == "broncoctf2026-proper-pwning"
        ]
        totals[trial] = len(subset)
        gate1 = sum(
            "Gate 1 opens" in ((r.get("validator") or {}).get("stdout_excerpt") or "")
            for r in subset
        )
        gate3 = sum(
            "Gate 3 opens" in ((r.get("validator") or {}).get("stdout_excerpt") or "")
            for r in subset
        )
        marker = sum(r["outcome"] == "success" for r in subset)
        counts[trial] = (gate1, gate3, marker)
    body = [
        f'<rect x="900" y="120" width="18" height="18" rx="3" fill="{BLUE}"/><text class="legend" x="928" y="135">Trial 2</text>',
        f'<rect x="1070" y="120" width="18" height="18" rx="3" fill="{GREEN}"/><text class="legend" x="1098" y="135">Trial 3</text>',
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
        rates = {
            trial: 100 * counts[trial][index] / totals[trial] for trial in (2, 3)
        }
        body.extend(
            [
                f'<text class="label" x="60" y="{y + 28}">{milestone}</text>',
                f'<rect x="{x0}" y="{y}" width="{plot_width * rates[2] / 100:.1f}" height="32" rx="5" fill="{BLUE}"/>',
                f'<rect x="{x0}" y="{y + 44}" width="{plot_width * rates[3] / 100:.1f}" height="32" rx="5" fill="{GREEN}"/>',
                f'<text class="value" x="{x0 + plot_width * rates[2] / 100 + 10:.1f}" y="{y + 22}">{counts[2][index]}/{totals[2]} = {rates[2]:.1f}%</text>',
                f'<text class="value" x="{x0 + plot_width * rates[3] / 100 + 10:.1f}" y="{y + 66}">{counts[3][index]}/{totals[3]} = {rates[3]:.1f}%</text>',
            ]
        )
    body.extend(
        [
            '<rect x="60" y="555" width="1420" height="82" rx="12" fill="#fef3c7"/>',
            '<text class="small" x="84" y="585">Both trials use retained final-record validator stdout here. Trial 3’s eight marker records contain all retained gate text;</text>',
            '<text class="small" x="84" y="611">its four nonmarkers retain none. This is a record-retention measure as well as a task-progress measure.</text>',
        ]
    )
    return base_svg(
        "BroncoCTF milestone progression",
        "Cumulative milestone shares within each trial’s finalized BroncoCTF records",
        700,
        body,
        "Source: finalized validator stdout excerpts and outcome fields",
    )


def main() -> None:
    records = {trial: load_records(path) for trial, path in TRIALS.items()}
    assert len(records[2]) == 92
    assert len(records[3]) == 146
    assert sum(r["outcome"] == "success" for r in records[2]) == 34
    assert sum(r["outcome"] == "success" for r in records[3]) == 43

    write("01_primary_endpoint_forest.svg", primary_endpoint(records))
    write("02_progress_ladders.svg", progress_ladders(records))
    write(
        "03_shared_backend_dumbbell.svg",
        dumbbell(
            records,
            dimension="backend",
            values=SHARED_BACKENDS,
            title="Shared-backend validator reach and success",
        ),
    )
    write(
        "04_shared_target_conversion.svg",
        dumbbell(
            records,
            dimension="target",
            values=SHARED_TARGETS,
            title="Shared-target validator reach and success",
            premium_only=True,
        ),
    )
    write("05_backend_strategy_delta_heatmap.svg", strategy_heatmap(records))
    write("06_tool_use_composition.svg", tool_composition(records))
    write("07_conditional_conversion.svg", conditional_conversion(records))
    write("08_resource_ecdfs.svg", resource_ecdfs(records))
    write("09_matrix_coverage_mosaic.svg", coverage_mosaic(records))
    write("10_bronco_milestones.svg", bronco_milestones(records))


if __name__ == "__main__":
    main()
