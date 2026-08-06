# Handoff — the polish pass, 2026-08-05/06

> **Updated 2026-08-06. Deployed and verified live.** Items 1, 2, 3a, 3b, 3c, 5
> and backlog 6–7 are done and serving. The answer drafter has met a live run
> and passed. One gap remains and it is named in §5. Read §0 and §5.

**Saido Labs LLC** · Written mid-task for a cold context window.

Read this, then `HANDOFF.md` §1a, §2, §2a. This file covers **only** the work
that started when the founder reviewed the deployed UI and said, correctly,
that there was "an insane amount of polish" still needed.

---

## 0. State right now

**Deployed.** `master` and `v2` are both at `e241aa5`, and both Render services
are serving it.

```
e241aa5  Bring the polish handoff up to what is actually done
2fb8823  Stop telling a founder their products are gone when a request fails
fe1f463  Say when the objections on screen predate the upload above them
46a4ff4  Show the product on the page that sells it
bb79c7d  Make the drafted answers argue for the founder, not against them
0a7b5e0  Say it in the same words on the page a founder forwards
```

Gate, green at `e241aa5`:

```
backend   ruff clean · pytest 1066 passed, 4 skipped
frontend  npm run build clean · eslint clean · vitest 16 passed
          jargon scan: ZERO hits, frontend AND backend
```

Verified **against the running services**, each check chosen so it could only
pass on the new build:

| | |
|---|---|
| Answer drafter | 12 assets, **12/12 open on a claim**, 2 concessions and never alone, migration guide runs onto the product, titles publishable |
| `document_count` | Three products that read `0` now report 2, 1, 1; the two empty ones still 0 |
| Stale notice | Fires on both runs with no brief, silent on both with `status=ready` |
| Landing page | 9,896px, no overflow, three screenshots decoded, **zero console errors** |

Migrations **017–031 all applied**. One is **owed** — §5 item 1.

**Spend: ~$2.27** of the $40 funded. The drafter run cost **$0.165**; everything
else was SQL, Playwright and the two suites.

---

## 1. The five items the founder asked for, and where each stands

| | Item | State |
|---|---|---|
| 1 | Delete the scaffolding | **Done** — `2c917d2`, −1,292 lines |
| 2 | Finish the vocabulary migration | **Done** on screens `44b6f18`; **done on the exported report** `0a7b5e0` |
| 3a | Buyers: stop returning competitors | **Done** — category matcher at the filter |
| 3b | Answers: the drafted assets are terrible | **Done and verified live** — `bb79c7d`, §2 |
| 3c | Step 2 shows stale objections | **Done** — `fe1f463`. Not the cause anyone guessed; §2 |
| 4 | Re-run the cold read | **NOT STARTED** — the deploy it was waiting for has happened |
| 5 | A real landing page | **Done** — `46a4ff4`, §3 |

Plus, from §5's backlog: items **6** (swallowed exceptions) and **7**
(`asset_count`) are done in `2fb8823`.

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

## 2. The engine work — what the five commits actually found

### 3b — The drafted answers (`bb79c7d`)

**The handoff's diagnosis was right and the data added two things it could not
see.** Queried before anything was written:

- `projects.name` for that run is **ParryAI**, so
  `ParryAI Removal & Migration Guide (Draft)` is a removal guide for the
  founder's own product. Its first line: "This document describes what it takes
  to remove ParryAI from a running agentic deployment."
- **Two of the three disclosures were the only asset drafted for their
  objection.** The entire answer to "your ROI claim is unproven" was a page
  agreeing with it.

