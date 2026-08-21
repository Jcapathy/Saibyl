"""The family-office bank is a recommendation, or it is not offered.

The contract under test:

- **No personal contact detail enters this module, from any direction.** A
  person record may hold only `privacy.ALLOWED_CONTACT_FIELDS`; an email or a
  phone number in a firm's thesis, in a person's role title, or in the
  founder's own supplied material is refused whole rather than trimmed. The
  one address the bank may store is a firm's own published role address, and
  the gate for that is a fixed allowlist of local parts rather than a judgment
  call.
- A record without `source_url` is invalid, the rule `gtm/schema.Candidate`
  already states: a lead a founder cannot trace back is a lead they cannot act
  on.
- A record past `stale_after` is withheld and named, never returned as
  current. The result type itself refuses to hold one.
- A firm that states it does not invest at this stage is reported as a refusal
  quoting its own published position — not dropped, and not replaced with a
  firm that would have said the same thing on the call.
- Every match states its reason quoting both sides' actual language, and the
  objection bridge quotes the buyer's sentence next to the firm's thesis.
- The price sits at the target margin, like every other paid artifact.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api import capital as capital_api
from app.services.capital import matching as m
from app.services.capital.schema import (
    FamilyOffice,
    FirmPerson,
    InboundPath,
    MatchReason,
    Shortlist,
    ShortlistEntry,
)
from app.services.gtm.privacy import ALLOWED_CONTACT_FIELDS

NOW = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)

ORG = "11111111-1111-1111-1111-111111111111"
PROJECT = "22222222-2222-2222-2222-222222222222"
SIM = "33333333-3333-3333-3333-333333333333"
ICP = "44444444-4444-4444-4444-444444444444"

# Both sides of the comparison, written so they genuinely share language —
# which is the only condition under which this module has anything to quote.
FOUNDER_MATERIAL = (
    "We sell compliance automation to regulated lenders. "
    "Our buyers are credit unions that ship software slowly."
)
VERRILL_THESIS = (
    "We back founders building for regulated financial markets, where "
    "compliance is the moat. We have written cheques into lending "
    "infrastructure since 2011."
)
BUYER_QUOTE = (
    "Nobody in regulated financial markets can adopt this without a "
    "compliance sign-off."
)


def _firm(
    name: str,
    *,
    thesis: str = VERRILL_THESIS,
    sectors: list[str] | None = None,
    stages: list[str] | None = None,
    domain: str = "verrill.example",
    inbound: InboundPath | None = None,
    retrieved_at: datetime | None = None,
    stale_after: datetime | None = None,
    **over: object,
) -> FamilyOffice:
    retrieved = retrieved_at or (NOW - timedelta(days=10))
    payload: dict[str, object] = {
        "firm_name": name,
        "domain": domain,
        "firm_type": "single_family",
        "thesis": thesis,
        "sectors": sectors if sectors is not None else ["Compliance automation"],
        "stages": stages if stages is not None else ["Pre-seed", "Seed"],
        "check_size_low": 250_000,
        "check_size_high": 2_000_000,
        "geography": ["United States"],
        "notable_investments": ["Ledgerway (2021)"],
        "inbound_path": inbound or InboundPath(
            kind="firm_address",
            value="submissions@verrill.example",
            source_url=f"https://{domain}/contact",
        ),
        "source_url": f"https://{domain}/approach",
        "retrieved_at": retrieved,
        "stale_after": stale_after or (retrieved + timedelta(days=180)),
    }
    payload.update(over)
    return FamilyOffice(**payload)  # type: ignore[arg-type]


def _context(**over: object) -> m.FounderContext:
    payload: dict[str, object] = {
        "product_name": "Ledgerguard",
        "sector": "Compliance automation",
        "stage": "pre-seed",
        "material": FOUNDER_MATERIAL,
        "check_size_needed": 500_000,
        "geography": "United States",
        "objections": [m.MeasuredObjection(
            objection_key="regulated-markets-move-slowly",
            label="Regulated markets move slowly",
            quote=BUYER_QUOTE,
            load_bearing_score=9.4,
        )],
    }
    payload.update(over)
    return m.FounderContext(**payload)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# The rule this module exists to keep
# ---------------------------------------------------------------------------

def test_a_person_may_hold_only_the_fields_privacy_permits():
    """The schema is enforced by the privacy rule, not merely agreeing with it.

    `rejects_as_personal_data` refuses any key outside `ALLOWED_CONTACT_FIELDS`,
    and it is what validates every `FirmPerson`. So this assertion is not
    decoration: the day somebody adds `email` to the model, every construction
    of one fails and this test says why.
    """
    assert set(FirmPerson.model_fields) == set(ALLOWED_CONTACT_FIELDS)


@pytest.mark.parametrize("field, value", [
    ("full_name", "Ana Ruiz ana.ruiz@verrill.example"),
    ("role_title", "Principal, +1 (212) 555-0147"),
    ("employer", "Verrill — reach us on 212-555-0147"),
    ("public_profile_url", "mailto:ana.ruiz@verrill.example"),
])
def test_a_personal_email_or_phone_on_a_person_is_rejected(field, value):
    """Dropped whole rather than trimmed.

    `privacy.py`'s reason, unchanged: a record that needed editing to be lawful
    is a record whose source was the wrong kind of page.
    """
    payload = {
        "full_name": "Ana Ruiz",
        "source_url": "https://verrill.example/team",
        "retrieved_at": NOW,
        field: value,
    }
    with pytest.raises(ValueError, match="personal contact detail"):
        FirmPerson(**payload)


@pytest.mark.parametrize("field, value", [
    ("thesis", "We back regulated fintech. Pitch us at ana.ruiz@verrill.example."),
    ("firm_name", "Verrill Family Office (+1 212 555 0147)"),
    ("notable_investments", ["Ledgerway — intro via ana.ruiz@verrill.example"]),
    ("geography", ["United States, call 212-555-0147"]),
])
def test_a_personal_detail_in_a_firms_free_text_is_rejected(field, value):
    """The thesis is the field this exists for.

    A thesis is copied off a firm's own page, and firm pages have footers. The
    same scan that guards a stored contact runs over it, so a personal address
    cannot enter the table inside a prose blob nobody thought of as contact
    data.
    """
    with pytest.raises(ValueError, match="personal contact detail"):
        _firm("Verrill Family Office", **{field: value})


def test_a_personal_detail_in_the_founders_own_material_is_rejected():
    """Not an over-reach onto the founder's data — a storage decision.

    Sentences from `material` are copied into the stored shortlist as quotes,
    so an address in a pasted deck footer becomes an address in Saibyl's
    database by way of a field nobody classified as contact data.
    """
    with pytest.raises(ValueError, match="personal contact detail"):
        _context(material="We sell compliance automation. Reach me on 212-555-0147.")


def test_a_firms_published_role_address_is_allowed():
    """Firm contact information is not personal data, and it is the whole
    reason a recommendation is actionable: the founder makes contact through
    the firm's own stated route."""
    firm = _firm("Verrill Family Office")
    assert firm.inbound_path.kind == "firm_address"
    assert firm.inbound_path.value == "submissions@verrill.example"


