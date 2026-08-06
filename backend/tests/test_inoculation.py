"""The inoculation loop's verdict logic and its refusals.

The loop's whole value is that it can say "this asset did not work". A verdict
engine that only ever reports progress is worth less than nothing, because it
launders an LLM opinion through a measurement pipeline. So these tests are
mostly about the cases where the honest answer is *we cannot tell*.
"""
from __future__ import annotations

import json

import pytest

from app.services.billing.agent_pricing import (
    estimate_inoculation_draft_cost,
    estimate_simulation_cost,
)
from app.services.engine.personas.icp_synthesizer import ProjectMaterial
from app.services.intelligence.inoculation import (
    _converted_agents,
    _evidence_claims,
    _proportion_interval,
    _sourced_numbers,
    _verdict,
    asset_prompt_block,
)
from app.services.intelligence.inoculation_schema import ObjectionDelta, ObjectionMeasurement
from app.services.platforms.base_adapter import BasePlatformAdapter


def _measurement(agent_count: int, agents_active: int) -> ObjectionMeasurement:
    return ObjectionMeasurement(
        agent_count=agent_count,
        agents_active=agents_active,
        reach=_proportion_interval(agent_count, agents_active),
    )


# ---------------------------------------------------------------------------
# Proportion intervals
# ---------------------------------------------------------------------------

def test_zero_observed_is_not_certainty():
    """"No agent raised it in 40" does not exclude a 7% true rate.

    Claiming an objection is dead on zero observations is the most tempting
    overstatement in the whole loop, so the interval carries the rule-of-three
    bound instead of collapsing to zero.
    """
    interval = _proportion_interval(0, 40)

    assert interval.mean == 0.0
    assert interval.upper == pytest.approx(0.075)
    assert interval.n == 40


def test_zero_of_a_tiny_swarm_has_a_very_wide_upper_bound():
    assert _proportion_interval(0, 8).upper == pytest.approx(0.375)


def test_no_active_agents_yields_an_empty_interval():
    interval = _proportion_interval(0, 0)
    assert interval.n == 0
    assert interval.upper == 0.0


def test_proportion_interval_is_centred_on_the_share():
    interval = _proportion_interval(20, 100)
    assert interval.mean == pytest.approx(0.2)
    assert interval.lower < 0.2 < interval.upper


# ---------------------------------------------------------------------------
# Verdicts
# ---------------------------------------------------------------------------

def test_an_objection_that_vanished_is_only_dead_when_the_interval_supports_it():
    before = _measurement(12, 40)
    after = _measurement(0, 40)

    assert _verdict(before, after, significant=True) == "died"
    # Same disappearance, unresolvable swarm: not a result.
    assert _verdict(before, after, significant=False) == "unresolved"


def test_a_measurable_drop_is_shrank():
    assert _verdict(_measurement(20, 40), _measurement(4, 40), True) == "shrank"


def test_a_measurable_rise_is_grew():
    """An asset can draw attention to the objection it answers."""
    assert _verdict(_measurement(4, 40), _measurement(20, 40), True) == "grew"


def test_a_move_inside_the_bands_is_unresolved_not_progress():
    """34% to 31% is not evidence of anything, and must never read as if it is."""
    verdict = _verdict(_measurement(14, 40), _measurement(12, 40), significant=False)
    assert verdict == "unresolved"


def test_no_movement_at_all_is_unchanged():
    assert _verdict(_measurement(10, 40), _measurement(10, 40), False) == "unchanged"


def test_an_objection_absent_before_and_present_after_emerged():
    """An asset that answers one objection and raises two is a result the
    founder needs before they publish it."""
    assert _verdict(_measurement(0, 40), _measurement(9, 40), True) == "emerged"


# ---------------------------------------------------------------------------
# Effectiveness
# ---------------------------------------------------------------------------

