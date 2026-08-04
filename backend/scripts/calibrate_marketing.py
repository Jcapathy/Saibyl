"""How many agents does it take to resolve a message difference worth acting on?

Read-only. Spends nothing. Answers the question in HANDOFF §0 item 4 from data
that already exists, so that the runs we do buy are chosen rather than guessed.

--------------------------------------------------------------------------
THE QUESTION
--------------------------------------------------------------------------
Two live runs put the SAME three messages in OPPOSITE orders — 42/42/35% then
23/15/8%, Proof-led last then first. The scoreboard refused to name a winner
both times, which is correct behaviour and also the finding: at 26 agents this
test cannot separate anything. Before the lens is sold, we need to know what it
CAN separate, and at what size.

--------------------------------------------------------------------------
WHAT THE SCOREBOARD ACTUALLY DOES, AND THE TWO CONSERVATISMS IN IT
--------------------------------------------------------------------------
`_resolve_winner` names a winner only when `best.lower > second.upper` — the
top two 95% intervals must not overlap. Each interval is a Wald proportion over
the agents active in that arena, computed independently per arena.

1. **Non-overlap is a much stricter test than it looks.** Two independent 95%
   intervals failing to overlap corresponds to roughly p < 0.006, not p < 0.05.
   It demands about 2.6x the effect an ordinary two-proportion test would.

2. **It discards the pairing.** Verified against `adedb93f`: all 27 agents
   appear in all 3 arenas. The matched swarm is Phase 3's central design
   decision — the same agents see every variant — and then the comparison
   treats the arenas as independent samples. Paired variance is
   Var(p1-p2) = [s1^2 + s2^2 - 2*rho*s1*s2]/n; ignoring rho inflates it.

Neither is a bug. Non-overlap is a deliberate, defensible refusal rule, and it
is the right instinct: a marketer acts on the top row, so an ordering drawn
from overlapping bands launders noise into a spend decision. The question this
script answers is what that instinct COSTS in agents, and whether using the
pairing the design already provides would buy it back without weakening a
single guarantee.

**Nothing here proposes relaxing the refusal.** Computing the correct interval
for the design actually run is a different act from lowering the bar, and only
one of them is honest.

--------------------------------------------------------------------------
WHICH RUNS ARE SAFE TO SAMPLE, AND WHY TWO ARE NOT
--------------------------------------------------------------------------
HANDOFF §1a: "Do not use any run created before 2026-08-04 as a calibration
baseline for agent counts." Agent usernames collided — 100 agents produced 45
distinct handles — so events were attributed to a fraction of the real swarm.

⚠ **`colliding_usernames = 0` on every run today, and that proves nothing.**
Migration 019 RENAMED the duplicates; it could not restore attribution, because
there is no record of which of nine identically-named agents produced a given
event. The fix erased the evidence of the defect, not the defect's consequence.

The detectable signature is `distinct agent_id with a measured intent` versus
`simulations.agent_count`. Two runs fail it and are excluded by id below.

This matters in a specific direction: merging several real agents into one row
SUPPRESSES between-agent variance, which is precisely the quantity being
measured. Including those runs would make the required swarm size look smaller
than it is — an optimistic answer, which is the dangerous kind.
"""
from __future__ import annotations

import math
import os
import random
import sys
from collections import defaultdict
from dataclasses import dataclass

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.database import get_supabase_admin  # noqa: E402
from app.services.intelligence.variant_scoreboard import (  # noqa: E402
    OBJECTIVE_INTENTS,
)

# Runs whose agent identity collapsed. See the module docstring — these are
# excluded by id rather than by a date filter, so a future reader can see
# exactly what was dropped and check the reasoning themselves.
EXCLUDED_RUNS = {
    "03de92ef-7e70-4588-a230-1b1fc25af6d3",  # 100 agents -> 45 distinct
    "05f1d879-a121-4bca-a00c-1aac9949ea43",  # 24 agents -> 19 distinct
}

_Z_95 = 1.959963985
BOOTSTRAP_REPLICATES = 4000
SWARM_SIZES = (26, 50, 75, 100, 150, 200, 300, 400, 600, 800)
SEED = 20260804


