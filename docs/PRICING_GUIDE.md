# Saibyl — Pricing Guide

**Saido Labs LLC** · Internal · Last recalculated 2026-08-02 (end of Phase 1)

Two parts: **Part 1** is how pricing is disclosed to self-serve customers in the
product. **Part 2** is how to quote a volume or annual deal on a call.

All figures come from the same cost model the product bills against
(`app/services/billing/agent_pricing.py`). Regenerate with:

```
cd backend && python scripts/quote.py
```

> **Figures moved at the end of Phase 1.** Report depth now scales down as well
> as up, which removed 2 Opus-written sections from a standard run and 4 from a
> free one. Standard run COGS fell $3.23 → **$2.78**; the free run fell
> $1.27 → **$0.66**. Margins are unchanged — the grants buy more, they were not
> re-sized down. **These are still estimated token profiles**, not measured
> medians; the `llm_usage` recalibration is the next thing to move them.

---

# Part 1 — Self-serve pricing and what the UI must say

## 1.1 The model

Credits ration usage; shape caps only prevent runaway spend. A customer can move
the sliders past the advertised "standard run" and consume more of their monthly
credits per run. **This must be disclosed before they hit it, not after.**

The reference unit for all advertised run counts:

> **Standard run** = 100 agents × 5 rounds × 2 platforms × 1 variant → **$2.78 COGS**

**One credit = $0.001 of COGS.** A standard run is 2,777 credits; the Founder
grant of $19.80 is 19,800. Credits are integers so a balance cannot drift, and
conversion always rounds up — a run costing a fraction of a credit more than it
charges is a run served at a loss.

## 1.2 Tier cards — required copy

Advertised run counts are *always* qualified. Never print a bare "7 runs".

```
FOUNDER — $99/mo
  ~7 standard runs per month
  ⓘ "Standard run" = 100 agents, 5 rounds, 2 platforms, 1 variant.
    Larger runs use more of your monthly credits — you'll see the exact
    cost before you start any run.
  Up to 100 agents · 8 rounds · 3 variants
```

Same pattern for Growth and Agency. The tooltip text is not optional — it is the
disclosure that makes the slider behavior fair.

## 1.3 Run Configurator — live readout

*Shipped in Phase 1: `frontend/src/components/RunConfigurator.tsx`.* Updates on
every slider change, always visible before the Run button:

```
┌────────────────────────────────────────────────────┐
│  150 agents · 8 rounds · 3 platforms · 4 variants   │
│                                                     │
│  This run will use  28,467 credits                  │
│  Your balance       59,800  →  31,333 after         │
│  Estimated runtime  ~16–32 minutes                  │
│                                                     │
│  ≈ 10.3 standard runs' worth of capacity            │
└────────────────────────────────────────────────────┘
```

The last line is the honesty line. A user who bought "21 standard runs" and
configures a 4-variant 150-agent run should see immediately that it consumes
half of them.

## 1.4 Required warning states

All four are implemented in `RunConfigurator.tsx`.

| Trigger | Copy |
|---|---|
| Run > 30% of remaining balance | ⚠️ **This run uses 48% of your remaining credits.** You'll have 31,333 left this cycle — about 11 standard runs. |
| Run > remaining balance | **Not enough credits.** This run needs 28,467; you have 19,800. → *Reduce to fit my balance* |
| Balance < 15% remaining | Heads up — after this run you'll have used most of this cycle's credits. |
| Slider hits tier cap | 🔒 Founder caps this at 3 (variants). |

"Reduce to fit my balance" computes the largest configuration that fits and
offers it in one click — `largest_affordable_run()`. It sheds agents first,
because that is the cheapest dimension to lose: halving the swarm widens the
confidence bands but preserves the round structure and every variant comparison,
whereas dropping a variant deletes a question the user asked.

## 1.5 Rules

- **Never** show a run count without the standard-run definition attached.
- **Never** start a run without showing its credit cost first. The review step
  re-prices live rather than echoing what the configure step showed.