def _delta(verdict: str, significant: bool) -> ObjectionDelta:
    return ObjectionDelta(
        objection_key="k",
        label="Objection",
        before=_measurement(20, 40),
        after=_measurement(4, 40),
        significant=significant,
        verdict=verdict,  # type: ignore[arg-type]
        asset_ids=["asset-1"],
    )


def test_only_a_significant_shrink_or_death_counts_as_effective():
    assert _delta("died", True).effective is True
    assert _delta("shrank", True).effective is True


def test_unresolved_never_counts_as_effective():
    """The number the product is sold on has to be one a sceptic accepts."""
    assert _delta("unresolved", False).effective is False
    assert _delta("unchanged", False).effective is False


def test_a_significant_rise_is_not_effective():
    assert _delta("grew", True).effective is False


def test_a_shrink_without_separated_intervals_is_not_effective():
    assert _delta("shrank", False).effective is False


# ---------------------------------------------------------------------------
# Fabricated evidence
#
# Found on the first live run: asked to answer "there is no proof synthetic
# feedback predicts real behavior", the drafter invented the proof and put it in
# three assets. This is Phase 1's bug #5 one level over — the report was stopped
# from writing its own numbers, and the asset drafter never was.
# ---------------------------------------------------------------------------

# Verbatim from the live run. Kept as the fixture because a paraphrase would
# drift away from the thing that actually happened.
_FABRICATED = (
    "In our 14-case internal dataset, the rank-order of objections matched "
    "real-user feedback in 11 cases (Spearman's ρ = 0.74)."
)

_MATERIAL = ProjectMaterial(
    own="Founder $99/mo, Growth $299/mo. A standard run is 100 agents, 5 rounds, "
        "2 platforms and costs 2,265 credits."
)


def test_a_fabricated_correlation_is_caught():
    claims = _evidence_claims(_FABRICATED, _sourced_numbers(_MATERIAL))
    assert claims, "the invented Spearman's rho was not flagged"


def test_prices_the_material_states_are_not_flagged():
    """$99/mo is a price the team sets, not a research finding."""
    body = "Our pricing is $99/mo because a standard run costs us real compute."
    assert _evidence_claims(body, _sourced_numbers(_MATERIAL)) == []


def test_a_number_in_the_material_survives_evidence_language():
    """A figure the material states is sourced, even in an evidential sentence.

    Both halves have to be true for this to test anything: "benchmark" is in
    `_EVIDENCE_WORDS`, and 100 is in the uploaded material. A sentence missing
    either would pass without exercising the exemption at all.
    """
    body = "Our benchmark is the standard run of 100 agents."
    assert "benchmark" in body.lower()
    assert "100" in _sourced_numbers(_MATERIAL)
    assert _evidence_claims(body, _sourced_numbers(_MATERIAL)) == []


def test_an_invented_customer_count_is_caught():
    body = "Across 412 customers, retention held at 94%."
    assert _evidence_claims(body, _sourced_numbers(_MATERIAL))


def test_copy_with_no_numbers_passes():
    body = (
        "We have not yet run a controlled study comparing our output to real "
        "outcomes. Here is the study we intend to run, and when."
    )
    assert _evidence_claims(body, _sourced_numbers(_MATERIAL)) == []


def test_a_number_without_evidence_language_passes():
    """Narrow by design — only figures wearing the clothes of a finding."""
    body = "Setup takes about 15 minutes and the first run completes in 20."
    assert _evidence_claims(body, _sourced_numbers(_MATERIAL)) == []


def test_sourced_numbers_reads_every_material_bucket():
    material = ProjectMaterial(own="a 12", competitor="b 34", market="c 56")
    assert {"12", "34", "56"} <= _sourced_numbers(material)


