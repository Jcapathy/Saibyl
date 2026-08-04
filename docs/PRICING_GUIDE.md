# Saibyl — Pricing Guide

**Saido Labs LLC** · Internal · Last recalculated **2026-08-04** (ledger re-derivation)

Two parts: **Part 1** is how pricing is disclosed to self-serve customers in the
product. **Part 2** is how to quote a volume or annual deal on a call.

All figures come from the same cost model the product bills against
(`app/services/billing/agent_pricing.py`). Regenerate with:

```
cd backend && python scripts/quote.py
```

> ### ⚠️ 2026-08-04 — the re-simulation was being under-charged
>
> **This one is not a rounding update.** A re-simulation carries its inoculation
> assets in *every agent action prompt*, and nothing in the model charged for
> that. Measured on the one live loop — same agents, same platforms, six assets
> apart — the child run's action input was **5.3× its parent's** (312 → 1,654
> tokens per call), and its clustering call cost **4.4×** more because it carries
> the parent's objections as priors.
>
> The loop was quoted as a *discount* on an ordinary run, because it skips agent
> generation. It skips generation and then spends more than it saved. Measured
> COGS $2.55 against a quote of $2.38 — a 78.5% margin where the model targets
> 80%. Above the 70% floor, so nothing alarmed. **Fixed; re-simulations now quote
> above what the measured loop cost.**
>
> **Standard run COGS $2.71 → $2.74**; blended agency mix $7.35 → **$7.46**; tier
> run counts **7/22/73 → 7/21/73** (only Growth moves). That small change is a
> separate item — event measurement was calibrated on the lowest of four runs.
> Prices, grants and the 80% margin are unchanged.
>
> ---
>
> ### Previously: costs went **up** on 2026-08-03. Run counts fell.
>
> **Standard run COGS $2.26 → $2.71**; blended agency mix $6.88 → $7.35;
> tier run counts **8/26/88 → 7/22/73**. Prices, grants and the 80% margin are
> unchanged — only the cost model moved.
>
> **The report writes six sections and was quoted for four.** It appends an
> executive summary and a conclusion, neither of which comes out of
> `report_section_count`, so a third of the largest main-model stage in every run
> was never quoted. Found by metering the first live Founder-lens run against its
> quote. Objection canonicalization was under-quoted on the same run.
>
> **Anything quoted off the previous table understates cost by ~20%.** If a
> contract was issued against $2.26/run, its margin is lower than the band table
> claimed — check it against the current §2.3 before renewal.
>
> The free grant moved $0.80 → **$1.20**: a 25-agent trial now costs $1.18 and
> 800 credits would no longer complete the one run the tier promises. That
> relationship is now asserted by a test.
>
> **Two profiles are deliberately conservative.** `AGENT_ACTION` and
> `AGENT_GENERATION` measured *lower* than their profiles on this run and were
> left alone: agent-action input is platform-dependent (a Hacker News feed line
> is far shorter than a Reddit post body) and generation input is
> document-dependent. Calibrating to one run's platform mix would under-quote
> every other. The current figures over-quote compact adapters on purpose —
> `ARCHITECTURE_V2.md` has the reasoning. The platform split is now measured
> rather than inferred: **748 input tokens per action on Reddit + Twitter/X
> against 312 on Hacker News + LinkedIn**, at a comparable run shape.
>
> ---
>
> **Still true from the 2026-08-02 recalibration:** adding a platform is close to
> cost-neutral. It spreads the same swarm thinner rather than buying more
> simulation. **Do not sell platforms as volume.**

---

# Part 1 — Self-serve pricing and what the UI must say

## 1.1 The model

Credits ration usage; shape caps only prevent runaway spend. A customer can move
the sliders past the advertised "standard run" and consume more of their monthly
credits per run. **This must be disclosed before they hit it, not after.**

The reference unit for all advertised run counts:

> **Standard run** = 100 agents × 5 rounds × 2 platforms × 1 variant → **$2.74 COGS**

**One credit = $0.001 of COGS.** A standard run is 2,736 credits; the Founder
grant of $19.80 is 19,800. Credits are integers so a balance cannot drift, and
conversion always rounds up — a run costing a fraction of a credit more than it
charges is a run served at a loss.

## 1.2 Tier cards — required copy

Advertised run counts are *always* qualified. Never print a bare "8 runs".

```
FOUNDER — $99/mo
  ~7 standard runs per month
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
│  This run will use  12,688 credits                  │
│  Your balance       59,800  →  47,112 after         │
│  Estimated runtime  ~16–32 minutes                  │
│                                                     │
│  ≈ 4.6 standard runs' worth of capacity             │
└────────────────────────────────────────────────────┘
```

