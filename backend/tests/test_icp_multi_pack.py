"""Segmenting an ICP into several packs must not move the adversarial share.

`simulations.persona_pack_ids` is already a list and `run_prepare_agents`
already loops over it, so emitting several packs is a compile-and-register
change. The hazard is `rebalance_adversarial`: it is applied **per pack** and
normalises a pack containing both cohorts to a total weight of 1.0. A pack with
no adversarial archetype is returned untouched at whatever its raw weights
summed to, and dilutes the cohort by an amount nobody can see.

The accuracy being protected is a selling point, and it is measured: the live
Founder-lens run allocated 30 of 96 agents to the incumbent-aligned cohort
against 30% configured — 31.2%, HANDOFF §1b. These tests assert the same
property holds when the audience is split N ways.
"""
from __future__ import annotations

import pytest
import structlog

from app.services.engine.personas.icp_schema import (
    AdversarialArchetype,
    ICPArchetype,
    ICPProfile,
)
from app.services.engine.personas.icp_synthesizer import (
    compile_pack,
    compile_packs,
    rebalance_adversarial,
)
from app.services.engine.personas.pack_loader import ICP_PACK_PREFIX, PersonaPack
from app.workers.simulation_tasks import apportion

BASE_PACK_ID = f"{ICP_PACK_PREFIX}deadbeef"
PLATFORMS = ["hacker_news"]

# The live Founder-lens run: 30 of 96 agents against 30% configured is 1.25
# percentage points, and that figure is quoted as a product claim. It is a
# property of `run_prepare_agents`' apportionment, not of anything in this
# module. Segmentation is held to it: the tests below compare against the
# single-pack case at the same configuration rather than against a number
# chosen here.
_LIVE_SINGLE_PACK_DEVIATION = 0.0125


def _profile(*, adversarial_count: int = 2) -> ICPProfile:
    """Three buyer archetypes falling in three different segments."""
    return ICPProfile(
        name="Observability buyers",
        product_summary="Tracing for teams already paying for something else.",
        archetypes=[
            ICPArchetype(
                id="platform-lead", label="Platform Lead", weight=0.4,
                role="Platform engineering lead", seniority="director",
                switching_cost="high", evaluation_criteria=["ingest cost"],
                platforms=PLATFORMS,
            ),
            ICPArchetype(
                id="sre", label="SRE", weight=0.35, role="Site reliability engineer",
                seniority="ic", switching_cost="moderate",
                evaluation_criteria=["alert quality"], platforms=PLATFORMS,
            ),
            ICPArchetype(
                id="eng-manager", label="Engineering Manager", weight=0.25,
                role="Engineering manager", seniority="manager",
                switching_cost="prohibitive", evaluation_criteria=["team ramp"],
                platforms=PLATFORMS,
            ),
        ],
        adversarial=[
            AdversarialArchetype(
                id=f"skeptic-{i}", label=f"Skeptic {i}", weight=1.0,
                role="category_skeptic", core_argument="We already have a process.",
                talking_points=["migration cost"], platforms=PLATFORMS,
            )
            for i in range(adversarial_count)
        ],
    )


def _single_segment_profile() -> ICPProfile:
    """Two archetypes that land in the same seniority/switching-cost cell."""
    return ICPProfile(
        name="One segment",
        archetypes=[
            ICPArchetype(id="a", label="A", weight=0.6, role="dev",
                         seniority="ic", switching_cost="low"),
            ICPArchetype(id="b", label="B", weight=0.4, role="dev",
                         seniority="manager", switching_cost="moderate"),
        ],
        adversarial=[
            AdversarialArchetype(id="s", label="Skeptic", role="category_skeptic"),
        ],
    )


def _simulate_agents(
    packs: list[PersonaPack],
    share: float,
    target_agents: int,
    platforms: list[str] | None = None,
) -> tuple[int, int]:
    """Mirror `run_prepare_agents`' allocation and count the cohorts.

    Calls the runner's own `apportion` rather than restating its arithmetic.
    The previous version was a deliberate copy, and it aged into the second
    source of truth §2a warns about: it pinned the old `max(1, round(...))`
    behaviour, so the envelope it measured was a property of the copy as much as
    of the runner. The structure around the call — split across platforms, then
    across archetypes — is all that is reproduced here.
    """
    platforms = platforms or PLATFORMS
    all_archetypes = []
    for pack in packs:
        for archetype in rebalance_adversarial(pack.archetypes, share):
            all_archetypes.append(archetype)

    weights = [a.weight for a in all_archetypes]
    adversarial = 0
    total = 0
    for platform_total in apportion([1.0] * len(platforms), target_agents):
        for archetype, count in zip(all_archetypes, apportion(weights, platform_total)):
            total += count
            if archetype.is_adversarial:
                adversarial += count
    return adversarial, total


