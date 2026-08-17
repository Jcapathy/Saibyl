"""The subject a run's agents actually react to.

The defect these guard: a founder uploaded a 14,028-character deck, it extracted
cleanly, and their agents discussed the one-line description of it. The material
reached the *agent-generation* prompt at `doc_context[:2000]` — shaping who the
agents were — and never reached the conversation those agents then had.

Four of these are the ones that matter, and they are the four that would have
caught it: the brief reaches all twelve adapters' prompts, competitor material
can never become the subject, a run with no material still works and says so,
and the quote moves when a brief is present.
"""
from __future__ import annotations

import inspect
import json
import pathlib
from collections import defaultdict

import pytest
from structlog.testing import capture_logs

from app.services.billing.agent_pricing import (
    SUBJECT_BRIEF_ACTION,
    SUBJECT_DISTILLATION,
    estimate_simulation_cost,
)
from app.services.engine.personas.icp_synthesizer import ProjectMaterial
from app.services.intelligence import subject_brief as sb
from app.services.platforms.base_adapter import BasePlatformAdapter
from app.services.platforms.registry import PLATFORM_REGISTRY, get_adapter, load_all_adapters

GOAL = "Whether founders will pay $99/month for synthetic audience testing"
BRIEF = (
    "Saibyl\n"
    "What it is: a synthetic audience that argues about your pitch before real "
    "buyers do.\n"
    "Who it is for: pre-seed and seed B2B founders without a customer list.\n"
    "What it claims: measured sentiment with confidence intervals, and objections "
    "ranked by how much of the swarm carries them.\n"
    "What it costs: $99/month."
)


def _events(logs) -> set[str]:
    """Event names from a `capture_logs` block.

    structlog is not bound to stdlib logging outside `create_app`, so `caplog`
    would see nothing here and every log assertion would pass vacuously.
    """
    return {entry["event"] for entry in logs}


def _entry(logs, event: str) -> dict:
    return next(e for e in logs if e["event"] == event)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class _Query:
    def __init__(self, store, table):
        self._store = store
        self._table = table

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def upsert(self, row, **_k):
        self._store.upserts.append(row)
        self._store.tables.setdefault(self._table, [])
        self._store.tables[self._table] = [row]
        return self

    def execute(self):
        return type("Result", (), {"data": list(self._store.tables.get(self._table, []))})()


class _Admin:
    """A supabase stand-in over a dict of table name -> rows."""

    def __init__(self, tables=None):
        self.tables = tables or {}
        self.upserts: list[dict] = []

    def table(self, name):
        return _Query(self, name)


def _adapter() -> BasePlatformAdapter:
    class _Probe(BasePlatformAdapter):
        platform_id = "probe"

        async def initialize(self, config, agents): ...
        async def run_round(self, round_number): ...  # type: ignore[override]
        async def get_feed(self, agent_username): ...
        async def post(self, agent_username, content, metadata=None): ...
        async def comment(self, agent_username, post_id, content): ...
        async def react(self, agent_username, post_id, reaction): ...
        def get_state_snapshot(self): return {}

    return _Probe()


# ---------------------------------------------------------------------------
# 1. The brief reaches all twelve adapters' prompts
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def adapters() -> list[BasePlatformAdapter]:
    load_all_adapters()
    return [get_adapter(pid) for pid in PLATFORM_REGISTRY]


def test_the_brief_reaches_every_adapters_rendered_prompt(adapters):
    """Not "the base class holds it" — the string is in the prompt, per adapter.

    `topic_block()` lives on `BasePlatformAdapter` precisely so there is no
    per-adapter path to miss. This renders each adapter's real `_ACTION_PROMPT`
    with its real topic block and looks for the subject inside it, which is what
    an agent is actually sent.
    """
    assert len(adapters) >= 12

    for adapter in adapters:
        adapter.set_topic({"prediction_goal": GOAL, "subject_brief": BRIEF})
        module = inspect.getmodule(type(adapter))
        rendered = module._ACTION_PROMPT.format_map(
            defaultdict(str, topic=adapter.topic_block())
        )

        assert "What it costs: $99/month." in rendered, (
            f"{adapter.platform_id} never shows its agents the subject brief"
        )
        assert GOAL in rendered, (
            f"{adapter.platform_id} lost the framing question"
        )


