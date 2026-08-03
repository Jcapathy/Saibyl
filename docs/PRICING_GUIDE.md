# Saibyl — Pricing Guide

**Saido Labs LLC** · Internal · Last recalculated 2026-08-02 (end of Phase 1)

Two parts: **Part 1** is how pricing is disclosed to self-serve customers in the
product. **Part 2** is how to quote a volume or annual deal on a call.

All figures come from the same cost model the product bills against
(`app/services/billing/agent_pricing.py`). Regenerate with:

```
cd backend && python scripts/quote.py
```

> **Recalibrated from measured `llm_usage`, 2026-08-02.** These are no longer
> estimates. Two live runs — 25 agents and the reference standard run — replaced
> the assumed token profiles, and the exercise found two errors in the model
> itself:
>
> - **Platforms were multiplying agent-action cost.** `agent_count` is the whole
>   swarm split across platforms, not duplicated onto each, so a 100-agent
>   2-platform run makes 500 action calls and not 1,000. The largest stage of
>   every quote was inflated by the platform count.
> - **Objection canonicalization was not priced at all**, and report depth was
>   ignored by the report writer.
>
> Net: standard run COGS $3.23 → **$2.26**, and the blended agency mix
> $11.77 → **$6.88**. Margins are unchanged — the model was wrong, not the
> margin policy, so the same 80% now sits on a lower and correct cost base.
> Estimate against measurement on the reference run is now **1.02x**.
>
> **Adding a platform is close to cost-neutral.** It spreads the same swarm
> thinner rather than buying more simulation. Do not sell platforms as volume.

---

# Part 1 — Self-serve pricing and what the UI must say

## 1.1 The model

Credits ration usage; shape caps only prevent runaway spend. A customer can move
the sliders past the advertised "standard run" and consume more of their monthly
credits per run. **This must be disclosed before they hit it, not after.**

The reference unit for all advertised run counts:

> **Standard run** = 100 agents × 5 rounds × 2 platforms × 1 variant → **$2.26 COGS**

**One credit = $0.001 of COGS.** A standard run is 2,265 credits; the Founder
grant of $19.80 is 19,800. Credits are integers so a balance cannot drift, and
conversion always rounds up — a run costing a fraction of a credit more than it
charges is a run served at a loss.

## 1.2 Tier cards — required copy

Advertised run counts are *always* qualified. Never print a bare "8 runs".