# ---------------------------------------------------------------------------
# Segmentation
# ---------------------------------------------------------------------------

def test_a_profile_that_splits_produces_several_packs():
    packs = compile_packs(_profile(), BASE_PACK_ID, PLATFORMS, 0.3)
    assert len(packs) == 3
    assert len({p.id for p in packs}) == 3
    for pack in packs:
        assert pack.id.startswith(BASE_PACK_ID)
        assert PersonaPack.model_validate(pack.model_dump()) == pack


def test_every_buyer_archetype_lands_in_exactly_one_pack():
    packs = compile_packs(_profile(), BASE_PACK_ID, PLATFORMS, 0.3)
    buyers = [a.id for pack in packs for a in pack.archetypes if not a.is_adversarial]
    assert sorted(buyers) == ["eng-manager", "platform-lead", "sre"]


def test_a_profile_that_does_not_split_returns_one_pack(monkeypatch):
    packs = compile_packs(_single_segment_profile(), BASE_PACK_ID, PLATFORMS, 0.3)
    assert len(packs) == 1
    assert packs[0].id == BASE_PACK_ID


def test_not_segmenting_is_reported():
    """"One pack" must be a stated outcome, not an empty result."""
    with structlog.testing.capture_logs() as logs:
        compile_packs(_single_segment_profile(), BASE_PACK_ID, PLATFORMS, 0.3)
    assert any(entry["event"] == "icp_packs_not_segmented" for entry in logs)


def test_compile_pack_still_produces_the_blended_pack():
    """The single-pack path is unchanged — nothing downstream regresses."""
    pack = compile_pack(_profile(), BASE_PACK_ID, PLATFORMS, 0.3)
    assert pack.id == BASE_PACK_ID
    assert len([a for a in pack.archetypes if not a.is_adversarial]) == 3
    assert sum(a.weight for a in pack.archetypes if a.is_adversarial) == pytest.approx(0.3)


# ---------------------------------------------------------------------------
# The adversarial share
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cohort", [1, 2, 3, 4])
def test_no_segment_pack_is_left_without_an_adversarial_cohort(cohort):
    """The invariant the share depends on.

    A pack without adversarial archetypes is skipped by `rebalance_adversarial`,
    keeps un-normalised weights, and silently dilutes the cohort across the run.
    Partitioning the cohort so that some segment gets none is the design this
    forbids.
    """
    packs = compile_packs(
        _profile(adversarial_count=cohort), BASE_PACK_ID, PLATFORMS, 0.3
    )
    counts = [len([a for a in pack.archetypes if a.is_adversarial]) for pack in packs]
    assert all(count > 0 for count in counts), counts
    # Dealt evenly: every pack carries the same number, so packs stay
    # interchangeable in weight.
    assert len(set(counts)) == 1, counts


@pytest.mark.parametrize("cohort", [1, 2, 3, 4])
def test_every_adversarial_archetype_appears_somewhere_in_the_run(cohort):
    """Dealing must not drop a role.

    The five adversarial roles are distinct cohorts, and a run that silently
    contains three of the four the founder configured reports a cohort split it
    did not measure.
    """
    profile = _profile(adversarial_count=cohort)
    packs = compile_packs(profile, BASE_PACK_ID, PLATFORMS, 0.3)

    dealt = {
        a.id.split("--")[0]
        for pack in packs
        for a in pack.archetypes
        if a.is_adversarial
    }
    assert dealt == {a.id for a in profile.adversarial}


@pytest.mark.parametrize("share", [0.1, 0.3, 0.4, 0.5])
def test_adversarial_weight_share_is_exact_across_n_packs(share):
    """Weight-level: the realised share equals the configured one, exactly."""
    packs = compile_packs(_profile(), BASE_PACK_ID, PLATFORMS, share)
    total = sum(a.weight for pack in packs for a in pack.archetypes)
    attackers = sum(
        a.weight for pack in packs for a in pack.archetypes if a.is_adversarial
    )
    assert attackers / total == pytest.approx(share)