def test_an_empty_sourced_set_condemns_the_founders_own_price():
    """Why the missing `project_id` mattered, stated as the failure it caused.

    The filter is right to be strict, and it has exactly one input. Starve it of
    the material and it stops distinguishing an invented study from a price the
    founder publishes — every draft is dropped, after a 6,000-token main-model
    pass has already been paid for. This test exists so that a future change
    that re-breaks the input fails here rather than in production.
    """
    body = "Our benchmark is the standard run of 100 agents."

    assert _evidence_claims(body, _sourced_numbers(_MATERIAL)) == []
    assert _evidence_claims(body, set()), "an empty material set must be the loud case"


# ---------------------------------------------------------------------------
# Drafting reads the project's material
# ---------------------------------------------------------------------------

class _Result:
    def __init__(self, data):
        self.data = data


class _Table:
    """Enough of the supabase builder for the drafting path."""

    def __init__(self, admin, name):
        self.admin = admin
        self.name = name
        self._insert: list[dict] | None = None

    def select(self, columns, *_a, **_kw):
        self.admin.selects.setdefault(self.name, []).append(columns)
        return self

    def eq(self, *_a, **_kw):
        return self

    def order(self, *_a, **_kw):
        return self

    def single(self):
        return self

    def insert(self, rows):
        self._insert = rows
        return self

    def execute(self):
        if self._insert is not None:
            self.admin.inserted.extend(self._insert)
            return _Result([
                {**row, "id": f"asset-{i}"} for i, row in enumerate(self._insert)
            ])
        return _Result(self.admin.rows.get(self.name, []))


class _Admin:
    def __init__(self, rows):
        self.rows = rows
        self.selects: dict[str, list[str]] = {}
        self.inserted: list[dict] = []

    def table(self, name):
        return _Table(self, name)


_OBJECTION_ROW = {
    "objection_key": "price-too-high-for-small-teams",
    "label": "Price is too high for small teams",
    "summary": "A two-person team would need a reason for the price.",
    "quotes": [{"text": "can't justify $99 a month"}],
    "agent_count": 12,
    "event_count": 20,
    "originating_cohort": "Buyer",
    "cohort_spread": {},
    "mean_intensity": 0.6,
    "load_bearing_score": 22.0,
}

# Cites "benchmark" and "100", both of which the uploaded material contains. The
# filter drops this asset when `sourced` is empty and keeps it when it is not,
# which makes it the exact probe for the missing column.
_GROUNDED_BODY = "Our benchmark is the standard run of 100 agents, at $99/mo."


def _draft_env(
    monkeypatch,
    project_id,
    body=_GROUNDED_BODY,
    *,
    assets=None,
    product_name="Tallyhook",
):
    from app.services.engine.personas import icp_synthesizer
    from app.services.intelligence import analysis_data, inoculation

    admin = _Admin({
        "simulations": {"id": "sim-1", "project_id": project_id,
                        "prediction_goal": "goal", "icp_profile_id": None},
        "canonical_objections": [_OBJECTION_ROW],
        "projects": {"name": product_name},
    })
    seen: dict[str, object] = {}

    def _gather(pid):
        seen["project_id"] = pid
        return _MATERIAL

    drafted = assets if assets is not None else [{
        "objection_key": "price-too-high-for-small-teams",
        "asset_type": "pricing_rationale",
        "title": "Why we price the way we do",
        "body": body,
        "hypothesis": "Small teams stop raising it.",
    }]

    async def _complete(**kwargs):
        seen["prompt"] = kwargs["messages"][0]["content"]
        return json.dumps({"assets": drafted})

    monkeypatch.setattr(inoculation, "get_supabase_admin", lambda: admin)
    monkeypatch.setattr(inoculation, "llm_complete", _complete)
    monkeypatch.setattr(icp_synthesizer, "gather_material", _gather)
    monkeypatch.setattr(analysis_data, "_named_competitors", lambda _id: [])
    return admin, seen


