# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# draft_assets(simulation_id, org_id, objection_keys=None, ...) -> list[dict]
# create_resimulation(simulation_id, org_id, asset_ids, ...) -> dict
# measure_inoculation(parent_id, child_id, org_id) -> InoculationResult
# asset_prompt_block(asset_rows) -> str
# ─────────────────────────────────────────────────────────
"""Detect → draft → re-simulate → prove (DECISIONS_V2 §4).

Step 3 is the entire product. Detection is Phase 1's canonical objections;
drafting is one main-model call; **the re-simulation is what makes the output
defensible**, and proving is a comparison of two artifacts built by one builder.

Four decisions run through this module.

**The re-simulation is an ordinary simulation with a parent.** It measures,
analyses, reports, prices and reconciles through exactly the same code as any
other run. A bespoke "inoculation run" object would produce a before number and
an after number computed by two different code paths, and those two numbers are
not comparable no matter how carefully they are labelled.

**The audience is copied, never regenerated.** `run_prepare_agents` would put
the same archetypes through the model again and produce different people. The
child's agents are copies of the parent's rows — same usernames, same profiles,
same cohort flags — so the only thing that differs between the two runs is the
material the agents were shown. That is the whole claim.

**Assets are pre-positioned, not posted.** They reach agents through
`topic_block()`, as material published alongside the subject, visible to
everyone from round one. Injecting them as feed posts would model *someone
posted the FAQ in the thread*, which is a different and weaker intervention —
and would depend on which agents happened to see that post.

**Reach is share of agents, and a verdict needs separated intervals.** An
objection voiced ten times by one agent is one agent's objection, and a move
from 34% to 31% is reported as unresolved rather than as progress. The product
is sold on `assets_effective`, so that number has to be one a sceptic would
accept.
"""
from __future__ import annotations

import json
import math
from typing import Any

import structlog

from app.core.database import fetch_all, get_supabase_admin
from app.core.llm_client import _extract_json, llm_complete
from app.services.billing.usage_ledger import usage_context
from app.services.intelligence.analysis_data import load_run_data, mean_interval
from app.services.intelligence.analysis_schema import Interval
from app.services.intelligence.inoculation_schema import (
    ASSET_TYPES,
    InoculationResult,
    ObjectionDelta,
    ObjectionMeasurement,
    Verdict,
)

logger = structlog.get_logger()

# Objections offered to the drafting pass, in load-bearing order. Beyond this
# the tail is single-agent complaints, and an asset written against one agent's
# objection is an asset written against noise.
MAX_OBJECTIONS_TO_DRAFT = 6
# Assets per objection. Two gives the founder a choice of angle; more produces
# variations on one idea at main-model prices.
ASSETS_PER_OBJECTION = 2
_DRAFT_MAX_TOKENS = 6_000

# Characters of an asset body carried into the agent prompt. An asset is
# published material, but a 4,000-character security page in every action prompt
# multiplies the run's largest cost line — and an agent reacting to a page reacts
# to its first paragraph either way.
ASSET_BODY_IN_PROMPT = 700

_Z_95 = 1.96


# ---------------------------------------------------------------------------
# Detect + draft
# ---------------------------------------------------------------------------

def _load_objections(simulation_id: str, keys: list[str] | None) -> list[dict[str, Any]]:
    admin = get_supabase_admin()
    query = (
        admin.table("canonical_objections")
        .select("objection_key, label, summary, quotes, agent_count, event_count, "
                "originating_cohort, cohort_spread, mean_intensity, load_bearing_score")
        .eq("simulation_id", simulation_id)
        .order("load_bearing_score", desc=True)
    )
    rows = query.execute().data or []
    if keys:
        wanted = set(keys)
        rows = [r for r in rows if r["objection_key"] in wanted]
    return rows[:MAX_OBJECTIONS_TO_DRAFT]


