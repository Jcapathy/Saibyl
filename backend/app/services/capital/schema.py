# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# FirmPerson, InboundPath, FamilyOffice          — the stored record
# MatchReason, MatchDimension, ShortlistEntry, StaleRecord, Shortlist — the result
# FIRM_TYPES, INBOUND_KINDS, FIRM_INBOUND_LOCAL_PARTS
# reject_personal_data(field, value) -> str | None
# DEFAULT_FRESHNESS_DAYS, default_stale_after(retrieved_at), as_utc(dt)
# ─────────────────────────────────────────────────────────
"""The shapes the family-office bank stores and returns.

Modelled on `gtm/schema.Candidate`, whose rule already fits: there is no valid
state without `source_url`, because a lead a founder cannot trace back is a lead
they cannot act on. Two rules are added on top of it, and both are enforced by
the types below rather than by anybody remembering them.

**No personal contact detail, in any field, ever.** `privacy.py` opens by saying
the contact gate "is not a feature flag, it is the boundary between two legal
positions", and its `ALLOWED_CONTACT_FIELDS` is the whole list of what a stored
person may hold: full_name, role_title, employer, public_profile_url,
source_url, retrieved_at. `FirmPerson` below has exactly those six fields and is
validated by `privacy.rejects_as_personal_data` *itself* — not by a re-statement
of its rules. That gate rejects any key outside the allowed set, so adding a
seventh field to `FirmPerson` makes every construction of one fail. The schema
is enforced by the privacy rule rather than merely agreeing with it, which is
the difference between a boundary and a comment.

Free text gets the same treatment. A thesis is the field most likely to smuggle
a personal detail in by accident — it is copied from a firm's own page, and firm
pages have footers — so `thesis`, `firm_name`, `domain`, and every entry of
`sectors`, `stages`, `geography` and `notable_investments` are scanned by the
same function before the record exists.

**The one deliberate carve-out is `InboundPath`**, and it is narrow on purpose.
A firm's own published inbound route is firm contact information: a submission
form is a URL, and `submissions@firm.example` is a role address the firm
publishes precisely so strangers use it. An individual's address is not, and the
difference has to be mechanical rather than judged, because "is this address a
person's?" answered by hand is answered wrong the first busy afternoon. So a
stored address must be an exact email whose local part is one of a fixed list of
role words. Nobody is named `submissions`. That is the whole enforcement, and it
is why a personal address cannot enter this table through the one field that
accepts an address at all.

**Freshness is a field, not a nicety.** `retrieved_at` and `stale_after` are
both required. A record past `stale_after` is withheld or re-verified, never
returned as current — `Shortlist` refuses to hold one, so the rule cannot be
lost by a caller that forgets to filter.
"""
from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field, computed_field, model_validator

from app.services.gtm.privacy import ALLOWED_CONTACT_FIELDS, rejects_as_personal_data

# The key a free-text string is presented under when it is handed to
# `rejects_as_personal_data`. Any member of `ALLOWED_CONTACT_FIELDS` would do;
# `employer` is a free-text one, so a firm's thesis is scanned by exactly the
# pass that scans a contact's employer.
_SCAN_KEY = "employer"

# Not a decorative assertion. The gate rejects any key outside
# `ALLOWED_CONTACT_FIELDS`, so if `employer` ever left that tuple every string
# this module scans would come back "not public professional information" and
# every record in the bank would be refused — a whole module failing closed
# with a message that names the wrong cause. Fail at import instead, one line
# from the reason.
if _SCAN_KEY not in ALLOWED_CONTACT_FIELDS:
    raise RuntimeError(
        f"'{_SCAN_KEY}' is no longer in privacy.ALLOWED_CONTACT_FIELDS; pick "
        f"another free-text key from it for the personal-data scan"
    )


