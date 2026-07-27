"""Generate the Trial 2 run-for-record diagram suite.

The archive reader is deliberately metadata-only: it opens record.json and
trace.jsonl members, but never opens exploit.py, payload.bin, or target files.
"""

from __future__ import annotations

import collections
from html import escape
import importlib.util
import json
from pathlib import Path
import re
import statistics
import tarfile
import textwrap
from typing import Any

import yaml


TRIAL_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = TRIAL_ROOT.parent
ARCHIVE = TRIAL_ROOT / "runz.tgz"
CONFIG = TRIAL_ROOT / "experiments.yaml"
OUTPUT = Path(__file__).resolve().parent

BACKEND_ORDER = (
    "claude-sonnet",
    "gpt-5",
    "gpt-oss-20b",
    "qwen3-coder-30b",
    "qwen3-30b-abliterated",
    "whiterabbitneo-v3-7b",
)
BACKEND_LABELS = {
    "claude-sonnet": "Claude Sonnet",
    "gpt-5": "GPT-5",
    "gpt-oss-20b": "GPT-OSS 20B",
    "qwen3-coder-30b": "Qwen3 Coder 30B",
    "qwen3-30b-abliterated": "Qwen3 30B Abliterated",
    "whiterabbitneo-v3-7b": "WhiteRabbitNeo 7B",
}
STRATEGY_ORDER = ("zero_shot", "react", "chain_of_thought")
STRATEGY_LABELS = {
    "zero_shot": "Zero-shot",
    "react": "ReAct",
    "chain_of_thought": "Chain of thought",
}
STRATEGY_COLORS = {
    "zero_shot": "#2563eb",
    "react": "#0f766e",
    "chain_of_thought": "#7c3aed",
}


def load_metadata() -> tuple[list[dict[str, Any]], dict[str, str], int]:
    """Read only final records and traces from the archive."""
    with tarfile.open(ARCHIVE, "r:gz") as archive:
        members = {member.name: member for member in archive.getmembers()}
        record_members = [
            member
            for member in members.values()
            if member.name.startswith("runs/")
            and member.name.endswith("/record.json")
            and "/.partial-" not in member.name
        ]
        records = []
        terminations = {}
        for member in record_members:
            handle = archive.extractfile(member)
            if handle is None:
                raise RuntimeError(f"cannot read {member.name}")
            record = json.load(handle)
            records.append(record)

            trace_name = f"runs/{record['run_id']}/trace.jsonl"
            trace_handle = archive.extractfile(members[trace_name])
            if trace_handle is None:
                raise RuntimeError(f"cannot read {trace_name}")
            last_reason = "<missing>"
            for raw_line in trace_handle:
                if not raw_line.strip():
                    continue
                event = json.loads(raw_line)
                if event.get("terminated"):
                    last_reason = event.get("termination_reason", "<missing>")
            terminations[record["run_id"]] = last_reason

        partials = {
            member.name.split("/")[1]
            for member in members.values()
            if member.name.startswith("runs/.partial-")
        }
    return records, terminations, len(partials)


def write_svg(name: str, content: str) -> None:
    (OUTPUT / name).write_text(content, encoding="utf-8")