def _draft_prompt(
    sim: dict[str, Any],
    objections: list[dict[str, Any]],
    named_competitors: list[str],
) -> str:
    blocks = []
    for objection in objections:
        quotes = objection.get("quotes") or []
        verbatim = "\n".join(
            f'    - "{str(q.get("text", ""))[:240]}"' for q in quotes[:4]
        )
        blocks.append(
            f"""[{objection['objection_key']}] {objection['label']}
  {objection.get('summary') or ''}
  Voiced by {objection.get('agent_count', 0)} agents across \
{objection.get('event_count', 0)} events; originated with \
{objection.get('originating_cohort') or 'an unidentified cohort'}.
  What they actually said:
{verbatim or '    (no verbatim quotes recorded)'}"""
        )

    # The same grounding rule as the adversarial cohort. A comparison page is
    # the one asset type that names a competitor, so it is available only when
    # uploaded material named one — otherwise the model writes a comparison
    # against a company it is imagining.
    if named_competitors:
        competitor_rule = f"""
A "comparison_page" is permitted, and may name: {', '.join(named_competitors)}.
These names came from material the user uploaded. Write only about the switch
itself — migration effort, what is lost, what is gained. Do NOT state any fact
about their product, pricing, roadmap, or customers; you do not know those."""
    else:
        competitor_rule = """
Do NOT use "comparison_page" and do NOT name any company, product, or
open-source project. No competitor material was uploaded, so any name you
produce would be invented. Write about the category and the status quo."""

    return f"""A synthetic audience reacted to this, and these are the objections that
carried the most weight. Draft the material the team should publish BEFORE the
next audience sees it.

SUBJECT: {sim.get('prediction_goal', '')}

OBJECTIONS, most load-bearing first:
{chr(10).join(blocks)}

Draft {ASSETS_PER_OBJECTION} candidate assets per objection. Asset types:
{', '.join(ASSET_TYPES)}
{competitor_rule}

RULES
- An asset is something a team can publish tomorrow. Write the actual copy, not
  advice about what the copy should say. "Address concerns about pricing" is
  not an asset; a pricing rationale page is.
- Answer the objection the agents actually voiced, in their words, not the
  objection you think they should have had. The quotes above are the brief.
- Where the objection is true, the asset says so. A disclosure that concedes a
  real limitation moves an objection; a denial of a true one hardens it.
- "hypothesis" states what you expect this to do, specifically enough to be
  wrong: which cohort stops raising it, and roughly how far it should fall.
  This is recorded before the test runs and judged against the measurement.
- Two assets for the same objection should take genuinely different angles —
  concede versus reframe, roadmap versus rationale — not two phrasings of one.

Return ONLY JSON:
{{"assets": [
  {{"objection_key": "...", "asset_type": "...", "title": "...",
    "body": "the publishable copy, 80-250 words",
    "hypothesis": "what this should do, and to whom"}}
]}}"""


async def draft_assets(
    simulation_id: str,
    org_id: str,
    objection_keys: list[str] | None = None,
    created_by: str | None = None,
) -> list[dict[str, Any]]:
    """Draft counter-assets for a run's load-bearing objections."""
    admin = get_supabase_admin()
    sim = (
        admin.table("simulations")
        .select("id, prediction_goal, icp_profile_id")
        .eq("id", simulation_id)
        .single()
        .execute()
    ).data or {}

    objections = _load_objections(simulation_id, objection_keys)
    if not objections:
        raise ValueError(
            "This run has no canonical objections to write against. Objections "
            "are clustered during analysis — a run that produced none had no "
            "measurable objection to inoculate against."
        )

    from app.services.intelligence.analysis_data import _named_competitors
    named = _named_competitors(sim.get("icp_profile_id"))

    with usage_context(
        "inoculation_draft", simulation_id=simulation_id, organization_id=org_id
    ):
        raw = await llm_complete(
            messages=[{
                "role": "user",
                "content": _draft_prompt(sim, objections, named),
            }],
            max_tokens=_DRAFT_MAX_TOKENS,
            temperature=0.5,
        )

    try:
        data = json.loads(_extract_json(raw))
    except json.JSONDecodeError as exc:
        logger.warning("inoculation_draft_parse_failed", error=str(exc), chars=len(raw))
        raise ValueError(
            "Asset drafting returned output that could not be parsed. Try again "
            "with fewer objections selected."
        ) from exc

    labels = {o["objection_key"]: o["label"] for o in objections}
    rows = []
    for asset in data.get("assets") or []:
        key = str(asset.get("objection_key") or "").strip()
        asset_type = asset.get("asset_type")
        title = str(asset.get("title") or "").strip()
        body = str(asset.get("body") or "").strip()
        if key not in labels or asset_type not in ASSET_TYPES or not title or not body:
            logger.info(
                "inoculation_asset_rejected",
                objection_key=key,
                asset_type=asset_type,
                reason="unknown objection, unknown type, or empty copy",
            )
            continue
        # A comparison page with no grounded competitor cannot exist — the same
        # rule the adversarial cohort enforces, applied to published material,
        # where the consequence is worse: this is copy a founder might ship.
        if asset_type == "comparison_page" and not named:
            logger.warning(
                "inoculation_comparison_page_dropped",
                detail="no competitor grounded in uploaded material",
            )
            continue
        rows.append({
            "simulation_id": simulation_id,
            "organization_id": org_id,
            "objection_key": key,
            "objection_label": labels[key],
            "asset_type": asset_type,
            "title": title[:200],
            "body": body,
            "hypothesis": str(asset.get("hypothesis") or "").strip(),
            "status": "draft",
            "created_by": created_by,
        })

    if not rows:
        raise ValueError("Asset drafting produced nothing usable for these objections.")

    created = admin.table("inoculation_assets").insert(rows).execute().data or []
    logger.info(
        "inoculation_assets_drafted",
        simulation_id=simulation_id,
        objections=len(objections),
        assets=len(created),
    )
    return created


