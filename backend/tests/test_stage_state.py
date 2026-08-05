"""The rail states what it inherited and what a missing input costs.

These are the server half of the acceptance criteria for the staged IA. The
frontend half lives in `frontend/src/lib/__tests__/`, and the two halves check
different things: this file checks that the *answer* is right, that one checks
that the answer is *rendered*.

The load-bearing test in here is
`test_no_stage_ever_declares_nothing_in_any_reachable_state`. It walks the
product of every input combination the four seeded states can produce and
asserts the invariant on all of them, because the failure it guards is not a
stage that renders wrongly — it is a stage that renders silently, and a silent
stage looks identical to a stage that had nothing to say.
"""
from __future__ import annotations

import itertools
from datetime import UTC, datetime, timedelta

import pytest
import structlog.testing

from app.services.stages import STAGE_ORDER, build_product_states
from app.services.stages.product_state import _OrgData

NOW = datetime(2026, 8, 5, 3, 0, tzinfo=UTC)
ORG = "11111111-1111-1111-1111-111111111111"
PRODUCT = "22222222-2222-2222-2222-222222222222"
SIM = "33333333-3333-3333-3333-333333333333"


class FakeOrgData:
    """Stand-in for `_OrgData` holding rows instead of querying for them.

    Substituted rather than mocked at the Supabase client, because the thing
    under test is the reasoning over the rows, and a mock of the query builder
    would mostly assert that the query builder was called the way it was written
    — which is a test of the test.
    """

    def __init__(self, **rows):
        self.org_id = ORG
        self.project_ids = [PRODUCT]
        self.documents = rows.get("documents", [])
        self.profiles = rows.get("profiles", [])
        self.simulations = rows.get("simulations", [])
        self.discovery_runs = rows.get("discovery_runs", [])
        self.objections = rows.get("objections", [])
        self.assets = rows.get("assets", [])
        self.inoculation_results = rows.get("inoculation_results", [])
        self.analyses = rows.get("analyses", [])


@pytest.fixture
def patched(monkeypatch):
    """Build states against supplied rows."""

    def build(**rows):
        monkeypatch.setattr(
            "app.services.stages.product_state._OrgData",
            lambda org_id, project_ids: FakeOrgData(**rows),
        )
        return build_product_states(
            ORG,
            [{"id": PRODUCT, "name": "ParryAI", "description": "A thing"}],
            now=NOW,
        )[0]

    return build


# ---------------------------------------------------------------------------
# Row builders — the four seeded states from the acceptance plan
# ---------------------------------------------------------------------------

def doc(status="completed"):
    return {
        "id": "d1",
        "project_id": PRODUCT,
        "processing_status": status,
        "material_kind": "own",
    }


def profile(*, confirmed=False, archetypes=6):
    return {
        "id": "p1",
        "project_id": PRODUCT,
        "name": "Buyers",
        "confirmed_at": "2026-08-04T10:00:00+00:00" if confirmed else None,
        "created_at": "2026-08-03T10:00:00+00:00",
        "updated_at": "2026-08-04T10:00:00+00:00",
        "profile": {"archetypes": [{"id": f"a{i}"} for i in range(archetypes)]},
    }


def simulation(*, status="completed", variants=1, stage="launch_gtm", sim_id=SIM):
    return {
        "id": sim_id,
        "project_id": PRODUCT,
        "name": "Run",
        "status": status,
        "variants": variants,
        "founder_stage": stage,
        "parent_simulation_id": None,
        "created_at": "2026-08-04T09:00:00+00:00",
        "completed_at": "2026-08-04T11:00:00+00:00",
    }


def objections(n, sim_id=SIM):
    return [{"id": f"o{i}", "simulation_id": sim_id} for i in range(n)]


# ---------------------------------------------------------------------------
# The binding rule
# ---------------------------------------------------------------------------