def test_the_subject_and_the_framing_are_distinguishable(adapters):
    """Both present, with different roles, and the difference is legible.

    An agent that cannot tell the product from the question about it argues with
    the question — which is the pre-2026-08-04 behaviour with extra text.
    """
    for adapter in adapters:
        adapter.set_topic({"prediction_goal": GOAL, "subject_brief": BRIEF})
        block = adapter.topic_block()

        assert "THE SUBJECT" in block
        assert "WHAT STARTED THE CONVERSATION" in block
        # The subject comes first: it is what is being reacted to.
        assert block.index("THE SUBJECT") < block.index("WHAT STARTED")


def test_every_adapter_captures_the_brief_on_initialize(adapters):
    """One hook, `set_topic(config)`, on all twelve. There is no second path."""
    for adapter in adapters:
        source = inspect.getsource(type(adapter).initialize)
        assert "set_topic(config)" in source, (
            f"{adapter.platform_id}.initialize does not capture the run config"
        )


def test_the_runner_hands_every_arena_the_same_subject():
    """One distillation per run, read before any adapter exists.

    A per-arena brief would make the variant comparison measure two changes at
    once, and a per-round one would mean the run has no single subject.
    """
    from app.workers import simulation_tasks

    source = inspect.getsource(simulation_tasks.run_simulation)
    assert "ensure_subject_brief(sim)" in source
    assert '"subject_brief": subject_brief' in source
    # Resolved once, above the arena loop — not inside it.
    assert source.index("ensure_subject_brief(sim)") < source.index("for arena in arenas")


# ---------------------------------------------------------------------------
# 2. Competitor material can never become the subject
# ---------------------------------------------------------------------------

def test_only_the_founders_own_material_may_describe_the_subject():
    """DECISIONS §7, as a constant rather than a convention.

    The `competitor` label exists to license a competitor's *name* in an
    adversarial agent's mouth. Letting it describe the subject would put a
    competitor's positioning in front of every agent as the founder's own
    product — the inverse of the guardrail, arrived at from the other side.

    `idea_brief` is the founder's own description composed from the guided
    idea form (PRD_V3 §3), so its presence keeps the guarantee this test
    pins: everything in this set is the founder speaking about their own
    product.
    """
    assert sb._SUBJECT_MATERIAL_KINDS == frozenset({"own", "idea_brief"})


def test_competitor_and_market_documents_are_not_subject_material():
    rows = [
        {"id": "d1", "material_kind": "competitor", "processing_status": "complete"},
        {"id": "d2", "material_kind": "market", "processing_status": "complete"},
    ]
    assert sb._subject_material_rows(rows) == []


def test_a_null_material_kind_reads_as_own():
    """NULL predates the column, and `gather_material` reads it as `own` too."""
    rows = [{"id": "d1", "material_kind": None, "processing_status": "complete"}]
    assert [d["id"] for d in sb._subject_material_rows(rows)] == ["d1"]


