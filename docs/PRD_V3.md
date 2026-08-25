# Saibyl V3 — Product Requirements

**Saido Labs LLC** · Version 3.0 · Status: signed off 2026-08-16 · Supersedes `PRD_V2.md`

> Test your startup on a synthetic market before you bet real money on it.
> Saibyl is the business brain for people who build with AI.

The governing narrative is `05_PRD/Saibyl-V3-Vision.html` (signed off 2026-08-16,
synthesized from a three-round founder interview). Where this document and any
older document conflict — including PRD V2 — this document wins. V2's engineering
remains the foundation: V3 is a **re-aim of the product**, not a rebuild of the
engine. The measurement substrate (PRD V2 §3), audience construction (§4),
matched swarms (§6), cost model (§8), and every verification discipline carry
forward unchanged unless amended here.

---

## 1. Why V3

**The audience changed shape.** V2 targeted "startup and SaaS founders" broadly,
with crisis PR and agency marketing as sibling lenses. The interview sharpened
this: Saibyl's user is the **AI-builder generation** — the millions of people
who can now build products with Claude Code, Codex, and similar tools but were
never taught to validate an idea, position it, or design a site that converts.
They can build anything; they don't know if anyone wants it. Saibyl closes the
business gap the coding tools opened.

**Distribution is already in hand.** The founder has a mailing list of tens of
thousands of founders from HBS Foundry, OutSkill C7, and YC Startup School
cohorts. The audience exists; the product must be worth their trust. Therefore:

- **The launch gate is quality, not billing.** Stripe subscription tiers are
  explicitly deferred (§6). The V2 "hard stop" (Stripe Price IDs) is removed
  from the critical path.
- **The only entry motion at launch is the free first run.**
- **Crisis PR is shelved** (§7): hidden from navigation and marketing, code
  dormant, returns later as a premium module.
- **A new flagship ships: Website Intelligence** (§4) — the launch headline.

## 2. Positioning

One engine, three founder-language jobs:

| Job | Founder question | Engine (state) |
|---|---|---|
| **Evaluate my idea** | Does this pain exist? Who pays? What kills it? | ICP synthesis → swarm → objection canonicalization *(live)* |
| **Test my marketing** | Which message wins, for which goal? | Matched swarms + objective metrics + virality *(built; first live multi-variant run owed)* |
| **Perfect my website** | Why doesn't my site convert, and what exactly do I change? | Page rendering → critic gauntlet → audience reaction → revised page → re-sim proof *(to build)* |
| **Check it's clear to build** | Has someone already patented or trademarked this? | USPTO clearance: trademarks, prior art, pending landscape → tiered risk report *(to build — §11)* |

> **Amended 2026-08-24 by §12.** The "Evaluate my idea" row asks *"Does this
> pain exist?"* of the swarm, and lists clearance as a sibling job. Both are
> corrected in **§12**: existence-of-pain is an empirical question that only
> retrieval can answer, and clearance opens the Validate stage rather than
> sitting beside it. Read §12 before building against this table.

What Saibyl is **not**, for now: a crisis-PR product, a billing exercise, or an
enterprise intelligence platform. The oracle heritage stays in the DNA, not the
pitch. The report reader is a founder, and the people they forward it to.

## 3. Tiered intake

One question — *"Where are you?"* — routes every new project. This replaces the
single upload-first flow.

| Stage | Input | First run |
|---|---|---|
| **Just an idea** | Guided form (below) | Idea evaluation |
| **Something built** | Website URL or HTML upload | Website gauntlet (§4) |
| **A launch coming** | Landing page / deck / PRD / launch copy upload | Objection map + message testing |

**Guided idea form** — five fields, stored as a generated document
(`material_kind='idea_brief'`) so the existing subject-brief pipeline consumes
it unchanged:

1. The problem (one or two sentences)
2. Who has it (the person, not "the market")
3. Your solution
4. What those people use today
5. What you'd roughly charge

The form grounds the simulation *and* teaches an untrained founder the five
questions every customer and investor will ask them anyway. Copy on the form
should say so.

**Free-run guardrail amendment.** V2 §8 required a document upload on the free
run as tire-kicker friction. That requirement is **waived for idea-stage only**
— the completed form is the required substance. Email verification and
domain-level dedupe are retained for all stages.

## 4. Website Intelligence (new flagship)

Working name: **Website Gauntlet** (final founder-facing name is an open item —
do not hard-code the name into copy; use a single constant).