- Price is computed server-side and returned signed (`POST /billing/quote`). The
  client displays it; it never calculates it. The quote is single-use, expires in
  30 minutes, and is checked against the simulation's stored shape at redemption.
- Overage credits are sold at the **same 80% margin** as the grant. Cheaper
  overage would let a heavy user buy the lowest tier and load up, cannibalizing
  upgrades. Upgrade pressure comes from caps, seats, the client layer, and
  white-label — not unit price.

## 1.6 Self-serve tiers

| Tier | Price | COGS grant | Credits | ≈ standard runs | ≈ 8-variant runs | Margin |
|---|---:|---:|---:|---:|---:|---:|
| Free trial | $0 (one run) | $0.70 | 700 | 1 capped | — | — |
| Founder | $99 | $19.80 | 19,800 | 7 | 2 | 80% |
| Growth | $299 | $59.80 | 59,800 | 21 | 6 | 80% |
| Agency | $999 | $199.80 | 199,800 | 71 | 23 | 80% |
| Enterprise | Custom annual | see Part 2 | | | | 68–78% |

The free grant is $0.70, not the $0.35 originally projected. That projection
assumed a 2-section report would bring a 25-agent run to $0.35; with depth
scaling actually implemented the run measures **$0.66**, because the report is
now 46% of a very small run's cost rather than 84% of it. The grant follows the
measured cost — one that did not cover a single free run would make the tier
unusable.

Regional bands (Tier 2 −40%, Tier 3 −60%) scale the grant with the price and
gate on card billing country — see `PRD_V2.md` §8. **The bands are unbuilt** —
`organizations.pricing_region` exists as of migration 018, but no Stripe Price
IDs and no card-country gating.

## 1.7 Tier run caps

Caps stop accidents; the credit balance rations. Enforced in
`agent_pricing.TIER_CAPS`, clamped on the sliders, and *reported* rather than
silently clamped by the quote — quoting one run and executing another is worse
than refusing.

| Tier | Agents | Rounds | Platforms | Variants |
|---|---:|---:|---:|---:|
| Free trial | 25 | 3 | 2 | 1 |
| Founder | 100 | 8 | 3 | 3 |
| Growth | 150 | 10 | 4 | 5 |
| Agency | 250 | 12 | 6 | 8 |
| Enterprise | 1,000 | 20 | 12 | 8 |

---

# Part 2 — Quoting volume and annual deals

## 2.1 Ask this before quoting anything

**The same "400 runs/month" is worth between $5,049 and $51,758 per month
depending on run shape.** Volume alone is not a quote.

| If their runs are… | COGS/run | COGS/mo @400 | Quote/mo | Annual prepay |
|---|---:|---:|---:|---:|
| All standard | $2.78 | $1,111 | $5,049 | $54,533 |
| Blended agency mix | $11.47 | $4,587 | $20,850 | $225,185 |
| All 8-variant marketing | $8.70 | $3,479 | $15,814 | $170,795 |
| All growth-size | $28.47 | $11,387 | $51,758 | $558,984 |

Three questions that pin the number down:

1. **How many runs a month?**
2. **What does a typical run look like** — how many agents, how many variants?
3. **What does your *biggest* run look like?** ← the one people forget

Question 3 matters more than it looks: in the blended mix, the 2% of runs that
are "heavy" contribute **31% of total COGS**. A customer who runs one 250-agent
8-variant test a week can double your cost base without changing their run count.

## 2.2 Cost per run by shape

| Shape | Config | COGS | vs standard |
|---|---|---:|---:|
| Light | 50ag / 5rd / 2pf / 1v | $1.69 | 0.6× |
| **Standard** | **100ag / 5rd / 2pf / 1v** | **$2.78** | **1.0×** |
| Marketing | 100ag / 5rd / 1pf / 8v | $8.70 | 3.1× |
| Founder-max | 100ag / 8rd / 3pf / 3v | $14.84 | 5.3× |
| Growth | 150ag / 8rd / 3pf / 4v | $28.47 | 10.3× |
| Heavy | 250ag / 12rd / 4pf / 8v | $181.52 | 65.4× |
| *Blended agency mix* | *55/30/13/2 weighting* | *$11.47* | *4.1×* |