async def test_competitor_text_never_reaches_the_distillation_prompt(monkeypatch):
    """The whole guardrail, end to end: what was sent to the model.

    `gather_material` buckets on `material_kind`; only `own` is read here. A
    regression that passed `material.competitor` into the prompt would be
    invisible to every other test in this file, because the resulting brief
    would look entirely plausible.
    """
    sent: list[str] = []

    material = ProjectMaterial(
        own="### deck.pdf\nSaibyl is a synthetic audience for founders.",
        competitor="### remesh.pdf\nRemesh runs live conversations with real people.",
        market="### gartner.pdf\nThe insights category is worth a lot.",
        own_ids=["d-own"],
        competitor_ids=["d-comp"],
        market_ids=["d-market"],
    )
    monkeypatch.setattr(
        "app.services.engine.personas.icp_synthesizer.gather_material",
        lambda _pid: material,
    )
    monkeypatch.setattr(sb, "get_supabase_admin", lambda: _Admin())

    async def _fake_llm(messages, **_kwargs):
        sent.append(messages[0]["content"])
        return json.dumps({
            "name": "Saibyl",
            "what_it_is": "A synthetic audience for founders.",
        })

    monkeypatch.setattr(sb, "llm_complete", _fake_llm)

    brief = await sb._build("sim-1", "proj-1", "org-1")

    assert brief.status == sb.STATUS_READY
    assert "Saibyl is a synthetic audience" in sent[0]
    assert "Remesh" not in sent[0]
    assert "Gartner" not in sent[0] and "gartner" not in sent[0]
    # And the provenance names only the documents that were allowed to speak.
    assert brief.source_document_ids == ["d-own"]


# ---------------------------------------------------------------------------
# 3. A run with no material still works, and says so
# ---------------------------------------------------------------------------

def test_a_run_without_a_brief_still_gets_its_subject():
    """An unlensed or document-free run must keep working, unchanged."""
    adapter = _adapter()
    adapter.set_topic({"prediction_goal": GOAL})

    assert adapter.topic_block() == f"The conversation is about: {GOAL}\n\n"


def test_no_goal_and_no_brief_is_still_an_empty_block():
    adapter = _adapter()
    adapter.set_topic({})
    assert adapter.topic_block() == ""
    assert adapter.topic_block(feed_is_empty=True) == ""


def test_the_empty_feed_nudge_survives_the_rewiring():
    """Without it, round one deadlocks at zero events — HANDOFF §5 bug #2."""
    adapter = _adapter()
    adapter.set_topic({"prediction_goal": GOAL, "subject_brief": BRIEF})

    cold = adapter.topic_block(feed_is_empty=True)
    warm = adapter.topic_block(feed_is_empty=False)

    assert "POST" in cold
    assert "POST" not in warm
    assert len(cold) > len(warm)


def test_pre_positioned_assets_survive_the_rewiring():
    """A re-simulation's assets ride in the same block and must still arrive."""
    adapter = _adapter()
    adapter.set_topic({
        "prediction_goal": GOAL,
        "subject_brief": BRIEF,
        "pre_positioned": "The team has published this material...\n\n",
    })

    block = adapter.topic_block()

    assert "THE SUBJECT" in block
    assert "The team has published this material" in block


async def test_a_project_with_no_documents_says_so_and_does_not_degrade_silently(monkeypatch):
    monkeypatch.setattr(sb, "get_supabase_admin", lambda: _Admin({"documents": []}))
    monkeypatch.setattr(
        "app.services.engine.personas.icp_synthesizer.gather_material",
        lambda _pid: ProjectMaterial(),
    )

    with capture_logs() as logs:
        brief = await sb._build("sim-1", "proj-1", "org-1")

    assert brief.status == sb.STATUS_NO_MATERIAL
    assert not brief.present
    assert "no uploaded documents" in brief.reason
    assert "subject_brief_unavailable" in _events(logs)