@dataclass
class Arena:
    """One variant's per-agent binary outcome: did this agent convert here?"""

    key: str
    label: str
    outcomes: dict[str, int]


def load_paired_runs() -> list[tuple[str, str, list[Arena]]]:
    """Per-agent, per-variant converting outcomes for every clean multi-variant run."""
    admin = get_supabase_admin()

    sims = (
        admin.table("simulations")
        .select("id, name, objective, variants, agent_count")
        .gt("variants", 1)
        .execute()
        .data
    )

    runs: list[tuple[str, str, list[Arena]]] = []
    for sim in sims:
        if sim["id"] in EXCLUDED_RUNS:
            continue

        intents = set(OBJECTIVE_INTENTS.get(sim.get("objective") or "signup", ("trial", "purchase")))

        rows = _fetch_all(
            admin, "simulation_events",
            "agent_id, variant, intent",
            sim["id"],
        )

        # An agent is "active" in an arena if it produced any measured event
        # there. Converting means at least one event carried an objective
        # intent. Same definition `variant_scoreboard` uses, deliberately — a
        # calibration measuring a different quantity than the product ships
        # would answer a question nobody asked.
        active: dict[str, set[str]] = defaultdict(set)
        converted: dict[str, set[str]] = defaultdict(set)
        for row in rows:
            agent, variant, intent = row.get("agent_id"), row.get("variant"), row.get("intent")
            if not agent or not variant or intent is None:
                continue
            active[variant].add(agent)
            if intent in intents:
                converted[variant].add(agent)

        if len(active) < 2:
            continue

        # Only agents present in EVERY arena can be paired. Verified 27/27 on
        # adedb93f, but asserting it here rather than assuming keeps the script
        # honest if the runner ever stops sharing the swarm.
        shared = set.intersection(*active.values())
        if len(shared) < 10:
            continue

        arenas = [
            Arena(
                key=variant,
                label=variant,
                outcomes={a: (1 if a in converted[variant] else 0) for a in sorted(shared)},
            )
            for variant in sorted(active)
        ]
        runs.append((sim["id"], sim.get("name") or sim["id"][:8], arenas))

    return runs


def _fetch_all(admin, table: str, columns: str, simulation_id: str) -> list[dict]:
    """Page past PostgREST's 1,000-row default.

    Three readers of this table were silently truncating at that cap on runs
    producing 10,000+ events. A calibration built on a truncated sample would
    be wrong in a way nothing would flag.
    """
    out: list[dict] = []
    page = 0
    while True:
        chunk = (
            admin.table(table)
            .select(columns)
            .eq("simulation_id", simulation_id)
            .range(page * 1000, page * 1000 + 999)
            .execute()
            .data
        )
        out.extend(chunk)
        if len(chunk) < 1000:
            return out
        page += 1


# ---------------------------------------------------------------------------
# The two decision rules
# ---------------------------------------------------------------------------

def _wald(hits: int, n: int) -> tuple[float, float, float]:
    """Exactly `variant_scoreboard._proportion_interval`, including rule-of-three."""
    if n <= 0:
        return 0.0, 0.0, 0.0
    p = hits / n
    if hits == 0:
        return 0.0, 0.0, min(1.0, 3.0 / n)
    margin = _Z_95 * math.sqrt(max(p * (1.0 - p), 0.0) / n)
    return p, max(0.0, p - margin), min(1.0, p + margin)


def shipped_rule_names_winner(sample: list[list[int]]) -> bool:
    """The rule in production: top two 95% intervals must not overlap."""
    scored = [_wald(sum(col), len(col)) for col in sample]
    ranked = sorted(scored, key=lambda t: t[0], reverse=True)
    return ranked[0][1] > ranked[1][2]


