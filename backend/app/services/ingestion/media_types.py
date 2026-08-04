# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# MEDIA_TYPES                       -> tuple[str, ...]
# EXTENSIONS_BY_MEDIA_TYPE          -> dict[str, frozenset[str]]
# ALL_EXTENSIONS                    -> frozenset[str]
# extension_of(filename)            -> str
# media_type_for_extension(ext)     -> str | None   (None = miss, countable)
# max_upload_bytes(media_type)      -> int
# ─────────────────────────────────────────────────────────
"""What kind of thing an upload is, in exactly one place.

This table used to exist twice — `api/uploads.py` accepted
`{pdf, docx, txt, md, jpg, …}` keyed by a caller-supplied `media_type`, and
`api/documents.py` accepted a different set (`doc`, `json`, `html`) keyed by
nothing at all. Two extension allowlists for one product is the "two sources of
truth" class in DECISIONS/HANDOFF §2a, and it produced the concrete failure this
module exists to end: `.pptx` was accepted by both routes and understood by
neither, so a founder's deck uploaded as a deck extracted zero characters and
the ICP was synthesized as if it had never been sent.

`media_type_for_extension` returns `None` on an extension nobody has mapped
rather than defaulting to `document`. A default there is the governing defect
class: an unmapped `.key` file would be routed to the plain-text extractor,
produce mojibake, be stored as `complete`, and contribute noise to the ICP with
nothing anywhere saying the type was never recognised.
"""
from __future__ import annotations

MEDIA_TYPES: tuple[str, ...] = (
    "document",
    "presentation",
    "image",
    "video",
    "spreadsheet",
    "news_article",
)

# Extension -> the processor family that can actually read it.
#
# `html`/`htm` map to `news_article` rather than `document`: the article
# processor strips script/style furniture and pulls the body, where the plain
# text extractor would hand the synthesis pass a page of markup.
EXTENSIONS_BY_MEDIA_TYPE: dict[str, frozenset[str]] = {
    "document": frozenset({"pdf", "docx", "txt", "md", "json"}),
    "presentation": frozenset({"pptx"}),
    "image": frozenset({"jpg", "jpeg", "png", "gif", "webp"}),
    "video": frozenset({"mp4", "mov", "webm", "avi"}),
    "spreadsheet": frozenset({"xlsx", "xls", "csv"}),
    "news_article": frozenset({"html", "htm"}),
}

ALL_EXTENSIONS: frozenset[str] = frozenset(
    ext for exts in EXTENSIONS_BY_MEDIA_TYPE.values() for ext in exts
)

_MEDIA_TYPE_BY_EXTENSION: dict[str, str] = {
    ext: media_type
    for media_type, exts in EXTENSIONS_BY_MEDIA_TYPE.items()
    for ext in exts
}

# Per-kind ceilings. Carried over from `api/uploads.py`, which was the only
# route that enforced any ceiling at all — `/api/documents` accepted a file of
# any size and neither checked nor billed the org's storage quota.
_MAX_UPLOAD_BYTES: dict[str, int] = {
    "document": 50 * 1024 * 1024,
    "presentation": 50 * 1024 * 1024,
    "image": 25 * 1024 * 1024,
    "video": 500 * 1024 * 1024,
    "spreadsheet": 20 * 1024 * 1024,
    "news_article": 5 * 1024 * 1024,
}
_DEFAULT_MAX_UPLOAD_BYTES = 50 * 1024 * 1024


def extension_of(filename: str | None) -> str:
    """The lowercase extension of a filename, or `""` when it has none."""
    if not filename or "." not in filename:
        return ""
    return filename.rsplit(".", 1)[-1].strip().lower()


def media_type_for_extension(ext: str | None) -> str | None:
    """The media type that can read this extension, or `None` on a miss.

    `None` is deliberate and must be counted by the caller. See the module
    docstring: silently defaulting an unknown extension to `document` is how an
    unreadable file becomes a `complete` document contributing mojibake.
    """
    if not ext:
        return None
    return _MEDIA_TYPE_BY_EXTENSION.get(ext.strip().lower().lstrip("."))


def max_upload_bytes(media_type: str | None) -> int:
    return _MAX_UPLOAD_BYTES.get(media_type or "", _DEFAULT_MAX_UPLOAD_BYTES)
