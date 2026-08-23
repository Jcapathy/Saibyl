# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# unsupported_claims(page_text, html) -> list[UnsupportedClaim]
# claim_complaint(claims) -> str
# UnsupportedClaim
# ─────────────────────────────────────────────────────────
"""Claims the rewritten page makes that the founder's page never made.

A live fintech revision (Ledgerline, 2026-08-22) delivered a page asserting
**SOC 2 Type II**, **ISO 27001**, **PCI DSS Level 1**, authorisation by the
**Central Bank of Ireland**, AES-256 at rest, TLS 1.2 in transit, and a
seven-line fee table — none of which appeared anywhere in the captured source
page. The generator's prompt forbids exactly this, twice and in plain words
(`revise._FACT_RULES`, and the closing sentence of `verticals.brief_section`:
"A page that claims a certification it does not hold is worse than one that
omits it"). It was overridden anyway, because the same prompt hands the model
a category checklist — *"Who holds the funds and under what licence"*, *"SOC 2
with its date"* — and satisfying a checklist from priors is the path of least
resistance when the material is silent.

So the instruction is not the control. This module is. It is the same
extract/verify split the rest of the codebase uses (`gtm.extraction`,
`capital.discovery.verify_firms`): the model writes, and a **pure function**
with no model call decides whether what it wrote is evidenced. "Every claim
must appear in the source" stops being a hope in a prompt and becomes an
assertion in a test.

Why this cannot be left to the critic gauntlet: **the six reviewers judge a
screenshot of the render and never see the original page's facts.** Invention
is structurally invisible to them. On the run above they scored the fabricating
page *up* — 78 → 80 overall, with credibility holding at 82 while being handed
certifications the founder does not hold. A reviewer that cannot see the source
cannot catch a claim that is not in it, no matter how the prompt is worded.

Three families are checked, in descending order of what a false one costs:

- **certification** — a named standard, regulator, licence or audit regime.
  Claiming one you do not hold is not a copy problem; depending on the badge it
  is a deceptive-practices exposure, and for a medical or payments founder it
  is the single most dangerous sentence the page could carry.
- **figure** — a price, a fee, a percentage. The Ledgerline page invented an
  entire fee schedule.
- **scale** — "trusted by 4,000 teams". Social proof is the other thing a
  generator reaches for when a section feels thin.

Precision is the design constraint, because every finding either costs a
regeneration or lands in front of the founder as an accusation. Only shapes
that are *claims* are considered: a bare number, a year, a step in a numbered
list and anything inside `<script>`/`<style>` are all ignored, and a figure is
reported only when its normalised form is absent from the source outright.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel

from app.services.website.style_guide import visible_copy

#: Never send more than this many to the model or the founder. A page that
#: trips dozens has one systemic problem, not thirty individual ones, and an
#: unbounded list would push the retry prompt past its own ceiling.
MAX_CLAIMS = 25

#: How much of the surrounding sentence rides along as the quote.
_QUOTE_CHARS = 180


class UnsupportedClaim(BaseModel):
    """One claim on the new page with no basis in the old one."""

    kind: str  # "certification" | "figure" | "scale"
    text: str  # the claim as it appears on the new page
    quote: str  # the sentence it sits in, so the founder can find it


# ── the vocabulary: named standards, regulators, licences, audits ────
#
# Matched on both sides with the same pattern, so a page that genuinely says
# "SOC 2" keeps saying it. Spelled as regexes rather than literals because the
# same badge has several house spellings ("SOC2", "SOC 2 Type II", "ISO/IEC
# 27001") and a founder who wrote one of them must not be told they invented
# another.
#
# Every pattern is anchored with `\b` on the left. Without it the short badges
# match inside ordinary words — `ce[\s-]mark` fires on "acceptan(ce mark)ing"
# — and a false accusation costs more here than a missed badge: it burns a
# regeneration and then tells a founder they invented something they wrote.
# Three entries are deliberately narrower than their acronym for the same
# reason: "SEC" collides with "30 sec", "MDR" is Managed Detection and Response
# to every security founder alive, and "ASIC" is a chip. Each requires the
# spelled-out form, accepting a miss to avoid a false positive.
#
# **A badge must be spelled the founder's way as well as the rewrite's.** The
# same pattern decides both sides, so an entry that accepts only the compressed
# spelling a copy rewriter reaches for ("SEC-registered", "e-money
# institution", "FDA-cleared") and not the ordinary phrasing a founder writes
# ("registered with the SEC", "electronic money institution", "cleared by the
# FDA") reports the founder's own licence back to them as an invention. That is
# the false accusation this module's docstring calls its worst failure, and it
# was live in three entries below; the alternations exist for that reason and
# each new spelling has to be one a page could only mean as the badge.
_CERTIFICATIONS: tuple[tuple[str, str], ...] = (
    # Security and assurance
    ("SOC 1", r"\bsoc[\s-]?1\b"),
    ("SOC 2", r"\bsoc[\s-]?2\b"),
    ("SSAE 18", r"\bssae[\s-]?18\b"),
    ("ISO 27001", r"\biso(?:/iec)?[\s-]?27001\b"),
    ("ISO 9001", r"\biso[\s-]?9001\b"),
    ("ISO 13485", r"\biso[\s-]?13485\b"),
    ("PCI DSS", r"\bpci(?:[\s-]?dss)?\b"),
    ("FedRAMP", r"\bfedramp\b"),
    ("HITRUST", r"\bhitrust\b"),
    ("CSA STAR", r"\bcsa\s+star\b"),
    ("NIST 800-53", r"\bnist\s+800[\s-]?53\b"),
    ("Cyber Essentials", r"\bcyber\s+essentials\b"),
    ("TISAX", r"\btisax\b"),
    # Privacy
    ("HIPAA", r"\bhipaa\b"),
    ("GDPR", r"\bgdpr\b"),
    ("CCPA", r"\bccpa\b"),
    ("Data Privacy Framework", r"\b(?:eu[\s-]us\s+)?data\s+privacy\s+framework\b"),
    ("Privacy Shield", r"\bprivacy\s+shield\b"),
    ("COPPA", r"\bcoppa\b"),
    ("FERPA", r"\bferpa\b"),
    # Financial regulators and licences
    ("FCA", r"\bfca\b"),
    ("FinCEN", r"\bfincen\b"),
    ("money transmitter licence", r"\bmoney\s+transmitter\b"),
    ("money services business", r"\bmoney\s+services\s+business\b"),
    ("Central Bank of Ireland", r"\bcentral\s+bank\s+of\s+ireland\b"),
    ("BaFin", r"\bbafin\b"),
    ("Monetary Authority of Singapore", r"\bmonetary\s+authority\s+of\s+singapore\b"),
    ("MiCA", r"\bmica\b"),
    ("PSD2", r"\bpsd\s?2\b"),
    (
        "e-money licence",
        r"\b(?:e[\s-]?money|electronic\s+money)\s+(?:licen[cs]e|institution)\b"
        r"|\bemi\s+licen[cs]e\b",
    ),
    (
        "SEC registration",
        # Not a bare "sec registration": "30 sec registration" is a signup
        # flow, and the whole reason this entry avoids the bare acronym.
        r"\bsecurities\s+and\s+exchange\s+commission\b|\bsec[\s-]registered\b"
        r"|\bregistered\s+with\s+the\s+sec\b",
    ),
    ("FINRA", r"\bfinra\b"),
    ("SIPC", r"\bsipc\b"),
    ("FDIC", r"\bfdic\b"),
    ("NCUA", r"\bncua\b"),
    # Medical and clinical
    (
        "FDA clearance",
        r"\bfda[\s-]?(?:cleared|approved|clearance|approval)\b"
        r"|\b(?:cleared|approved)\s+by\s+the\s+fda\b",
    ),
    ("510(k)", r"\b510\s?\(\s?k\s?\)"),
    ("De Novo", r"\bde\s+novo\s+(?:clearance|classification)\b"),
    ("premarket approval", r"\bpremarket\s+approval\b"),
    ("CE mark", r"\bce[\s-]mark(?:ed|ing)?\b"),
    ("EU MDR", r"\bmedical\s+device\s+regulation\b|\beu\s+mdr\b"),
    ("CLIA", r"\bclia\b"),
    # Both word orders. The compressed form is the rewrite's voice; "accredited
    # by the College of American Pathologists" is how a lab actually writes it,
    # and matching only the first meant a founder who wrote it the second way
    # was told they had invented their own accreditation. The same asymmetry
    # was closed for SEC, FDA, e-money and AES; this entry was missed.
    ("CAP accreditation",
     r"\bcap[\s-]accredit|\baccredited\s+by\s+(?:the\s+)?cap\b"
     r"|\bcollege\s+of\s+american\s+pathologists\b"),
    # Cryptography and transport, which are checkable technical assertions
    ("AES-256", r"\baes[\s-]?256\b|\b256[\s-]bit\s+aes\b"),
    ("TLS", r"\btls\s?1\.\d\b"),
    # Accessibility conformance
    ("WCAG", r"\bwcag\b"),
    ("Section 508", r"\bsection\s+508\b"),
    # Intellectual property, which is a legal assertion of its own
    ("patented", r"\bpatented\b"),
    ("patent pending", r"\bpatent[\s-]pending\b"),
)

# ── figure and scale shapes ──────────────────────────────────────────

_MONEY = re.compile(r"[$£€]\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:k|m|bn?|million|billion))?\b", re.I)
_PERCENT = re.compile(r"\d[\d,]*(?:\.\d+)?\s?%")
_CENTS = re.compile(r"\d[\d,]*(?:\.\d+)?\s?¢")

#: Countable social proof. Deliberately requires the noun: "4,000" alone is a
#: number, "4,000 customers" is a claim about the business.
#: Widened after a live marketplace run found this family nearly inert on its
#: own category: of 17 nouns tested, 13 were missing, so "Trusted by 50,000
#: creators" would have gone unflagged on a creator marketplace — the exact
#: category the run was chosen to exercise. Social proof is counted in whatever
#: noun the category uses, so the list has to reach the categories the product
#: actually serves rather than the ones B2B software happens to use.
_SCALE_NOUNS = (
    "customers|companies|teams|businesses|users|developers|clinics|hospitals|"
    "practices|banks|merchants|institutions|organisations|organizations|"
    "startups|founders|patients|providers|firms|brands|stores|"
    "creators|sellers|buyers|designers|makers|artists|shops|storefronts|"
    "listings|subscribers|members|vendors|freelancers|agencies|engineers|"
    "students|learners|schools|districts|accounts|workspaces|"
    "repos|repositories|projects|sites|apps|installs|downloads|signups"
)

#: A unit of time between the number and the noun means the number is not
#: counting the noun: "in 30 days our customers see…" counts days, not
#: customers, and reporting it would be a false accusation.
_NOT_A_MODIFIER = r"days?|weeks?|months?|years?|hours?|minutes?|seconds?|times?|x"

#: Up to two describing words may sit between the count and the noun, because
#: "4,000 finance teams" and "4,000 teams" are the same claim and a founder who
#: wrote the first must not be told they invented the second. The count and the
#: noun are captured separately for exactly that reason — the describing words
#: are dropped from the key, so the two spellings compare equal.
_SCALE = re.compile(
    rf"(\d[\d,]*(?:\.\d+)?\s?(?:\+|k|m|million|billion)?)"
    rf"\s+(?:(?!(?:{_NOT_A_MODIFIER})\b)[a-z][a-z-]*\s+){{0,2}}"
    rf"({_SCALE_NOUNS})\b",
    re.I,
)

#: kind, pattern — evaluated against the source and the render identically.
_FAMILIES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("figure", _MONEY),
    ("figure", _PERCENT),
    ("figure", _CENTS),
    ("scale", _SCALE),
)

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def _normalise(text: str) -> str:
    """Lowercased, tag-free, whitespace-collapsed, with the spellings that
    differ only cosmetically folded together.

    `visible_copy` runs on both sides even though the source is usually already
    plain extracted text: it is a no-op on text without tags, and it is the
    only thing standing between this check and a caller that hands it raw HTML
    — in which case a `<style>` block full of percentages would count as
    evidence for any percentage the page cared to claim.
    """
    folded = visible_copy(text or "")
    folded = folded.lower()
    # "30 percent" and "30%" are the same claim; so are the two dashes and the
    # two apostrophes that word processors substitute.
    folded = re.sub(r"\s*per\s?cent(?:age)?\b", "%", folded)
    # And "30 cents" and "30¢". The unit word has to fold here rather than in
    # `_figure_key`, because until it does the source's spelling is not even a
    # figure: no family pattern matches "30 cents", so the source states no
    # figure at all and the page's "30¢" is reported as invented. Only after a
    # number, so "Ledgerline cents" is untouched.
    #
    # "100 cents on the dollar" is an idiom, not a price, and folding it made
    # the page's own restatement of it look like an invented figure. The
    # exclusion is narrow on purpose: the idiom always continues "on the
    # dollar", and nothing else about the fold changes.
    folded = re.sub(r"(\d)\s*cents?\b(?!\s+on\s+the\s+dollar)", r"\1¢", folded)
    folded = folded.replace("–", "-").replace("—", "-")
    folded = folded.replace("’", "'").replace("“", '"').replace("”", '"')
    return " ".join(folded.split())


#: What a magnitude word or letter multiplies the number by.
#:
#: Only the spellings the family patterns above can actually match, so the
#: table cannot claim to fold something that never reaches it.
_MAGNITUDES: dict[str, int] = {
    "k": 1_000,
    "m": 1_000_000,
    "million": 1_000_000,
    "b": 1_000_000_000,
    "bn": 1_000_000_000,
    "billion": 1_000_000_000,
}

#: A figure split into the parts that decide whether two of them are one claim:
#: the currency it is in, the number, the magnitude it carries, and the unit it
#: is measured in.
_FIGURE_PARTS = re.compile(
    r"^(?P<prefix>[$£€]?)(?P<number>\d+(?:\.\d+)?)"
    r"(?P<magnitude>million|billion|bn|k|m|b)?(?P<suffix>[%¢]?)$"
)


def _figure_key(token: str) -> str:
    """A figure reduced to what makes it the same figure.

    `$1,200`, `$ 1200` and `$1,200.00` are one claim; spacing and thousands
    separators are typography. The trailing zeros go too, so a source that
    writes `2.9%` covers a render that writes `2.90%`.

    **The magnitude word is arithmetic, not typography, so it is multiplied out
    rather than left in the key.** Compressing `$5 million` to `$5M` is the
    single most likely thing a copy rewriter does to a headline number, and
    keyed as strings the two do not match — the founder was then told in a paid
    artifact that they invented a figure they wrote themselves, and `_rounds_to`
    could not rescue it because `Decimal("5m")` raises. Folded to `$5000000`,
    both spellings are one claim in either direction, and the key stays a
    number `_rounds_to` can read.
    """
    key = token.lower().replace(",", "").replace(" ", "")
    parts = _FIGURE_PARTS.match(key)
    if parts:
        value = Decimal(parts["number"]) * _MAGNITUDES.get(parts["magnitude"] or "", 1)
        # `normalize` alone renders large values as `5E+6`; the plain format is
        # what makes `$5 million` and `$5,000,000` the same string.
        return f"{parts['prefix']}{format(value.normalize(), 'f')}{parts['suffix']}"
    key = re.sub(r"(\.\d*?)0+(?=\D|$)", r"\1", key)
    return key.rstrip(".")


def _rounds_to(stated: str, sourced: set[str]) -> bool:
    """Whether some source figure rounds to what the page wrote.

    A page that reads `1.70269159%` off its own source and writes `1.70%` has
    reported it, not invented it — but keyed on the string the two do not
    match, and the founder was shown "1.70%" as a claim their page could not
    support. That is the one failure mode this module must never have: an
    accusation aimed at somebody for quoting themselves accurately.

    Only figures are rounded. A certification either appears or does not.
    """
    text = stated.lstrip("$£€").rstrip("%¢").replace(",", "").strip()
    try:
        value = Decimal(text)
    except (InvalidOperation, ValueError):
        return False
    places = len(text.split(".", 1)[1]) if "." in text else 0
    prefix = stated[: len(stated) - len(stated.lstrip("$£€"))]
    suffix = stated[len(stated.rstrip("%¢")) :]

    for candidate in sourced:
        raw = candidate.lstrip("$£€").rstrip("%¢")
        try:
            other = Decimal(raw)
        except (InvalidOperation, ValueError):
            continue
        # Same unit, or the comparison is meaningless: "$2.9" does not
        # evidence "2.9%".
        if candidate[: len(prefix)] != prefix or not candidate.endswith(suffix):
            continue
        if round(other, places) == value:
            return True
    return False


def _key_of(kind: str, match: re.Match[str]) -> str:
    """What makes two mentions the same claim.

    A scale claim is its count and its noun, with any describing words between
    them discarded — "4,000 finance teams" and "4,000 teams" are one claim, and
    keying on the whole match would report the second as invented on a page
    whose source states the first.
    """
    if kind == "scale":
        return f"{_figure_key(match.group(1))} {match.group(2).lower()}"
    return _figure_key(match.group(0))


def _sentence_around(haystack: str, start: int, end: int) -> str:
    """The sentence containing a match, trimmed to something quotable.

    The quote is what makes a finding actionable: the founder has to be able to
    search the page for it. A bare "you invented '2.9%'" sends them hunting.
    """
    left = max(
        (haystack.rfind(mark, 0, start) for mark in (". ", "! ", "? ")),
        default=-1,
    )
    left = 0 if left == -1 else left + 2

    rights = [pos for pos in (haystack.find(mark, end) for mark in (". ", "! ", "? ")) if pos != -1]
    right = min(rights) + 1 if rights else min(len(haystack), end + _QUOTE_CHARS)

    quote = haystack[left:right].strip()
    if len(quote) <= _QUOTE_CHARS:
        return quote
    # Too long to quote whole: keep the claim itself in view rather than the
    # head of a sentence that may not mention it for another eighty characters.
    offset = max(0, (start - left) - 60)
    return "…" + quote[offset : offset + _QUOTE_CHARS].strip() + "…"


def unsupported_claims(page_text: str, html: str) -> list[UnsupportedClaim]:
    """Claims present on the rewritten page and absent from the source page.

    Pure: same inputs, same findings, no model call, no network. The whole
    point is that this is decidable — the generator's honesty is measured here
    rather than trusted upstream.

    Ordered certification-first, because that is the order in which a false one
    hurts, and capped at `MAX_CLAIMS`.
    """
    source = _normalise(page_text)
    rendered_raw = visible_copy(html or "")
    rendered = _normalise(rendered_raw)
    if not rendered:
        return []

    found: list[UnsupportedClaim] = []
    seen: set[tuple[str, str]] = set()

    def _add(kind: str, label: str, key: str, start: int, end: int) -> None:
        if (kind, key) in seen:
            return
        seen.add((kind, key))
        found.append(
            UnsupportedClaim(
                kind=kind, text=label, quote=_sentence_around(rendered, start, end)
            )
        )

    # Certifications: the same pattern decides both sides, so a badge the
    # founder already claims is never reported.
    for label, pattern in _CERTIFICATIONS:
        match = re.search(pattern, rendered, re.I)
        if match and not re.search(pattern, source, re.I):
            _add("certification", label, label.lower(), match.start(), match.end())

    # Figures and scale: compared as normalised keys, since the source states a
    # price once and the page may restate it in five places.
    source_keys = {
        _key_of(kind, m) for kind, regex in _FAMILIES for m in regex.finditer(source)
    }
    for kind, regex in _FAMILIES:
        for match in regex.finditer(rendered):
            key = _key_of(kind, match)
            if key in source_keys:
                continue
            # A rounded source figure is still the source figure.
            if kind == "figure" and _rounds_to(key, source_keys):
                continue
            _add(kind, match.group(0).strip(), key, match.start(), match.end())

    order = {"certification": 0, "figure": 1, "scale": 2}
    found.sort(key=lambda c: (order.get(c.kind, 9), c.text))
    return found[:MAX_CLAIMS]


# ── the complaint that rides on the retry ────────────────────────────

_KIND_NOUN = {
    "certification": "a certification, licence or regulator",
    "figure": "a price or percentage",
    "scale": "a customer count",
}

_COMPLAINT_HEAD = """\
STOP — your previous answer invented facts, which is the one thing this task
forbids. Each line below is {noun} that appears on the page you wrote and
appears NOWHERE in the page's real words above. You did not read these
anywhere; you supplied them because a section looked thin without them."""

_COMPLAINT_TAIL = """\
Rewrite the whole document. For every line above: delete the invented fact, and
where the section genuinely needs that fact, write the placeholder
[OWNER: fill in] in its place. A visible placeholder is the correct answer when
the material is silent — it is honest, and the founder can fill it in. An
invented certification is not a stylistic slip: the founder ships this page,
and a badge they do not hold is a claim regulators and customers act on.
Every other fact on the page must survive this edit unchanged."""


def claim_complaint(claims: list[UnsupportedClaim]) -> str:
    """The retry's complaint, naming every invented claim exactly.

    A retry that merely repeats the question gets the same wrong answer
    (CRITICS_LOG, 2026-08-16), and this failure is the strongest case for that
    rule in the codebase: the prompt already forbade invention in two separate
    sections and was overridden regardless. The complaint therefore quotes the
    model's own sentences back at it, so the instruction is about *this page*
    rather than about honesty in general.
    """
    kinds = {c.kind for c in claims}
    noun = (
        _KIND_NOUN[next(iter(kinds))]
        if len(kinds) == 1
        else "a fact — a certification, a price, or a customer count"
    )
    lines = [_COMPLAINT_HEAD.format(noun=noun), ""]
    for claim in claims:
        lines.append(f'- "{claim.text}" — you wrote: "{claim.quote}"')
    lines += ["", _COMPLAINT_TAIL]
    return "\n".join(lines)
