# V1 audit — the whole list, in one place

**Saido Labs LLC** · Opened 2026-08-04 · **Status: open, being worked down**

This exists because V1 defects were being discovered one at a time, always
mid-task, usually at the worst moment — twice during a single Phase 3 gate run.
The sweep that produced this list is the standing rule in `HANDOFF.md` §2a; this
is its output.

**The honest headline: the sweep found far more than one session can fix.** Four
parallel audits over silent failures, model-supplied strings, dead code and
schema drift, and the frontend/backend contract returned roughly 70 findings.
Pretending otherwise by fixing the easy ones and closing the list is how this
became a drip in the first place. So: everything is written down, ranked, and
each item is either **FIXED**, **ACCEPTED** with a reason, or **OPEN** with an
owner-decision attached.

**Findings are claims until verified.** Several were checked directly against the
code and the database before acting; those are marked ✅ verified. The rest are
credible and unverified — treat them as leads, not facts, and confirm before
fixing. That distinction is the whole point of the exercise.

---

## The pattern underneath almost all of it

> **A lookup miss and a legitimate absence are represented by the same value.**

Nearly every finding is a `.get()` default, a `continue`, or an `if/elif` with no
`else`. The value is not merely wrong — it is *indistinguishable from nothing
being there*, so no counter moves, no log fires, and the health output reports
success. That is why these survived months in production and why they surface
only when something new finally compares two things that were always meant to
match.

The second pattern, which produced the largest single class:

> **Anything rendered into a prompt comes back decorated the way it was
> displayed.** Ids shown as `[id]` come back bracketed. Keys shown as
> `key — "label"` come back as the label. Roles shown pipe-joined come back
> title-cased. This is structural, not a model defect, and the fix is to
> normalise at every boundary — `app/services/refs.py`.

---

## FIXED — 2026-08-04

| # | Finding | Severity | Evidence |
|---|---|---|---|
| 1 | **Cross-tenant leak in both SSE endpoints.** `simulation_stream_sse` and `report_progress_sse` bound `auth` via `Depends(get_current_org)` and never used it. Authenticated ≠ authorised: any signed-in user could stream any organisation's live events or report progress by knowing a UUID. The WebSocket path does not have the hole — it passes `org_id` to `manager.connect`; the SSE fallbacks were added later and did not carry the check. | **Security** | ✅ verified in `api/ws.py` |
| 2 | **A Flash Report purchase downgraded a paying customer.** `create_flash_report_checkout` sets `mode="payment"` with metadata `{org_id, report_type}` and no `plan`. The webhook read `metadata.get("plan", "starter")` and wrote it — so an Agency org buying one report was set to `plan="starter"` with starter limits, and `data["subscription"]` is `None` on a payment-mode session, so `stripe_subscription_id` was nulled at the same time. | **Money** | ✅ verified in `stripe_service.py` |
| 3 | **`intent` was type-checked, not membership-checked** — `isinstance(intent, str)` — while `stance` eight lines below it was validated against a set. `intent` is the Marketing lens's *headline metric*: `variant_scoreboard` counts converting agents with `e.intent in intents`, so `"Purchase"` or `"none."` lands in no bucket, the objective rate reads 0.0 with a rule-of-three interval, and `_resolve_winner` explains a parsing bug to the customer as a sampling problem. | **Wrong number** | ✅ verified in `event_measurement.py` |
| 4 | **`app/services/refs.py` created** — one home for `post_ref`, `key_ref`, `enum_ref`, `slugify`. The strip set previously existed as a literal in two files; if they drift, the 193-of-193 link failure returns silently. | Structural | — |

Earlier the same day, from the same root cause: the twelve-adapter `post_ref`
fix, the `isSupportedSchema` range fix, and the V1 A/B subsystem removal.

---

## FIXED — 2026-08-04, second pass (six parallel audits)

