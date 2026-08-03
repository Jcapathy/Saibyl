# Saibyl V2 — Product Requirements

**Saido Labs LLC** · Version 2.0 · Status: in build (Phase 0 complete)

> Saibyl tells you how the market will react to what you're about to say — and what to say instead.

---

## 1. Why V2

V1 shipped a working crisis-PR intelligence tool: ingest documents → generate a synthetic public → simulate discourse across 12 platforms → produce a long-form report. Two things force a second version.

**Market.** Crisis PR firms have not bought. Startup and SaaS founders have an urgent, recurring, underserved need for exactly what the engine does — product validation, positioning, GTM message testing, and pre-emptive narrative defense — and they need it at every stage of the company, not once. Marketing teams and agencies need N-way ad copy comparison against a realistic audience. Crisis PR becomes the third lens rather than the whole product.

**Integrity.** The V1 analysis layer cannot support that market. Event sentiment was computed as `sentiment_baseline × (1 + round/max_rounds × 1.5)` — a function of the archetype's preset and the round index, never of what the agent actually said. The frontend regex-scraped one scalar out of the report markdown and then generated the sentiment timeline, per-platform sentiment, persona metrics, and risk matrix with `Math.sin()` and `Math.random()`. Risk likelihood was literally `0.3 + Math.random() * 0.5`.

For narrative texture in a crisis brief, that was survivable. For a founder reallocating an ad budget or delaying a launch on Saibyl's advice, it is not. Everything V2 promises — "the synthetic audience flagged the specific claims that turn discourse negative" — requires that flagging be *measured from what agents said*.

**Outcome:** a multi-vertical decision-intelligence platform whose numbers are measured, whose runs are priced at 70–90% gross margin, and whose flagship loop — detect the flashpoint, draft the counter-asset, re-simulate, prove the delta — has no equivalent in the market.

---

## 2. Positioning and lenses

One engine, three lenses over one workspace. A founder who needs narrative rehabilitation switches to the Crisis lens without re-onboarding or re-uploading anything.

| Lens | Buyer | Core question | Headline metric |
|---|---|---|---|
| **Founder** | Startup / SaaS founders | Will the market receive this, and what will they object to? | Objection map + adoption intent |
| **Marketing** | In-house marketers, agencies | Which message wins, for which objective? | Per-objective intent lift by variant |
| **Crisis** | Comms leads, PR firms | How does this spread, and how do we stop it? | Propagation velocity + containment delta |

A lens changes the intake form, audience routing, which metrics are computed and surfaced, and the report template. All three read the same simulation and analysis objects.

---

## 3. The measurement substrate

Everything else depends on this.

**Per-event measurement.** Every `simulation_event` is scored from its actual content by a batched Haiku classifier: `valence` (−1..1), `stance` (support / oppose / undecided / off-topic), `intensity` (0..1), `objections[]`, `intent` (objective-specific, §6), `is_novel_claim`. Batched ~25 events per call.

**Objection canonicalization.** A second pass clusters raw objections across the run into canonical objections with a stable ID, label, verbatim supporting quotes, originating cohort, first-round-seen, and propagation curve. This is the object the Founder lens is built around.

**Typed analysis artifact.** A `simulation_analysis` row holds versioned JSON: sentiment timeline with confidence bands derived from actual agent count, per-platform and per-archetype breakdowns, canonical objections, flashpoints, variant scoreboard, propagation graph, and a `quality` block. **Every number rendered in the UI or a report must come from this artifact.** No `Math.random()`, no regex scraping of markdown.

**Evidence pointers.** Every finding carries `event_ids[]`, so any claim drills down to the agent quotes that produced it. This is what makes the output defensible.

---

## 4. Audience construction

**ICP synthesis.** From uploaded material (PRD, landing page, deck, pricing page), an Opus pass derives buyer/user archetypes: role, seniority, budget authority, incumbent tooling, switching cost, evaluation criteria, skepticism triggers. Output is a generated persona pack, editable and reusable across runs in the project. The 16 built-in packs become priors and blend targets, not the answer.

**Adversarial cohort (Founder lens, core).** A configurable share of the swarm is incumbent-aligned: incumbent employee, incumbent power user, sunk-cost consultant/agency, category skeptic, free-alternative advocate.