def test_no_stage_ever_declares_nothing_in_any_reachable_state(patched):
    """Every stage renders an inherited line or a missing-input notice.

    Never neither. Walked across the product of the inputs that vary rather
    than on one happy path, because the state this is guarding against is a
    stage that happens to have neither in some corner nobody clicked through.
    """
    doc_states = ([], [doc("completed")], [doc("processing")], [doc("failed")])
    profile_states = ([], [profile(confirmed=False)], [profile(confirmed=True)])
    sim_states = (
        [],
        [simulation(status="running")],
        [simulation(status="completed")],
        [simulation(status="completed", variants=4)],
    )
    objection_states = ([], objections(12))

    checked = 0
    for docs, profs, sims, objs in itertools.product(
        doc_states, profile_states, sim_states, objection_states
    ):
        state = patched(
            documents=docs, profiles=profs, simulations=sims, objections=objs
        )
        for stage in state.stages:
            assert stage.inherited or stage.missing, (
                f"stage {stage.id} declared nothing with "
                f"docs={len(docs)} profiles={len(profs)} sims={len(sims)} "
                f"objections={len(objs)}"
            )
            checked += 1

    # The count is asserted so this cannot silently degrade into a test that
    # iterates an empty product and passes.
    assert checked == 4 * 3 * 4 * 2 * len(STAGE_ORDER)


def test_every_blocked_stage_carries_the_button_that_unblocks_it(patched):
    """`blocked` without an action is a grey button by another name."""
    state = patched()
    blocked = [s for s in state.stages if s.runnable == "blocked"]
    assert blocked, "an empty product should block at least one stage"
    for stage in blocked:
        assert any(m.action for m in stage.missing), (
            f"stage {stage.id} is blocked with no way forward"
        )


def test_nothing_is_ever_disabled_only_ready_degraded_or_blocked(patched):
    state = patched(documents=[doc()], profiles=[profile(confirmed=True)])
    assert {s.runnable for s in state.stages} <= {"ready", "degraded", "blocked"}


# ---------------------------------------------------------------------------
# The stated cost of a missing input — the copy the design settled on
# ---------------------------------------------------------------------------

def test_reactions_without_an_audience_states_what_the_answer_loses(patched):
    state = patched(documents=[doc()])
    reactions = next(s for s in state.stages if s.id == "reactions")
    assert reactions.runnable == "degraded"
    consequences = " ".join(m.consequence for m in reactions.missing)
    assert "general business audience" in consequences
    assert "not the ones yours will get" in consequences


def test_reactions_without_material_says_agents_see_only_the_description(patched):
    state = patched(profiles=[profile()])
    reactions = next(s for s in state.stages if s.id == "reactions")
    consequences = " ".join(m.consequence for m in reactions.missing)
    assert "one-line description" in consequences


def test_answers_is_blocked_not_degraded_when_no_objection_exists(patched):
    """Skipping to stage 3 is meaningless, not merely weaker."""
    state = patched(
        documents=[doc()],
        profiles=[profile(confirmed=True)],
        simulations=[simulation()],
        objections=[],
    )
    answers = next(s for s in state.stages if s.id == "answers")
    assert answers.runnable == "blocked"
    assert answers.missing[0].action is not None
    assert "reactions" in answers.missing[0].action.href


def test_answers_unblocks_once_a_run_produced_objections(patched):
    state = patched(
        documents=[doc()],
        profiles=[profile(confirmed=True)],
        simulations=[simulation()],
        objections=objections(12),
    )
    answers = next(s for s in state.stages if s.id == "answers")
    assert answers.runnable == "ready"
    assert any("12 to answer" in line.label for line in answers.inherited)


def test_buyers_says_the_list_is_a_guess_until_the_audience_is_confirmed(patched):
    state = patched(documents=[doc()], profiles=[profile(confirmed=False)])
    buyers = next(s for s in state.stages if s.id == "buyers")
    assert buyers.runnable == "degraded"
    assert "guess at your buyer" in " ".join(m.consequence for m in buyers.missing)


def test_buyers_is_ready_once_the_audience_is_confirmed(patched):
    state = patched(documents=[doc()], profiles=[profile(confirmed=True)])
    buyers = next(s for s in state.stages if s.id == "buyers")
    assert buyers.runnable == "ready"
    assert not buyers.missing


def test_editing_is_not_the_only_way_to_be_confirmed(patched):
    """A founder who agrees with everything must still read as confirmed.

    This is the whole reason `confirmed_at` exists as a column separate from
    `edited_by_user` — see migration 030. A profile with no edits and a
    confirmation timestamp is the common path, not an edge case.
    """
    state = patched(documents=[doc()], profiles=[profile(confirmed=True)])
    audience = next(s for s in state.stages if s.id == "audience")
    assert audience.produced is not None
    assert "confirmed 4 Aug" in audience.produced