async def test_uploaded_material_that_never_reaches_the_agents_is_an_error(monkeypatch):
    """The originating defect, in the shape it would take now.

    Documents exist, none of them may describe the subject, and the run proceeds
    on `prediction_goal` alone. That is *not* an ordinary document-free run — a
    founder uploaded something and it did not arrive — so it logs at error and
    the reason names every excluded document by why.
    """
    documents = [
        {"id": "d1", "material_kind": "competitor", "processing_status": "complete"},
        {"id": "d2", "material_kind": "own", "processing_status": "pending"},
        {"id": "d3", "material_kind": "market", "processing_status": "complete"},
    ]
    monkeypatch.setattr(sb, "get_supabase_admin", lambda: _Admin({"documents": documents}))
    monkeypatch.setattr(
        "app.services.engine.personas.icp_synthesizer.gather_material",
        lambda _pid: ProjectMaterial(competitor="rival deck", market="analyst note"),
    )

    with capture_logs() as logs:
        brief = await sb._build("sim-1", "proj-1", "org-1")

    assert brief.status == sb.STATUS_MATERIAL_UNUSABLE
    assert not brief.present

    entry = _entry(logs, "subject_brief_unavailable")
    assert entry["log_level"] == "error"
    assert "competitor material" in entry["reason"]
    assert "pending" in entry["reason"]
    assert "market context" in entry["reason"]


def test_an_unreadable_documents_table_is_not_read_as_an_empty_one(monkeypatch):
    """"We could not look" and "there is nothing there" are opposite facts.

    Reported at error level, because an unreadable table is not evidence that a
    founder uploaded nothing — and this is the branch that decides whether the
    missing subject reads as an ordinary unlensed run or as a defect.
    """
    class _Broken:
        def table(self, _name):
            raise RuntimeError("connection reset by peer")

    monkeypatch.setattr(sb, "get_supabase_admin", lambda: _Broken())

    with capture_logs() as logs:
        reason, uploaded_something = sb._no_material_reason("proj-1")

    assert uploaded_something is True
    assert "could not be read" in reason
    assert "subject_material_lookup_failed" in _events(logs)


async def test_a_failed_distillation_is_recorded_not_swallowed(monkeypatch):
    monkeypatch.setattr(
        "app.services.engine.personas.icp_synthesizer.gather_material",
        lambda _pid: ProjectMaterial(own="a real deck", own_ids=["d1"]),
    )
    monkeypatch.setattr(sb, "get_supabase_admin", lambda: _Admin())

    async def _boom(messages, **_kwargs):
        raise RuntimeError("overloaded_error")

    monkeypatch.setattr(sb, "llm_complete", _boom)

    with capture_logs() as logs:
        brief = await sb._build("sim-1", "proj-1", "org-1")

    assert brief.status == sb.STATUS_DISTILLATION_FAILED
    assert "overloaded_error" in brief.reason
    assert "subject_brief_distillation_failed" in _events(logs)


def test_the_runner_announces_a_run_without_a_subject():
    from app.workers import simulation_tasks

    source = inspect.getsource(simulation_tasks.run_simulation)
    assert "simulation_running_without_subject_brief" in source
    assert "subject_brief_unresolved" in source


# ---------------------------------------------------------------------------
# 4. The quote moves when a brief is present
# ---------------------------------------------------------------------------

def test_a_run_carrying_a_brief_costs_more_than_one_that_does_not():
    without = estimate_simulation_cost(100, 5, 2, 1, "standard")
    with_brief = estimate_simulation_cost(100, 5, 2, 1, "standard", subject_brief=True)

    assert with_brief.actual_cost_usd > without.actual_cost_usd
    assert with_brief.credits > without.credits


def test_the_brief_is_charged_on_every_action_not_once():
    """It rides in `topic_block()`, which is rebuilt per call with no caching.

    Quoting it as a one-off would repeat the mistake the inoculation assets made
    — the largest stage in the run under-charged by a factor, defended by the
    fact that the stage looked already calibrated.
    """
    small = estimate_simulation_cost(25, 3, 2, 1, "standard", subject_brief=True)
    small_without = estimate_simulation_cost(25, 3, 2, 1, "standard")
    big = estimate_simulation_cost(200, 10, 2, 1, "standard", subject_brief=True)
    big_without = estimate_simulation_cost(200, 10, 2, 1, "standard")

    small_delta = small.breakdown["agent_actions"] - small_without.breakdown["agent_actions"]
    big_delta = big.breakdown["agent_actions"] - big_without.breakdown["agent_actions"]

    assert small_delta > 0
    # 75 actions against 2,000: the surcharge scales with the action count.
    assert big_delta > small_delta * 20