Rationale: a B2B buyer never evaluates a product in isolation — they evaluate it net of switching cost. A swarm of pure buyers systematically misses *"we already use X and it's good enough,"* which is why most SaaS deals actually die. Separately, the loudest early responders on HN, Product Hunt, Reddit, and LinkedIn skew toward incumbent-aligned actors who arrive first and arrive credentialed; neutral buyers read the thread after those replies have set the tone.

*Guardrails.* The cohort is grounded **only** in competitor material the user uploads, never model memory. Adversarial agents are labeled synthetic in every report and export. No model-generated claim about a real company is presented as fact. With no competitor material, the cohort is generated generically with no named entity.

---

## 5. Founder lens — stage-aware workflows

Five entry points over one engine. Each has its own intake, audience defaults, metrics, and report template. This is the retention mechanism: five purchase occasions per account instead of one.

| Stage | Input | Output |
|---|---|---|
| **Concept validation** | Problem statement, target segment | Does the pain exist, who feels it most, willingness to pay, top disqualifiers |
| **Pre-launch positioning** | PRD, landing page, deck | Objection map by cohort, positioning gaps, credibility deficits |
| **Launch / GTM** | Launch copy, channel plan | Per-channel reception, message-channel fit, pre-positioning asset set |
| **Growth** | Pricing page, feature announcement, churn signals | Pricing reaction, expansion resistance, churn narratives |
| **Fundraise** | Deck, narrative memo | How investors and press read the story, the questions you'll be asked |

### The inoculation loop (flagship)

Available at every stage:

1. **Detect** — canonical objections ranked by load-bearing weight (propagation reach × intensity × cohort spread), not raw frequency.
2. **Draft** — candidate counter-assets per objection (disclosure, roadmap, pricing rationale, security page, migration guide, FAQ entry), each with a stated hypothesis.
3. **Re-simulate** — same audience, same seed, assets pre-seeded into the environment.
4. **Prove** — measured before/after delta per objection: did it die, shrink, or move to another cohort. Assets that don't move the number are reported as ineffective.

Step 3 is what separates this from an LLM opinion, and it is the natural forcing function for the second paid run.

---

## 6. Marketing lens — N-way matched swarms

**Matched-swarm testing.** 2–8 variants judged by the *same* generated audience — identical agents, identical seeds — each in an isolated arena, so differences are attributable to the copy rather than the audience draw. Output is a ranked scoreboard with confidence intervals plus a per-archetype breakdown of who each variant wins and loses.

**Objective-driven metrics.** The objective selected at setup determines what is measured and what winning means. Each agent returns a structured decision alongside its reaction.

| Objective | Primary metric | Secondary |
|---|---|---|
| Clicks / traffic | Click intent | Scroll-past rate, curiosity |
| Foot traffic | Visit intent | Barrier cited, timeframe |
| Product sale | Purchase intent | Price objection, alternative considered |
| Service sale | Inquiry intent | Trust deficit, proof required |
| Signup / trial | Trial intent | Friction cited |
| Awareness / brand | Recall + share intent | Message takeaway accuracy |

Sentiment becomes a supporting metric, not the score. **Message takeaway accuracy** — what agents believe the ad said versus what it said — is reported for every objective.

### Virality Potential Score (0–100)

Reported per variant on every objective, as a *separate axis* from the objective metric, because a variant can spread widely and convert terribly.

| Component | What it measures | Why it matters |
|---|---|---|
| Share intent rate | % of agents with repost/share intent | Direct propagation willingness |
| Cross-archetype reach | Did it escape its originating cohort | **Heaviest weight** — spread confined to one archetype is an echo chamber, not virality |
| Cascade depth | Reply-chain depth and branching | Conversation generation vs. passive consumption |
| Cross-platform jump | Did content surface where it didn't originate | Strongest real-world virality signal |
| Restatement rate | Agents restating the message in their own words | Memetic durability |
| Velocity | Rounds to peak engagement | Fast-burn vs. slow-build shapes channel and budget timing |