@pytest.mark.asyncio
async def test_drafting_reads_the_projects_material(monkeypatch):
    """`project_id` was missing from the `.select()`, so `sourced` was always
    empty and every drafted asset was dropped as fabricated."""
    from app.services.intelligence.inoculation import draft_assets

    admin, seen = _draft_env(monkeypatch, "proj-1")

    created = await draft_assets("sim-1", "org-1")

    assert seen["project_id"] == "proj-1", "the run's material was never read"
    assert len(created) == 1
    assert admin.inserted[0]["body"] == _GROUNDED_BODY
    assert any("project_id" in cols for cols in admin.selects["simulations"])


@pytest.mark.asyncio
async def test_the_fabrication_filter_stays_strict_with_material_loaded(monkeypatch):
    """Fixing the input must not soften the check. This is copy a founder may
    publish as their own claim, so there is no partial version worth keeping."""
    from app.services.intelligence.inoculation import draft_assets

    _draft_env(monkeypatch, "proj-1", body=_FABRICATED)

    with pytest.raises(ValueError):
        await draft_assets("sim-1", "org-1")


# ---------------------------------------------------------------------------
# The asset has to argue for the product
#
# The founder read the first real draft and called it commercially suicidal.
# They were right. Twelve assets came back for the ParryAI run; three were
# titled "Disclosure: …" and were lists of what the team did not know, two of
# those three were the *only* asset drafted for their objection, and the answer
# to "patent-pending creates lock-in" was
# `ParryAI Removal & Migration Guide (Draft)`, opening "This document describes
# what it takes to remove ParryAI from a running agentic deployment."
#
# The diagnosis is not that the drafter is dishonest — it is that it had
# over-learned the anti-fabrication rules. Those rules are right for
# *measurement*: the report must not invent a number. They are wrong for *asset
# drafting*, where the job is to make the case the material supports. The
# prompt's own worked example taught it, in as many words: "the honest asset
# says what the team does not yet know". The fixtures below are the real titles
# and the real opening lines.
# ---------------------------------------------------------------------------

_REMOVAL_TITLE = "ParryAI Removal & Migration Guide (Draft)"
_REMOVAL_BODY = (
    "This document describes what it takes to remove ParryAI from a running "
    "agentic deployment. We are publishing it before you buy, not after."
)


def _asset(objection_key, asset_type, title, body="Copy that makes a case."):
    return {
        "objection_key": objection_key,
        "asset_type": asset_type,
        "title": title,
        "body": body,
        "hypothesis": "They stop raising it.",
    }


def test_a_removal_guide_for_the_founders_own_product_is_caught():
    from app.services.intelligence.inoculation import _leads_away

    assert _leads_away(_REMOVAL_TITLE, _REMOVAL_BODY, "ParryAI")
    # The title alone is enough — both halves of the claim are in it.
    assert _leads_away(_REMOVAL_TITLE, "", "ParryAI")
    # And the body alone, for a title that gives nothing away.
    assert _leads_away("Your exit is documented", _REMOVAL_BODY, "ParryAI")


def test_the_check_is_anchored_on_the_products_own_name():
    """Otherwise it eats good copy.

    Removing friction, cancelling a meeting and migrating off the incumbent are
    all things an asset should be free to say. Only doing it *to the product
    being argued for* is the defect.
    """
    from app.services.intelligence.inoculation import _leads_away

    assert not _leads_away(
        "Removing the friction from your CI",
        "Wiring Tallyhook in takes one workflow file. Remove the three scripts "
        "you wrote to paper over the gap.",
        "Tallyhook",
    )
    assert not _leads_away(
        "Moving off spreadsheets",
        "Migrating off your spreadsheet takes an afternoon: export, import, done.",
        "Tallyhook",
    )
    # The intended direction of a migration guide, which must not fire.
    assert not _leads_away(
        "Switching to Tallyhook from a manual chase",
        "Tallyhook imports your open invoices on day one.",
        "Tallyhook",
    )


def test_without_a_product_name_the_check_refuses_rather_than_guesses():
    """"" means "cannot check", never "no match".

    A keyword-only fallback would fire on "Removing the friction" and drop the
    best asset in the draft, which is a worse failure than the one it is
    guarding against — and a silent one.
    """
    from app.services.intelligence.inoculation import _leads_away

    assert _leads_away(_REMOVAL_TITLE, _REMOVAL_BODY, "") == ""