@pytest.mark.parametrize("address", [
    "ana.ruiz@verrill.example",
    "aruiz@verrill.example",
    "ana@verrill.example",
])
def test_an_individuals_address_is_not_allowed_even_as_an_inbound_route(address):
    """The one field that accepts an address is gated by an allowlist, not by
    judgment. "Is this address a person's?" answered by inspection is answered
    wrong the first busy afternoon; nobody is named `submissions`."""
    with pytest.raises(ValueError, match="not a firm role address"):
        InboundPath(
            kind="firm_address",
            value=address,
            source_url="https://verrill.example/contact",
        )


def test_a_stated_refusal_carries_no_route():
    """A route stored next to "they take no inbound" is a route somebody uses."""
    with pytest.raises(ValueError, match="declining inbound"):
        InboundPath(
            kind="no_inbound",
            value="submissions@verrill.example",
            source_url="https://verrill.example/contact",
        )


def test_an_inbound_address_must_be_at_the_firms_own_domain():
    """A role address on a page that merely mentions the firm is not the firm's
    published route."""
    with pytest.raises(ValueError, match="not the firm's domain"):
        _firm(
            "Verrill Family Office",
            inbound=InboundPath(
                kind="firm_address",
                value="submissions@some-directory.example",
                source_url="https://some-directory.example/verrill",
            ),
        )


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------