def matrix_accounting(
    planned: int, finalized: int, partials: int, attempts: int
) -> str:
    no_directory = planned - attempts
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="720" viewBox="0 0 1200 720" role="img" aria-labelledby="title desc">
  <title id="title">Trial 2 run-for-record matrix accounting</title>
  <desc id="desc">Of {planned} planned runs, {attempts} produced an archived run directory, {finalized} finalized, {partials} remained partial, and {no_directory} produced no archived directory.</desc>
  <style>
    .title {{ font: 700 34px system-ui, sans-serif; fill: #172554; }}
    .sub {{ font: 18px system-ui, sans-serif; fill: #475569; }}
    .big {{ font: 700 42px system-ui, sans-serif; fill: #fff; }}
    .label {{ font: 700 20px system-ui, sans-serif; fill: #fff; }}
    .pct {{ font: 17px system-ui, sans-serif; fill: #dbeafe; }}
    .darkBig {{ font: 700 42px system-ui, sans-serif; fill: #172554; }}
    .darkLabel {{ font: 700 20px system-ui, sans-serif; fill: #172554; }}
    .darkPct {{ font: 17px system-ui, sans-serif; fill: #475569; }}
    .note {{ font: 16px system-ui, sans-serif; fill: #475569; }}
    .source {{ font: 14px system-ui, sans-serif; fill: #64748b; }}
  </style>
  <rect width="1200" height="720" fill="#f8fafc"/>
  <text class="title" x="70" y="68">Trial 2 run-for-record matrix accounting</text>
  <text class="sub" x="70" y="102">4 binaries × 6 backends × 3 strategies × 2 replicates</text>

  <rect x="70" y="155" width="250" height="230" rx="18" fill="#172554"/>
  <text class="big" x="195" y="235" text-anchor="middle">{planned}</text>
  <text class="label" x="195" y="278" text-anchor="middle">planned</text>
  <text class="pct" x="195" y="318" text-anchor="middle">100% of matrix</text>
  <path d="M330 270 H385" stroke="#94a3b8" stroke-width="5"/><path d="M385 270 l-14 -10 v20 z" fill="#94a3b8"/>

  <rect x="395" y="155" width="250" height="230" rx="18" fill="#2563eb"/>
  <text class="big" x="520" y="235" text-anchor="middle">{attempts}</text>
  <text class="label" x="520" y="278" text-anchor="middle">attempt directories</text>
  <text class="pct" x="520" y="318" text-anchor="middle">{attempts / planned:.1%} of planned</text>
  <path d="M655 270 H710" stroke="#94a3b8" stroke-width="5"/><path d="M710 270 l-14 -10 v20 z" fill="#94a3b8"/>

  <rect x="720" y="155" width="250" height="230" rx="18" fill="#0f766e"/>
  <text class="big" x="845" y="235" text-anchor="middle">{finalized}</text>
  <text class="label" x="845" y="278" text-anchor="middle">finalized records</text>
  <text class="pct" x="845" y="318" text-anchor="middle">{finalized / planned:.1%} of planned</text>

  <path d="M520 395 V448" stroke="#94a3b8" stroke-width="4"/><path d="M520 448 l-10 -14 h20 z" fill="#94a3b8"/>
  <rect x="395" y="460" width="250" height="150" rx="16" fill="#f59e0b"/>
  <text class="big" x="520" y="520" text-anchor="middle">{partials}</text>
  <text class="label" x="520" y="555" text-anchor="middle">trace-only partials</text>
  <text class="pct" x="520" y="586" text-anchor="middle">{partials / attempts:.1%} of attempts</text>

  <path d="M195 395 V448" stroke="#94a3b8" stroke-width="4"/><path d="M195 448 l-10 -14 h20 z" fill="#94a3b8"/>
  <rect x="70" y="460" width="250" height="150" rx="16" fill="#e2e8f0" stroke="#94a3b8" stroke-width="2"/>
  <text class="darkBig" x="195" y="520" text-anchor="middle">{no_directory}</text>
  <text class="darkLabel" x="195" y="555" text-anchor="middle">no archived directory</text>
  <text class="darkPct" x="195" y="586" text-anchor="middle">{no_directory / planned:.1%} of planned</text>

  <rect x="720" y="430" width="410" height="180" rx="16" fill="#fff" stroke="#cbd5e1" stroke-width="2"/>
  <text class="darkLabel" x="750" y="472">Interpretation</text>
  <text class="note" x="750" y="510">Finalized coverage is 63.9%, with missingness</text>
  <text class="note" x="750" y="538">concentrated in three curtailed local-model arms.</text>
  <text class="note" x="750" y="566">The four partial attempts are not scored as failures.</text>
  <text class="source" x="70" y="678">Source: experiments.yaml, runz.tgz record/trace metadata, and batch logs • July 2026</text>
</svg>
"""


def backend_termination_mix(
    records: list[dict[str, Any]], terminations: dict[str, str]
) -> str:
    groups: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for record in records:
        groups[record["backend_handle"]].append(record)
    colors = {
        "success": "#16a34a",
        "token_budget": "#2563eb",
        "wall_clock": "#f59e0b",
        "truncated": "#dc2626",
    }
    bar_x, bar_width = 360, 760
    rows = {
        "claude-sonnet": 240,
        "gpt-5": 300,
        "gpt-oss-20b": 415,
        "qwen3-coder-30b": 475,
        "qwen3-30b-abliterated": 590,
        "whiterabbitneo-v3-7b": 650,
    }
    sections = ((203, "PREMIUM"), (378, "OPEN WEIGHT"), (553, "UNRESTRICTED"))
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="830" viewBox="0 0 1400 830" role="img" aria-labelledby="title desc">',
        "<title id=\"title\">Trial 2 termination mix by backend</title>",
        "<desc id=\"desc\">Normalized bars show success, token-budget, wall-clock, and truncation endings by backend.</desc>",
        """<style>
    .title { font: 700 34px system-ui, sans-serif; fill: #172554; }
    .sub { font: 18px system-ui, sans-serif; fill: #475569; }
    .name { font: 600 17px system-ui, sans-serif; fill: #1e293b; }
    .meta { font: 15px system-ui, sans-serif; fill: #475569; }
    .axis { font: 14px system-ui, sans-serif; fill: #64748b; }
    .legend { font: 15px system-ui, sans-serif; fill: #334155; }
    .section { font: 700 15px system-ui, sans-serif; fill: #64748b; letter-spacing: 1.5px; }
    .source { font: 14px system-ui, sans-serif; fill: #64748b; }
  </style>""",
        '<rect width="1400" height="830" fill="#f8fafc"/>',
        '<text class="title" x="55" y="58">How finalized Trial 2 runs ended, by backend</text>',
        '<text class="sub" x="55" y="91">Bars are normalized within backend; metadata reports runnable-or-higher and marker success</text>',
    ]
    legend_x = 690
    for label, key, width in (
        ("success", "success", 110),
        ("token budget", "token_budget", 150),
        ("wall clock", "wall_clock", 135),
        ("truncated", "truncated", 125),
    ):
        parts.append(
            f'<rect x="{legend_x}" y="112" width="18" height="18" rx="3" fill="{colors[key]}"/>'
            f'<text class="legend" x="{legend_x + 28}" y="127">{label}</text>'
        )
        legend_x += width
    parts.extend(
        [
            '<text class="axis" x="355" y="166">0%</text><text class="axis" x="732" y="166">50%</text><text class="axis" x="1110" y="166">100%</text>',
            '<line x1="360" y1="175" x2="360" y2="695" stroke="#cbd5e1"/>',
            '<line x1="740" y1="175" x2="740" y2="695" stroke="#e2e8f0"/>',
            '<line x1="1120" y1="175" x2="1120" y2="695" stroke="#cbd5e1"/>',
        ]
    )
    for y, label in sections:
        parts.append(f'<text class="section" x="55" y="{y}">{label}</text>')
    for backend in BACKEND_ORDER:
        subset = groups[backend]
        y = rows[backend]
        counts = collections.Counter(
            terminations[record["run_id"]] for record in subset
        )
        cursor = bar_x
        for key in ("success", "token_budget", "wall_clock", "truncated"):
            segment = bar_width * counts[key] / len(subset)
            if segment:
                parts.append(
                    f'<rect x="{cursor:.1f}" y="{y - 22}" width="{segment:.1f}" height="30" rx="4" fill="{colors[key]}"/>'
                )
            cursor += segment
        runnable = sum(
            record["max_tier_reached"] != "none" for record in subset
        )
        successes = counts["success"]
        parts.extend(
            [
                f'<text class="name" x="55" y="{y}">{BACKEND_LABELS[backend]}</text>',
                f'<text class="meta" x="1140" y="{y}">n={len(subset)} • RAN+ {runnable / len(subset):.1%} • success {successes / len(subset):.1%}</text>',
            ]
        )
    parts.extend(
        [
            '<rect x="55" y="715" width="1290" height="66" rx="12" fill="#dcfce7"/>',
            '<text class="name" x="80" y="744" fill="#166534">Primary endpoint: 34 validator-confirmed successes among 92 finalized runs (37.0%).</text>',
            '<text class="meta" x="80" y="768">Coverage is incomplete and backend-skewed; normalized bars describe observed finalized records only.</text>',
            '<text class="source" x="55" y="812">Source: 92 finalized record.json and trace.jsonl artifacts; submitted files were not opened</text>',
            "</svg>",
            "",
        ]
    )
    return "\n".join(parts)


def strategy_comparison(records: list[dict[str, Any]]) -> str:
    groups: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for record in records:
        groups[record["prompting_strategy"]].append(record)
    rows = {"zero_shot": 220, "react": 350, "chain_of_thought": 480}
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="720" viewBox="0 0 1200 720" role="img" aria-labelledby="title desc">',
        "<title id=\"title\">Trial 2 prompting-strategy comparison</title>",
        "<desc id=\"desc\">Marker-success and runnable-or-higher shares are shown for Trial 2's three prompting strategies.</desc>",
        """<style>
    .title { font: 700 34px system-ui, sans-serif; fill: #172554; }
    .sub { font: 18px system-ui, sans-serif; fill: #475569; }
    .label { font: 700 21px system-ui, sans-serif; fill: #1e293b; }
    .value { font: 700 18px system-ui, sans-serif; fill: #172554; }
    .meta { font: 16px system-ui, sans-serif; fill: #475569; }
    .axis { font: 14px system-ui, sans-serif; fill: #64748b; }
    .note { font: 16px system-ui, sans-serif; fill: #334155; }
    .source { font: 14px system-ui, sans-serif; fill: #64748b; }
  </style>""",
        '<rect width="1200" height="720" fill="#f8fafc"/>',
        '<text class="title" x="65" y="66">Prompt strategy: no clear separation in Trial 2</text>',
        '<text class="sub" x="65" y="102">Solid bars show marker success; pale bars show the share reaching RAN or higher</text>',
        '<line x1="315" y1="150" x2="315" y2="540" stroke="#cbd5e1"/>',
        '<line x1="635" y1="150" x2="635" y2="540" stroke="#e2e8f0"/>',
        '<line x1="955" y1="150" x2="955" y2="540" stroke="#cbd5e1"/>',
        '<text class="axis" x="305" y="140">0%</text><text class="axis" x="620" y="140">50%</text><text class="axis" x="940" y="140">100%</text>',
    ]
    scale = 640
    for strategy in STRATEGY_ORDER:
        subset = groups[strategy]
        y = rows[strategy]
        success = sum(record["outcome"] == "success" for record in subset)
        runnable = sum(record["max_tier_reached"] != "none" for record in subset)
        run_calls = [
            record.get("tool_call_counts", {}).get("run_exploit_script", 0)
            for record in subset
        ]
        parts.extend(
            [
                f'<text class="label" x="65" y="{y + 13}">{STRATEGY_LABELS[strategy]}</text>',
                f'<rect x="315" y="{y - 22}" width="{scale * runnable / len(subset):.1f}" height="48" rx="8" fill="#cbd5e1"/>',
                f'<rect x="315" y="{y - 22}" width="{scale * success / len(subset):.1f}" height="48" rx="8" fill="{STRATEGY_COLORS[strategy]}"/>',
                f'<text class="value" x="975" y="{y + 9}">{success / len(subset):.1%} ({success}/{len(subset)})</text>',
                f'<text class="meta" x="315" y="{y + 54}">RAN+ {runnable / len(subset):.1%} • median run_exploit_script calls {statistics.median(run_calls):g}</text>',
            ]
        )
    parts.extend(
        [
            '<rect x="65" y="575" width="1070" height="82" rx="14" fill="#e0f2fe"/>',
            '<text class="note" x="92" y="608">Observed success rates span 34.4%–41.4%, but unequal denominators, clustered runs, two replicates,</text>',
            '<text class="note" x="92" y="635">and backend/target missingness make this an exploratory comparison—not evidence of equivalence.</text>',
            '<text class="source" x="65" y="695">Source: 92 finalized RunRecords and recorded tool-call counts</text>',
            "</svg>",
            "",
        ]
    )
    return "\n".join(parts)


def progress_funnel(records: list[dict[str, Any]]) -> str:
    tiers = collections.Counter(record["max_tier_reached"] for record in records)
    runnable = len(records) - tiers["none"]
    bronco = [r for r in records if r["binary_id"] == "broncoctf2026-proper-pwning"]
    gate_counts = collections.Counter()
    for record in bronco:
        if record["outcome"] == "success":
            gate_counts["marker"] += 1
            continue
        stdout = ((record.get("validator") or {}).get("stdout_excerpt") or "")
        if "Gate 3 opens" in stdout:
            gate_counts["gate3"] += 1
        elif "Gate 2 opens" in stdout:
            gate_counts["gate2"] += 1
        elif "Gate 1 opens" in stdout:
            gate_counts["gate1"] += 1
        else:
            gate_counts["none"] += 1
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="920" viewBox="0 0 1400 920" role="img" aria-labelledby="title desc">
  <title id="title">Trial 2 progress ladder</title>
  <desc id="desc">Trial 2 finalized records flow from no runnable candidate through ran, control, and marker tiers.</desc>
  <style>
    .title {{ font: 700 34px system-ui, sans-serif; fill: #172554; }}
    .sub {{ font: 18px system-ui, sans-serif; fill: #475569; }}
    .num {{ font: 700 31px system-ui, sans-serif; fill: #fff; }}
    .boxlabel {{ font: 650 17px system-ui, sans-serif; fill: #fff; }}
    .sideNum {{ font: 700 27px system-ui, sans-serif; fill: #172554; }}
    .sideLabel {{ font: 600 16px system-ui, sans-serif; fill: #334155; }}
    .small {{ font: 15px system-ui, sans-serif; fill: #475569; }}
    .call {{ font: 650 16px system-ui, sans-serif; fill: #92400e; }}
    .source {{ font: 14px system-ui, sans-serif; fill: #64748b; }}
  </style>
  <defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#94a3b8"/></marker></defs>
  <rect width="1400" height="920" fill="#f8fafc"/>
  <text class="title" x="55" y="58">What progress did finalized Trial 2 runs make?</text>
  <text class="sub" x="55" y="92">Mutually exclusive maximum tiers recorded by the schema-v5 validator ladder</text>

  <rect x="470" y="130" width="310" height="90" rx="16" fill="#172554"/>
  <text class="num" x="625" y="171" text-anchor="middle">{len(records)}</text>
  <text class="boxlabel" x="625" y="200" text-anchor="middle">finalized runs</text>
  <line x1="625" y1="220" x2="625" y2="286" stroke="#94a3b8" stroke-width="4" marker-end="url(#arrow)"/>
  <line x1="470" y1="175" x2="350" y2="175" stroke="#94a3b8" stroke-width="3" marker-end="url(#arrow)"/>
  <rect x="65" y="130" width="270" height="90" rx="16" fill="#e2e8f0" stroke="#cbd5e1" stroke-width="2"/>
  <text class="sideNum" x="200" y="171" text-anchor="middle">{tiers['none']}</text>
  <text class="sideLabel" x="200" y="200" text-anchor="middle">NONE: no runnable candidate</text>

  <rect x="470" y="300" width="310" height="90" rx="16" fill="#2563eb"/>
  <text class="num" x="625" y="341" text-anchor="middle">{runnable}</text>
  <text class="boxlabel" x="625" y="370" text-anchor="middle">reached RAN or higher</text>
  <line x1="625" y1="390" x2="625" y2="456" stroke="#94a3b8" stroke-width="4" marker-end="url(#arrow)"/>
  <line x1="780" y1="345" x2="970" y2="345" stroke="#94a3b8" stroke-width="3" marker-end="url(#arrow)"/>
  <rect x="985" y="300" width="280" height="90" rx="16" fill="#dbeafe" stroke="#bfdbfe" stroke-width="2"/>
  <text class="sideNum" x="1125" y="341" text-anchor="middle">{tiers['ran']}</text>
  <text class="sideLabel" x="1125" y="370" text-anchor="middle">RAN: no control or marker</text>

  <rect x="470" y="470" width="310" height="90" rx="16" fill="#7c3aed"/>
  <text class="num" x="625" y="511" text-anchor="middle">{tiers['control'] + tiers['marker']}</text>
  <text class="boxlabel" x="625" y="540" text-anchor="middle">reached CONTROL or MARKER</text>
  <line x1="625" y1="560" x2="625" y2="626" stroke="#94a3b8" stroke-width="4" marker-end="url(#arrow)"/>
  <line x1="470" y1="515" x2="350" y2="515" stroke="#94a3b8" stroke-width="3" marker-end="url(#arrow)"/>
  <rect x="65" y="470" width="270" height="90" rx="16" fill="#fef3c7" stroke="#fde68a" stroke-width="2"/>
  <text class="sideNum" x="200" y="511" text-anchor="middle">{tiers['control']}</text>
  <text class="sideLabel" x="200" y="540" text-anchor="middle">CONTROL without marker</text>

  <rect x="470" y="640" width="310" height="100" rx="16" fill="#16a34a"/>
  <text class="num" x="625" y="683" text-anchor="middle">{tiers['marker']}</text>
  <text class="boxlabel" x="625" y="714" text-anchor="middle">MARKER: validator success</text>
  <line x1="780" y1="690" x2="900" y2="690" stroke="#94a3b8" stroke-width="3" marker-end="url(#arrow)"/>
  <rect x="915" y="625" width="350" height="130" rx="15" fill="#fff" stroke="#cbd5e1" stroke-width="2"/>
  <text class="sideNum" x="1090" y="666" text-anchor="middle">34 / 35</text>
  <text class="sideLabel" x="1090" y="696" text-anchor="middle">CONTROL+ runs reached MARKER</text>
  <text class="small" x="1090" y="724" text-anchor="middle">97.1% conversion within the stored ladder</text>

  <rect x="65" y="650" width="320" height="145" rx="15" fill="#fffbeb" stroke="#fde68a" stroke-width="2"/>
  <text class="call" x="90" y="683">BroncoCTF final-record evidence</text>
  <text class="small" x="90" y="711">Marker: {gate_counts['marker']} • Gate 3, no marker: {gate_counts['gate3']}</text>
  <text class="small" x="90" y="738">Gate 1, no marker: {gate_counts['gate1']} • Gate 2: {gate_counts['gate2']}</text>
  <text class="small" x="90" y="765">No retained gate text: {gate_counts['none']}</text>

  <rect x="470" y="785" width="795" height="70" rx="14" fill="#dcfce7"/>
  <text class="sideLabel" x="500" y="817">Primary endpoint: 34/92 finalized runs succeeded (37.0%).</text>
  <text class="small" x="500" y="842">Tier counts are maxima stored in RunRecord; they do not independently prove control mechanics.</text>
  <text class="source" x="55" y="898">Source: 92 finalized RunRecords and retained validator stdout excerpts</text>
</svg>
"""


STRUCTURAL = re.compile(
    r"^(?:Constraints:|Each turn has the form:|Continue the loop until you can emit:|"
    r"Format each turn as:|Thought:|Action:|Observation:|THOUGHT:|ACTION:)"
)


def load_prompt_module(name: str):
    path = REPO_ROOT / "agent" / "prompts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"trial2_prompt_{name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def logical_prompt_lines(value: str) -> list[str]:
    logical: list[str] = []
    for raw_line in value.rstrip("\n").splitlines():
        stripped = raw_line.strip()
        if not stripped:
            if logical and logical[-1] != "":
                logical.append("")
            continue
        indent = raw_line[: len(raw_line) - len(raw_line.lstrip())]
        if stripped.startswith("- ") or STRUCTURAL.match(stripped):
            logical.append(indent + stripped)
        elif not logical or logical[-1] == "":
            logical.append(stripped)
        else:
            logical[-1] += " " + stripped
    return logical


def wrap_prompt(value: str) -> list[str]:
    output: list[str] = []
    for logical_line in logical_prompt_lines(value):
        if not logical_line:
            output.append("")
            continue
        indent = logical_line[: len(logical_line) - len(logical_line.lstrip())]
        wrapper = textwrap.TextWrapper(
            width=80,
            initial_indent=indent,
            subsequent_indent=indent,
            break_long_words=True,
            break_on_hyphens=False,
        )
        output.extend(wrapper.wrap(logical_line.strip()))
    assert all(len(line) <= 80 for line in output)
    return output


def prompt_text(lines: list[str], x: int, y: int, line_height: int) -> str:
    spans = []
    for index, line in enumerate(lines):
        content = escape(line, quote=False) if line else "&#160;"
        spans.append(
            f'<tspan x="{x}" dy="{0 if index == 0 else line_height}">{content}</tspan>'
        )
    return (
        f'<text class="prompt" x="{x}" y="{y}" xml:space="preserve">'
        + "".join(spans)
        + "</text>"
    )


def prompt_section(
    x: int, y: int, width: int, title: str, value: str
) -> tuple[str, int]:
    lines = wrap_prompt(value)
    font_size, line_height = 21, 27
    top, title_height = 20, 28
    bottom = 4 if title == "SYSTEM PROMPT" else 16
    height = top + title_height + len(lines) * line_height + bottom
    return (
        "\n".join(
            [
                f'<rect class="section-box" x="{x}" y="{y}" width="{width}" height="{height}" rx="14"/>',
                f'<text class="section-title" x="{x + 20}" y="{y + 38}">{title}</text>',
                prompt_text(
                    lines, x + 20, y + top + title_height + font_size, line_height
                ),
            ]
        ),
        height,
    )


def prompt_card_metrics(module) -> tuple[list[tuple[str, str, int]], int]:
    sections = []
    total = 0
    for title, value in (
        ("SYSTEM PROMPT", module.SYSTEM),
        ("TOOL-USE PROMPT", module.TOOL_USE),
        ("TASK PROMPT TEMPLATE", module.task("{binary_id}")),
    ):
        _, height = prompt_section(0, 0, 0, title, value)
        sections.append((title, value, height))
        total += height
    return sections, total


def prompt_comparison() -> str:
    methods = (
        ("Zero-shot", "zero_shot.py", "#2563eb", load_prompt_module("zero_shot")),
        ("ReAct", "react.py", "#0f766e", load_prompt_module("react")),
        (
            "Chain of thought",
            "chain_of_thought.py",
            "#7c3aed",
            load_prompt_module("chain_of_thought"),
        ),
    )
    metrics = [prompt_card_metrics(module) for _, _, _, module in methods]
    header_source = 120
    minimum_gap = 16
    bottom = 14
    target_height = max(
        header_source + total + 2 * minimum_gap + bottom for _, total in metrics
    )
    width, card_width = 3600, 1120
    height = 1050
    x_positions = (70, 1240, 2410)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="2400" height="700" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        "<title id=\"title\">Trial 2 prompting methods: verbatim comparison</title>",
        "<desc id=\"desc\">Three-column comparison of Trial 2's system, tool-use, and task prompt templates.</desc>",
        """<style>
    .title { font: 700 48px system-ui, sans-serif; fill: #172554; }
    .sub { font: 24px system-ui, sans-serif; fill: #475569; }
    .method { font: 700 31px system-ui, sans-serif; fill: #fff; }
    .source { font: 18px system-ui, sans-serif; fill: #64748b; }
    .order { font: 700 17px system-ui, sans-serif; fill: #fff; }
    .outer { fill: #fff; stroke: #cbd5e1; stroke-width: 3; }
    .section-box { fill: #f8fafc; stroke: #e2e8f0; stroke-width: 2; }
    .section-title { font: 700 17px system-ui, sans-serif; fill: #172554; letter-spacing: 1px; }
    .prompt { font: 21px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; fill: #1e293b; }
  </style>""",
        f'<rect width="{width}" height="{height}" fill="#f8fafc"/>',
        '<text class="title" x="70" y="76">Trial 2 prompting methods — verbatim comparison</text>',
        '<text class="sub" x="70" y="116">Three configured arms; every displayed prompt line is limited to 80 characters</text>',
    ]
    for index, ((label, filename, color, module), (sections, total), x) in enumerate(
        zip(methods, metrics, x_positions), 1
    ):
        extra = target_height - (header_source + total + bottom)
        gaps = (extra // 2, extra - extra // 2)
        y = 155
        parts.extend(
            [
                f'<rect class="outer" x="{x}" y="{y}" width="{card_width}" height="{target_height}" rx="22"/>',
                f'<path d="M{x + 22} {y} H{x + card_width - 22} Q{x + card_width} {y} {x + card_width} {y + 22} V{y + 78} H{x} V{y + 22} Q{x} {y} {x + 22} {y} Z" fill="{color}"/>',
                f'<text class="order" x="{x + 30}" y="{y + 34}">{index:02d}</text>',
                f'<text class="method" x="{x + 76}" y="{y + 52}">{label}</text>',
                f'<text class="source" x="{x + 26}" y="{y + 108}">agent/prompts/{filename}</text>',
            ]
        )
        section_y = y + header_source
        for section_index, (title, value, _) in enumerate(sections):
            markup, section_height = prompt_section(
                x + 22, section_y, card_width - 44, title, value
            )
            parts.append(markup)
            section_y += section_height
            if section_index < 2:
                section_y += gaps[section_index]
    parts.extend(
        [
            '<text class="source" x="70" y="1028">Source: agent/prompts/{zero_shot,react,chain_of_thought}.py • Task prompts shown with runtime {binary_id} placeholder</text>',
            "</svg>",
            "",
        ]
    )
    return "\n".join(parts)


def configuration_diagram(
    records: list[dict[str, Any]], planned: int, attempts: int, partials: int
) -> str:
    by_backend = collections.Counter(r["backend_handle"] for r in records)
    by_binary = collections.Counter(r["binary_id"] for r in records)
    by_strategy = collections.Counter(r["prompting_strategy"] for r in records)
    successes = sum(r["outcome"] == "success" for r in records)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1536" height="1024" viewBox="0 0 1536 1024" role="img" aria-labelledby="title desc">
  <title id="title">SARA Trial 2 configuration and execution</title>
  <desc id="desc">Trial 2 used four binaries, six backends, three strategies, two replicates, a 500,000-token limit, and a 600-second limit.</desc>
  <style>
    .title {{ font: 800 48px system-ui, sans-serif; fill: #071a4d; letter-spacing: 2px; }}
    .headline {{ font: 800 31px system-ui, sans-serif; fill: #071a4d; }}
    .sub {{ font: 750 24px system-ui, sans-serif; fill: #071a4d; }}
    .panel {{ fill: #fff; stroke: #071a4d; stroke-width: 2.5; }}
    .panelTitle {{ font: 750 24px system-ui, sans-serif; fill: #071a4d; letter-spacing: 1px; }}
    .group {{ font: 750 20px system-ui, sans-serif; fill: #123b4a; }}
    .groupOrange {{ font: 750 20px system-ui, sans-serif; fill: #c42d09; }}
    .item {{ font: 18px ui-monospace, monospace; fill: #123b4a; }}
    .itemOrange {{ font: 18px ui-monospace, monospace; fill: #c42d09; }}
    .strategy {{ font: 700 25px ui-monospace, monospace; fill: #071a4d; }}
    .limit {{ font: 20px ui-monospace, monospace; fill: #071a4d; }}
    .foot {{ font: 700 20px system-ui, sans-serif; fill: #071a4d; }}
    .caveat {{ font: 15px system-ui, sans-serif; fill: #64748b; }}
  </style>
  <rect width="1536" height="1024" fill="#fafafa"/>
  <text class="title" x="768" y="54" text-anchor="middle">SARA TRIAL 2 — CONFIGURATION &amp; EXECUTION</text>
  <text class="headline" x="768" y="100" text-anchor="middle">4 BINARIES × 6 BACKENDS × 3 STRATEGIES = 72 CELLS</text>
  <text class="sub" x="768" y="137" text-anchor="middle">2 REPLICATES PER CELL → {planned} PLANNED RUNS</text>
  <text class="sub" x="768" y="169" text-anchor="middle">{attempts} ATTEMPT DIRECTORIES → {len(records)} FINALIZED + {partials} PARTIAL</text>
  <text class="sub" x="768" y="201" text-anchor="middle">{planned - attempts} PLANNED RUNS PRODUCED NO ARCHIVED DIRECTORY</text>

  <rect class="panel" x="55" y="220" width="460" height="505" rx="12"/>
  <text class="panelTitle" x="285" y="258" text-anchor="middle">BINARIES · FINALIZED RUNS</text>
  <rect class="panel" x="73" y="276" width="424" height="92" rx="9"/>
  <text class="group" x="285" y="305" text-anchor="middle">TIER −1 · BASELINE</text>
  <text class="item" x="285" y="340" text-anchor="middle">ret2win-baseline · {by_binary['ret2win-baseline']}</text>
  <rect class="panel" x="73" y="380" width="424" height="92" rx="9"/>
  <text class="group" x="285" y="409" text-anchor="middle">HIGH · DARPA CGC</text>
  <text class="item" x="285" y="444" text-anchor="middle">cgc-cadet-00001 · {by_binary['cgc-cadet-00001']}</text>
  <rect x="73" y="484" width="424" height="92" rx="9" fill="#fff" stroke="#c42d09" stroke-width="2"/>
  <text class="groupOrange" x="285" y="513" text-anchor="middle">MEDIUM · ISP RAS SYNTHETIC</text>
  <text class="itemOrange" x="285" y="548" text-anchor="middle">ropbench-synth-ex005 · {by_binary['ropbench-synth-ex005']}</text>
  <rect class="panel" x="73" y="588" width="424" height="112" rx="9"/>
  <text class="group" x="285" y="620" text-anchor="middle">LOW · BRONCOCTF 2026</text>
  <text class="item" x="285" y="657" text-anchor="middle">broncoctf2026-</text>
  <text class="item" x="285" y="682" text-anchor="middle">proper-pwning · {by_binary['broncoctf2026-proper-pwning']}</text>

  <rect class="panel" x="535" y="220" width="460" height="505" rx="12"/>
  <text class="panelTitle" x="765" y="258" text-anchor="middle">BACKENDS · FINALIZED RUNS</text>
  <rect class="panel" x="553" y="276" width="424" height="126" rx="9"/>
  <text class="group" x="765" y="305" text-anchor="middle">PREMIUM · HOSTED</text>
  <text class="item" x="765" y="340" text-anchor="middle">claude-sonnet · {by_backend['claude-sonnet']}</text>
  <text class="item" x="765" y="372" text-anchor="middle">gpt-5 · {by_backend['gpt-5']}</text>
  <rect x="553" y="414" width="424" height="126" rx="9" fill="#fff" stroke="#c42d09" stroke-width="2"/>
  <text class="groupOrange" x="765" y="443" text-anchor="middle">OPEN WEIGHT · LM STUDIO</text>
  <text class="itemOrange" x="765" y="478" text-anchor="middle">gpt-oss-20b · {by_backend['gpt-oss-20b']}</text>
  <text class="itemOrange" x="765" y="510" text-anchor="middle">qwen3-coder-30b · {by_backend['qwen3-coder-30b']}</text>
  <rect class="panel" x="553" y="552" width="424" height="148" rx="9"/>
  <text class="group" x="765" y="581" text-anchor="middle">UNRESTRICTED · LM STUDIO</text>
  <text class="item" x="765" y="616" text-anchor="middle">whiterabbitneo-v3-7b · {by_backend['whiterabbitneo-v3-7b']}</text>
  <text class="item" x="765" y="650" text-anchor="middle">qwen3-30b-abliterated ·</text>
  <text class="item" x="765" y="678" text-anchor="middle">{by_backend['qwen3-30b-abliterated']}</text>

  <rect class="panel" x="1015" y="220" width="466" height="505" rx="12"/>
  <text class="panelTitle" x="1248" y="258" text-anchor="middle">STRATEGIES · FINALIZED RUNS</text>
  <rect class="panel" x="1033" y="292" width="430" height="105" rx="9"/>
  <text class="strategy" x="1248" y="355" text-anchor="middle">zero_shot · {by_strategy['zero_shot']}</text>
  <rect class="panel" x="1033" y="420" width="430" height="105" rx="9"/>
  <text class="strategy" x="1248" y="483" text-anchor="middle">chain_of_thought · {by_strategy['chain_of_thought']}</text>
  <rect class="panel" x="1033" y="548" width="430" height="105" rx="9"/>
  <text class="strategy" x="1248" y="611" text-anchor="middle">react · {by_strategy['react']}</text>

  <rect class="panel" x="55" y="738" width="1426" height="78" rx="10"/>
  <text class="panelTitle" x="768" y="765" text-anchor="middle">RUN LIMITS</text>
  <rect class="panel" x="70" y="775" width="340" height="32" rx="6"/><text class="limit" x="240" y="799" text-anchor="middle">500,000 tokens</text>
  <rect class="panel" x="420" y="775" width="340" height="32" rx="6"/><text class="limit" x="590" y="799" text-anchor="middle">600 seconds</text>
  <rect class="panel" x="770" y="775" width="340" height="32" rx="6"/><text class="limit" x="940" y="799" text-anchor="middle">100-reason-turn backstop</text>
  <rect class="panel" x="1120" y="775" width="346" height="32" rx="6"/><text class="limit" x="1293" y="799" text-anchor="middle">max_nudges: 3 · ignored</text>

  <rect class="panel" x="55" y="828" width="1426" height="88" rx="10"/>
  <text class="panelTitle" x="768" y="855" text-anchor="middle">ACTIVE PREMIUM COST CAPS</text>
  <rect class="panel" x="260" y="866" width="480" height="34" rx="6"/><text class="limit" x="500" y="891" text-anchor="middle">claude-sonnet · $75</text>
  <rect class="panel" x="795" y="866" width="480" height="34" rx="6"/><text class="limit" x="1035" y="891" text-anchor="middle">gpt-5 · $100</text>

  <text class="foot" x="350" y="949" text-anchor="middle">output_dir: ./runs</text>
  <text class="foot" x="768" y="949" text-anchor="middle">overrides: {{}}</text>
  <text class="foot" x="1160" y="949" text-anchor="middle">PRIMARY ENDPOINT: {successes} / {len(records)}</text>
  <text class="caveat" x="768" y="984" text-anchor="middle">Aggregate experiments.yaml shown; exact runtime split configuration files were not archived.</text>
</svg>
"""


def main() -> None:
    records, terminations, partials = load_metadata()
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    planned = (
        len(config["binaries"])
        * len(config["backends"])
        * len(config["strategies"])
        * config["replicates"]
    )
    attempts = len(records) + partials
    assert planned == 144
    assert len(records) == 92
    assert partials == 4
    assert sum(r["outcome"] == "success" for r in records) == 34

    write_svg(
        "01_matrix_accounting.svg",
        matrix_accounting(planned, len(records), partials, attempts),
    )
    write_svg(
        "02_backend_termination_mix.svg",
        backend_termination_mix(records, terminations),
    )
    write_svg("03_strategy_engagement.svg", strategy_comparison(records))
    write_svg("04_progress_funnel.svg", progress_funnel(records))
    write_svg("05_prompt_method_verbatim_comparison.svg", prompt_comparison())
    write_svg(
        "experiment_configuration_trial_2_actual.svg",
        configuration_diagram(records, planned, attempts, partials),
    )


if __name__ == "__main__":
    main()
