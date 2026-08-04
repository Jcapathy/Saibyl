"""The load-bearing invariant: the two runs must share objection keys.

Phase 2's worst defect **reported a perfect score**. Parent and child shared
zero canonical objection keys, so every objection read as `died` or `emerged`
and all six assets scored effective — a report of total success from a
comparison that had matched nothing. Nobody investigates a perfect score.

Two things have to hold for the comparison to mean anything, and each of them
failed silently in its own way:

1. A key the model hands back must resolve to its prior **even when the model
   decorated it**, because priors are rendered as ``  {key} — "{label}"`` and a
   value rendered into a prompt comes back dressed the way it was shown. An
   exact-match compare mints a fresh key instead, and the objection reads as one
   dying and an unrelated one appearing.
2. The carry-over health check must fire on a **low ratio**, not only at zero.
   Zero is the catastrophic case and it was already caught. "12 of 46 carried"
   produces the same wrong answer over three quarters of the comparison and used
   to log nothing at all, which made the survivable failure the invisible one.
"""
from __future__ import annotations

import pytest

from app.services.intelligence import objection_canonicalizer as oc
from app.services.intelligence.analysis_data import MeasuredEvent, RunData

_PRIORS = [
    {"key": "price-too-high-for-small-teams", "label": "Price is too high for small teams"},
    {"key": "integration-debt-not-addressed", "label": "Integration debt is not addressed"},
    {"key": "no-proof-it-predicts-real-behavior", "label": "No proof it predicts real behavior"},
    {"key": "security-review-would-block-it", "label": "Security review would block it"},
]


# ---------------------------------------------------------------------------
# Resolving a key the model handed back
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "returned",
    [
        # Exactly as offered.
        "price-too-high-for-small-teams",
        # Wrapped in what it was rendered inside.
        "`price-too-high-for-small-teams`",
        "[price-too-high-for-small-teams]",
        '"price-too-high-for-small-teams"',
        "price-too-high-for-small-teams.",
        # Re-cased, the way a model restates an identifier in prose.
        "Price-Too-High-For-Small-Teams",
        # Whitespace, which is all the old `.strip()` handled.
        "  price-too-high-for-small-teams  ",
        # The label sitting next to the key on the same line — the copy-back the
        # prior block's own formatting invites.
        "Price is too high for small teams",
        'Price is too high for small teams.',
    ],
)
def test_a_decorated_or_labelled_key_still_matches_its_prior(returned):
    """The exact-match compare missed every one of these and minted a new key."""
    index = oc._prior_index(_PRIORS)

    assert oc._resolve_prior_key(returned, index) == "price-too-high-for-small-teams"


def test_a_genuinely_new_objection_does_not_get_forced_onto_a_prior():
    """A new objection with a new key is a real finding, and must stay one.

    Forcing a match would fabricate continuity, which fails in the same
    flattering direction as finding none.
    """
    index = oc._prior_index(_PRIORS)

    assert oc._resolve_prior_key("onboarding-takes-too-long", index) is None
    assert oc._resolve_prior_key("", index) is None
    assert oc._resolve_prior_key(None, index) is None


def test_the_heavier_prior_keeps_a_contested_form():
    """Priors arrive in load-bearing order, so the first one wins."""
    index = oc._prior_index([
        {"key": "heavy", "label": "Same Label"},
        {"key": "light", "label": "Same Label"},
    ])

    assert index[oc.slugify("Same Label")] == "heavy"


def test_key_derivation_has_exactly_one_definition():
    """`objection_canonicalizer` had its own `_slugify`; `inoculation` had a
    third, incompatible one. A verbatim identical objection produced two
    different keys, and one whole feature was always empty because of it."""
    assert not hasattr(oc, "_slugify")


# ---------------------------------------------------------------------------
# The carry-over health check
# ---------------------------------------------------------------------------

def _event(event_id: str, agent: str, objection: str) -> MeasuredEvent:
    return MeasuredEvent(
        id=event_id,
        agent_id=agent,
        agent_username=agent,
        archetype="Buyer",
        platform="hacker_news",
        round_number=1,
        event_type="post",
        content="text",
        valence=-0.5,
        stance="oppose",
        intensity=0.6,
        intent=None,
        is_novel_claim=False,
        objections=[objection],
    )


def _run_of(phrasings: list[str]) -> RunData:
    return RunData(
        simulation_id="child-1",
        organization_id="org-1",
        prediction_goal="goal",
        max_rounds=3,
        events=[
            _event(f"e{i}", f"agent-{i}", phrasing)
            for i, phrasing in enumerate(phrasings)
        ],
        agents_total=len(phrasings),
        parent_simulation_id="parent-1",
    )


async def _canonicalize(monkeypatch, phrasings, groups, priors):
    """Run the real function with only the model call replaced."""
    async def _fake_cluster(goal, raw_index, priors=None):
        return groups

    monkeypatch.setattr(oc, "_cluster", _fake_cluster)
    return await oc.canonicalize_objections(_run_of(phrasings), priors)


def _log(monkeypatch) -> list[tuple[str, str, dict]]:
    captured: list[tuple[str, str, dict]] = []

    class _Logger:
        def __getattr__(self, level):
            def record(event, **kw):
                captured.append((level, event, kw))
            return record

    monkeypatch.setattr(oc, "logger", _Logger())
    return captured


