# Saibyl V2 — Architecture Log

**Saido Labs LLC**

Append-only record of architectural decisions and their rationale during the V2
build. Each entry is written in the same commit as the work it describes.
Newest last.

---

## [PHASE 0 | 2026-08-02] Branch created

`v2` branched from `master` at `178568b`. `master` stays deployed and untouched
until the merge is approved. All V2 work lands on `v2`.

---

## [PHASE 0 | 2026-08-02] Dead-code removal

Eight modules deleted after verifying zero live callers (grep across direct
calls, type references, string literals, dynamic imports, re-exports, tests):

| Removed | Why it was dead |
|---|---|
| `services/platforms/simulation_runner.py` | A second, unreachable simulation engine. The live engine is `workers/simulation_tasks.py::run_simulation`. Only `stop_simulation` and `get_simulation_status` were imported. |
| `services/engine/personas/agent_profile_generator.py` | Generated one agent per knowledge-graph entity. The live path is `run_prepare_agents`, which generates from persona packs. |
| `services/engine/personas/agent_persistence.py` | Only caller was itself. |
| `services/engine/personas/platform_formatters.py` | Only caller was `agent_persistence.py`. |
| `services/engine/simulation_config_generator.py` | Only consumer was `agent_profile_generator.py`. |
| `services/streaming/visualizer.py` | `compute_snapshot` never called by the live runner. |
| `services/intelligence/quality_scorer.py` | Queried tables `agents` and `events`, and a column `simulations.num_rounds` — none of which exist. |
| `services/export/benchmark.py` | Wrote to `benchmark_metrics`, a table no migration ever created, inside a swallow-all `try/except`. |
| `shared/types.ts` | Never imported; had drifted from the API. |

The last four formed a closed island referencing only each other, which is why
the whole cluster could go at once.

**Decision — rename over trim.** `stop_simulation` and `get_simulation_status`
moved to a new `services/platforms/simulation_control.py`. Keeping the name
`simulation_runner.py` for a module that does not run simulations — and which
defined a `run_simulation` colliding with the real one in
`workers/simulation_tasks.py` — is the exact confusion Phase 0 exists to remove.
The one import in `api/simulations.py` was updated.

**Deliberately preserved.** `services/platforms/simulation_runner.py` also
contained the *better* unreachable implementation: real Redis event publishing,
timezone-aware activity curves, and genuine concurrent A/B variant execution.
That logic is not carried forward verbatim because it must be rewritten against
the V2 event schema in Phase 1 — the frontend listens for `agent_action` while
the backend schema emits `agent_post`/`agent_comment`, so the streaming contract
is being redefined regardless.

---

## [PHASE 0 | 2026-08-02] Route collision: report export was unreachable

`reports.router` (mounted at `/api/reports`, `main.py:131`) and `exports.router`
(mounted at `/api`, `main.py:137`) both registered
`POST /api/reports/{id}/export`. FastAPI matches routes in registration order,
so the synchronous implementation in `reports.py` shadowed the asynchronous one.

Consequence: `api/exports.py::export_report`, `workers/export_tasks.py::
run_export_report`, and `services/export/pdf_exporter.py` — including all
matplotlib chart rendering — were dead code reachable by no request.

**Decision — keep the async path, delete the sync duplicate.** The async path
renders charts, gzips JSON, and returns signed URLs; the sync one emitted a
plain markdown-to-PDF conversion. Neither was called by the frontend (its
"PDF" button opens the print page; CSV and JSON are built client-side), so
there was no compatibility surface to preserve. `POST /api/simulations/{id}/export`
was never shadowed and is unaffected.

---

## [PHASE 0 | 2026-08-02] Cost model rebuilt on measured pricing

**The defect.** `COST_PER_AGENT_ROUND = 0.000017` USD. One agent action is a
single LLM call of roughly 1,000 input and 120 output tokens; on Opus 4.7
($5/$25 per MTok) that is about $0.0075 — the constant understated true cost by
roughly 440×. A second defect compounded it: `check_agent_budget` compared
requested agent-rounds against `usage_records.simulations_run`, a count of
*simulations*. An org that had run 3 simulations was treated as having consumed
3 of its 150,000 agent-rounds. A third: nothing charged the estimated retail
cost, so plans were flat-rate against uncapped compute.

**Decision — price per stage, not per agent-round.** A single flat constant
cannot express a pipeline whose stages differ by an order of magnitude in both
volume and model tier. `agent_pricing.py` now sums four independently priced
stages: agent generation, agent actions, event measurement, and report
generation.

This also makes N-way matched-swarm runs price correctly. Action cost scales
with variant count; agent generation does not, because every variant is judged
by the *same* generated audience — that reuse is precisely what makes the
comparison valid, and the cost model has to reflect it or it will over-quote
multi-variant runs by the generation cost times the variant count.

**Decision — unknown models price at the highest known rate.** `model_pricing.py`
resolves a model ID by longest prefix match, so dated snapshots
(`claude-haiku-4-5-20251001`) and provider prefixes (`anthropic/…`,
`anthropic.…`) land on the right rate. An ID matching nothing falls back to the
most expensive entry and logs a warning. A pricing table that fails toward
under-charging is a table that silently loses money.