The technique is the "gauntlet loop" pattern (draft → panel of critics → revise
→ re-run until it survives), which is structurally the inoculation loop (V2 §5)
applied to a page instead of a message. Reuse that machinery wherever it fits.

### 4a. Ingestion & rendering (Phase B)

- Accept a **URL** or **raw HTML upload** as a new document kind
  (`material_kind='website_url' | 'website_html'`).
- Snapshot pipeline: fetch → render headless (Playwright, already used in
  verification tooling; becomes a backend dependency) → capture full-page
  screenshot (desktop + mobile viewports), extracted DOM text, meta/OG tags,
  and load-weight basics.
- New table `website_snapshots`: `id`, `project_id`, `document_id`, `url`,
  `html_hash`, `screenshot_paths` (storage refs), `dom_text`, `viewports`,
  `fetched_at`. RLS: `org_isolation`, like every table.
- A snapshot is immutable; re-checking a site creates a new snapshot. Reports
  always name the snapshot date they judged.

### 4b. The critic gauntlet (Phase B)

Five critics, each a structured LLM call with a rubric, judging the rendered
screenshots + DOM text (vision-capable model required — critics look at the
page, not just its text):

1. **Hierarchy** — can a stranger tell what this is and what to do in 5 seconds
2. **Credibility** — trust signals, proof, specificity of claims
3. **Conversion path** — the route from landing to acting, and what blocks it
4. **Copy clarity** — message takeaway accuracy, jargon, reading level
5. **Accessibility & mobile** — responsiveness, contrast, tap targets

Each finding is typed: `{dimension, severity, region (selector or screenshot
coords), verbatim_quote, finding, fix_instruction}`. Per-dimension score 0–100
plus an overall gauntlet score. Findings land in `simulation_analysis` with
evidence pointers like every other number in the product — **no rendered value
without an artifact field** (the V2 Phase 1+ integrity gate applies).

### 4b². Design intelligence augmentation (added 2026-08-16, founder-directed)

Distilled from Jack Roberts' evaluation playbook and the styles.refero.design
DESIGN.md model, and wired onto 4b:

- **Style census** — deterministic computed-style aggregation at capture time
  (fonts/weights, letter-spacing, palette frequencies, radius and shadow
  vocabularies, spacing histogram + base unit). The census is the receipt for
  every design claim.
- **Sixth critic: "The look"** — judges the design *system*. Absolute mode
  checks the slop tells (default-font stack is an automatic finding, palette
  coherence, radius vocabulary size, elevation ladder, spacing rhythm, one
  asset family). Reference mode: the founder names **a site they admire**;
  both sites' censuses are measured against each other and findings carry
  both values ("Your body letter-spacing: 0em. Theirs: -0.011em.").
- **Design DNA** — every check extracts a refero-shaped DESIGN.md artifact
  (characterization line, token tables with roles, do/don'ts, agent-prompt
  guide) the founder can paste into their coding tool, plus a 1–7 design
  maturity level (score = highest level whose signature the site exhibits).
- **The design gallery** — every check's DNA, census, screenshots, and scores
  persist as a `design_gallery` row. Platform-admin routes (`/api/admin/…`,
  gated on `ADMIN_ORGANIZATION_ID`) read the cross-org feed. Strategic
  substrate for the future before/after showcase — flagged in HANDOFF, not
  built.

### 4c. Audience reaction (Phase B)

The synthetic market (existing swarm engine, Founder lens, adversarial cohort
per V2 §4) reacts to the page itself: the snapshot's DOM text + a structured
description of the rendered page ride in the agent action prompts the way a
subject brief does. Objections canonicalize as usual. The website report is one
report: critics say what's weak about the page, the market says what they
wouldn't buy and why, and each claim carries its `event_ids[]`.

### 4d. Revised page & proof (Phase C)

- **Generate the revised page**: improved HTML/copy produced through gauntlet
  iterations — revise → critics re-score → repeat until pass threshold or max 3
  rounds. New table `page_revisions`: `id`, `snapshot_id`, `revision_html`
  (storage ref), `rounds`, `scores_before`, `scores_after`, `created_at`.
- **Before/after presentation**: original beside revision, each critique beside
  its resolution.
