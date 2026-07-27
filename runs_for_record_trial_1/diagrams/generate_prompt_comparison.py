"""Generate the Trial 1 verbatim prompt-comparison diagram as native SVG."""

from __future__ import annotations

from html import escape
import importlib.util
from pathlib import Path
import re
import textwrap


REPO_ROOT = Path(__file__).resolve().parents[2]


def load_prompt_module(name: str):
    """Load one prompt file without importing the dependency-heavy agent package."""
    path = REPO_ROOT / "agent" / "prompts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"sara_prompt_{name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load prompt module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


zero_shot = load_prompt_module("zero_shot")
react = load_prompt_module("react")
chain_of_thought = load_prompt_module("chain_of_thought")
majorca = load_prompt_module("majorca")


WIDTH = 3600
HEIGHT = 4200
DISPLAY_WIDTH = 2400
DISPLAY_HEIGHT = 2800
OUTPUT = Path(__file__).with_name("05_prompt_method_verbatim_comparison.svg")
MAX_PROMPT_COLUMNS = 80

METHODS = (
    ("Zero-shot", "zero_shot.py", "#2563eb", zero_shot),
    ("ReAct", "react.py", "#0f766e", react),
    ("Chain of thought", "chain_of_thought.py", "#7c3aed", chain_of_thought),
    ("MAJORCA", "majorca.py", "#f59e0b", majorca),
)

STRUCTURAL = re.compile(
    r"^(?:"
    r"Constraints:|Each turn has the form:|Continue the loop until you can emit:|"
    r"Format each turn as:|STAGE [1-4] - |Target capability:|RESTRICTED SYMBOLS|"
    r"\d+\. |NoOp\b|LoadConst\b|InitConst\b|MoveReg\b|Arithmetic\b|LoadMem\b|"
    r"InitMem\b|ArithLoad\b|StackPivot\b|Syscall / Int\b|Call / CallMem\b|"
    r"Thought:|Action:|Observation:|THOUGHT:|ACTION:"
    r")"
)


def logical_prompt_lines(value: str) -> list[str]:
    """Remove source-code hard wraps while retaining prompt structure and wording."""
    logical: list[str] = []
    for raw_line in value.rstrip("\n").splitlines():
        stripped = raw_line.strip()
        if not stripped:
            if logical and logical[-1] != "":
                logical.append("")
            continue

        indent = raw_line[: len(raw_line) - len(raw_line.lstrip())]
        starts_item = stripped.startswith("- ") or STRUCTURAL.match(stripped) is not None
        if starts_item:
            logical.append(indent + stripped)
        elif not logical or logical[-1] == "":
            logical.append(stripped)
        else:
            logical[-1] += " " + stripped
    return logical


def wrap_prompt(value: str) -> list[str]:
    """Wrap every displayed prompt line to at most 80 characters."""
    output: list[str] = []
    for logical_line in logical_prompt_lines(value):
        if not logical_line:
            output.append("")
            continue
        indent = logical_line[: len(logical_line) - len(logical_line.lstrip())]
        wrapper = textwrap.TextWrapper(
            width=MAX_PROMPT_COLUMNS,
            initial_indent=indent,
            subsequent_indent=indent,
            expand_tabs=False,
            replace_whitespace=False,
            drop_whitespace=True,
            break_long_words=True,
            break_on_hyphens=False,
        )
        output.extend(wrapper.wrap(logical_line.strip()) or [""])
    assert all(len(line) <= MAX_PROMPT_COLUMNS for line in output)
    return output


def text_lines(lines: list[str], x: int, y: int, line_height: int, css_class: str) -> str:
    tspans = []
    for index, line in enumerate(lines):
        dy = 0 if index == 0 else line_height
        # An empty SVG tspan can be collapsed by renderers even though its line
        # was included in the section-height calculation. A non-breaking space
        # preserves the intended paragraph break instead of leaving that
        # reserved height as apparent padding below the final prompt line.
        content = escape(line, quote=False) if line else "&#160;"
        tspans.append(
            f'<tspan x="{x}" dy="{dy}">{content}</tspan>'
        )
    return f'<text class="{css_class}" x="{x}" y="{y}" xml:space="preserve">' + "".join(
        tspans
    ) + "</text>"


def section(
    *,
    x: int,
    y: int,
    width: int,
    title: str,
    prompt: str,
    font_size: int,
    compact: bool = False,
) -> tuple[str, int]:
    lines = wrap_prompt(prompt)
    line_height = round(font_size * 1.3)
    top_padding = 20 if compact else 24
    title_height = 28 if compact else 32
    # System prompts are the longest section in every card. Keep only a small
    # optical inset after their final baseline instead of the general padding.
    bottom_padding = 4 if title == "SYSTEM PROMPT" else (18 if compact else 22)
    height = top_padding + title_height + len(lines) * line_height + bottom_padding
    markup = [
        f'<rect class="section-box" x="{x}" y="{y}" width="{width}" height="{height}" rx="16"/>',
        f'<text class="section-title" x="{x + 24}" y="{y + 40}">{escape(title)}</text>',
        text_lines(
            lines,
            x + 24,
            y + top_padding + title_height + font_size,
            line_height,
            f"prompt prompt-{font_size}",
        ),
    ]
    return "\n".join(markup), height


def method_card(
    *,
    index: int,
    label: str,
    filename: str,
    color: str,
    module,
    x: int,
    y: int,
    width: int,
    font_size: int,
    compact: bool,
) -> tuple[str, int]:
    card_parts: list[str] = []
    header_height = 78
    source_height = 42
    inner_gap = 14 if compact else 18
    section_x = x + 24
    section_width = width - 48
    section_y = y + header_height + source_height

    sections: list[str] = []
    for section_title, prompt in (
        ("SYSTEM PROMPT", module.SYSTEM),
        ("TOOL-USE PROMPT", module.TOOL_USE),
        ("TASK PROMPT TEMPLATE", module.task("{binary_id}")),
    ):
        markup, section_height = section(
            x=section_x,
            y=section_y,
            width=section_width,
            title=section_title,
            prompt=prompt,
            font_size=font_size,
            compact=compact,
        )
        sections.append(markup)
        section_y += section_height + inner_gap

    card_height = section_y - y + 10
    card_parts.extend(
        [
            f'<rect class="outer" x="{x}" y="{y}" width="{width}" height="{card_height}" rx="22"/>',
            f'<path d="M{x + 22} {y} H{x + width - 22} Q{x + width} {y} {x + width} {y + 22} V{y + header_height} H{x} V{y + 22} Q{x} {y} {x + 22} {y} Z" fill="{color}"/>',
            f'<text class="order" x="{x + 32}" y="{y + 34}">{index:02d}</text>',
            f'<text class="method" x="{x + 78}" y="{y + 52}">{escape(label)}</text>',
            f'<text class="source" x="{x + 28}" y="{y + header_height + 30}">agent/prompts/{filename}</text>',
            *sections,
        ]
    )
    return "\n".join(card_parts), card_height


def generate() -> str:
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{DISPLAY_WIDTH}" height="{DISPLAY_HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-labelledby="title desc">',
        "  <title id=\"title\">Trial 1 prompting methods: verbatim comparison</title>",
        "  <desc id=\"desc\">Two-column comparison of the exact system, tool-use, and task prompt templates. Zero-shot, ReAct, and Chain of thought are stacked in the left column; MAJORCA occupies the right column.</desc>",
        """  <style>
    .title { font: 700 48px system-ui, sans-serif; fill: #172554; }
    .sub { font: 24px system-ui, sans-serif; fill: #475569; }
    .method { font: 700 32px system-ui, sans-serif; fill: #fff; }
    .source { font: 18px system-ui, sans-serif; fill: #64748b; }
    .order { font: 700 17px system-ui, sans-serif; fill: #fff; }
    .outer { fill: #fff; stroke: #cbd5e1; stroke-width: 3; }
    .section-box { fill: #f8fafc; stroke: #e2e8f0; stroke-width: 2; }
    .section-title { font: 700 18px system-ui, sans-serif; fill: #172554; letter-spacing: 1.2px; }
    .prompt { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; fill: #1e293b; }
    .prompt-32 { font-size: 32px; }
  </style>""",
        f'  <rect width="{WIDTH}" height="{HEIGHT}" fill="#f8fafc"/>',
        '  <text id="title" class="title" x="70" y="76">Trial 1 prompting methods — verbatim comparison</text>',
        '  <text class="sub" x="70" y="116">Every displayed prompt line is limited to 80 characters; wording and structure preserved</text>',
    ]

    left_x = 70
    right_x = 1835
    column_width = 1695

    # Measure both columns first, then distribute the MAJORCA height surplus
    # between the two left-column row gaps. This aligns the column bottoms.
    left_heights = []
    for index, (label, filename, color, module) in enumerate(METHODS[:3], start=1):
        _, card_height = method_card(
            index=index,
            label=label,
            filename=filename,
            color=color,
            module=module,
            x=left_x,
            y=0,
            width=column_width,
            font_size=32,
            compact=True,
        )
        left_heights.append(card_height)

    label, filename, color, module = METHODS[3]
    majorca_markup, majorca_height = method_card(
        index=4,
        label=label,
        filename=filename,
        color=color,
        module=module,
        x=right_x,
        y=155,
        width=column_width,
        font_size=32,
        compact=False,
    )
    total_row_space = majorca_height - sum(left_heights)
    if total_row_space < 0:
        raise RuntimeError("left-column cards are taller than the MAJORCA card")
    row_gaps = (total_row_space // 2, total_row_space - total_row_space // 2)

    left_y = 155
    for offset, (label, filename, color, module) in enumerate(METHODS[:3]):
        index = offset + 1
        markup, card_height = method_card(
            index=index,
            label=label,
            filename=filename,
            color=color,
            module=module,
            x=left_x,
            y=left_y,
            width=column_width,
            font_size=32,
            compact=True,
        )
        parts.append(markup)
        left_y += card_height
        if offset < len(row_gaps):
            left_y += row_gaps[offset]

    parts.append(majorca_markup)

    parts.extend(
        [
            '  <text class="source" x="70" y="4165">Source: agent/prompts/{zero_shot,react,chain_of_thought,majorca}.py • Task prompts shown as runtime templates with {binary_id}</text>',
            "</svg>",
            "",
        ]
    )
    return "\n".join(parts)


if __name__ == "__main__":
    OUTPUT.write_text(generate(), encoding="utf-8")