# ---------------------------------------------------------------------------
# Nothing invented
# ---------------------------------------------------------------------------

def test_a_product_with_nothing_to_report_returns_no_attention_lines(patched):
    state = patched()
    assert state.attention == []


def test_attention_lines_only_appear_for_rows_that_exist(patched):
    state = patched(
        documents=[doc(), doc("processing")],
        profiles=[profile(confirmed=True)],
        simulations=[simulation()],
        objections=objections(12),
    )
    kinds = {line.kind for line in state.attention}
    assert "run_finished" in kinds
    assert "documents_processing" in kinds
    # Never searched for companies, so there is no list to call stale.
    assert "buyers_stale" not in kinds
    assert any("12 objections found" in line.text for line in state.attention)


def test_a_stale_candidate_list_is_reported_only_once_it_is_stale(patched):
    fresh = (NOW - timedelta(days=2)).isoformat()
    stale = (NOW - timedelta(days=30)).isoformat()

    def with_search(created_at):
        return patched(
            documents=[doc()],
            profiles=[profile(confirmed=True)],
            discovery_runs=[
                {
                    "id": "g1",
                    "project_id": PRODUCT,
                    "status": "completed",
                    "candidates_found": 40,
                    "created_at": created_at,
                }
            ],
        )

    assert not any(
        line.kind == "buyers_stale" for line in with_search(fresh).attention
    )
    assert any(
        line.kind == "buyers_stale" for line in with_search(stale).attention
    )


def test_an_unreadable_archetype_list_reports_absence_not_zero(patched):
    """`0 buyer types` would be a measurement. We did not measure anything."""
    broken = profile()
    broken["profile"] = None
    state = patched(documents=[doc()], profiles=[broken])
    audience = next(s for s in state.stages if s.id == "audience")
    assert audience.produced is not None
    assert "0 buyer types" not in audience.produced


def test_a_finished_run_with_no_objections_does_not_claim_zero_objections(patched):
    state = patched(
        documents=[doc()],
        profiles=[profile(confirmed=True)],
        simulations=[simulation()],
        objections=[],
    )
    reactions = next(s for s in state.stages if s.id == "reactions")
    assert reactions.produced is not None
    assert "0 objections" not in reactions.produced
    assert "not worked out yet" in reactions.produced


def test_an_unresolved_message_test_is_reported_as_unresolved(patched):
    state = patched(
        documents=[doc()],
        profiles=[profile(confirmed=True)],
        simulations=[simulation(variants=4)],
        analyses=[{"simulation_id": SIM, "scoreboard": {"winner_variant_key": None}}],
    )
    messages = next(s for s in state.stages if s.id == "messages")
    assert messages.produced is not None
    assert "too close to call" in messages.produced
    assert any(
        line.kind == "message_test_unresolved" for line in state.attention
    )


def test_a_resolved_message_test_is_not_reported_as_needing_attention(patched):
    state = patched(
        documents=[doc()],
        profiles=[profile(confirmed=True)],
        simulations=[simulation(variants=4)],
        analyses=[{"simulation_id": SIM, "scoreboard": {"winner_variant_key": "b"}}],
    )
    assert not any(
        line.kind == "message_test_unresolved" for line in state.attention
    )


# ---------------------------------------------------------------------------
# Axis B
# ---------------------------------------------------------------------------

def test_the_moment_defaults_to_the_last_run(patched):
    state = patched(simulations=[simulation(stage="growth")])
    assert state.moment.id == "growth"
    assert state.moment.source == "last_run"


def test_the_moment_says_it_is_a_default_when_nothing_has_run(patched):
    state = patched()
    assert state.moment.source == "default"


def test_an_unrecognised_stored_stage_falls_back_rather_than_rendering_a_key(
    patched,
):
    """A stage id that is not in the registry must not reach the screen."""
    state = patched(simulations=[simulation(stage="not_a_stage")])
    assert state.moment.source == "default"
    assert state.moment.label != "not_a_stage"


# ---------------------------------------------------------------------------
# Counting
# ---------------------------------------------------------------------------

