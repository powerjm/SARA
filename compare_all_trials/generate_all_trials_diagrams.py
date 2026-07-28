"""Generate full-matrix and premium-model diagrams for Trials 1–3.

Only finalized ``runs/*/record.json`` members are opened. Trial 1 tool totals
are aggregate values reported by its metadata/log analysis because schema v4
did not store per-record tool counts. No submission artifact is opened.
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
ARCHIVES = {
    1: ROOT / "runs_for_record_trial_1" / "runs.tgz",
    2: ROOT / "runs_for_record_trial_2" / "runz.tgz",
    3: ROOT / "runs_for_record_trial_3" / "runs.tgz",
}
PLANNED = {1: 2200, 2: 144, 3: 216}
PARTIALS = {1: 341, 2: 4, 3: 3}
PREMIUM = {
    1: ("claude-sonnet", "claude-opus", "gpt-5", "gemini-pro-latest"),
    2: ("claude-sonnet", "gpt-5"),
    3: ("claude-sonnet", "claude-opus", "gpt-5"),
}
SHARED_PREMIUM = ("claude-sonnet", "gpt-5")
SHARED_TARGETS = (
    "broncoctf2026-proper-pwning",
    "ropbench-synth-ex005",
)
BACKENDS = (
    "claude-sonnet",
    "claude-opus",
    "gpt-5",
    "gemini-pro-latest",
    "gpt-oss-20b",
    "qwen3-coder-30b",
    "qwen2.5-coder-32b",
    "devstral-small",
    "qwen3-30b-abliterated",
    "whiterabbitneo-v3-7b",
    "dolphin-3.0-mistral-24b",
)
BACKEND_LABEL = {
    "claude-sonnet": "Claude Sonnet",
    "claude-opus": "Claude Opus",
    "gpt-5": "GPT-5",
    "gemini-pro-latest": "Gemini Pro",
    "gpt-oss-20b": "GPT-OSS 20B",
    "qwen3-coder-30b": "Qwen3 Coder 30B",
    "qwen2.5-coder-32b": "Qwen2.5 Coder 32B",
    "devstral-small": "Devstral Small",
    "qwen3-30b-abliterated": "Qwen3 Abliterated",
    "whiterabbitneo-v3-7b": "WhiteRabbitNeo 7B",
    "dolphin-3.0-mistral-24b": "Dolphin Mistral 24B",
}
TARGETS = (
    "ret2win-baseline",
    "broncoctf2026-proper-pwning",
    "cgc-cadet-00001",
    "cgc-cromu-00004",
    "cgc-eagle-00005",
    "cgc-nrfin-00056",
    "ropbench-synth-ex002",
    "ropbench-synth-ex005",
    "ropbench-synth-ex010",
    "ropbench-synth-ex020",
    "ropbench-synth-ex101",
)
TARGET_LABEL = {
    "ret2win-baseline": "ret2win",
    "broncoctf2026-proper-pwning": "BroncoCTF",
    "cgc-cadet-00001": "CGC CADET",
    "cgc-cromu-00004": "CGC CROMU",
    "cgc-eagle-00005": "CGC EAGLE",
    "cgc-nrfin-00056": "CGC NRFIN",
    "ropbench-synth-ex002": "ROPBench ex002",
    "ropbench-synth-ex005": "ROPBench ex005",
    "ropbench-synth-ex010": "ROPBench ex010",
    "ropbench-synth-ex020": "ROPBench ex020",
    "ropbench-synth-ex101": "ROPBench ex101",
}

WIDTH = 1600
NAVY = "#172554"
BLUE = "#2563eb"
PURPLE = "#7c3aed"
GREEN = "#16a34a"
TEAL = "#0f766e"
ORANGE = "#f59e0b"
RED = "#dc2626"
SLATE = "#94a3b8"
LIGHT = "#e2e8f0"
MUTED = "#64748b"
TRIAL_COLOR = {1: SLATE, 2: BLUE, 3: GREEN}


def load_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with tarfile.open(path, "r:gz") as archive:
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
    return records


def backend(record: dict[str, Any]) -> str:
    return record.get("backend_handle") or record["backend"]["name"]


def success(record: dict[str, Any]) -> bool:
    return record["outcome"] == "success"


def validator(record: dict[str, Any]) -> bool:
    return record.get("validator") is not None


def wilson(k: int, n: int, z: float = 1.95996398454) -> tuple[float, float]:
    denominator = 1 + z * z / n
    centre = (k / n + z * z / (2 * n)) / denominator
    spread = (
        z
        * math.sqrt(k * (n - k) / n**3 + z * z / (4 * n * n))
        / denominator
    )
    return max(0.0, centre - spread), min(1.0, centre + spread)


def subset_premium(trial: int, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [record for record in records if backend(record) in PREMIUM[trial]]


def subset_core(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        record
        for record in records
        if backend(record) in SHARED_PREMIUM
        and record["binary_id"] in SHARED_TARGETS
    ]


def median(records: list[dict[str, Any]], getter: Callable[[dict[str, Any]], float]) -> float:
    return statistics.median(getter(record) for record in records)


def svg_text(
    value: str,
    x: float,
    y: float,
    css: str,
    *,
    width: int = 30,
    anchor: str = "start",
    line_height: int = 20,
) -> str:
    lines = textwrap.wrap(value, width=width, break_long_words=False) or [value]
    spans = [
        f'<tspan x="{x:.1f}" dy="{0 if i == 0 else line_height}">{escape(line)}</tspan>'
        for i, line in enumerate(lines)
    ]
    return (
        f'<text class="{css}" x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}">'
        + "".join(spans)
        + "</text>"
    )


def base_svg(
    title: str, subtitle: str, height: int, body: list[str], source: str
) -> str:
    title_lines = textwrap.wrap(title, width=76, break_long_words=False)
    offset = 42 * (len(title_lines) - 1)
    final_height = height + offset
    title_markup = [
        f'<text class="title" x="60" y="{57 + i * 42}">{escape(line)}</text>'
        for i, line in enumerate(title_lines)
    ]
    subtitle_y = 57 + len(title_lines) * 42 + 4
    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{final_height}" viewBox="0 0 {WIDTH} {final_height}" role="img">',
            f"<title>{escape(title)}</title>",
            """<style>
 .title{font:700 34px system-ui,sans-serif;fill:#172554}
 .sub{font:17px system-ui,sans-serif;fill:#475569}
 .label{font:650 17px system-ui,sans-serif;fill:#1e293b}
 .small{font:15px system-ui,sans-serif;fill:#64748b}
 .value{font:700 15px system-ui,sans-serif;fill:#172554}
 .legend{font:15px system-ui,sans-serif;fill:#334155}
 .axis{font:14px system-ui,sans-serif;fill:#64748b}
 .white{font:700 15px system-ui,sans-serif;fill:#fff}
 .source{font:14px system-ui,sans-serif;fill:#64748b}
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
    rsvg.rsvg_handle_new_from_file.argtypes = [ctypes.c_char_p, ctypes.c_void_p]
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
        ctypes.c_void_p,
    ]
    rsvg.rsvg_handle_render_document.restype = ctypes.c_bool
    cairo.cairo_image_surface_create.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int]
    cairo.cairo_image_surface_create.restype = ctypes.c_void_p
    cairo.cairo_create.argtypes = [ctypes.c_void_p]
    cairo.cairo_create.restype = ctypes.c_void_p
    cairo.cairo_surface_write_to_png.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    cairo.cairo_destroy.argtypes = [ctypes.c_void_p]
    cairo.cairo_surface_destroy.argtypes = [ctypes.c_void_p]
    gobject.g_object_unref.argtypes = [ctypes.c_void_p]
    handle = rsvg.rsvg_handle_new_from_file(str(svg_path).encode(), None)
    if not handle:
        raise RuntimeError(f"cannot load {svg_path}")
    width, height = ctypes.c_double(), ctypes.c_double()
    if not rsvg.rsvg_handle_get_intrinsic_size_in_pixels(
        handle, ctypes.byref(width), ctypes.byref(height)
    ):
        raise RuntimeError(f"cannot size {svg_path}")
    surface = cairo.cairo_image_surface_create(0, round(width.value), round(height.value))
    context = cairo.cairo_create(surface)
    viewport = RsvgRectangle(0, 0, width.value, height.value)
    if not rsvg.rsvg_handle_render_document(
        handle, context, ctypes.byref(viewport), None
    ):
        raise RuntimeError(f"cannot render {svg_path}")
    cairo.cairo_surface_write_to_png(
        surface, str(svg_path.with_suffix(".png")).encode()
    )
    cairo.cairo_destroy(context)
    cairo.cairo_surface_destroy(surface)
    gobject.g_object_unref(handle)


def write(name: str, content: str) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT / name
    path.write_text(content)
    render_png(path)


def endpoint_forest(
    records: dict[int, list[dict[str, Any]]],
    selector: Callable[[int, list[dict[str, Any]]], list[dict[str, Any]]],
    *,
    title: str,
    subtitle: str,
    source: str,
    maximum: float = 0.85,
) -> str:
    body: list[str] = []
    x0, plot_width = 380, 1030
    for tick in range(6):
        x = x0 + plot_width * tick / 5
        body.extend(
            [
                f'<line x1="{x}" y1="175" x2="{x}" y2="530" stroke="#e2e8f0"/>',
                f'<text class="axis" x="{x}" y="164" text-anchor="middle">{maximum * tick / 5:.0%}</text>',
            ]
        )
    for i, trial in enumerate((1, 2, 3)):
        subset = selector(trial, records[trial])
        n, k = len(subset), sum(success(r) for r in subset)
        low, high = wilson(k, n)
        y = 240 + i * 125
        body.extend(
            [
                f'<text class="label" x="60" y="{y + 6}">Trial {trial}</text>',
                f'<line x1="{x0 + plot_width * low / maximum:.1f}" y1="{y}" x2="{x0 + plot_width * high / maximum:.1f}" y2="{y}" stroke="{TRIAL_COLOR[trial]}" stroke-width="7"/>',
                f'<circle cx="{x0 + plot_width * (k / n) / maximum:.1f}" cy="{y}" r="12" fill="{NAVY}"/>',
                f'<text class="value" x="{min(x0 + plot_width * (k / n) / maximum + 25, 1240):.1f}" y="{y + 6}">{k}/{n} = {k/n:.1%} [{low:.2%}, {high:.2%}]</text>',
            ]
        )
    body.extend(
        [
            '<rect x="60" y="560" width="1420" height="72" rx="12" fill="#fef3c7"/>',
            '<text class="small" x="84" y="590">Wilson intervals describe run-level sampling only. They do not adjust for clustered replicates, structured attrition,</text>',
            '<text class="small" x="84" y="616">or changes in targets, backends, prompts, tools, schemas, and resource envelopes.</text>',
        ]
    )
    return base_svg(title, subtitle, 690, body, source)


def progress(records: dict[int, list[dict[str, Any]]]) -> str:
    body: list[str] = []
    body.extend(
        [
            f'<rect x="930" y="120" width="18" height="18" rx="3" fill="{TEAL}"/><text class="legend" x="958" y="135">Validator reach</text>',
            f'<rect x="1150" y="120" width="18" height="18" rx="3" fill="{GREEN}"/><text class="legend" x="1178" y="135">Marker success</text>',
        ]
    )
    x0, width = 400, 1010
    for tick in range(6):
        x = x0 + width * tick / 5
        body.extend(
            [
                f'<line x1="{x}" y1="170" x2="{x}" y2="570" stroke="#e2e8f0"/>',
                f'<text class="axis" x="{x}" y="160" text-anchor="middle">{tick*20}%</text>',
            ]
        )
    for i, trial in enumerate((1, 2, 3)):
        subset = records[trial]
        n = len(subset)
        reached = sum(validator(r) for r in subset)
        marker = sum(success(r) for r in subset)
        y = 225 + i * 125
        body.extend(
            [
                f'<text class="label" x="60" y="{y + 30}">Trial {trial}</text>',
                f'<rect x="{x0}" y="{y}" width="{width*reached/n:.1f}" height="34" rx="5" fill="{TEAL}"/>',
                f'<rect x="{x0}" y="{y+45}" width="{width*marker/n:.1f}" height="34" rx="5" fill="{GREEN}"/>',
                f'<text class="value" x="{x0+width*reached/n+10:.1f}" y="{y+23}">{reached}/{n} = {reached/n:.1%}</text>',
                f'<text class="value" x="{x0+width*marker/n+10:.1f}" y="{y+68}">{marker}/{n} = {marker/n:.1%}</text>',
            ]
        )
    return base_svg(
        "Full-matrix engagement and end-to-end conversion",
        "Validator-result prevalence and validator-confirmed marker success",
        650,
        body,
        "Source: finalized record.json validator and outcome fields",
    )


def resource_bars(
    records: dict[int, list[dict[str, Any]]],
    selector: Callable[[int, list[dict[str, Any]]], list[dict[str, Any]]],
    *,
    title: str,
    source: str,
) -> str:
    metrics = [
        ("Median total tokens", lambda r: r["tokens"]["total"], 500_000, "k"),
        ("Median wall time", lambda r: r["wall_clock_seconds"], 350, "s"),
        ("Median iterations", lambda r: r["iterations"], 30, ""),
    ]
    body: list[str] = []
    for p, (label, getter, maximum, unit) in enumerate(metrics):
        left = 75 + p * 510
        body.extend(
            [
                f'<rect x="{left-15}" y="160" width="470" height="450" rx="14" fill="#fff" stroke="#cbd5e1" stroke-width="2"/>',
                f'<text class="label" x="{left+10}" y="200">{label}</text>',
            ]
        )
        for i, trial in enumerate((1, 2, 3)):
            subset = selector(trial, records[trial])
            value = median(subset, getter)
            bar = min(value / maximum, 1) * 350
            y = 255 + i * 105
            display = (
                f"{value/1000:,.1f}k"
                if unit == "k"
                else f"{value:,.1f}{unit}"
            )
            body.extend(
                [
                    f'<text class="label" x="{left+10}" y="{y+24}">T{trial}</text>',
                    f'<rect x="{left+75}" y="{y}" width="{bar:.1f}" height="34" rx="5" fill="{TRIAL_COLOR[trial]}"/>',
                    f'<text class="value" x="{left+85+bar:.1f}" y="{y+23}">{display}</text>',
                ]
            )
    return base_svg(
        title,
        "Medians among finalized records; axes are independently scaled by panel",
        680,
        body,
        source,
    )


def coverage(records: dict[int, list[dict[str, Any]]]) -> str:
    body: list[str] = [
        f'<rect x="810" y="120" width="18" height="18" fill="{BLUE}"/><text class="legend" x="838" y="135">Finalized</text>',
        f'<rect x="985" y="120" width="18" height="18" fill="{ORANGE}"/><text class="legend" x="1013" y="135">Initiated, unfinalized</text>',
        f'<rect x="1240" y="120" width="18" height="18" fill="{LIGHT}"/><text class="legend" x="1268" y="135">Never started</text>',
    ]
    x0, width = 330, 1100
    for i, trial in enumerate((1, 2, 3)):
        final = len(records[trial])
        partial = PARTIALS[trial]
        absent = PLANNED[trial] - final - partial
        y = 220 + i * 130
        cursor = x0
        body.append(f'<text class="label" x="60" y="{y+30}">Trial {trial}</text>')
        for value, color in ((final, BLUE), (partial, ORANGE), (absent, LIGHT)):
            segment = width * value / PLANNED[trial]
            body.append(
                f'<rect x="{cursor:.1f}" y="{y}" width="{segment:.1f}" height="54" fill="{color}"/>'
            )
            cursor += segment
        body.extend(
            [
                f'<text class="small" x="{x0}" y="{y+82}">{final:,}/{PLANNED[trial]:,} finalized ({final/PLANNED[trial]:.1%}) · {partial:,} partial · {absent:,} absent</text>',
            ]
        )
    body.extend(
        [
            '<rect x="60" y="590" width="1420" height="72" rx="12" fill="#fef3c7"/>',
            '<text class="small" x="84" y="620">Coverage is structured by backend, target order, provider/cost interruption, and batch execution. Finalized records are not</text>',
            '<text class="small" x="84" y="646">simple random samples of their planned matrices.</text>',
        ]
    )
    return base_svg(
        "Planned-matrix accounting across all trials",
        "Finalized, initiated-but-unfinalized, and never-started planned runs",
        720,
        body,
        "Source: experiment matrices and archive directory accounting",
    )


def heat_color(rate: float) -> str:
    ratio = max(0, min(1, rate))
    red = round(241 + (22 - 241) * ratio)
    green = round(245 + (163 - 245) * ratio)
    blue = round(249 + (74 - 249) * ratio)
    return f"rgb({red},{green},{blue})"


def matrix_heatmap(
    records: dict[int, list[dict[str, Any]]],
    *,
    rows: tuple[str, ...],
    row_label: dict[str, str],
    subsetter: Callable[[int, list[dict[str, Any]], str], list[dict[str, Any]]],
    title: str,
    subtitle: str,
    source: str,
) -> str:
    left, top, cell_w, cell_h = 610, 200, 285, 66
    body: list[str] = []
    for col, trial in enumerate((1, 2, 3)):
        body.append(
            f'<text class="label" x="{left+col*cell_w+(cell_w-10)/2}" y="165" text-anchor="middle">Trial {trial}</text>'
        )
    for row, value in enumerate(rows):
        y = top + row * cell_h
        body.append(svg_text(row_label[value], 60, y + 36, "label", width=32))
        for col, trial in enumerate((1, 2, 3)):
            subset = subsetter(trial, records[trial], value)
            x = left + col * cell_w
            if not subset:
                body.extend(
                    [
                        f'<rect x="{x}" y="{y}" width="{cell_w-10}" height="{cell_h-7}" rx="8" fill="#e2e8f0"/>',
                        f'<text class="small" x="{x+(cell_w-10)/2}" y="{y+36}" text-anchor="middle">not represented</text>',
                    ]
                )
                continue
            k, n = sum(success(r) for r in subset), len(subset)
            color = heat_color(k / n)
            css = "white" if k / n > 0.48 else "value"
            body.extend(
                [
                    f'<rect x="{x}" y="{y}" width="{cell_w-10}" height="{cell_h-7}" rx="8" fill="{color}"/>',
                    f'<text class="{css}" x="{x+(cell_w-10)/2}" y="{y+27}" text-anchor="middle">{k/n:.1%}</text>',
                    f'<text class="{css}" x="{x+(cell_w-10)/2}" y="{y+48}" text-anchor="middle">{k}/{n}</text>',
                ]
            )
    height = 285 + len(rows) * cell_h
    return base_svg(title, subtitle, height, body, source)


def premium_progress(records: dict[int, list[dict[str, Any]]]) -> str:
    premium = {t: subset_premium(t, rs) for t, rs in records.items()}
    body: list[str] = []
    x0, width = 430, 960
    for tick in range(6):
        x = x0 + width * tick / 5
        body.extend(
            [
                f'<line x1="{x}" y1="170" x2="{x}" y2="590" stroke="#e2e8f0"/>',
                f'<text class="axis" x="{x}" y="160" text-anchor="middle">{tick*20}%</text>',
            ]
        )
    for i, trial in enumerate((1, 2, 3)):
        subset = premium[trial]
        n = len(subset)
        reached = sum(validator(r) for r in subset)
        marker = sum(success(r) for r in subset)
        conditional = marker / reached if reached else 0
        y = 220 + i * 125
        body.extend(
            [
                f'<text class="label" x="60" y="{y+8}">Trial {trial}</text>',
                f'<line x1="{x0}" y1="{y}" x2="{x0+width*reached/n:.1f}" y2="{y}" stroke="{TEAL}" stroke-width="28"/>',
                f'<circle cx="{x0+width*marker/n:.1f}" cy="{y}" r="12" fill="{GREEN}"/>',
                f'<text class="small" x="{x0}" y="{y+43}">validator {reached}/{n} ({reached/n:.1%}) · marker {marker}/{n} ({marker/n:.1%}) · marker | validator {conditional:.1%}</text>',
            ]
        )
    body.extend(
        [
            f'<rect x="930" y="120" width="18" height="18" fill="{TEAL}"/><text class="legend" x="958" y="135">Validator reach</text>',
            f'<circle cx="1170" cy="129" r="9" fill="{GREEN}"/><text class="legend" x="1190" y="135">Marker rate</text>',
        ]
    )
    return base_svg(
        "Premium-class engagement and success",
        "Each trial’s configured hosted/frontier class; membership changes by trial",
        670,
        body,
        "Source: finalized premium-backend records; premium composition is trial-specific",
    )


def tool_groups(records: list[dict[str, Any]], trial: int) -> collections.Counter[str]:
    if trial == 1:
        return collections.Counter({"enumerate": 25406, "submit": 6664})
    raw: collections.Counter[str] = collections.Counter()
    for record in records:
        raw.update(record.get("tool_call_counts") or {})
    grouped: collections.Counter[str] = collections.Counter()
    for name, count in raw.items():
        if name in ("enumerate_gadgets", "find_gadget"):
            key = "search / enumerate"
        elif name == "run_exploit_script":
            key = "execute"
        elif name == "submit_payload":
            key = "submit"
        elif name.startswith(("radare2_", "radace2_", "radae2_", "radale2_")):
            key = "disassembly / analysis"
        elif name.startswith(("gdb_", "ghidra_", "ropper_", "pwntools_")):
            key = "debug / frameworks"
        else:
            key = "other"
        grouped[key] += count
    return grouped


def tool_evolution(records: dict[int, list[dict[str, Any]]]) -> str:
    colors = {
        "enumerate": BLUE,
        "search / enumerate": BLUE,
        "execute": GREEN,
        "submit": ORANGE,
        "disassembly / analysis": TEAL,
        "debug / frameworks": PURPLE,
        "other": LIGHT,
    }
    body: list[str] = []
    left, width = 330, 1100
    for i, trial in enumerate((1, 2, 3)):
        groups = tool_groups(records[trial], trial)
        total = sum(groups.values())
        y = 220 + i * 130
        cursor = left
        body.append(f'<text class="label" x="60" y="{y+30}">Trial {trial}</text>')
        for name, count in groups.most_common():
            segment = width * count / total
            color = colors.get(name, LIGHT)
            body.append(
                f'<rect x="{cursor:.1f}" y="{y}" width="{segment:.1f}" height="56" fill="{color}"/>'
            )
            if segment > 150:
                body.extend(
                    [
                        f'<text class="white" x="{cursor+segment/2:.1f}" y="{y+25}" text-anchor="middle">{name}</text>',
                        f'<text class="white" x="{cursor+segment/2:.1f}" y="{y+46}" text-anchor="middle">{count/total:.1%}</text>',
                    ]
                )
            cursor += segment
        body.append(
            f'<text class="small" x="{left}" y="{y+82}">{total:,} calls · {total/len(records[trial]):.1f} per finalized record</text>'
        )
    body.extend(
        [
            '<rect x="60" y="605" width="1420" height="72" rx="12" fill="#e0f2fe"/>',
            '<text class="small" x="84" y="635">Trial 1 exposed two tools; Trial 2 expanded to 22; Trial 3 curated eight. Call intensity rose across trials, but tool identity,</text>',
            '<text class="small" x="84" y="661">record schema, target/model composition, and resource limits also changed.</text>',
        ]
    )
    return base_svg(
        "Tool-surface and recorded-call evolution",
        "Normalized composition and aggregate call intensity",
        735,
        body,
        "Source: Trial 1 log-derived aggregate report; Trial 2/3 record.json tool_call_counts",
    )


def main() -> None:
    records = {trial: load_records(path) for trial, path in ARCHIVES.items()}
    assert {trial: len(value) for trial, value in records.items()} == {
        1: 1755,
        2: 92,
        3: 146,
    }
    assert {trial: sum(success(r) for r in value) for trial, value in records.items()} == {
        1: 0,
        2: 34,
        3: 43,
    }

    write(
        "01_full_matrix_endpoint_forest.svg",
        endpoint_forest(
            records,
            lambda _t, rs: rs,
            title="Full realized matrices: validator-confirmed success",
            subtitle="Finalized-run marker rate with descriptive Wilson 95% intervals",
            source="Source: finalized record.json outcome metadata",
            maximum=0.55,
        ),
    )
    write("02_full_matrix_progress.svg", progress(records))
    write(
        "03_full_matrix_resources.svg",
        resource_bars(
            records,
            lambda _t, rs: rs,
            title="Full-matrix resource profiles",
            source="Source: finalized token, wall-clock, and iteration metadata",
        ),
    )
    write("04_matrix_accounting.svg", coverage(records))
    write(
        "05_full_backend_success_heatmap.svg",
        matrix_heatmap(
            records,
            rows=BACKENDS,
            row_label=BACKEND_LABEL,
            subsetter=lambda _t, rs, name: [r for r in rs if backend(r) == name],
            title="Full realized matrices: backend success rates",
            subtitle="Within-trial rates; grey cells were not represented in the finalized trial",
            source="Source: finalized records; denominators reflect structured realized coverage",
        ),
    )
    write(
        "06_premium_endpoint_forest.svg",
        endpoint_forest(
            records,
            subset_premium,
            title="Premium-class validator-confirmed success",
            subtitle="Each trial’s configured hosted/frontier class; membership is not constant",
            source="Source: finalized premium-backend records",
            maximum=0.85,
        ),
    )
    write("07_premium_progress.svg", premium_progress(records))
    write(
        "08_premium_backend_heatmap.svg",
        matrix_heatmap(
            records,
            rows=("claude-sonnet", "claude-opus", "gpt-5", "gemini-pro-latest"),
            row_label=BACKEND_LABEL,
            subsetter=lambda t, rs, name: [
                r for r in rs if name in PREMIUM[t] and backend(r) == name
            ],
            title="Premium-model success by backend",
            subtitle="Full realized target/prompt matrices within each trial",
            source="Source: finalized records; backend rows do not align target or prompt exposure",
        ),
    )
    write(
        "09_aligned_premium_core.svg",
        endpoint_forest(
            records,
            lambda _t, rs: subset_core(rs),
            title="Backend/target-aligned premium sensitivity cohort",
            subtitle="Claude Sonnet + GPT-5 on BroncoCTF and ROPBench ex005",
            source="Source: finalized records; prompt arms and replicate exposure still differ",
            maximum=1.0,
        ),
    )
    write(
        "10_premium_target_heatmap.svg",
        matrix_heatmap(
            records,
            rows=TARGETS,
            row_label=TARGET_LABEL,
            subsetter=lambda t, rs, name: [
                r
                for r in rs
                if backend(r) in PREMIUM[t] and r["binary_id"] == name
            ],
            title="Premium-class success by target",
            subtitle="Within-trial target rates; grey denotes absence from that trial’s premium panel",
            source="Source: finalized premium-backend records; target panels differ substantially",
        ),
    )
    write(
        "11_premium_resources.svg",
        resource_bars(
            records,
            subset_premium,
            title="Premium-class resource profiles",
            source="Source: finalized premium-backend token, wall-clock, and iteration metadata",
        ),
    )
    write("12_tool_workflow_evolution.svg", tool_evolution(records))


if __name__ == "__main__":
    main()