def paired_rule_names_winner(sample: list[list[int]]) -> bool:
    """The same 95% standard, applied to the paired design actually run.

    Per-agent differences between the top two arenas, so an agent that converts
    on both contributes nothing to the variance — which is the whole point of
    handing the same swarm to every arena. Two-sided 95%, so this is NOT a
    lower evidential bar than the shipped rule; it is the same bar, measured
    against the design that produced the data.
    """
    means = [sum(col) / len(col) for col in sample]
    order = sorted(range(len(sample)), key=lambda i: means[i], reverse=True)
    a, b = sample[order[0]], sample[order[1]]

    diffs = [x - y for x, y in zip(a, b)]
    n = len(diffs)
    if n < 2:
        return False
    mean_d = sum(diffs) / n
    var = sum((d - mean_d) ** 2 for d in diffs) / (n - 1)
    if var <= 0:
        return mean_d > 0
    return mean_d - _Z_95 * math.sqrt(var / n) > 0


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

def resample(arenas: list[Arena], n: int, rng: random.Random) -> list[list[int]]:
    """Resample AGENTS with replacement, keeping each agent's full row intact.

    Resampling agents rather than events is what preserves the pairing and the
    within-agent correlation. Resampling events independently would destroy
    both and manufacture precision — the same error `mean_interval` exists to
    prevent inside the product.
    """
    agents = list(arenas[0].outcomes)
    picked = [rng.choice(agents) for _ in range(n)]
    return [[arena.outcomes[a] for a in picked] for arena in arenas]


def permute_null(arenas: list[Arena], n: int, rng: random.Random) -> list[list[int]]:
    """The A/A control, built from real data: shuffle each agent's outcomes
    across arenas so any true difference between variants is destroyed while
    every agent's own propensity is preserved.

    If a rule names a winner here, it is naming one from noise. This measures
    the false-positive rate directly, which is the number that decides whether
    the refusal is doing its job.
    """
    agents = list(arenas[0].outcomes)
    picked = [rng.choice(agents) for _ in range(n)]
    cols: list[list[int]] = [[] for _ in arenas]
    for agent in picked:
        row = [arena.outcomes[agent] for arena in arenas]
        rng.shuffle(row)
        for i, value in enumerate(row):
            cols[i].append(value)
    return cols


def observed_gap(arenas: list[Arena]) -> float:
    means = sorted((sum(a.outcomes.values()) / len(a.outcomes) for a in arenas), reverse=True)
    return means[0] - means[1]


