# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# canonicalize_objections(run_data) -> list[ObjectionSummary]
# persist_objections(run_data, objections) -> None
# ─────────────────────────────────────────────────────────
"""Clusters raw per-event objections into canonical ones.

The measurement pass returns objections in each agent's own framing: "too
expensive for a two-person team", "pricing is steep", "can't justify $99 a
month". Those are one objection said three ways. Left unclustered they rank as
three minor complaints and the real one — the objection that actually loses the
deal — never surfaces.

This runs on the main model rather than the fast one. Clustering is a judgment
task where the failure mode is silent: over-merging collapses two distinct
objections into a label that answers neither, and under-merging buries the
signal. It is also cheap — one call over the distinct strings, not per event.

**Ranking is by load-bearing weight, not frequency.** reach x intensity x cohort
spread. The most-repeated objection is usually the most quotable one, not the
one that decides the purchase; an objection voiced once by every cohort with
high intensity outranks one voiced ten times inside a single archetype.

The canonical objection is the object the whole Founder lens is built on, and
Phase 2's inoculation loop diffs it across two runs, which is why the key is
deterministic from the label rather than a random UUID.
"""
from __future__ import annotations

import json
import re
from typing import Any

import structlog

from app.core.database import get_supabase_admin
from app.core.llm_client import _extract_json, llm_complete
from app.services.billing.usage_ledger import usage_context
from app.services.intelligence.analysis_data import MeasuredEvent, RunData
from app.services.intelligence.analysis_schema import (
    ObjectionQuote,
    ObjectionSummary,
    PropagationPoint,
)

logger = structlog.get_logger()

# Distinct raw strings sent to the clusterer, most frequent first. Beyond this
# the tail is single-mention phrasings that add tokens without changing the
# clusters they would join.
MAX_DISTINCT_STRINGS = 800

# Output budget for the clustering call. Members are indices rather than echoed
# strings precisely so this budget scales with group count, not input count.
#
# Was 8,000, sized for "~300 phrasings collapsing into ~60 groups". The first
# live Founder-lens run produced **728** distinct phrasings and consumed exactly
# 8,000 output tokens. It survived only because the JSON object closed before
# the cut and `_extract_json` discards the truncated prose after it — one more
# group and `json.loads` raises and the caller falls back to one canonical
# objection per phrasing, which is the failure this function's docstring
# describes as quiet and total.
#
# The adversarial cohort is what pushed it there: incumbent-aligned agents raise
# objections buyers do not, so a Founder-lens run generates materially more
# distinct phrasings than the Phase 1 standard run's 601 at a comparable event
# count. Doubling the ceiling buys room for that; **batched clustering remains
# the real fix** for very large runs — see MAX_DISTINCT_STRINGS.
CLUSTER_MAX_TOKENS = 16000

# Fraction of the ceiling above which the clustering output is treated as having
# very likely been cut off. Measured as characters rather than tokens because
# `llm_complete` returns text and not usage — approximate, and deliberately so:
# the point is to make a near-miss loud, not to measure it precisely.
_CEILING_WARN_RATIO = 0.9
_CHARS_PER_TOKEN = 3.6

# Verbatim quotes kept per objection. Enough to show the range of framings
# without turning the drill-down into a transcript.
MAX_QUOTES = 5

_PRIOR_BLOCK = """
=== OBJECTIONS FROM THE PREVIOUS RUN OF THIS AUDIENCE ===
The same swarm was simulated before, and produced these canonical objections.
This run is being compared against that one, objection by objection.

{priors}

**If a group you form is the same objection as one above, return that
objection's exact `key`.** Same objection means answering one would answer the
other — the wording will differ, because these are different agents saying it a
second time. This is the whole basis of the comparison: an objection that is
present in both runs must carry the same key in both, or it will read as one
objection dying and an unrelated one appearing.

Only omit `key` when a group is genuinely an objection that does not appear
above. Do not force a match: a new objection with a new key is a real and useful
finding.
=== END PREVIOUS RUN ===
"""

