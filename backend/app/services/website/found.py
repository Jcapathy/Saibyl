# PUBLIC INTERFACE
# ───────────────────────────────────────────────────────
# machine_dimension(capture) -> CriticDimension | None
# FOUND_KEY, FOUND_LABEL
# ───────────────────────────────────────────────────────
"""Whether the machines a buyer now asks can read this page at all.

**The half of the audience nothing else in the gauntlet judges.** Six reviewers
look at a screenshot and two count the CSS. All eight are reading the page a
*person* gets. The other reader is a crawler deciding whether this product can
be described, quoted or recommended when somebody asks a model what to use in
this category.

**Why it is a separate module from `machine.py`.** That one reads the evidence
and this one judges it — the same split as `capture.py`'s style census and
`measured.py`. It is also load-bearing for imports: `capture` calls the reader
at module scope, and `critics` imports `capture`, so a reader that imported the
finding models would close a cycle. Evidence has no opinions; opinions import
freely.

**The two goals genuinely pull against each other.** Measured 2026-08-30:
linear.app scores **100** on the visual standard and ships **zero** structured
data. vercel.com renders **866 characters** of text behind a rich visual page.
Neither is a bad site; both are half-legible to a machine. A page that scores
well here and badly on `standard` is a different problem from one that scores
well on `standard` and badly here, and the founder needs to be told which they
have.

**Ordering is the argument.** `robots.txt` comes first because it decides
whether any of the rest matters, and the words-in-the-HTML check comes second
for the same reason: a page nothing can fetch, or one whose text does not exist
until JavaScript runs, is not helped by better structured data. The `fix` lines
say so explicitly rather than presenting seven equal chores.

**No model call and no cost**, like `measured` and `standard`. Reproducible
across runs and free to re-run.

**A note on vocabulary.** Nothing here renders the word for the `rel` value it
reads, nor the acronyms for what it measures. A founder should not have to
learn either to read their own report: it is "the page's declared web address",
and the dimension is called "being found".
"""
from __future__ import annotations

import structlog

from app.services.website.critics import CriticDimension, CriticFinding

logger = structlog.get_logger()


# ── the dimension ────────────────────────────────────────────────────────────

#: What the founder sees this dimension called. Not "AEO" and not "SEO": a
#: founder should not have to learn an acronym to read their own report, and
#: the outcome they want is to be found and quoted, not to have optimised
#: something.
FOUND_KEY = "found"
FOUND_LABEL = "being found"

#: Same scale as `taste.py`, deliberately. Two counted dimensions using two
#: different arithmetics would make their scores look comparable when they are
#: not.
_WEIGHT = {"critical": 34, "major": 18, "minor": 7}


def _blocked_finding(blocked: list[str]) -> CriticFinding:
    return CriticFinding(
        severity="critical",
        region="crawler access",
        quote=f"robots.txt tells these to go away: {', '.join(blocked)}",
        why=(
            "These are the agents that fetch a page in order to answer a "
            "question about it. A model asked what to use in this category "
            "cannot name a page it is not allowed to read, however good the "
            "page is. This one decides whether any of the rest matters."
        ),
        fix=(
            "If the intent was to keep the writing out of training runs, that "
            "is a different set of agents. Allow the ones above and block the "
            "training crawlers instead."
        ),
    )


def _headline_finding() -> CriticFinding:
    return CriticFinding(
        severity="critical",
        region="what a crawler receives",
        quote="the page's own headline is not in the HTML the server sends",
        why=(
            "The headline arrives only after JavaScript runs, and the crawlers "
            "that answer questions do not run it. A person sees the page; a "
            "machine sees an empty shell, so the site cannot be described or "
            "quoted even though it is not blocked."
        ),
        fix=(
            "Serve the page's own words in the first response — server-render "
            "it, or prerender the pages you want found. Everything else on "
            "this list is worth less until the words are in the HTML."
        ),
    )


def _no_structured_data_finding() -> CriticFinding:
    return CriticFinding(
        severity="major",
        region="machine-readable summary",
        quote="no structured data on the page",
        why=(
            "Structured data is the part of a page that states plainly what "
            "kind of thing this is, what it costs and who makes it, in a form "
            "that needs no interpretation. Without it a machine has to infer "
            "all of that from prose, and it will sometimes infer wrongly."
        ),
        fix=(
            "Add a JSON-LD block naming the organisation and the product. If "
            "the page answers common questions, mark those up too — a question "
            "and its answer are the shape an assistant quotes most readily."
        ),
    )