def within_agent_correlation(arenas: list[Arena]) -> float | None:
    """Correlation between the top two arenas' per-agent outcomes.

    This is the quantity the shipped rule throws away. Positive correlation is
    what makes the paired analysis more powerful on identical data.
    """
    means = [sum(a.outcomes.values()) / len(a.outcomes) for a in arenas]
    order = sorted(range(len(arenas)), key=lambda i: means[i], reverse=True)
    xs = list(arenas[order[0]].outcomes.values())
    ys = list(arenas[order[1]].outcomes.values())
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def main() -> None:
    rng = random.Random(SEED)
    runs = load_paired_runs()

    if not runs:
        print("No clean multi-variant run with measured outcomes. Nothing to calibrate.")
        return

    excluded = ", ".join(sorted(EXCLUDED_RUNS))
    print(f"\nRuns sampled (excluded by id: {excluded})")
    pooled: list[Arena] | None = None
    for sim_id, name, arenas in runs:
        rho = within_agent_correlation(arenas)
        print(
            f"  {sim_id[:8]}  {name[:34]:34s} agents={len(arenas[0].outcomes):3d} "
            f"arenas={len(arenas)}  top-two gap={observed_gap(arenas):6.1%}  "
            f"rho={'n/a' if rho is None else f'{rho:+.2f}'}"
        )
        for arena in arenas:
            p = sum(arena.outcomes.values()) / len(arena.outcomes)
            print(f"      {arena.label:12s} {p:6.1%}")

    # Pool the runs into one agent population. They share a shape and an
    # objective; pooling widens the base from ~26 agents to ~79, which is the
    # difference between a curve and an anecdote. Stated as an assumption
    # because it IS one.
    n_arenas = min(len(a) for _, _, a in runs)
    pooled = []
    for i in range(n_arenas):
        merged: dict[str, int] = {}
        for sim_id, _, arenas in runs:
            for agent, value in arenas[i].outcomes.items():
                merged[f"{sim_id}:{agent}"] = value
        pooled.append(Arena(key=f"arena{i}", label=f"arena{i}", outcomes=merged))

    gap = observed_gap(pooled)
    rho = within_agent_correlation(pooled)
    print(
        f"\nPooled: {len(pooled[0].outcomes)} agent-observations across {n_arenas} arenas, "
        f"top-two gap {gap:.1%}, within-agent rho {'n/a' if rho is None else f'{rho:+.2f}'}"
    )

    print("\n── Power: how often each rule names the leading variant ──────")
    print(f"{'agents':>7}  {'shipped':>9}  {'paired':>9}   {'shipped FP':>11}  {'paired FP':>10}")
    for n in SWARM_SIZES:
        shipped = paired = shipped_fp = paired_fp = 0
        for _ in range(BOOTSTRAP_REPLICATES):
            sample = resample(pooled, n, rng)
            shipped += shipped_rule_names_winner(sample)
            paired += paired_rule_names_winner(sample)
            null = permute_null(pooled, n, rng)
            shipped_fp += shipped_rule_names_winner(null)
            paired_fp += paired_rule_names_winner(null)
        r = BOOTSTRAP_REPLICATES
        print(
            f"{n:7d}  {shipped / r:8.1%}  {paired / r:8.1%}   "
            f"{shipped_fp / r:10.1%}  {paired_fp / r:9.1%}"
        )

    # ---------------------------------------------------------------
    # The number that maps to a price list: what can each tier resolve?
    # ---------------------------------------------------------------
    means = [sum(a.outcomes.values()) / len(a.outcomes) for a in pooled]
    order = sorted(range(len(pooled)), key=lambda i: means[i], reverse=True)
    xs = list(pooled[order[0]].outcomes.values())
    ys = list(pooled[order[1]].outcomes.values())
    p1, p2 = means[order[0]], means[order[1]]

    diffs = [x - y for x, y in zip(xs, ys)]
    md = sum(diffs) / len(diffs)
    var_d = sum((d - md) ** 2 for d in diffs) / (len(diffs) - 1)

    print("\n── Smallest difference each tier can actually resolve ────────")
    print(f"{'tier':<12}{'cap':>6}   {'shipped rule':>13}   {'paired rule':>12}")
    for tier, cap in (
        ("founder", 100), ("growth", 150), ("agency", 250), ("enterprise", 1000),
    ):
        # Shipped: the bands must not touch, so the gap must exceed the sum of
        # both half-widths.
        mde_shipped = _Z_95 * (
            math.sqrt(max(p1 * (1 - p1), 0) / cap) + math.sqrt(max(p2 * (1 - p2), 0) / cap)
        )
        # Paired: the gap must clear one half-width of the per-agent difference.
        mde_paired = _Z_95 * math.sqrt(var_d / cap)
        print(f"{tier:<12}{cap:>6}   {mde_shipped:>12.1%}   {mde_paired:>11.1%}")

    print(
        "\n  Read this as: a message difference smaller than the figure shown cannot be\n"
        "  called at that tier, and the product will correctly refuse to name a winner.\n"
        "  These are percentage-point differences in the objective rate."
    )

    print(
        "\n  Power = how often the rule names a winner when the observed difference is real.\n"
        "  FP    = how often it names one when variant labels are shuffled, i.e. from noise.\n"
        "          A rule whose FP rate is high is not refusing enough; a rule whose power\n"
        "          stays low at every buyable size cannot be sold as a message test.\n"
        f"\n  Effect size sampled: {gap:.1%}. Required n scales as 1/delta^2, so a difference\n"
        "  half this size needs roughly four times the agents.\n"
        "\n  ⚠ Extrapolating past ~80 agents resamples a population of that many observed\n"
        "  agents. It will understate tail variance, so treat large-n power as an UPPER\n"
        "  bound. The A/A/A control run is what confirms it."
    )


if __name__ == "__main__":
    main()