**Decision — a hard margin floor, not just a target.** Pricing targets 80% gross
margin with a 70% floor enforced in the quote calculator. The stage token
profiles are estimates until the ledger has real data; the floor bounds the
damage if one is wrong.

**Decision — attribute usage via contextvar, not parameters.** `llm_usage`
records real token counts and cost per call, tagged with a pipeline stage.
Agent actions are issued deep inside platform adapters that have no reason to
know about billing, and threading a stage parameter through the adapter ABC
would couple the two for no benefit. Because the engine is asyncio-based,
contextvars follow the task correctly across concurrent platform runs. Writes
are buffered and flushed in batches — a 100-agent, 5-round run makes 500 calls,
and 500 individual inserts would dominate wall-clock time. A ledger failure logs
and never fails a run.

**Measured output** at 80% margin (Haiku actions, Opus report):

| Preset | Agent-rounds | LLM calls | Cost | Price |
|---|---:|---:|---:|---:|
| Free trial (25 / 3 / 2 platforms) | 75 | 181 | $1.27 | $6.35 |
| Standard (100 / 5 / 2) | 500 | 1,107 | $3.23 | $16.17 |
| Marketing 8-variant (100 / 5 / 1) | 500 | 4,107 | $8.85 | $44.25 |
| Deep (250 / 10 / 4) | 2,500 | 30,257 | $57.97 | $289.82 |

**Open item for Phase 1 — report depth does not scale down.** The section-count
formula in `report_agent.py` is `min(7, max(4, event_count // 30 + 2))`. The
floor of 4 means a 25-agent free-trial run still generates 6 Opus-written
sections, which is $1.07 of that run's $1.27 cost — 84% of the total, on a run
whose whole point is to be nearly free. Report depth should scale with run size;
2 sections is right for a 25-agent run and would drop the free run to roughly
$0.35.

---

## [PHASE 0 | 2026-08-02] Schema drift reconciled (migration 017)

Three objects were written by the application but created by no migration, so a
database built purely from the migration files would fail on them. Production
has them because they were added by hand — which is itself the problem.

- `simulations.persona_pack_ids TEXT[]` — written by `run_prepare_agents`. The
  singular `persona_pack_id` from migration 012 is retained and backfilled into
  the array.
- `simulations.error_message` — written by the `_safe_task` error handler.
- `increment_asset_count(project_uuid, delta)` RPC — called by `api/documents.py`.

Migration 017 also creates the `llm_usage` table with RLS matching the
established `organization_id = ANY(public.user_organization_ids())` pattern, and
a `simulation_llm_cost(sim_uuid)` aggregate used to verify that a quote covered
what the run actually cost.

---

## [PHASE 0 | 2026-08-02] Correctness fixes carried in the cleanup

- **`/api/score` was broken on the JWT path.** `api/score.py:42` referenced an
  undefined name `token`, so every JWT-authenticated request raised
  `NameError`; only the `X-API-Key` path worked. Ruff's `F821` catches this —
  it had simply never been run against the file.
- **`/api/score` status gate never matched.** It required status `"completed"`
  while the engine writes `"complete"`, so scores were unavailable for finished
  simulations. Both values are now accepted.
- **`DELETE /api/simulations/{id}` did not exist** despite `SimulationsPage.tsx`
  calling it. Added; refuses to delete a running simulation and clears
  `report_sections` before `reports` to respect the foreign key.
- **Frontend error handling.** Eight `catch (err: any)` blocks hand-unwrapped
  `err.response.data.detail`, which renders as `[object Object]` for FastAPI 422
  bodies where `detail` is an array. Replaced with `lib/errors.ts::getErrorMessage`.
- **`MarketDetailPage` computed elapsed time by calling `Date.now()` during
  render**, so the counter only advanced when the component re-rendered for an
  unrelated reason. Moved to an interval.

---

## [PHASE 0 | 2026-08-02] Stale tests corrected

`test_pack_loader` asserted exactly 13 persona packs; there are 16. It now
derives the expected count from the JSON files on disk, so adding a pack cannot
break the suite. `test_config` constructed a production `Settings` with an
8-character `SECRET_KEY`, which the security audit's 32-character validator
correctly rejects — the test was wrong, not the validator. A test asserting
that short keys *are* rejected in production was added.

Phase 0 end state: ruff clean, 43 tests passing, `tsc --noEmit` clean,
`eslint --quiet` clean.

---

## [PHASE 1 | 2026-08-02] Sentiment is measured from content

**The defect.** `simulation_tasks.py` computed each event's sentiment as
`sentiment_baseline × (1 + round/max_rounds × 1.5)` and wrote it into the event's
`metadata` blob. Two agents of the same archetype posting *"this is exactly what
we've needed for years"* and *"this will get someone fired"* received identical
sentiment. Every downstream figure — timeline, platform breakdown, flashpoints —
inherited that.