def test_the_live_run_shape_reproduces_the_measured_share():
    """96 agents at 30% — the shape HANDOFF §1b measured at 30 of 96.

    Segmented into three packs, the allocation is still 30 of 96. The number
    the product quotes survives the split at the shape it was measured on.
    """
    packs = compile_packs(_profile(), BASE_PACK_ID, PLATFORMS, 0.3)
    adversarial, total = _simulate_agents(packs, 0.3, 96)

    assert (adversarial, total) == (30, 96)
    assert abs(adversarial / total - 0.3) <= _LIVE_SINGLE_PACK_DEVIATION + 1e-9


def test_realised_agent_share_survives_multiple_platforms():
    """The live run was two platforms; allocation runs per platform."""
    share = 0.3
    platforms = ["hacker_news", "reddit"]
    segmented = _simulate_agents(
        compile_packs(_profile(), BASE_PACK_ID, platforms, share),
        share, 96, platforms=platforms,
    )
    assert (
        abs(segmented[0] / segmented[1] - share) <= _LIVE_SINGLE_PACK_DEVIATION + 1e-9
    )


# ---------------------------------------------------------------------------
# The envelope
#
# This section was written against the old apportionment — `max(1, round(weight
# / total * n))` per archetype against a truncating running remainder — which
# could not deliver per-configuration accuracy for *either* design. It was 10
# percentage points out on a 30-agent swarm at a single pack (20% realised
# against 30% configured), and it lost agents outright: 48 requested allocated
# 45. So the only claim it could make was the relative one, that splitting does
# not make things worse.
#
# `run_prepare_agents.apportion` is now largest-remainder, and the relative
# claim is no longer the interesting one. The tests below assert the absolute
# properties it delivers — the allocated total *equals* the requested total, and
# the realised share sits inside a measured envelope — and keep the relative
# claim underneath them, because `compile_packs` can still dilute the cohort by
# how it deals archetypes into packs and that is this module's own defect to
# guard against.
# ---------------------------------------------------------------------------

# Measured against the grid below (180 configurations, single-pack and
# segmented) after the switch to largest-remainder: worst deviation 0.0333 in
# both columns, against 0.1000 single / 0.0778 segmented before it. The bound is
# the measurement plus a hair, not a target chosen for comfort — if a change
# moves it, re-measure with `_envelope()` and move the constant deliberately.
_APPORTIONMENT_ENVELOPE = 0.034

# The four segment cells `_segment_key` can produce.
_CELLS = (
    ("ic", "low"),
    ("manager", "high"),
    ("director", "moderate"),
    ("vp", "prohibitive"),
)


def _grid_profile(buyers: int, adversarial: int) -> ICPProfile:
    """`buyers` archetypes dealt across as many distinct segments as they fill."""
    return ICPProfile(
        name="Grid",
        archetypes=[
            ICPArchetype(
                id=f"buyer-{i}", label=f"Buyer {i}", weight=1.0, role="buyer",
                seniority=_CELLS[i % len(_CELLS)][0],
                switching_cost=_CELLS[i % len(_CELLS)][1],
                platforms=PLATFORMS,
            )
            for i in range(buyers)
        ],
        adversarial=[
            AdversarialArchetype(
                id=f"adv-{i}", label=f"Adversary {i}", weight=1.0,
                role="category_skeptic", platforms=PLATFORMS,
            )
            for i in range(adversarial)
        ],
    )


def _envelope() -> tuple[float, float]:
    """Worst deviation from the configured share: (one pack, segmented)."""
    single_worst = 0.0
    segmented_worst = 0.0
    for buyers in (3, 4, 6):
        for cohort in (2, 3, 4):
            for agents in (30, 48, 96, 150, 200):
                for share in (0.2, 0.3, 0.4, 0.5):
                    profile = _grid_profile(buyers, cohort)
                    one = _simulate_agents(
                        [compile_pack(profile, BASE_PACK_ID, PLATFORMS, share)],
                        share, agents,
                    )
                    many = _simulate_agents(
                        compile_packs(profile, BASE_PACK_ID, PLATFORMS, share),
                        share, agents,
                    )
                    single_worst = max(single_worst, abs(one[0] / one[1] - share))
                    segmented_worst = max(segmented_worst, abs(many[0] / many[1] - share))
    return single_worst, segmented_worst


