# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# markdown_to_html(text: str, heading_base: int = 3) -> str
# escape_html(text: str) -> str
# ─────────────────────────────────────────────────────────
"""The markdown subset the report agent actually emits, typeset for print.

The PDF exporter previously did `content.replace("\\n", "<br>")`, which turns a
markdown table into a wall of pipes and a bulleted list into a paragraph with
hyphens in it. On screen that reads as sloppy; on paper it reads as a document
nobody proof-read, which is the opposite of what an exported report is for.

Scope is deliberately the subset `REACT_PROMPT` asks for and `SectionRenderer`
renders — headings, bold, italic, inline code, ordered and unordered lists,
blockquotes, rules and pipe tables. Anything outside that is emitted as plain
text rather than guessed at: a half-understood construct rendered wrongly is
worse than one rendered literally.

Two print-specific behaviours that a generic markdown library would not give:

* **Headings are demoted into the document's own hierarchy.** A section's `##`
  is a *sub*-heading of the section it sits in, not a peer of the section title,
  so `heading_base` shifts the whole run down. Without this the contents page
  and the running header disagree with the body about what a heading means.

* **Numeric table columns are detected and right-aligned** with tabular
  figures, and every table carries `<thead>` so it can repeat across a page
  break. Columns of numerals that do not line up are the single most common
  tell of a report that was printed from a web page.
"""
from __future__ import annotations

import re

_TABLE_SEPARATOR = re.compile(r"^\s*\|?[\s:-]*[-:]{2,}[\s:|-]*\|?\s*$")
_ORDERED_ITEM = re.compile(r"^\s{0,3}(\d{1,3})[.)]\s+(.*)$")
_UNORDERED_ITEM = re.compile(r"^\s{0,3}[-*+]\s+(.*)$")
_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
_RULE = re.compile(r"^\s{0,3}([-*_])(?:\s*\1){2,}\s*$")
_BLOCKQUOTE = re.compile(r"^\s{0,3}>\s?(.*)$")

_INLINE_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_ITALIC = re.compile(r"(?<![*\w])\*(?!\s)([^*\n]+?)(?<!\s)\*(?!\*)")
_UNDERSCORE_ITALIC = re.compile(r"(?<![_\w])_(?!\s)([^_\n]+?)(?<!\s)_(?!\w)")

# A cell is numeric if it is a number, possibly signed, with optional
# thousands separators, decimals, a percent sign, a currency prefix, or a
# bracketed interval. Deliberately strict: "Round 3" must not right-align.
_NUMERIC_CELL = re.compile(
    r"^[\s(\[]*[+\-−]?\$?\d[\d,]*(?:\.\d+)?\s*%?"
    r"(?:\s*(?:to|[-–−,])\s*[+\-−]?\$?\d[\d,]*(?:\.\d+)?\s*%?)?"
    r"[\s)\]]*$"
)