The last line is the honesty line. A user who bought "21 standard runs" and
configures a 4-variant 150-agent run should see immediately that it consumes
nearly a quarter of them.

## 1.4 Required warning states

All four are implemented in `RunConfigurator.tsx`.

| Trigger | Copy |
|---|---|
| Run > 30% of remaining balance | ⚠️ **This run uses 34% of your remaining credits.** You'll have 24,424 left this cycle — about 8 standard runs. |
| Run > remaining balance | **Not enough credits.** This run needs 12,688; you have 5,000. → *Reduce to fit my balance* |
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
| Free trial | $0 (one run) | $1.20 | 1,200 | 1 capped | — |
| Founder | $99 | $19.80 | 19,800 | 7 | 80% |
| Growth | $299 | $59.80 | 59,800 | 21 | 80% |
| Agency | $999 | $199.80 | 199,800 | 73 | 80% |
| Enterprise | Custom annual | see Part 2 | | | 68–78% |

The free grant is $1.20, up from $0.80. The report and the objection
canonicalizer are both main-model stages that barely shrink with run size, so on
a 25-agent run they dominate: the run now measures **$1.18** against $0.75
before. **The grant follows the cost** — one that did not cover a single free run
would make the tier unusable, and 800 credits no longer did. That relationship is
asserted by `test_the_free_grant_covers_one_free_run`, because it has now gone
stale twice.

> ⚠️ **The free grant has 20 credits of headroom** — a free run costs 1,180 of
> the 1,200 granted, or 98.3% of it. That is not headroom, it is a coincidence,
> and it has been under 30 credits since the grant moved to 1,200. **Any stage
> repricing at all can consume it, and the symptom is a signup that cannot run
> the one run the tier promises.** Raising the grant to 1,400 costs $0.22 per
> free trial and removes a recurring failure; it has not been done because the
> grant is a published commercial number. **Decision needed.**

Run counts **fell** again at the 2026-08-04 re-derivation, but only Growth moved:
**7/22/73 → 7/21/73**, on a standard run going $2.71 → $2.74. Growth sat at 21.9
runs and was rounding up in the advertised figure. The previous revision
(2026-08-03) was the larger fall — Founder 8 → 7, Growth 26 → 22, Agency 88 → 73,
after the recalibration found the report writes six sections and was quoted for
four (`ARCHITECTURE_V2.md`). The grants, the prices and the 80% margin are
unchanged throughout; only the cost model moved.

This is the direction DECISIONS §15c did not anticipate. That decision passed a
*corrected downward* cost base through to price and run counts rose, which is
easy. Here the correction runs the other way and the honest options were to
publish lower run counts, raise the grants and absorb the margin, or raise
prices. **Lower run counts was chosen**: the grants and the 80% floor are the
promises the pricing rests on, and the run count is the derived figure. Anyone
already on a tier keeps their credits — the number of *runs* those credits buy
was always shape-dependent and always disclosed as approximate.

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

**The same "400 runs/month" is worth between $4,975 and $23,069 per month
depending on run shape.** Volume alone is not a quote.

| If their runs are… | COGS/run | COGS/mo @400 | Quote/mo | Annual prepay |
|---|---:|---:|---:|---:|
| All standard | $2.74 | $1,094 | $4,975 | $53,725 |
| Blended agency mix | $7.46 | $2,986 | $13,572 | $146,582 |
| All 8-variant marketing* | $10.73 | $4,291 | $19,506 | $210,664 |
| All growth-size* | $12.69 | $5,075 | $23,069 | $249,145 |

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
| Light | 50ag / 5rd / 2pf / 1v | $1.82 | 0.7× |
| **Standard** | **100ag / 5rd / 2pf / 1v** | **$2.74** | **1.0×** |
| Marketing* | 100ag / 5rd / 1pf / 8v | $10.73 | 3.9× |
| Founder-max* | 100ag / 8rd / 3pf / 3v | $7.13 | 2.6× |
| Growth* | 150ag / 8rd / 3pf / 4v | $12.69 | 4.6× |
| Heavy* | 250ag / 12rd / 4pf / 8v | $54.61 | 20.0× |
| *Blended agency mix* | *55/30/13/2 weighting* | *$7.46* | *2.7×* |
| Re-simulation† | 96ag / 5rd / 2pf / 1v, 6 assets | $3.13 | 1.1× |