**Decision — a batched classifier, not a per-event call.** `services/intelligence/
event_measurement.py` scores each event from its content: `valence`, `stance`,
`intensity`, `objections[]`, `intent`, `is_novel_claim`, batched ~25 events per
Haiku call. Per-event calls would make measurement cost comparable to the agent
actions themselves; at 25 per call the stage is roughly 4% of a standard run.

**Decision — reactions are engagement, never sentiment.** A like or repost has no
text, so there is nothing to measure. They are marked measured with a *null*
valence and excluded from every sentiment aggregate, rather than assigned an
invented value like "like = +0.3". Inventing that constant would be the same
class of mistake as the drift formula, only smaller.

**Decision — a failed batch leaves events unmeasured.** It does not fall back to
a default. A defaulted score silently drags every aggregate toward zero and is
invisible; an unmeasured event shows up in the artifact's coverage figure.

**Decision — measurement columns are typed, not JSON.** They are aggregated on
every analysis build and joined for drill-down, and the database now enforces the
−1..1 and 0..1 bounds. A model returning 3.7 for a valence must not be able to
poison a number a customer will act on.

---

## [PHASE 1 | 2026-08-02] The analysis artifact, and one rule

`simulation_analysis` holds one versioned JSON artifact per run, validated
against `services/intelligence/analysis_schema.py` before it is written.

**The rule: every number rendered in the UI or written into a report comes from
this artifact.** It is enforceable only because the shape is declared in one
place — a field that does not exist on the schema cannot be displayed, so there
is nowhere for a `Math.random()` to hide.

**Decision — confidence intervals are computed across agents, not events.** A
25-agent run that produced 400 events has 25 independent observations, not 400:
one agent posting ten times is one opinion repeated. Each agent's events are
averaged first and the interval taken across the per-agent means. Treating events
as independent would shrink the band by roughly √(events per agent) —
manufacturing precision out of an agent's verbosity. The visible consequence is
that a small swarm honestly reports a wide band, which is both true and the most
credible argument for buying more agents.

**Decision — gaps stay gaps.** A round with no measurable opinion is omitted from
the timeline rather than interpolated; a flat segment would read as "sentiment
held steady", which is a different claim from "nobody spoke". Groups whose
intervals overlap are reported as unresolved rather than ranked.

**Decision — objections rank by load-bearing weight, not frequency.** Reach ×
intensity × cohort spread, on 0–100. The most-repeated objection is usually the
most quotable one, not the one that decides the purchase. All three factors are
shares, so any factor near zero collapses the score — a fiercely-held objection
confined to one archetype is a niche complaint, and a widely-shrugged-at one is
not an obstacle.

**Decision — canonicalization runs on the main model.** Clustering is a judgment
task whose failure mode is silent: over-merging collapses two distinct objections
into a label that answers neither. It is also cheap — one call over the distinct
strings, not per event. When clustering fails, each distinct phrasing becomes its
own objection; unclustered real objections are worse than clustered ones, but
fabricated clusters would be worse than both.

---

## [PHASE 1 | 2026-08-02] The fabricated frontend is gone

`ReportViewerPage.tsx` regex-scraped one sentiment scalar out of the report
markdown and generated the timeline, per-platform sentiment, persona metrics and
risk matrix from it with `Math.sin()` and `Math.random()`; risk likelihood was
`0.3 + Math.random() * 0.5`. `ReportPrintPage.tsx` carried its own copy —
platform sentiment was `baseSent + Math.sin(i * 2.1) * 0.2`, and the sentiment
distribution pie was a "plausible population split" derived from the same scalar.

Both pages are rebuilt on the artifact, and the seven components that existed
only to render generated data were deleted after grepping for direct references,
type references, string literals, dynamic imports, re-exports, and tests:
`SentimentTimeline`, `PlatformBreakdown`, `PersonaAnalysis`, `ThemeCloud`,
`RiskMatrix`, `SampleResponses`, `ExecutiveSummary`, plus the unused
`SentimentBar`. Their replacements live in `components/analysis/`.

**Decision — an unknown schema version renders nothing.** The client checks
`schema_version` and refuses an artifact it does not know, rather than rendering
the fields it recognises. Partial rendering is how a chart quietly loses a series.

**Decision — empty states are blunt.** "No round produced a measurable opinion"
rather than a placeholder chart. An empty slot filled with plausible data is
strictly worse than an empty slot: the reader cannot tell the difference, so
every genuine chart inherits the doubt.

**Decision — every finding drills down to quotes.** `GET /simulations/{id}/
evidence` returns the events behind any `event_ids[]`, rendered in a drawer. A
number that cannot be opened is an assertion regardless of how it was computed.

---

## [PHASE 1 | 2026-08-02] Agent actions moved to Haiku

All twelve platform adapters now call `llm_fast` rather than `llm_complete`.
`llm_complete` resolves to `settings.llm_model` (Opus), so the highest-volume,
lowest-judgment stage was running on the most expensive model — the single
largest line in every run.

**Watch this**, per DECISIONS_V2 §14: if measured objection diversity drops
against V1 baselines, the model tier is the first thing to check. The counter-
argument is real — surprising minority opinions are where flashpoints come from,
and a weaker model may produce blander agents.