def test_the_distillation_is_its_own_stage_charged_once_per_run():
    one = estimate_simulation_cost(100, 5, 2, 1, "standard", subject_brief=True)
    four_variants = estimate_simulation_cost(
        100, 5, 2, 4, "standard", subject_brief=True
    )

    assert one.breakdown["subject_distillation"] > 0
    # Once per run, not once per arena — every arena reads the same brief.
    assert (
        four_variants.breakdown["subject_distillation"]
        == one.breakdown["subject_distillation"]
    )


def test_a_run_without_a_brief_pays_for_no_distillation():
    assert (
        estimate_simulation_cost(100, 5, 2, 1, "standard").breakdown["subject_distillation"]
        == 0.0
    )


def test_a_resimulation_inherits_the_brief_and_pays_no_distillation():
    """It copies its parent's subject rather than building one, so it makes zero
    distillation calls — the same argument as `agent_generation`. It still pays
    the per-action surcharge, because it still sends the brief 480 times."""
    child = estimate_simulation_cost(
        96, 5, 2, 1, "standard", reuse_agents=True, subject_brief=True
    )
    child_without = estimate_simulation_cost(96, 5, 2, 1, "standard", reuse_agents=True)

    assert child.breakdown["subject_distillation"] == 0.0
    assert child.breakdown["agent_actions"] > child_without.breakdown["agent_actions"]


def test_the_brief_surcharge_matches_its_character_budget():
    """The arithmetic in `SUBJECT_BRIEF_ACTION`, checked rather than asserted.

    HANDOFF §2a: a comment stating a fact about cost is a place to look, not a
    reason to stop looking. 1,200 characters at the 3.4 characters per token
    measured on the inoculation asset pair is 353 tokens, and the profile must
    cover it with room for the two header lines `topic_block` wraps it in.
    """
    from_chars = sb.SUBJECT_BRIEF_CHARS / 3.4

    assert SUBJECT_BRIEF_ACTION.input_tokens >= from_chars
    assert SUBJECT_BRIEF_ACTION.input_tokens <= from_chars + 60
    assert SUBJECT_BRIEF_ACTION.output_tokens > 0


def test_the_distillation_profile_covers_the_material_it_is_sent():
    """Its input is a ceiling the code enforces, not a sample.

    `gather_material` caps the `own` bucket, and this stage is sent all of it.
    """
    from app.services.engine.personas.icp_synthesizer import _OWN_MATERIAL_CHARS

    assert SUBJECT_DISTILLATION.input_tokens >= _OWN_MATERIAL_CHARS / 3.4
    # Output is priced at the enforced ceiling, which cannot under-quote.
    assert SUBJECT_DISTILLATION.output_tokens >= sb._DISTIL_MAX_TOKENS


async def test_the_distillation_is_metered_under_its_own_stage(monkeypatch):
    """A stage missing from the ledger is a stage the margin gate cannot see —
    Phase 1's bug #6, where canonicalization was 24% of spend and 0% of quote."""
    from app.services.billing import usage_ledger

    recorded: list[list[dict]] = []

    class _Recorder:
        def table(self, _name):
            return self

        def insert(self, rows):
            recorded.append(list(rows))
            return self

        def execute(self):
            return type("Result", (), {"data": []})()

    monkeypatch.setattr(usage_ledger, "get_supabase_admin", lambda: _Recorder())

    async def _fake_llm(messages, **_kwargs):
        usage_ledger.record_llm_call(
            "claude-opus-4-6", input_tokens=7000, output_tokens=400
        )
        return json.dumps({"name": "Saibyl", "what_it_is": "A synthetic audience."})

    monkeypatch.setattr(sb, "llm_complete", _fake_llm)

    text, _dropped, _model = await sb._distil("sim-1", "org-1", "the deck", set())

    assert "Saibyl" in text
    assert recorded and recorded[0][0]["stage"] == "subject_distillation"
    assert recorded[0][0]["simulation_id"] == "sim-1"


