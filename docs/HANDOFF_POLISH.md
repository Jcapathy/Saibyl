# Handoff — the polish pass, 2026-08-05/06

**Saido Labs LLC** · Written mid-task for a cold context window.

Read this, then `HANDOFF.md` §1a, §2, §2a. This file covers **only** the work
that started when the founder reviewed the deployed UI and said, correctly,
that there was "an insane amount of polish" still needed.

---

## 0. State right now

Everything is **committed, pushed and deployed**. `master` and `v2` are the same
commit. Working tree is clean apart from one **untracked directory that matters**
— see §3.

```
ef11ba7  Give the dashboard the job it was missing, and delete the V1 API
44b6f18  Say it in words a founder already knows, everywhere
2c917d2  Delete the scaffolding a solo founder never asked for
61985e2  Say why $5 is too small, instead of "greater than or equal to 1000"
f0d3ba5  $20 does not buy a full-size run, so stop saying it does
03a4052  Let a founder spend $10 before deciding about $99 a month
```

Gate, green at `ef11ba7`:

```
backend   ruff clean · pytest 1032 passed, 4 skipped
frontend  npm run build clean · eslint clean · vitest 15 passed
          jargon scan: ZERO hits, with NO debt list
```

Migrations **017–031 all applied**. 031 is `credit_topups` + `apply_credit_topup`.

**Spend today: ~$2.10** of the $40 the founder funded. Two live runs (one on
their real product, one on the demo) plus two audience syntheses.

---

## 1. The five items the founder asked for, and where each stands

| | Item | State |
|---|---|---|
| 1 | Delete the scaffolding | **Done** — `2c917d2`, −1,292 lines |
| 2 | Finish the vocabulary migration | **Done** — `44b6f18`, 110 hits → 0 across 35 files |
| 3a | Buyers: stop returning competitors | **Done** — category matcher at the filter |
| 3b | Answers: the drafted assets are terrible | **NOT STARTED** — §2 |
| 3c | Step 2 shows stale objections | **NOT STARTED** — §2 |
| 4 | Re-run the cold read | **NOT STARTED** — do last |
| 5 | A real landing page | **IN FLIGHT** — screenshots taken, page not built. §3 |

### Decisions the founder made, already applied

- **Scaffolding: delete outright.** Done. Settings is two tabs.
- **`/api/score` and API keys: V1 residue.** Deleted, `ef11ba7`.
- **"Analyze Predictions" must not fire empty.** Done — the control is replaced
  by a sentence when there is no number, and the handler refuses too.
- **A dashboard IS wanted** — "one central place to extract reports and have
  shortcuts". Built as the **export surface**, `ef11ba7`. This is not a rebuild
  of the old page; see §4.
- **Landing page imagery: a neutral demo product**, not their real one.

---

## 2. The engine work — the part that actually matters

Everything above is chrome. **These two are the product.**

### 3b — The drafted answers are unpublishable

The founder pasted step 3's output. It is technically responsive and
commercially suicidal:

```
Disclosure: What We Have Not Yet Measured
Disclosure: We Don't Yet Know Our Own ROI Numbers
ParryAI Removal & Migration Guide (Draft)      ← answering "creates lock-in"
```

**Diagnosis (mine, unverified in code):** the drafter has over-learned the
anti-fabrication guardrails. Those rules are right for *measurement* — the
report must not invent numbers — and wrong for *asset drafting*, where the job
is to make a case the material supports. It has turned "be honest" into "admit
weakness", and no founder can publish a migration guide for removing their own
product as an answer to a lock-in objection.

**What the fix probably needs** (decide after reading the drafter):
1. An asset must state a **positive claim the uploaded material supports**.
2. `disclosure` demoted from default to rare fallback, with a cap.
3. Asset-type selection constrained by whether *publishing it helps the founder*.
4. A live re-run to verify — **do not trust a passing test here**, the whole
   session's history says otherwise.