Agent generation moved to `llm_fast` for the same reason and is now wrapped in a
`usage_context`, as are agent actions and the measurement pass, so the ledger
attributes every call to a stage.

---

## [PHASE 1 | 2026-08-02] Report depth scales down

The section-count formula was `min(7, max(4, event_count // 30 + 2))`. The floor
of 4 meant a 25-agent free-trial run generated 6 Opus-written sections — 84% of
that run's cost, on a run whose entire purpose is to be nearly free.

`report_section_count(measured_events, depth)` now scales from 2 to 7 across
threshold bands, with the depth preset shifting by one. A 25-agent run gets 2
sections, a standard run 4, a 250-agent run 7.

**Measured effect.** The free run drops from $1.27 to **$0.66**, and the report
falls from 84% to 46% of its cost. That is short of the $0.35 the Phase 0 note
projected: at two sections the report is $0.31 of the $0.66, and the remaining
cost is the simulation itself. The free grant is sized at 700 credits from the
measured figure rather than the estimate — a grant that does not cover one free
run would make the tier unusable.

The standard run also moved, $3.23 → **$2.78**, because it drops from 6 sections
to 4. `PRICING_GUIDE.md` and `PRD_V2.md` §8 are regenerated from
`scripts/quote.py` against the new model.

---

## [PHASE 1 | 2026-08-02] Credits replace the agent-round allowance

**Decision — the metered unit is credits, at 1 credit = $0.001 of COGS.**
DECISIONS_V2 §15b settles that grants are denominated in credits, not runs. This
implements that: `check_agent_budget` and its `PLAN_ALLOWANCES` table (in
agent-rounds) are replaced by `check_credit_budget` and `TIER_CREDIT_GRANTS`.

An agent-round allowance cannot ration this product. A run varies 65× in cost at
the tier caps — a standard run is $2.78, a 250-agent 8-variant run is $181.52 —
so the same agent-round count buys wildly different amounts of compute depending
on variants and platforms. Milli-dollars rather than dollars so the balance is an
integer: a float balance that drifts by a cent per deduction produces support
tickets nobody can reproduce. Conversion always rounds **up**, because at volume
the rounding direction is the difference between the margin floor holding and not.

**Divergence from the Phase 1 brief, recorded deliberately.** `HANDOFF.md` §3.6
said "wire `deduct_agent_credits` on completion". That function deducts
agent-rounds, which is the unit DECISIONS_V2 §15b retires. It is superseded by
`deduct_credits`; the `deduct_agent_credits` RPC remains in the database
untouched, and `organizations.agent_credits_balance` is no longer read.

**Decision — credits are charged at start, not at completion.** Deducting on
completion lets a user with one run's worth of credits start ten runs at once and
have every balance check pass. A run that is started and then fails still
consumed compute.

**Decision — caps are reported, not clamped, in the quote.** `issue_quote`
returns which tier limit a shape exceeds rather than silently shrinking it;
quoting one run and executing another is worse than refusing. The *sliders* are
capped, so the normal path cannot reach an unquotable shape.

---

## [PHASE 1 | 2026-08-02] Signed run quotes

`POST /billing/quote` prices a shape server-side, HMACs the priced fields against
`SECRET_KEY`, and stores the row. The client displays it and hands the id to
`POST /simulations/{id}/start`.

Without this the run shape that gets billed is whatever the browser posted: a
user who edits `agent_count` in a request body gets a 250-agent run at a 25-agent
price. `consume_quote` checks the signature, the owning org, the expiry, that the
quote is unconsumed, **and that its shape matches the simulation row** — a quote
for 25 agents cannot be redeemed against a 250-agent run, however the two were
submitted. Quotes are single-use with a 30-minute TTL, so one cheap quote cannot
fund unlimited runs or outlive a recalibration of the token profiles.

`POST /billing/estimate-cost` returns the same figures unsigned, for display
while sliders move. Issuing a signed quote per slider tick would leave hundreds
of unconsumed rows per configured run.

**Cost-integrity gate.** `workers/analysis_tasks.py::reconcile_run_cost` compares
the quote against measured `llm_usage` after every run, charges any shortfall
rather than absorbing it, and logs `margin_floor_breached` when the retail price
falls under measured cost × the 70% floor. The stage token profiles behind every
quote are still estimates; this is what surfaces a bad one on the first run
instead of in a month's P&L.

---

## [PHASE 1 | 2026-08-02] PostgREST truncation

`fetch_all` in `core/database.py` pages past PostgREST's 1,000-row cap. An
unbounded select returns the truncated set *without erroring*, and a 250-agent,
10-round run produces well over 1,000 events — an aggregate computed over the
first 1,000 of 2,500 events looks entirely plausible and is wrong. Every query
that reads a whole simulation now pages.

---

## [PHASE 1 | 2026-08-02] Sovereign palette

Obsidian `#0A0F1C` · Graphite `#111827` · Sovereign Gold `#C9A227` · Signal Blue
`#2563EB` · Insight Violet `#8B5CF6`. Replaces Indigo `#5B5FEE` / Neon Cyan
`#00D4FF`. `saibyl.purple` and `saibyl.cyan` survive as aliases onto the new
accents so a straggling class name renders in-palette rather than falling back to
an undefined colour.

