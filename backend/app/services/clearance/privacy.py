# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# redact_personal_contact_detail(text) -> str
# scrub_clearance_artifact(artifact) -> dict
# scrub_clearance_report(markdown) -> str
# REDACTION_MARKER, SCANNED_FIELDS_BY_SECTION
# ─────────────────────────────────────────────────────────
"""What a clearance run may keep out of a USPTO record, and what it may not.

**Read this before changing anything in this file**, the same standing
`gtm/privacy.py` claims for the contact gate — and for the same reason. The
rule below is not a filter somebody added to be careful. It is a decision about
which half of a public register Saibyl is willing to become the custodian of,
and it is deliberately *not* the rule the rest of the codebase applies.

## Why this module is not `rejects_as_personal_data`

Everywhere else, a record carrying personal data is dropped whole.
`gtm/privacy.rejects_as_personal_data` says so plainly — "a record that needed
editing to be lawful is a record whose source was the wrong kind of page" — and
`capital/schema` enforces the same thing by types, so a `FirmPerson` with a
seventh field cannot be constructed at all.

That rule is right there and wrong here, because the premise underneath it does
not hold. In GTM and capital, Saibyl *chose* to go looking: nobody asked for
those people, discovery proposed them, and a record with an email address in it
is evidence the crawl landed somewhere it should not have. Dropping it costs
one lead.

A clearance finding is the opposite on both counts. The founder asked a
specific question — "has someone already patented this?" — and the answer is a
row of the United States patent register, published by statute (35 U.S.C.
§122(b)) and reachable by anyone at data.uspto.gov. Dropping it costs the
finding, and a clearance report that silently omits the one reference that
blocks you is worse than no report at all. Refusing at the boundary here would
not protect anybody; it would delete the product and hide the deletion.

So this module **redacts rather than rejects**, and the line it draws is
between two things that USPTO returns in the same JSON body:

*The name of record is the finding.* "US 11,222,333, filed 2021, Jane Doe" is
what a founder takes to counsel. Strip the name and they cannot tell a
competitor from a troll from their own former employer, cannot look the
reference up, and cannot brief anyone. It is also the category the law itself
separates out: information lawfully made available from government records is
excluded from "personal information" under CCPA (Cal. Civ. Code
§1798.140(v)(2)), and the register exists precisely so the public can read who
claims what. **Names of record stay, in every field, always.**

*A contact channel is never the finding.* USPTO file wrappers carry inventor
and attorney correspondence addresses, telephone numbers and email addresses,
and not one claim-overlap judgement in this codebase has any use for them.
Storing them would make Saibyl the keeper of a contact database it never
wanted, assembled from people who never signed up for anything — the exact
position `gtm/privacy.py` refuses to enter without an org opting in. Here there
is no opt-in to offer, because there is no product state in which we want them.
**Contact channels never enter storage, and never leave it.**

## Both boundaries, and why both

`scrub_clearance_artifact` runs in two places, and neither is redundant:

- **On the way in**, in `artifact.build_artifact`, before the worker writes the
  row. This is what makes an erasure request answerable with "we never held
  it", which is a different and much better answer than "we deleted it". It
  also covers `clearance_findings` and `report_markdown` for free, because both
  are derived from the artifact the builder returns.
- **On the way out**, in `GET /api/clearance/{run_id}`. Rows written before
  this module existed are still in the table — a live QUICK run produced a
  7,583-character report through that path — and a scan whose only copy is at
  write time cannot protect a row that some future ingestion path inserts.

The same function on both sides, so the two cannot drift. It is idempotent:
scrubbing already-scrubbed text changes nothing.

## The false-positive economics are inverted here, on purpose

`gtm/schema.contains_personal_contact_detail` is deliberately over-broad,
because there "a false positive costs one dropped contact". Here a false
positive silently rewrites a founder's prior-art finding, so the patterns below
are *narrower* than that module's — a phone number must be shaped like one, not
merely be a run of digits, because `filed 2021-03-01` is a run of digits and
this text is full of dates and reference numbers.

Two things keep that from being a quiet privacy hole. The email pattern, which
is the one that actually matters and the one USPTO actually returns, stays
broad: `@` does not appear in a date or a patent number, so there is no
accuracy to trade away. And every redaction leaves `REDACTION_MARKER` in place
of what it removed, so an over-redaction is visible to the reader and can be
reported, rather than being an unexplained gap.

`SCANNED_FIELDS_BY_SECTION` is the whole list of what gets scanned, and dates,
reference numbers, statuses and classification codes are deliberately absent
from it. Adding a field there is safe; leaving one out is the failure mode, so
the list is written per artifact section against the output contract in
`artifact.py` rather than inferred by walking the blob.
"""
from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

