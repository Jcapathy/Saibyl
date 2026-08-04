# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# process_presentation(file_bytes: bytes, filename: str) -> dict
# ─────────────────────────────────────────────────────────
"""Read a `.pptx` deck.

A founder's deck is the single most ICP-dense thing they upload, and until this
module existed it was the one thing the pipeline could not read. `.pptx` was
accepted by both upload routes; the old media dispatcher handed it to the
document processor *labelled `docx`*, whose extractor looks for
`word/document.xml` — a member no PPTX archive contains. The chain then returned
the literal string `"[Unable to extract text from this DOCX file]"`, the row was
marked `complete`, and the deck contributed a sentence of error text to the
synthesis pass.

PPTX is a ZIP of `ppt/slides/slideN.xml`, and every run of text sits in an
`<a:t>` node, so stdlib is enough. Speaker notes are read too — they carry the
positioning argument the slide only gestures at.
"""
from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
import zipfile

import structlog

logger = structlog.get_logger()

_DRAWINGML_TEXT = "{http://schemas.openxmlformats.org/drawingml/2006/main}t"
_SLIDE_RE = re.compile(r"^ppt/slides/slide(\d+)\.xml$")
_NOTES_RE = re.compile(r"^ppt/notesSlides/notesSlide(\d+)\.xml$")

# Slides past this are appendix in every deck anyone has ever sent, and the
# synthesis pass truncates on characters anyway — this only bounds the parse.
_MAX_SLIDES = 200


def _text_of(xml_bytes: bytes) -> str:
    root = ET.fromstring(xml_bytes)
    runs = [(node.text or "").strip() for node in root.iter(_DRAWINGML_TEXT)]
    return "\n".join(run for run in runs if run)


def _numbered(names: list[str], pattern: re.Pattern[str]) -> list[tuple[int, str]]:
    """Slide members in slide order.

    Sorted numerically, not lexicographically: `zf.namelist()` order is archive
    order, and a plain string sort puts `slide10` before `slide2`, which
    reorders the narrative the deck is making.
    """
    found: list[tuple[int, str]] = []
    for name in names:
        match = pattern.match(name)
        if match:
            found.append((int(match.group(1)), name))
    return sorted(found)[:_MAX_SLIDES]


async def process_presentation(file_bytes: bytes, filename: str) -> dict:
    """Extract slide text and speaker notes from a PPTX file."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(file_bytes))
    except zipfile.BadZipFile as exc:
        # Raised, not returned as text. A deck we cannot open must fail the
        # document rather than land in `documents` as a `complete` row holding
        # an apology, which is what the previous path did.
        raise ValueError(f"{filename} is not a readable PPTX archive: {exc}") from exc

    with archive as zf:
        names = zf.namelist()
        slides = _numbered(names, _SLIDE_RE)
        notes = dict(_numbered(names, _NOTES_RE))

        parts: list[str] = []
        empty_slides = 0
        for number, member in slides:
            body = _text_of(zf.read(member))
            note_member = notes.get(number)
            note = _text_of(zf.read(note_member)) if note_member else ""
            if not body and not note:
                empty_slides += 1
                continue
            section = [f"## Slide {number}"]
            if body:
                section.append(body)
            if note:
                section.append(f"### Speaker notes\n{note}")
            parts.append("\n".join(section))

    text = "\n\n".join(parts)
    logger.info(
        "presentation_processed",
        filename=filename,
        slides=len(slides),
        slides_with_text=len(parts),
        # An all-image deck extracts nothing here and is a legitimate outcome,
        # but it is also indistinguishable from a broken parse unless counted.
        empty_slides=empty_slides,
        chars=len(text),
    )
    if not text.strip():
        raise ValueError(
            f"{filename} has {len(slides)} slides and no extractable text — it is "
            "most likely an image-only deck. Export the slides as images and "
            "upload those, so the vision pass can read them."
        )

    return {
        "extracted_text": text,
        "metadata": {
            "slides": len(slides),
            "slides_with_text": len(parts),
            "empty_slides": empty_slides,
            "file_size": len(file_bytes),
        },
    }
