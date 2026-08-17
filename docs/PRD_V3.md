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

- **Free first run** per verified email (guardrails per §3) is the only
  promoted motion at launch.
- The **credit top-up stays live but unpromoted** (it needs no Price ID).
- **Stripe tier migration ($99/$299/$999) is deferred to Phase E.** The pricing
  math in `PRICING_GUIDE.md` and PRD V2 §8 remains valid and preserved — do not
  delete it, do not build it yet. `stripe_service.py`'s stale V1 prices are
  quarantined behind the deferral, not fixed in place.
- Regional pricing, enterprise quoting: unchanged from V2, also deferred.

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

Phase IP's position in the order is the founder's call; the recommendation
is **IP before B**: it is the smaller build (HTTP APIs only — no rendering
infra), its methodology is fully specified by the founder's skill, the USPTO
APIs are free so margin is LLM-only, and it monetizes the Validate stage the
idea-brief intake just opened.

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