# ---------------------------------------------------------------------------
# The budget is enforced by the code, not requested of the model
# ---------------------------------------------------------------------------

def test_the_rendered_brief_is_bounded_however_long_the_model_writes():
    """`AGENT_ACTION` is the largest stage by call count; an unbounded brief
    multiplies the dominant cost line with nothing failing."""
    fields = {key: "x" * 20_000 for key, _label, _limit in sb._FIELD_LIMITS}

    text, dropped = sb._render(fields, sourced=set())

    assert len(text) <= sb.SUBJECT_BRIEF_CHARS
    assert dropped == []


def test_every_field_survives_a_maximal_brief():
    """The whole-string slice must never be what removes the price line.

    Truncating the rendered brief from the bottom would drop `what it costs`
    first, which silently removes the most objectionable fact in any pitch from
    every run that has a long product description.
    """
    fields = {key: "x" * 20_000 for key, _label, _limit in sb._FIELD_LIMITS}

    text, _dropped = sb._render(fields, sourced=set())

    for _key, label, _limit in sb._FIELD_LIMITS:
        if label:
            assert label in text, f"{label!r} was truncated out of a maximal brief"


def test_the_per_field_caps_fit_inside_the_budget():
    """Stated arithmetic, checked. Otherwise the hard slice is load-bearing and
    silently drops the last field on every long brief."""
    labels = sum(len(label) for _k, label, _l in sb._FIELD_LIMITS)
    caps = sum(limit for _k, _label, limit in sb._FIELD_LIMITS)
    newlines = len(sb._FIELD_LIMITS) - 1

    assert labels + caps + newlines <= sb.SUBJECT_BRIEF_CHARS


# ---------------------------------------------------------------------------
# Grounding: it may only contain what the material says
# ---------------------------------------------------------------------------

def test_a_field_asserting_an_unsourced_number_is_dropped():
    """Both free-writing stages in this codebase invented evidence when
    unconstrained (HANDOFF §5 bug #5, §1b). This one is worse than either,
    because every agent in the run then reacts to the fabrication."""
    fields = {
        "name": "Saibyl",
        "what_it_is": "A synthetic audience.",
        "what_it_claims": "Trusted by 400 founders with 92% accuracy.",
    }

    text, dropped = sb._render(fields, sourced={"400"})

    assert "Saibyl" in text
    assert "92%" not in text
    assert dropped and "what_it_claims" in dropped[0]


def test_a_number_the_material_contains_is_kept():
    fields = {"name": "Saibyl", "what_it_costs": "$99/month."}

    text, dropped = sb._render(fields, sourced={"99"})

    assert "$99/month." in text
    assert dropped == []


def test_a_digit_inside_a_word_is_not_a_fabricated_statistic():
    """Found by rendering a real brief: the bare number regex the asset drafter
    uses matches the 2 in "B2B", and a fully grounded audience line was dropped
    as an invented figure. `S3`, `K8s`, `GPT-4o` and `Web3` are the same shape.
    """
    for token in ("B2B", "S3 buckets", "K8s", "GPT-4o", "Web3", "IPv6"):
        assert sb._unsourced_numbers(f"Built for {token} teams.", set()) == [], token


def test_a_standalone_figure_is_still_caught():
    """The narrowing must not have bought the false negatives back."""
    assert sb._unsourced_numbers("92% accurate across 14 studies.", set()) == ["92%", "14"]
    assert sb._unsourced_numbers("Spearman's rho of 0.74.", set()) == ["0.74"]
    assert sb._unsourced_numbers("Trusted by 400 teams.", set()) == ["400"]