# What the reader sees in place of what was removed. Present tense and plain:
# a founder who sees this in a report should understand that the register said
# something here and that Saibyl chose not to keep it, not wonder whether the
# USPTO record was blank.
REDACTION_MARKER = "[contact detail removed]"

# An email address. Kept broad — the same shape as
# `gtm/schema._EMAIL` — because `@` cannot appear in a date, a patent number, a
# CPC code or an application serial, so breadth costs nothing here. This is
# also the pattern that earns the module: TSDR owner records and ODP
# correspondence data are where an address would actually arrive from.
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")

# A telephone number, and **narrower than the GTM detector on purpose** (see the
# module docstring). That one matches any 9+ digit run with punctuation in it,
# which is also an exact description of `2021-03-01` and of half the identifiers
# in a clearance report. This requires real phone structure: an optional country
# code, a three-digit group, a separator that is actually a separator, and the
# 3-4 split.
_PHONE = re.compile(
    r"(?:\+\d{1,3}[\s.-]?)?"      # optional country code
    r"(?:\(\d{3}\)\s?|\d{3})"     # area code, parenthesised or bare
    r"[\s.-]"                     # a real separator — never optional, or dates match
    r"\d{3}"
    r"[\s.-]"
    r"\d{4}"
    r"(?!\d)"
)

# A number introduced by the word for what it is. Catches the formats the
# structured pattern above deliberately will not — `Fax: 5551234567` — without
# letting a bare digit run anywhere near the matcher.
_LABELLED_NUMBER = re.compile(
    r"\b(?:tel|telephone|phone|fax|mobile|cell)\b[.:\s]*\+?[\d\s().-]{7,}\d",
    re.IGNORECASE,
)

# A street address. USPTO correspondence blocks are the source: a house number,
# a street name, and a thoroughfare word.
#
# **At least one word must sit between the number and the thoroughfare**, and
# that requirement is the whole safety of this pattern. Half the standard postal
# abbreviations are also units of measure, and this product searches every
# discipline — `12 fl oz` in a beverage formulation, `1 ct` in a gemstone claim,
# `2 ln` in a mathematical one. Requiring a street name in between means none of
# those can match, because there is nothing to be the street name. `100 Main St`
# has one; `12 fl` never will.
_STREET = re.compile(
    r"\b\d{1,6}\s+(?:[A-Za-z][A-Za-z0-9.'-]*\s+){1,4}"
    r"(?:street|st|avenue|ave|road|rd|boulevard|blvd|drive|dr|lane|ln|way|"
    r"court|ct|place|pl|parkway|pkwy|circle|cir|terrace|ter|highway|hwy|"
    r"square|plaza|suite|ste)\b\.?",
    re.IGNORECASE,
)

# The unit half of an address, where the number follows the word rather than
# leading it — `Suite 400` — so `_STREET` cannot reach it. Only the three words
# that are never units of measure or claim vocabulary.
_UNIT = re.compile(r"\b(?:suite|ste|apartment|apt)\.?\s*#?\s*\d{1,6}\b", re.IGNORECASE)

# The tail of a US postal address — state abbreviation plus ZIP — which is what
# a correspondence block collapses to once the street line is gone. The
# `(?!\d)` matters: without it, `US 11123456` reads as a two-letter state and a
# five-digit ZIP, and every patent number cited with a country prefix would be
# redacted.
_STATE_ZIP = re.compile(r"\b[A-Z]{2}\.?\s+\d{5}(?:-\d{4})?(?!\d)")

# A PO box, which has no street number to anchor on.
_PO_BOX = re.compile(r"\bP\.?\s?O\.?\s*Box\s+\d+", re.IGNORECASE)

_PATTERNS = (
    _EMAIL, _LABELLED_NUMBER, _PHONE, _PO_BOX, _STREET, _UNIT, _STATE_ZIP
)