# ---------------------------------------------------------------------------
# Re-simulate
# ---------------------------------------------------------------------------

def asset_prompt_block(asset_rows: list[dict[str, Any]]) -> str:
    """Pre-positioned material, as the agents see it.

    Delivered through `topic_block()` — published alongside the subject and
    visible to every agent from round one — rather than injected as a feed post.
    A feed post models "someone posted the FAQ in the thread", which is a
    different intervention and reaches only the agents whose feed slice included
    it. Pre-positioning is the thing being tested.
    """
    if not asset_rows:
        return ""
    blocks = [
        f"— {row['title']} ({str(row['asset_type']).replace('_', ' ')})\n"
        f"  {str(row['body'])[:ASSET_BODY_IN_PROMPT]}"
        for row in asset_rows
    ]
    return (
        "The team has published this material alongside the subject. It is "
        "available to you and you may have read it:\n"
        + "\n".join(blocks)
        + "\n\n"
    )


def create_resimulation(
    simulation_id: str,
    org_id: str,
    asset_ids: list[str],
    created_by: str | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    """Clone a finished run with assets pre-positioned, agents and all.

    Returns a simulation already in status `ready`: its agents are copies, so
    there is nothing for `run_prepare_agents` to do. That is not an
    optimisation — regenerating would put the same archetypes through the model
    again and produce different people, and the loop's entire claim is that the
    audience did not change.
    """
    admin = get_supabase_admin()
    parent = (
        admin.table("simulations")
        .select("*")
        .eq("id", simulation_id)
        .eq("organization_id", org_id)
        .single()
        .execute()
    ).data
    if not parent:
        raise ValueError("Simulation not found")
    if parent.get("status") != "complete":
        raise ValueError(
            "Only a completed run can be re-simulated. The before/after "
            "comparison needs the parent's measured objections to compare against."
        )

    assets = (
        admin.table("inoculation_assets")
        .select("id")
        .eq("simulation_id", simulation_id)
        .eq("organization_id", org_id)
        .in_("id", asset_ids)
        .execute()
    ).data or []
    found = [a["id"] for a in assets]
    if len(found) != len(set(asset_ids)):
        raise ValueError(
            "One or more assets do not belong to this simulation. An asset can "
            "only be tested against the run whose objections it answers."
        )

    child = (
        admin.table("simulations")
        .insert({
            "name": name or f"{parent['name']} — inoculated",
            "prediction_goal": parent["prediction_goal"],
            "project_id": parent["project_id"],
            "organization_id": org_id,
            # Same shape, so the two runs' agent-rounds match and the swarm is
            # not quietly larger or louder on the second pass.
            "platforms": parent.get("platforms"),
            "max_rounds": parent.get("max_rounds"),
            "agent_count": parent.get("agent_count"),
            "persona_pack_ids": parent.get("persona_pack_ids"),
            "variants": parent.get("variants") or 1,
            "depth": parent.get("depth") or "standard",
            "lens": parent.get("lens"),
            "founder_stage": parent.get("founder_stage"),
            "icp_profile_id": parent.get("icp_profile_id"),
            "adversarial_share": parent.get("adversarial_share") or 0,
            "parent_simulation_id": simulation_id,
            "inoculation_asset_ids": found,
            # Ready, not draft: the agents below are copies and there is nothing
            # to prepare.
            "status": "ready",
            "created_by": created_by,
        })
        .execute()
    ).data[0]

    agents = fetch_all(
        admin.table("simulation_agents")
        .select("entity_id, entity_name, persona_pack_id, variant, platform, "
                "profile, username, is_adversarial, adversarial_role")
        .eq("simulation_id", simulation_id)
        .order("id")
    )
    if not agents:
        raise ValueError("The parent run has no agents to copy.")

    copies = [
        {**agent, "simulation_id": child["id"], "organization_id": org_id}
        for agent in agents
    ]
    for i in range(0, len(copies), 20):
        admin.table("simulation_agents").insert(copies[i:i + 20]).execute()

    admin.table("inoculation_assets").update({"status": "selected"}).in_(
        "id", found
    ).execute()

    logger.info(
        "resimulation_created",
        parent_simulation_id=simulation_id,
        child_simulation_id=child["id"],
        agents_copied=len(copies),
        assets=len(found),
    )
    return child


def load_run_assets(simulation_id: str) -> list[dict[str, Any]]:
    """Assets pre-positioned in this run, or an empty list for an ordinary run."""
    admin = get_supabase_admin()
    sim = (
        admin.table("simulations")
        .select("inoculation_asset_ids")
        .eq("id", simulation_id)
        .single()
        .execute()
    ).data or {}
    ids = sim.get("inoculation_asset_ids") or []
    if not ids:
        return []
    return (
        admin.table("inoculation_assets")
        .select("id, title, asset_type, body, objection_key")
        .in_("id", ids)
        .execute()
    ).data or []


# ---------------------------------------------------------------------------
# Prove
# ---------------------------------------------------------------------------

def _proportion_interval(successes: int, total: int) -> Interval:
    """A share of agents with a 95% interval on the proportion.

    Normal approximation, matching `mean_interval`'s choice for the same reason:
    the difference from an exact method at these n is dwarfed by the classifier's
    own variance, and a constant keeps the band explicable to a customer.

    Zero out of n is not certainty. It reports a band up to the rule-of-three
    bound 3/n, because "no agent raised it in 40" genuinely does not exclude a
    10% true rate — and claiming an objection is dead on that evidence is the
    single most tempting overstatement in this whole loop.
    """
    if total <= 0:
        return Interval(mean=0.0, lower=0.0, upper=0.0, n=0)

    p = successes / total
    if successes == 0:
        return Interval(mean=0.0, lower=0.0, upper=round(min(1.0, 3 / total), 4), n=total)

    half = _Z_95 * math.sqrt(p * (1 - p) / total)
    return Interval(
        mean=round(p, 4),
        lower=round(max(0.0, p - half), 4),
        upper=round(min(1.0, p + half), 4),
        n=total,
    )


def _measure(run, objection_key: str, objection_rows: dict[str, dict]) -> ObjectionMeasurement:
    """One objection's reach in one run, from that run's own agent base."""
    agents_active = len({e.agent_id or e.agent_username for e in run.events})
    row = objection_rows.get(objection_key)
    if row is None:
        return ObjectionMeasurement(
            agents_active=agents_active,
            reach=_proportion_interval(0, agents_active),
        )

    agent_count = int(row.get("agent_count") or 0)
    return ObjectionMeasurement(
        agent_count=agent_count,
        agents_active=agents_active,
        event_count=int(row.get("event_count") or 0),
        mean_intensity=float(row.get("mean_intensity") or 0.0),
        load_bearing_score=float(row.get("load_bearing_score") or 0.0),
        reach=_proportion_interval(agent_count, agents_active),
    )


def _verdict(
    before: ObjectionMeasurement, after: ObjectionMeasurement, significant: bool
) -> Verdict:
    if not before.present and after.present:
        return "emerged"
    if before.present and not after.present:
        # Only called dead when the interval supports it. With 12 active agents
        # the upper bound on "zero observed" is 25%, which is not a dead
        # objection — it is a quiet run.
        return "died" if significant else "unresolved"
    if not significant:
        return "unresolved" if abs(after.reach.mean - before.reach.mean) > 0.01 else "unchanged"
    return "shrank" if after.reach.mean < before.reach.mean else "grew"


def _objection_rows(simulation_id: str) -> dict[str, dict]:
    admin = get_supabase_admin()
    rows = (
        admin.table("canonical_objections")
        .select("objection_key, label, agent_count, event_count, mean_intensity, "
                "load_bearing_score, event_ids")
        .eq("simulation_id", simulation_id)
        .execute()
    ).data or []
    return {r["objection_key"]: r for r in rows}


def _converted_agents(parent_run, child_run, objection_key: str) -> list[str]:
    """Agents who voiced this objection before and not after.

    Matched on username, which is stable across the copy — `create_resimulation`
    copies the rows verbatim, so the same person exists in both runs under the
    same handle with a different id. This is the only place in the codebase where
    username is used as an identity, and it is sound precisely because the copy
    guarantees it: the pairing is by construction, not by hoping handles are
    unique.
    """
    def voices(run) -> set[str]:
        return {
            e.agent_username
            for e in run.events
            if objection_key in _normalised(e.objections)
        }

    return sorted(voices(parent_run) - voices(child_run))[:25]


def _normalised(objections: list[str]) -> set[str]:
    """Raw per-event objection strings, slugged to compare with canonical keys.

    Approximate by design. Raw strings are the classifier's phrasing and
    canonical keys come from the clustering pass, so this matches only the
    objections whose phrasing survived clustering unchanged. It backs the
    "agents who changed their mind" list, which is illustrative; every number in
    the delta comes from `canonical_objections`, not from here.
    """
    out = set()
    for raw in objections or []:
        slug = "-".join(str(raw).lower().split())[:64]
        out.add(slug)
    return out


async def measure_inoculation(
    parent_id: str, child_id: str, org_id: str
) -> InoculationResult:
    """Compare two runs and say, per objection, whether the asset worked."""
    parent_run = load_run_data(parent_id)
    child_run = load_run_data(child_id)

    parent_objections = _objection_rows(parent_id)
    child_objections = _objection_rows(child_id)

    admin = get_supabase_admin()
    child = (
        admin.table("simulations")
        .select("inoculation_asset_ids")
        .eq("id", child_id)
        .single()
        .execute()
    ).data or {}
    asset_ids = child.get("inoculation_asset_ids") or []
    assets = (
        admin.table("inoculation_assets")
        .select("id, title, objection_key")
        .in_("id", asset_ids)
        .execute()
    ).data or [] if asset_ids else []

    assets_by_objection: dict[str, list[dict]] = {}
    for asset in assets:
        assets_by_objection.setdefault(asset["objection_key"], []).append(asset)

    deltas: list[ObjectionDelta] = []
    for key in sorted(set(parent_objections) | set(child_objections)):
        before = _measure(parent_run, key, parent_objections)
        after = _measure(child_run, key, child_objections)

        significant = (
            before.reach.n >= 2
            and after.reach.n >= 2
            and (
                after.reach.upper < before.reach.lower
                or after.reach.lower > before.reach.upper
            )
        )
        targeting = assets_by_objection.get(key, [])
        label = (
            parent_objections.get(key) or child_objections.get(key) or {}
        ).get("label", key)

        deltas.append(
            ObjectionDelta(
                objection_key=key,
                label=label,
                before=before,
                after=after,
                reach_delta_pct=round((after.reach.mean - before.reach.mean) * 100, 2),
                significant=significant,
                verdict=_verdict(before, after, significant),
                asset_ids=[a["id"] for a in targeting],
                asset_titles=[a["title"] for a in targeting],
                converted_agent_usernames=_converted_agents(parent_run, child_run, key)
                if targeting
                else [],
            )
        )

    # Targeted objections first, then by how far they moved. An untargeted
    # objection that shrank is interesting; a targeted one that did not is the
    # finding the founder is paying for.
    deltas.sort(key=lambda d: (not d.asset_ids, -abs(d.reach_delta_pct)))

    headline_before = mean_interval(parent_run.scored_events)
    headline_after = mean_interval(child_run.scored_events)
    headline_significant = (
        headline_before.n >= 2
        and headline_after.n >= 2
        and (
            headline_after.lower > headline_before.upper
            or headline_after.upper < headline_before.lower
        )
    )

    targeted = [d for d in deltas if d.asset_ids]
    result = InoculationResult(
        parent_simulation_id=parent_id,
        child_simulation_id=child_id,
        deltas=deltas,
        headline_before=headline_before,
        headline_after=headline_after,
        headline_delta=round(headline_after.mean - headline_before.mean, 4),
        headline_significant=headline_significant,
        assets_tested=len(asset_ids),
        assets_effective=sum(len(d.asset_ids) for d in targeted if d.effective),
        emerged_objection_keys=[d.objection_key for d in deltas if d.verdict == "emerged"],
        caveats=_caveats(parent_run, child_run, deltas),
    )

    _persist_result(result, org_id)
    if asset_ids:
        admin.table("inoculation_assets").update({"status": "tested"}).in_(
            "id", asset_ids
        ).execute()

    logger.info(
        "inoculation_measured",
        parent_simulation_id=parent_id,
        child_simulation_id=child_id,
        objections=len(deltas),
        assets_tested=result.assets_tested,
        assets_effective=result.assets_effective,
        emerged=len(result.emerged_objection_keys),
    )
    return result


def _caveats(parent_run, child_run, deltas: list[ObjectionDelta]) -> list[str]:
    caveats: list[str] = []

    before_active = len({e.agent_id or e.agent_username for e in parent_run.events})
    after_active = len({e.agent_id or e.agent_username for e in child_run.events})
    if before_active and after_active:
        drift = abs(after_active - before_active) / before_active
        if drift >= 0.15:
            # A quieter second run shrinks every objection's share without any
            # asset doing anything. Reach is a proportion of active agents,
            # which absorbs most of it, but a swing this large is worth saying
            # out loud rather than trusting the denominator to hide.
            caveats.append(
                f"{before_active} agents produced measured events in the original "
                f"run and {after_active} in the re-simulation. Objection reach is "
                "a share of active agents, but a swing this size makes small "
                "movements harder to attribute to the assets."
            )

    unresolved = sum(1 for d in deltas if d.asset_ids and d.verdict == "unresolved")
    if unresolved:
        caveats.append(
            f"{unresolved} targeted objection(s) moved by less than their "
            "confidence bands. That is not evidence the asset worked, and it is "
            "not evidence it failed — it is a swarm too small to resolve the "
            "difference."
        )

    caveats.append(
        "This measures how a synthetic audience reacted to published material, "
        "not what a real audience will do. It is a comparison between two runs "
        "that differ only in that material."
    )
    return caveats


def _persist_result(result: InoculationResult, org_id: str) -> None:
    admin = get_supabase_admin()
    admin.table("inoculation_results").upsert(
        {
            "parent_simulation_id": result.parent_simulation_id,
            "child_simulation_id": result.child_simulation_id,
            "organization_id": org_id,
            "deltas": [d.model_dump(mode="json") for d in result.deltas],
            "headline_before": result.headline_before.model_dump(mode="json"),
            "headline_after": result.headline_after.model_dump(mode="json"),
            "assets_tested": result.assets_tested,
            "assets_effective": result.assets_effective,
        },
        on_conflict="parent_simulation_id,child_simulation_id",
    ).execute()


def get_inoculation_result(child_simulation_id: str) -> dict | None:
    admin = get_supabase_admin()
    rows = (
        admin.table("inoculation_results")
        .select("*")
        .eq("child_simulation_id", child_simulation_id)
        .limit(1)
        .execute()
    ).data or []
    return rows[0] if rows else None