**Items 1–18 and 20–38 are fixed**, each verified against the code and, where it
mattered, against production before anything was changed. Detail is in the four
commits; what follows is only what a future session needs to *not* re-derive.

**One finding was rejected on evidence.** Item 29's headline — "every upload
500s" — is **wrong**. `increment_asset_count(p_project_id uuid)` exists in
production and PostgREST binds overloads by argument name, so uploads worked.
The real defect underneath it is worse and different: **neither single-argument
function is in any migration.** A database rebuilt from `scripts/migrations/`
breaks upload *and* delete on day one. Migration `025` reproduces both from
`pg_get_functiondef` on production. `scripts/migrations/apply.py` also depends
on an `exec_sql` RPC that **exists in no schema** — the migration runner has
never applied anything.

**Corrections to the audit's own text, so they are not inherited as facts:**

- Item 13 said "~13 sites". It is **15**, plus 17 further raw-id parse sites.
- Item 28's diagnosis was partly wrong. `sentiment_score` is not always a
  misspelling of `valence`: on the `simulations` list reads there is **no
  backend source under any name**, so those displays were removed rather than
  renamed. On the WS stream the backend declares the field but never constructs
  it — events are written unmeasured and scored afterwards, so live sentiment is
  architecturally impossible. Three sites in `SimulationDetailPage` were
  **correct** and left alone (interview responses genuinely carry it).
- Item 39's "no caller" list was right about `/api/uploads` and the five
  ingestion processors, and that is now **resolved by wiring, not deletion** —
  see the ingestion unification below.

**What the sweep found that the audit did not have:**

| Finding | Why it matters |
|---|---|
| **`.pptx` was extracted as DOCX.** The extractor looks for `word/document.xml`, which no PPTX contains, so a deck stored `"[Unable to extract text from this DOCX file]"` as its whole contribution to the ICP, status `complete` | A deck is the most likely thing a founder uploads. Every ICP synthesized from one was built on nothing |
| **PDF `doc_context` was mojibake.** `_download_doc` decoded the raw upload as UTF-8 with `errors="replace"`, which never raises | The other most likely upload. Both silent |
| **The swarm was short.** Apportionment allocated 45 agents where 48 were requested; 85 of 180 configurations missed their total | Credits are charged at start from the selected count. Paid for, not delivered — and a second source of the interval-widening in §1a |
| **`rate_limit` built a Redis pool per request** | It manufactured the very error `fail_open=True` was swallowing. Cause and cover-up in one function |
| **The strip set in `post_ref` had already drifted by one character** between its two copies | The 193-of-193 link failure returning, exactly as the audit predicted a duplicated literal would |
| **28 log assertions could pass while capturing nothing** | `create_app()` installs a new structlog processor list; `capture_logs` swaps the current one in place. Order-dependent, so 4 files had private fixtures and 6 did not. Now one `conftest` fixture and a canary that was verified to fail without it |

---

## FIXED — 2026-08-04, third pass: item 36, closed with evidence

**Item 36 is closed.** One commit carries the whole fix:

- **`63e8ee5`** — *"Typeset the report as a document, and make the export produce
  a file"* (18 files, +4,503/−533).

It is the only commit that introduces either of the two root causes' fixes:
`git log -S"fonts-liberation" -- backend/Dockerfile` and
`git log -S'"upsert": "true"' -- backend/app/workers/export_tasks.py` each return
`63e8ee5` and nothing else.

**The two root causes the audit never recorded.** Both are the transferable part
— each is an *environment* defect that presents as a code defect, which is why
the entry above described the symptom and not the cause.