def test_a_firm_without_source_url_is_invalid():
    """`gtm/schema.Candidate`'s rule, unchanged: a recommendation a founder
    cannot trace back to a published page is one they cannot check."""
    with pytest.raises(ValueError, match="source_url"):
        _firm("Verrill Family Office", source_url="   ")


def test_a_person_without_source_url_is_invalid():
    """Provenance is what makes an erasure request answerable per person."""
    with pytest.raises(ValueError, match="source_url"):
        FirmPerson(full_name="Ana Ruiz", source_url="", retrieved_at=NOW)


def test_stale_after_must_be_after_retrieved_at():
    with pytest.raises(ValueError, match="stale_after"):
        _firm(
            "Verrill Family Office",
            retrieved_at=NOW - timedelta(days=10),
            stale_after=NOW - timedelta(days=20),
        )


# ---------------------------------------------------------------------------
# Freshness
# ---------------------------------------------------------------------------

def test_a_stale_record_is_withheld_and_named_rather_than_ranked():
    """Withheld is honest; stale is a wrong pitch sent to a real firm with our
    name on the recommendation. Named, because a founder told "we hold a record
    and it is past its verification date" can go and check it, where a founder
    handed a shorter list reads the shorter list as the whole market."""
    fresh = _firm("Verrill Family Office")
    stale = _firm(
        "Decayed Capital",
        retrieved_at=NOW - timedelta(days=400),
        stale_after=NOW - timedelta(days=20),
    )

    shortlist = m.build_shortlist(_context(), [fresh, stale], now=NOW)

    named = [w.firm_name for w in shortlist.withheld_stale]
    assert named == ["Decayed Capital"]
    assert shortlist.withheld_stale[0].stale_after == stale.stale_after
    shown = [e.firm.firm_name for e in (*shortlist.matches, *shortlist.refusals)]
    assert "Decayed Capital" not in shown
    assert shortlist.considered == 2


def test_the_result_type_refuses_to_hold_a_stale_record():
    """The rule is encoded, not documented.

    `partition_by_freshness` is the reader that enforces it, and this is the
    second line: a future ingestion path, or a replay of a stored row, that
    assembles entries some other way still cannot present a decayed claim as a
    current one — it fails loudly instead.
    """
    stale = _firm(
        "Decayed Capital",
        retrieved_at=NOW - timedelta(days=400),
        stale_after=NOW - timedelta(days=20),
    )
    entry = ShortlistEntry(
        firm=stale,
        verdict="match",
        reasons=[MatchReason(
            dimension="sector",
            firm_quote="Compliance automation",
            founder_quote="Compliance automation",
        )],
    )

    with pytest.raises(ValueError, match="may not be returned as current"):
        Shortlist(as_of=NOW, matches=[entry])


def test_every_returned_record_carries_the_date_it_was_retrieved():
    """A founder who sees how old a claim is can weigh it. Hiding the date is
    how a list launders decay into confidence."""
    shortlist = m.build_shortlist(_context(), [_firm("Verrill Family Office")], now=NOW)

    entry = shortlist.matches[0]
    assert entry.retrieved_at == entry.firm.retrieved_at
    assert "retrieved_at" in entry.model_dump()


# ---------------------------------------------------------------------------
# Refusals count
# ---------------------------------------------------------------------------

def test_a_firm_that_does_not_invest_at_this_stage_is_a_refusal_not_a_drop():
    """The padded-list failure, refused.

    A founder at pre-seed is better served by "this firm publishes Series A and
    Series B" than by a list quietly shortened and then padded back to length
    with firms that would have said the same thing on the call.
    """
    later_stage = _firm("Meridian Growth", stages=["Series A", "Series B"])

    shortlist = m.build_shortlist(_context(), [later_stage], now=NOW)

    assert [e.firm.firm_name for e in shortlist.matches] == []
    assert [e.firm.firm_name for e in shortlist.refusals] == ["Meridian Growth"]
    refusal = shortlist.refusals[0]
    assert "Series A" in refusal.refusal_reason
    assert "pre-seed" in refusal.refusal_reason