\* Multi-variant shapes are **not runnable yet** — the engine runs one arena
(`MAX_RUNNABLE_VARIANTS = 1`). They are priced here for planning only. Do not
quote a variant count a customer can actually configure until Phase 3 ships
N-way matched swarms.

† **A re-simulation costs more than the run it repeats, not less.** It skips
agent generation, which is the intuition, and then carries its assets in every
action prompt, which costs more than it saved. A founder running the full
inoculation loop — parent run, one drafting pass, one re-simulation — consumes
**$5.97, or 2.18 standard runs**, not one and a bit. Quote the loop, not the
run, and never write an "unlimited re-tests" clause on the assumption that a
re-test is cheap.

## 2.3 Volume band table — standard runs · **QUOTE THIS ONE**

**Use this for every contract starting before Phase 3 ships N-way matched
swarms.** Priced at **$2.74/run COGS** — the only run shape the engine can
actually execute today, since `MAX_RUNNABLE_VARIANTS = 1`.

| Runs/mo | Margin | COGS/mo | **PRICE/mo** | $/run | Annual prepay | Gross profit/yr |
|---:|---:|---:|---:|---:|---:|---:|
| 100 | 80% | $274 | **$1,368** | $13.68 | $14,774 | $11,491 |
| 200 | 78% | $547 | **$2,487** | $12.44 | $26,863 | $20,296 |
| 300 | 78% | $821 | **$3,731** | $12.44 | $40,294 | $30,444 |
| 400 | 78% | $1,094 | **$4,975** | $12.44 | $53,725 | $40,592 |
| 500 | 78% | $1,368 | **$6,218** | $12.44 | $67,156 | $50,740 |
| 750 | 75% | $2,052 | **$8,208** | $10.94 | $88,646 | $64,022 |
| 1,000 | 75% | $2,736 | **$10,944** | $10.94 | $118,195 | $85,363 |
| 1,500 | 72% | $4,104 | **$14,657** | $9.77 | $158,297 | $109,049 |
| 2,000 | 72% | $5,472 | **$19,543** | $9.77 | $211,063 | $145,399 |
| 3,000 | 70% | $8,208 | **$27,360** | $9.12 | $295,488 | $196,992 |
| 5,000 | 70% | $13,680 | **$45,600** | $9.12 | $492,480 | $328,320 |

Generate for an exact volume: `python scripts/quote.py --runs 400 --shape 100,5,2,1 --annual`

**Why this and not the blended table.** The blended agency mix assumes 45% of
runs are multi-variant. The engine runs one arena, so every run a customer can
execute today is single-variant. Quoting $34/run against runs that cost $2.74
reads as a 78% margin and is in fact far higher — pleasant right up until the
customer works it out at renewal, which is the worst possible moment for a
number you cannot defend.

Quote what they can run. The variant entitlement goes in the contract as a
Phase 3 addition — see §2.6.

## 2.3b Volume band table — blended agency mix · **PHASE 3 ONWARD**

Priced at **$7.46/run COGS**, assuming the 55/30/13/2 mix. **Do not quote this
for a contract that begins before N-way matched swarms ship.** It becomes the
default the moment they do.

| Runs/mo | Margin | COGS/mo | **PRICE/mo** | $/run | Annual prepay | Gross profit/yr |
|---:|---:|---:|---:|---:|---:|---:|
| 100 | 80% | $746 | **$3,732** | $37.32 | $40,310 | $31,352 |
| 200 | 78% | $1,493 | **$6,786** | $33.93 | $73,291 | $55,375 |
| 300 | 78% | $2,239 | **$10,179** | $33.93 | $109,936 | $83,063 |
| 400 | 78% | $2,986 | **$13,572** | $33.93 | $146,582 | $110,751 |
| 500 | 78% | $3,732 | **$16,966** | $33.93 | $183,227 | $138,439 |
| 750 | 75% | $5,599 | **$22,394** | $29.86 | $241,860 | $174,677 |
| 1,000 | 75% | $7,465 | **$29,859** | $29.86 | $322,480 | $232,902 |
| 1,500 | 72% | $11,197 | **$39,990** | $26.66 | $431,893 | $297,527 |
| 2,000 | 72% | $14,930 | **$53,320** | $26.66 | $575,858 | $396,702 |
| 3,000 | 70% | $22,394 | **$74,648** | $24.88 | $806,201 | $537,467 |
| 5,000 | 70% | $37,324 | **$124,414** | $24.88 | $1,343,668 | $895,779 |

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