1. **`python:3.12-slim` ships zero fonts.** Not "a limited set" — none.
   `find /usr/share/fonts -type f` on the base image returns nothing, so
   WeasyPrint had no face to set the document in and the PDF path produced
   nothing readable. No amount of reading the exporter finds this: the code was
   correct and the image was empty. The fix is two apt packages, and the reason
   there are two is itself worth keeping — `backend/Dockerfile:12-18`:

   ```dockerfile
   # The font packages are not optional. `python:3.12-slim` ships **zero** fonts —
   # `find /usr/share/fonts -type f` returns nothing — so WeasyPrint had nothing to
   # set the exported report in. Liberation covers the document's serif/sans/mono
   # stack with Arial- and Times-compatible metrics; DejaVu is the per-glyph
   # fallback that carries the typographic characters the report actually uses
   # (U+2212 minus in every figure, en/em dashes, curly quotes, the middot in the
   # page furniture).
   RUN apt-get update && apt-get install -y --no-install-recommends \
       ...
       fonts-liberation \
       fonts-dejavu-core \
       ...
   ```

   The install is `backend/Dockerfile:27-28` — `fonts-liberation` and
   `fonts-dejavu-core`. **Do not drop either when slimming the image.** Dropping
   DejaVu does not blank the report; it turns every minus sign in every figure
   into a fallback box, which is the failure mode that survives review.

2. **The storage upload had no `upsert`.** The export path is deterministic —
   `exports/{org_id}/{report_id}/report.{ext}` — so the *second* upload of the
   same report collided with the existing object and failed, while the first
   succeeded. A user who re-exported after fixing a title could never get the new
   file, and nothing in the response distinguished the two cases. Fixed at
   `backend/app/workers/export_tasks.py:40-49`, with the reasoning kept next to
   it:

   ```python
   # Upload to Supabase Storage. `upsert` because the path is deterministic:
   # without it the *second* export of a report 409s on a duplicate object, so
   # a user who re-exports after fixing a typo in the title can never get the
   # new file.
   storage_path = f"exports/{org_id}/{report_id}/report.{ext}"
   admin.storage.from_("exports").upload(
       storage_path,
       file_bytes,
       {"content-type": content_type, "upsert": "true"},
   )
   ```

   The same fix is applied to the simulation export at
   `export_tasks.py:80-84`. Note the value is the **string** `"true"`, not the
   boolean — supabase-py passes `file_options` through as HTTP headers, and a
   Python `True` serialises to `"True"`, which the storage API does not accept.

**Item 36's own claims, each checked against the current tree:**

| Claim in item 36 | Status | Evidence |
|---|---|---|
| `services/export/` produces nothing — `simulation_analytics` was refactored and its three consumers were not | ✅ fixed | `simulation_analytics` is no longer called from `app/services/export/` at all. Both exporters read the validated artifact instead: `pdf_exporter.py:115-119` (`get_analysis` → `artifact`, gated on `build_status == "complete"`), `pptx_exporter.py:39-44` (`load_artifact` → `SimulationAnalysis`) |
| PDF export reports success and writes no file | ✅ fixed | `pdf_exporter.py:181-187` refuses a stub rather than returning one: under the `MIN_PDF_BYTES = 6_000` floor (`:59`) it raises, and it also rejects bytes not starting `%PDF-`. `ExportError` (`:62-68`) is raised, never returned |
| The API reports success for a failed export | ✅ fixed | `api/exports.py:42-61` (`_run`) awaits the export and turns every failure into a stated HTTP 500: `:46` handles `ExportError` with the reason in the detail, `:49` catches everything else, and `:55-60` refuses to report success when a file exists but no URL could be signed. The `asyncio.create_task` wrapper that swallowed exceptions **and** discarded the signed URL is gone — see the module docstring at `api/exports.py:1-19` |
| PPTX ships with zero charts | ✅ fixed | The chart block is no longer inside a blanket `try`. Each chart is drawn on an explicit measured-data guard — `pptx_exporter.py:225-274`, `if len(arc) >= 2`, `if len(platforms) >= 2`, `if len(archetypes) >= 2`, `if len(cohorts) >= 2` — so a missing chart now means "fewer than two measured points", not "an exception was logged and swallowed" |
| `variant="a"` hardcoded in **all six exporter calls** | ✅ fixed | No `variant` argument survives anywhere in `app/services/export/`. The artifact is per-simulation and carries every arena in `scoreboard`, so reading it removed the parameter rather than fixing its value (`pdf_exporter.py:28-31`) |
| `variant="a"` hardcoded **one layer down in `report_agent.py`** | ❌ **NOT fixed** | Still present. Filed as **item 40** below rather than closed with the rest |