---

## [PHASE 1 | 2026-08-02] The live run, and the three bugs it found

Static verification passes nothing that matters here. A 25-agent / 3-round /
2-platform run against production (`05f1d879`) is what actually validated the
phase, and the first attempt produced **zero events**.

**Bug 1 — no adapter ever told its agents what the simulation was about.** All
twelve stored `prediction_goal` in `self._config` during `initialize()` and not
one read it. The subject reached agents only through the persona bio, which is
generated *from* the subject — so the simulation silently depended on the bio
generator succeeding. Fixed with `BasePlatformAdapter.topic_block()`, threaded
into all twelve action prompts.

**Bug 2 — the cold-start deadlock.** On round one the feed is empty, and
"observe before engaging" is what a thoughtful person actually does. So every
agent chose NOTHING, the feed stayed empty, and rounds two and three did the
same. A run can end at zero events with no error anywhere. `topic_block()` takes
`feed_is_empty` and tells the agent to post rather than wait.

**Bug 3 — agent generation truncated.** Moving generation to Haiku kept
`max_tokens=400`, which is not enough for seven fields including a bio and a
backstory. 20 of 25 profiles failed `json.loads` mid-string and fell through to
the stub profile — which has no topic knowledge, which is what made bug 1 fatal
rather than merely degrading. Raised to 900; the re-run had zero generation
failures.

Bugs 1 and 2 predate Phase 1. Moving generation to Haiku is what exposed them,
by removing the accident that had been hiding them.

**Measured results (24 agents, 72 events, 100% coverage):**

The test that matters is whether valence varies between agents of the *same*
archetype, because the drift formula could not do that by construction — every
agent of an archetype got an identical score in a given round.

| Archetype | n | min | max | spread |
|---|---:|---:|---:|---:|
| Operations Manager | 12 | −0.60 | +0.60 | 1.20 |
| VP Engineering | 6 | −0.60 | +0.60 | 1.20 |
| Founder/CEO | 12 | −0.60 | +0.40 | 1.00 |
| IT Director | 12 | −0.50 | +0.30 | 0.80 |
| CTO / Finance Lead / Procurement | 6–12 | −0.70 | +0.30 | 0.70 |
| Security Manager | 6 | −0.80 | −0.20 | 0.60 |

Headline −0.280 (95% CI −0.375 to −0.184, n=19 agents), 56% oppose / 10%
support, confidence `moderate`, one flashpoint correctly reported as *within the
bands* rather than narrated as a finding. 124 distinct raw objection phrasings —
every single one unique, which is precisely why canonicalization exists —
clustered into 19 canonical objections. The top one by load-bearing weight was
*"positioned as nice-to-have not must-have"* (8 agents, 7 cohorts), which
outranked *"$99/month too high"* (7 agents, 4 cohorts) despite similar frequency.
That ordering is the whole argument for weighting by cohort spread.

**Bug 4 — an unguarded Redis publish killed the report.** `generate_report`
published section progress to Redis with no error handling, inside
`asyncio.gather`. With Redis unreachable the ConnectionError propagated out and
destroyed the entire report: every section left `pending`, status `failed`, an
Opus-priced narrative lost to a notification nobody was listening to. Progress
publishing is now `_publish_progress`, which logs and continues.

---

## [PHASE 1 | 2026-08-02] The report was still writing its own numbers

With Redis guarded, report generation completed — and the fidelity check on the
output was bad. Across four sections and 48,000 characters it made **zero**
references to a confidence interval, never cited the agent count the figures
rest on, and named none of the canonical objections. It did produce a confident
*"accounting for ~58% of all SMB objections on Reddit"* — a number that appears
nowhere in the artifact.

**The cause is structural, not a prompt weakness.** `_run_react_loop` starts with
`evidence = "None yet."` and the model is free to answer on its first turn. The
prompt says *"Use MULTIPLE different tools — do not answer after just 1-2 tool
calls"*, but that is advice, and a model with a section to write and a token
budget will decline it. Every measurement rule added to the prompt in this phase
was conditional on a tool call the model never had to make.

**Decision — seed the artifact into evidence before the loop runs.** Every
section now starts with `simulation_analytics("measured_findings")` already in
its evidence, whether or not the model would have asked. The loop can still
gather more.

Seeding is also strictly cheaper than asking: it costs one read of a row already
built, rather than an Opus turn spent deciding to request it. And it makes the
"every number comes from the artifact" rule structural — the artifact is in
context unconditionally, so a fabricated figure is now a model choosing to ignore
data in front of it rather than filling a vacuum.

This is the same class of mistake as the original defect, one level up: V1
generated numbers in the frontend because the backend had none; the report
generated numbers in prose because the loop had none in context. Both are fixed
by making the measured object impossible to route around.

**Measured effect**, same simulation, same prompts, only the seeding changed:

| | Before | After |
|---|---:|---:|
| "95% CI" / "confidence interval" mentions | 0 | 7 |
| Cites the agent count behind the figures | no | 8 times |
| Cites the measured oppose share | no | yes |
| Cites canonical objections by name | no | yes |
| Wall clock | 368s | 261s |

