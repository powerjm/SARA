"""Generate the Trial 3 run-for-record core diagram suite.

The archive reader is deliberately metadata-only: it opens record.json members
and never opens exploit.py, payload.bin, or any submitted artifact.
"""

from __future__ import annotations

import collections
import ctypes
from html import escape
import importlib.util
import json
from pathlib import Path
import statistics
import tarfile
import textwrap
from typing import Any


TRIAL_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = TRIAL_ROOT.parent
ARCHIVE = TRIAL_ROOT / "runs.tgz"
OUTPUT = Path(__file__).resolve().parent

PLANNED = 216
PREMIUM_PLANNED = 108
LOCAL_PLANNED = 108

BACKEND_ORDER = (
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
    "qwen3-30b-abliterated": "Qwen3 30B Abliterated",
    "whiterabbitneo-v3-7b": "WhiteRabbitNeo 7B",
}
STRATEGY_ORDER = ("template_backward", "recon_first")
STRATEGY_LABELS = {
    "template_backward": "Template backward",
    "recon_first": "Recon first",
}
STRATEGY_COLORS = {
    "template_backward": "#7c3aed",
    "recon_first": "#0f766e",
}

NAVY = "#172554"
BLUE = "#2563eb"
TEAL = "#0f766e"
PURPLE = "#7c3aed"
GREEN = "#16a34a"
ORANGE = "#f59e0b"
RED = "#dc2626"
LIGHT = "#e2e8f0"
MUTED = "#64748b"
INK = "#1e293b"
BG = "#f8fafc"


def load_records() -> tuple[list[dict[str, Any]], int]:
    """Read only finalized record metadata and count trace-only partials."""
    records: list[dict[str, Any]] = []
    partial_ids: set[str] = set()
    with tarfile.open(ARCHIVE, "r:gz") as archive:
        for member in archive.getmembers():
            if member.name.startswith("runs/.partial-"):
                partial_ids.add(member.name.split("/")[1])
            if (
                member.name.startswith("runs/")
                and member.name.endswith("/record.json")
                and "/.partial-" not in member.name
            ):
                handle = archive.extractfile(member)
                if handle is None:
                    raise RuntimeError(f"cannot read {member.name}")
                records.append(json.load(handle))
    return records, len(partial_ids)


def write_svg(name: str, content: str) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / name).write_text(content, encoding="utf-8")


class RsvgRectangle(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_double),
        ("y", ctypes.c_double),
        ("width", ctypes.c_double),
        ("height", ctypes.c_double),
    ]


def render_png(svg_path: Path) -> None:
    """Render one generated SVG with the system librsvg/cairo libraries."""
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
    cairo.cairo_image_surface_create.argtypes = [
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
    ]
    cairo.cairo_image_surface_create.restype = ctypes.c_void_p
    cairo.cairo_create.argtypes = [ctypes.c_void_p]
    cairo.cairo_create.restype = ctypes.c_void_p
    cairo.cairo_surface_write_to_png.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    cairo.cairo_surface_write_to_png.restype = ctypes.c_int
    cairo.cairo_destroy.argtypes = [ctypes.c_void_p]
    cairo.cairo_surface_destroy.argtypes = [ctypes.c_void_p]
    gobject.g_object_unref.argtypes = [ctypes.c_void_p]

    error = ctypes.c_void_p()
    handle = rsvg.rsvg_handle_new_from_file(
        str(svg_path).encode(), ctypes.byref(error)
    )
    if not handle:
        raise RuntimeError(f"librsvg could not open {svg_path}")
    width = ctypes.c_double()
    height = ctypes.c_double()
    if not rsvg.rsvg_handle_get_intrinsic_size_in_pixels(
        handle, ctypes.byref(width), ctypes.byref(height)
    ):
        gobject.g_object_unref(handle)
        raise RuntimeError(f"{svg_path} has no intrinsic pixel dimensions")
    pixel_width, pixel_height = round(width.value), round(height.value)
    surface = cairo.cairo_image_surface_create(0, pixel_width, pixel_height)
    context = cairo.cairo_create(surface)
    viewport = RsvgRectangle(0.0, 0.0, width.value, height.value)
    if not rsvg.rsvg_handle_render_document(
        handle, context, ctypes.byref(viewport), ctypes.byref(error)
    ):
        cairo.cairo_destroy(context)
        cairo.cairo_surface_destroy(surface)
        gobject.g_object_unref(handle)
        raise RuntimeError(f"librsvg could not render {svg_path}")
    png_path = svg_path.with_suffix(".png")
    status = cairo.cairo_surface_write_to_png(surface, str(png_path).encode())
    cairo.cairo_destroy(context)
    cairo.cairo_surface_destroy(surface)
    gobject.g_object_unref(handle)
    if status != 0:
        raise RuntimeError(f"cairo failed to write {png_path}: status {status}")