**Regression cover added by the same commit**, so this cannot silently rot again:
`tests/test_pdf_export.py` (counts bytes and pages — the docstring states outright
that "no exception" is not a sufficient assertion, because the exporter used to
throw one while the product reported success), `tests/test_pptx_export.py`,
`tests/test_export_api.py`, `tests/test_report_document.py`.

**One thing the closure does not buy.** `/api/exports` is registered
(`main.py:157`) and now works, but **nothing in the frontend calls it** — zero
hits for `/exports`, `pptx` or a download handler across `frontend/src`. The
export was repaired; it is still unreachable from the product. That is item 39's
decision, not item 36's, and item 39 stays open.

---

## OPEN — ranked. Verify before fixing.

> **Status 2026-08-04:** items 1–18 and 20–38 are **fixed** (above). What remains
> open below is **item 19** (fire-and-forget tasks, which wants the durable-jobs
> work in Phase 4), **item 25** (the tier migration — decided, but it needs
> Stripe Products and Price IDs, so it is blocked on an external action), and
> **item 39** (the no-caller subsystems, which needs a wire-up-or-delete decision
> per subsystem; `/api/uploads` and the ingestion processors are now wired).
>
> **Item 36 now carries its evidence** — commit, file:line and the two root
> causes — in the third-pass section above. It had been fixed in code while still
> reading open here, which is the same failure mode as the defects this document
> exists to catch: a claim nobody could check. Closing it turned up **item 40**,
> a genuinely unfixed remainder of item 36's last clause.
>
> The ranked list is kept below **unedited**, because several entries record the
> reasoning that made the fix findable and a summary would lose it. Where an
> entry has since been closed or corrected, a marked line is *appended* to it
> rather than the entry being rewritten.

### Money and correctness

1. **`analysis_tasks.py:137` — the margin gate passes on no data.** `floor_price = … if measured_usd else 0.0` makes `margin_held = retail >= 0.0` unconditionally true, and `credits_for(0) == 0` charges nothing. The cost-integrity half of the phase gate reports a pass when the ledger is empty. Should return `margin_floor_held=None` and log an error.
2. **`analysis_tasks.py:94` — a completed run returns `{"cost_reconciled": False}` with no log**, so it is never charged and nothing says so.
3. **`usage_ledger.py:88/127` — the buffer is cleared before the insert is confirmed**, destroying up to 50 metering rows on one transient error. Also `:165` returns `"available": True` on zero rows.
4. **`rate_limit.py:40` defaults `fail_open=True`** and swallows all Redis errors, so brute-force protection disappears silently. All three callers already pass `False`; the default is the risk.
5. **`core/auth.py:39` — `.limit(1)` with no `.order()`.** A multi-org user gets an arbitrary org per request. Related to the missing org switcher (§8) but distinct: this is non-determinism, not a missing feature.
6. **`markets.py:162` — `on_conflict="organization_id"`** against a per-org unique constraint means saving a Polymarket key overwrites the org's Kalshi key.
7. **`core/security.py:36` — SSRF check validates only `getaddrinfo(...)[0]`**, so `::ffff:127.0.0.1` bypasses it.

### Silently wrong numbers shown as measured