def test_a_refusal_keeps_the_reasons_it_did_find():
    """"Right thesis, wrong stage" is the most useful thing this module can say,
    and it is only sayable because a refusal keeps its reasons."""
    later_stage = _firm("Meridian Growth", stages=["Series A"])

    shortlist = m.build_shortlist(_context(), [later_stage], now=NOW)

    dimensions = {r.dimension for r in shortlist.refusals[0].reasons}
    assert "thesis" in dimensions
    assert shortlist.refusals[0].objection_bridge is not None


def test_a_firm_whose_published_cheque_range_rules_the_founder_out_is_a_refusal():
    big = _firm("Meridian Growth", check_size_low=20_000_000, check_size_high=50_000_000)

    shortlist = m.build_shortlist(_context(), [big], now=NOW)

    assert [e.firm.firm_name for e in shortlist.refusals] == ["Meridian Growth"]
    assert "$20,000,000" in shortlist.refusals[0].refusal_reason


def test_a_firm_that_publishes_no_stages_is_not_treated_as_a_refusal():
    """Silence is not a published position. Recording it as one would be as
    dishonest as recording it as agreement."""
    quiet = _firm("Quiet Capital", stages=[])

    shortlist = m.build_shortlist(_context(), [quiet], now=NOW)

    assert [e.firm.firm_name for e in shortlist.matches] == ["Quiet Capital"]
    assert {r.dimension for r in shortlist.matches[0].reasons}.isdisjoint({"stage"})


def test_an_empty_result_is_stated_rather_than_padded():
    unrelated = _firm(
        "Timberline Holdings",
        thesis="We buy midwestern industrial real estate and hold it forever.",
        sectors=["Industrial real estate"],
        stages=[],
        check_size_low=None,
        check_size_high=None,
        geography=["Midwest"],
    )

    shortlist = m.build_shortlist(
        _context(geography=None), [unrelated], now=NOW
    )

    assert shortlist.matches == []
    assert any("padded list" in note for note in shortlist.notes)


# ---------------------------------------------------------------------------
# The match is the product
# ---------------------------------------------------------------------------

def test_every_match_reason_quotes_both_sides_verbatim():
    """A reason with one side's language is an assertion. With both it is a
    comparison the founder can check in ten seconds against two pages."""
    firm = _firm("Verrill Family Office")

    shortlist = m.build_shortlist(_context(), [firm], now=NOW)

    entry = shortlist.matches[0]
    assert entry.reasons
    for reason in entry.reasons:
        assert reason.firm_quote.strip()
        assert reason.founder_quote.strip()

    thesis = next(r for r in entry.reasons if r.dimension == "thesis")
    assert thesis.firm_quote in firm.thesis
    assert thesis.founder_quote in FOUNDER_MATERIAL


def test_a_reason_missing_one_side_cannot_be_constructed():
    """Enforced by the type, so no code path can emit a half-reason."""
    with pytest.raises(ValueError, match="no quote from the founder's material"):
        MatchReason(dimension="thesis", firm_quote="We back regulated markets.",
                    founder_quote="   ")


def test_the_objection_bridge_puts_the_buyers_words_next_to_the_thesis():
    """The signal no list vendor has.

    The founder's measured evidence meeting the firm's published position: the
    buyer sentence and the thesis sentence, both verbatim, side by side.
    """
    firm = _firm("Verrill Family Office")

    shortlist = m.build_shortlist(_context(), [firm], now=NOW)

    bridge = shortlist.matches[0].objection_bridge
    assert bridge is not None
    assert bridge.dimension == "objection_bridge"
    assert bridge.firm_quote in firm.thesis
    assert bridge.founder_quote in BUYER_QUOTE
    assert "Regulated markets move slowly" in bridge.explanation
    # And it leads the reasons, because a renderer reads them in order.
    assert shortlist.matches[0].reasons[0] is bridge