def test_reassurance_about_lock_in_late_in_the_body_is_not_a_removal_guide():
    """The correct answer to a lock-in objection mentions leaving. It must pass.

    An asset is judged on what it sets out to do, so only the opening counts.
    A closing sentence saying the door is not locked is exactly the copy this
    objection needs.
    """
    from app.services.intelligence.inoculation import _leads_away

    body = (
        "Your policy definitions are yours. They are exportable in a documented, "
        "open schema, and nothing in them is specific to us. "
        + "Every rule you write is portable. " * 12
        + "If you ever remove ParryAI, the policies you wrote come with you."
    )
    assert _leads_away("What you keep", body, "ParryAI") == ""


def test_a_title_that_says_it_is_unfinished_is_caught():
    from app.services.intelligence.inoculation import _unpublishable_title

    assert _unpublishable_title(_REMOVAL_TITLE)
    assert _unpublishable_title("Pricing page [draft]")
    assert _unpublishable_title("What a seat costs, and why") == ""


def test_a_concession_never_stands_alone_for_an_objection():
    """Two of the three real disclosures were the only asset for their objection.

    So the founder's entire answer to "your ROI claim is unproven" was a page
    agreeing with it. The cap keeps one — dropping it would hide the drafter's
    failure — and the ERROR log is what makes it visible, because the UI cannot
    show a difference between "one asset" and "one asset that concedes".
    """
    from app.services.intelligence.inoculation import _cap_concessions

    rows = [
        _asset("roi", "disclosure", "Disclosure: We Don't Yet Know Our Own ROI"),
        _asset("roi", "disclosure", "Disclosure: What We Have Not Yet Measured"),
    ]
    kept = _cap_concessions(rows)

    assert len(kept) == 1
    assert kept[0]["title"] == "Disclosure: We Don't Yet Know Our Own ROI"


def test_one_concession_beside_a_positive_asset_survives():
    """The cap is a cap, not a ban.

    DECISIONS §4's headline claim is that an honest disclosure measurably moved
    an objection. Forbidding the type would delete the finding along with the
    failure mode.
    """
    from app.services.intelligence.inoculation import _cap_concessions

    rows = [
        _asset("roi", "faq_entry", "How we measure blast radius today"),
        _asset("roi", "disclosure", "Disclosure: What We Have Not Yet Measured"),
    ]
    assert len(_cap_concessions(rows)) == 2


def test_extra_concessions_are_dropped_and_the_order_is_kept():
    from app.services.intelligence.inoculation import _cap_concessions

    rows = [
        _asset("a", "faq_entry", "What it does"),
        _asset("a", "disclosure", "First concession"),
        _asset("a", "disclosure", "Second concession"),
        _asset("b", "pricing_rationale", "What a seat costs"),
    ]
    kept = _cap_concessions(rows)

    assert [r["title"] for r in kept] == [
        "What it does", "First concession", "What a seat costs",
    ]


def test_the_menu_puts_the_case_making_types_first():
    """A model reaches for the first plausible item on a list.

    `disclosure` was first, and 3 of 12 assets in the first live draft were
    disclosures. Order in this tuple is prompt copy, not bookkeeping.
    """
    from app.services.intelligence.inoculation_schema import ASSET_TYPES

    assert ASSET_TYPES[0] != "disclosure"
    assert ASSET_TYPES[-1] == "disclosure"