async def test_a_brief_whose_every_field_was_fabricated_is_not_stored_as_ready(monkeypatch):
    monkeypatch.setattr(
        "app.services.engine.personas.icp_synthesizer.gather_material",
        lambda _pid: ProjectMaterial(own="a deck with no figures in it", own_ids=["d1"]),
    )
    monkeypatch.setattr(sb, "get_supabase_admin", lambda: _Admin())

    async def _fake_llm(messages, **_kwargs):
        return json.dumps({
            "name": "Saibyl serving 400 teams",
            "what_it_claims": "92% accurate across 14 studies.",
        })

    monkeypatch.setattr(sb, "llm_complete", _fake_llm)

    with capture_logs() as logs:
        brief = await sb._build("sim-1", "proj-1", "org-1")

    assert brief.status == sb.STATUS_DISTILLATION_FAILED
    assert not brief.present
    assert "subject_brief_fields_dropped" in _events(logs)
    assert "subject_brief_empty" in _events(logs)


def test_the_distillation_prompt_forbids_improving_the_pitch():
    """The prompt rule is the first line; `_unsourced_numbers` is the check.

    Pinned because this is the rule a future edit would soften to get nicer
    output, and nicer output here is a different product than the one uploaded.
    """
    prompt = sb._DISTIL_PROMPT.lower()

    assert "only what the material says" in prompt
    assert "do not improve the pitch" in prompt
    assert "no number that is not in the material" in prompt
    assert "omit any field the material does not state" in prompt


# ---------------------------------------------------------------------------
# One subject per run: persisted, re-read, inherited
# ---------------------------------------------------------------------------

async def test_a_stored_brief_is_re_read_not_regenerated(monkeypatch):
    """A run stopped and restarted must not pay for a second main-model pass and
    hand its agents a different subject than its existing events were produced
    against."""
    stored = {
        "simulation_id": "sim-1",
        "status": sb.STATUS_READY,
        "brief": BRIEF,
        "reason": "",
        "source_document_ids": ["d1"],
        "inherited_from": None,
    }
    monkeypatch.setattr(
        sb, "get_supabase_admin", lambda: _Admin({"subject_briefs": [stored]})
    )

    async def _never(*_a, **_k):
        raise AssertionError("the model must not be called for a stored brief")

    monkeypatch.setattr(sb, "llm_complete", _never)

    with capture_logs() as logs:
        brief = await sb.ensure_subject_brief({"id": "sim-1", "project_id": "p", "organization_id": "o"})

    assert brief.text == BRIEF
    assert "subject_brief_reused" in _events(logs)


def test_a_resimulation_takes_its_parents_subject_verbatim(monkeypatch):
    """The loop's claim is that parent and child differ only in the published
    material. Distilling afresh for the child would change the subject too, and
    every before/after delta would be measuring two changes at once."""
    parent_row = {
        "simulation_id": "parent-1",
        "status": sb.STATUS_READY,
        "brief": BRIEF,
        "reason": "",
        "source_document_ids": ["d1"],
        "inherited_from": None,
    }
    admin = _Admin({"subject_briefs": [parent_row]})
    monkeypatch.setattr(sb, "get_supabase_admin", lambda: admin)

    async def _never(*_a, **_k):
        raise AssertionError("a re-simulation must not distil its own subject")

    monkeypatch.setattr(sb, "llm_complete", _never)

    brief = sb._inherit("child-1", "parent-1", "proj-1", "org-1")

    assert brief.status == sb.STATUS_INHERITED
    assert brief.text == BRIEF
    assert brief.inherited_from == "parent-1"
    assert brief.source_document_ids == ["d1"]


