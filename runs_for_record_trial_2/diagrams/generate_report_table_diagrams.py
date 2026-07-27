"""Render every Markdown table in both Trial 2 analyses as native SVG.

This generator reads only the two Markdown reports. It does not open the run
archive or any submitted artifact.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path
import re
import textwrap


TRIAL_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_ROOT = Path(__file__).resolve().parent / "report_tables"
REPORTS = (
    ("opus5", TRIAL_ROOT / "RUN_FOR_RECORD_ANALYSIS.Opus5.md"),
    ("sol56", TRIAL_ROOT / "RUN_FOR_RECORD_ANALYSIS.Sol56.md"),
)

CANVAS_WIDTH = 1600
MARGIN = 60
TABLE_WIDTH = CANVAS_WIDTH - 2 * MARGIN
CELL_FONT_SIZE = 17
CELL_LINE_HEIGHT = 24


@dataclass
class Table:
    number: int
    source_line: int
    heading: str
    context: str
    headers: list[str]
    rows: list[list[str]]


def split_markdown_row(line: str) -> list[str]:
    """Split a Markdown table row while respecting escaped and code-span pipes."""
    text = line.strip()
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|"):
        text = text[:-1]
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    in_code = False
    for char in text:
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
            current.append(char)
        elif char == "`":
            in_code = not in_code
            current.append(char)
        elif char == "|" and not in_code:
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    cells.append("".join(current).strip())
    return cells


def clean_markdown(value: str) -> str:
    value = value.replace("<br>", "\n").replace("<br/>", "\n")
    value = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", value)
    value = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value)
    value = value.replace("**", "").replace("__", "")
    value = value.replace("`", "")
    value = value.replace("\\|", "|")
    return re.sub(r"\s+", " ", value).strip()


def clean_heading(value: str) -> str:
    value = value.lstrip("#").strip()
    return clean_markdown(value)


def parse_tables(path: Path) -> list[Table]:
    lines = path.read_text(encoding="utf-8").splitlines()
    tables: list[Table] = []
    heading = path.stem
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        if stripped.startswith("#"):
            heading = clean_heading(stripped)
        is_table = (
            index + 1 < len(lines)
            and stripped.startswith("|")
            and re.match(r"^\s*\|?\s*:?-+", lines[index + 1])
        )
        if not is_table:
            index += 1
            continue

        start = index
        block = []
        while index < len(lines) and lines[index].strip().startswith("|"):
            block.append(lines[index])
            index += 1
        headers = [clean_markdown(cell) for cell in split_markdown_row(block[0])]
        rows = [
            [clean_markdown(cell) for cell in split_markdown_row(line)]
            for line in block[2:]
        ]
        for row in rows:
            if len(row) < len(headers):
                row.extend([""] * (len(headers) - len(row)))
            elif len(row) > len(headers):
                raise RuntimeError(
                    f"{path.name}:{start + 1}: row has {len(row)} cells; "
                    f"header has {len(headers)}"
                )

        context = ""
        probe = start - 1
        while probe >= 0:
            candidate = lines[probe].strip()
            if candidate and candidate != "---":
                context = clean_heading(candidate)
                break
            probe -= 1
        tables.append(
            Table(
                number=len(tables) + 1,
                source_line=start + 1,
                heading=heading,
                context=context,
                headers=headers,
                rows=rows,
            )
        )
    return tables


def slugify(value: str) -> str:
    value = re.sub(r"^\d+(?:\.\d+)*\.?\s*", "", value)
    value = value.lower().replace("×", " x ")
    value = re.sub(r"[^a-z0-9]+", "_", value).strip("_")
    return value[:72] or "table"


def is_numeric_column(values: list[str]) -> bool:
    nonempty = [value for value in values if value]
    if not nonempty:
        return False
    numericish = re.compile(r"^[\d\s$€£.,%/+\-–—<>=()[\]:]+$")
    return sum(bool(numericish.match(value)) for value in nonempty) / len(nonempty) >= 0.8


def column_widths(table: Table) -> list[float]:
    columns = list(zip(table.headers, *table.rows))
    desired = []
    minimums = []
    for index, column in enumerate(columns):
        values = [str(value) for value in column]
        numeric = is_numeric_column(values[1:])
        longest = max(
            (len(part) for value in values for part in value.splitlines()),
            default=0,
        )
        if numeric:
            minimum = 105
            want = min(220, max(minimum, longest * 10 + 40))
        else:
            minimum = 175 if index == 0 else 135
            want = min(520, max(minimum, longest * 8.7 + 42))
        minimums.append(minimum)
        desired.append(want)

    total = sum(desired)
    if total <= TABLE_WIDTH:
        extra = TABLE_WIDTH - total
        weights = [max(1, width - minimum) for width, minimum in zip(desired, minimums)]
        weight_total = sum(weights)
        return [
            width + extra * weight / weight_total
            for width, weight in zip(desired, weights)
        ]

    shrinkable = sum(width - minimum for width, minimum in zip(desired, minimums))
    needed = total - TABLE_WIDTH
    if shrinkable < needed:
        scale = TABLE_WIDTH / sum(minimums)
        return [minimum * scale for minimum in minimums]
    return [
        width - needed * (width - minimum) / shrinkable
        for width, minimum in zip(desired, minimums)
    ]


def wrap_cell(value: str, pixel_width: float, bold: bool = False) -> list[str]:
    char_width = 9.4 if bold else 8.8
    width = max(8, int((pixel_width - 30) / char_width))
    output: list[str] = []
    for paragraph in value.splitlines() or [""]:
        if not paragraph:
            output.append("")
            continue
        wrapper = textwrap.TextWrapper(
            width=width,
            break_long_words=True,
            break_on_hyphens=False,
            replace_whitespace=True,
            drop_whitespace=True,
        )
        output.extend(wrapper.wrap(paragraph) or [""])
    return output or [""]


def svg_text(
    lines: list[str],
    *,
    x: float,
    y: float,
    css_class: str,
    anchor: str = "start",
) -> str:
    spans = []
    for line_index, line in enumerate(lines):
        content = escape(line, quote=False) if line else "&#160;"
        spans.append(
            f'<tspan x="{x:.1f}" dy="{0 if line_index == 0 else CELL_LINE_HEIGHT}">{content}</tspan>'
        )
    return (
        f'<text class="{css_class}" x="{x:.1f}" y="{y:.1f}" '
        f'text-anchor="{anchor}" xml:space="preserve">'
        + "".join(spans)
        + "</text>"
    )


def title_for(table: Table) -> str:
    context = table.context.rstrip(":")
    if context.startswith("#"):
        context = clean_heading(context)
    if 4 <= len(context) <= 105 and context != table.heading:
        if context.lower().startswith(("cell =", "all ", "per ", "finalized ", "broncoctf")):
            return context
        if context.startswith("Wilson 95%"):
            return context
    return table.heading


def render_table(report_key: str, report_name: str, table: Table) -> str:
    widths = column_widths(table)
    numeric_columns = [
        is_numeric_column([row[index] for row in table.rows])
        for index in range(len(table.headers))
    ]

    title = title_for(table)
    title_lines = textwrap.wrap(title, width=72, break_long_words=False) or [title]
    title_height = 44 * len(title_lines)
    top = 52
    subtitle_y = top + title_height + 18
    table_y = subtitle_y + 42

    wrapped_header = [
        wrap_cell(header, width, bold=True)
        for header, width in zip(table.headers, widths)
    ]
    header_height = max(58, max(map(len, wrapped_header)) * CELL_LINE_HEIGHT + 28)
    wrapped_rows: list[list[list[str]]] = []
    row_heights = []
    for row in table.rows:
        wrapped = [
            wrap_cell(value, width)
            for value, width in zip(row, widths)
        ]
        wrapped_rows.append(wrapped)
        row_heights.append(max(50, max(map(len, wrapped)) * CELL_LINE_HEIGHT + 26))

    table_height = header_height + sum(row_heights)
    canvas_height = int(table_y + table_height + 72)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{CANVAS_WIDTH}" height="{canvas_height}" viewBox="0 0 {CANVAS_WIDTH} {canvas_height}" role="img" aria-labelledby="title desc">',
        f'<title id="title">{escape(title)}</title>',
        f'<desc id="desc">Table {table.number} from {escape(report_name)}, source line {table.source_line}.</desc>',
        """<style>
    .title { font: 700 34px system-ui, sans-serif; fill: #172554; }
    .sub { font: 17px system-ui, sans-serif; fill: #475569; }
    .head { font: 700 17px system-ui, sans-serif; fill: #fff; }
    .cell { font: 17px system-ui, sans-serif; fill: #1e293b; }
    .cellStrong { font: 700 17px system-ui, sans-serif; fill: #172554; }
    .source { font: 14px system-ui, sans-serif; fill: #64748b; }
  </style>""",
        f'<rect width="{CANVAS_WIDTH}" height="{canvas_height}" fill="#f8fafc"/>',
    ]
    for line_index, line in enumerate(title_lines):
        parts.append(
            f'<text id="{"title" if line_index == 0 else ""}" class="title" '
            f'x="{MARGIN}" y="{top + 36 + line_index * 44}">{escape(line)}</text>'
        )
    parts.append(
        f'<text class="sub" x="{MARGIN}" y="{subtitle_y}">'
        f'{escape(report_name)} • Table {table.number:02d} • source line {table.source_line}</text>'
    )
    parts.append(
        f'<rect x="{MARGIN}" y="{table_y}" width="{TABLE_WIDTH}" height="{table_height}" '
        'rx="16" fill="#fff" stroke="#cbd5e1" stroke-width="2"/>'
    )
    parts.append(
        f'<path d="M{MARGIN + 16} {table_y} H{MARGIN + TABLE_WIDTH - 16} '
        f'Q{MARGIN + TABLE_WIDTH} {table_y} {MARGIN + TABLE_WIDTH} {table_y + 16} '
        f'V{table_y + header_height} H{MARGIN} V{table_y + 16} '
        f'Q{MARGIN} {table_y} {MARGIN + 16} {table_y} Z" fill="#172554"/>'
    )

    x = float(MARGIN)
    for index, (header, width, lines) in enumerate(
        zip(table.headers, widths, wrapped_header)
    ):
        if index:
            parts.append(
                f'<line x1="{x:.1f}" y1="{table_y}" x2="{x:.1f}" '
                f'y2="{table_y + table_height}" stroke="#cbd5e1"/>'
            )
        anchor = "middle" if numeric_columns[index] else "start"
        text_x = x + width / 2 if anchor == "middle" else x + 15
        baseline = table_y + 25 + (header_height - len(lines) * CELL_LINE_HEIGHT) / 2
        parts.append(
            svg_text(lines, x=text_x, y=baseline, css_class="head", anchor=anchor)
        )
        x += width

    y = table_y + header_height
    for row_index, (row, wrapped, row_height) in enumerate(
        zip(table.rows, wrapped_rows, row_heights)
    ):
        first = row[0].lower() if row else ""
        total_row = "total" in first or first in {"all", "overall"}
        fill = "#dbeafe" if total_row else ("#ffffff" if row_index % 2 == 0 else "#f1f5f9")
        parts.append(
            f'<rect x="{MARGIN}" y="{y}" width="{TABLE_WIDTH}" height="{row_height}" fill="{fill}"/>'
        )
        parts.append(
            f'<line x1="{MARGIN}" y1="{y}" x2="{MARGIN + TABLE_WIDTH}" y2="{y}" stroke="#e2e8f0"/>'
        )
        x = float(MARGIN)
        for column_index, (value, width, lines) in enumerate(
            zip(row, widths, wrapped)
        ):
            anchor = "middle" if numeric_columns[column_index] else "start"
            text_x = x + width / 2 if anchor == "middle" else x + 15
            baseline = y + 21 + (row_height - len(lines) * CELL_LINE_HEIGHT) / 2
            css = "cellStrong" if total_row or column_index == 0 else "cell"
            parts.append(
                svg_text(lines, x=text_x, y=baseline, css_class=css, anchor=anchor)
            )
            x += width
        y += row_height
    parts.extend(
        [
            f'<text class="source" x="{MARGIN}" y="{canvas_height - 27}">'
            f'Source: {escape(report_name)}, Markdown table beginning at line {table.source_line}</text>',
            "</svg>",
            "",
        ]
    )
    return "\n".join(parts)


def main() -> None:
    index_lines = [
        "# Trial 2 report-table diagram index",
        "",
        "Every Markdown table in both analyses is rendered as PNG and editable SVG.",
        "",
    ]
    total = 0
    for report_key, report_path in REPORTS:
        tables = parse_tables(report_path)
        output_dir = OUTPUT_ROOT / report_key
        output_dir.mkdir(parents=True, exist_ok=True)
        index_lines.extend([f"## {report_path.name}", ""])
        for table in tables:
            slug = slugify(title_for(table))
            stem = f"{table.number:02d}_{slug}"
            svg_name = f"{stem}.svg"
            (output_dir / svg_name).write_text(
                render_table(report_key, report_path.name, table),
                encoding="utf-8",
            )
            index_lines.append(
                f"- {table.number:02d}. [{title_for(table)}]"
                f"({report_key}/{stem}.png) "
                f"([SVG]({report_key}/{svg_name})) — source line {table.source_line}"
            )
            total += 1
        index_lines.append("")
    index_lines.append(f"Total tables rendered: **{total}**.")
    index_lines.append("")
    (OUTPUT_ROOT / "INDEX.md").write_text("\n".join(index_lines), encoding="utf-8")


if __name__ == "__main__":
    main()