Start at `backend/app/services/…` inoculation asset drafting; `AssetType` is in
`frontend/src/lib/founder.ts` and mirrors the server enum.

### 3c — Step 2 shows objections derived from the description, not the upload

Founder-reported, **not yet reproduced**. Two very different causes:

- the page is picking the wrong run (a run from before they uploaded), or
- the run genuinely read the one-line description over the documents.

**Reproduce before theorising.** Note that `ReactionsStagePage` was already
fixed once to exclude re-simulations (`2c709ec`), so the selection logic is
suspect but was not the whole story.

### NEW — the exported report is the least-cleaned surface we have

Found while verifying the export end to end. **Every screen now speaks plainly;
the PDF a founder takes to a board meeting does not.** Scanned the real 27-page
export from the demo run:

```
adversarial   pages 1, 4, 6, 11, 12, 13, 15, 16
cohort        pages 1, 3, 4, 5, 6, 7, 9, 11
archetype     pages 3, 6, 7, 18, 19, 20, 21, 25
valence       pages 3, 7, 12, 23, 24, 25
variant       page 20
```

This is **server-side report copy** — `report_document.py`, `report_agent.py`,
and the composed `adversarial.disclosure`. The frontend jargon test cannot see
it. One agent deliberately left `adversarial.disclosure` alone because PRD §4
requires viewer / print / PDF / JSON to render it identically — so **fix it at
the source, once**, not per surface.

Arguably higher value than the landing page: it is the artifact that leaves the
building.

---

## 3. Item 5 — the landing page, in flight

**What is already true:** the deployed page is 6,910px of centred prose on a
starfield with **zero product imagery**. The copy is good and honest (it was
rewritten to remove a 1,000× overstatement); it is not a website. The founder's
words: "reads more like an internal tool that somebody built over a weekend."

**What is done:** a neutral demo product exists and has been run live, so the
imagery is real product output and not a mockup.

> ### ⚠️ `frontend/public/demo/` is UNTRACKED. Commit it or the work is lost.
>
> `objections.png`, `audience.png`, `rail.png` — 2× retina, clipped to the
> content column so the demo account's own balance and email are not on a
> marketing page.

**The demo product — "Tallyhook"**, a fictional invoice-chaser for freelancers.
Deliberately not a real company. Its run produced 26 genuinely good objections:

```
3 people  risk of damaging client relationships
3 people  won't work on clients who intentionally delay payment
2 people  too expensive for what it does
2 people  real problem is the client relationship not the tool
2 people  automated messages sound robotic or impersonal
2 people  guilt about bothering clients for money
```

**What the founder asked the page to carry:** value proposition, CTA,
capabilities, and *what the founder can use from the runs*. Plus: a story a
stranger gets in four seconds, section rhythm rather than a wall, and an honest
substitute for social proof while in beta.

**Still to do:** write the page. `frontend/src/pages/LandingPage.tsx` and
`frontend/src/components/landing/`. `tiers.ts` already holds every number traced
to `agent_pricing.py` — **do not write a number that does not come from there.**

**Three verified benchmark citations** already live in
`frontend/src/components/billing/ValueCase.tsx`, with the two that were rejected
and why. Reuse them; do not re-research.

---

## 4. Things that are true now and were not this morning

- **Settings is two tabs.** Invite-team sent no email; invoice history called an
  endpoint that does not exist; payment-method could never work; Cancel Plan ran
  a TODO comment. All gone.
- **The webhooks subsystem is gone entirely**, including three
  `try: … except Exception: pass` call sites in the run worker.
- **The dashboard is the export surface.** `/api/exports` had **no caller
  anywhere in the frontend** — the PDF fix from 2026-08-05 shipped to nobody.
  New endpoint `GET /api/reports` lists an org's reports with run and product
  names. **Verified end to end: a real 184KB, 27-page PDF with Liberation fonts
  embedded**, so the Dockerfile font fix is confirmed working in production.