Two derived flags: **viral but off-message** (high virality, low takeaway accuracy — it will spread as something you didn't say) and **converts but won't travel** (high intent, low virality — needs paid distribution).

---

## 7. Crisis lens

Migrated onto the new substrate, gaining measured propagation velocity, containment-strategy testing via the same re-simulation loop, and adversarial amplification modeling. The V1 report structure (Source Material → Executive Summary → Data & Analysis → Detailed Findings → Strategic Implications) is preserved, with fabricated charts replaced by real ones.

---

## 8. Run configurator, cost model, and billing

**Run Configurator.** Sliders for agents, rounds, and variants; platform multi-select; depth preset. Live readout on every change: agent-rounds → estimated LLM cost → credits required → price → estimated runtime. Tier caps clamp each slider's maximum. Below balance, the Run button becomes "Buy N credits — $X". The quote is computed server-side and returned signed so the client cannot tamper with the price.

**Tiered model policy.** Haiku for agent actions and per-event measurement (high volume, low judgment). Opus for ICP synthesis, objection canonicalization, variant scoring rationale, and report writing.

**Empirical cost model** *(shipped in Phase 0)*. `model_pricing.py` holds per-model rates; `agent_pricing.py` prices four stages (agent generation, agent actions, event measurement, report) rather than one flat constant; `llm_usage` records real token counts and cost per call, attributed by pipeline stage. Target margin 80% with a hard 70% floor.

Measured output at 80% margin:

| Preset | Agent-rounds | LLM calls | Cost | Price |
|---|---:|---:|---:|---:|
| Free trial (25 agents / 3 rounds / 2 platforms) | 75 | 102 | $0.75 | $3.75 |
| Standard (100 / 5 / 2) | 500 | 604 | $2.26 | $11.32 |
| Marketing 8-variant (100 / 5 / 1 platform)* | 4,000 | 4,107 | $10.06 | $50.32 |
| Deep (250 / 10 / 4) | 2,500 | 3,006 | $7.46 | $37.29 |

\* Multi-variant runs are priced but **not runnable** until Phase 3.

Recalculated at the end of Phase 1, when report depth started scaling down as
well as up: a free run dropped from 6 Opus-written sections to 2 and a standard
run from 6 to 4; objection canonicalization, a Phase 1 stage that had not been
priced at all, was added; and the profiles were then **recalibrated from
measured `llm_usage`** across two live runs. That recalibration found the model
had been multiplying agent-action cost by the platform count — the swarm is
split across platforms, not duplicated onto each — which inflated the largest
stage of every quote. Estimate against measurement on the reference run is now
1.02x. Margins are unchanged; the cost base was wrong, not the margin policy.

**Billing.** Subscription with a monthly credit grant; every run quoted before it starts and deducted on completion; overage buys more credits.

**Credits are the metered unit; runs are the sales language.** All advertised run
counts are quoted against a defined reference:

> **Standard run** = 100 agents × 5 rounds × 2 platforms × 1 variant → $2.26 COGS

One credit is **$0.001 of COGS**, so a standard run is 2,265 credits. Grants are
denominated in credits because a run varies 65× in cost across the tier caps —
an allowance denominated in runs or agent-rounds rations nothing.

| Tier | Price (US anchor) | COGS grant | Credits | ≈ std runs | ≈ 8-var runs | Margin |
|---|---:|---:|---:|---:|---:|---:|
| Free trial | $0, one run | $0.80 | 800 | 1 (capped) | — | — |
| Founder | **$99/mo** | $19.80 | 19,800 | 8 | 2 | 80% |
| Growth | **$299/mo** | $59.80 | 59,800 | 26 | 6 | 80% |
| Agency | **$999/mo** | $199.80 | 199,800 | 88 | 20 | 80% |
| Enterprise | Custom annual | see `PRICING_GUIDE.md` | | | | 68–78% |

Growth and Agency were re-derived from the cost model on 2026-08-02, replacing
the $499/$1,499 figures inherited from V1 strategy docs. The ladder is now
99 → 299 → 999 (3.0× then 3.3×) rather than 99 → 499 → 1,499 (5.0× then 3.0×);
the 5× first step was the stall point. Margin held at 80% by right-sizing the
grants rather than by discounting compute.

**Credits ration usage; shape caps only prevent runaway spend.** A customer can
push the sliders past the advertised standard run and consume more credits per
run — which must be disclosed in the Run Configurator *before* they commit, not
discovered afterward. Required UI copy and warning states are in
`docs/PRICING_GUIDE.md` Part 1. Overage credits sell at the same 80% margin as
the grant, so a heavy user cannot buy the cheapest tier and load up.

Enterprise/annual quoting, the volume band table, and the `scripts/quote.py`
tool are in `docs/PRICING_GUIDE.md` Part 2.

### Regional pricing

Saibyl's marginal cost is real and location-independent — an LLM call costs the
same in Mumbai as in Manhattan — so a purchasing-power discount comes out of
margin rather than being nearly free. **Regional tiers therefore discount the
subscription and scale the included grant proportionally**, keeping every region
above the 70% floor.

| Region band | Price | Runs | COGS | Margin |
|---|---:|---:|---:|---:|
| Tier 1 — US / EU / UK / AU / CA / JP | $99 | 8 | $19.41 | 80.4% |
| Tier 2 — −40% | $59 | 4 | $12.94 | 78.1% |
| Tier 3 — −60% (incl. India) | $39 | 3 | $9.70 | 75.1% |

Holding the US grant at the Tier 3 price would yield 50.2% margin — below the
floor — which is why the grant scales.

**Implementation.** Separate Stripe Price IDs per band on one Product; store
`organization.pricing_region` at subscription time and re-validate on renewal.
**Eligibility is gated on the card's billing country** (`payment_method.card.
country`), never on IP or a client-asserted value — IP geolocation is for
display only and a VPN defeats it instantly. Band membership should follow a
published PPP list rather than an invented one.

Billing appears on customer statements as **SAIDO LABS LLC**.

**Free-run guardrails.** One per verified email with domain-level dedupe, and a required document upload — that friction filters most tire-kickers. The free report is limited by **scope**, not hidden content: it delivers the sentiment arc and top 3 objections with verbatim quotes, complete and honest, and closes with a specific quantified gap the paid run answers.

---

## 9. Data model additions

New tables (migrations `017`+): `llm_usage` *(shipped)*, `simulation_analysis` *(shipped, 018)*, `canonical_objections` *(shipped, 018)*, `run_quotes` *(shipped, 018)*, `icp_profiles` *(written, 020)*, `inoculation_assets` and `inoculation_results` *(written, 021)*, `clients` (agency layer between org and project), `simulation_variants`, `prediction_outcomes`.

Migration `020` also adds `documents.material_kind` — the adversarial cohort's
grounding, without which the PRD §4 guardrail is unenforceable — plus
`simulations.lens` / `founder_stage` / `icp_profile_id` / `adversarial_share`
and `simulation_agents.is_adversarial` / `adversarial_role`. Migration `021`
adds `simulations.parent_simulation_id` and `inoculation_asset_ids`.

Migration 018 also adds the per-event measurement columns on `simulation_events`
(`valence`, `stance`, `intensity`, `intent`, `is_novel_claim`, `objections`,
`measured_at`, `measure_model`), the credit ledger on `organizations`
(`credits_balance`, `credits_granted`, `credit_cycle_start`, `pricing_region`),
and `simulations.variants` / `simulations.depth`.

Also required: a real org switcher. `get_current_org` silently locks every user to their first membership.

---

## 10. Calibration

Post-launch, users report actuals (real CTR, signups, objections heard in sales calls, press reaction). Saibyl scores its own prediction, displays a per-account accuracy record, and feeds deltas back into archetype priors. This is the answer to "why should I believe synthetic people," it compounds per account, and it is the hardest thing for a competitor to copy.

---

## 11. UI

Sovereign palette: Obsidian `#0A0F1C`, Graphite `#111827`, Sovereign Gold `#C9A227`, Signal Blue `#2563EB`, Insight Violet `#8B5CF6`. Navigation restructured around the three lenses. New surfaces: lens switcher, stage picker, Run Configurator, objection map, variant scoreboard, inoculation workbench, calibration record. The report viewer is rebuilt on `simulation_analysis` with drill-down to agent quotes.

---

## 12. Build phases

| Phase | Scope | Status |
|---|---|---|
| **0** | Dead-code purge, route-collision fix, schema drift, cost model + usage ledger, docs | ✅ Complete |
| **1** | Measurement layer, `simulation_analysis`, report viewer rebuild, Run Configurator, Sovereign palette | ✅ Complete |
| **2** | Founder lens — ICP synthesis, adversarial cohort, five stages, inoculation loop | Built; static gate passed. **Awaiting migrations 020/021 and a live run.** |
| **3** | Marketing lens — N-way matched swarms, objective metrics, virality score | |
| **4** | Crisis lens migration, client layer, calibration, V2 README | |

Per-phase verification gate: `pytest`, `tsc --noEmit`, `eslint --quiet`, live end-to-end run, plus (Phase 1+) a numeric-integrity check that no rendered value lacks a `simulation_analysis` field, and a cost-integrity check that quoted price ≥ measured `llm_usage` cost × margin floor.
