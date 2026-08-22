# Pre-launch bug register

**Opened 2026-08-17.** Produced by a four-method hunt after the app-shell
restyle: a brand-new production account walked end to end with console and
network capture, three blind static audits (dead ends, frontend↔backend
contract, error handling and money), and a live pipeline exercise of all five
founder stages. Ranked by what it costs the founder who hits it.

**Evidence discipline used here:** every P0 below is marked either
**[verified]** — I reproduced it against production data or read both sides of
the contract myself — or **[audit]** — reported by a static audit with a
file:line I have not personally re-run. Nothing is listed on reasoning alone.
Two independent methods (a visual critic reading pixels and a contract audit
reading code) landed on the same defect twice; those are noted.

---

## What is NOT broken (checked, so nobody re-checks it)

- **Migrations 026–031 are applied.** Two migration files still carry stale
  `-- NOT APPLIED` headers, which sent an audit into a panic. All ten tables
  (`gtm_discovery_runs`, `subject_briefs`, `credit_topups`, `persona_packs`,
  `custom_persona_packs`, `simulation_variants`, `page_revisions`,
  `website_snapshots`, `design_gallery`, `clearance_runs`) exist in
  production. **Fix: delete the stale headers**, they are a trap.
- **Signup works end to end** — a brand-new account was created, landed on
  `/app/home`, and every empty-state page rendered with **zero console errors
  and zero failed requests**. Empty states across home, reports, IP check,
  settings, runs, uploads, audiences, companies, messages, guide are all
  well-formed with working CTAs.
- **Product creation works** (`POST /projects` → 200, product appears).
- **Endpoint existence and method: clean.** ~60 frontend calls all resolve to
  a real backend route with the right verb; no route shadowing.
- **The five-stage pipeline runs.** All five founder stages cleared intake →
  idea brief → audience synthesis → confirm → create → prepare → start with
  200s (see §Pipeline at the bottom).

---

## Status — 2026-08-17 night

**Fixed, shipped to production, and verified live:** P0-1 (the room's prove
leg), P0-2 (the 0.00 feed), P0-4 (credits contradiction), P0-5 (the free-plan
lie), P0-10 (no error boundary), P1-6 (dead error fallbacks), P1-8 (no axios
timeout). Master = `ab0dc98`; discriminators and live screenshots recorded in
INFRA_LOG.

**Found while shipping, and fixed:** the CI gate had **never executed a single
test** — `uv sync --dev` installed nothing because the dev tools are declared
as an *extra*, so the step died at `ruff` — and once running, CI had no Redis.
Both fixed; the Tests workflow is green for the first time. The Render
deploy-hook secrets are empty, so that job cannot work; production updates
through Render's own GitHub auto-deploy. Founder decision recorded in
INFRA_LOG.

**Still open below:** P0-3, P0-6, P0-7, P0-8, P0-9, P0-11, and the P1/P2
tails. Two need a founder decision before code (P0-7 flagship vs free grant,
P0-8 wire Google or remove it).

---

## Status — 2026-08-21 (the last build push)

**Closed and deployed:** **P0-3** (the live run feed had subscribers and no
publisher — `services/streaming/publish.py`, plus the vocabulary collision
between the browser's `event_type` and the adapters' `EventType`), **P0-6**
(the quote omitted `subject_brief` while the charge included it; `RunShape`
now carries an optional `simulation_id` and both pricing paths ask the same
question the charging path asks), **P0-9** (`PLAN_LIMITS` held only the V2
tier names, so every V3 tier fell through to the free allowance; now derived
from `TIER_CREDIT_GRANTS` at ten times what the grant buys, so credits ration
and this only stops a runaway loop).

**Found by the three sample products and closed the same day** — see the
sample-pipeline section at the bottom: a malformed model response destroying
a paid artifact (no retry, *and* `ValidationError` subclassing `ValueError` so
the pydantic error reached the founder), credits kept for a capture that never
loaded a page, the capital shortlist recommending a firm on funding stage
alone, and a website check able to hang at `capturing` forever because
`chromium.launch()` was outside the timeout.

**Also closed:** three artifacts that were priced and charged but absent from
`GET /billing/prices` (`messaging_doc`, `outbound_sequence`,
`capital_shortlist`), so the founder met the price as a 402 at submit. A test
now reads the pricing module and requires every artifact it finds to be
published.