The report now opens findings as *"Opposition outpaced support by nearly 6:1
(55.6% oppose vs. 9.7% support)"* and carries *"−0.28 (95% CI −0.375 to
−0.184)"* through the analysis, including a passage on how the small swarm
widens those intervals. It got faster and cheaper as well as more accurate,
because a seeded turn replaces an Opus turn spent deciding to ask.

---

## [PHASE 1 | 2026-08-02] Cost model: one missing stage, and what the ledger says

**Objection canonicalization was not priced at all.** It is a stage this phase
added, and `estimate_simulation_cost` never learned about it — 24% of the live
run's measured spend was invisible to the quote. Added as
`OBJECTION_CANONICALIZATION`, charged once per run on the main model: its input
is the run's *distinct* objection phrasings, which saturates long before the
event count does. It is nearly constant while every other stage scales, so
omitting it under-quoted small runs badly and large runs barely at all.

Adding it moves the standard run $2.78 → **$2.87** and the free run
$0.66 → **$0.75**, so the free grant goes to 800 credits.

**Measured vs. estimated, from the live run.** The quote was $0.6595; the run
actually cost **$0.3144**. The margin floor held comfortably (90.5% actual
against a 70% floor), and the direction is the safe one — but a 2× over-quote is
not harmless: it means a customer's grant buys half the runs it should.

| Stage | Calls | Measured per unit | Profile says |
|---|---:|---|---|
| `agent_action` | 72 | 404 in / 169 out | 1,000 in / 120 out |
| `agent_generation` | 24 | 1,900 in / 537 out | 1,200 in / 350 out |
| `event_measurement` | 3 (72 events) | 81 in / 92 out per event | 140 in / 40 out |
| `objection_canonicalization` | 1 | 2,199 in / 2,587 out | 3,000 in / 3,000 out |

**The four profiles were deliberately NOT recalibrated from this run.** Per-call
input scales with feed size, which scales with agent count and round depth — a
25-agent, 3-round run has a far smaller feed than the 100-agent, 5-round run the
profiles are meant to price. Extrapolating from one small run would replace a
conservative estimate with a confidently wrong one. The recalibration needs
several runs across shapes; it stays the first item in `HANDOFF.md` §5, now with
a baseline to compare against.

---

## [PHASE 1 | 2026-08-02] Variants were billable before they were runnable

**The gap.** The cost model scales agent-action cost with variant count, and
correctly so. But nothing executes more than one arena: `run_prepare_agents`
assigns every agent `variant: "a"`, the runner never branches on variant, and
`run_simulation_ab` calls `run_simulation` once. Phase 1 then shipped a variants
slider, stored `simulations.variants`, and charged credits from the quote — which
made a 4-variant run cost four times the agent-action price for one arena's
work. That is billing for compute that is never performed.

The cost model was not wrong and the A/B stub was not new. What was new was
exposing the dimension to customers and wiring it to a charge.

**Decision — cap at what the engine runs, refuse rather than clamp.**
`MAX_RUNNABLE_VARIANTS = 1` clamps `tier_caps()`, so the slider cannot reach an
unrunnable shape; `issue_quote` and `POST /simulations` both refuse `variants > 1`
outright rather than silently reducing it, because quoting one shape and running
another is the failure this whole quote mechanism exists to prevent. Phase 3
raises the constant to 8 — `TIER_CAPS` already holds the intended per-tier
values, so that is the only edit.

The estimator itself is deliberately left able to price multi-variant shapes:
`PRICING_GUIDE.md` quotes an 8-variant marketing run, and `scripts/quote.py`
needs to model shapes the engine cannot yet run. The refusal belongs at the
boundaries that take money, not in the planning model.

**Generalisable lesson:** the cost model is a forward-looking artifact and the
engine is not. Any dimension the model prices needs a check that the engine
delivers it before a slider is attached to it.

---

## [PHASE 1 | 2026-08-02] The standard run, and four more defects

A second live run at the reference shape (100 agents / 5 rounds / 2 platforms,
`03de92ef`) produced 497 events at 100% coverage with confidence `high` — the
bands narrowed from the 25-agent run exactly as the agent-count model predicts.
It also found four things.

**Objection canonicalization silently collapsed at scale.** The clustering call
returned `output_tokens = 4000`, precisely its `max_tokens`: the JSON truncated,
`json.loads` raised, and the fallback produced one "canonical objection" per raw
phrasing. **300 objections, 265 of them with a single event**, with "integration
debt not addressed", "doesn't address integration complexity" and "doesn't
surface integration debt" sitting in three separate rows. The Founder lens ranks
on exactly this object, so the failure was quiet and total — and invisible at 25
agents, where 124 phrasings still fit in the budget.

The cause was that the prompt asked the model to echo every member string, so
output scaled with input. Members are now **indices** into a numbered shortlist,
which makes output scale with the number of *groups* instead. Same run,
rebuilt: **300 → 17 canonical objections, zero single-event**, the top one
spanning 18 agents and 8 cohorts. `MAX_DISTINCT_STRINGS` also rose to 800, since
a standard run produces ~600 distinct phrasings and the truncation is now logged
rather than silent.