def test_the_bridge_takes_the_most_load_bearing_objection_that_bridges():
    """The loudest objection and the one that kills the deal are usually
    different objections, and the ranking is the product."""
    firm = _firm("Verrill Family Office")
    context = _context(objections=[
        m.MeasuredObjection(
            objection_key="loud",
            label="Pricing",
            quote="Nobody in regulated financial markets pays this much for compliance.",
            load_bearing_score=1.0,
        ),
        m.MeasuredObjection(
            objection_key="kills-deals",
            label="Regulated markets move slowly",
            quote=BUYER_QUOTE,
            load_bearing_score=9.4,
        ),
    ])

    shortlist = m.build_shortlist(context, [firm], now=NOW)

    assert "Regulated markets move slowly" in shortlist.matches[0].objection_bridge.explanation


def test_a_firm_with_a_bridge_outranks_one_without():
    """The objection bridge is weighted highest because it is the only
    dimension a list vendor cannot compute."""
    bridged = _firm("Verrill Family Office")
    generic = _firm(
        "Generic AI Capital",
        domain="generic.example",
        thesis="We invest in software companies with strong founding teams.",
        inbound=InboundPath(
            kind="submission_form",
            value="https://generic.example/apply",
            source_url="https://generic.example/apply",
        ),
    )

    shortlist = m.build_shortlist(_context(), [generic, bridged], now=NOW)

    assert [e.firm.firm_name for e in shortlist.matches] == [
        "Verrill Family Office", "Generic AI Capital",
    ]
    assert shortlist.matches[0].score > shortlist.matches[1].score


def test_a_firms_stated_access_position_is_carried_onto_the_match():
    """Family offices are private by design and many take no inbound at all.
    Where that is the firm's stated position, that is what the record says."""
    firm = _firm(
        "Verrill Family Office",
        inbound=InboundPath(
            kind="warm_intro_only",
            source_url="https://verrill.example/contact",
        ),
    )

    shortlist = m.build_shortlist(_context(), [firm], now=NOW)

    assert "introductions only" in shortlist.matches[0].access_note


def test_a_broader_published_sector_still_matches_the_founders():
    """Published taxonomies do not agree with founders' words, and a founder
    who writes "compliance automation" should still see a firm that publishes
    "Compliance automation and risk tooling"."""
    firm = _firm(
        "Verrill Family Office",
        sectors=["Compliance automation and risk tooling"],
    )

    shortlist = m.build_shortlist(_context(), [firm], now=NOW)

    sector = next(r for r in shortlist.matches[0].reasons if r.dimension == "sector")
    assert sector.firm_quote == "Compliance automation and risk tooling"
    assert sector.founder_quote == "Compliance automation"


def test_a_two_letter_published_sector_does_not_match_on_its_letters():
    """"AI" nested inside a normalised label is a match a founder cannot see
    the reason for, so the nesting test requires a real word on both sides."""
    assert not m._names_the_same_thing("AI", "Retail chains")
    assert m._names_the_same_thing("Fintech", "Fintech and insurance")


def test_the_weights_are_a_ranking_and_they_sum_to_one():
    assert m.MATCH_WEIGHTS["objection_bridge"] == max(m.MATCH_WEIGHTS.values())
    assert sum(m.MATCH_WEIGHTS.values()) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# A Supabase stand-in for the routes
# ---------------------------------------------------------------------------

class _Query:
    def __init__(self, table: str, store: dict, calls: list):
        self._table = table
        self._store = store
        self._calls = calls
        self._filters: dict = {}
        self._single = False
        self._op = "select"
        self._payload = None

    def select(self, *_a, **_k):
        self._op = "select"
        return self

    def insert(self, payload):
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def eq(self, column, value):
        self._filters[column] = value
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def single(self):
        self._single = True
        return self

    def _matched(self):
        rows = self._store.setdefault(self._table, [])
        return [r for r in rows if all(r.get(k) == v for k, v in self._filters.items())]

    def execute(self):
        rows = self._store.setdefault(self._table, [])
        if self._op == "insert":
            items = self._payload if isinstance(self._payload, list) else [self._payload]
            created = [{"id": str(uuid4()), **item} for item in items]
            rows.extend(created)
            self._calls.append(("insert", self._table, created))
            return SimpleNamespace(data=created, count=len(created))
        if self._op == "update":
            matched = self._matched()
            for row in matched:
                row.update(self._payload)
            self._calls.append(("update", self._table, dict(self._payload)))
            return SimpleNamespace(data=matched, count=len(matched))
        matched = self._matched()
        if self._single:
            return SimpleNamespace(data=(matched[0] if matched else None), count=len(matched))
        return SimpleNamespace(data=matched, count=len(matched))