def test_every_configuration_allocates_exactly_the_agents_requested():
    """The billing invariant, across 180 configurations, split or not.

    Credits are charged at start from the agent count the customer selected
    (HANDOFF §4.3). Under the old apportionment 85 of these 180 configurations
    missed their requested total — 48 requested allocating 45 is the reported
    case — so every one of those runs built a swarm the customer had paid more
    for, and drew every confidence interval across fewer agents than the quote
    implied.
    """
    missed = []
    for buyers in (3, 4, 6):
        for cohort in (2, 3, 4):
            for agents in (30, 48, 96, 150, 200):
                for share in (0.2, 0.3, 0.4, 0.5):
                    profile = _grid_profile(buyers, cohort)
                    for label, packs in (
                        ("one", [compile_pack(profile, BASE_PACK_ID, PLATFORMS, share)]),
                        ("many", compile_packs(profile, BASE_PACK_ID, PLATFORMS, share)),
                    ):
                        _, total = _simulate_agents(packs, share, agents)
                        if total != agents:
                            missed.append((label, buyers, cohort, agents, share, total))

    assert not missed, f"{len(missed)} configurations lost or gained agents: {missed[:5]}"


def test_the_reported_48_agent_case_allocates_48():
    """The regression, pinned at the exact reported shape.

    Three buyers, a four-strong incumbent cohort at 30%, segmented: **45 agents
    where 48 were requested**. Three agents the customer was charged for and did
    not receive, on one run.
    """
    packs = compile_packs(_grid_profile(3, 4), BASE_PACK_ID, PLATFORMS, 0.3)
    adversarial, total = _simulate_agents(packs, 0.3, 48)

    assert total == 48
    assert abs(adversarial / total - 0.3) <= _APPORTIONMENT_ENVELOPE


def test_the_realised_share_stays_inside_the_measured_envelope():
    """Absolute accuracy, not just accuracy relative to the unsegmented case."""
    single_worst, segmented_worst = _envelope()

    assert single_worst <= _APPORTIONMENT_ENVELOPE, single_worst
    assert segmented_worst <= _APPORTIONMENT_ENVELOPE, segmented_worst


def test_segmentation_does_not_widen_the_share_envelope():
    """Kept underneath the absolute claim: `compile_packs` deals archetypes into
    packs, and a bad deal still dilutes the cohort however exact the
    apportionment downstream of it is."""
    single_worst, segmented_worst = _envelope()

    assert segmented_worst <= single_worst + 1e-9, (
        f"segmenting widened the worst-case deviation from {single_worst:.4f} "
        f"to {segmented_worst:.4f}"
    )


def test_copying_the_cohort_into_every_pack_would_widen_the_envelope():
    """Why `compile_packs` deals the cohort instead of copying it.

    Pins the reasoning in the `compile_packs` docstring to an executable
    measurement, so a future change to "just give every pack the whole cohort"
    — which is the more obvious design, and preserves the cohort's internal mix
    exactly — fails here rather than in a founder's report.
    """
    single_worst, dealt_worst = _envelope()

    copied_worst = 0.0
    for buyers in (3, 4, 6):
        for cohort in (2, 3, 4):
            for agents in (30, 48, 96, 150, 200):
                for share in (0.2, 0.3, 0.4, 0.5):
                    profile = _grid_profile(buyers, cohort)
                    packs = compile_packs(profile, BASE_PACK_ID, PLATFORMS, share)
                    # Rebuild each pack with the whole cohort attached.
                    copied = []
                    for pack in packs:
                        buyers_only = [a for a in pack.archetypes if not a.is_adversarial]
                        attackers = [
                            a
                            for a in compile_pack(
                                profile, BASE_PACK_ID, PLATFORMS, share
                            ).archetypes
                            if a.is_adversarial
                        ]
                        copied.append(
                            PersonaPack(
                                id=pack.id, name=pack.name, version="1.0",
                                category="synthesized-icp", description="",
                                archetypes=buyers_only + attackers,
                            )
                        )
                    a, t = _simulate_agents(copied, share, agents)
                    copied_worst = max(copied_worst, abs(a / t - share))

    assert dealt_worst <= single_worst + 1e-9
    assert copied_worst > single_worst, (
        f"copying no longer widens the envelope ({copied_worst:.4f} against "
        f"{single_worst:.4f}); re-measure before simplifying compile_packs"
    )