def test_a_child_of_a_briefless_parent_also_runs_without_one(monkeypatch):
    """Worse output and a valid comparison, rather than better output and an
    invalid one."""
    monkeypatch.setattr(sb, "get_supabase_admin", lambda: _Admin({"subject_briefs": []}))

    with capture_logs() as logs:
        brief = sb._inherit("child-1", "parent-1", "proj-1", "org-1")

    assert brief.status == sb.STATUS_INHERITED
    assert not brief.present
    assert "subject_brief_not_inherited" in _events(logs)
    assert "measure two changes at once" in brief.reason


def test_a_failed_lookup_is_not_read_as_no_brief(monkeypatch):
    """None means "distil one", which is a main-model call already paid for.
    A database blip must not be answered with the same value."""
    class _Broken:
        def table(self, _name):
            raise RuntimeError("connection reset by peer")

    monkeypatch.setattr(sb, "get_supabase_admin", lambda: _Broken())

    with pytest.raises(RuntimeError):
        sb.load_subject_brief("sim-1")


# ---------------------------------------------------------------------------
# Quote-time prediction
# ---------------------------------------------------------------------------

def test_a_project_with_own_material_is_quoted_for_a_brief(monkeypatch):
    documents = [{"id": "d1", "material_kind": "own", "processing_status": "complete"}]
    monkeypatch.setattr(sb, "get_supabase_admin", lambda: _Admin({"documents": documents}))

    assert sb.run_will_carry_subject_brief({"id": "s", "project_id": "p"}) is True


def test_a_project_with_only_competitor_material_is_not(monkeypatch):
    documents = [{"id": "d1", "material_kind": "competitor", "processing_status": "complete"}]
    monkeypatch.setattr(sb, "get_supabase_admin", lambda: _Admin({"documents": documents}))

    assert sb.run_will_carry_subject_brief({"id": "s", "project_id": "p"}) is False


def test_a_run_with_no_project_is_not_quoted_for_a_brief():
    assert sb.project_has_subject_material(None) is False


def test_a_resimulation_is_quoted_on_its_parents_brief(monkeypatch):
    parent_row = {
        "simulation_id": "parent-1",
        "status": sb.STATUS_READY,
        "brief": BRIEF,
        "reason": "",
        "source_document_ids": [],
        "inherited_from": None,
    }
    monkeypatch.setattr(
        sb, "get_supabase_admin", lambda: _Admin({"subject_briefs": [parent_row]})
    )

    carried = sb.run_will_carry_subject_brief(
        {"id": "child-1", "project_id": "p", "parent_simulation_id": "parent-1"}
    )
    assert carried is True


# ---------------------------------------------------------------------------
# The migration
# ---------------------------------------------------------------------------

def test_migration_028_keeps_one_subject_per_run():
    """A UNIQUE constraint, not an index: two rows would mean two arenas of one
    run could be handed different subjects."""
    sql = pathlib.Path("scripts/migrations/029_subject_brief.sql").read_text(
        encoding="utf-8"
    )

    assert "CREATE TABLE IF NOT EXISTS subject_briefs" in sql
    assert "simulation_id        UUID NOT NULL UNIQUE" in sql
    assert "NOT APPLIED" in sql
    assert "subject_briefs_org_isolation" in sql


def test_every_status_the_code_writes_is_allowed_by_the_migration():
    """The CHECK constraint and the module's constants are one vocabulary.

    Two definitions of a closed vocabulary is the class that produced the
    event-type allow-list defect; here it would fail every insert at runtime on
    a status nobody tested against the database.
    """
    sql = pathlib.Path("scripts/migrations/029_subject_brief.sql").read_text(
        encoding="utf-8"
    )

    for status in (
        sb.STATUS_READY,
        sb.STATUS_INHERITED,
        sb.STATUS_NO_MATERIAL,
        sb.STATUS_MATERIAL_UNUSABLE,
        sb.STATUS_DISTILLATION_FAILED,
    ):
        assert f"'{status}'" in sql, f"migration 028 rejects status {status!r}"