class _Admin:
    def __init__(self, store, calls):
        self.store = store
        self.calls = calls

    def table(self, name):
        return _Query(name, self.store, self.calls)


def _row(firm: FamilyOffice) -> dict:
    return {"id": str(uuid4()), **firm.model_dump(mode="json")}


def _install(monkeypatch, *, firms, balance=10_000, objections=None):
    store = {
        "family_offices": [_row(f) for f in firms],
        "projects": [{"id": PROJECT, "organization_id": ORG, "name": "Ledgerguard"}],
        "simulations": [{"id": SIM, "organization_id": ORG, "icp_profile_id": ICP}],
        "icp_profiles": [{"id": ICP, "product_summary": FOUNDER_MATERIAL}],
        "canonical_objections": objections or [],
        "capital_shortlists": [],
    }
    calls: list = []
    charged: list[int] = []
    monkeypatch.setattr(capital_api, "get_supabase_admin", lambda: _Admin(store, calls))
    monkeypatch.setattr(
        capital_api, "get_credit_balance", lambda _org: (balance, balance, "founder")
    )
    monkeypatch.setattr(
        capital_api, "deduct_credits", lambda _org, credits: charged.append(credits)
    )
    return store, calls, charged


def _body(**over):
    payload = {
        "project_id": PROJECT,
        "sector": "Compliance automation",
        "stage": "pre-seed",
        "check_size_needed": 500_000,
        "geography": "United States",
        "material": FOUNDER_MATERIAL,
        "simulation_id": SIM,
    }
    payload.update(over)
    return capital_api.ShortlistBody(**payload)


AUTH = {"org_id": ORG}

OBJECTION_ROW = {
    "simulation_id": SIM,
    "organization_id": ORG,
    "objection_key": "regulated-markets-move-slowly",
    "label": "Regulated markets move slowly",
    "quotes": [{"text": BUYER_QUOTE}],
    "load_bearing_score": 9.4,
}


# ---------------------------------------------------------------------------
# The routes
# ---------------------------------------------------------------------------

async def test_the_bank_listing_withholds_stale_records_and_names_them(monkeypatch):
    stale = _firm(
        "Decayed Capital",
        retrieved_at=NOW - timedelta(days=400),
        stale_after=datetime.now(UTC) - timedelta(days=1),
    )
    _install(monkeypatch, firms=[_firm("Verrill Family Office"), stale])

    page = await capital_api.list_firms(
        sector=None, stage=None, firm_type=None, auth=AUTH
    )

    assert [f.firm_name for f in page.firms] == ["Verrill Family Office"]
    assert [w.firm_name for w in page.withheld_stale] == ["Decayed Capital"]


async def test_a_stale_firm_is_refused_rather_than_shown_as_current(monkeypatch):
    """409, not 404. A record we hold and will not stand behind is a different
    answer from a record we do not have, and collapsing them hides that we have
    it."""
    from fastapi import HTTPException

    stale = _firm(
        "Decayed Capital",
        retrieved_at=NOW - timedelta(days=400),
        stale_after=datetime.now(UTC) - timedelta(days=1),
    )
    store, _calls, _charged = _install(monkeypatch, firms=[stale])
    firm_id = store["family_offices"][0]["id"]

    with pytest.raises(HTTPException) as excinfo:
        await capital_api.get_firm(firm_id, auth=AUTH)

    assert excinfo.value.status_code == 409
    assert "verification date" in excinfo.value.detail


async def test_a_row_carrying_a_personal_detail_is_never_served(monkeypatch):
    """The gate runs on read as well as on write.

    A reader that trusts its own table is a reader that serves whatever got
    past the writer — a manual INSERT during curation, a restored backup, a
    later ingestion path written by somebody who did not read this module.
    """
    store, _calls, _charged = _install(monkeypatch, firms=[_firm("Verrill Family Office")])
    store["family_offices"][0]["thesis"] = "Pitch us at ana.ruiz@verrill.example."

    page = await capital_api.list_firms(
        sector=None, stage=None, firm_type=None, auth=AUTH
    )

    assert page.firms == []
    assert page.unreadable == 1