## 2.3 Volume band table — blended agency mix

Priced at **$11.47/run COGS**. This is the default quoting table.

| Runs/mo | Margin | COGS/mo | **PRICE/mo** | $/run | Annual prepay | Gross profit/yr |
|---:|---:|---:|---:|---:|---:|---:|
| 100 | 80% | $1,147 | **$5,734** | $57.34 | $61,926 | $48,165 |
| 200 | 78% | $2,294 | **$10,425** | $52.13 | $112,593 | $85,070 |
| 300 | 78% | $3,440 | **$15,638** | $52.13 | $168,889 | $127,605 |
| 400 | 78% | $4,587 | **$20,850** | $52.13 | $225,185 | $170,140 |
| 500 | 78% | $5,734 | **$26,063** | $52.13 | $281,482 | $212,675 |
| 750 | 75% | $8,601 | **$34,403** | $45.87 | $371,556 | $268,346 |
| 1,000 | 75% | $11,468 | **$45,871** | $45.87 | $495,408 | $357,795 |
| 1,500 | 72% | $17,202 | **$61,435** | $40.96 | $663,493 | $457,073 |
| 2,000 | 72% | $22,936 | **$81,913** | $40.96 | $884,657 | $609,430 |
| 3,000 | 70% | $34,403 | **$114,678** | $38.23 | $1,238,520 | $825,680 |
| 5,000 | 70% | $57,339 | **$191,130** | $38.23 | $2,064,199 | $1,376,133 |

**Annual prepay** = 12 × monthly, less 10% for paying up front. That discount is
a cash-flow trade, not a margin concession — it does not move COGS.

## 2.4 Margin bands are a choice, not a cost

**COGS does not fall with volume.** Anthropic pricing is linear; there is no
bulk discount unless one is negotiated. Every step down the band table is a
deliberate decision to trade margin for a larger contract.

| Volume | Margin | Rationale |
|---|---:|---|
| ≤100 | 80% | Self-serve equivalent, no discount earned |
| 101–500 | 78% | Committed volume |
| 501–1,000 | 75% | Displaces a research line item |
| 1,001–2,000 | 72% | Strategic account |
| 2,001–5,000 | 70% | Floor for standard deals |
| 5,000+ | 68% | Requires approval — below the product's own margin floor |

**Do not quote below 68% without checking the assumption that COGS stays flat.**
If Anthropic pricing changes or the measured `llm_usage` medians come in above
the estimated token profiles, these bands move.

## 2.5 Quoting on a call

```
python scripts/quote.py --runs 400 --annual                # blended default
python scripts/quote.py --runs 400 --mix marketing --annual
python scripts/quote.py --runs 250 --shape 150,8,3,4       # their exact shape
python scripts/quote.py --runs 1500 --margin 72            # override band
```

Output gives COGS, monthly price, per-run price, annual list, annual prepay, and
gross profit — enough to answer live.

## 2.6 Contract terms to insist on

1. **Define the included run shape in the contract**, not just the run count.
   "500 runs/month up to 150 agents / 8 rounds / 4 variants; larger runs draw
   proportionally more credits." Without this you have sold unbounded compute.
2. **Credits, not runs, are the metered unit.** Runs are the sales language.
3. **Annual prepay is credits granted monthly**, not a single annual pool —
   otherwise a customer can burn twelve months of capacity in January.
4. **Re-quote annually against the current cost model.** These numbers assume
   Haiku for agent actions; a model policy change invalidates them.

## 2.7 When these numbers change

Recalculate and update this file when any of these move:

- Model pricing (`app/services/billing/model_pricing.py`)
- The stage token profiles in `agent_pricing.py` — **these are still estimates**
  and should be recalibrated from measured `llm_usage` medians once Phase 1 has
  produced real data. That recalibration is the most likely source of change.
- The tiered model policy (Haiku for actions, Opus for judgment)
- Report depth scaling (a Phase 1 fix that will *lower* small-run COGS)