```
FOUNDER — $99/mo
  ~8 standard runs per month
  ⓘ "Standard run" = 100 agents, 5 rounds, 2 platforms, 1 variant.
    Larger runs use more of your monthly credits — you'll see the exact
    cost before you start any run.
  Up to 100 agents · 8 rounds · 3 platforms
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

The 8-variant column is gone: multi-variant runs are priced but not runnable
until Phase 3, and advertising a run shape a customer cannot configure is the
kind of claim this guide exists to prevent.

| Tier | Price | COGS grant | Credits | ≈ standard runs | Margin |
|---|---:|---:|---:|---:|---:|
| Free trial | $0 (one run) | $0.80 | 800 | 1 capped | — |
| Founder | $99 | $19.80 | 19,800 | 8 | 80% |
| Growth | $299 | $59.80 | 59,800 | 26 | 80% |
| Agency | $999 | $199.80 | 199,800 | 88 | 80% |
| Enterprise | Custom annual | see Part 2 | | | 68–78% |

The free grant is $0.80, not the $0.35 originally projected. The report and the
objection canonicalizer are both main-model stages that barely shrink with run
size, so on a 25-agent run they dominate: the run measures **$0.75**. The grant
follows the cost — one that did not cover a single free run would make the tier
unusable.

Run counts rose against the previous revision (Founder 6 → 8, Growth 20 → 26,
Agency 69 → 88) purely because the cost model was corrected. The grants and the
80% margin are unchanged; the same COGS dollars simply buy more runs than the
inflated model claimed.

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

**The same "400 runs/month" is worth between $4,118 and $21,795 per month
depending on run shape.** Volume alone is not a quote.

| If their runs are… | COGS/run | COGS/mo @400 | Quote/mo | Annual prepay |
|---|---:|---:|---:|---:|
| All standard | $2.26 | $906 | $4,118 | $44,474 |
| Blended agency mix | $6.88 | $2,753 | $12,515 | $135,161 |
| All 8-variant marketing* | $10.06 | $4,025 | $18,295 | $197,586 |
| All growth-size* | $11.99 | $4,795 | $21,795 | $235,386 |

Three questions that pin the number down:

1. **How many runs a month?**
2. **What does a typical run look like** — how many agents, how many variants?
3. **What does your *biggest* run look like?** ← the one people forget

Question 3 matters more than it looks: in the blended mix, the 2% of runs that
are "heavy" contribute **15% of total COGS**. Doubling that slice to 4% raises
blended COGS by about 15% without changing the run count at all — so a customer
who quietly runs one very large test a week is not on the same deal as one who
does not. (This was 31% before the cost model was corrected; the sensitivity is
real but no longer extreme.)

## 2.2 Cost per run by shape

| Shape | Config | COGS | vs standard |
|---|---|---:|---:|
| Light | 50ag / 5rd / 2pf / 1v | $1.37 | 0.6× |
| **Standard** | **100ag / 5rd / 2pf / 1v** | **$2.26** | **1.0×** |
| Marketing* | 100ag / 5rd / 1pf / 8v | $10.06 | 4.4× |
| Founder-max* | 100ag / 8rd / 3pf / 3v | $6.55 | 2.9× |
| Growth* | 150ag / 8rd / 3pf / 4v | $11.99 | 5.3× |
| Heavy* | 250ag / 12rd / 4pf / 8v | $53.02 | 23.4× |
| *Blended agency mix* | *55/30/13/2 weighting* | *$6.88* | *3.0×* |

\* Multi-variant shapes are **not runnable yet** — the engine runs one arena
(`MAX_RUNNABLE_VARIANTS = 1`). They are priced here for planning only. Do not
quote a variant count a customer can actually configure until Phase 3 ships
N-way matched swarms.

## 2.3 Volume band table — standard runs · **QUOTE THIS ONE**

**Use this for every contract starting before Phase 3 ships N-way matched
swarms.** Priced at **$2.26/run COGS** — the only run shape the engine can
actually execute today, since `MAX_RUNNABLE_VARIANTS = 1`.

| Runs/mo | Margin | COGS/mo | **PRICE/mo** | $/run | Annual prepay | Gross profit/yr |
|---:|---:|---:|---:|---:|---:|---:|
| 100 | 80% | $226 | **$1,132** | $11.32 | $12,228 | $9,511 |
| 200 | 78% | $453 | **$2,059** | $10.29 | $22,233 | $16,798 |
| 300 | 78% | $679 | **$3,088** | $10.29 | $33,350 | $25,198 |
| 400 | 78% | $906 | **$4,117** | $10.29 | $44,467 | $33,597 |
| 500 | 78% | $1,132 | **$5,147** | $10.29 | $55,583 | $41,996 |
| 750 | 75% | $1,698 | **$6,794** | $9.06 | $73,370 | $52,989 |
| 1,000 | 75% | $2,264 | **$9,058** | $9.06 | $97,826 | $70,652 |
| 1,500 | 72% | $3,397 | **$12,131** | $8.09 | $131,017 | $90,256 |
| 2,000 | 72% | $4,529 | **$16,175** | $8.09 | $174,690 | $120,342 |
| 3,000 | 70% | $6,794 | **$22,645** | $7.55 | $244,566 | $163,044 |
| 5,000 | 70% | $11,322 | **$37,742** | $7.55 | $407,610 | $271,740 |

Generate for an exact volume: `python scripts/quote.py --runs 400 --shape 100,5,2,1 --annual`

**Why this and not the blended table.** The blended agency mix assumes 45% of
runs are multi-variant. The engine runs one arena, so every run a customer can
execute today is single-variant. Quoting $31/run against runs that cost $2.26
reads as a 78% margin and is in fact far higher — pleasant right up until the
customer works it out at renewal, which is the worst possible moment for a
number you cannot defend.

Quote what they can run. The variant entitlement goes in the contract as a
Phase 3 addition — see §2.6.

## 2.3b Volume band table — blended agency mix · **PHASE 3 ONWARD**

Priced at **$6.88/run COGS**, assuming the 55/30/13/2 mix. **Do not quote this
for a contract that begins before N-way matched swarms ship.** It becomes the
default the moment they do.

| Runs/mo | Margin | COGS/mo | **PRICE/mo** | $/run | Annual prepay | Gross profit/yr |
|---:|---:|---:|---:|---:|---:|---:|
| 100 | 80% | $688 | **$3,442** | $34.42 | $37,169 | $28,909 |
| 200 | 78% | $1,377 | **$6,257** | $31.29 | $67,580 | $51,061 |
| 300 | 78% | $2,065 | **$9,386** | $31.29 | $101,370 | $76,591 |
| 400 | 78% | $2,753 | **$12,515** | $31.29 | $135,161 | $102,121 |
| 500 | 78% | $3,442 | **$15,644** | $31.29 | $168,951 | $127,652 |
| 750 | 75% | $5,162 | **$20,650** | $27.53 | $223,015 | $161,066 |
| 1,000 | 75% | $6,883 | **$27,533** | $27.53 | $297,353 | $214,755 |
| 1,500 | 72% | $10,325 | **$36,874** | $24.58 | $398,241 | $274,344 |
| 2,000 | 72% | $13,766 | **$49,166** | $24.58 | $530,988 | $365,792 |
| 3,000 | 70% | $20,650 | **$68,832** | $22.94 | $743,383 | $495,589 |
| 5,000 | 70% | $34,416 | **$114,720** | $22.94 | $1,238,972 | $825,981 |

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
# Quote this today — standard runs, the only shape the engine executes
python scripts/quote.py --runs 400 --shape 100,5,2,1 --annual

python scripts/quote.py --runs 250 --shape 150,8,1,1       # their exact shape
python scripts/quote.py --runs 1500 --margin 72            # override band

# Phase 3 onward only — assumes 45% multi-variant runs
python scripts/quote.py --runs 400 --annual                # blended mix
```