async def test_building_refuses_before_charging_when_nothing_is_current(monkeypatch):
    """Charging first and discovering there is nothing to match against second
    is how a product takes money for an empty document."""
    from fastapi import HTTPException

    stale = _firm(
        "Decayed Capital",
        retrieved_at=NOW - timedelta(days=400),
        stale_after=datetime.now(UTC) - timedelta(days=1),
    )
    store, _calls, charged = _install(monkeypatch, firms=[stale])

    with pytest.raises(HTTPException) as excinfo:
        await capital_api.create_shortlist(_body(), auth=AUTH)

    assert excinfo.value.status_code == 409
    assert charged == []
    assert store["capital_shortlists"] == []


async def test_building_refuses_before_charging_when_the_balance_is_short(monkeypatch):
    from fastapi import HTTPException

    store, _calls, charged = _install(
        monkeypatch, firms=[_firm("Verrill Family Office")], balance=10
    )

    with pytest.raises(HTTPException) as excinfo:
        await capital_api.create_shortlist(_body(), auth=AUTH)

    assert excinfo.value.status_code == 402
    assert charged == []
    assert store["capital_shortlists"] == []


async def test_material_carrying_a_personal_detail_is_refused_before_charging(monkeypatch):
    from fastapi import HTTPException

    store, _calls, charged = _install(
        monkeypatch, firms=[_firm("Verrill Family Office")]
    )

    with pytest.raises(HTTPException) as excinfo:
        await capital_api.create_shortlist(
            _body(simulation_id=None, material="Call me on 212-555-0147."),
            auth=AUTH,
        )

    assert excinfo.value.status_code == 422
    assert charged == []
    assert store["capital_shortlists"] == []


async def test_a_build_charges_once_and_stores_the_shortlist(monkeypatch):
    from app.services.billing.agent_pricing import capital_shortlist_credits

    later_stage = _firm("Meridian Growth", stages=["Series A"])
    store, _calls, charged = _install(
        monkeypatch,
        firms=[_firm("Verrill Family Office"), later_stage],
        objections=[OBJECTION_ROW],
    )

    row = await capital_api.create_shortlist(_body(), auth=AUTH)

    assert charged == [capital_shortlist_credits()]
    assert row["status"] == "complete"
    assert row["credits_charged"] == capital_shortlist_credits()
    assert row["matches_count"] == 1
    assert row["refusals_count"] == 1
    assert row["matches"][0]["firm"]["firm_name"] == "Verrill Family Office"
    # The measured objection reached the bridge through the database, not
    # through the request body.
    assert row["matches"][0]["objection_bridge"]["founder_quote"] in BUYER_QUOTE
    assert store["capital_shortlists"][0]["id"] == row["id"]


async def test_a_stored_shortlist_carries_each_records_retrieval_date(monkeypatch):
    _install(monkeypatch, firms=[_firm("Verrill Family Office")], objections=[OBJECTION_ROW])

    row = await capital_api.create_shortlist(_body(), auth=AUTH)

    assert row["matches"][0]["retrieved_at"]
    assert row["matches"][0]["firm"]["retrieved_at"]
    assert row["as_of"]


# ---------------------------------------------------------------------------
# Price
# ---------------------------------------------------------------------------

def test_the_shortlist_is_priced_at_the_target_margin():
    from app.services.billing.agent_pricing import (
        CAPITAL_SHORTLIST_COGS_USD,
        MIN_MARGIN_PCT,
        capital_shortlist_credits,
    )

    price = capital_shortlist_credits()
    assert price == 3_000

    # The margin floor, asserted rather than assumed: a COGS revision that
    # pushes this under the floor should fail here, not on the ledger.
    revenue = price / 1000  # credits are $0.001 of COGS by definition
    margin_pct = (revenue - float(CAPITAL_SHORTLIST_COGS_USD)) / revenue * 100
    assert margin_pct >= float(MIN_MARGIN_PCT)
