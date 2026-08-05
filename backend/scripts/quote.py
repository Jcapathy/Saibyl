#!/usr/bin/env python
"""Sales quoting tool — what a volume customer costs us, and what to charge.

Answers "an agency wants 400 runs a month, what do I quote?" without guesswork.
Prices come from the same cost model the product bills against
(app/services/billing/agent_pricing.py), so a quote and an invoice cannot drift.

    # Standard band table — the thing to keep open during a sales call
    python scripts/quote.py

    # One specific customer
    python scripts/quote.py --runs 400
    python scripts/quote.py --runs 400 --mix marketing --annual
    python scripts/quote.py --runs 1500 --margin 72

    # Custom run shape (agents/rounds/platforms/variants)
    python scripts/quote.py --runs 250 --shape 150,8,3,4

THE ONE THING TO GET RIGHT: ask what shape their runs are. A 250-agent
8-variant run costs 56x a standard run. Quoting 500 "runs" without knowing the
mix is how you lose money on a contract.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.billing.agent_pricing import (  # noqa: E402
    estimate_simulation_cost,
)

# Named run shapes: (agents, rounds, platforms, variants)
SHAPES = {
    "light": (50, 5, 2, 1),
    "standard": (100, 5, 2, 1),
    "marketing": (100, 5, 1, 8),
    "founder-max": (100, 8, 3, 3),
    "growth": (150, 8, 3, 4),
    "heavy": (250, 12, 4, 8),
}

# What a real agency's month looks like — most runs are routine, a few are big.
# Used for the default blended quote. Weights must sum to 1.0.
AGENCY_MIX = {
    "standard": 0.55,
    "marketing": 0.30,
    "growth": 0.13,
    "heavy": 0.02,
}

# Recommended margin by monthly volume. COGS does not fall with volume — LLM
# pricing is linear — so every step down here is a deliberate business choice,
# not a cost saving. Defaults are conservative; override with --margin.
VOLUME_BANDS = [
    (100, 80.0),
    (500, 78.0),
    (1_000, 75.0),
    (2_000, 72.0),
    (5_000, 70.0),
    (10**9, 68.0),
]

ANNUAL_PREPAY_DISCOUNT = 0.10  # cash up front, not a margin concession


def shape_cost(shape: tuple[int, int, int, int]) -> float:
    """COGS for one run of this shape, **carrying a subject brief**.

    The brief is not in the shape tuple — it is not something a customer
    configures, it is whether their project has uploaded material — and since
    2026-08-04 a run's agents react to that material rather than to the one-line
    description of it. That costs one main-model distillation per run plus a
    surcharge on every action, and it is the reference run's definition
    (`agent_pricing._standard_run_credits`).

    Quoting the document-free version here would understate every enterprise
    contract by ~10% for customers who use the product as it is sold. A customer
    who genuinely uploads nothing is over-quoted by the same amount, which is the
    safe direction and is stated in the output.
    """
    return estimate_simulation_cost(*shape, subject_brief=True).actual_cost_usd


def blended_cost(mix: dict[str, float]) -> float:
    total = sum(mix.values())
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"mix weights must sum to 1.0, got {total}")
    return sum(shape_cost(SHAPES[name]) * w for name, w in mix.items())


def margin_for_volume(runs: int) -> float:
    for ceiling, margin in VOLUME_BANDS:
        if runs <= ceiling:
            return margin
    return VOLUME_BANDS[-1][1]


def quote(runs: int, cost_per_run: float, margin_pct: float) -> dict:
    cogs = runs * cost_per_run
    monthly = cogs / (1 - margin_pct / 100)
    annual_list = monthly * 12
    annual_prepay = annual_list * (1 - ANNUAL_PREPAY_DISCOUNT)
    return {
        "runs": runs,
        "cost_per_run": cost_per_run,
        "monthly_cogs": cogs,
        "monthly_price": monthly,
        "price_per_run": monthly / runs if runs else 0.0,
        "margin_pct": margin_pct,
        "annual_list": annual_list,
        "annual_prepay": annual_prepay,
        "annual_cogs": cogs * 12,
        "annual_gross_profit": annual_prepay - cogs * 12,
        "effective_annual_margin": (annual_prepay - cogs * 12) / annual_prepay * 100,
    }


def print_shape_table() -> None:
    print("WHAT A RUN COSTS US, BY SHAPE")
    print(f"  {'shape':<14} {'config':<22} {'COGS':>9}   {'vs standard':>11}")
    print("  " + "-" * 60)
    std = shape_cost(SHAPES["standard"])
    for name, s in SHAPES.items():
        c = shape_cost(s)
        cfg = f"{s[0]}ag/{s[1]}rd/{s[2]}pf/{s[3]}v"
        print(f"  {name:<14} {cfg:<22} ${c:>8.2f}   {c / std:>10.1f}x")
    print()
    print(f"  Blended agency mix{'':<18} ${blended_cost(AGENCY_MIX):>8.2f}")
    print("  (55% standard / 30% marketing / 13% growth / 2% heavy)")
    print()
    print("  Every figure above assumes the customer uploads material, so their")
    print("  agents react to the product rather than to its description. A run")
    print("  with nothing to distil costs ~10% less; quoting it is only right for")
    print("  a customer who will never upload anything.")
    print()


def print_band_table(cost_per_run: float, label: str) -> None:
    print(f"VOLUME BANDS - priced on {label} (${cost_per_run:.2f}/run COGS)")
    print(
        f"  {'runs/mo':>8} {'margin':>7} {'COGS/mo':>10} {'PRICE/mo':>11} "
        f"{'$/run':>8} {'annual prepay':>15} {'gross profit/yr':>16}"
    )
    print("  " + "-" * 82)
    for runs in (100, 200, 300, 400, 500, 750, 1_000, 1_500, 2_000, 3_000, 5_000):
        q = quote(runs, cost_per_run, margin_for_volume(runs))
        print(
            f"  {q['runs']:>8,} {q['margin_pct']:>6.0f}% ${q['monthly_cogs']:>9,.0f} "
            f"${q['monthly_price']:>10,.0f} ${q['price_per_run']:>7.2f} "
            f"${q['annual_prepay']:>14,.0f} ${q['annual_gross_profit']:>15,.0f}"
        )
    print()
    print(f"  Annual prepay = 12 x monthly, less {ANNUAL_PREPAY_DISCOUNT:.0%} for paying up front.")
    print("  COGS does not fall with volume. Every margin step down is a choice.")
    print()


def print_single_quote(q: dict, label: str, annual: bool) -> None:
    print("=" * 64)
    print(f"QUOTE - {q['runs']:,} runs/month on {label}")
    print("=" * 64)
    print(f"  Cost per run (COGS)      ${q['cost_per_run']:>12,.2f}")
    print(f"  Monthly COGS             ${q['monthly_cogs']:>12,.2f}")
    print(f"  Target margin            {q['margin_pct']:>12.0f}%")
    print("  " + "-" * 46)
    print(f"  MONTHLY PRICE            ${q['monthly_price']:>12,.2f}")
    print(f"  Price per run            ${q['price_per_run']:>12,.2f}")
    print(f"  Monthly gross profit     ${q['monthly_price'] - q['monthly_cogs']:>12,.2f}")
    if annual:
        print("  " + "-" * 46)
        print(f"  Annual (list)            ${q['annual_list']:>12,.2f}")
        print(f"  ANNUAL PREPAY            ${q['annual_prepay']:>12,.2f}")
        print(f"  Annual COGS              ${q['annual_cogs']:>12,.2f}")
        print(f"  Annual gross profit      ${q['annual_gross_profit']:>12,.2f}")
        print(f"  Effective margin         {q['effective_annual_margin']:>12.1f}%")
    print("=" * 64)
    # Derived, not hardcoded: this ratio moved from 2.7x to 4.4x when the cost
    # model was recalibrated, and a stale warning is worse than none.
    _std = shape_cost(SHAPES["standard"])
    _mkt = shape_cost(SHAPES["marketing"])
    print("  Before sending: confirm their run shape. Quoting a standard mix to")
    print(f"  a customer who runs 8-variant tests understates COGS by ~{_mkt / _std:.1f}x.")
    print("  Multi-variant runs are NOT runnable before Phase 3 - quote the")
    print("  standard shape and write the entitlement in (PRICING_GUIDE 2.6a).")


def main() -> None:
    p = argparse.ArgumentParser(description="Saibyl volume/annual quoting tool")
    p.add_argument("--runs", type=int, help="runs per month")
    p.add_argument(
        "--mix",
        default="blended",
        help=f"run shape: blended (default) or one of {', '.join(SHAPES)}",
    )
    p.add_argument("--shape", help="custom shape as agents,rounds,platforms,variants")
    p.add_argument("--margin", type=float, help="override target margin %%")
    p.add_argument("--annual", action="store_true", help="include annual figures")
    args = p.parse_args()

    if args.shape:
        parts = tuple(int(x) for x in args.shape.split(","))
        if len(parts) != 4:
            p.error("--shape needs 4 values: agents,rounds,platforms,variants")
        cost, label = shape_cost(parts), f"custom {args.shape}"
    elif args.mix == "blended":
        cost, label = blended_cost(AGENCY_MIX), "blended agency mix"
    elif args.mix in SHAPES:
        cost, label = shape_cost(SHAPES[args.mix]), f"{args.mix} runs"
    else:
        p.error(f"unknown mix {args.mix!r}; choose blended or one of {', '.join(SHAPES)}")

    if args.runs:
        margin = args.margin if args.margin is not None else margin_for_volume(args.runs)
        print_single_quote(quote(args.runs, cost, margin), label, args.annual)
    else:
        print()
        print_shape_table()
        print_band_table(cost, label)
        print("Quote one customer:  python scripts/quote.py --runs 400 --annual")


if __name__ == "__main__":
    main()