def test_prepare_time_share_overrides_the_compiled_share_on_every_pack():
    """An ICP is reused across runs; the run's share is the authoritative one."""
    packs = compile_packs(_profile(), BASE_PACK_ID, PLATFORMS, 0.1)
    for pack in packs:
        rebalance_adversarial(pack.archetypes, 0.45)

    total = sum(a.weight for pack in packs for a in pack.archetypes)
    attackers = sum(
        a.weight for pack in packs for a in pack.archetypes if a.is_adversarial
    )
    assert attackers / total == pytest.approx(0.45)


def test_zero_share_leaves_the_cohort_present_and_negligible():
    packs = compile_packs(_profile(), BASE_PACK_ID, PLATFORMS, 0.0)
    for pack in packs:
        attackers = [a for a in pack.archetypes if a.is_adversarial]
        assert attackers
        assert all(a.weight < 0.001 for a in attackers)


def test_packs_carry_equal_swarm_weight_at_every_share():
    """Pack-level normalisation is what preserves the cohort share.

    At share 0 the buyers used to keep their raw weights, so a pack with more
    archetypes took more of the swarm than one with fewer — at that share only.
    """
    for share in (0.0, 0.3):
        packs = compile_packs(_profile(), BASE_PACK_ID, PLATFORMS, share)
        totals = [sum(a.weight for a in pack.archetypes) for pack in packs]
        assert all(t == pytest.approx(totals[0], abs=1e-3) for t in totals), share


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------

def test_replicated_adversarial_archetypes_get_distinct_ids():
    """`run_prepare_agents` builds `entity_id` from the archetype id.

    HANDOFF §1a is the record of what two agents sharing one identity did to
    this codebase: nine agents, one memory, one row of event attribution, and
    confidence intervals drawn from a ninth of the observations.
    """
    packs = compile_packs(_profile(), BASE_PACK_ID, PLATFORMS, 0.3)
    ids = [a.id for pack in packs for a in pack.archetypes]
    assert len(ids) == len(set(ids)), "an archetype id repeats across packs"


def test_a_dealt_adversarial_keeps_its_cohort_and_role():
    """Only the id is suffixed. The cohort is carried on the flag, not the id."""
    packs = compile_packs(_profile(adversarial_count=1), BASE_PACK_ID, PLATFORMS, 0.3)
    for pack in packs:
        attacker = next(a for a in pack.archetypes if a.is_adversarial)
        assert attacker.id.startswith("skeptic-0--")
        assert attacker.adversarial_role == "category_skeptic"
        assert attacker.label == "Skeptic 0"


def test_a_profile_with_no_adversarial_cohort_still_yields_equal_weight_packs():
    """No cohort means `rebalance_adversarial` is a no-op on every pack."""
    profile = _profile()
    profile.adversarial = []

    packs = compile_packs(profile, BASE_PACK_ID, PLATFORMS, 0.3)

    totals = [sum(a.weight for a in pack.archetypes) for pack in packs]
    assert all(total == pytest.approx(1.0) for total in totals), totals


def test_segment_packs_are_ordered_deterministically():
    """Order must not depend on the order the model emitted archetypes in."""
    first = [p.id for p in compile_packs(_profile(), BASE_PACK_ID, PLATFORMS, 0.3)]
    reordered = _profile()
    reordered.archetypes.reverse()
    second = [p.id for p in compile_packs(reordered, BASE_PACK_ID, PLATFORMS, 0.3)]
    assert first == second


def test_an_unrecognised_seniority_is_reported_not_absorbed(monkeypatch):
    """A silent default merges two segments and reports a clean split."""
    from app.services.engine.personas import icp_synthesizer

    profile = _profile()
    # Bypasses the Literal so the runtime path can be exercised, which is what a
    # profile round-tripped through an older schema would look like.
    object.__setattr__(profile.archetypes[0], "seniority", "principal")

    with structlog.testing.capture_logs() as logs:
        icp_synthesizer._segment_key(profile.archetypes[0])

    assert any(
        entry["event"] == "icp_segment_seniority_unrecognised" for entry in logs
    )


def test_a_restated_seniority_still_resolves():
    from app.services.engine.personas import icp_synthesizer

    profile = _profile()
    for form in ("director", "Director", "  director ", "[director]"):
        object.__setattr__(profile.archetypes[0], "seniority", form)
        assert icp_synthesizer._segment_key(profile.archetypes[0])[0] == "decision_maker"