- **Credits replaced two fabricated meters** in the sidebar. `simulations_limit`
  read a table keyed on V1 plan names and signup puts everyone on `free`, which
  is not a key; `agents_limit`'s 50K was a `.get()` default belonging to no plan.
- **`JARGON_DEBT` is deleted.** It had excused 35 files including pages the rail
  links directly to. Three holes in the scanner were also fixed: it skipped
  plurals, skipped `label=` attributes, and rejected any text containing `;` —
  which silently excluded every sentence with an `&mdash;` in it.

---

## 5. Open, and roughly in value order

1. **The exported report's jargon** (§2). Server-side, single source, high value.
2. **3b, the answer drafter** (§2). The product's weakest output.
3. **The landing page** (§3). Screenshots ready.
4. **3c, stale objections** (§2). Reproduce first.
5. **Re-run the cold read.** The first one never reached the build — it landed
   on the old dashboard and gave up. Fresh agent, no design docs, real browser.
6. **Swallowed exceptions**, reported by an agent and not fixed:
   - `ProjectsPage.tsx:17` — a failed list renders "No products yet". The
     founder is told their products are gone.
   - `ProjectsPage.tsx:34,47` — create and delete fail silently.
   - `ProjectDetailPage.tsx:114` — a 404 leaves the heading reading "Product"
     with no explanation, indefinitely.
7. **`projects.asset_count` is fiction.** Never backfilled; its RPC existed in
   production only because someone added it by hand; one call site never called
   `.execute()`. The UI no longer renders it. Fix: one-time
   `UPDATE projects SET asset_count = (SELECT count(*) FROM documents d WHERE
   d.project_id = projects.id)`, or return a real count from `GET /projects`.
8. **Two behaviour bugs for the founder to decide**, both in run setup:
   - picking a stage silently discards an adversarial share they set by hand;
   - that slider is unreachable until *after* the audience is built, yet the
     stage default is what compiles the initial audience.
9. **Audit items 19, 39, 40.** 40 is new: `report_agent.py:768` defaults
   `variant="a"` and its only caller passes nothing, so a matched-swarm report
   illustrates whole-run statistics with one arena's quotes.

### Hard stop, unchanged

**Stripe Products and Price IDs** for founder/growth/agency at $99/$299/$999.
`stripe_service.py` still carries V1 prices ($499/$1,499). **The credit top-up
does not depend on this and is live** — a variable amount needs no Price ID —
so revenue is no longer fully blocked, but the tier migration is.

---

## 6. Accounts and IDs (production, all disposable)

| Purpose | Email / password | Org / product |
|---|---|---|
| Landing-page demo | `demo-tallyhook-2026-08-05@saidolabs.com` / `Sb-Demo-2026-08-05!x` | org `840eedd7-3a84-4ccd-8f66-eea5bac114fa`, product `80e5d9fb-2715-4506-9553-0800ecf2e6dc` |
| Live-run verification | `live-run-2026-08-05@saidolabs.com` / `Sb-Live-2026-08-05!x` | product `e0faae5e-a9f4-487b-baf7-9f20bff800c3` |
| Seeded rail states A–D | `ia-acceptance-2026-08-05@saidolabs.com` / `Sb-Accept-2026-08-05!x` | org `2cf27261-22d9-45b7-ab6d-316d255849b4` |

Delete any of them whenever; nothing outside them refers to them.

---

## 7. The one lesson worth carrying

**Nine defects were found today. The test suite caught none of them.**

Three came from screenshotting the deployed page, two from reading an API
response against live data, one from uploading a real file, one from exporting a
real PDF, and two from readers who had not built the thing.

Three separate times a test agreed with the implementation because both were
written from the same wrong assumption — the seeded `completed` status, the
`round()` on the runs figure, and the refusal sentences that never crossed the
API boundary. A green suite is evidence that the code does what its author
believed. It is not evidence that the belief was right.

**Look at the running product. Then look at what it exports.**