def redact_personal_contact_detail(text: str) -> str:
    """Replace every contact channel in `text` with `REDACTION_MARKER`.

    Names, titles, employers, patent numbers, dates and classification codes
    pass through untouched — they are the finding. See the module docstring for
    why that asymmetry is the point rather than an oversight.

    Idempotent: `REDACTION_MARKER` contains no email, phone or address, so a
    second pass over redacted text is a no-op.
    """
    if not text:
        return text
    for pattern in _PATTERNS:
        text = pattern.sub(REDACTION_MARKER, text)
    return text


def scrub_clearance_report(markdown: str) -> str:
    """The same pass over a composed report.

    The report is written from an already-scrubbed artifact, so this changes
    nothing on the write path. It exists for the rows composed before this
    module did, which are served from storage rather than rebuilt.
    """
    return redact_personal_contact_detail(markdown or "")


# ---------------------------------------------------------------------------
# What gets scanned
# ---------------------------------------------------------------------------
#
# Keyed by the artifact's own section names, and listing only free text and
# register-sourced names. Everything absent from this map is absent
# deliberately:
#
#   `filed`, `priority`, `search_date`, `blind_spot_note`   dates
#   `number`, `app`, `serial_or_reg`, `provisional`, `via`  identifiers
#   `status`, `risk`, `live`, `classes`, `hits`             enumerations
#   `limitations`, `disclaimer`, `official_search_link`     our own constants
#
# Running an address or phone matcher over a date field is how a redactor
# corrupts the record it was added to protect.
#
# `item` is also absent, and that one is a judgement rather than a type
# argument: it is the founder's own submitted text, stored verbatim in
# `clearance_runs.item` as well. Rewriting a caller's own words in the copy we
# show back to them — while keeping the original in the column next to it —
# would be theatre, not protection. If a founder puts their own address in the
# thing they are clearing, that is their data in their workspace.
SCANNED_FIELDS_BY_SECTION: dict[str, tuple[str, ...]] = {
    "trademark_conflict": ("mark", "owner", "goods_services"),
    "closest_art": ("title", "assignee", "claim_requirements", "differences"),
    "notable_pending": ("title", "assignee"),
    "watch_list": ("target", "reason"),
    "queries_run": ("query",),
}


def _scrub_entries(entries: Any, fields: tuple[str, ...]) -> Any:
    """Scrub the named string fields of every dict in a list, in place."""
    if not isinstance(entries, list):
        return entries
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        for field in fields:
            value = entry.get(field)
            if isinstance(value, str):
                entry[field] = redact_personal_contact_detail(value)
    return entries


def _scrub_strings(values: Any) -> Any:
    """Scrub a list of bare strings, in place."""
    if not isinstance(values, list):
        return values
    for index, value in enumerate(values):
        if isinstance(value, str):
            values[index] = redact_personal_contact_detail(value)
    return values


def scrub_clearance_artifact(artifact: dict) -> dict:
    """A copy of `artifact` with every contact channel replaced.

    Pure over its input — the caller's dict is not mutated — because
    `build_artifact` promises purity and because the serving path scrubs a row
    it did not build.

    Tolerant of a missing or oddly-shaped section rather than raising. This runs
    on rows written by earlier versions of the artifact builder, and a
    KeyError here would turn a privacy pass into a 500 on a completed run the
    founder has already paid for.
    """
    if not isinstance(artifact, dict):
        return artifact

    scrubbed = deepcopy(artifact)

    _scrub_strings(scrubbed.get("assumptions"))

    trademark = scrubbed.get("trademark")
    if isinstance(trademark, dict):
        _scrub_strings(trademark.get("marks_checked"))
        _scrub_entries(
            trademark.get("conflicts"),
            SCANNED_FIELDS_BY_SECTION["trademark_conflict"],
        )

    patents = scrubbed.get("patents")
    if isinstance(patents, dict):
        _scrub_entries(
            patents.get("closest_art"), SCANNED_FIELDS_BY_SECTION["closest_art"]
        )
        _scrub_strings(patents.get("whitespace_signals"))
        _scrub_strings(patents.get("crowded_areas"))

    pending = scrubbed.get("pending_landscape")
    if isinstance(pending, dict):
        _scrub_entries(
            pending.get("notable_pending"),
            SCANNED_FIELDS_BY_SECTION["notable_pending"],
        )

    _scrub_entries(
        scrubbed.get("queries_run"), SCANNED_FIELDS_BY_SECTION["queries_run"]
    )
    _scrub_entries(
        scrubbed.get("watch_list"), SCANNED_FIELDS_BY_SECTION["watch_list"]
    )

    return scrubbed