**Agent usernames collided, and the swarm was under-counted.** Asked for 100
handles the model produced 45 distinct ones — nine agents named `mchen_itdir`.
Adapters address agents by username and nothing else: they key agent memory on
it, and the runner maps `event.agent_username` back to a row through it. So nine
agents shared one memory, all their events were attributed to one row, and — because
confidence intervals are computed across agents — nine independent observations
counted as one. Every band in both runs' artifacts was drawn from a swarm less
than half its real size. The arithmetic gives it away: 45 agents acting once per
round for 5 rounds cannot produce 497 events.

Usernames are now deduped at generation with a suffix, and the runner logs an
error if it ever sees a collision again. **The two existing runs cannot be
repaired** — there is no record of which of nine identically-named agents
produced a given event — so their `n` values remain understated. Intervals were
therefore *wider* than truth, which is the safe direction, but wrong.

**The report ignored the configured depth.** `run_generate_report` defaults to
`evidence_depth="deep"` and `run_simulation` never passed anything, so
`simulations.depth` — set by the configurator, priced in the quote — did nothing.
A run quoted at 4 sections was written at 6.

**Report spend was not metered at all.** `run_generate_report` was fired via
`asyncio.create_task` *after* the run's usage contexts had exited, so
`record_llm_call` found no active context and dropped every call. The report is
the largest main-model stage, so `simulation_llm_cost` under-reported every run
by roughly a fifth and `reconcile_run_cost` compared quotes against a figure
with its biggest line missing — a margin breach could have passed the gate.
Report generation is now wrapped in a `usage_context`, and reconciliation moved
to *after* the report rather than before it, so it sees the complete ledger.

---

## [PHASE 1 | 2026-08-02] Cost model recalibrated from measurement

The stage profiles are no longer estimates. Measured across both runs:

| Stage | Old profile | Measured | Scales with run size? |
|---|---|---|---|
| `agent_action` | 1,000 / 120 | **750 / 170** | yes — 404 in at 25 agents, 748 at 100 |
| `agent_generation` | 1,200 / 350 | **1,900 / 550** | no — 1,900/548 and 1,900/537 |
| `event_measurement` | 140 / 40 | **78 / 87** | no |
| `objection_canonicalization` | 3,000 / 3,000 | **11,000 / 6,000** | with distinct phrasings, not events |
| `report` (per section) | 18,000 / 2,500 | **5,650 / 4,250** | no — evidence is capped |

`agent_action` input grows with the feed and the agent's memory, but both are
capped by the adapters (top 8 posts, last 10 actions), so it plateaus rather
than climbing indefinitely. Calibrating at the reference shape means small runs
are over-quoted, which is safe.

**Two model errors, found only because measurement disagreed with the estimate:**

**Platforms were multiplying agent-action cost.** `action_units` was
`agents × rounds × platforms × variants`, but `agent_count` is the whole swarm
and `run_prepare_agents` *splits* it — 100 agents over 2 platforms is 50 on
each, not 100 on each. Measured: exactly 500 action calls against the 1,000 the
formula predicted. This inflated the largest stage of every quote by the
platform count and is most of why runs were over-quoted ~2×.

The honest consequence is worth stating plainly: **adding a platform is close to
cost-neutral**, because it spreads the same swarm thinner rather than buying
more simulation. Platforms cannot be sold as volume.

**Only ~80% of actions were assumed to produce events.** Measured 497 from 500.
The assumption came from agents answering NOTHING, which they rarely do now that
the action prompt states the subject.

**Result:** standard run $3.23 → **$2.26**, estimate against measurement
**1.02×**. The blended agency mix falls $11.77 → $6.88, so a 400-run/month
enterprise quote drops from ~$21,000 to ~$12,515 *at the same margin* — the old
number was over-priced by a broken model, not protected by a policy. Tier run
counts rise (Founder 6 → 8, Growth 20 → 26, Agency 69 → 88) for the same reason:
the grants and the 80% margin are untouched.

**Decision — one formula, not two.** `_stage_costs()` now derives the unit
counts in a single place. They had been written out twice, in
`estimate_simulation_cost` and in the reference-run helper, and the two drifted
apart during this very recalibration — so a run's price and its "worth N
standard runs" line were briefly computed from different formulas.

---

## [PHASE 1 | 2026-08-02] Agent identity, fixed structurally

The username-collision fix committed earlier — deduping handles at generation —
patched the symptom. It left the flaw in place: **the adapter boundary carried
only a username**, so agent identity, per-agent memory and event attribution all
routed through a string an LLM invented. Dedup made collisions unlikely; it did
not make identity real. Any future agent-creation path, imported swarm, or
adapter that forgot the convention would reintroduce the same bug.

**Scope, measured on production.** 248 colliding username groups across **44 of
63 simulations**, 377 of 2,512 agent rows, and every simulation from April 2026
onward. This is a **long-standing V1 defect, not a Phase 1 regression** — Phase 1
is simply the first thing that depended on agent identity being real, and so the
first thing to notice. Before Phase 1 the consequence was mis-attributed events
under a fabricated sentiment number; after it, the consequence is a confidence
interval computed from half the swarm.