def test_the_three_declarations_of_the_asset_menu_agree():
    """`ASSET_TYPES`, the schema's `AssetType`, and the API's edit `Literal`.

    Three spellings of one set, in two files, and none of them can import the
    others: pydantic needs a static `Literal` and the tuple is what gets
    interpolated into the prompt. Reordering the tuple for the prompt is exactly
    the kind of edit that would leave the third behind, and the symptom would be
    a founder's edit rejected as an unknown type.

    `frontend/src/lib/founder.ts` carries a fourth. It cannot be reached from
    pytest; it is a union rather than an ordered list, so order cannot drift,
    and membership drift shows up as a build error there.
    """
    import typing

    from app.api.inoculation import UpdateAssetBody
    from app.services.intelligence.inoculation_schema import ASSET_TYPES, AssetType

    assert set(typing.get_args(AssetType)) == set(ASSET_TYPES)

    patch_type = UpdateAssetBody.model_fields["asset_type"].annotation
    literal = next(
        arg for arg in typing.get_args(patch_type) if typing.get_args(arg)
    )
    assert set(typing.get_args(literal)) == set(ASSET_TYPES)


@pytest.mark.asyncio
async def test_the_removal_guide_never_reaches_the_database(monkeypatch):
    """End to end, on the asset the founder actually read."""
    from app.services.intelligence.inoculation import draft_assets

    admin, _ = _draft_env(
        monkeypatch, "proj-1", product_name="ParryAI",
        assets=[
            _asset(
                "price-too-high-for-small-teams", "faq_entry",
                "What you keep if you leave",
                "Your policy definitions are exportable in an open schema.",
            ),
            _asset(
                "price-too-high-for-small-teams", "migration_guide",
                _REMOVAL_TITLE, _REMOVAL_BODY,
            ),
        ],
    )

    created = await draft_assets("sim-1", "org-1")

    assert [row["title"] for row in created] == ["What you keep if you leave"]
    assert all(_REMOVAL_TITLE != row["title"] for row in admin.inserted)


@pytest.mark.asyncio
async def test_the_prompt_tells_the_drafter_whose_side_it_is_on(monkeypatch):
    """The prompt is the lever the checks cannot replace.

    Both halves are asserted: that it names the product, and that the worked
    example it used to teach — "the honest asset says what the team does not yet
    know" — is gone. That sentence is why the confessions were written.
    """
    from app.services.intelligence.inoculation import draft_assets

    _, seen = _draft_env(monkeypatch, "proj-1", product_name="Tallyhook")
    await draft_assets("sim-1", "org-1")
    prompt = seen["prompt"]

    assert "on Tallyhook's side" in prompt
    assert "Every asset leads with a claim about what Tallyhook does" in prompt
    assert "moving **onto** Tallyhook" in prompt
    assert "the honest asset says what the team does not yet know" not in prompt
    assert "no evidence. Do not invent any" in prompt.replace("**", "")


# ---------------------------------------------------------------------------
# Who changed their mind
# ---------------------------------------------------------------------------

class _Ev:
    def __init__(self, event_id, username):
        self.id = event_id
        self.agent_username = username
        self.agent_id = event_id


class _Run:
    def __init__(self, events):
        self.events = events


def test_converted_agents_comes_from_the_canonical_event_ids():
    """The list was always empty, and the docstring pre-excused it.

    It re-derived membership by slugging each raw objection string with a
    *second, incompatible* algorithm — `"-".join(s.lower().split())[:64]`
    against the canonicalizer's `re.sub(r"[^a-z0-9]+", "-", ...)[:60]` — so a
    verbatim identical objection produced two different keys and the set
    intersection never matched anything. Membership now comes from the
    clustering pass's own record of which events it assigned to the key.
    """
    parent = _Run([_Ev("p1", "ada"), _Ev("p2", "grace"), _Ev("p3", "linus")])
    child = _Run([_Ev("c1", "grace")])

    converted = _converted_agents(
        parent,
        child,
        {"event_ids": ["p1", "p2"]},
        {"event_ids": ["c1"]},
    )

    assert converted == ["ada"]