@pytest.mark.asyncio
async def test_a_low_carry_over_ratio_fires_the_health_check(monkeypatch):
    """"12 of 46 carried" is the case nobody sees, and it is the realistic one.

    One of four priors carries here — 0.25, below the floor. The comparison is
    still going to report the other three as `died` and their assets as
    effective, which is the same wrong answer the zero case gave, over three
    quarters of the objections.
    """
    captured = _log(monkeypatch)
    phrasings = ["pricing is steep", "integrations missing", "no evidence", "soc2?"]
    groups = [
        {"label": "Price is too high for small teams", "members": ["pricing is steep"],
         "key": "price-too-high-for-small-teams"},
        {"label": "Nobody owns the rollout", "members": ["integrations missing"]},
        {"label": "Docs are thin", "members": ["no evidence"]},
        {"label": "Onboarding takes too long", "members": ["soc2?"]},
    ]

    await _canonicalize(monkeypatch, phrasings, groups, _PRIORS)

    errors = [c for c in captured if c[0] == "error"]
    assert errors, "a 1-of-4 carry-over logged nothing at all"
    level, event, fields = errors[0]
    assert event == "objection_keys_carried_over_too_few"
    assert fields["keys_carried_over"] == 1
    assert fields["keys_carried_over_ratio"] == 0.25


@pytest.mark.asyncio
async def test_zero_carry_over_still_fires(monkeypatch):
    """The catastrophic case the first live loop hit stays caught."""
    captured = _log(monkeypatch)
    groups = [{"label": "Something else entirely", "members": ["pricing is steep"]}]

    await _canonicalize(monkeypatch, ["pricing is steep"], groups, _PRIORS)

    events = [c[1] for c in captured if c[0] == "error"]
    assert "objection_keys_carried_over_too_few" in events


@pytest.mark.asyncio
async def test_a_healthy_carry_over_is_silent(monkeypatch):
    """27 of 46 — what the repaired live loop produced — is not an error.

    A guard that fires on an ordinary run with genuine churn in its objections
    is a guard that gets ignored.
    """
    captured = _log(monkeypatch)
    phrasings = ["pricing is steep", "integrations missing", "no evidence", "soc2?"]
    groups = [
        {"label": "Price is too high for small teams", "members": ["pricing is steep"],
         "key": "price-too-high-for-small-teams"},
        {"label": "Integration debt is not addressed", "members": ["integrations missing"],
         "key": "integration-debt-not-addressed"},
        {"label": "No proof it predicts real behavior", "members": ["no evidence"],
         "key": "no-proof-it-predicts-real-behavior"},
        {"label": "Onboarding takes too long", "members": ["soc2?"]},
    ]

    await _canonicalize(monkeypatch, phrasings, groups, _PRIORS)

    assert [c for c in captured if c[0] == "error"] == []


@pytest.mark.asyncio
async def test_a_decorated_key_survives_the_whole_pass(monkeypatch):
    """End to end: the model returns the key backticked and the label re-cased.

    Under the exact-match compare both groups minted new keys, the run shared
    zero keys with its parent, and every asset scored effective.
    """
    captured = _log(monkeypatch)
    phrasings = ["pricing is steep", "integrations missing"]
    groups = [
        {"label": "Cost is hard to justify", "members": ["pricing is steep"],
         "key": "`Price-Too-High-For-Small-Teams`"},
        {"label": "Integration work is unowned", "members": ["integrations missing"],
         "key": "Integration debt is not addressed"},
    ]

    summaries = await _canonicalize(monkeypatch, phrasings, groups, _PRIORS)

    assert {o.key for o in summaries} == {
        "price-too-high-for-small-teams",
        "integration-debt-not-addressed",
    }
    info = {c[1]: c[2] for c in captured if c[0] == "info"}
    assert info["objections_canonicalized"]["keys_normalised"] == 2
    assert [c for c in captured if c[0] == "error"] == []


@pytest.mark.asyncio
async def test_two_groups_cannot_claim_the_same_prior(monkeypatch):
    """The second becomes a new objection, which understates carry-over rather
    than double-counting it — and says so."""
    captured = _log(monkeypatch)
    phrasings = ["pricing is steep", "too pricey"]
    groups = [
        {"label": "Cost is hard to justify", "members": ["pricing is steep"],
         "key": "price-too-high-for-small-teams"},
        {"label": "Cost is still hard to justify", "members": ["too pricey"],
         "key": "Price is too high for small teams"},
    ]

    summaries = await _canonicalize(monkeypatch, phrasings, groups, _PRIORS)

    keys = [o.key for o in summaries]
    assert len(keys) == len(set(keys)), "a duplicate key would collapse two objections"
    assert "price-too-high-for-small-teams" in keys
    assert any(c[1] == "objection_prior_key_claimed_twice" for c in captured)


@pytest.mark.asyncio
async def test_an_ordinary_run_with_no_priors_never_fires_the_check(monkeypatch):
    """Carry-over is meaningless without a parent, and must not read as failure."""
    captured = _log(monkeypatch)
    groups = [{"label": "Price is too high", "members": ["pricing is steep"]}]

    await _canonicalize(monkeypatch, ["pricing is steep"], groups, None)

    assert [c for c in captured if c[0] == "error"] == []