The prompt was teaching the confession in as many words — "the honest asset says
what the team does not yet know and what they will run to find out" was its
worked example, which is the strongest instruction in any prompt. That is
replaced, `ASSET_TYPES` is reordered so `disclosure` is no longer the first item
a model reaches for, and three checks back the prompt up: `_leads_away`
(anchored on the product's own name as the *object* of the leaving verb),
`_cap_concessions` (at most one per objection, never the only one, ERROR when
every asset concedes), and `_unpublishable_title`.

> **Ran live, and it holds.** `draft_assets` on the Tallyhook run, **$0.165**,
> 12 assets over 6 objections. All twelve open on a claim about the product
> ("Tallyhook sends nothing until you approve it"; "Tallyhook costs $12/month,
> flat"). Two are disclosures — down from three — and every objection has two
> assets with at most one concession, so the case where the whole answer was a
> page agreeing with the objection cannot occur. The disclosures argue first and
> concede second, which is the rewritten rule verbatim. The migration guide runs
> **onto** the product and says so. No "(Draft)", no "Disclosure:" prefix.
>
> The one number — "$12 a month, flat" — was checked against the subject brief
> rather than assumed: it is the founder's own price from their own material.
>
> `_leads_away` and `_cap_concessions` never fired. The prompt did the work,
> which is the right division: the checks are the floor, not the mechanism.

### 3c — Step 2's stale objections (`fe1f463`)

**Neither hypothesis was the live defect.** The run whose objections were pasted
has **no `subject_briefs` row at all** and started **1h42m before**
`subject_brief.py` first deployed, so its agents saw `prediction_goal` and
nothing else. Its objections are reactions to the sentence "Trustless agentic
run-time security that's patent-pending", almost word for word. The engine
defect was already fixed and the page was picking the only run there was.

What was not fixed: `subject_briefs.status` has recorded this in five values
since 2026-08-05 and **nothing read it**. That recurs on every
`material_unusable` and `distillation_failed`, not just on old runs. Step 2 now
carries a `StaleResult` — a separate shape from `MissingInput` on purpose, since
one warns about the next run and the other describes the answer already on
screen.

Found while wiring it: the page and the rail each chose "the latest run" by
different keys (`created_at` vs `completed_at or created_at`).
`StageState.produced_by` is now the single answer.

### The exported report's jargon (`0a7b5e0`) — **done**

Five banned words on twenty-four of twenty-seven pages. Fixed at the composer
where four renderers share a sentence, and at the prompt where a model writes
one. `tests/test_report_vocabulary.py` renders the whole document and reads what
a reader reads.

It also found a defect nobody was looking for: an **A/A/A run — identical copy
in every version — shipped `verdict=""`**, so the report printed "No winner."
followed by nothing and the writer's prompt carried
`VERDICT FROM THE MEASUREMENT:` with a blank line after it.

## 3. Item 5 — the landing page (`46a4ff4`) — **done**

The copy was never the problem. The page had **zero product imagery**, which is
what "reads like an internal tool somebody built over a weekend" describes.

Now: a hero shot, two `Split` sections (copy beside screen, then flipped, copy
first on mobile in both directions), a section showing what the Tallyhook run
returned, and the three verified benchmark citations moved to `lib/benchmarks.ts`
so the landing page and the billing page quote one declaration.

`frontend/public/demo/` is committed. Retake rather than edit if the app's
chrome changes — a touched-up screenshot is a claim about a screen that does not
exist. `demoRun.ts` holds the six objections shown beside `objections.png`; they
come from the same run and must move together.

**Four defects came out of rendering it with Playwright and reading it.** Build,
eslint and vitest were green the whole time:

- `&nearr;` rendered as the six literal characters. **It was already shipping on
  the billing page** — the landing page inherited it by copy.
- "on the right" was wrong in two of the three layouts `Split` renders in.
- The h1 left "out" alone on a fourth line.
- Both split screenshots were unreadable at half width until cropped.

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

Everything from the previous list is done, deployed and verified. What is left:

1. **A migration is owed, and its ordering matters.** `projects.asset_count` is
   read by nothing now, but `api/documents.py` still calls
   `increment_asset_count` / `decrement_asset_count` on every upload and delete.
   The release that stopped reading it **is now serving**, so the drop is safe to
   land: drop the column and both RPCs together. Leaving the column costs
   nothing today; leaving it *and* forgetting why is how the next reader trusts
   a number that has been wrong on a third of production since March.

2. **Existing artifacts still carry the old report vocabulary.** This is the one
   gap the vocabulary fix does not reach. `adversarial.disclosure`, the
   scoreboard verdict and the quality caveats are composed at analysis time and
   frozen into `simulation_analysis.artifact`, so both existing runs still read
   "incumbent-aligned", "this swarm size" and "the cohort breakdown". Exporting
   either today gives a PDF whose own copy is fixed and whose composed sentences
   are not — **including the Tallyhook run the landing page is built on.**

   Every *new* run is correct. `build_simulation_analysis` makes no LLM calls, so
   a rebuild is free, but nothing exposes it: `run_analysis` is reachable only
   from the simulation worker. Either add a rebuild route, or re-run Tallyhook
   before anyone exports it.

3. **Re-run the cold read.** Fresh agent, no design docs, real browser, against
   the deployed site. Worth much more now that there is a landing page with
   product imagery and a rail that explains itself.

4. **Two behaviour bugs for the founder to decide**, both in run setup:
   - picking a stage silently discards an adversarial share they set by hand;
   - that slider is unreachable until *after* the audience is built, yet the
     stage default is what compiles the initial audience.

5. **Audit items 19, 39, 40.** 40: `report_agent.py` defaults `variant="a"` and
   its only caller passes nothing, so a matched-swarm report illustrates
   whole-run statistics with one arena's quotes.

6. **`REPORT_SYSTEM_PROMPT` still says "McKinsey or Bloomberg Intelligence
   analyst".** The political-consultancy framing and its Spencer Pratt examples
   are gone and the vocabulary is a founder's, but the register above it was left
   alone as out of scope. Worth a decision: the reader is a founder and the
   people they forward it to.

7. **A test account is carrying granted credits.** `grant_credits` put 200 on the
   Tallyhook demo org to pay for the drafter verification; 35 are left. Harmless,
   but it is not a real balance and nothing else in the ledger says so.

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

**Nine defects were found in the first pass. The test suite caught none of them.**
The second pass found eight more, and the suite caught none of those either.

Where they came from:

| Method | Found |
|---|---|
| Querying production before theorising | ParryAI is the founder's own product; two disclosures were the only asset for their objection; `asset_count` wrong on 12 of 35; **the ParryAI run predates `subject_brief.py` by 1h42m** |
| Rendering the page and reading it | `&nearr;` printing literally (**and already shipping on the billing page**); "on the right" wrong in two of three layouts; an orphaned word; two unreadable screenshots |
| Writing the test before the fix | The A/A/A run shipping `verdict=""` |

That last one is the pattern worth naming. The vocabulary test was written to
scan copy, and the first thing it did was fail for a reason that had nothing to
do with copy: constructing a three-version run where every version performs
identically produced an empty verdict string, which the report printed as
**"No winner."** followed by nothing. Nobody was looking for it. A test that
builds a real input finds things a test that asserts on a fixture cannot,
because the fixture was written by somebody who already believed the code was
right.

Twice more this pass, a fix was one edit away from introducing the defect it was
fixing. `_leads_away` in its first form dropped "Remove the three scripts you
wrote", the best sentence in the draft. `produced_by` exists because the stale
notice would otherwise have named one run above another run's objections — a
two-sources-of-truth bug introduced while fixing a two-sources-of-truth bug.

One more this pass, and it is the sharpest. The first check that the frontend
had deployed waited for `/demo/rail.png` to return 200. It returned 200 in
twenty seconds — because those images shipped in the *previous* commit and were
already live. The check would have reported a deploy that had not happened, and
every verification after it would have been run against the old build and
believed. **A check that can pass for the wrong reason is worse than no check**,
because it is the one nobody re-runs.

**Look at the running product. Then look at what it exports. Then query the
database before you explain either — and make sure your check could only have
passed for the reason you think it did.**