def test_an_objection_absent_from_the_child_converts_everyone_who_voiced_it():
    parent = _Run([_Ev("p1", "ada"), _Ev("p2", "grace")])
    child = _Run([_Ev("c1", "ada")])

    assert _converted_agents(parent, child, {"event_ids": ["p1", "p2"]}, None) == [
        "ada", "grace"
    ]


def test_an_objection_absent_from_the_parent_converts_nobody():
    parent = _Run([_Ev("p1", "ada")])
    child = _Run([_Ev("c1", "ada")])

    assert _converted_agents(parent, child, None, {"event_ids": ["c1"]}) == []


def test_the_second_slug_algorithm_is_gone():
    """One definition of key derivation, in `refs.slugify`. A duplicated strip
    set is how these failures come back."""
    from app.services.intelligence import inoculation

    assert not hasattr(inoculation, "_normalised")


# ---------------------------------------------------------------------------
# Pre-positioning
# ---------------------------------------------------------------------------

class _Adapter(BasePlatformAdapter):
    """Minimal concrete adapter — the base class is abstract."""

    platform_id = "test"

    async def initialize(self, config: dict, agents: list) -> None:  # pragma: no cover
        self.set_topic(config)

    async def run_round(self, round_number: int):  # pragma: no cover
        yield  # type: ignore[misc]

    async def get_feed(self, agent_username: str):  # pragma: no cover
        return []

    async def post(self, agent_username: str, content: str, metadata=None):  # pragma: no cover
        raise NotImplementedError

    async def comment(self, agent_username: str, post_id: str, content: str):  # pragma: no cover
        raise NotImplementedError

    async def react(self, agent_username: str, post_id: str, reaction):  # pragma: no cover
        raise NotImplementedError

    def get_state_snapshot(self) -> dict:  # pragma: no cover
        return {}


def test_asset_block_is_empty_for_an_ordinary_run():
    assert asset_prompt_block([]) == ""


def test_asset_block_presents_material_as_published_not_posted():
    block = asset_prompt_block([
        {
            "title": "Why we price per seat",
            "asset_type": "pricing_rationale",
            "body": "Our pricing follows the value a team gets, not its headcount.",
            "objection_key": "price-too-high",
        }
    ])

    assert "published this material alongside the subject" in block
    assert "Why we price per seat" in block
    assert "pricing rationale" in block


def test_asset_body_is_truncated_in_the_prompt():
    """A 4,000-character page in every action prompt multiplies the run's
    largest cost line, and an agent reacts to the first paragraph anyway."""
    block = asset_prompt_block([
        {
            "title": "Security",
            "asset_type": "security_page",
            "body": "x" * 5000,
            "objection_key": "security",
        }
    ])

    assert len(block) < 1200


def test_assets_reach_agents_through_the_topic_block():
    """One hook on the base class, inherited by all twelve adapters.

    Adding it to twelve `initialize` implementations would be twelve chances to
    miss one, and a missed adapter means a re-simulation whose agents never saw
    the asset — which would report as "the asset did not work".
    """
    adapter = _Adapter()
    adapter.set_topic({
        "prediction_goal": "Our new pricing",
        "pre_positioned": "The team has published this material...\n\n",
    })

    block = adapter.topic_block()

    assert "Our new pricing" in block
    assert "The team has published this material" in block


def test_an_ordinary_run_topic_block_is_unchanged():
    adapter = _Adapter()
    adapter.set_topic({"prediction_goal": "Our new pricing"})

    assert adapter.topic_block() == "The conversation is about: Our new pricing\n\n"


# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------

def test_a_resimulation_is_not_charged_for_agents_it_never_generates():
    normal = estimate_simulation_cost(100, 5, 2, 1, "standard")
    reused = estimate_simulation_cost(100, 5, 2, 1, "standard", reuse_agents=True)

    assert reused.breakdown["agent_generation"] == 0.0
    assert normal.breakdown["agent_generation"] > 0.0
    assert reused.actual_cost_usd < normal.actual_cost_usd