def _no_description_finding() -> CriticFinding:
    return CriticFinding(
        severity="major",
        region="machine-readable summary",
        quote="the page has no description tag",
        why=(
            "This is the one sentence a search result, a link preview and an "
            "assistant all reach for first. With none, each writes its own "
            "from whatever text it found, and the page loses control of its "
            "own summary."
        ),
        fix="Write one sentence saying what this is and who it is for.",
    )


def _no_declared_address_finding() -> CriticFinding:
    return CriticFinding(
        severity="minor",
        region="machine-readable summary",
        quote="the page does not declare its own web address",
        why=(
            "Without it, the same page reached by two routes reads as two "
            "pages, and whatever standing it has is split between them."
        ),
        fix="Declare the one address this page should be known by.",
    )


def _alt_text_finding(without: int, total: int) -> CriticFinding:
    return CriticFinding(
        severity="major" if without > total / 2 else "minor",
        region="images",
        quote=f"{without} of {total} images carry no alt text",
        why=(
            "Alt text is what a machine reads instead of the picture, and what "
            "a screen reader says out loud. An image carrying the page's "
            "argument is, to both, silence."
        ),
        fix=(
            "Describe what the image shows, in the words the page would use. "
            "Images that are purely decorative take an empty alt rather than "
            "no alt, which is how you say 'skip this' rather than 'unknown'."
        ),
    )


def _no_llms_txt_finding() -> CriticFinding:
    return CriticFinding(
        severity="minor",
        region="machine-readable summary",
        quote="no /llms.txt is served",
        why=(
            "A plain-text file saying what this is and where the important "
            "pages are. **This is an emerging convention rather than a "
            "standard, and no crawler is documented as requiring it** — it is "
            "listed because it is cheap, it cannot hurt, and the pages a "
            "founder is compared against increasingly carry one."
        ),
        fix=(
            "Write a short file at /llms.txt: what the product is, who it is "
            "for, and links to the pages worth reading. Serve it as text."
        ),
    )


def machine_dimension(capture: object) -> CriticDimension | None:
    """How legible this page is to the machines its buyers now ask.

    `None` when the capture holds no machine signals at all — a pasted-HTML
    review, which never made a request and so has no server response, no
    address to resolve robots.txt against, and nothing honest to say. Scoring
    that 100 would credit a page for having been unmeasurable, which is the
    defect this codebase names most often, and a 0 would blame the founder for
    the shape of the input they were invited to give.
    """
    signals = getattr(capture, "machine", None)
    if not isinstance(signals, dict) or not signals:
        logger.info("machine_no_signals", detail="no machine signals; no dimension")
        return None

    findings: list[CriticFinding] = []
    strengths: list[str] = []

    blocked = signals.get("answering_crawlers_blocked") or []
    if blocked:
        findings.append(_blocked_finding(list(blocked)))
    else:
        strengths.append("The crawlers that answer questions are allowed to read the page.")

    headline = signals.get("headline_reaches_the_crawler")
    if headline is False:
        findings.append(_headline_finding())
    elif headline is True:
        strengths.append("The page's own words are in the HTML the server sends.")

    structured = signals.get("structured_data") or {}
    if not structured.get("blocks"):
        findings.append(_no_structured_data_finding())
    else:
        named = ", ".join(structured.get("types") or []) or "structured data"
        strengths.append(f"The page states what it is in a form a machine can read: {named}.")

    if signals.get("has_description") is False:
        findings.append(_no_description_finding())
    if signals.get("has_declared_address") is False:
        findings.append(_no_declared_address_finding())

    total = signals.get("images_in_raw_html") or 0
    without = signals.get("images_without_alt") or 0
    if total and without:
        findings.append(_alt_text_finding(without, total))
    elif total:
        strengths.append("Every image carries alt text.")

    if signals.get("has_llms_txt") is False:
        findings.append(_no_llms_txt_finding())
    elif signals.get("has_llms_txt") is True:
        strengths.append("A plain-text summary is served at /llms.txt.")

    score = 100
    for finding in findings:
        score -= _WEIGHT.get(finding.severity, 10)
    score = max(0, min(100, score))

    logger.info(
        "machine_dimension",
        score=score,
        failing=[f.region for f in findings],
        blocked=list(blocked),
    )
    return CriticDimension(
        key=FOUND_KEY, score=score, findings=findings, strengths=strengths[:4]
    )