**Still open:** P0-7, P0-8, P0-11, and the P1/P2 tails. **P0-11 is confirmed
live** — all three sample products got a 503 from IP Check because
`USPTO_ODP_API_KEY` is unset in Render. The guard refuses before creating or
charging, so nothing is lost, but the module is dead in production until the
keys are pasted.

---

## The loss leader, exercised on a real free account (2026-08-17 night)

Run against production as a genuinely free org, from the five questions to
the report, on the 1,500-credit grant. **The evaluation itself works**: buyers
synthesized and confirmed, run started and charged, complete in 235s, 19
objections, headline valence 0.272 (95% CI 0.106–0.438, n=25), two report
sections of 9.0K and 10.3K characters.

**Then the write-up failed.** `reports.status = 'failed'`, no Executive
Summary, and the final section row — "Strategic Implications & Recommended
Actions" — persisted with **null content**. The founder is left holding a
completed run, no report, and a balance of **0**: the grant is spent, so on
the free tier there is nothing left to run again with.

Two defects, both now fixed:

- **P0-12 · The failure screen was a dead end.** It said the write-up "has not
  been started again" and then offered no way to start it — reached, by
  definition, only by someone who has already paid. `regenerateReport` already
  existed in that file and is **free** (`POST /reports/generate` charges
  nothing; nobody goes back in the room), it was simply never wired to the
  failure it exists for. Now offered, with the honest sentence that the run is
  safe and only the write-up needs redoing.
- **P1-9 stands and now has a face.** Credits are charged at run start and
  never refunded on failure. A free founder whose one run's write-up dies has
  spent the entire grant. Recovery is free, so this is survivable — but only
  because the button now exists.