def test_reuse_changes_generation_and_canonicalization_and_nothing_else():
    """Two stages differ for a re-simulation, and the ledger says which two.

    This test previously asserted that *only* generation moved. That was wrong
    in the expensive direction: a re-simulation's clustering call carries the
    parent's objections as priors, and the same run measured 3,162 output tokens
    without them against 13,955 with them.
    """
    normal = estimate_simulation_cost(100, 5, 2, 1, "standard")
    reused = estimate_simulation_cost(100, 5, 2, 1, "standard", reuse_agents=True)

    for stage in ("agent_actions", "event_measurement", "report"):
        assert reused.breakdown[stage] == normal.breakdown[stage]
    assert reused.breakdown["agent_generation"] == 0.0
    assert (
        reused.breakdown["objection_canonicalization"]
        > normal.breakdown["objection_canonicalization"]
    )


def test_pre_positioned_assets_are_charged_on_every_action():
    """An asset rides in `topic_block()`, so it is re-sent with every prompt.

    Measured on the parent/child pair `f980fe0d` / `fa28d899` — same agents,
    same platforms, six assets apart — at 312 against 1,654 input tokens per
    action. Charging assets as a one-off would under-quote the largest stage of
    the run by more than a factor of two.
    """
    without = estimate_simulation_cost(96, 5, 2, 1, "standard", reuse_agents=True)
    with_six = estimate_simulation_cost(
        96, 5, 2, 1, "standard", reuse_agents=True, inoculation_assets=6
    )

    assert with_six.breakdown["agent_actions"] > without.breakdown["agent_actions"] * 1.5
    # Only the action stage moves — assets are not sent to the classifier or
    # the report writer.
    for stage in ("agent_generation", "event_measurement", "objection_canonicalization", "report"):
        assert with_six.breakdown[stage] == without.breakdown[stage]


def test_the_asset_surcharge_scales_with_the_number_of_assets():
    def actions(n: int) -> float:
        return estimate_simulation_cost(
            96, 5, 2, 1, "standard", reuse_agents=True, inoculation_assets=n
        ).breakdown["agent_actions"]

    assert actions(0) < actions(1) < actions(6) < actions(12)


def test_a_negative_asset_count_is_rejected():
    with pytest.raises(ValueError):
        estimate_simulation_cost(96, 5, 2, 1, "standard", inoculation_assets=-1)


def test_the_measured_loop_is_quoted_above_what_it_cost():
    """The margin floor, checked against the one live loop we have bills for.

    From `llm_usage`, excluding the separately-quoted drafting pass and counting
    one clustering call per run: `f980fe0d` cost **$2.307** and `fa28d899`
    **$2.553**. A quote below either figure is a run served under the margin the
    whole model exists to hold — and the child was the one that slipped, because
    it was quoted as a cheaper version of its parent when it is a more expensive
    one.

    (The child's ledger total reads $2.660 because it was re-clustered after the
    key-carryover fix. That second call is a repair, not what the run costs.)
    """
    parent = estimate_simulation_cost(96, 5, 2, 1, "standard")
    child = estimate_simulation_cost(
        96, 5, 2, 1, "standard", reuse_agents=True, inoculation_assets=6
    )

    assert parent.actual_cost_usd >= 2.307
    # Above the as-billed total too, not just the clean one.
    assert child.actual_cost_usd >= 2.660
    # And the direction is the measured one: an asset-carrying re-simulation
    # costs *more* than its parent, not less. The saving on agent generation is
    # real and smaller than the surcharge on actions.
    assert child.actual_cost_usd > parent.actual_cost_usd


def test_asset_drafting_is_priced_as_its_own_stage():
    estimate = estimate_inoculation_draft_cost()

    assert estimate.stage == "inoculation_draft"
    assert estimate.credits > 0
    assert estimate.margin_pct >= 70.0


def test_drafting_costs_a_fraction_of_a_standard_run():
    assert estimate_inoculation_draft_cost().standard_run_equivalents < 0.25
