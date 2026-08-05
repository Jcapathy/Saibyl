# Saibyl V2 — Decision Record

**Saido Labs LLC** · Reasoning captured 2026-08-02

`PRD_V2.md` says *what* V2 is. This says *why*, including the alternatives that
were rejected and what would justify reopening each decision.

It exists so a future session can push back intelligently instead of either
following the spec blindly or overturning a considered decision because the
reasoning wasn't written down. **If you are about to change something here,
read that decision's "What would change this" row first.**

---

## 1. Rebuild the measurement layer before shipping any V2 feature

**Chose:** Phase 1 replaces formulaic sentiment with per-event measurement
before the Founder, Marketing, or Crisis lens is built.

**Why.** V1's event sentiment was `sentiment_baseline × (1 + round/max_rounds ×
1.5)` — a function of the archetype preset and the round index that never read
what the agent said. The frontend then scraped one scalar out of the report
markdown and *generated* the timeline, per-platform sentiment, persona metrics,
and risk matrix with `Math.sin()` and `Math.random()`.

The severity is a function of what the customer does with the number. For
crisis-PR narrative texture, a plausible-looking arc was survivable. For a
founder reallocating $200K of ad spend or delaying a launch because Saibyl
flagged a flashpoint, it is not. Every V2 promise — "the synthetic audience
flagged the specific claims that turn discourse negative" — is a claim that the
flagging is *measured*. Building three lenses on top of a formula would mean
three products making a false claim instead of one.

**Rejected — ship tabs first, fix numbers after.** Faster to demo, and the
argument for it is real: customer feedback beats internal correctness work. It
was rejected because the early founder cohort is exactly the audience that would
act on the numbers hardest and churn loudest, and because retrofitting
measurement under three shipped report formats is strictly more work than
building them on it.

**Rejected — fix only the surfaces founders touch.** Would leave two truth
systems in one codebase. Every shared component would need to know which one it
was rendering.

**What would change this:** nothing short of the numbers already being measured.
This is the load-bearing decision in V2.

---

## 2. Three lenses over one workspace, not three products

**Chose:** One org, one project, one set of ingested assets. A lens changes the
intake form, audience routing, computed metrics, and report template — all three
read the same simulation and analysis objects.

**Why.** The scenario that motivated V2 is a founder who launches, takes
narrative damage, and needs crisis work. If Crisis is a separate product, that
founder re-onboards, re-uploads, and loses their history at the exact moment
they are most stressed and most likely to churn. Sharing the workspace also
means calibration history and ICP profiles accumulate per account rather than
per product.

**Rejected — separate SKUs sharing an engine.** Cleaner pricing story and easier
to market each vertical independently. Rejected because it makes the
founder→crisis path a second purchase decision, which is where it would die.

**What would change this:** if Crisis is ever sold to a genuinely different
buyer (agencies of record, not founders) with no account overlap, the shared
workspace stops paying for itself.

---

## 3. Derive the ICP from uploaded material, don't pick from packs

**Chose:** An Opus pass reads the founder's PRD/landing page/deck and synthesizes
buyer archetypes — role, budget authority, incumbent tooling, switching cost,
evaluation criteria, skepticism triggers. The 16 built-in packs become priors
and blend targets, not the answer.

**Why.** This is the single biggest quality lever in the Founder lens. Sixteen
generic packs cannot represent "developers evaluating an observability tool who
already pay for Datadog." A simulation run against the wrong audience produces
confidently wrong output, which is worse than no output.

**Rejected — expand the pack library to 40.** Cheapest to build, and packs are
already data-not-code so it scales. Rejected because no fixed library covers the
long tail of B2B niches, and the founder is the wrong person to ask which of 40
packs matches their buyer — that judgment is what they're paying for.

**Rejected — founder fills in a structured ICP form.** More control, less magic,
and a real option if synthesis proves unreliable. Kept as the editing surface:
synthesis proposes, the founder corrects.

**What would change this:** if synthesis quality proves unreliable in Phase 2
testing, fall back to form-first with synthesis as a suggestion.

---

## 4. The inoculation loop must re-simulate, not just recommend

**Chose:** detect → draft counter-asset → **re-simulate with the asset
pre-seeded** → report the measured before/after delta per objection.

**Why.** Step 3 is the entire product. Without it, "here's what to pre-position"
is an LLM opinion — which every competitor can generate and no founder should
trust. With it, Saibyl can say *this specific disclosure moved this specific
objection from 34% of the swarm to 9%, and here are the agents who changed their
mind.* Nobody else has that, and it cannot be faked without the measurement
layer from decision #1.

It is also the cleanest conversion trigger in the product: detect-then-verify is
structurally two runs. The free tier gets one.

**Rejected — detect and recommend only.** Much cheaper. Rejected because it
throws away the defensibility *and* the natural second-run trigger in one move.

**What would change this:** if re-simulation cost makes the loop unsellable. It
does not, but the margin is narrower than this entry claimed until 2026-08-04,
and the correction is worth recording because the error was in the *direction*
of the argument rather than its size.

The claim was that a re-simulation is the cheaper of the two runs, because it
copies its parent's agents instead of generating them. It does copy them, and it
is still the **more expensive** run. Its assets are pre-positioned through
`topic_block()`, which means they are re-sent with every agent action prompt —
measured at 312 input tokens per action in the parent against 1,654 in the child.
The generation it skips is worth less than the assets it carries.

The full loop — parent run, one drafting pass, one re-simulation — is **$5.97**
of COGS at the current model against a $99/mo tier whose grant is $19.80. Three
loops a month, not four. Still not the constraint, and no longer a figure that
gets better the more of the loop a founder uses.

---

## 5. N-way matched swarms, not a repair of the 2-way A/B

**Chose:** 2–8 variants judged by the *same* generated audience — identical
agents, identical seeds — each in an isolated arena.

**Why.** Two reasons. First, V1's A/B never ran variant B at all
(`run_simulation_ab` calls `run_simulation` once), so there is nothing to
repair — it is net-new either way. Second, matched audiences are what make the
comparison valid: if each variant faces a differently-drawn swarm, differences
are confounded by audience draw and the scoreboard is noise dressed as signal.

Nobody tests two headlines. They test six.

**Consequence to preserve:** agent generation cost does **not** scale with
variant count, because the audience is shared. The cost model reflects this. If
someone "fixes" that by regenerating per variant, cost rises 8× on an 8-variant
run *and* the results stop being comparable.

**What would change this:** nothing foreseeable. Seed-locking is table stakes
for the claim being made.

---

## 6. Per-objective intent metrics, with virality on a separate axis

**Chose:** The objective chosen at setup determines the headline metric (click
intent, visit intent, purchase intent, …). Sentiment demotes to a supporting
metric. Virality Potential Score is reported *separately*, never blended into
the objective score.

**Why.** "Not all marketing is the same" was the founding observation — an ad
meant to drive foot traffic and an ad meant to sell a service succeed
differently, and scoring both on sentiment measures neither. Sentiment is a
proxy that stopped being needed once intent could be measured directly.

Virality stays a separate axis because **a variant can spread widely and convert
terribly.** Blending them into one score hides exactly the two cases a marketer
must act on: *viral but off-message* (it will spread as something you didn't
say) and *converts but won't travel* (good copy that needs paid distribution).

**Cross-archetype reach carries the heaviest weight** inside the virality score.
Content that spreads only within its originating cohort is an echo chamber, not
virality, and a naive share-count metric cannot tell the difference.

**What would change this:** if users find two axes confusing, present a combined
headline — but keep both computed and drillable underneath. Do not collapse the
underlying measurement.

---

## 7. The adversarial/incumbent cohort is core to the Founder lens

**Chose:** A configurable share of the swarm is incumbent-aligned — incumbent
employee, incumbent power user, sunk-cost consultant, category skeptic,
free-alternative advocate.

**Why.** Three arguments, in order of strength:

1. **The most common objection is invisible without it.** A B2B buyer never
   evaluates a product in isolation; they evaluate it net of switching cost. A
   swarm of pure buyers reacts to the pitch on its merits and systematically
   misses *"we already use X and it's good enough"* — which is why most SaaS
   deals actually die.
2. **Competitor advocates start the narrative decline.** On HN, Product Hunt,
   Reddit, and LinkedIn the loudest early responders skew toward incumbent
   employees, sunk-cost consultants, and OSS-alternative maintainers. They
   arrive first and arrive credentialed; neutral buyers read the thread *after*
   those replies have set the tone.
3. **The inoculation loop is mostly counter-competitive.** Migration paths,
   pricing rationale, security posture, "why not just use X" — all answers to
   competitive attack. Testing whether a defense works requires the attacker in
   the room, or you are only measuring whether it reassures people who were
   never going to attack.

**Guardrails are load-bearing, not decoration.** A model asked about a named
competitor will confabulate. So: grounded only in competitor material the user
uploads, never model memory; adversarial agents labeled synthetic in every
report and export; no model-generated claim about a real company presented as
fact; generic no-named-entity skeptic when no material is uploaded. **Do not
relax these to improve output quality.**

**What would change this:** if the guardrails prove insufficient in practice —
i.e. confabulated competitor claims reach a report — narrow the cohort to
unnamed category skeptics rather than removing it.

---

## 8. Stage-aware founder workflows, not one general flow

**Chose:** Five entry points — concept validation, pre-launch positioning,
launch/GTM, growth, fundraise.

**Why — this is the retention mechanism, not a UX nicety.** A validation tool is
a one-time purchase; a positioning system is a subscription. One general "validate
my product" flow gets used once and churns. Five stages are five purchase
occasions for the same account, and the answer legitimately changes every time
the founder ships a feature, changes pricing, rewrites the landing page, or
hears a new objection in a sales call.

**What would change this:** if usage data shows founders only ever use one or
two stages, consolidate — but consolidate toward the stages actually used, not
back to a single generic flow.

---

## 9. Free tier limited by scope, never by hiding content

**Chose:** The free run is capped on agents/rounds/variants/platforms. Everything
the founder receives is complete and honest: sentiment arc plus top 3 objections
with verbatim quotes. What's withheld is *more simulation* — which objection is
load-bearing, cohort attribution, pre-positioning assets, the re-simulation
proof.

**Why.** Blurred text and "upgrade to see" breeds resentment and gets
screenshotted uncharitably. Scope-limiting gives the right asymmetry: the founder
walks away knowing they have a problem and having no plan. That is a real,
honest reason to pay.

A 25-agent run also genuinely has wide confidence bands. Showing those honestly
is both truthful *and* a reason to buy more agents.

**The free run should close with a specific quantified gap**, not a generic
upsell — e.g. *"3 of your 5 objections originate in the incumbent-advocate
cohort and reach neutral buyers by round 3."*

**What would change this:** nothing. Content-gating is a trust decision, not a
conversion-optimization one.

---

## 10. Calibration is the moat

**Chose:** Users report actuals post-launch; Saibyl scores its own prediction and
shows a per-account accuracy record.

**Why.** It is the only real answer to "why should I believe synthetic people,"
it compounds per account (leaving means restarting at zero credibility), and a
competitor cannot copy an accuracy history. Everything else in V2 is replicable
given enough engineering.

**What would change this:** sequencing only — it needs run volume to mean
anything, which is why it is Phase 4 rather than Phase 1.

---

## 11. Additive build with a Step-0 purge, not a rewrite

**Chose:** Keep FastAPI/Supabase/adapters/auth/billing. Delete dead duplicates
first, in separate commits, before any feature work.

**Why.** The solid parts are genuinely solid — 12 platform adapters behind a
clean ABC, RLS multi-tenancy, Stripe, the persona pack format. But the codebase
carried three competing implementations of the simulation runner and two of the
exporter. Building V2 on top would mean every future change asking "which one is
real?"

The purge paid for itself immediately: it surfaced a route collision that had
made the entire chart-rendering export path unreachable, and a `NameError` that
broke `/api/score` on every JWT request.

**What would change this:** nothing. This is complete.

---

## 12. Structured artifacts first, narrative second

**Chose:** The report becomes typed data (`simulation_analysis`) first and prose
second. Every finding carries `event_ids[]`.

**Why.** It is what permanently kills the regex-scraping architecture, and it is
what makes "show me the evidence" possible — a claim that drills down to the
agent quotes that produced it is defensible in a way prose never is. It also
unlocks real charts, CSV/JSON/API export, and the GTM brief as views over one
artifact rather than four parallel generators.

**What would change this:** nothing. Prose-first is what produced the
`Math.random()` charts.

---

## 13. Cost priced per stage, not per agent-round

**Chose:** Four independently priced stages (agent generation, agent actions,
event measurement, report), against real per-model rates.

**Why.** A single flat constant cannot express a pipeline whose stages differ by
an order of magnitude in both volume and model tier. The V1 constant
(`0.000017`) understated an Opus-backed agent action by ~440×. Per-stage pricing
also makes matched-swarm runs price correctly: action cost scales with variants,
generation cost does not.

**Design details worth preserving:**
- Unknown model IDs price at the *highest* known rate. A pricing table that
  fails toward under-charging silently loses money.
- The 70% margin floor is enforced in the quote calculator, not just targeted.
  The stage token profiles are estimates until `llm_usage` has real data; the
  floor bounds the damage if one is wrong.
- Usage attribution uses a contextvar, not a threaded parameter — agent actions
  are issued inside platform adapters that have no reason to know about billing.

**What would change this:** recalibrate the token profiles from measured
`llm_usage` medians once there is data. That is the ledger's whole purpose.

---

## 14. Haiku for volume, Opus for judgment

**Chose:** Haiku for agent actions and per-event measurement; Opus for ICP
synthesis, objection canonicalization, variant scoring rationale, report writing.

**Why.** Agent actions are ~5× cheaper on Haiku and are the highest-volume,
lowest-judgment stage. This is what makes 8-variant runs affordable at all.

**The counter-argument, which is real:** surprising minority opinions are where
flashpoints come from, and a weaker model may produce blander agents. Mitigation
is the depth preset — a premium run can promote agent actions to a stronger
model. **Watch for this in Phase 1**: if measured objection diversity drops
versus V1 baselines, the model tier is the first thing to check.

**What would change this:** measured evidence that Haiku agents produce
materially less diverse objections. Test it rather than assuming either way.

---

## 15. Regional pricing scales the grant with the price

**Chose:** $99/mo US anchor. Regional tiers discount the subscription *and*
proportionally scale the included credit grant. Discount eligibility is gated on
the card's billing country.

**Why.** Saibyl is not typical SaaS: marginal cost is real and
location-independent. An LLM call costs the same in Mumbai as in Manhattan, so a
PPP discount comes straight out of margin rather than being nearly free. Holding
the grant constant at a 60% discount drops margin to 50% — below the floor.
Scaling the grant keeps every region above 70% and is honest: less compute for
less money, not the same compute at a loss.

| Region | Price | Runs | COGS | Margin |
|---|---:|---:|---:|---:|
| US / EU anchor | $99 | 6 | $19.41 | 80.4% |
| Tier 2 (−40%) | $59 | 4 | $12.94 | 78.1% |
| Tier 3 / India (−60%) | $39 | 3 | $9.70 | 75.1% |
| *India at US grant* | *$39* | *6* | *$19.41* | *50.2% ✗* |

**Card-country gating is the one control that matters.** IP geolocation is for
display only — a VPN defeats it instantly, and letting the client assert its own
region means no pricing integrity at all. Store the region on the org at
subscription time and re-validate on renewal.

**What would change this:** if LLM costs fall enough that COGS stops being
material, the grant could stay constant and the discount become a pure
land-grab lever.

---

## 15b. Tier ladder is 99 / 299 / 999, and credits ration instead of caps

**Chose:** Growth $299 and Agency $999 (down from $499/$1,499), with margin held
at 80% by right-sizing the grants. Grants denominated in credits (COGS dollars),
not runs. Shape caps exist only to prevent runaway spend; the credit balance is
what actually rations.

**Why the prices moved.** The problem was the ladder shape, not the numbers.
99 → 499 is a 5× step and that is where prospects stall; 99 → 299 → 999 is 3.0×
then 3.3×. The old grants (~30 runs at $499, ~100 at $1,499) came from a V1
strategy doc written before any cost model existed and had never been validated
against anything — so cutting the price did **not** require cutting margin, only
sizing the grant honestly. $299 at 80% still buys 21 standard runs or 5
eight-variant runs a month.

**Why credits, not runs.** A "run" varies by roughly 20× across the tier caps —
standard is $2.74, a 250-agent 8-variant run is $54.61. A grant denominated in
runs is therefore unbounded compute. Runs survive as sales language against a
defined reference run only.

That the multiplier itself has moved — it was quoted at 56× when the cost model
was wrong in a different place — is the argument for credits restated. Any unit
whose meaning shifts when the cost model is corrected cannot be the metered
unit; a credit is $0.001 of COGS by definition and does not move.

**Why not tighter shape caps.** Rationing by caps punishes the user for the
system's inability to price. The Run Configurator shows exact credit cost before
commit, so a user spending 34% of their balance on one large run is making an
informed choice. Caps then only need to stop accidents, not enforce fairness.
**This only holds if the disclosure actually happens** — the required copy and
warning states in `PRICING_GUIDE.md` Part 1 are load-bearing, not decoration.

**Why overage is priced at the same 80% margin, not cheaper.** Volume-discounted
overage would let a heavy user buy the cheapest tier and load up on credits,
cannibalizing upgrades. Upgrade pressure should come from caps, seats, the client
layer, and white-label — real feature differences — not unit price.

**Enterprise margin bands (80% → 68% by volume) are a choice, not a cost saving.**
COGS is linear in volume; Anthropic gives no bulk discount absent a negotiated
one. Every band step trades margin for contract size deliberately.

**What would change this:** the stage token profiles behind every figure here are
still estimates. Recalibrating them from measured `llm_usage` medians after
Phase 1 is the most likely reason these numbers move. Re-run `scripts/quote.py`
and update `PRICING_GUIDE.md` when they do.

---

## 15c. Pass the corrected cost base through to price, don't bank it

**Chose:** when the cost model was recalibrated from measured `llm_usage` at the
end of Phase 1 and COGS fell, prices fell with it. Enterprise quotes drop ~40%
(a 400-run/month blended deal goes from ~$21,000 to $12,515), and self-serve
tiers keep their grants so run counts rise instead — Founder 6 → 8, Growth
20 → 26, Agency 69 → 88.

**Why.** The old numbers were not a pricing position; they were an artifact of a
bug. Agent-action cost was being multiplied by the platform count, when the
swarm is split across platforms rather than duplicated onto each. Holding the
old prices would have meant charging a margin nobody had decided on, defended by
a cost figure known to be wrong — and every quote after that would be built on a
number the team could no longer explain.

There is also a competitive argument, but it is secondary: at $31/run blended,
Saibyl undercuts the research line item it displaces by more than it needs to.
The primary reason is that a price should be traceable to a real cost.

**Margin policy is untouched.** 80% target, 70% floor, the same volume bands.
The margin was never the thing that changed — only the cost base it sits on. A
recalibration that moved COGS *up* would raise prices by the same logic.

**Rejected — hold the old price points and bank the margin.** Real money, and
defensible if the market had validated those prices. Rejected because nothing
had: no enterprise deal has been quoted, so there is no anchor to protect and no
customer to disappoint. Banking margin on a corrected bug also means the *next*
recalibration has to be argued against a price that has no derivation.

**Rejected — hold prices until a deal is lost on price.** Slower and lower risk,
but it means the quoting table and the cost model disagree, and the guide exists
precisely so a person on a call can quote from one source.

**Carry this caveat:** the blended agency mix assumes 45% multi-variant runs and
the engine runs one arena until Phase 3 — see §15d.

**What would change this:** an enterprise deal actually closing near the old
numbers, which would be evidence the market bears them. Failing that, the next
recalibration moves prices again, in whichever direction the measurement goes.

---

## 15d. Quote what runs today; sell variants as a dated addition

**Chose:** every contract beginning before Phase 3 is quoted from the
**standard-run** band table (`PRICING_GUIDE.md` §2.3, **$2.74/run COGS** as of
2026-08-04), not the blended agency mix. The matched-variant capability is
written into the contract as a planned addition at a defined price, explicitly
unavailable at the effective date, with no fees accruing until the customer
elects it.

**Why.** The blended mix assumes 45% multi-variant runs and the engine runs one
arena (`MAX_RUNNABLE_VARIANTS = 1`). Quoting $34/run for runs that cost $2.74
reads as a 78% margin and is in fact far higher. The customer discovers the gap
at renewal — the worst moment to be holding a number you cannot defend — and the
thing they will remember is the margin, not the product.

**Note on the cost base.** The per-run figure has now moved three times — $3.23 →
$2.26 → $2.71 → $2.74 — as the cost model was corrected against measured usage. The
decision is unaffected: it is about *which table* to quote, not what the numbers
in it are. Always take the figure from `PRICING_GUIDE.md` §2.3 rather than from
this page, and regenerate with `python scripts/quote.py` if in any doubt.

Selling the capability as a dated addition is strictly better than either
alternative. It gives the customer a reason to sign now, and it gives you a
pre-agreed uplift when Phase 3 lands instead of a renegotiation.

**Rejected — quote the blended table and treat the excess as a buffer against
Phase 3 cost growth.** Defensible arithmetic: multi-variant runs will raise COGS
later, so charging for them early smooths it. Rejected because it charges today
for a capability that does not exist, and the buffer argument is invisible to
the customer — they see only that they paid a variant price for single-variant
runs.

**Rejected — wait for Phase 3 before quoting enterprise at all.** Cleanest, and
wrong: it forfeits every deal in the interim for a problem a contract clause
solves.

**Load-bearing in the clause** (§2.6a): the capability is named unavailable *in
the contract text*, no fees accrue before election, and existing entitlements are
not conditioned on its delivery. That last point is what keeps a Phase 3 slip
from becoming a contractual failure. **Have counsel review before use** — the
sample language is a starting point, not an opinion.

**What would change this:** Phase 3 shipping, at which point §2.3b becomes the
default table and the clause becomes a live price rather than a placeholder.

---

## 16. Sequencing: truth → founder → marketing → crisis

**Chose:** Phase 1 measurement, Phase 2 Founder, Phase 3 Marketing, Phase 4
Crisis + calibration.

**Why.** Founder before Marketing because the underserved-market thesis is the
reason for V2 at all, and Phase 2 is the first sellable milestone. Crisis last
because it is the only lens with an existing (if flawed) product, so it is the
one that can wait.

**Rejected — Marketing first.** A defensible alternative: ad-copy testing is the
most concrete, most easily priced, and closest to an existing budget line, and
agencies may be easier to reach than founders. Reconsider if founder outreach
proves slow — the engine work in Phase 1 serves both.

---

## 16b. Score the variant comparison as the paired design it is

**Chose:** compute the winner test from **per-agent differences between arenas**,
not from two independently-estimated arena proportions. The evidential bar does
not move: still 95%, still a refusal when the evidence does not clear it.

**Why.** Phase 3 hands *the same swarm, by agent id, to every arena* — that is
the central design decision of the Marketing lens and the reason generation cost
does not scale with variants. Verified on `adedb93f`: all 27 agents produced
measured events in all 3 arenas. The comparison then threw that away.
`_proportion_interval` estimates each arena's band as though the arenas were
independent samples of different people, and `_resolve_winner` requires the top
two bands not to overlap.

Two costs compounded:

- **Non-overlapping 95% intervals is roughly a p < 0.006 test**, not p < 0.05.
  It demands about 2.6x the effect an ordinary two-proportion test would.
- **Ignoring the pairing inflates the variance.** Paired variance is
  `[s1² + s2² − 2·rho·s1·s2]/n`; the unpaired form drops the `rho` term. Pooled
  within-agent correlation measured **+0.20** across the three clean runs.

Measured consequence — the smallest difference each tier can resolve, in
percentage points of the objective rate:

| tier | cap | unpaired (shipped) | paired |
|---|---:|---:|---:|
| founder | 100 | 17.0 | **10.8** |
| growth | 150 | 13.9 | **8.8** |
| agency | 250 | 10.8 | **6.8** |
| enterprise | 1,000 | 5.4 | **3.4** |

At 17 points, most honest message tests return "no winner" and the founder tier
is hard to defend as a message-testing product at all.

**This is not a lower bar, and the distinction is the whole decision.** The
paired estimator's false-positive rate measured **1.0–2.5% against a 2.5%
nominal** for a one-sided 95% test — calibrated, not permissive. Had it come
back at 8% it would have been rejected. Computing the correct statistic for the
design that was actually run is a different act from lowering the standard, and
only one of them is honest. `scripts/calibrate_marketing.py` reproduces every
figure above; it is read-only and spends nothing.

**Rejected — leave it alone.** The shipped rule names a winner from shuffled
labels **0.0% of the time at every swarm size tested**, which is a genuinely
strong property to be able to state. Rejected because it is also 0.2% likely to
name a real winner at 100 agents: a rule that never fires is not a conservative
test, it is not a test. The refusal was never the problem; the estimator behind
it was.

**Rejected — relax the overlap rule to a plain significance test.** This would
buy similar power and is what most A/B tools do. Rejected because the refusal is
the product. A marketer acts on the top row, so an ordering drawn from
overlapping bands launders sampling noise into a spend decision, and the
inoculation loop's `unresolved` verdict rests on the same principle. Loosening
one would eventually be used to argue for loosening the other.

**Rejected — just sell bigger swarms.** Required n scales as 1/delta², so
resolving a 5-point difference under the unpaired rule needs roughly enterprise
scale. Telling founders to buy 1,000 agents to answer a question their design
already answers at 250 is charging for our own statistical inefficiency.

**Conditions attached to adoption**, all three of which must hold:

1. **An A/A/A control run first** — identical copy in all three arenas — so the
   false-positive rate is *measured on the live pipeline* rather than simulated
   by permutation. `scripts/live_run_marketing.py --null-control`. A named
   winner there is a failure, not a finding.
2. **A test that fails if arenas ever stop sharing a swarm.** Pairing is only
   valid while they do. If a future change gives each arena its own agents, the
   paired estimator becomes silently *wrong* rather than merely conservative —
   the same shape as `test_each_arena_gets_its_own_adapter_instance` guarding
   arena isolation.
3. **Both estimators reported in the artifact for one release**, so the change
   is visible rather than silent. A run analysed before and after will not be
   comparable, and a customer citing an old "no winner" may find the same data
   now names one. That is correct, and it will still look like the product
   changed its mind.

**What would reopen this:** a measured within-agent `rho` near zero on a larger
sample — the benefit scales with it, and +0.20 comes from three runs and ~79
agent-observations. Or the A/A/A control naming a winner, which would mean the
refusal has a false-positive problem that must be fixed before anything is
layered on top of it.

**What this does not license.** The reach bands, inoculation verdicts and cohort
splits are *not* paired designs and keep the unpaired form. Two conventions now
exist in one artifact, which is the "two sources of truth" class — so the paired
form applies to the variant comparison and nowhere else, and that boundary is
stated at the call site.

---

## 17. Open questions deliberately left unresolved

Do not treat these as settled:

- **Which countries fall in which regional tier** is unspecified. Use a published
  PPP band list rather than inventing one.
- **The blended agency run mix** (55% standard / 30% marketing / 13% growth / 2%
  heavy) behind the enterprise quoting table is an assumption, not observed data.
  It matters more than it looks: the 2% "heavy" slice contributes 31% of blended
  COGS. Replace it with real `llm_usage` distributions as soon as there are any.
- **Whether the adversarial cohort share should default to a fixed percentage or
  scale with detected market maturity** — a founder in a brand-new category has
  no incumbent to model.
- **Report depth scaling** (Phase 1 fix) needs a curve, not just a lower floor.
  2 sections at 25 agents and 7 at 250 is a starting point, not a validated one.