**Decision — identity is `agent_id`, username is display.** `SimulationEvent`
gained an `agent_id`; all twelve adapters receive it, key `record_action` /
`get_agent_memory` on it via `BasePlatformAdapter.agent_key()`, and stamp it on
every event they emit. `run_simulation` attributes from `event.agent_id`, with
the old username lookup retained only as a fallback for events that lack one.
Collisions become cosmetic rather than corrupting.

**Decision — enforce the invariant in the database, not in convention.**
Migration `019` adds a unique index on `(simulation_id, username)`. Layers 1 and
2 are conventions enforced by code somebody will eventually change; the database
is the only place an invariant holds regardless of who writes the next caller.

The rename that precedes the index uses `~` as its suffix separator, which the
generator cannot emit — so `(simulation_id, base, occurrence)` being unique by
construction makes a single pass provably sufficient. A plain numeric suffix
would not be: renaming a duplicate `mchen` to `mchen2` can collide with a
literal `mchen2`. Dry-run against production: one pass, **0 duplicates
remaining**, 0 existing usernames containing `~`.

**Decision — do not apply 019 until the merge.** `master` is the deployed branch
and has no dedup, and collisions occur on essentially every run. Adding the
index now would fail agent insertion on every new simulation — an outage of the
live product caused by a migration for an unmerged branch. It is applied in the
same window as the merge, after the deploy carrying the generation-time dedup.
This is the first migration in the V2 sequence that is *not* safe to apply
ahead of the merge, and the file says so at the top in a banner.

**Not repairable.** Renaming does not restore attribution — there is no record
of which of nine identically-named agents produced a given event. Every pre-fix
run has an understated agent count and intervals wider than truth. That includes
both Phase 1 live runs, which is why the recalibration used their *token* counts
(unaffected) and not their agent counts.

**The generalisable lesson.** A value generated by a model is not an identifier,
however unique it looks in a sample. If something must be addressable, give it an
id you control, pass the id, and let the generated string be a label. The tell
here was arithmetic that could not be true: 45 agents acting once per round for
5 rounds cannot produce 497 events.

---

## Known issues carried into Phase 2

Recorded here so they are not rediscovered. Items 1, 2 and 7 from the Phase 1
list are resolved above.

1. **A/B never runs variant B.** `run_simulation_ab` in `workers/simulation_tasks.py`
   calls `run_simulation` once. `simulations.variants` exists and is priced, but
   nothing executes more than one arena, so `MAX_RUNNABLE_VARIANTS = 1` now
   blocks multi-variant runs from being configured or quoted. **Phase 3 raising
   that constant to 8 is the switch that turns N-way on** — along with actually
   implementing per-variant arenas.
2. **The live WebSocket feed is empty.** The active runner publishes nothing to
   Redis, and `SimulationRunPage` filters on `event_type === 'agent_action'` while
   the backend schema emits `post`/`comment`/`react`. The UI silently falls back
   to 5-second polling. Not addressed in Phase 1 — the measurement layer took
   priority and the streaming contract is unchanged.
3. **No org switcher.** `core/auth.py::get_current_org` takes the user's *first*
   organization membership, so multi-org users are silently locked to one.
4. **Background jobs are not durable.** Every job is `asyncio.create_task` inside
   the API process, with no queue and no worker service in `render.yaml`.
   Restarting the backend kills in-flight simulations with no resume. Phase 1
   made this worse in one respect: measurement and analysis now run inside the
   same task, so a restart late in a run loses the artifact as well as the run.
5. **Stripe tiers still carry V1 names and prices.** `PLAN_PRICE_MAP` maps
   `starter`/`pro` to $149/$499 Price IDs. `TIER_CREDIT_GRANTS` and `TIER_CAPS`
   map both the V1 names and the V2 ones (`founder`/`growth`/`agency`) so nothing
   breaks, but the actual tier migration — new Stripe Products, regional Price
   IDs, `pricing_region` gating on card country — is unbuilt.
6. **Model upgrade available, deliberately deferred.** Config pins
   `claude-opus-4-7`; Opus 5 is available at the same $5/$25 rate. On Opus 5
   thinking is *on by default*, and agent action calls set `max_tokens=160`, so
   thinking would consume the budget and truncate every action. Migrating
   requires setting `thinking` explicitly and re-tuning `max_tokens`. Less urgent
   now that actions run on Haiku, but the report stages would benefit.
7. **The measurement classifier is unvalidated against human judgment.** Nothing
   yet checks that Haiku's valence agrees with what a person would say. The
   calibration loop (Phase 4) is the eventual answer; a smaller interim check
   would be hand-scoring 50 events from a real run and correlating.
8. **`simulations.metadata.sentiment` still exists on 10,236 historical events.**
   Written by the removed drift formula. Nothing reads it — `react_tools` was
   switched to the artifact — but it is stale data that will read as real to
   anyone querying the table directly.