8. **`metadata.sentiment` is a dead key with six readers.** Written by the drift formula removed in Phase 1; sentiment now lives in the `valence` column. Still read by `api/score.py:119` (the headline Saibyl Score), `api/reports.py:44` (polarization), `api/accuracy.py:60`, `api/comparison.py:47`, `prediction_runner.py:233`, and `report_agent.py:902` (which feeds `or "N/A"` into an Opus prompt that mandates a filled stat card, so the writer invents the label). **This is the single highest-value cluster on the list** — one dead key, six customer-visible outputs.
9. **`objection_canonicalizer.py:502` — the model's returned `key` is exact-matched with only `.strip()`.** Priors are rendered as `  {key} — "{label}"`, the same copy-back pressure that produced `[<post_id>]`. A mangled key silently mints a new one; the ERROR guard fires **only at exactly zero carry-over**, so the realistic 12-of-46 case is invisible. Downstream, an unmatched key means `agent_count=0` → verdict `died` → the asset counts as proven while the same objection reappears as `emerged`. ✅ The exact-match and the zero-only guard are verified; the downstream consequence is reasoned, not observed.
10. **`inoculation.py:267` — `project_id` is never in the `.select()`**, so `sourced` is always empty and the fabrication filter treats *every* number as unsourced, dropping assets after a 6,000-token Opus draft.
11. **`inoculation.py:619` — two incompatible slug algorithms**, so the "agents who changed their mind" list is always empty and the docstring pre-excuses it as approximate.
12. **`simulation_tasks.py:446` — `event_type` is a negative allow-list.** Anything not in `("comment","react")` is treated as a post and claims a ref, overwriting a real parent. `event_type` is an unconstrained `str` set independently in twelve adapters, and discord already emits `"dm"`. ✅ verified — this is my own Phase 3 code.
13. **Adapter reaction parsing uses `line.split(maxsplit=1)[1].strip()`**, capturing the whole rest of the line as the id. `post_ref` strips edges only and cannot repair it. ~13 sites. `UPVOTE [a1b2c3] — solid` yields `a1b2c3] — solid`. ✅ verified in `reddit.py`.
14. **`hacker_news.py:194` — `_flag_post` still compares raw**, missed by the twelve-adapter fix because it is a private helper rather than one of the three abstract methods. HN's moderation weighting is permanently inert.
15. **`news_comments.py` — the feed renders comments but `react()` resolves against `self._posts`**, which holds only the seeded article whose id is never shown. 100% of upvotes match nothing.
16. `icp_synthesizer.py:524` (adversarial role silently defaults, collapsing four cohorts into one), `:606` (unknown archetype id silently substitutes the pack's heaviest archetype, inheriting a different psychometric profile), `pack_loader.py:194` (a custom pack id equal to a built-in overwrites it process-globally, across tenants).
17. `facebook.py:203` / `linkedin.py:175` — unrecognised reaction verbs collapse to `LIKE`, inverting the backlash signal the product measures.
18. `analysis_builder.py:531` — objections truncated *after* the slice builders ran, so `top_objection_keys` can name objections absent from the artifact.

### Reliability

19. **Nine fire-and-forget `asyncio.create_task(...)` calls hold no strong reference** and may be garbage-collected mid-run — after credits are deducted. Five duplicated `_safe_task` helpers should collapse into one. Related to the durable-jobs item in §8.

    ⚠️ **Still open, but the count has moved — re-counted 2026-08-04.** Five
    fire-and-forget call sites remain: `api/simulations.py:406`, `:566`,
    `api/reports.py:77`, `api/ontologies.py:60`, `api/documents.py:171`; and four
    `_safe_task` copies: `api/simulations.py:28`, `api/reports.py:24`,
    `api/ontologies.py:17`, `api/documents.py:36`. The sixth call site and fifth
    helper were in `api/exports.py` and are gone — `63e8ee5` replaced them with
    an awaited call, which is the item-36 fix. `main.py:48` is **not** in this
    count: `bridge_task` is bound and cancelled at shutdown (`:50-54`), so it
    holds a strong reference and is not the defect class. Do not read the
    reduction as progress on item 19 — nothing became durable; one caller stopped
    needing to be.

20. `simulation_tasks.py:362` — `_check_stop_signal` returns `False` on any Redis error, so a user's stop never takes effect while the API has already set status `stopped`.
21. `redis_bridge.py:46` — the bridge exits permanently after one Redis blip; all WS/SSE dead for the process lifetime while `/health` stays green. `main.py:180` hardcodes `checks["llm"] = "ok"`.
22. `simulation_tasks.py:306/713` — `gather(return_exceptions=True)` results filtered by `isinstance`, discarding exceptions with no log; a partial failure ships a smaller swarm than the customer was quoted.
23. `pptx_exporter.py:161` — reads key names `simulation_analytics` does not return, and a blanket handler means every PPTX ships with zero charts. Unguarded equivalent at `pdf_exporter.py:69` 500s the export.
24. `report_agent.py:679` — a preamble before `TOOL:` makes the model's reasoning the published section; `clean_report_output`'s existence is the symptom.

---

### Revenue — needs a decision, not a fix

25. 🚨 **Payment is impossible from the UI, and three layers disagree on tier
    names.** ✅ verified.
    - `stripe_service.py` → `starter` / `pro` / `enterprise`
    - `SettingsPage.tsx:88` → `analyst` / `strategist` / `war_room`
    - `PRD_V2` §8 → `founder` / `growth` / `agency` at $99 / $299 / $999

    `PLAN_PRICES[org.plan]` is therefore `undefined`: price shows `$—`, the
    agent cap shows `—`, the features card never renders, and `getNextPlan`
    returns null so **the Upgrade button is never drawn at all**. Clicking
    Upgrade from elsewhere posts `plan:"strategist"`, which
    `PLAN_PRICE_MAP.get(plan, "price_starter")` turns into the literal string
    `"price_starter"` — not a Stripe price id — and 500s into an empty catch.

    This is §8's "Stripe tiers are still V1" item, but that entry undersells it:
    the tiers are not merely un-migrated, the billing UI is **actively broken**.

    ✅ **DECIDED 2026-08-04 by the user: `founder` / `growth` / `agency` at
    $99 / $299 / $999 wins.** The other two vocabularies migrate to it. Still
    open as *work* because it needs new Stripe Products and Price IDs — a rename
    alone leaves `PLAN_PRICE_MAP` pointing at prices for the old tiers.

    Scope when picking this up:
    - `stripe_service.py` — `PLAN_PRICE_MAP`, `PLAN_LIMITS`, the cancellation
      path at `:188` which currently writes `plan:"starter"` (a *paid* tier, so
      churned customers keep paid entitlements — should be `free`)
    - `SettingsPage.tsx:87-101` — delete the local maps; serve tiers from the
      backend so this cannot drift a third time
    - `agent_pricing.TIER_CREDIT_GRANTS` / `TIER_CAPS` already map both old and
      new names; drop the old once nothing writes them
    - migration `018:180-190` backfilled grants using a CASE that knows only V1
      names and sent everything else to `ELSE 800` — orgs on the new names have
      a stale grant below the 1,180 a free run costs
    - `LandingPage.tsx` advertises 5,000/25,000/100,000 agents per sim against
      enforced caps of 100/150/1,000 — a 50–100× overstatement that ships today

### The mechanism the drift came through

26. **`frontend/src/types/index.ts` is imported by nothing.** Zero hits for
    `@/types` or any relative import across `frontend/src`. All nine interfaces
    are dead, and seven pages each redeclare their own local copy. The dead file
    even carries the *correct* `key_prefix` that `SettingsPage.tsx:757` gets
    wrong as `prefix`. **Fix this first of the contract items** — it is the hole
    every other frontend/backend mismatch drifted through.

### The live feed is deader than known

27. **The WebSocket feed has no publisher at all.** The known `agent_action`
    filter mismatch is the least of three stacked breaks: (a) nothing publishes
    `simulation:{id}:events` — the only `.publish(` in the backend is report
    progress; (b) `redis_bridge` broadcasts into a room keyed by the channel's
    resource id, while clients are registered under simulation id; (c) the
    catch-up burst passes DB `event_type` values (`post`/`comment`/`react`/`dm`)
    to a frontend subscribed to `agent_action`/`round_start`/… — zero overlap.
    `services/streaming/event_schema.py` declares a *third* vocabulary
    (`agent_post`/…) and is imported by nothing. Both SSE fallbacks subscribe to
    the same unpublished channel; the report-progress SSE works and has no
    caller.
28. **`sentiment_score` does not exist** — the column is `valence`. Read by
    `store/simulation.ts:12` and five sites in `SimulationRunPage`, plus
    `SimulationsPage` and `DashboardPage` against `simulations`. Even with the
    feed fixed, every sentiment reading stays blank.

### Broken flows — verify then fix

29. `documents.py:95` calls `increment_asset_count` with the wrong parameter name
    and a missing required arg → **every upload 500s after succeeding**;
    `documents.py:163` calls `decrement_asset_count`, which exists in no
    migration → every delete leaves a ghost row. Same defect family as the
    `simulation_llm_cost(sim_uuid)` mismatch already hit this session.
30. `markets.py` — `GET /keys` is shadowed by `GET /{market_id}`, so `"keys"`
    parses as a UUID and 500s. Same class as the `founder-stages` collision
    Phase 0 already fixed once.
31. **`analyzing` freezes the detail page.** The status is written at
    `simulation_tasks.py:789` but appears in none of the frontend's status
    constants, so polling stops the moment a run enters it and no "View Report"
    link ever appears until a manual refresh. Cheapest high-visibility fix on
    this list.
32. `material_kind` can never be set from the UI, so **the entire
    competitor-grounding feature is unreachable** — `competitor_ids` is always
    empty, every competitor name is stripped, and `comparison_page` assets can
    never exist. DECISIONS §7's guardrail is intact but its input is unwired.
33. `PATCH /icp/{id}` has no caller, so "synthesis proposes, the founder
    disposes" — the claim the whole `ICPProfile` shape exists to serve — is
    unreachable from the product.
34. `RunConfigurator` lets a user select and **be charged for** up to 8 variants,
    but variant copy is only writable after creation; a 4-variant run with no
    copy is billed 4× and executes one arena. Add a pre-start guard.
35. Report chat 500s on any question asked before the report finishes
    (`markdown_content[:8000]` on NULL); a failed report polls forever because
    the frontend has no `failed` branch.
36. `services/export/` produces nothing: `react_tools.simulation_analytics` was
    refactored and its three consumers were not, so PDF export reports success
    and writes no file, and PPTX ships with zero charts. Also `variant="a"` is
    still hardcoded one layer down in `report_agent.py` and all six exporter
    calls — on exactly the matched-swarm runs the scoreboard exists for.

    ✅ **CLOSED in `63e8ee5`** — evidence, file:line and the two root causes the
    entry above never found (`python:3.12-slim` ships zero fonts; the storage
    upload had no `upsert`) are in the third-pass section. **One clause did not
    close**: the `report_agent.py` half of the `variant="a"` finding is still
    live and is now **item 40**.

37. Webhook event names never match (`simulation.completed` vs
    `simulation.complete`) and `webhooks.py` does not validate them, so a broken
    subscription is accepted and displayed as healthy. The create-webhook
    response carrying the signing secret is discarded by the UI, so a user can
    never verify `X-Saibyl-Signature`.
38. `GET /simulations` computes `count="exact"` and returns bare `result.data`,
    so `totalPages` is always 1 — **a user with 50 simulations can never reach
    page 2.**

### Whole subsystems with no caller

39. `/api/platforms`, `/api/ontologies` (+ `ontology_generator.py`),
    `/api/uploads` (+ all five ingestion processors and the `project_assets`
    table), `/api/score`, `/api/exports` (+ `services/export/`). Decide per
    subsystem: wire it up or delete it. Maintaining code nothing calls is how
    `services/export/` silently rotted.

    ⚠️ **`/api/exports` re-checked 2026-08-04: still has no caller.** The
    subsystem now *works* (item 36) and is registered at `main.py:157`, but
    `frontend/src` has zero hits for `/exports`, `pptx`, or any download handler.
    Repairing it did not wire it. The decision this item asks for is still owed —
    and `services/export/` is now the strongest argument for the item, since it
    rotted unnoticed precisely because nothing called it.

### Found while closing item 36 — verified 2026-08-04

40. **The report writer still reads only arena `a`.** This is the surviving half
    of item 36's last clause: the exporters were fixed by reading the
    per-simulation artifact, but the ReACT loop underneath them was not.

    `report_agent.py:762-768` declares `_run_react_loop(..., variant: str = "a")`,
    and its only caller — `report_agent.py:1007-1010`, inside `generate_section` —
    **passes no `variant`**, so the default stands on every report. It is then
    forwarded to `simulation_analytics` at `:790` (the `measured_findings` seed),
    `:877` (every model-requested analytics call) and to `agent_interview_tool` at
    `:885`. `agent_interview_tool` has its own `variant: str = "a"` default at
    `react_tools.py:376`.

    The filter is real, not vestigial — `react_tools.py:219-220`:

    ```python
    if variant != "all":
        query = query.eq("variant", variant)
    ```

    **What is and is not affected, checked branch by branch** — this matters,
    because the blast radius is smaller than it first looks and overstating it
    would be its own defect:

    - **Unaffected** — `sentiment_over_time` (`:246`), `platform_comparison`
      (`:290`), `persona_breakdown` (`:303`) and `measured_findings` (`:316`) all
      call `_artifact(sim_id)`, which is keyed on simulation only
      (`react_tools.py:168-180`) and carries every arena. The numbers a report
      cites are therefore whole-run and correct.
    - **Affected** — `top_posts` (`:228`), `viral_moments` (`:273`) and
      `agent_activity` (`:280`) iterate the arena-filtered `events` list, and
      `agent_interview_tool` samples from one arena. So on a matched-swarm run
      the report's *measured figures* cover every arena while its *quotes,
      example posts, viral moments and interview responses* are drawn only from
      arena `a` — and nothing in the output says so.

    That combination is worse than either half alone: the reader is given
    whole-run statistics illustrated by single-arena evidence, which reads as
    corroboration and is not. Same shape as the rest of this document — the
    output is not visibly broken, so nothing fires.

    Fix is the same move that closed the exporter half: the artifact is
    per-simulation, so the parameter should be removed rather than defaulted,
    and the event-backed branches should take `variant="all"` unless a caller
    genuinely wants one arena. ✅ Verified by reading; **not** yet observed
    against a live multi-arena run.

---

## ACCEPTED — not fixing, with reasons

- **~90 legitimate silent handlers** — shutdown-path `CancelledError`, already-logged
  best-effort metering, idempotent removals, and the measurement pipeline's
  deliberate "leave unmeasured rather than invent a value" returns. Leaving a
  failure unlogged is only a defect when the failure can hide data loss.
- **`get_feed(agent_username)` unused in all twelve adapters.** The feed is not
  personalised per agent. That is a design fact worth knowing, not a bug; the
  parameter documents the interface a personalised feed would use.
- **Abstract-method parameters in `base_adapter.py`** flagged as unused. They are
  signature declarations.

---

## How to work this list

Take the top item, **verify it against the code and the data before changing
anything**, fix it, move it to FIXED with the evidence. Do not batch-fix from
this document — several entries are reasoned rather than observed, and shipping a
fix for a defect that does not exist is its own defect.