def test_stages_ready_counts_only_stages_with_everything_they_need(patched):
    state = patched(documents=[doc()], profiles=[profile(confirmed=True)])
    ready = [s.id for s in state.stages if s.runnable == "ready"]
    assert state.stages_ready == len(ready)
    # Answers is blocked with no run, so a fully-prepared product still cannot
    # report 5 of 5 — which is the honest number.
    assert state.stages_ready < len(STAGE_ORDER)


def test_a_bad_timestamp_is_logged_rather_than_silently_dropped(patched):
    """A parse that quietly yields None is how absence and failure merge."""
    bad = profile(confirmed=True)
    bad["confirmed_at"] = "not-a-date"
    with structlog.testing.capture_logs() as logs:
        patched(documents=[doc()], profiles=[bad])
    assert any(
        entry.get("event") == "stage_state_unparseable_timestamp" for entry in logs
    )


def test_a_stage_that_declares_nothing_is_logged_at_error():
    """The invariant is enforced in code, not only in this test file."""
    from app.services.stages.product_state import StageState, _check_invariants

    silent = StageState(
        id="audience",
        number=1,
        label="Audience",
        blurb="who reacts to this",
        href="/app/products/x/audience",
        runnable="ready",
    )
    with structlog.testing.capture_logs() as logs:
        _check_invariants("x", [silent])
    assert any(entry.get("event") == "stage_declares_nothing" for entry in logs)


# ---------------------------------------------------------------------------
# Found on the deployed rail, against a seeded product
# ---------------------------------------------------------------------------

def test_a_resimulation_is_not_read_as_the_latest_run(patched):
    """A re-simulation answers the parent's objections; it is not stage 2's run.

    On the seeded full-rail product the child was the newest completed run, so
    stage 2 announced "objections not worked out yet" about a run that never had
    objections of its own, and stage 5 lost the scoreboard because that lives on
    the parent. Everything else about the product was correct, which is why no
    existing test caught it — the rail was right, it was reading the wrong row.
    """
    parent = simulation(sim_id=SIM, variants=4)
    child = {
        **simulation(sim_id="44444444-4444-4444-4444-444444444444", variants=4),
        "parent_simulation_id": SIM,
        "completed_at": "2026-08-04T23:00:00+00:00",
    }
    state = patched(
        documents=[doc()],
        profiles=[profile(confirmed=True)],
        simulations=[child, parent],
        objections=objections(12),
        analyses=[{"simulation_id": SIM, "scoreboard": {"winner_variant_key": None}}],
    )

    reactions = next(s for s in state.stages if s.id == "reactions")
    assert reactions.produced is not None
    assert "12 objections found" in reactions.produced

    messages = next(s for s in state.stages if s.id == "messages")
    assert messages.produced is not None
    assert "too close to call" in messages.produced


def test_counted_nouns_are_spelled_the_way_a_person_writes_them(patched):
    """`12 companys` shipped to production. Absent is absent; so is grammar."""
    state = patched(
        documents=[doc()],
        profiles=[profile(confirmed=True)],
        simulations=[simulation()],
        objections=objections(4),
        discovery_runs=[
            {
                "id": "g1",
                "project_id": PRODUCT,
                "status": "completed",
                "candidates_found": 12,
                "created_at": "2026-08-04T10:00:00+00:00",
            }
        ],
    )
    buyers = next(s for s in state.stages if s.id == "buyers")
    assert buyers.produced is not None
    assert "companys" not in buyers.produced
    assert "12 companies found" in buyers.produced

    answers = next(s for s in state.stages if s.id == "answers")
    assert any("4 to answer" in line.label for line in answers.inherited)
    assert not any("to answers" in line.label for line in answers.inherited)


def test_one_company_is_singular(patched):
    state = patched(
        documents=[doc()],
        profiles=[profile(confirmed=True)],
        discovery_runs=[
            {
                "id": "g1",
                "project_id": PRODUCT,
                "status": "completed",
                "candidates_found": 1,
                "created_at": "2026-08-04T10:00:00+00:00",
            }
        ],
    )
    buyers = next(s for s in state.stages if s.id == "buyers")
    assert buyers.produced is not None
    assert buyers.produced.startswith("1 company found")


def test_org_data_makes_no_query_for_an_org_with_no_products():
    """An empty org must not reach the database at all."""
    data = _OrgData(ORG, [])
    assert data.documents == []
    assert data.simulations == []
    assert data.analyses == []