def escape_html(text: str) -> str:
    """Escape for HTML text content and double-quoted attributes."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _inline(text: str) -> str:
    """Inline markdown on already-escaped text."""
    out = escape_html(text)
    out = _INLINE_CODE.sub(lambda m: f"<code>{m.group(1)}</code>", out)
    out = _BOLD.sub(lambda m: f"<strong>{m.group(1)}</strong>", out)
    out = _ITALIC.sub(lambda m: f"<em>{m.group(1)}</em>", out)
    out = _UNDERSCORE_ITALIC.sub(lambda m: f"<em>{m.group(1)}</em>", out)
    return out


def _is_numeric(cell: str) -> bool:
    stripped = cell.strip()
    if not stripped or stripped in {"-", "—", "–"}:
        return False
    return bool(_NUMERIC_CELL.match(stripped))


def _split_row(line: str) -> list[str]:
    trimmed = line.strip()
    if trimmed.startswith("|"):
        trimmed = trimmed[1:]
    if trimmed.endswith("|"):
        trimmed = trimmed[:-1]
    return [cell.strip() for cell in trimmed.split("|")]


def _render_table(header: list[str], rows: list[list[str]]) -> str:
    width = max([len(header)] + [len(r) for r in rows]) if rows else len(header)
    header = header + [""] * (width - len(header))
    padded = [r + [""] * (width - len(r)) for r in rows]

    # A column is numeric when the majority of its non-empty cells parse as
    # numbers. Majority rather than all: one "n/a" in a column of figures must
    # not knock the whole column back to left-aligned.
    numeric_cols: set[int] = set()
    for col in range(width):
        values = [r[col] for r in padded if r[col].strip()]
        if values and sum(_is_numeric(v) for v in values) * 2 > len(values):
            numeric_cols.add(col)

    head_cells = "".join(
        f'<th class="{"num" if i in numeric_cols else "txt"}">{_inline(c)}</th>'
        for i, c in enumerate(header)
    )
    body_rows = "".join(
        "<tr>"
        + "".join(
            f'<td class="{"num" if i in numeric_cols else "txt"}">{_inline(c)}</td>'
            for i, c in enumerate(row)
        )
        + "</tr>"
        for row in padded
    )
    return (
        '<table class="md-table"><thead><tr>'
        f"{head_cells}</tr></thead><tbody>{body_rows}</tbody></table>"
    )


def markdown_to_html(text: str, heading_base: int = 3) -> str:
    """Convert the supported markdown subset to semantic print HTML.

    `heading_base` is the level a top-level `#` maps to. The default of 3 keeps
    narrative headings below the document's own `<h2>` section titles, so the
    contents page, the running header and the body all agree on what a heading
    is.
    """
    if not text or not text.strip():
        return ""

    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out: list[str] = []
    paragraph: list[str] = []
    quote: list[str] = []
    list_items: list[str] = []
    list_tag = ""
    index = 0

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            out.append(f"<p>{_inline(' '.join(paragraph))}</p>")
            paragraph = []

    def flush_list() -> None:
        nonlocal list_items, list_tag
        if list_items:
            items = "".join(f"<li>{_inline(i)}</li>" for i in list_items)
            out.append(f"<{list_tag}>{items}</{list_tag}>")
            list_items = []
            list_tag = ""

    def flush_quote() -> None:
        nonlocal quote
        if quote:
            out.append(f"<blockquote>{_inline(' '.join(quote))}</blockquote>")
            quote = []

    def flush_all() -> None:
        flush_paragraph()
        flush_list()
        flush_quote()

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if not stripped:
            flush_all()
            index += 1
            continue

        # Table: a pipe row followed by a separator row.
        if (
            "|" in stripped
            and index + 1 < len(lines)
            and _TABLE_SEPARATOR.match(lines[index + 1])
        ):
            flush_all()
            header = _split_row(stripped)
            index += 2
            rows: list[list[str]] = []
            while index < len(lines):
                candidate = lines[index].strip()
                if "|" not in candidate or _TABLE_SEPARATOR.match(candidate):
                    break
                rows.append(_split_row(candidate))
                index += 1
            out.append(_render_table(header, rows))
            continue

        if _RULE.match(line):
            flush_all()
            out.append('<hr class="md-rule">')
            index += 1
            continue

        heading = _HEADING.match(line)
        if heading:
            flush_all()
            level = min(6, heading_base + len(heading.group(1)) - 1)
            out.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
            index += 1
            continue

        blockquote = _BLOCKQUOTE.match(line)
        if blockquote:
            flush_paragraph()
            flush_list()
            quote.append(blockquote.group(1).strip())
            index += 1
            continue

        unordered = _UNORDERED_ITEM.match(line)
        if unordered:
            flush_paragraph()
            flush_quote()
            if list_tag and list_tag != "ul":
                flush_list()
            list_tag = "ul"
            list_items.append(unordered.group(1).strip())
            index += 1
            continue

        ordered = _ORDERED_ITEM.match(line)
        if ordered:
            flush_paragraph()
            flush_quote()
            if list_tag and list_tag != "ol":
                flush_list()
            list_tag = "ol"
            list_items.append(ordered.group(2).strip())
            index += 1
            continue

        flush_list()
        flush_quote()
        paragraph.append(stripped)
        index += 1

    flush_all()
    return "".join(out)