_PROMPT = """These are objections raised about: {goal}

Each line is one distinct phrasing, numbered, with how many times it was raised:

{strings}
{prior_block}
Group them into canonical objections. Two phrasings belong to the same group
only if answering one would answer the other. "Too expensive" and "no annual
discount" are different objections even though both concern price. Conversely
"integration debt not addressed" and "doesn't address integration complexity"
are the same objection said twice — group them.

For each group return:
- "label": 3-8 words naming the objection as the audience would state it, not as
  the company would like it framed. "Price is too high for small teams", not
  "Pricing perception".
- "summary": one sentence on what would have to be true for this objection to go
  away.
- "members": the NUMBERS of the phrasings in this group, e.g. [0, 4, 17].

Every number from 0 to {last_index} must appear in exactly one group. Do not
invent objections that no phrasing supports. Do not merge groups to reach a
target count.

Return JSON: {{"groups": [{{"label": "...", "summary": "...", "members": [0, 1],
"key": "reuse-a-previous-key-or-omit"}}]}}
No commentary."""


def _slugify(label: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
    return slug[:60] or "objection"


def _collect_raw(events: list[MeasuredEvent]) -> dict[str, list[MeasuredEvent]]:
    """Map each distinct raw objection string to the events that raised it."""
    index: dict[str, list[MeasuredEvent]] = {}
    for event in events:
        for raw in event.objections:
            index.setdefault(raw, []).append(event)
    return index


async def _cluster(
    goal: str,
    raw_index: dict[str, list[MeasuredEvent]],
    priors: list[dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Group distinct phrasings. Returns [] on failure.

    Members come back as **indices into the shortlist**, not as echoed strings.
    Echoing was how this silently broke at scale: output size tracked input
    size, so a 100-agent run's ~500 phrasings blew past `max_tokens`, the JSON
    truncated mid-array, `json.loads` raised, and the caller fell back to one
    "canonical objection" per phrasing. A standard run produced 300 objections
    of which 265 had a single event — "integration debt not addressed" and
    "doesn't address integration complexity" sitting in separate rows. The
    Founder lens ranks on these, so the failure was quiet and total.

    Indices cut output by roughly an order of magnitude and make it scale with
    the number of *groups* rather than the number of inputs.
    """
    ranked = sorted(raw_index.items(), key=lambda kv: len(kv[1]), reverse=True)
    shortlist = ranked[:MAX_DISTINCT_STRINGS]
    if len(ranked) > MAX_DISTINCT_STRINGS:
        # No silent caps: say what was dropped rather than letting the tail
        # vanish into a figure that reads as complete.
        logger.warning(
            "objection_shortlist_truncated",
            distinct=len(ranked),
            kept=MAX_DISTINCT_STRINGS,
            dropped=len(ranked) - MAX_DISTINCT_STRINGS,
        )

    lines = "\n".join(
        f'[{i}] "{raw}" ({len(evts)}x)' for i, (raw, evts) in enumerate(shortlist)
    )

    prior_block = ""
    if priors:
        prior_lines = "\n".join(
            f'  {p["key"]} — "{p["label"]}"' for p in priors
        )
        prior_block = _PRIOR_BLOCK.format(priors=prior_lines)

    try:
        response = await llm_complete(
            messages=[
                {
                    "role": "user",
                    "content": _PROMPT.format(
                        goal=goal or "(not specified)",
                        strings=lines,
                        last_index=len(shortlist) - 1,
                        prior_block=prior_block,
                    ),
                }
            ],
            temperature=0.0,
            max_tokens=CLUSTER_MAX_TOKENS,
        )
        # A stage that quietly survives at its own ceiling is a stage that fails
        # on the next run without anyone changing a line of code. That is
        # precisely what happened here: the first live Founder-lens run consumed
        # exactly the budget, parsed by luck, and reported nothing unusual.
        approx_tokens = len(response) / _CHARS_PER_TOKEN
        if approx_tokens >= CLUSTER_MAX_TOKENS * _CEILING_WARN_RATIO:
            logger.warning(
                "objection_clustering_near_ceiling",
                approx_output_tokens=int(approx_tokens),
                ceiling=CLUSTER_MAX_TOKENS,
                distinct=len(shortlist),
                detail=(
                    "clustering output is within 10% of max_tokens. The next "
                    "larger run will truncate and fall back to one objection "
                    "per phrasing. Raise CLUSTER_MAX_TOKENS or batch the "
                    "clustering."
                ),
            )
        parsed = json.loads(_extract_json(response))
    except Exception as exc:
        logger.warning(
            "objection_clustering_failed",
            error=str(exc),
            distinct=len(shortlist),
            note="falling back to one objection per phrasing",
        )
        return []

    groups = parsed.get("groups")
    if not isinstance(groups, list):
        return []

    # Translate indices back to phrasings. Tolerates a model that returns the
    # string anyway, since that is the cheaper mistake to absorb.
    resolved: list[dict[str, Any]] = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        members: list[str] = []
        for ref in group.get("members") or []:
            if isinstance(ref, bool):
                continue
            if isinstance(ref, int) and 0 <= ref < len(shortlist):
                members.append(shortlist[ref][0])
            elif isinstance(ref, str):
                if ref in raw_index:
                    members.append(ref)
                elif ref.strip().isdigit():
                    idx = int(ref.strip())
                    if 0 <= idx < len(shortlist):
                        members.append(shortlist[idx][0])
        if members:
            resolved.append({**group, "members": members})

    # A model that grouped almost nothing has not clustered; it has relabelled.
    # Better to know than to publish 300 "canonical" objections.
    if resolved and len(resolved) > len(shortlist) * 0.8:
        logger.warning(
            "objection_clustering_ineffective",
            groups=len(resolved),
            distinct=len(shortlist),
            note="model produced roughly one group per phrasing",
        )
    return resolved


def _fallback_groups(raw_index: dict[str, list[MeasuredEvent]]) -> list[dict[str, Any]]:
    """One group per distinct phrasing, used when clustering fails.

    Unclustered objections are worse than clustered ones but they are still
    measured from real agent content. Fabricating clusters would not be.
    """
    ranked = sorted(raw_index.items(), key=lambda kv: len(kv[1]), reverse=True)
    return [
        {"label": raw[:80], "summary": "", "members": [raw]}
        for raw, _ in ranked[:MAX_DISTINCT_STRINGS]
    ]


def _score(
    agent_count: int,
    active_agents: int,
    intensity: float,
    cohorts_hit: int,
    cohorts_total: int,
) -> float:
    """Load-bearing weight: reach x intensity x cohort spread, on 0-100.

    All three factors are shares, so the product is a share too — an objection
    scoring 25 is one that roughly a quarter of the swarm holds, holds firmly,
    and holds across cohorts. Any factor near zero collapses the score, which is
    the intended behaviour: a fiercely-held objection confined to one archetype
    is a niche complaint, and a widely-shrugged-at one is not an obstacle.
    """
    if active_agents <= 0 or cohorts_total <= 0:
        return 0.0
    reach = min(1.0, agent_count / active_agents)
    spread = min(1.0, cohorts_hit / cohorts_total)
    return round(reach * max(intensity, 0.0) * spread * 100, 2)


def _build_summary(
    key: str,
    label: str,
    summary: str,
    events: list[MeasuredEvent],
    run: RunData,
    active_agents: int,
    archetype_totals: dict[str, int],
) -> ObjectionSummary:
    agent_ids = {e.agent_id or e.agent_username for e in events}
    rounds = sorted({e.round_number for e in events})

    per_round: dict[int, list[MeasuredEvent]] = {}
    for event in events:
        per_round.setdefault(event.round_number, []).append(event)

    propagation = [
        PropagationPoint(
            round_number=rnd,
            event_count=len(evts),
            agent_count=len({e.agent_id or e.agent_username for e in evts}),
        )
        for rnd, evts in sorted(per_round.items())
    ]

    # Share of each archetype's agents voicing this, not share of the objection
    # made up by each archetype. The first answers "has this reached the buyers
    # yet"; the second only says which cohort is loudest.
    cohort_agents: dict[str, set[str]] = {}
    for event in events:
        cohort_agents.setdefault(event.archetype, set()).add(
            event.agent_id or event.agent_username
        )
    cohort_spread = {
        archetype: round(len(ids) / archetype_totals[archetype], 4)
        for archetype, ids in cohort_agents.items()
        if archetype_totals.get(archetype)
    }

    # The cohort that raised it first, tie-broken by how much of that cohort
    # holds it — this is the "who started it" line in the Founder report.
    first_round = rounds[0] if rounds else None
    originating = None
    if first_round is not None:
        first_round_cohorts = {
            e.archetype for e in per_round.get(first_round, [])
        }
        if first_round_cohorts:
            originating = max(
                first_round_cohorts, key=lambda a: cohort_spread.get(a, 0.0)
            )

    intensities = [e.intensity for e in events if e.intensity is not None]
    mean_int = round(sum(intensities) / len(intensities), 4) if intensities else 0.0

    # Strongest-felt first: the quote a founder should read is the one that
    # states the objection most forcefully, not the earliest one logged.
    quoted = sorted(events, key=lambda e: (e.intensity or 0.0), reverse=True)
    quotes = [
        ObjectionQuote(
            event_id=e.id,
            agent_username=e.agent_username,
            archetype=e.archetype,
            platform=e.platform,
            round_number=e.round_number,
            text=e.content[:400],
        )
        for e in quoted[:MAX_QUOTES]
        if e.content
    ]

    return ObjectionSummary(
        key=key,
        label=label,
        summary=summary,
        quotes=quotes,
        event_ids=[e.id for e in events],
        agent_count=len(agent_ids),
        event_count=len(events),
        first_round_seen=first_round,
        originating_cohort=originating,
        cohort_spread=cohort_spread,
        propagation=propagation,
        mean_intensity=mean_int,
        load_bearing_score=_score(
            agent_count=len(agent_ids),
            active_agents=active_agents,
            intensity=mean_int,
            cohorts_hit=len(cohort_agents),
            cohorts_total=len(archetype_totals) or 1,
        ),
    )


def prior_objections(simulation_id: str | None) -> list[dict[str, str]]:
    """The parent run's canonical objections, as (key, label) pairs.

    Empty for an ordinary run. Passed into clustering so a re-simulation can
    reuse the parent's keys — see `canonicalize_objections`.
    """
    if not simulation_id:
        return []
    try:
        rows = (
            get_supabase_admin()
            .table("canonical_objections")
            .select("objection_key, label")
            .eq("simulation_id", simulation_id)
            .order("load_bearing_score", desc=True)
            .execute()
        ).data or []
    except Exception:
        logger.exception("prior_objections_lookup_failed", simulation_id=simulation_id)
        return []
    return [{"key": r["objection_key"], "label": r["label"]} for r in rows]


async def canonicalize_objections(
    run: RunData, priors: list[dict[str, str]] | None = None
) -> list[ObjectionSummary]:
    """Cluster a run's raw objections and rank them by load-bearing weight.

    `priors` carries the parent run's canonical objections when this run is an
    inoculation re-simulation. **Without them the whole loop is meaningless**,
    and it fails in the most flattering possible direction.

    Clustering labels are generated per run. The first live loop produced 46
    canonical objections in the parent and 39 in the child with **zero keys in
    common**, because the same objection was named differently the second time.
    Every parent objection therefore read as `died`, every child objection as
    `emerged`, and all six tested assets scored as effective — a report of total
    success from a comparison that had matched nothing. Migration 021 asserts
    the key is "stable and deterministic from the label"; the key is, but the
    label is not, and that distinction is the entire defect.
    """
    raw_index = _collect_raw(run.events)
    if not raw_index:
        logger.info("no_objections_raised", simulation_id=run.simulation_id)
        return []

    prior_keys = {p["key"] for p in (priors or [])}

    with usage_context(
        "objection_canonicalization",
        simulation_id=run.simulation_id,
        organization_id=run.organization_id,
    ):
        groups = await _cluster(run.prediction_goal, raw_index, priors)

    if not groups:
        groups = _fallback_groups(raw_index)

    # Denominators. Active agents rather than agents generated: an agent that
    # never posted cannot have declined to raise an objection.
    active_agents = len({e.agent_id or e.agent_username for e in run.events}) or 1
    agents_by_archetype: dict[str, set[str]] = {}
    for event in run.events:
        agents_by_archetype.setdefault(event.archetype, set()).add(
            event.agent_id or event.agent_username
        )
    archetype_totals = {k: len(v) for k, v in agents_by_archetype.items()}

    summaries: list[ObjectionSummary] = []
    seen_keys: set[str] = set()
    claimed: set[str] = set()

    for group in groups:
        if not isinstance(group, dict):
            continue
        label = str(group.get("label") or "").strip()
        members = group.get("members")
        if not label or not isinstance(members, list):
            continue

        events: list[MeasuredEvent] = []
        for member in members:
            if not isinstance(member, str):
                continue
            # A model that echoes a phrasing into two groups would otherwise
            # double-count its events across both.
            if member in claimed:
                continue
            matched = raw_index.get(member)
            if matched:
                claimed.add(member)
                events.extend(matched)
        if not events:
            continue

        # De-duplicate: one event raising two phrasings of the same canonical
        # objection is one occurrence, not two.
        unique: dict[str, MeasuredEvent] = {e.id: e for e in events}

        # A key carried over from the previous run, when this objection is the
        # same one said again. Everything the inoculation loop reports depends
        # on this: the two runs' objections are lined up by key, so an objection
        # present in both must carry one key across both or it reads as one
        # dying and an unrelated one appearing.
        reused = str(group.get("key") or "").strip()
        if reused and reused in prior_keys and reused not in seen_keys:
            key = reused
        else:
            if reused and reused not in prior_keys:
                # The model invented a key rather than reusing one. Slugging the
                # label instead keeps key derivation in one place.
                logger.info(
                    "objection_key_not_from_priors", proposed=reused[:60], label=label[:60]
                )
            key = _slugify(label)
            suffix = 2
            while key in seen_keys:
                key = f"{_slugify(label)}-{suffix}"
                suffix += 1
        seen_keys.add(key)

        summaries.append(
            _build_summary(
                key=key,
                label=label,
                summary=str(group.get("summary") or "").strip(),
                events=list(unique.values()),
                run=run,
                active_agents=active_agents,
                archetype_totals=archetype_totals,
            )
        )

    summaries.sort(key=lambda o: o.load_bearing_score, reverse=True)

    carried = len({o.key for o in summaries} & prior_keys)
    if priors and not carried:
        # The comparison has nothing to compare. Every prior objection will read
        # as `died` and every new one as `emerged`, and every tested asset will
        # score effective — a report of total success from a matched set of
        # size zero. Loud, because the output looks like the best possible
        # result rather than like a failure.
        logger.error(
            "objection_keys_share_nothing_with_parent",
            simulation_id=run.simulation_id,
            priors=len(priors),
            canonical=len(summaries),
            detail=(
                "no canonical objection reused a key from the parent run. The "
                "before/after comparison will report every objection as died or "
                "emerged and every asset as effective. Treat the delta as invalid."
            ),
        )

    logger.info(
        "objections_canonicalized",
        simulation_id=run.simulation_id,
        distinct_raw=len(raw_index),
        canonical=len(summaries),
        unassigned=len(set(raw_index) - claimed),
        priors_offered=len(prior_keys),
        keys_carried_over=carried,
    )
    return summaries


def persist_objections(run: RunData, objections: list[ObjectionSummary]) -> None:
    """Replace this run's canonical objections with a freshly built set.

    A rebuild is a full replacement rather than an upsert: labels and clusters
    can change between builds, and leaving orphaned rows behind would make the
    objection table disagree with the artifact rendered from the same build.
    """
    admin = get_supabase_admin()
    admin.table("canonical_objections").delete().eq(
        "simulation_id", run.simulation_id
    ).execute()

    if not objections:
        return

    rows = [
        {
            "simulation_id": run.simulation_id,
            "organization_id": run.organization_id,
            "objection_key": o.key,
            "label": o.label,
            "summary": o.summary,
            "quotes": [q.model_dump() for q in o.quotes],
            "event_ids": o.event_ids,
            "agent_count": o.agent_count,
            "event_count": o.event_count,
            "first_round_seen": o.first_round_seen,
            "originating_cohort": o.originating_cohort,
            "cohort_spread": o.cohort_spread,
            "propagation": [p.model_dump() for p in o.propagation],
            "mean_intensity": o.mean_intensity,
            "load_bearing_score": o.load_bearing_score,
        }
        for o in objections
    ]
    for i in range(0, len(rows), 20):
        admin.table("canonical_objections").insert(rows[i : i + 20]).execute()