**Still open (founder's call): report generation is not retried server-side.**
The section died mid-write and nothing tried again; the same shape succeeded on
five concurrent runs an hour earlier, so it reads as a transient model failure.
A single automatic retry on a failed section would make the loss leader
reliable without any UI at all.

## The revenue bridge does not exist yet

The model is: idea evaluation free, then pay for the website check and the
USPTO clearance. The free half works. **The paid half is never offered.**

Verified by grep across the whole frontend: **nothing links to `/app/ip-check`
except the sidebar nav item**, and no post-run surface — not the report, not
the product home, not the rail — contains the words patent, trademark or USPTO
anywhere. The website check is reachable only as an *intake path* on the
audience step, never as a paid product a founder is invited to buy.

So the conversion moment — a founder has just read 19 objections about their
idea and is thinking "is this even mine to build?" — is unbuilt. That is the
highest-value remaining work for revenue, and it is small: an offer block at
the end of a finished evaluation naming both checks and their prices, which
`GET /billing/prices` now serves. **Not built unprompted — placement and copy
are the founder's call.**

## P0 — Launch blockers

### P0-1 · The flagship "prove it with the room" leg can never run **[verified]**
`backend/app/api/website_room.py:47` gates on
`revision.get("revision_html") or revision.get("revision_text")`.
**Neither column exists.** `037_page_revisions.sql:56` declares `html_path`,
and `workers/revision_tasks.py:181` writes `"html_path": paths["html"]`.
`services/website/room_run.py:248,252` reads the same two phantom keys.
→ Every "Prove it with the room" click returns *"That revised page hasn't
finished building yet"* on a page that finished building. The proof-of-delta
leg is the PRD's headline claim for the flagship.
**Fix:** read `html_path` (and fetch the stored HTML) in `_revision_is_complete`
and in `room_run.py`. One-line gate change plus the body fetch.

### P0-2 · Every event in the run feed reads "how they took it: 0.00" **[verified]**
`frontend/src/pages/SimulationDetailPage.tsx:643` reads
`(evt.metadata)?.sentiment`; the backend writes a **flat `valence` column**
(`event_measurement.py:247`).
**Production proof:** of 2,798 measured events, **2,794 have `valence` and
exactly 0 have `metadata.sentiment`.** Every event on every run since the
Phase-1 rewrite has rendered 0.00.
Two independent methods found this: a blind visual critic ("a column of
identical zeros reads as broken placeholder data") and the contract audit.
**Fix:** read `evt.valence`, render null as "not scored" rather than 0.00.

### P0-3 · "Watch it live" shows nothing, forever **[verified]**
Two independent causes, either alone fatal:
1. **Nothing ever publishes simulation events.** The only `r.publish` in the
   whole backend is `report:{report_id}:progress`
   (`report_agent.py:840`). The bridge subscribes to `simulation:*:events`,
   which no code writes to.
2. **The vocabularies do not overlap.** The frontend subscribes to
   `agent_action`, `round_start`, `round_end`, `simulation_completed`
   (`SimulationRunPage.tsx:66-72`); the backend's `EventType` is
   `Literal["post","comment","react","dm"]` (`base_adapter.py:55`). A third
   vocabulary exists in `event_schema.py:47` that nothing produces.
→ The founder clicks "A run is going now — watch it" and sits on *"Waiting for
the first reaction…"* while a paid run executes fine server-side.
**Fix:** publish measured events to `simulation:{id}:events` from the runner
and align on one vocabulary (prefer the adapter's, mapped at the edge). Until
then, the poll-only fallback should at least drive the counters.

### P0-4 · The app tells a brand-new founder they have zero runs **[verified]**
Seen on a brand-new account: sidebar shows **"Credits left 1,500"**, a **100%
full bar**, and **"About 0 more runs — add more"** simultaneously.
Both numbers are arithmetically correct and neither answers the question:
`AppLayout.tsx:192` computes `floor(balance / standard_run_credits)` =
`floor(1500 / 3014)` = **0**, but `standard_run_credits()` is the price of a
**100-agent, 5-round** run that a free account is **capped out of configuring**
(`TIER_CAPS["free"].max_agents = 25`). A run at the free cap costs **1,273**,
so the grant genuinely covers **one full free run with 227 credits spare** —
which is exactly what the landing page ("1 COMPLETE RUN · 25-PERSON ROOM") and
`PRICING_GUIDE.md` ("1 capped") promise.
→ The free run is the entire launch motion, and the chrome denies it on every
page. Worse: a founder who tops up $10 (1,500 credits) still sees "About 0".
**Fix:** `/billing/credits` must return the price of a run **at this tier's
cap**; the sidebar divides by that. Backend already returns `caps`
(`api/billing.py:231`) but not a tier-appropriate price, so this cannot be
fixed frontend-only.

### P0-5 · Settings tells free accounts they are on the $99/mo Founder plan **[audit]**
`SettingsPage.tsx:85-93` — `LEGACY_PLAN_ALIAS` maps `free → 'founder'`, so a
non-paying account renders **"Your plan: Founder · $99/mo"**, while
`AppLayout.tsx:256` renders the raw plan **"FREE"** one panel away. Two
surfaces, opposite answers, on the page that asks for money. Second-order: a
**failed** `/billing/status` also lands here (`billing === null` →
`resolvePlan(undefined)` → `'founder'`), fabricating a billing fact from an
error.
**Fix:** alias only genuinely legacy names; render `free` as Free with the
grant, and render an error state when billing fails to load.

### P0-6 · The quoted price is 8–14% below the price charged **[audit]**
`run_quote.py:136-165` (`issue_quote`) and `api/billing.py:275-281`
(`/billing/estimate-cost`, which drives the Run Configurator's live price) both
call `estimate_simulation_cost` **without `subject_brief`**. But
`reconcile_run_cost` charges the measured difference afterwards
(`analysis_tasks.py:173-176`), and `max(0, …)` makes it one-way: overruns are
charged, underruns never refunded. Executed gap for any project with uploaded
material — the main path: free cap +93 (7.9%), standard **+278 (10.2%)**, large
**+1,148 (14.3%)**. The founder is never told; `shortfall` appears in zero
frontend files.
This violates the codebase's own rule at `RunConfigurator.tsx:250`: *"the cost
shown must be the cost charged."*
**Fix:** thread `subject_brief` into both quote paths.

### P0-7 · The flagship costs more than the entire free grant **[audit]**
`website_check_credits()` = **1,750**; free grant = **1,500**. Website
Intelligence is the PRD's launch headline, and a new founder fills in the form
then gets a hard 402 *after* doing the work (`api/website.py:153-161`);
`SiteCheckForm.tsx` never shows the price up front. Also unaffordable on the
grant: page revision (5,000), IP check STANDARD (2,000) / COMPREHENSIVE
(6,000). (IP check QUICK is free and is the form default, so that first click
does work.)
**Fix (founder's call):** raise the grant above the flagship's price, or price
a free tier of the check, or show the price and the shortfall *before* the
work. Add the missing test asserting the grant covers the flagship.

### P0-8 · "Continue with Google" is a dead end on both auth screens **[verified]**
`LoginPage.tsx:88-91` / `SignupPage.tsx:120-123` call
`supabase.auth.signInWithOAuth` and **never exchange the Supabase session for
an app JWT** (the TODO says so). `onAuthStateChange`/`getSession` appear
nowhere in `src/`. **Production proof:** all 11 accounts are email/password;
**zero** have a Google identity — nobody has ever completed this flow.
It is the first and most prominent button on both pages.
**Fix:** wire the session→JWT exchange, or remove the button until it exists.
Removing is a 10-minute change; the button is currently the default path a new
visitor takes.

### P0-9 · Paying Growth and Agency customers are capped at 15 runs/month **[audit]**
`stripe_service.py:37-41` — `PLAN_LIMITS` holds only `starter`/`pro`/
`enterprise`; line 394 falls back to `starter` for every V2 tier name. Growth
($299, paid for 19 runs) and Agency ($999, paid for 66) are both enforced at
**15** by `api/simulations.py:503` with a bare 402. An Agency customer loses 51
runs of paid capacity. `AppLayout.tsx:281-288` documents this exact bug as the
reason the sidebar's counters were removed — the **display** was fixed, the
**enforcement** was not.
**Fix:** add `founder`/`growth`/`agency` to `PLAN_LIMITS`. (Gated behind the
Stripe tier migration for billing, but the limit table is independent.)

### P0-10 · No error boundary anywhere → any render throw is a permanent white page **[audit]**
Zero matches for `componentDidCatch|ErrorBoundary|getDerivedStateFromError|
errorElement` in the frontend; no `@app.exception_handler` in
`backend/app/main.py` either. This is a **severity multiplier** on every other
finding — and there is a live path to it: `LoginPage.tsx:76-82` casts an error
`detail` as a string, but a FastAPI 422 returns an **array**, so
`setError(array)` throws *"Objects are not valid as a React child"* → blank
login page with no recovery but a manual reload.
**Fix:** one boundary at the router root + gate `errors.ts:23`. Cheapest
highest-value fix in this register.

### P0-11 · IP Check 503s in production right now **[verified — env, not code]**
`USPTO_ODP_API_KEY` and `USPTO_TSDR_API_KEY` are still unset in the Render
backend env, so one of four core nav items returns an honest 503. Keys are
probe-validated and sit in the repo root `.env`. Also owed:
`ADMIN_ORGANIZATION_ID=231b7f17-d17c-4f6e-b530-f0196acd841b`.
**Fix:** founder pastes three env vars into Render. No code.

---

## P1 — Wrong data, or controls that do nothing

| # | What | Where | Consequence |
|---|---|---|---|
| P1-1 | Product filter silently dropped | `BuyersStagePage.tsx:142` links `?project_id=`; `ProspectsPage` never reads or forwards it | Founder sees **every** company in the workspace believing they are this product's buyers. Silently wrong beats a 404. |
| P1-2 | Revision before/after table always empty | writer nests `{overall, dimensions:{}}` (`revision_tasks.py:215`), reader expects flat (`website/types.ts:262`) | Per-dimension deltas render as nothing. **Same bug class already fixed once** on the writer side — the reader was missed. |
| P1-3 | "Run this again" carries nothing | `ReportViewerPage.tsx:505` writes `?clone=`; `NewSimulationPage` reads only `project`/`founder_stage` | The payoff screen's CTA drops the founder into a blank wizard. |
| P1-4 | Four dead buttons | `SimulationsPage.tsx:392,399,587,596` — bulk Export/Archive, row Duplicate/Archive, all TODO bodies | Row items also `stopPropagation`, so clicking produces *zero* response. |
| P1-5 | Failed list renders as authoritative empty state | `SimulationsPage.tsx:150` (no error state at all), + `NewSimulationPage`, `ProspectDiscoverPage`, `ProspectsPage` | A founder with 40 paid runs is told "No runs yet" when the request fails. `ProjectsPage.tsx` already solves this with a `loaded` flag — copy it. |
| P1-6 | Every hand-written error fallback is dead on a 500 | `errors.ts:23` returns `err.message` before the caller's fallback | ~65 written sentences never render; founders see "Request failed with status code 500". |
| P1-7 | Raw Python exceptions rendered to founders | `simulation_tasks.py:1009` → `SimulationDetailPage.tsx:433`, + 5 more pipelines | e.g. `[run_simulation] KeyError: 'organization_id'` in monospace. The good pattern exists (`website_tasks.py:182` `GENERIC_FAILURE_MESSAGE`). |
| P1-8 | No axios timeout | `api/lib/api.ts:3-6` | A stalled request (cold Render backend) = permanent textless spinner on `ProtectedRoute`, the founder's first load. |
| P1-9 | No refund on failure | every worker except GTM discovery | A free user whose only run crashes loses the entire grant; code concedes "the only remedy is a manual refund". |
| P1-10 | Persona pack library renames/deletes 404 | FE sends row UUID (`packs.ts:25`), BE resolves slug `pack_id` (`api/packs.py:130`); list returns **both**, FE type declares only `id` | Library edits fail. Same UUID also feeds `persona_pack_ids` on a run, where a miss is swallowed — chosen audience silently dropped. |
| P1-11 | Forgot password / org selector do nothing | `LoginPage.tsx:318`, `AppLayout.tsx:248` | Both render as live controls. Settings already documents that resets go through `info@saidolabs.com`. |
| P1-12 | Upgrade CTA ejects to marketing and doesn't scroll | `SettingsPage.tsx:205` `to="/#pricing"`, no hash-scroll handling anywhere | The monetization CTA lands at the top of a long public page. |

---

## P2 — Polish, and the debt the critics named

404 redirects logged-in users to the public landing page with no explanation
(`App.tsx:115`) · three native `window.confirm` modals · `#clearance-form`
anchor doesn't scroll (React Router intercepts) · Terms/Privacy on signup are
`<a>` not `<Link>`, so they full-reload and discard a half-filled form ·
`GET /api/products/<non-uuid>` returns **500** where it should 404 · money
format drift on Settings ("$20" vs "$20.00") · platform chips render "R"/"x" ·
sidebar labels vs page titles ("Home" → "Your products") · the audience step
offers four entry points for one upload · `maturity_level` and GTM `excluded`/
`delivery` fields computed by the backend and never rendered.

---

## The systemic root cause worth one decision

**Zero `response_model=` declarations across all 23 modules in
`backend/app/api/`.** FastAPI therefore performs no response validation
anywhere, and the OpenAPI schema is untyped — there is no server-side contract
for the frontend to drift *from*. P0-1, P0-2, P1-2, P1-10 are all the same
defect wearing different clothes. Adding response models to the ~10
highest-traffic routes converts this entire bug class from silent to loud.

Second: **the test suite (1,318 backend + 16 frontend, all green) asserts the
model is self-consistent, never that the customer-visible semantics are true.**
No test asks what "runs left" means, whether the grant covers the flagship, or
whether quoted equals charged. Each P0 fix below should land with the assertion
that would have caught it.

---

## Fix plan

**Wave 1 — stop the lying (highest value per line changed)**
1. P0-10 error boundary + `errors.ts` fallback gate — caps the blast radius of everything else.
2. P0-2 read `valence` — one-line, kills the "0.00" that undermines every number on screen.
3. P0-4 tier-aware "runs left" (backend returns the capped-run price) + P0-5 plan display — the app stops contradicting itself about money.
4. P0-11 three env vars in Render (founder, no code).

**Wave 2 — the flagship works**
5. P0-1 website-room gate reads `html_path` — restores the proof-of-delta leg.
6. P0-3 publish simulation events + one vocabulary — restores "watch it live".
7. P1-2 revision before/after reader, P1-10 pack identity, P1-1 product filter.

**Wave 3 — money is honest**
8. P0-6 thread `subject_brief` into both quote paths (quoted == charged).
9. P0-7 founder's decision on the flagship vs the free grant, then the test.
10. P0-9 `PLAN_LIMITS` tier names.

**Wave 4 — dead controls and error paths**
11. P0-8 Google button (wire or remove — recommend remove for launch).
12. P1-4/11/12 dead buttons, P1-5 `loaded` flag across five pages, P1-6/7 error text, P1-8 axios timeout, P1-9 refund policy.

**Wave 5 — the ratchets**
13. `response_model=` on the top ~10 routes.
14. A test per P0, and one cheap acceptance ratchet: *every query param written into a link literal must be read by the destination page* (catches P1-1 and P1-3 as a class).

---

## Pipeline exercise — all five founder stages

Run 2026-08-17 against production at 25 agents × 3 rounds × 2 platforms, from
the five-question idea brief through audience synthesis to a finished report.
Five concurrent pipelines, one per founder stage.

**Result: the engine is healthy. All five stages completed with zero
problems.** Every step returned 200 — project, idea brief, ICP synthesis,
confirm, create, prepare, start — and every run finished in 186–233s.

| stage | run | objections | report | sections |
|---|---|---:|---|---:|
| concept_validation | complete (233s) | 25 | complete | 4 |
| pre_launch_positioning | complete (201s) | 14 | complete | 4 |
| launch_gtm | complete (187s) | 17 | complete | 4 |
| growth | complete (186s) | 12 | complete | 4 |
| fundraise | complete (186s) | 17 | complete | 4 |

Each report carries an Executive Summary (5.2–5.6K chars), two
stage-specific sections (9–11.5K each) and Strategic Implications
(9–11.8K). Headlines carry real measured values — e.g. launch_gtm: valence
mean 0.547 (CI 0.356–0.737, n=24), 67.6% support / 10.8% oppose, trajectory
flat.

**The founder stage genuinely drives the report.** The section titles are
written to the stage's question, not templated:
- concept_validation → *"Does the pain exist and is it unprompted?"*
- pre_launch_positioning → *"Objection Gravity: What Stops the Room, and Who It Stops"*
- launch_gtm → *"Message-Channel Fit, Objection Timing, and Pre-Launch Positioning"*
- growth → *"Platform Dynamics and the Geography of Resistance"*
- fundraise → *"What Readers Believed and Where the Story Lost Them"*

Objections read as real buyer language — the top one on three of five runs
was a variant of *"synthetic objections won't match real customer
objections"*, which is the honest thing this audience would say.

**Two false alarms worth recording, both caught by re-checking rather than
reporting:**
1. *"Strategic Implications is 0 chars"* on four of five runs — a **race**,
   not a bug. Sections stream in as they are written; all four had 9–12K
   chars four minutes later.
2. *"report status=generating"* on four of five — the same race. All five
   read `complete` on the settled poll.

A third apparent failure — *"analysis returned no headline"* and *"report has
zero sections"* on all five — was **my harness reading the wrong keys** (the
artifact nests under `artifact`; sections have their own route). The product
was right and the test was wrong, which is the failure mode this register
exists to avoid asserting.

**Conclusion: the defects in this register are in the UI, the money layer and
the contracts — not in the engine.** The thing the product is sold on works,
at every founder stage.

---

## Sample-product exercise — 2026-08-21

Three products built as real sample projects and driven through **every**
module against production: **Chartwell** (medical SaaS, prior-authorisation),
**Ledgerline** (fintech, multi-entity treasury), **Parry** (prompt-injection
security). Chosen so the category-aware paths — `verticals.py`, the redesign
brief, the capital matcher's sector — see genuinely different material rather
than three flavours of one thing.

**What worked, first time.** All three rooms completed (217/218/263s) with
22/24/31 canonical objections and reports of 39k/36k/35k characters. Answer
packs 3/3. Messaging documents 3/3. Capital shortlists 3/3, each considering
7 firms and returning 3 matches with refusals reported rather than dropped.

### S-1 · One malformed response destroys a paid artifact — **fixed**

Chartwell's outbound sequence died on truncated model JSON. Two causes, both
closed:

- `llm_structured` made exactly one attempt. It now retries twice, handing the
  model its own output and the parser's error, with every attempt recorded to
  the cost ledger.
- **`pydantic.ValidationError` subclasses `ValueError`.** All three GTM
  workers catch `ValueError` to pass through deliberate refusals, which carry
  a founder-readable sentence — so a malformed response took that branch and
  the founder was shown *"1 validation error for _Generated / Invalid JSON:
  expected `,` or `}` at line 16 column 375"*. This is P1-7's exact shape
  arriving through a door nobody had checked. A test now pins the `except`
  ordering, because reordering them would silently restore it.

### S-2 · Credits kept for work never done — **fixed**

Parry's website check failed because the site did not answer in 45 seconds: no
page captured, no critic run, no model called, 1,750 credits kept, and a
message inviting the founder to try again at the same price. `refund_credits`
now returns the charge on failures **before any model spend**. A check that
died halfway through its critics is not refunded — a rule that quietly
sometimes pays is worse than one that says plainly when it does. This is the
first crack in P1-9.

### S-3 · The shortlist recommended a firm for no reason — **fixed**

Parry was matched with the Charles H. Hood Foundation, a paediatric health
funder, on a reason list of one row: `stage`, "seed" ↔ "seed". Stage, cheque
size and geography are qualifiers — they rule a founder out, but satisfying
one says only that nothing disqualifies you. A match now needs the objection
bridge, a thesis overlap, or a published sector.

### S-4 · A website check could hang forever — **fixed**

Two checks sat at `capturing` for twelve minutes with no screenshots and no
error. `timeout_s` bounds `page.goto`; it never bounded `chromium.launch()`,
and three checks starting within four minutes on one instance was enough. The
whole capture now runs under a hard deadline, and at most two browsers run per
process — the deadline makes the failure honest, the pool stops it happening.

### S-6 · The Website Gauntlet cannot read a real website — **CLOSED 2026-08-22**

**Resolved.** The founder moved the instance to Standard (1 vCPU, 2 GB) and
the flagship module reads real websites for the first time. Measured against a
commit confirmed through `/health`:

| site | capture | full check | text | critique |
|---|---|---|---|---|
| stripe.com | 11s | 136s | 12,084 chars | 79 |
| simplepractice.com | 21s | 156s | 4,636 chars | 67 |

Both had **never once completed** in the entire production history. Every
attempt before this failed or wedged.

**And the case that used to kill the service now holds.** Two heavy captures
started together: both completed (150s, 160s) while an unrelated billing
endpoint was polled throughout — **48 calls, 0 failures**. On the old plan
that combination returned 502 across every endpoint. Concurrency raised from
one browser to two, which is what the 2 GB buys.

It took both halves. The code fixes below made the failures legible and
bounded; the CPU is what moved a capture from "never finishes" to eleven
seconds. Neither alone would have been enough — and the code fixes had to come
first, because until the event loop was unblocked every symptom pointed at the
wrong cause.

The history is kept below because the wrong turns are the useful part.

---

**The original finding, and the investigation that corrected it:**

Read off the production table rather than inferred: the last website check to
complete was **2026-08-17**. Since then, twelve failures and none finished.
And every check that has *ever* completed in this database was the same small
Vercel page. **Every attempt at stripe.com or simplepractice.com — the kind of
site a founder actually submits — has failed or hung, every time.**

What was found and fixed along the way, none of which was the cause:

- `chromium.launch()` took **no arguments**, so Chromium was capped at the
  container's 64 MB `/dev/shm`. `--disable-dev-shm-usage` and the usual
  container flags now ship. Correct, standard, and **did not fix it**.
- Everything after `page.goto` was unbounded — `page.evaluate` has no default
  timeout, and the style census walks the whole DOM. Now bounded.
- Concurrent captures OOM'd the 512 MB instance and returned **502 across
  every endpoint**, taking down runs and billing calls. Capped at one browser.

### The investigation, after the founder asked "leak, or genuinely more memory?"

That question was worth asking and the first answer — "raise the plan" — was
wrong. What follows is what the evidence actually showed, in order.

**1. Storage was blocking the event loop. This was the big one.**
`get_supabase_admin()` returns `supabase._sync.client.Client`, and `store.py`
called `bucket.upload(...)` directly inside `async def`. A multi-megabyte
screenshot upload held the loop for its whole duration, so no request was
served, Render's health check timed out, and the platform returned **502 on
every endpoint** — which is precisely what an out-of-memory box looks like
from outside. Six call sites moved onto threads. *This is why it looked like
a memory problem and was not.*

**2. It also explains why the deadlines never fired.** A blocked loop cannot
run its own timers. With the loop free, `asyncio.wait_for` cancels Playwright
exactly as expected — which the next three failures demonstrated by firing
cleanly at 150s, at a step timeout, and at the overall ceiling.

**3. Three real performance bugs, each found by the next clean failure:**
- `wait_until="load"` waited for every analytics beacon and chat widget. Now
  `domcontentloaded` plus a bounded settle.
- The **optional** style census ran **before** the **required** page text, so
  a heavy page spent its budget on a nice-to-have and failed on the essential.
- `innerText` forces a full layout recompute to decide what is visible; on a
  long page at half a CPU that exceeded 45 seconds. Tried briefly now, with a
  layout-free tree-walk fallback that skips `<script>` and `<style>`.

**4. A defect I introduced while fixing the others.** The one-browser
semaphore let a wedged capture swallow every check behind it: `wait_for`
cancels a task and then *awaits* its cancellation, so a wedged browser leaves
the deadline waiting, the slot is never released, and later captures blocked
on `acquire()` — outside the deadline, with no ceiling at all. The symptom was
identical to the original fault, so **several "still hanging" results reported
during this investigation were this, not the wedge.** The queue wait is now
bounded and the two cases say different things.

**What remains true, measured on a fresh process with a free slot and the
running commit confirmed via `/health`:** a capture of simplepractice.com sat
at `capturing` for 607 seconds against a 300-second deadline. Once a browser
call wedges, in-process cancellation does not clear it — `wait_for` waits on a
cancellation that never completes.

**What holds today.** The reaper closes the row at 20 minutes and refunds the
1,750 credits. Later checks now fail fast with "the checker is busy" instead
of hanging. `example.com` completes the full check end to end in 94 seconds
with a real critique, so the pipeline itself — browser, census, screenshots,
storage, critics, verdict — is healthy.

**The recommendation, in order:**

1. **Raise the plan.** `render.yaml` has `starter`: 512 MB and **half a CPU**.
   The constraint is CPU more than memory — layout and DOM work are what run
   long, and a wedge is what a starved Chromium does. The 2 GB Standard plan
   is 1 CPU and 2 GB: double the CPU, quadruple the memory. This is a config
   change, it is cheap, and it should be measured before anything is built.
   `WEBSITE_CAPTURE_CONCURRENCY` and `WEBSITE_CAPTURE_DEADLINE_S` are both
   env-tunable so the new headroom can be used without a deploy.
2. **Then, if wedges persist: run the browser as a killable subprocess.** A
   process can be killed; a wedged coroutine cannot. It also stops a browser
   fault taking the API with it. This needs a machine with the browser runtime
   to build against and should not be written blind.

### S-5 · IP Check is dead in production (P0-11) — **CLOSED 2026-08-22**

Founder added `USPTO_ODP_API_KEY`, `USPTO_TSDR_API_KEY` and
`ADMIN_ORGANIZATION_ID` in the Render dashboard. Verified live on Chartwell:
QUICK clearance **complete in 31 seconds**, a 7,583-character report, both
tracks run (trademark and patent — so both keys work), 0 credits charged,
which confirms QUICK is the free tier.

Admin routes opened at the same time: `/admin/design-gallery` returns 200 for
a member of the Saido Labs organisation.

**Learned, and worth keeping:** `render.yaml` in this repository is
**descriptive, not synced**. `ADMIN_ORGANIZATION_ID` was set as a literal in
that file, deployed, and confirmed live by commit — and the admin gate still
refused, because Render never read it. Two consequences: env vars must be set
in the dashboard, and the earlier worry that a Blueprint sync could silently
downgrade the instance back to `starter` was unfounded.

### The same false alarm, twice — a note on method

Three of the thirteen problems the harness reported were **the harness reading
keys the API does not serve**: the analysis nests its findings under
`artifact`, a report carries `markdown_content` and `section_count` rather
than a `sections` array, and `GET /reports` takes no simulation filter — so
passing one silently returns the org's newest reports instead of that run's.
The app itself uses `/reports/by-simulation` and was never affected.

**This register already recorded that exact false alarm on 2026-08-17**, and a
freshly written harness reproduced it. The lesson is not "check the keys" but
that a test harness written from memory of an API is a second implementation
of that API, and it drifts. Every claim above was checked against the database
before it was called a bug.
