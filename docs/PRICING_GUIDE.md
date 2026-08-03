# Saibyl — Pricing Guide

**Saido Labs LLC** · Internal · Last recalculated 2026-08-02

Two parts: **Part 1** is how pricing is disclosed to self-serve customers in the
product. **Part 2** is how to quote a volume or annual deal on a call.

All figures come from the same cost model the product bills against
(`app/services/billing/agent_pricing.py`). Regenerate with:

```
cd backend && python scripts/quote.py
```

---

# Part 1 — Self-serve pricing and what the UI must say

## 1.1 The model

Credits ration usage; shape caps only prevent runaway spend. A customer can move
the sliders past the advertised "standard run" and consume more of their monthly
credits per run. **This must be disclosed before they hit it, not after.**

The reference unit for all advertised run counts:

> **Standard run** = 100 agents × 5 rounds × 2 platforms × 1 variant → **$3.23 COGS**

## 1.2 Tier cards — required copy

Advertised run counts are *always* qualified. Never print a bare "6 runs".

```
FOUNDER — $99/mo
  ~6 standard runs per month
  ⓘ "Standard run" = 100 agents, 5 rounds, 2 platforms, 1 variant.
    Larger runs use more of your monthly credits — you'll see the exact
    cost before you start any run.
  Up to 100 agents · 8 rounds · 3 variants
```

Same pattern for Growth and Agency. The tooltip text is not optional — it is the
disclosure that makes the slider behavior fair.

## 1.3 Run Configurator — live readout

Updates on every slider change, always visible before the Run button:

```
┌────────────────────────────────────────────────────┐
│  150 agents · 8 rounds · 3 platforms · 4 variants   │
│                                                     │
│  This run will use   1,240 credits                  │
│  Your balance        3,890 credits  →  2,650 after  │
│  Estimated runtime   ~11 minutes                    │
│                                                     │
│  ≈ 8.8 standard runs' worth of capacity             │
└────────────────────────────────────────────────────┘
```

The last line is the honesty line. A user who bought "18 standard runs" and
configures a 4-variant 150-agent run should see immediately that it consumes
nearly nine of them.

## 1.4 Required warning states

| Trigger | Copy |
|---|---|
| Run > 30% of remaining balance | ⚠️ **This run uses 34% of your remaining credits.** You'll have 2,650 left this cycle — about 8 standard runs. *(Continue / Adjust)* |
| Run > remaining balance | **Not enough credits.** This run needs 1,240; you have 890. → *Buy credits* · *Reduce to fit my balance* |
| Balance < 15% remaining | Heads up — you've used 85% of this cycle's credits. Renews on the 14th. |
| Slider hits tier cap | Founder tier caps runs at 3 variants. *Upgrade to Growth* for up to 5. |

"Reduce to fit my balance" should actually compute the largest configuration
that fits and offer it in one click. That converts a dead end into a run.

## 1.5 Rules

- **Never** show a run count without the standard-run definition attached.
- **Never** start a run without showing its credit cost first.
- Price is computed server-side and returned signed. The client displays it; it
  never calculates it.
- Overage credits are sold at the **same 80% margin** as the grant. Cheaper
  overage would let a heavy user buy the lowest tier and load up, cannibalizing
  upgrades. Upgrade pressure comes from caps, seats, the client layer, and
  white-label — not unit price.

## 1.6 Self-serve tiers

| Tier | Price | COGS grant | ≈ standard runs | ≈ 8-variant runs | Margin |
|---|---:|---:|---:|---:|---:|
| Free trial | $0 (one run) | ~$0.35 | 1 capped | — | — |
| Founder | $99 | $19.80 | 6 | 2 | 80% |
| Growth | $299 | $59.80 | 18 | 7 | 80% |
| Agency | $999 | $199.80 | 62 | 23 | 80% |
| Enterprise | Custom annual | see Part 2 | | | 68–78% |

Regional bands (Tier 2 −40%, Tier 3 −60%) scale the grant with the price and
gate on card billing country — see `PRD_V2.md` §8.

---

# Part 2 — Quoting volume and annual deals

## 2.1 Ask this before quoting anything

**The same "400 runs/month" is worth between $5,881 and $51,758 per month
depending on run shape.** Volume alone is not a quote.

| If their runs are… | COGS/run | COGS/mo @400 | Quote/mo | Annual prepay |
|---|---:|---:|---:|---:|
| All standard | $3.23 | $1,294 | $5,881 | $63,514 |
| Blended agency mix | $11.77 | $4,706 | $21,391 | $231,025 |
| All 8-variant marketing | $8.85 | $3,540 | $16,092 | $173,792 |
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
| Light | 50ag / 5rd / 2pf / 1v | $2.15 | 0.7× |
| **Standard** | **100ag / 5rd / 2pf / 1v** | **$3.23** | **1.0×** |
| Marketing | 100ag / 5rd / 1pf / 8v | $8.85 | 2.7× |
| Founder-max | 100ag / 8rd / 3pf / 3v | $14.84 | 4.6× |
| Growth | 150ag / 8rd / 3pf / 4v | $28.47 | 8.8× |
| Heavy | 250ag / 12rd / 4pf / 8v | $181.52 | 56.1× |
| *Blended agency mix* | *55/30/13/2 weighting* | *$11.77* | *3.6×* |

## 2.3 Volume band table — blended agency mix

Priced at **$11.77/run COGS**. This is the default quoting table.

| Runs/mo | Margin | COGS/mo | **PRICE/mo** | $/run | Annual prepay | Gross profit/yr |
|---:|---:|---:|---:|---:|---:|---:|
| 100 | 80% | $1,177 | **$5,883** | $58.83 | $63,532 | $49,414 |
| 200 | 78% | $2,353 | **$10,696** | $53.48 | $115,512 | $87,276 |
| 300 | 78% | $3,530 | **$16,043** | $53.48 | $173,269 | $130,914 |
| 400 | 78% | $4,706 | **$21,391** | $53.48 | $231,025 | $174,552 |
| 500 | 78% | $5,883 | **$26,739** | $53.48 | $288,781 | $218,190 |
| 750 | 75% | $8,824 | **$35,295** | $47.06 | $381,191 | $275,304 |
| 1,000 | 75% | $11,765 | **$47,061** | $47.06 | $508,254 | $367,073 |
| 1,500 | 72% | $17,648 | **$63,028** | $42.02 | $680,698 | $468,925 |
| 2,000 | 72% | $23,530 | **$84,037** | $42.02 | $907,597 | $625,234 |
| 3,000 | 70% | $35,295 | **$117,651** | $39.22 | $1,270,636 | $847,091 |
| 5,000 | 70% | $58,826 | **$196,086** | $39.22 | $2,117,727 | $1,411,818 |

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