def reject_personal_data(field: str, value: str | None) -> str | None:
    """Reason this string may not be stored, or None.

    **The decision is `privacy.rejects_as_personal_data`'s, not a second copy of
    its patterns.** Re-implementing the email and phone regexes here is the
    defect this indirection prevents: two copies drift, and the copy that drifts
    is the one nobody re-reads. The gate keys on `ALLOWED_CONTACT_FIELDS`, so the
    string is presented under an allowed key and what actually runs is the same
    scan that guards every stored contact in the GTM module.

    Over-broad by design, inherited from that module: a false positive costs one
    dropped record, a false negative puts a personal email address in Saibyl's
    database.
    """
    if not value:
        return None
    if rejects_as_personal_data({_SCAN_KEY: value}) is None:
        return None
    return f"'{field}' contains personal contact detail"


def _reject_each(field: str, values: list[str]) -> str | None:
    for index, value in enumerate(values):
        verdict = reject_personal_data(f"{field}[{index}]", value)
        if verdict is not None:
            return verdict
    return None


def as_utc(value: datetime) -> datetime:
    """Attach UTC to a naive datetime.

    Records arrive from three places — a Pydantic parse of a PostgREST row, a
    test fixture, and `datetime.now(UTC)` — and only the last is reliably
    aware. Comparing an aware `stale_after` with a naive `now` raises
    `TypeError`, and the place it would raise is the freshness check, which is
    the one check in this module that must never be skipped by an exception
    somebody then catches.
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


# ---------------------------------------------------------------------------
# People — the permitted set, and nothing else
# ---------------------------------------------------------------------------

class FirmPerson(BaseModel):
    """A named person at a firm. Public professional information only.

    The field list is `privacy.ALLOWED_CONTACT_FIELDS`, and that is not a
    coincidence to be maintained by hand: the validator hands the whole record
    to `rejects_as_personal_data`, which rejects any key outside that tuple. Add
    an eighth field — `email`, `phone`, `mobile`, whatever the ticket calls it —
    and every `FirmPerson` in the codebase fails to construct. The schema cannot
    drift away from the privacy rule because the privacy rule is what validates
    it.

    `source_url` is required for the reason `gtm/schema.Contact` requires it: a
    subject-access or erasure request is answerable only if Saibyl can say where
    a personal record came from and when it was retrieved.
    """

    full_name: str
    role_title: str = ""
    employer: str = ""
    # A public professional profile page — a firm bio, a conference speaker
    # page, a piece they wrote. Never a personal contact channel.
    public_profile_url: str | None = None
    source_url: str
    retrieved_at: datetime

    @model_validator(mode="after")
    def _only_public_professional_information(self) -> FirmPerson:
        verdict = rejects_as_personal_data(self.model_dump())
        if verdict is not None:
            raise ValueError(verdict)
        if not self.source_url.strip():
            raise ValueError(
                "a person with no source_url cannot be traced back or erased, "
                "so there is no valid state of this record without one"
            )
        return self


# ---------------------------------------------------------------------------
# The firm's own published inbound route
# ---------------------------------------------------------------------------

INBOUND_KINDS: tuple[str, ...] = (
    "submission_form",
    "firm_address",
    "warm_intro_only",
    "no_inbound",
)

InboundKind = Literal["submission_form", "firm_address", "warm_intro_only", "no_inbound"]

# Local parts a stored firm address may have. **This list is the enforcement of
# "firm contact information, not an individual's".** A role address is published
# by the firm so that strangers use it; a person's address is published, when it
# is published at all, for people who already know them. Judging which is which
# by inspection fails the first busy afternoon, so the test is mechanical: the
# local part must be one of these words. Nobody is named `submissions`.
#
# Adding a word here is a privacy decision, not a schema decision — the same
# standing `privacy.py` gives `ALLOWED_CONTACT_FIELDS`. Any word that could also
# be a person's given name or initials does not belong on this list.
FIRM_INBOUND_LOCAL_PARTS: frozenset[str] = frozenset({
    "info",
    "contact",
    "contacts",
    "hello",
    "enquiries",
    "inquiries",
    "submissions",
    "submit",
    "pitch",
    "pitches",
    "dealflow",
    "deals",
    "investorrelations",
    "office",
    "admin",
    "general",
})

# A whole-string email. Anchored on both ends: a value that merely *contains* an
# address is prose with an address in it, which is not an inbound route and is
# exactly the shape a footer scrape produces.
_WHOLE_ADDRESS = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._+-]*)@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)$")

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _local_part_key(local: str) -> str:
    """`investor.relations` and `investor-relations` are the same role address."""
    return _NON_ALNUM.sub("", local.casefold())


class InboundPath(BaseModel):
    """How the firm itself says to approach it.

    Four kinds, and two of them are refusals stated honestly. Family offices are
    private by design and many take no inbound at all; where that is the firm's
    published position, that is what the record says. A refusal carries no
    `value`, because a route stored next to "they take no inbound" is a route
    somebody uses.

    `source_url` is where the firm published this, and it is required. An
    inbound route with no source is a route we invented.
    """

    kind: InboundKind
    value: str | None = None
    source_url: str

    @model_validator(mode="after")
    def _is_the_firms_own_route(self) -> InboundPath:
        if not self.source_url.strip():
            raise ValueError("an inbound route with no source_url is one we invented")

        if self.kind in ("warm_intro_only", "no_inbound"):
            if self.value:
                raise ValueError(
                    f"kind '{self.kind}' is the firm declining inbound; storing a "
                    f"route alongside it is how a route gets used anyway"
                )
            return self

        if not (self.value or "").strip():
            raise ValueError(f"kind '{self.kind}' requires the route itself")
        value = self.value.strip()

        if self.kind == "submission_form":
            if not value.lower().startswith(("http://", "https://")):
                raise ValueError("a submission form must be a URL")
            # A form URL carrying an address in a query string is not a form
            # URL; it is an address wearing one.
            verdict = reject_personal_data("inbound_path.value", value)
            if verdict is not None:
                raise ValueError(verdict)
            return self

        # kind == "firm_address". The one place an address may be stored, and
        # the narrowest gate in this file — see FIRM_INBOUND_LOCAL_PARTS.
        match = _WHOLE_ADDRESS.match(value)
        if match is None:
            raise ValueError(
                "a firm address must be exactly an address and nothing else"
            )
        if _local_part_key(match.group(1)) not in FIRM_INBOUND_LOCAL_PARTS:
            raise ValueError(
                f"'{value}' is not a firm role address. Only the published "
                f"inbound addresses in FIRM_INBOUND_LOCAL_PARTS may be stored; "
                f"an individual's address may not be stored at all"
            )
        return self

    @property
    def address_domain(self) -> str | None:
        """The domain of a stored firm address, for the record to check."""
        if self.kind != "firm_address" or not self.value:
            return None
        match = _WHOLE_ADDRESS.match(self.value.strip())
        return match.group(2).casefold() if match else None


# ---------------------------------------------------------------------------
# The record
# ---------------------------------------------------------------------------

FIRM_TYPES: tuple[str, ...] = ("single_family", "multi_family", "foundation")

FirmType = Literal["single_family", "multi_family", "foundation"]

# How long a record stands before it must be re-verified or withheld.
#
# **A declared prior, labelled as such** — there is no measurement behind it,
# because no record has yet been re-verified. What stops it being the invented
# number `scoring.py` warns about is that it gates nothing silently: a record
# past it is *withheld and named*, so a founder sees coverage shrink rather than
# reading a stale claim as a current one. Six months is the outer bound at which
# a published thesis is still worth asserting; family-office theses move slowly,
# but they do move, and the failure this bounds is a pitch sent to a real firm
# with Saibyl's name on the recommendation.
DEFAULT_FRESHNESS_DAYS = 180


def default_stale_after(retrieved_at: datetime) -> datetime:
    """When a record retrieved now should stop being asserted."""
    return as_utc(retrieved_at) + timedelta(days=DEFAULT_FRESHNESS_DAYS)


class FamilyOffice(BaseModel):
    """One firm in the bank, firm-level and evidenced.

    Every claim field is optional except the ones that make the record
    actionable — the same rule `gtm/schema.Candidate` installs. A firm that does
    not publish a cheque range carries `check_size_low=None`, not a plausible
    band: a founder who finds one invented range has no reason to believe any of
    the others, and this is a recommendation with our name on it.

    `source_url` and `retrieved_at` are required. `stale_after` is required too,
    because a record with no expiry is a record that never goes stale, which is
    how an investor list launders decay into confidence.
    """

    firm_name: str
    domain: str | None = None
    firm_type: FirmType

    # The firm's own published words, quoted rather than paraphrased. A
    # paraphrase cannot be compared against a founder's material and quoted back
    # to them, which is the entire mechanism of the match.
    thesis: str = ""
    sectors: list[str] = Field(default_factory=list)
    stages: list[str] = Field(default_factory=list)

    # Only when the firm publishes a range. None beats a guess.
    check_size_low: int | None = None
    check_size_high: int | None = None

    geography: list[str] = Field(default_factory=list)
    notable_investments: list[str] = Field(default_factory=list)

    inbound_path: InboundPath
    people: list[FirmPerson] = Field(default_factory=list)

    source_url: str
    source_title: str = ""
    retrieved_at: datetime
    verified_at: datetime | None = None
    stale_after: datetime

    @model_validator(mode="after")
    def _evidenced_fresh_and_free_of_personal_data(self) -> FamilyOffice:
        if not self.source_url.strip():
            raise ValueError(
                "a firm a founder cannot trace back to a published page is a "
                "recommendation they cannot check, so there is no valid state "
                "of this record without source_url"
            )

        # Every stored string, through the same gate that guards a contact. The
        # thesis is the field this exists for: it is copied off a firm's own
        # page, and firm pages have footers.
        for field, value in (
            ("firm_name", self.firm_name),
            ("domain", self.domain),
            ("thesis", self.thesis),
            ("source_title", self.source_title),
        ):
            verdict = reject_personal_data(field, value)
            if verdict is not None:
                raise ValueError(verdict)
        for field, values in (
            ("sectors", self.sectors),
            ("stages", self.stages),
            ("geography", self.geography),
            ("notable_investments", self.notable_investments),
        ):
            verdict = _reject_each(field, values)
            if verdict is not None:
                raise ValueError(verdict)

        if (
            self.check_size_low is not None
            and self.check_size_high is not None
            and self.check_size_low > self.check_size_high
        ):
            raise ValueError("check_size_low cannot exceed check_size_high")

        object.__setattr__(self, "retrieved_at", as_utc(self.retrieved_at))
        object.__setattr__(self, "stale_after", as_utc(self.stale_after))
        if self.verified_at is not None:
            object.__setattr__(self, "verified_at", as_utc(self.verified_at))

        if self.stale_after <= self.retrieved_at:
            raise ValueError("stale_after must be after retrieved_at")

        # A role address at a domain the firm does not own is not the firm's
        # published route — it is an address on a page that mentioned the firm.
        address_domain = self.inbound_path.address_domain
        if address_domain and self.domain:
            own = self.domain.casefold().removeprefix("www.")
            if not (address_domain == own or address_domain.endswith(f".{own}")):
                raise ValueError(
                    f"inbound address is at '{address_domain}', which is not "
                    f"the firm's domain '{own}'"
                )
        return self

    def is_stale(self, now: datetime | None = None) -> bool:
        """Whether this record is past the date it may be asserted."""
        moment = as_utc(now) if now is not None else datetime.now(UTC)
        return moment >= self.stale_after


# ---------------------------------------------------------------------------
# The result
# ---------------------------------------------------------------------------

MatchDimension = Literal[
    "sector", "stage", "check_size", "geography", "thesis", "objection_bridge"
]


class MatchReason(BaseModel):
    """Why this firm, in both sides' actual words.

    **Both quotes are required and both are verbatim.** A reason carrying only
    the firm's language is a claim about the founder; carrying only the
    founder's is a claim about the firm. Carrying both is a comparison the
    founder can check in ten seconds against two pages they can open — which is
    the same reference-anchored discipline the website check's critics use, and
    the reason this list is worth more than a list somebody bought.
    """

    dimension: MatchDimension
    firm_quote: str
    founder_quote: str
    explanation: str = ""

    @model_validator(mode="after")
    def _quotes_both_sides(self) -> MatchReason:
        if not self.firm_quote.strip():
            raise ValueError(f"{self.dimension}: no quote from the firm")
        if not self.founder_quote.strip():
            raise ValueError(f"{self.dimension}: no quote from the founder's material")
        # The second gate. Records are already validated at construction, so a
        # quote drawn from one cannot carry a personal detail — this keeps that
        # true if a construction path is ever relaxed, and costs one regex pass.
        for field, value in (
            ("firm_quote", self.firm_quote),
            ("founder_quote", self.founder_quote),
            ("explanation", self.explanation),
        ):
            verdict = reject_personal_data(field, value)
            if verdict is not None:
                raise ValueError(verdict)
        return self


class StaleRecord(BaseModel):
    """A firm we hold but will not assert.

    Named rather than silently dropped. A founder who is told "we hold a record
    for this firm and it is past its verification date" can decide to look it up
    themselves; a founder shown a shorter list learns nothing.
    """

    firm_name: str
    retrieved_at: datetime
    stale_after: datetime
    reason: str = "past its verification date and not re-verified"


Verdict = Literal["match", "refusal"]


class ShortlistEntry(BaseModel):
    """One firm's place in the answer: a match with reasons, or a refusal.

    A refusal is a result, not an omission. A founder at idea stage is better
    served by "these four state they do not invest pre-revenue" than by a list
    padded to the same length with firms that would have said so on the call.
    """

    firm: FamilyOffice
    verdict: Verdict
    reasons: list[MatchReason] = Field(default_factory=list)
    # Called out separately from `reasons` because it is the signal no list
    # vendor can produce, and a renderer should lead with it.
    objection_bridge: MatchReason | None = None
    # Required on a refusal, and it quotes the firm's own stated position.
    refusal_reason: str | None = None
    # "Warm intro only", "takes no inbound" — the firm's stated access position,
    # surfaced next to a match rather than buried in the record.
    access_note: str | None = None
    score: float = 0.0
    score_components: dict[str, float] = Field(default_factory=dict)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def retrieved_at(self) -> datetime:
        """Carried onto the entry so a client renders the age without digging.

        A founder seeing how old a claim is can weigh it. This is the field that
        makes that possible in one place, and it is computed rather than copied
        so it cannot disagree with the record it describes.
        """
        return self.firm.retrieved_at

    @computed_field  # type: ignore[prop-decorator]
    @property
    def stale_after(self) -> datetime:
        return self.firm.stale_after

    @model_validator(mode="after")
    def _states_its_case(self) -> ShortlistEntry:
        if self.verdict == "refusal":
            if not (self.refusal_reason or "").strip():
                raise ValueError(
                    "a refusal must say what the firm stated, or it is an "
                    "omission with a label on it"
                )
        elif not self.reasons:
            raise ValueError(
                f"{self.firm.firm_name} is offered as a match with no reason; "
                f"an unreasoned match is the padding this module exists to avoid"
            )
        return self


class Shortlist(BaseModel):
    """The answer to "who would fund this", with its refusals and its gaps.

    **The freshness rule lives in this type.** `_no_stale_record_is_current`
    refuses to construct a shortlist holding a record past its `stale_after`, so
    a caller that assembles entries some other way — a future ingestion path, a
    replay of a stored row — still cannot present a stale claim as a current
    one. Withheld is honest; stale is a wrong pitch sent to a real firm with our
    name on the recommendation.
    """

    product_name: str = ""
    sector: str = ""
    stage: str = ""
    check_size_needed: int | None = None

    # When this was built, and the instant every freshness decision was made
    # against. Stored so a re-read of the row can say what "current" meant.
    as_of: datetime

    matches: list[ShortlistEntry] = Field(default_factory=list)
    refusals: list[ShortlistEntry] = Field(default_factory=list)
    withheld_stale: list[StaleRecord] = Field(default_factory=list)

    # How many records the match was run over, before any of the above. The
    # denominator a founder needs to read the numerator.
    considered: int = 0
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _no_stale_record_is_current(self) -> Shortlist:
        object.__setattr__(self, "as_of", as_utc(self.as_of))
        for entry in (*self.matches, *self.refusals):
            if entry.firm.is_stale(self.as_of):
                raise ValueError(
                    f"{entry.firm.firm_name}'s record went stale on "
                    f"{entry.firm.stale_after.isoformat()} and may not be "
                    f"returned as current; withhold it or re-verify it"
                )
        return self