def render_all_pngs() -> None:
    for svg_path in sorted(OUTPUT.glob("*.svg")):
        render_png(svg_path)


def svg_document(
    width: int,
    height: int,
    title: str,
    description: str,
    body: str,
) -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
  <title id="title">{escape(title)}</title>
  <desc id="desc">{escape(description)}</desc>
  <style>
    .title {{ font: 700 34px system-ui, sans-serif; fill: {NAVY}; }}
    .headline {{ font: 800 31px system-ui, sans-serif; fill: {NAVY}; }}
    .sub {{ font: 18px system-ui, sans-serif; fill: #475569; }}
    .section {{ font: 700 15px system-ui, sans-serif; fill: {MUTED}; letter-spacing: 1.5px; }}
    .label {{ font: 650 18px system-ui, sans-serif; fill: {INK}; }}
    .small {{ font: 15px system-ui, sans-serif; fill: #475569; }}
    .smalllight {{ font: 15px system-ui, sans-serif; fill: #dbeafe; }}
    .tiny {{ font: 13px system-ui, sans-serif; fill: {MUTED}; }}
    .value {{ font: 700 18px system-ui, sans-serif; fill: {NAVY}; }}
    .big {{ font: 800 42px system-ui, sans-serif; fill: #fff; }}
    .bigdark {{ font: 800 42px system-ui, sans-serif; fill: {NAVY}; }}
    .white {{ font: 700 16px system-ui, sans-serif; fill: #fff; }}
    .axis {{ font: 14px system-ui, sans-serif; fill: {MUTED}; }}
    .source {{ font: 14px system-ui, sans-serif; fill: {MUTED}; }}
    .mono {{ font: 17px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; fill: #123b4a; }}
    .panel {{ fill: #fff; stroke: #cbd5e1; stroke-width: 2; }}
  </style>
  <rect width="{width}" height="{height}" fill="{BG}"/>
{body}
</svg>
"""


def matrix_accounting(records: list[dict[str, Any]], partials: int) -> str:
    finalized = len(records)
    attempts = finalized + partials
    never_started = PLANNED - attempts
    body = f"""
  <text class="title" x="70" y="68">Trial 3 run-for-record matrix accounting</text>
  <text class="sub" x="70" y="103">9 binaries × 6 backends × 2 strategies × 2 replicates</text>

  <rect x="70" y="155" width="250" height="230" rx="18" fill="{NAVY}"/>
  <text class="big" x="195" y="235" text-anchor="middle">{PLANNED}</text>
  <text class="white" x="195" y="278" text-anchor="middle">planned runs</text>
  <text class="smalllight" x="195" y="318" text-anchor="middle">100% of matrix</text>
  <path d="M330 270 H385" stroke="#94a3b8" stroke-width="5"/><path d="M385 270 l-14 -10 v20 z" fill="#94a3b8"/>

  <rect x="395" y="155" width="250" height="230" rx="18" fill="{BLUE}"/>
  <text class="big" x="520" y="235" text-anchor="middle">{attempts}</text>
  <text class="white" x="520" y="278" text-anchor="middle">attempt directories</text>
  <text class="smalllight" x="520" y="318" text-anchor="middle">{attempts / PLANNED:.1%} of planned</text>
  <path d="M655 270 H710" stroke="#94a3b8" stroke-width="5"/><path d="M710 270 l-14 -10 v20 z" fill="#94a3b8"/>

  <rect x="720" y="155" width="250" height="230" rx="18" fill="{TEAL}"/>
  <text class="big" x="845" y="235" text-anchor="middle">{finalized}</text>
  <text class="white" x="845" y="278" text-anchor="middle">finalized records</text>
  <text class="smalllight" x="845" y="318" text-anchor="middle">{finalized / PLANNED:.1%} of planned</text>

  <path d="M520 395 V448" stroke="#94a3b8" stroke-width="4"/><path d="M520 448 l-10 -14 h20 z" fill="#94a3b8"/>
  <rect x="395" y="460" width="250" height="150" rx="16" fill="{ORANGE}"/>
  <text class="big" x="520" y="520" text-anchor="middle">{partials}</text>
  <text class="white" x="520" y="555" text-anchor="middle">incomplete attempts</text>
  <text class="label" x="520" y="586" text-anchor="middle">2 errors + 1 interruption</text>

  <path d="M195 395 V448" stroke="#94a3b8" stroke-width="4"/><path d="M195 448 l-10 -14 h20 z" fill="#94a3b8"/>
  <rect x="70" y="460" width="250" height="150" rx="16" fill="{LIGHT}" stroke="#94a3b8" stroke-width="2"/>
  <text class="bigdark" x="195" y="520" text-anchor="middle">{never_started}</text>
  <text class="label" x="195" y="555" text-anchor="middle">never started</text>
  <text class="small" x="195" y="586" text-anchor="middle">{never_started / PLANNED:.1%} of planned</text>

  <rect x="720" y="430" width="410" height="180" rx="16" fill="#fff" stroke="#cbd5e1" stroke-width="2"/>
  <text class="label" x="750" y="472">Interpretation</text>
  <text class="small" x="750" y="510">Premium: 108/108 finalized.</text>
  <text class="small" x="750" y="538">Local: 38/108 finalized + 3 incomplete.</text>
  <text class="small" x="750" y="566">Missingness is ordered by the batch sequence.</text>
  <text class="source" x="70" y="678">Source: premium.log, local.log, and runs.tgz record/trace inventory • submitted artifacts not opened</text>
"""
    return svg_document(
        1200,
        720,
        "Trial 3 run-for-record matrix accounting",
        f"{PLANNED} planned, {attempts} initiated, {finalized} finalized, {partials} incomplete, and {never_started} never started.",
        body,
    )


def backend_termination_mix(records: list[dict[str, Any]]) -> str:
    groups: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for record in records:
        groups[record["backend_handle"]].append(record)
    colors = {
        "success": GREEN,
        "wall_clock": ORANGE,
        "token_budget": BLUE,
        "iteration_cap": PURPLE,
        "refusal": RED,
    }
    labels = {
        "success": "success",
        "wall_clock": "wall clock",
        "token_budget": "token budget",
        "iteration_cap": "iteration cap",
        "refusal": "refusal",
    }
    order = ("success", "wall_clock", "token_budget", "iteration_cap", "refusal")
    rows = {
        "claude-sonnet": 245,
        "claude-opus": 305,
        "gpt-5": 365,
        "gpt-oss-20b": 500,
        "qwen3-30b-abliterated": 560,
        "whiterabbitneo-v3-7b": 620,
    }
    parts = [
        '<text class="title" x="55" y="58">How finalized Trial 3 runs ended, by backend</text>',
        '<text class="sub" x="55" y="91">Normalized within backend; termination labels describe observed finalized records</text>',
    ]
    legend_x = 575
    for key in order:
        parts.append(f'<rect x="{legend_x}" y="112" width="18" height="18" rx="3" fill="{colors[key]}"/>')
        parts.append(f'<text class="small" x="{legend_x + 27}" y="127">{labels[key]}</text>')
        legend_x += 125 if key != "iteration_cap" else 145
    parts.extend(
        [
            '<text class="axis" x="355" y="174">0%</text><text class="axis" x="732" y="174">50%</text><text class="axis" x="1110" y="174">100%</text>',
            '<line x1="360" y1="182" x2="360" y2="660" stroke="#cbd5e1"/>',
            '<line x1="740" y1="182" x2="740" y2="660" stroke="#e2e8f0"/>',
            '<line x1="1120" y1="182" x2="1120" y2="660" stroke="#cbd5e1"/>',
            '<text class="section" x="55" y="208">PREMIUM · COMPLETE MATRIX</text>',
            '<text class="section" x="55" y="463">LOCAL · ORDERED PARTIAL MATRIX</text>',
        ]
    )
    bar_x, bar_width = 360, 760
    for backend in BACKEND_ORDER:
        subset = groups[backend]
        y = rows[backend]
        counts = collections.Counter(
            "success" if r["outcome"] == "success" else (r.get("failure_mode") or "other")
            for r in subset
        )
        cursor = bar_x
        for key in order:
            width = bar_width * counts[key] / len(subset)
            if width:
                parts.append(
                    f'<rect x="{cursor:.1f}" y="{y - 22}" width="{width:.1f}" height="32" rx="4" fill="{colors[key]}"/>'
                )
                if width > 38:
                    parts.append(
                        f'<text class="white" x="{cursor + width / 2:.1f}" y="{y}" text-anchor="middle">{counts[key]}</text>'
                    )
            cursor += width
        ran_plus = sum(r["max_tier_reached"] != "none" for r in subset)
        success = sum(r["outcome"] == "success" for r in subset)
        parts.append(f'<text class="label" x="55" y="{y}">{BACKEND_LABELS[backend]}</text>')
        parts.append(
            f'<text class="small" x="1140" y="{y}">n={len(subset)} · RAN+ {ran_plus / len(subset):.1%} · success {success / len(subset):.1%}</text>'
        )
    parts.extend(
        [
            '<rect x="55" y="692" width="1290" height="76" rx="12" fill="#e0f2fe"/>',
            '<text class="label" x="80" y="723">Premium failures are entirely wall-clock labeled; local failures also hit token and iteration limits.</text>',
            '<text class="small" x="80" y="750">The nominal premium limit was checkpointed: five successes and many failures finalized after 300 seconds.</text>',
            '<text class="source" x="55" y="807">Source: 146 finalized record.json files • refusal is an outcome overlay, not a progress tier</text>',
        ]
    )
    return svg_document(
        1400,
        830,
        "Trial 3 termination mix by backend",
        "Normalized termination bars for six Trial 3 backends.",
        "\n".join(parts),
    )


def strategy_engagement(records: list[dict[str, Any]]) -> str:
    groups: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for record in records:
        groups[record["prompting_strategy"]].append(record)
    rows = {"template_backward": 250, "recon_first": 430}
    parts = [
        '<text class="title" x="65" y="66">Prompt strategy: modest directional separation in Trial 3</text>',
        '<text class="sub" x="65" y="102">Solid bars show marker success; pale bars show the share reaching RAN or higher</text>',
        '<line x1="315" y1="155" x2="315" y2="520" stroke="#cbd5e1"/>',
        '<line x1="635" y1="155" x2="635" y2="520" stroke="#e2e8f0"/>',
        '<line x1="955" y1="155" x2="955" y2="520" stroke="#cbd5e1"/>',
        '<text class="axis" x="305" y="145">0%</text><text class="axis" x="620" y="145">50%</text><text class="axis" x="940" y="145">100%</text>',
    ]
    scale = 640
    for strategy in STRATEGY_ORDER:
        subset = groups[strategy]
        premium = [r for r in subset if r["backend"]["category"] == "premium"]
        y = rows[strategy]
        success = sum(r["outcome"] == "success" for r in subset)
        premium_success = sum(r["outcome"] == "success" for r in premium)
        ran_plus = sum(r["max_tier_reached"] != "none" for r in subset)
        calls = [r.get("tool_call_counts", {}).get("run_exploit_script", 0) for r in subset]
        parts.extend(
            [
                f'<text class="label" x="65" y="{y + 13}">{STRATEGY_LABELS[strategy]}</text>',
                f'<rect x="315" y="{y - 27}" width="{scale * ran_plus / len(subset):.1f}" height="54" rx="8" fill="#cbd5e1"/>',
                f'<rect x="315" y="{y - 27}" width="{scale * success / len(subset):.1f}" height="54" rx="8" fill="{STRATEGY_COLORS[strategy]}"/>',
                f'<text class="value" x="975" y="{y + 7}">{success / len(subset):.1%} ({success}/{len(subset)})</text>',
                f'<text class="small" x="315" y="{y + 57}">RAN+ {ran_plus / len(subset):.1%} · premium success {premium_success}/{len(premium)} ({premium_success / len(premium):.1%}) · median script calls {statistics.median(calls):g}</text>',
            ]
        )
    parts.extend(
        [
            '<rect x="65" y="565" width="1070" height="86" rx="14" fill="#e0f2fe"/>',
            '<text class="small" x="92" y="600">Balanced premium comparison: recon first 23/54 versus template backward 18/54.</text>',
            '<text class="small" x="92" y="627">Simple Fisher p≈0.428; clustered replicates and two samples per cell support direction, not an established effect.</text>',
            '<text class="source" x="65" y="694">Source: 146 finalized RunRecords; premium-only statistic removes ordered local-arm missingness</text>',
        ]
    )
    return svg_document(
        1200,
        720,
        "Trial 3 strategy engagement",
        "Marker success and runnable-or-higher rates for template-backward and recon-first prompting.",
        "\n".join(parts),
    )


def progress_funnel(records: list[dict[str, Any]]) -> str:
    tiers = collections.Counter(r["max_tier_reached"] for r in records)
    runnable = len(records) - tiers["none"]
    control_plus = tiers["control"] + tiers["marker"]
    refusals = sum(r["outcome"] == "safeguard_refusal" for r in records)
    submitted = sum((r.get("tool_call_counts", {}).get("run_exploit_script", 0) > 0) for r in records)
    body = f"""
  <defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0 L10 5 L0 10 z" fill="#94a3b8"/></marker></defs>
  <text class="title" x="55" y="58">What progress did finalized Trial 3 runs make?</text>
  <text class="sub" x="55" y="92">Mutually exclusive maximum tiers; refusal is shown separately as an outcome overlay</text>

  <rect x="470" y="130" width="310" height="90" rx="16" fill="{NAVY}"/>
  <text class="big" x="625" y="171" text-anchor="middle">{len(records)}</text>
  <text class="white" x="625" y="200" text-anchor="middle">finalized records</text>
  <line x1="625" y1="220" x2="625" y2="286" stroke="#94a3b8" stroke-width="4" marker-end="url(#arrow)"/>
  <line x1="470" y1="175" x2="350" y2="175" stroke="#94a3b8" stroke-width="3" marker-end="url(#arrow)"/>
  <rect x="65" y="130" width="270" height="90" rx="16" fill="{LIGHT}" stroke="#cbd5e1" stroke-width="2"/>
  <text class="bigdark" x="200" y="171" text-anchor="middle">{tiers['none']}</text>
  <text class="label" x="200" y="200" text-anchor="middle">NONE</text>

  <rect x="470" y="300" width="310" height="90" rx="16" fill="{BLUE}"/>
  <text class="big" x="625" y="341" text-anchor="middle">{runnable}</text>
  <text class="white" x="625" y="370" text-anchor="middle">reached RAN or higher</text>
  <line x1="625" y1="390" x2="625" y2="456" stroke="#94a3b8" stroke-width="4" marker-end="url(#arrow)"/>
  <line x1="780" y1="345" x2="970" y2="345" stroke="#94a3b8" stroke-width="3" marker-end="url(#arrow)"/>
  <rect x="985" y="300" width="280" height="90" rx="16" fill="#dbeafe" stroke="#bfdbfe" stroke-width="2"/>
  <text class="bigdark" x="1125" y="341" text-anchor="middle">{tiers['ran']}</text>
  <text class="label" x="1125" y="370" text-anchor="middle">RAN only</text>

  <rect x="470" y="470" width="310" height="90" rx="16" fill="{PURPLE}"/>
  <text class="big" x="625" y="511" text-anchor="middle">{control_plus}</text>
  <text class="white" x="625" y="540" text-anchor="middle">CONTROL or MARKER</text>
  <line x1="625" y1="560" x2="625" y2="626" stroke="#94a3b8" stroke-width="4" marker-end="url(#arrow)"/>
  <line x1="470" y1="515" x2="350" y2="515" stroke="#94a3b8" stroke-width="3" marker-end="url(#arrow)"/>
  <rect x="65" y="470" width="270" height="90" rx="16" fill="#fef3c7" stroke="#fde68a" stroke-width="2"/>
  <text class="bigdark" x="200" y="511" text-anchor="middle">{tiers['control']}</text>
  <text class="label" x="200" y="540" text-anchor="middle">CONTROL only</text>

  <rect x="470" y="640" width="310" height="100" rx="16" fill="{GREEN}"/>
  <text class="big" x="625" y="683" text-anchor="middle">{tiers['marker']}</text>
  <text class="white" x="625" y="714" text-anchor="middle">MARKER · validator success</text>
  <line x1="780" y1="690" x2="900" y2="690" stroke="#94a3b8" stroke-width="3" marker-end="url(#arrow)"/>
  <rect x="915" y="625" width="350" height="130" rx="15" fill="#fff" stroke="#cbd5e1" stroke-width="2"/>
  <text class="bigdark" x="1090" y="666" text-anchor="middle">43 / 48</text>
  <text class="label" x="1090" y="696" text-anchor="middle">CONTROL+ ended at MARKER</text>
  <text class="small" x="1090" y="724" text-anchor="middle">hierarchical maximum-tier ratio: 89.6%</text>

  <rect x="65" y="650" width="320" height="145" rx="15" fill="#fff1f2" stroke="#fecdd3" stroke-width="2"/>
  <text class="label" x="90" y="683">Outcome overlays</text>
  <text class="small" x="90" y="715">Refusal-classified: {refusals}</text>
  <text class="small" x="90" y="743">Script-execution runs: {submitted}</text>
  <text class="small" x="90" y="771">Refusals occupy 2 NONE + 2 RAN tiers.</text>

  <rect x="470" y="785" width="795" height="70" rx="14" fill="#dcfce7"/>
  <text class="label" x="500" y="817">Primary endpoint: 43/146 finalized records succeeded (29.5%).</text>
  <text class="small" x="500" y="842">Maximum tiers are stored outcomes, not proof that every marker run first registered control.</text>
  <text class="source" x="55" y="898">Source: 146 finalized RunRecords • submitted artifacts not opened</text>
"""
    return svg_document(
        1400,
        920,
        "Trial 3 progress funnel",
        "Maximum progress tiers for 146 finalized Trial 3 records.",
        body,
    )


def load_prompt_module(name: str):
    path = REPO_ROOT / "agent" / "prompts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"trial3_prompt_{name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def wrapped_prompt(value: str, width: int = 76) -> list[str]:
    output: list[str] = []
    for raw in value.rstrip().splitlines():
        if not raw.strip():
            output.append("")
            continue
        indent = raw[: len(raw) - len(raw.lstrip())]
        output.extend(
            textwrap.wrap(
                raw.strip(),
                width=width,
                initial_indent=indent,
                subsequent_indent=indent,
                break_long_words=False,
                break_on_hyphens=False,
            )
            or [""]
        )
    return output


def prompt_comparison() -> str:
    methods = (
        ("Template backward", "template_backward", PURPLE),
        ("Recon first", "recon_first", TEAL),
    )
    modules = [(label, name, color, load_prompt_module(name)) for label, name, color in methods]
    cards: list[str] = []
    card_width = 1110
    for index, (label, name, color, module) in enumerate(modules):
        x = 60 + index * 1170
        sections = (
            ("SYSTEM PROMPT", module.SYSTEM),
            ("TOOL-USE PROMPT", module.TOOL_USE),
            ("TASK PROMPT TEMPLATE", module.task("{binary_id}")),
        )
        y = 175
        cards.extend(
            [
                f'<rect class="panel" x="{x}" y="{y}" width="{card_width}" height="1350" rx="22"/>',
                f'<path d="M{x + 22} {y} H{x + card_width - 22} Q{x + card_width} {y} {x + card_width} {y + 22} V{y + 78} H{x} V{y + 22} Q{x} {y} {x + 22} {y} Z" fill="{color}"/>',
                f'<text x="{x + 32}" y="{y + 50}" style="font:700 30px system-ui,sans-serif;fill:#fff">{label}</text>',
                f'<text class="source" x="{x + 28}" y="{y + 108}">agent/prompts/{name}.py</text>',
            ]
        )
        section_y = y + 130
        for section_name, value in sections:
            lines = wrapped_prompt(value)
            height = 58 + len(lines) * 25
            cards.append(
                f'<rect x="{x + 22}" y="{section_y}" width="{card_width - 44}" height="{height}" rx="14" fill="#f8fafc" stroke="#e2e8f0" stroke-width="2"/>'
            )
            cards.append(
                f'<text x="{x + 44}" y="{section_y + 34}" style="font:700 16px system-ui,sans-serif;fill:{NAVY};letter-spacing:1px">{section_name}</text>'
            )
            line_y = section_y + 62
            for line in lines:
                cards.append(
                    f'<text x="{x + 44}" y="{line_y}" style="font:18px ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;fill:{INK}">{escape(line) if line else "&#160;"}</text>'
                )
                line_y += 25
            section_y += height + 18
    body = "\n".join(
        [
            '<text class="title" x="60" y="70">Trial 3 prompting methods — verbatim comparison</text>',
            '<text class="sub" x="60" y="112">Only the configured specialist scaffold differs; shared objective, rubric, and expert fragment are omitted here</text>',
            *cards,
            '<text class="source" x="60" y="1570">Source: agent/prompts/{template_backward,recon_first}.py • task prompts use the runtime {binary_id} placeholder</text>',
        ]
    )
    return svg_document(
        2400,
        1600,
        "Trial 3 prompting methods: verbatim comparison",
        "Side-by-side verbatim comparison of the template-backward and recon-first prompt modules.",
        body,
    )


def configuration_diagram(records: list[dict[str, Any]], partials: int) -> str:
    by_backend = collections.Counter(r["backend_handle"] for r in records)
    by_strategy = collections.Counter(r["prompting_strategy"] for r in records)
    by_binary = collections.Counter(r["binary_id"] for r in records)
    successes = sum(r["outcome"] == "success" for r in records)
    attempts = len(records) + partials
    binaries = [
        ("ret2win-baseline", "BASELINE"),
        ("broncoctf2026-proper-pwning", "LOW · CTF"),
        ("ropbench-synth-ex002", "MEDIUM · SYNTHETIC"),
        ("ropbench-synth-ex005", "MEDIUM · SYNTHETIC"),
        ("ropbench-synth-ex020", "MEDIUM · SYNTHETIC"),
        ("ropbench-synth-ex101", "MEDIUM · SYNTHETIC"),
        ("cgc-cromu-00004", "HIGH · CGC"),
        ("cgc-eagle-00005", "HIGH · CGC"),
        ("cgc-nrfin-00056", "HIGH · CGC"),
    ]
    left_items: list[str] = []
    y = 305
    for binary, group in binaries:
        display = binary.replace(
            "broncoctf2026-proper-pwning", "broncoctf-proper-pwning"
        )
        left_items.extend(
            [
                f'<text class="tiny" x="78" y="{y}">{group}</text>',
                f'<text class="mono" x="215" y="{y}">{display} · {by_binary[binary]}</text>',
            ]
        )
        y += 42
    backend_items: list[str] = []
    y = 315
    categories = {
        "claude-sonnet": "PREMIUM",
        "claude-opus": "PREMIUM",
        "gpt-5": "PREMIUM",
        "gpt-oss-20b": "OPEN WEIGHT",
        "qwen3-30b-abliterated": "UNRESTRICTED",
        "whiterabbitneo-v3-7b": "UNRESTRICTED",
    }
    for backend in BACKEND_ORDER:
        backend_items.extend(
            [
                f'<text class="tiny" x="570" y="{y}">{categories[backend]}</text>',
                f'<text class="mono" x="700" y="{y}">{backend} · {by_backend[backend]}</text>',
            ]
        )
        y += 59
    body = "\n".join(
        [
            '<text class="headline" x="768" y="52" text-anchor="middle">SARA TRIAL 3 — CONFIGURATION &amp; EXECUTION</text>',
            '<text class="title" x="768" y="99" text-anchor="middle">9 BINARIES × 6 BACKENDS × 2 STRATEGIES = 108 CELLS</text>',
            f'<text class="sub" x="768" y="137" text-anchor="middle">2 REPLICATES PER CELL → {PLANNED} PLANNED RUNS</text>',
            f'<text class="sub" x="768" y="169" text-anchor="middle">{attempts} ATTEMPT DIRECTORIES → {len(records)} FINALIZED + {partials} INCOMPLETE</text>',
            f'<text class="sub" x="768" y="201" text-anchor="middle">{PLANNED - attempts} PLANNED RUNS NEVER STARTED</text>',
            '<rect class="panel" x="45" y="230" width="475" height="485" rx="12"/>',
            '<text class="label" x="282" y="268" text-anchor="middle">BINARIES · FINALIZED RECORDS</text>',
            *left_items,
            '<rect class="panel" x="535" y="230" width="475" height="485" rx="12"/>',
            '<text class="label" x="772" y="268" text-anchor="middle">BACKENDS · FINALIZED RECORDS</text>',
            *backend_items,
            '<rect class="panel" x="1025" y="230" width="466" height="485" rx="12"/>',
            '<text class="label" x="1258" y="268" text-anchor="middle">STRATEGIES · FINALIZED RECORDS</text>',
            '<rect x="1050" y="305" width="416" height="120" rx="10" fill="#f5f3ff" stroke="#c4b5fd" stroke-width="2"/>',
            f'<text class="mono" x="1258" y="360" text-anchor="middle">template_backward · {by_strategy["template_backward"]}</text>',
            '<text class="small" x="1258" y="395" text-anchor="middle">20 successes overall · 18 premium</text>',
            '<rect x="1050" y="460" width="416" height="120" rx="10" fill="#ecfdf5" stroke="#99f6e4" stroke-width="2"/>',
            f'<text class="mono" x="1258" y="515" text-anchor="middle">recon_first · {by_strategy["recon_first"]}</text>',
            '<text class="small" x="1258" y="550" text-anchor="middle">23 successes overall · 23 premium</text>',
            '<text class="small" x="1258" y="635" text-anchor="middle">Two replicates per complete cell</text>',
            '<text class="small" x="1258" y="663" text-anchor="middle">Local matrix curtailed in target order</text>',
            '<rect class="panel" x="45" y="735" width="1446" height="93" rx="10"/>',
            '<text class="label" x="768" y="765" text-anchor="middle">RUN LIMITS OBSERVED IN LOGS / RECORDS</text>',
            '<rect class="panel" x="65" y="782" width="335" height="32" rx="6"/><text class="mono" x="232" y="805" text-anchor="middle">1,000,000 tokens</text>',
            '<rect class="panel" x="415" y="782" width="335" height="32" rx="6"/><text class="mono" x="582" y="805" text-anchor="middle">premium · 300 s nominal</text>',
            '<rect class="panel" x="765" y="782" width="335" height="32" rx="6"/><text class="mono" x="932" y="805" text-anchor="middle">local · 1,200 s nominal</text>',
            '<rect class="panel" x="1115" y="782" width="355" height="32" rx="6"/><text class="mono" x="1292" y="805" text-anchor="middle">100-iteration backstop</text>',
            '<rect class="panel" x="45" y="845" width="1446" height="90" rx="10"/>',
            '<text class="label" x="768" y="875" text-anchor="middle">RECORDED PREMIUM COST CAPS FROM LAUNCHER LOG</text>',
            '<text class="mono" x="310" y="910" text-anchor="middle">claude-sonnet · $90</text>',
            '<text class="mono" x="768" y="910" text-anchor="middle">claude-opus · $180</text>',
            '<text class="mono" x="1225" y="910" text-anchor="middle">gpt-5 · $130</text>',
            f'<text class="label" x="260" y="975" text-anchor="middle">PREMIUM: {PREMIUM_PLANNED}/{PREMIUM_PLANNED} FINALIZED</text>',
            f'<text class="label" x="768" y="975" text-anchor="middle">LOCAL: {len(records) - PREMIUM_PLANNED}/{LOCAL_PLANNED} FINALIZED</text>',
            f'<text class="label" x="1260" y="975" text-anchor="middle">PRIMARY ENDPOINT: {successes}/{len(records)}</text>',
            '<text class="source" x="768" y="1008" text-anchor="middle">Reconstructed from premium.log, local.log, and finalized record metadata; governing YAML files were not archived</text>',
        ]
    )
    return svg_document(
        1536,
        1024,
        "SARA Trial 3 configuration and execution",
        "Reconstructed Trial 3 experiment matrix, limits, completion, and endpoint.",
        body,
    )


def main() -> None:
    records, partials = load_records()
    assert len(records) == 146
    assert partials == 3
    assert sum(r["outcome"] == "success" for r in records) == 43
    assert collections.Counter(r["max_tier_reached"] for r in records) == {
        "none": 35,
        "ran": 63,
        "control": 5,
        "marker": 43,
    }

    write_svg("01_matrix_accounting.svg", matrix_accounting(records, partials))
    write_svg("02_backend_termination_mix.svg", backend_termination_mix(records))
    write_svg("03_strategy_engagement.svg", strategy_engagement(records))
    write_svg("04_progress_funnel.svg", progress_funnel(records))
    write_svg("05_prompt_method_verbatim_comparison.svg", prompt_comparison())
    write_svg(
        "experiment_configuration_trial_3_actual.svg",
        configuration_diagram(records, partials),
    )
    render_all_pngs()


if __name__ == "__main__":
    main()
