#!/usr/bin/env python
"""Phase 3 gate — a live multi-variant run against production.

Run this in-process rather than through the deployed API: `master` is what is
deployed, and `master` has none of this. It calls the same worker entry points
the API calls, against the production Supabase, so what it exercises is the real
pipeline and not a harness that resembles it.

    cd backend && python scripts/live_run_marketing.py --dry-run   # price only
    cd backend && python scripts/live_run_marketing.py             # spends money

**Deliberately underpowered.** Three variants at ~27 agents over 3 rounds, which
is roughly 13 agents per arena per platform. That is not enough to separate three
similar messages, and that is the point: the single most important behaviour in
the Marketing lens is `winner_variant_key` coming back None when the intervals
overlap, and a big clean run would very likely produce a winner and leave the
refusal path proved only by unit tests. If this run *does* separate them, that is
also a real result — but the refusal is what is being bought.

What to check afterwards is in `--verify`, and the checks are written to be able
to fail. A run that reports everything as fine is the thing Phase 2 taught us to
disbelieve.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Quote signing falls back to an empty key in development (HANDOFF §8 item 11).
# Set before anything imports settings.
os.environ.setdefault("SECRET_KEY", "phase3-live-run-" + "x" * 32)

from app.core.database import get_supabase_admin  # noqa: E402
from app.services.billing.agent_pricing import (  # noqa: E402
    estimate_simulation_cost,
)

# The org and project Phase 2 verified against — Saido Labs' own material, which
# is also a fair subject for a marketing test of Saibyl itself.
ORG_ID = "231b7f17-d17c-4f6e-b530-f0196acd841b"
PROJECT_ID = "7a82f3cd-2310-490f-82e5-8e5e9e139ed0"
# `simulations.created_by` is NOT NULL. The API always has a user; a script does
# not, and the insert fails before anything is spent — which is the safe
# direction, but only once you know why.
CREATED_BY = "31114d04-b57c-4024-a11b-7352fc8c0cfc"  # Saido Labs owner

AGENTS = 27
ROUNDS = 3
PLATFORMS = ["reddit", "twitter_x"]
OBJECTIVE = "signup"

# Three genuinely different pitches for the same product, not three rewordings.
# Rewordings would be the easier test to pass and the less useful one: the
# scoreboard's job is to tell a marketer which *argument* lands, and three
# variants of one argument would separate on noise if they separated at all.
VARIANTS = [
    (
        "Proof-led",
        "Test your launch on 100 synthetic buyers before you ship it. Every "
        "number in the report drills down to the agent quote that produced it — "
        "no invented percentages, no vibes. Start free.",
    ),
    (
        "Fear-led",
        "The objection that kills your deal is one you have never heard, because "
        "the people who hold it never replied to your email. Saibyl surfaces it "
        "before launch, then proves whether your answer works. Start free.",
    ),
    (
        "Speed-led",
        "Audience research in nine minutes, not six weeks. Upload your deck, pick "
        "your market, and read what 100 buyers say about it this afternoon. "
        "Start free.",
    ),
]

# ── The A/A/A negative control ──────────────────────────────────────────────
#
# `--null-control` replaces the three arguments with the SAME copy three times.
# Any separation the scoreboard then reports is separation it invented, because
# there is nothing to find: identical copy, one shared swarm, three arenas.
#
# This is the number that decides whether the refusal rule can be trusted. The
# bootstrap in `calibrate_marketing.py` estimates a 0.0% false-positive rate by
# permutation; this measures it once, for real, on the live pipeline — prompts,
# adapters, measurement, clustering and all. A simulated rate is an argument; a
# measured one is evidence.
#
# **The pass condition inverts.** On the ordinary gate run a named winner is a
# note to go and look. Here a named winner is a FAILURE, full stop: the product
# would have told a founder to spend money on a difference that does not exist.
NULL_CONTROL_COPY = VARIANTS[0][1]
NULL_CONTROL_VARIANTS = [
    ("Control A", NULL_CONTROL_COPY),
    ("Control B", NULL_CONTROL_COPY),
    ("Control C", NULL_CONTROL_COPY),
]

# Set by main() before anything reads VARIANTS. Module-level so the existing
# helpers keep working unchanged rather than growing a parameter each.
NULL_CONTROL = False

PREDICTION_GOAL = (
    "How will early-stage founders and marketers react to Saibyl, a swarm "
    "simulation tool that tests launch messaging on synthetic buyers?"
)


def price() -> None:
    est = estimate_simulation_cost(
        AGENTS, ROUNDS, platforms=len(PLATFORMS), variants=len(VARIANTS)
    )
    single = estimate_simulation_cost(AGENTS, ROUNDS, platforms=len(PLATFORMS))
    print("\n── What this run costs ─────────────────────────────")
    print(f"  shape            {AGENTS} agents / {ROUNDS} rounds / "
          f"{len(PLATFORMS)} platforms / {len(VARIANTS)} variants")
    print(f"  objective        {OBJECTIVE}")
    print(f"  COGS             ${est.actual_cost_usd:.2f}")
    print(f"  credits          {est.credits:,}")
    print(f"  vs 1 variant     ${single.actual_cost_usd:.2f} "
          f"({est.actual_cost_usd / single.actual_cost_usd:.1f}x)")
    print(f"  standard runs    {est.standard_run_equivalents}")
    for stage, cost in est.breakdown.items():
        print(f"    {stage:<28} ${cost:.3f}")
    print()
    print("  Agents per arena per platform: "
          f"~{AGENTS // (len(PLATFORMS) * 1)} — deliberately underpowered, so the")
    print("  overlap refusal has a real chance to fire.")
    print()


def create() -> str:
    """Create the simulation and its variants. Returns the simulation id."""
    admin = get_supabase_admin()

    sim = (
        admin.table("simulations")
        .insert({
            "name": ("Marketing lens — A/A/A null control (identical copy)"
                     if NULL_CONTROL
                     else "Phase 3 — matched-swarm gate (3 variants)"),
            "prediction_goal": PREDICTION_GOAL,
            "project_id": PROJECT_ID,
            "organization_id": ORG_ID,
            "platforms": PLATFORMS,
            "max_rounds": ROUNDS,
            "agent_count": AGENTS,
            # Both are real built-in packs — checked against `list_available_packs()`
            # before this ran. A pack id that does not exist fails at prepare,
            # after the run has already been created.
            "persona_pack_ids": ["saas-buyer-smb", "enterprise-it-buyer"],
            "variants": len(VARIANTS),
            "depth": "standard",
            "lens": "marketing",
            "objective": OBJECTIVE,
            "status": "draft",
            "created_by": CREATED_BY,
        })
        .execute()
    ).data[0]
    sim_id = sim["id"]

    admin.table("simulation_variants").insert([
        {
            "simulation_id": sim_id,
            "organization_id": ORG_ID,
            "variant_key": "abc"[i],
            "label": label,
            "content": content,
            "position": i,
        }
        for i, (label, content) in enumerate(VARIANTS)
    ]).execute()

    print(f"  simulation  {sim_id}")
    print(f"  variants    {', '.join(label for label, _ in VARIANTS)}")
    return sim_id


async def execute(sim_id: str) -> None:
    from app.workers.simulation_tasks import run_prepare_agents, run_simulation

    print("\n── Preparing agents (one shared swarm) ─────────────")
    await run_prepare_agents(sim_id)

    print("\n── Running every arena ─────────────────────────────")
    result = await run_simulation(sim_id)
    print(f"  status {result.get('status')} · events {result.get('total_events')}")


def verify(sim_id: str) -> int:
    """Check what a green test suite cannot. Returns an exit code.

    Every check below is written so it can fail. Phase 2's worst defect reported
    a perfect score, and the reason it was caught is that a perfect score was
    treated as suspicious rather than as success.
    """
    admin = get_supabase_admin()
    failures: list[str] = []
    notes: list[str] = []

    events = (
        admin.table("simulation_events")
        .select("id, variant, agent_id, target_event_id, event_type, takeaway")
        .eq("simulation_id", sim_id)
        .execute()
    ).data or []

    print("\n── Verification ────────────────────────────────────")

    # 1. Every arena ran.
    by_variant: dict[str, int] = {}
    for e in events:
        by_variant[e.get("variant") or "?"] = by_variant.get(e.get("variant") or "?", 0) + 1
    print(f"  events by arena       {by_variant}")
    missing = {"a", "b", "c"} - set(by_variant)
    if missing:
        failures.append(f"arenas produced no events at all: {sorted(missing)}")

    # 2. The arenas are genuinely separate conversations. If one adapter were
    #    shared, agents would be acting once rather than once per arena, and the
    #    per-arena event counts would be a third of what they should be.
    agents = (
        admin.table("simulation_agents").select("id")
        .eq("simulation_id", sim_id).execute()
    ).data or []
    expected = len(agents) * ROUNDS
    total = len(events)
    print(f"  agents                {len(agents)}")
    print(f"  events                {total} (ceiling {expected} = agents x rounds x arenas"
          f" is {len(agents) * ROUNDS * len(VARIANTS)})")
    if total <= expected:
        failures.append(
            f"{total} events for {len(agents)} agents over {ROUNDS} rounds and "
            f"{len(VARIANTS)} arenas — that is at most one arena's worth. The "
            f"arenas are probably not running separately."
        )

    # 3. The event graph resolved.
    linked = sum(1 for e in events if e.get("target_event_id"))
    replies = sum(1 for e in events if e.get("event_type") in ("comment", "react"))
    print(f"  replies               {replies}")
    print(f"  linked to a parent    {linked}")
    if replies and not linked:
        failures.append(
            "replies exist but none resolved to a parent — the event graph is "
            "not being written, and cascade branching will read as zero"
        )
    elif replies:
        notes.append(f"{linked}/{replies} replies linked ({linked / replies:.0%})")

    # 4. Takeaway is being measured.
    with_takeaway = sum(1 for e in events if e.get("takeaway"))
    print(f"  takeaways captured    {with_takeaway}/{total}")
    if total and not with_takeaway:
        failures.append("no event carries a takeaway — restatement rate and "
                        "takeaway accuracy will both read as unmeasured")

    # 5. The scoreboard exists and says something honest.
    artifact = (
        admin.table("simulation_analysis")
        .select("artifact").eq("simulation_id", sim_id)
        .order("created_at", desc=True).limit(1).execute()
    ).data
    board = ((artifact or [{}])[0].get("artifact") or {}).get("scoreboard")
    if not board:
        failures.append("no scoreboard in the artifact for a 3-variant run")
    else:
        print(f"\n  objective             {board.get('objective')}")
        print(f"  winner                {board.get('winner_variant_key') or 'NONE (bands overlap)'}")
        print(f"  verdict               {board.get('verdict', '')[:120]}")
        for v in board.get("variants", []):
            rate = v.get("objective_rate") or {}
            vir = v.get("virality") or {}
            score = vir.get("score")
            print(
                f"    {(v.get('label') or v.get('variant_key')):<12} "
                f"{rate.get('mean', 0):>6.1%} "
                f"[{rate.get('lower', 0):.1%}–{rate.get('upper', 0):.1%}] n={rate.get('n', 0):<3} "
                f"virality {'—' if score is None else f'{score:.0f}'} "
                f"({vir.get('components_used', 0)}/{vir.get('components_total', 6)} components)"
            )
        if len(board.get("variants", [])) != len(VARIANTS):
            failures.append(
                f"scoreboard has {len(board.get('variants', []))} rows for "
                f"{len(VARIANTS)} configured variants"
            )
        if NULL_CONTROL:
            # Identical copy in every arena. There is nothing to find, so a
            # named winner is a false positive on the live pipeline — the
            # product telling a founder to act on noise.
            if board.get("winner_variant_key"):
                failures.append(
                    "A/A/A CONTROL NAMED A WINNER. Identical copy in all three "
                    "arenas, so this is a false positive in the shipped refusal "
                    "rule. Do not adopt the paired estimator on top of this — "
                    "fix the rule first."
                )
            else:
                notes.append(
                    "A/A/A control correctly refused to name a winner. That is "
                    "the false-positive rate measured rather than simulated."
                )
            rates = [
                (v.get("objective_rate") or {}).get("mean", 0.0)
                for v in board.get("variants", [])
            ]
            if rates:
                spread = max(rates) - min(rates)
                notes.append(
                    f"Null-control spread between identical arenas: {spread:.1%}. "
                    "Any real difference smaller than this is inside the noise "
                    "floor of a run this size."
                )
        # Disbelieve a clean result. Not a failure — a prompt to look.
        elif board.get("winner_variant_key"):
            notes.append(
                "A winner WAS named on a deliberately underpowered run. Check the "
                "intervals above actually separate before believing it."
            )

    # 6. Cost reconciliation — the margin gate.
    # The parameter is `sim_uuid`, not `sim_id`. Migration 017 named it that and
    # nothing else calls it, so the mismatch surfaced only here.
    # Summed here rather than through `simulation_llm_cost`, whose shape through
    # PostgREST is per-stage rows and whose parameter is `sim_uuid` — two
    # surprises in one call, in a script whose whole job is to be believed.
    ledger = (
        admin.table("llm_usage")
        .select("cost_usd")
        .eq("simulation_id", sim_id)
        .execute()
    ).data or []
    cost = sum(float(r.get("cost_usd") or 0) for r in ledger)
    quoted = estimate_simulation_cost(
        AGENTS, ROUNDS, platforms=len(PLATFORMS), variants=len(VARIANTS)
    ).actual_cost_usd
    print(f"\n  measured COGS         ${cost:.3f}")
    print(f"  quoted                ${quoted:.3f}")
    if cost > quoted:
        failures.append(
            f"measured ${cost:.3f} exceeds the quote ${quoted:.3f} — the "
            f"run was served below the margin it was priced at"
        )

    print()
    for note in notes:
        print(f"  NOTE  {note}")
    for failure in failures:
        print(f"  FAIL  {failure}")
    if not failures:
        print("  All checks passed. Read the scoreboard above anyway.")
    print()
    return 1 if failures else 0


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", help="price it, change nothing")
    p.add_argument("--verify", metavar="SIM_ID", help="re-run the checks on a finished run")
    p.add_argument(
        "--null-control",
        action="store_true",
        help="A/A/A: identical copy in all three arenas. A named winner is a failure.",
    )
    args = p.parse_args()

    global VARIANTS, NULL_CONTROL
    if getattr(args, "null_control", False):
        NULL_CONTROL = True
        VARIANTS = NULL_CONTROL_VARIANTS
        print("\n  A/A/A NULL CONTROL — identical copy in all three arenas.")
        print("  A named winner is a FAILURE, not a finding.")

    if args.verify:
        sys.exit(verify(args.verify))

    price()
    if args.dry_run:
        print("  Dry run — nothing created, nothing spent.\n")
        return

    print("── Creating ────────────────────────────────────────")
    sim_id = create()
    asyncio.run(execute(sim_id))
    code = verify(sim_id)
    print(f"Simulation: {sim_id}")
    sys.exit(code)


if __name__ == "__main__":
    main()