Output gives COGS, monthly price, per-run price, annual list, annual prepay, and
gross profit — enough to answer live.

**The bare `--runs N` form defaults to the blended mix**, which is not what you
want for a contract starting before Phase 3. Pass `--shape 100,5,2,1` explicitly,
or read §2.3. Note that the platform figure in a shape barely moves the price —
the swarm is split across platforms rather than duplicated onto each, so
platforms are close to cost-neutral and cannot be sold as volume.

## 2.6 Contract terms to insist on

1. **Define the included run shape in the contract**, not just the run count.
   "500 runs/month up to 100 agents / 5 rounds / 2 platforms / 1 variant; larger
   runs draw proportionally more credits." Without this you have sold unbounded
   compute.
2. **Credits, not runs, are the metered unit.** Runs are the sales language.
3. **Annual prepay is credits granted monthly**, not a single annual pool —
   otherwise a customer can burn twelve months of capacity in January.
4. **Re-quote annually against the current cost model.** These numbers assume
   Haiku for agent actions; a model policy change invalidates them.
5. **Write the variant entitlement in as a Phase 3 addition** — §2.6a. Do not
   sell multi-variant capability as though it exists.

### 2.6a The variant entitlement clause

Multi-variant runs are priced, capped at one arena, and unbuilt. A customer
signing today buys single-variant runs. Two ways to handle that, and only the
first is honest:

**Do:** sell what runs today, and commit to the variant capability as a dated
addition at a defined price. That gives the customer a reason to sign now and
gives you a clean, pre-agreed uplift when Phase 3 lands — rather than a
renegotiation.

**Do not:** quote the blended table, deliver single-variant runs, and let the
customer discover the difference. They will, and the number they will focus on
is the margin.

Sample language, to be reviewed by counsel before use:

> **Included Runs.** During the Initial Term, Customer is entitled to
> [N] Standard Runs per calendar month. A **Standard Run** means one simulation
> of up to 100 synthetic agents across up to 5 rounds and 2 platforms, testing a
> single message variant. Runs exceeding this shape consume credits in
> proportion to their measured compute cost, disclosed in the product before
> each run is started.
>
> **Matched-Variant Testing (Planned Capability).** Provider is developing
> matched-variant testing, in which 2–8 message variants are evaluated by an
> identical synthetic audience under a shared random seed. This capability is
> **not available as of the Effective Date**. Upon general availability,
> Customer may elect to add it at [$X] per month for entitlement to runs of up
> to [V] variants, on the same billing terms. Customer is under no obligation to
> elect it, and no fees for this capability accrue before Customer elects it in
> writing. Nothing in this Agreement conditions Customer's existing entitlements
> on the delivery of this capability.

Three points that clause is doing deliberately:

- **"not available as of the Effective Date"** in the contract itself, not just
  in a sales conversation. This is the sentence that stops a future dispute.
- **No fees accrue until elected.** A customer must never pay for a capability
  during the period it does not exist.
- **Existing entitlements are not conditioned on it.** If Phase 3 slips, the
  customer's contract is unaffected — which is the only version of this you can
  sign without carrying delivery risk into a revenue commitment.

Set `[$X]` from the delta between the two volume band tables at their run count
(§2.3 versus §2.3b) once the mix is known, not from a guess. If they cannot
articulate a variant mix, the honest answer is that the uplift is priced when
the capability ships.

## 2.7 When these numbers change

Recalculate and update this file when any of these move:

- Model pricing (`app/services/billing/model_pricing.py`)
- **Any prompt in the pipeline.** The stage token profiles in `agent_pricing.py`
  are now measured from `llm_usage`, not estimated — which means every prompt
  edit invalidates them. Re-derive with the query in `HANDOFF.md` §7, minding
  that the units differ per stage (per call, per event, per section, per run).
- The tiered model policy (Haiku for actions, Opus for judgment)
- `MAX_RUNNABLE_VARIANTS` — when Phase 3 raises it, §2.3b becomes the default
  quoting table and the variant entitlement clause in §2.6a becomes a live price
- The blended agency run mix (55/30/13/2), which is still an assumption rather
  than observed data

**Do not let this file drift from the model.** Every figure here is reproducible
from `scripts/quote.py`; if a number cannot be regenerated, it is wrong.