- **Re-simulate**: same audience, same seed, against the revised page — the
  inoculation re-run machinery (`parent_simulation_id`, migration 021) is the
  template. Report the measured delta per objection. An unmoved number is
  reported as unmoved (V2's honesty rule).
- **Paste-ready fixes**: every finding's `fix_instruction` is also emitted as a
  prompt block formatted for Claude Code / Codex, so the founder's coding tool
  applies what Saibyl prescribes. This output is a first-class report section,
  not an appendix.

### 4e. Cost model

Two new priced stages in `agent_pricing.py`: **critic pass** and **revision
generation**. Price them the V2 way: profile from measured `llm_usage` on live
runs, not from estimates (remember the platform-count inflation bug — measure
first). The Run Configurator quote must include them; the cost-integrity gate
(quoted ≥ measured × margin floor) applies.

## 5. The wow standard (confirmed 2026-08-16)

Acceptance criteria for every report, in priority order. These are testable
review criteria for the Phase D gate, and the standing bar afterward:

1. **Brutal specificity** — the report names the exact sentence, claim, or
   price that fails. "Improve your value proposition" is a defect.
2. **Voices that feel real** — verbatim reactions read like the actual
   internet; the founder recognizes Reddit and HN in them.
3. **Paste-ready fixes** — every finding ends in something the founder can do
   immediately, including prompts for their coding tool.
4. **Proof of the delta** — before/after evidence from the re-run, with
   receipts.

Supporting change: `REPORT_SYSTEM_PROMPT` still addresses "a McKinsey or
Bloomberg Intelligence analyst." The reader is a founder. Rewrite the register;
keep the evidence discipline.

## 6. Monetization posture

**Amended 2026-08-24/25, founder-directed. Subscription tiers are removed, not
deferred.** The previous version of this section deferred a $99/$299/$999 tier
migration to Phase E and told future sessions to preserve the pricing maths.
That deferral is now a deletion, and the reasoning is in §12e and
`DECISIONS_LOG` 2026-08-24: the ladder existed to justify a recurring charge,
and `founder_stages.py` said so outright — *"five stages are five purchase
occasions for the same account."* Pricing was shaping the product.

- **Founders top up as they go.** Credits are the only ration. There is one
  balance, one price list, and no plan that changes what anybody may do.
- **The free first run** per verified email (guardrails per §3) is the only
  thing Saibyl gives away, and it is **a 30-person room** — raised from 25 on
  2026-08-25. It costs 1,335 credits against a 2,000-credit grant, so the
  founder is left with 665: visibly some, and deliberately too few to buy a
  second service.
- **Two concepts, never one object.** `FREE_RUN_SHAPE` is a *product* — the run
  the grant buys, advertised publicly. `RUN_CAPS` is a *safety limit* — the
  largest shape anyone may configure, which exists to stop a typo rather than
  to ration. Collapsing them is what broke the first attempt at this change.
- **No runs-remaining count, anywhere.** What a founder is shown is what a
  *specific* run costs — this module, this size — quoted before they commit.
  `GET /billing/prices` is that surface. A remaining-runs number has to divide
  by an assumed shape, and every version of that assumption has been wrong.
- **What is gone:** `PLAN_PRICE_MAP`, the per-tier grant and cap tables, and
  the per-plan run allowance. `PLAN_LIMITS` survives only as a flat
  runaway-automation backstop, far above any honest month's use, because a
  monthly cap derived from the grant would bind on the first founder to top up.
- **Still to remove** (next commit): the Stripe subscription paths themselves —
  `/checkout`, `/portal`, `get_subscription_status`, the subscription branch of
  the webhook — and the $99/month argument in `ValueCase.tsx` and
  `SettingsPage.tsx`. Nobody is on a subscription: on the day this was decided
  production held thirteen orgs, twelve `trialing` and one `canceled`, with a
  single Stripe subscription id in the entire system, on the cancelled row.
- Regional pricing and enterprise quoting: gone with the tiers.

## 7. Crisis lens: shelved

- Remove Crisis from the lens switcher, navigation, marketing pages, and all
  launch copy. Gate with a feature flag (`CRISIS_ENABLED`, default false) —
  **no code deletion**. Routes return 404-equivalent when flagged off.
- The Crisis code remains tested; it returns later as a premium module
  (possibly reframed as "launch defense" — a future decision, not this build).

## 8. Debt carried into Phase A

From `HANDOFF_POLISH.md` §5, now scheduled rather than open-ended:

1. Drop `projects.asset_count` + both RPCs (the release that stopped reading it
   is serving; the ordering constraint is satisfied).
2. Rebuild stale `simulation_analysis` artifacts (frozen pre-vocabulary
   sentences) — add a rebuild route or re-run; the Tallyhook run the landing
   page cites must be rebuilt before anyone exports it.
3. Run-setup bugs: picking a stage silently discards a hand-set adversarial
   share; the share slider is unreachable until after the audience is built yet
   the stage default compiles the initial audience.
4. Audit items 19, 39, 40 (40: `report_agent.py` defaults `variant="a"`, so a
   matched-swarm report illustrates whole-run statistics with one arena's
   quotes).
5. Remove the 35 granted test credits on the Tallyhook demo org or annotate the
   ledger.

## 9. Build phases

Per the project's phased-execution rule: complete a phase, run its gate, wait
for the founder's explicit approval before the next. No multi-phase responses.

| Phase | Scope | Gate |
|---|---|---|
| **A — Realignment & debt** | Crisis shelving (§7), tiered intake + guided form (§3), report register (§5), debt items (§8) | pytest / tsc / eslint green · an idea-stage founder completes a free run with no document |
| **IP — Clearance tab** (§11) | Backend USPTO client (ported from the reference server), three-track search, tiered report artifact, the new tab UI, QUICK free teaser, pricing stage | a real invention description produces a STANDARD report with claim deep-reads and honest NOT_SEARCHED/blind-spot statements, and the QUICK teaser runs free end-to-end |
| **B — Website: see & judge** | Ingestion + rendering (§4a), critic gauntlet (§4b), audience reaction (§4c), unified report | a live run against a real founder site produces a critique the founder would forward |
| **C — Website: fix & prove** | Revised page generation, before/after, re-sim delta, paste-ready fixes (§4d), cost stages (§4e) | a re-run shows a measured improvement on a real site; paste-ready prompts apply cleanly |
| **D — The wow gate** | Five real founder ideas end-to-end vs. §5; the overdue cold read (fresh evaluator, no docs, real browser, deployed site); first live multi-variant run | the founder reads all five reports and would pay for each — then, and only then, the first email |
| **E — Deferred** | Stripe tiers, Crisis return, calibration (V2 §10), cohort/bootcamp deals | out of scope until D passes |

**Order DECIDED by the founder, 2026-08-16: Phase IP first, then Phase B —
and explicitly with no approval gate between them** ("Once that's done, with
no gating step, proceed to phase B"). This is a recorded exception to the
per-phase approval rule for these two phases only; Phase C onward returns to
the normal gate. Rationale for IP-first: the smaller build (HTTP APIs only —
no rendering infra), fully specified by the founder's skill, LLM-only margin,
and it monetizes the Validate stage the idea-brief intake just opened.

Standing verification gates (V2 §12) apply to every phase: `pytest`,
`tsc --noEmit`, `eslint --quiet`, a live end-to-end run, the numeric-integrity
check (no rendered value without a `simulation_analysis` field), and the
cost-integrity check (quoted price ≥ measured `llm_usage` cost × margin floor).

And the lesson that closed V2, still the law of this codebase: **look at the
running product, then at what it exports, then query the database before you
explain either — and make sure your check could only have passed for the reason
you think it did.**

## 10. Open items

1. Final founder-facing name for Website Intelligence (working name: Website
   Gauntlet). One constant, no scattered strings.
2. Launch email scope and the welcome offer (one free run vs. idea run +
   website run) — deferred by the founder until the product clears Phase D.
3. Final founder-facing name for the IP clearance tab (working name: IP
   Check). Same one-constant rule.

## 11. IP clearance (added 2026-08-16, founder-supplied)

A new tab: a founder submits a name, an invention description, or both, and
gets a tiered USPTO clearance report — trademarks, granted-patent and
published-application prior art, the pending/provisional landscape, and
(premium) examiner-behavior intelligence. Born from the founder's own
experience: ideas he researched turned out to have 50–100 companies with
patents already on them. The tab answers "is this even mine to build?" —
which makes it the natural companion to the Validate stage.

**Spec of record:** the `ip-clearance-search` skill (installed at
`~/.claude/skills/ip-clearance-search/`, source archive in
`Saido Labs LLC/Provisional Patent MCP and Skill/`). Its methodology is the
product's methodology: Stage-0 classification (name vs invention vs both),
three-axis query decomposition (FUNCTION / STRUCTURE / DOMAIN) with
patent-ese translation, Track A trademarks, Track B prior art with claim
deep-reads, Track C pending-landscape honesty, Track D examiner behavior,
GREEN/YELLOW/RED risk tiers, and the non-negotiable rules (never fabricate
numbers/titles/owners; empty ≠ cleared; date-stamp everything; the
not-legal-advice disclaimer on every output).

**Architecture.** Production calls USPTO APIs directly from the backend — the
founder's `uspto-patent-mcp` server (complete TypeScript implementation in
the same folder, `dist/` bundle included) is the reference client: port its
API-client patterns, the documented quirks (404 = zero hits; TSDR XML
defaults; date-format chaos; PTAB field-name drift), `[NOT_FOUND]`
anti-hallucination discipline, key masking, response caps, and TTL caching
into the Python backend. Keys: `USPTO_ODP_API_KEY` + `USPTO_TSDR_API_KEY`
(separate registrations; the founder holds both) as Render env vars —
production traffic runs on Saibyl's keys with per-org rate limiting, and
PatentsView is the no-key fallback. LLM usage (query decomposition, claim
reading, report composition) goes through the tiered-model policy and
`llm_usage` like every other stage; the USPTO APIs themselves are free, so
margins here are LLM-only — price it accordingly in `agent_pricing.py`.

**Tier mapping** (from the skill, mapped to billing): QUICK = free teaser
(exact-name trademark check + top-10 keyword sweep, one screen); STANDARD =
in-plan, priced per run (CPC sweep, 3–5 claim deep-reads, risk tiers, search
record); COMPREHENSIVE = premium (assignee sweeps, continuity mapping,
examiner behavior, watch-list).

**Report discipline.** The clearance report is a first-class artifact like
`simulation_analysis`: versioned JSON per the skill's output contract +
`queries_run` with hit counts so any run is reproducible, rendered with the
same evidence-pointer drill-down ethos. Every render and export carries the
skill's disclaimer verbatim. Trademark results without a real search return
NOT_SEARCHED, never "clear".

**Data model sketch:** `clearance_runs` (org, project, item, type_hint, tier,
status, quote/credits), `clearance_findings` (per-reference: number, title,
owner, dates, status, risk tier, claim elements, differences), the JSON
artifact on the run row. RLS `org_isolation` as always.

## 12. The founder's journey — corrected evaluation logic (added 2026-08-24, founder-directed)

**This section governs where it conflicts with §2, §3 or §11.** The five stages,
their order, and the tagline *"The platform that grows with you"* are unchanged
and are not in question. What changes is **which instrument answers which
question** — and today the product has it backwards.

### 12a. What prompted it

The founder's own product, ParryAI, in the order it actually happened:

1. He ran his business on AI agents.
2. He hit the failure himself — agents holding access to sensitive information,
   and agents recommending changes to the software stack that would be
   catastrophic if a human applied them unreviewed.
3. He built the fix for himself: prompt-injection defense, a harness to see what
   the agents were actually doing, and a human-approval backstop on any
   recommendation that could cause a catastrophic event.
4. **Only then** did he realise Fortune 500 companies had the same problem.
5. **Only then** did he run a patent search — and find that nobody had done it.

Saibyl's Validate stage asks *"Does this pain exist, who feels it most, and
would they pay?"* and answers it with a synthetic room. That is a question this
founder had already answered from his own operations before he wrote a line of
code — and every founder who builds a product out of a pain they personally hit
is in the same position. **They have ground truth. We are offering them
synthetic opinion about a fact they lived.**

The two questions he genuinely could not answer — *does my own experience
generalise beyond me?* and *has someone already built this?* — are answered
today by `ClearanceCard`, one card sitting below that headline.

This is the whole defect, and it is upstream of every messaging problem the
dogfood runs surfaced.

### 12b. The rule: two instruments, two classes of question

| Class | Question is about | Instrument | Output |
|---|---|---|---|
| **Empirical** | the world — does this pain exist beyond me, who else has it, has it been built, is it defensible, who funds it | **Retrieval** | real records, cited, checkable |
| **Reaction** | response — how does my pitch read, which objection kills it, where do I lose them, what do they push back on | **The room** | ranked objections, sentiment, verbatims |

**The room cannot answer an empirical question, and no amount of validation data
would fix that** — it is a category error, not a data gap. Existence of a market
is not establishable by synthetic opinion at any sample size.

This also retires the objection that has dominated every dogfood run to date —
*"synthetic feedback doesn't correlate with real buyer behavior"* (load-bearing
6.56 on run three, present in 6 of 8 groups, unanswered across three rounds).
That objection is **correct** as applied to empirical claims and **irrelevant**
as applied to reaction claims. We have been arguing it on the wrong ground.
Narrowing the room to reaction questions retires it without needing the
correlation study we cannot yet run.

### 12c. Validate, re-specified retrieval-first

**The stage question changes** from *"Does this pain exist, who feels it most,
and would they pay?"* to:

> **"Is it just me — and has anyone already built it?"**

Retrieval leads; the room is optional and secondary. The stage's deliverable is
**facts with citations**, not a sentiment score.

Order of the stage, and the order is the argument:

1. **Prior art and trademark clearance (§11) opens the stage.** Promoted from a
   card to Validate's first move. This is the only capability in the product
   with **zero correlation exposure** — it cites the patent office — and it is
   the sharpest fear an AI-builder founder carries, because shipping in a
   weekend means fifty other people plausibly shipped it that same weekend.
   Front-loading a claim nobody can call a mirror is what earns the credibility
   the room's claims need later.
2. **Who else has this problem** — real evidence of the pain in the wild, so the
   founder learns whether their n=1 generalises. This is the step the founder
   took at ParryAI stage 4, and **no surface returns it today.** The nearest
   existing machinery is `gtm/discovery` — real-company search, already bounded,
   billed and reconciled — but it is aimed at *who do I sell to*, not at
   *who else has this pain*. Build this by re-pointing that query compiler, not
   from scratch.
3. **Who has already shipped it** — competitor discovery, real companies.
4. **Then, optionally, the room** — and only on reaction questions.

**`founder_stages.py` must be re-cut accordingly.** Two of
`concept_validation`'s five `report_questions` are empirical questions put to
the wrong instrument and come out:

- *"Do agents recognise this pain unprompted, or only when named?"* — a proxy
  for real-world prevalence, measured synthetically.
- *"Is there stated willingness to pay, and at what shape of price?"* — the
  stage's own `cannot_conclude` already says pricing "indicates direction, not
  a number." **A stage that declares it cannot conclude a thing must not list
  that thing as a question it answers.** That contradiction ships today.

*"What would disqualify a solution before they tried it?"* is a genuine reaction
question and stays.

### 12d. Raise gates on real recurring revenue

Founder's sequence, verbatim: *"After they've done all of those things and they
have monthly recurring revenue, raise money from prospective investors."*

`capital/matching.py` already handles the *firm* side of this well — it will
report *"these four state they do not invest pre-revenue"* rather than pad a
list. **Nothing gates the founder.** Today Saibyl will run a fundraise for an
account with zero customers and hand back a polished report, which makes the
platform complicit in precisely the self-delusion it exists to prevent.

**Decided:** Raise requires declared recurring revenue.

Per the standing rule, this is **not** a `disabled` control. A stage either runs
and states plainly what its answer will be missing, or it is blocked with the
control that unblocks it and the reason beside it. There is no third rendering.

The gate is also the strongest retention mechanism in the product: the founder
comes back when the revenue is real. That is a better subscription argument than
five purchase occasions, and it is honest.

### 12e. What this makes true of the tagline

*"The platform that grows with you"* stops being a slogan on top of the
architecture and becomes a description of it. Each stage deposits **real
evidence** into the founder's record — prior art, companies with the pain,
ranked objections, which fixes actually moved the number, real prospects — and
each later stage consumes what the earlier ones deposited. `capital/matching.py`
already states this as its own defensible claim: *"Saibyl knows things about
this founder no list vendor does — the objections real buyers actually raised."*

The platform grows with the founder because it **accumulates their record**, not
because its claims escalate. That distinction is the difference between a
product the room believes and the one it stopped believing at stage three.

### 12f. Consequent amendments

- **§2**, "Evaluate my idea" row: the founder question and the engine are both
  restated by §12c. Clearance is no longer a sibling job — it opens Validate.
- **§3**, tiered intake: "Just an idea" must route to retrieval first. The
  guided form stays (it teaches the five questions), but the first thing the
  founder receives back is a clearance and prevalence read, not a room.
- **DECISIONS_LOG 2026-08-23 item 3** — "the USPTO clearance check folds into
  Validate, **as a card**" — is superseded. It folds into Validate as the
  **opening move**.
- **§9** Phase IP's rationale ("it monetizes the Validate stage the idea-brief
  intake just opened") is strengthened, not changed: Phase IP now *is* Validate's
  front door, so its ordering ahead of Phase B stands on firmer ground.
- `founder_stages.py`'s docstring cites "PRD §5" for the stage registry; §5 of
  this document is the wow standard. The reference is stale — it should cite
  §12.
