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

## [PHASE 2 | 2026-08-03] The audience is derived, not picked

DECISIONS §3 settled that the ICP comes from the founder's own material rather
than from a library of 16 packs. This is that, plus the adversarial cohort it
has to carry, plus the stage registry the rest of Phase 2 reads.

**Decision — the ICP profile and the persona pack are one row, two shapes.**
A founder reads role, budget authority, incumbent tooling, switching cost and
skepticism triggers, and corrects them. The engine reads a `PersonaPack`:
demographics, Big Five, posting cadence. `icp_synthesizer.compile_pack` is the
only bridge, and `icp_profiles` stores both — the editable profile and the
compiled pack — so an edit and the pack the next run uses cannot drift apart.
Nothing downstream of `run_prepare_agents` learns that ICPs exist; `get_pack`
resolves the `icp_` prefix out of the new table and everything else is unchanged.

**Decision — the pack is recompiled on write, never on read.** A pack rebuilt at
read time would make a re-simulation's audience depend on when it was read, and
the inoculation loop's whole claim is that the audience did not change between
the two runs. The ICP pack is also the one pack that is deliberately *not*
cached in `_pack_cache`: built-in packs are files and cannot change under a
running process, but a founder can edit an ICP between runs, and a
process-lifetime cache would serve the pre-edit audience to whichever API worker
loaded it first.

**Decision — the built-in packs become priors, in code and not just in prose.**
A synthesized archetype states what a buyer cares about and what they would have
to rip out. The nearest built-in archetype supplies the Big Five vector and
posting cadence, recorded in `icp_profiles.prior_pack_ids`. Asking a language
model to invent psychometrics per project produces numbers with no referent that
then propagate into every agent in the run.

**Decision — `ArchetypeContext` reaches the agent-generation prompt.** The value
of a synthesized ICP is entirely in fields the pack format has nowhere to put:
what this archetype uses today, what switching would cost, what makes them stop
reading. Without carrying those into the prompt, a synthesized ICP is a
relabelled generic pack — the exact outcome DECISIONS §3 rejected the pack
library to avoid. `Archetype` gained three optional fields, absent on all 16
built-in packs, so the JSON on disk validates unchanged.

**Decision — the adversarial guardrail is enforced in data, at two layers.**
PRD §4 permits an incumbent-aligned agent to name a competitor only from
material the user uploaded and marked as competitor material. That is
unenforceable unless the database records which document is which, so
`documents.material_kind` does — and `NULL`, meaning uploaded before the column
existed, reads as `own`, because an unlabelled document must never be the thing
that authorises naming a competitor.

The rule then holds at two layers. `AdversarialArchetype` refuses to validate
with a `competitor_name` and an empty `grounded_in`; `_ground_adversarial`
strips the name from any archetype whose citation is not in the project's
competitor-material set, before validation. **The name is stripped, not the
archetype** — an unnamed category skeptic is still the cohort PRD §4 asks for
when there is no competitor material, and dropping the archetype would quietly
remove the adversarial cohort from precisely the runs that have none, which are
most early runs and the ones where "we already have a process for this" is the
objection that matters. By the time a confabulated incumbent reaches a report it
has already been through agent generation and into verbatim quotes, and there is
no honest way to redact it there.

**Decision — the cohort share is expressed as archetype weight, and re-applied
at prepare time.** `run_prepare_agents` allocates by weight and knows nothing
about cohorts, so a share has to be weight or nothing. It is re-applied from
`simulations.adversarial_share` at prepare rather than baked in at synthesis,
because an ICP is reused across runs and a founder who wants the reception at
40% incumbents should not have to re-synthesize their audience to find out. The
0.5 ceiling is enforced in the migration, the create endpoint, and the ICP API:
past half the swarm the headline valence is a function of the share the user
picked, and it will still be read as a measurement of the market.

A share configured without an ICP is rejected at create rather than silently
doing nothing — built-in packs carry no adversarial archetypes, so the run would
otherwise complete and report a cohort split the user configured and never got.

**Decision — synthesis is metered as its own stage, charged per synthesis.**
`ICP_SYNTHESIS` is priced in `agent_pricing` and runs inside
`usage_context("icp_synthesis")`. It is not folded into the run quote: an ICP is
a project-level object reused across every run in the project, so folding it in
would charge the second run for work the first one did. Leaving it out of
pricing altogether is Phase 1's bug #6, where objection canonicalization was 24%
of measured spend and 0% of the quote.

**Its profile is estimated, not measured** — the only one in the model that is.
It is sized from the material budget in `icp_synthesizer` and deliberately
biased high, because an over-quoted stage costs a customer credits they can see
while an under-quoted one is served at a loss nobody notices. Re-derive it from
`llm_usage` after the first live Founder-lens runs.

**Decision — one narrower retry, rather than a higher token ceiling.** Synthesis
writes a whole profile in one object, which is how Phase 1's canonicalizer failed
(bug #7: a single main-model call whose output hit `max_tokens` exactly and
returned unparseable JSON, on the run that mattered). On a parse failure the
retry halves the archetype budget instead of raising the ceiling. Three sharp
archetypes are a better ICP than six vague ones, so the degraded path is barely
degraded.

**Decision — `lens` and `founder_stage` are nullable with no backfill.** The 63
existing simulations were run before lenses existed. Stamping them `crisis` or
`founder` would invent an attribute nobody recorded, which is the failure mode
Phase 1 spent itself removing. `NULL` reads as "legacy, no lens".

**The stage registry is data.** `services/engine/founder_stages.py` declares all
five stages: expected inputs, audience defaults, the questions the report must
answer, and — the load-bearing field — `cannot_conclude`. A concept-validation
run has no product to adopt, so it cannot measure adoption intent; a fundraise
run models how a story reads, not whether the round closes. Those limits live in
the same object that drives the report, because a caveat that lives in a doc
reaches nobody. Adding a sixth stage is a dict entry rather than a search for
every `if stage ==` in the codebase.

Concept validation defaults to a **0%** adversarial share and growth to **40%**,
which is the whole argument for stages in one number: at concept there is no
product to switch away from and an incumbent cohort would be arguing with a
problem statement, while at growth the buyer already has something that works.

**Migration 020 is safe to apply while `master` is deployed** — one new table,
new nullable columns, and defaults that reproduce today's behaviour exactly.
This is deliberately unlike 019, which still waits for the merge.

---

## [PHASE 2 | 2026-08-03] The headline is not the market, and the artifact says so

A run with 40% incumbent-aligned agents produces a negative headline **by
construction**. That is the point of the cohort — but a founder reading −0.4
without knowing the swarm was configured to argue against them is being misled
by a number that is, technically, measured. Phase 1's rule was that every number
is measured; this is the corollary, that a measured number still needs to say
what it measured.

**Decision — a cohort split, separate from the archetype breakdown.** They
answer different questions. `by_archetype` says which *kind of person* reacted
how; `by_cohort` says how much of the negativity came from agents constructed to
oppose. No archetype table makes the second legible, because a founder does not
know which of their six archetypes were the adversarial ones. Empty on a run
with no cohort — a one-sided split is not a split.

**Decision — the disclosure sentence is composed once, in the artifact.** PRD §4
requires adversarial agents to be labelled synthetic in every report and export.
There are five renderers — the viewer, the print page, the PDF, the PPTX, the
JSON export — and a rule re-implemented in five places is a rule that will be
missing from one of them. `AdversarialDisclosure.disclosure` holds the sentence;
all five read it. The PPTX gets its own slide rather than a methodology bullet,
because a deck is presented one slide at a time and a disclosure sharing a slide
with the platform list is a disclosure that gets skipped.

**Decision — a cohort slice reports allocation, not only participation.** A
cohort allocated 40 agents that spoke twice is a finding. It is only visible if
the denominator is the allocation, so `agents_total` sits next to `agent_count`
and the UI shows "3 of 40 agents spoke" when they differ.

**Decision — an objection originated adversarial only when *every* first-round
voice was adversarial.** A mixed first round means the objection was already in
the market's mouth, and crediting the incumbent for it overstates the cohort's
influence — which is the direction this feature is most likely to be wrong in.
The pair (`originated_adversarial`, `buyer_agent_count`) is what makes argument 2
for the cohort — "competitor advocates start the narrative decline" — checkable
rather than asserted. An objection that starts adversarial and stays adversarial
is a competitor talking to themselves; one that crosses into buyers is the thing
the inoculation loop exists to answer.

**Decision — `SCHEMA_VERSION` moves to 2 even though both additions are
additive.** A client that renders a Founder-lens run without the disclosure
presents incumbent-aligned synthetic agents as ordinary market voices, which is
the one thing PRD §4 forbids. The frontend's refusal to render an unknown
version is the correct failure there, so `SUPPORTED_SCHEMA_VERSION` moves with
it in the same commit — a version bump shipped without the frontend mirror would
blank every report in the product.

**Decision — the report's lens context is prohibitions, not caveats.** A stage's
`cannot_conclude` list reaches the outline prompt and every section prompt as
"do not state or imply", because a model handed a caveat writes the claim and
then hedges it. The stage's `report_questions` come from the same registry the
stage picker reads, so the report cannot answer a different question from the
one the founder was shown when they chose the stage.

The naming rule is in the same block: with a grounded competitor, the writer may
report what agents said about them and may not state a fact about their product,
pricing, roadmap or customers — the uploaded material grounded the *name*, not
the claims. With none, it may not name one at all.

Legacy runs — no lens, no cohort — get an empty lens context and an unchanged
report. That is checked by a test, because "the new feature does not alter old
output" is the kind of property that quietly stops being true.

---

## [PHASE 2 | 2026-08-03] The inoculation loop, and the verdict it is allowed to give

DECISIONS §4: detect → draft → **re-simulate with the asset pre-seeded** → prove
the delta. Step 3 is the entire product. Without it, "here's what to
pre-position" is an LLM opinion every competitor can generate. With it, Saibyl
can say *this disclosure moved this objection from 34% of the swarm to 9%*.

**Decision — a re-simulation is an ordinary simulation with a parent.** It
measures, analyses, reports, prices and reconciles through the same code as any
other run, so the before number and the after number come out of one builder. A
bespoke "inoculation run" object would produce two numbers computed by two code
paths, and those are not comparable however carefully they are labelled.

**Decision — the audience is copied, never regenerated.** `run_prepare_agents`
would put the same archetypes through the model again and produce different
people. The child's agents are row-for-row copies — same usernames, same
profiles, same cohort flags — so the only thing that differs between the two
runs is the material the agents were shown. That is the claim the whole feature
rests on, and it is also why `create_resimulation` returns a run already in
status `ready`.

This is the one place in the codebase where username is used to pair records
across simulations, in `_converted_agents`. It is sound *because* of the copy:
the pairing is by construction rather than by hoping handles are unique — which
they are not, as §1a records at length.

**Decision — assets are pre-positioned, not posted.** They reach agents through
`topic_block()` as material published alongside the subject, visible to everyone
from round one. A feed post would model *someone dropped the FAQ into the
thread* — a different, weaker intervention that reaches only the agents whose
feed slice happened to include it. One hook on `BasePlatformAdapter` covers all
twelve adapters; adding it to twelve `initialize` implementations would be
twelve chances to miss one, and a missed adapter produces a re-simulation whose
agents never saw the asset and a result that reads "the asset did not work".

**Decision — reach is a share of agents, with an interval on the proportion.**
An objection voiced ten times by one agent is one agent's objection — the same
clustering rule as `mean_interval`, applied to a proportion. It is also what
makes the two runs comparable when one produced more events than the other.

**Decision — zero observed is not certainty.** `_proportion_interval` reports an
upper bound of 3/n when nothing was observed, so "no agent raised it in 40" is a
band up to 7.5%, and in a 12-agent run it is 25%. Declaring an objection dead on
zero observations is the most tempting overstatement in the loop, and this is
the line that refuses it.

**Decision — `unresolved` is a verdict, and it does not count as effective.** A
move from 34% to 31% is reported as unresolved, never as progress. `effective`
requires separated intervals *and* a downward move, because `assets_effective`
is the number this product is sold on and it has to be one a sceptic would
accept. An asset that does not work is the most valuable thing the loop can
report — it is the one finding an LLM opinion structurally cannot produce, since
a model asked whether its own suggestion would work says yes.

`emerged` exists for the same reason: an asset that answers one objection and
raises two is a result the founder needs *before* they publish it.

**Decision — the hypothesis is recorded before the test runs.** An unstated
hypothesis is always retroactively correct. `inoculation_assets.hypothesis` is
written at draft time and judged against the measurement.

**Decision — a re-simulation is not charged for agent generation.** It copies
its parent's agents and provably makes zero generation calls, so
`estimate_simulation_cost(..., reuse_agents=True)` drops the stage. The honest
quote is also the one that makes the second run of the loop cheaper than the
first, which is the right incentive for the step the product is sold on.

**Decision — asset drafting is charged per pass, like ICP synthesis.** A founder
can draft, discard, and draft again without ever running a re-simulation, and
each of those is a main-model call that was made. Its profile is estimated and
must be re-derived from `llm_usage` after the first live loop; the stage is
already attributed as `inoculation_draft`, so the data will be there.

**Decision — a failed comparison does not fail the run.** `measure_inoculation`
is wrapped: the run itself is valid, measured and paid for, and the comparison
is derived from two stored artifacts. `POST /result/rebuild` recomputes it for
free, because a task that dies after a run completes must not cost a second run
to recover from.

**Migration 021 is additive and safe to apply while `master` is deployed.**

---

## [PHASE 2 | 2026-08-03] The Founder lens on screen

**Decision — the stage list is fetched, never duplicated in the frontend.**
`GET /api/simulations/founder-stages` serves the same registry the report
planner reads. A copy in the picker would eventually disagree with the report,
and the disagreement would be invisible: the founder would choose a stage whose
described limits are not the limits the report was written under.

**Decision — the stage's `cannot_conclude` list is shown at intake.** Before the
run, not as a footnote afterwards. The point of stating a limit is to stop
somebody asking a question the run cannot answer, and by the time they are
reading the report they have already asked it.

**Decision — choosing a stage adopts its audience default.** Concept validation
sets the adversarial share to 0 and growth to 40%. A picker that changed the
label and nothing else would be decoration; that difference is the substance of
stage-awareness.

**Decision — the adversarial slider is disabled without an ICP, with the reason
on screen.** The share is expressed as archetype weight and the built-in packs
carry none, so a share applied to them silently does nothing. The API rejects it
too; the UI says why rather than leaving the user to discover a 400.

**Decision — `lens` is null unless a stage was chosen.** The UI never defaults
to `'founder'`. A run with no stage is an unlensed run, which is what every
simulation before Phase 2 was, and stamping one with a lens the user did not
choose is inventing an attribute — the failure mode migration 020 avoided in the
backfill and this avoids at the point of creation.

**Decision — the Inoculate tab is appended, not inserted.** `activeTab` is an
index, and renumbering the existing tabs would silently change what a linked or
remembered position points at. It sits at index 5 with the label between
Objections and the rest, which is where the founder already is when they decide
to act on one.

**The workbench never renders an unsupported improvement.** A delta whose
intervals overlap says so in the row, next to the number. This is the one place
in the product where the temptation to show green is strongest — the founder
just paid for a second run — and it is the place where doing so would destroy
the only thing the loop sells: that it can come back and say the asset did
nothing.

---

## [PHASE 2 | 2026-08-03] Cost model: the report was under-counted by two sections

Measured against the first live Founder-lens run, the estimate came in at 0.955x
of actual. The aggregate was fine; the composition was not, and two errors were
cancelling.

**The report writes more sections than it prices.** `report_section_count`
returned 4, the outline produced 4, and the report then wrote **6** — it appends
an executive summary and a conclusion, neither of which comes out of that
function. A third of the largest main-model stage in every run was never quoted.
This is Phase 1's #9 and #10 one level up: not the report being written at the
wrong depth, nor its spend going unmetered, but the *unit count in the quote*
disagreeing with what the writer does. `REPORT_FIXED_SECTIONS = 2` closes it, and
`REPORT_SECTION` is recalibrated per **written** section — estimate now $0.8715
against $0.8709 measured.

**Canonicalization was under-quoted** at 11,000/6,000 against 13,950/8,000
measured — and the output was capped, so the measurement is a floor. Priced at
14,000/10,000, to be re-derived once the raised ceiling lets output find its
level.

**Two profiles deliberately left alone.** `AGENT_ACTION` measured 312 input
against a profile of 750, and `AGENT_GENERATION` 1,459 against 1,900. Neither is
a shifted mean:

- Agent-action input is **platform-dependent**. This run used Hacker News and
  LinkedIn, whose feed slice is a compact `[id] title (points)` line; the Phase 1
  calibration ran on adapters that put post bodies in the feed. Calibrating down
  to 312 would under-quote every Twitter and Reddit run in order to make Hacker
  News runs exact. The real fix is a per-adapter profile; until then 750 is a
  ceiling across platforms rather than an average of them, on purpose.
- Agent-generation input is **document-dependent** — the prompt carries
  `doc_context[:2000]`, and this project's two short Markdown files do not fill
  the slice a PDF deck would.

**Consequence, which is a pricing decision and not a code one.** Standard-run
COGS moves $2.26 → **$2.71**, and tier run counts fall: Founder 8 → 7, Growth
26 → 22, Agency 88 → 73. `PRICING_GUIDE.md` §2.3's table and every enterprise
quote derived from $2.26 now understate cost by ~20%. The tables are **not**
regenerated here — DECISIONS §15c set the precedent of passing a corrected cost
base through to price when costs fell, and the same question arriving in the
opposite direction deserves an explicit decision rather than a silent edit.

---

## [PHASE 2 | 2026-08-03] The first live Founder-lens run, and the four defects it found

Parent `f980fe0d` — 96 agents / 5 rounds / 2 platforms, `pre_launch_positioning`,
30% adversarial, against Saibyl's own product brief plus one competitor
document. Child `fa28d899`, same audience, six assets pre-positioned.

**None of the four were visible to static verification. 187 tests passed
throughout.** That is now the second phase in a row where the test suite was
green and the live run was not, which should be read as a statement about what
tests can do rather than about these tests.

### 1. Objection keys did not survive across runs — the loop measured nothing

**The most serious defect in Phase 2, and it failed in the most flattering
possible direction.** The parent produced 46 canonical objections, the child 39,
and they shared **zero keys**. Every parent objection therefore read as `died`,
every child objection as `emerged`, and **all six tested assets scored
effective** — a report of total success from a comparison that had matched
nothing.

Migration 021 asserts that `objection_key` is "stable and deterministic from the
label". The key is; **the label is not.** Clustering runs independently per
simulation and names the same objection differently the second time.

**Fix.** `canonicalize_objections` takes the parent's objections as priors and
the clustering prompt instructs the model to reuse an existing key when a group
is the same objection said again. Keys carried over went 0 → 27 of 46, and
`assets_effective` 6/6 → **3/6**. Verdicts now spread across shrank 7, died 7,
unresolved 29, unchanged 3, emerged 1.

A `objection_keys_share_nothing_with_parent` error fires at ERROR level when a
re-simulation carries nothing over, because the symptom of this bug is a
perfect score and nobody investigates a perfect score.

### 2. The asset drafter fabricated evidence

Asked to answer *"no proof synthetic feedback predicts real behavior"*, the
drafter **invented the proof** — "in our 14-case internal dataset, the
rank-order of objections matched real-user feedback in 11 cases (Spearman's
ρ = 0.74)" — and carried it into three assets. No such dataset exists; the
uploaded material lists the absence of validation data as a *gap*.

This is Phase 1's bug #5 one level over. The report was stopped from writing its
own numbers by making the measured object impossible to route around. The asset
drafter has no measured object to route to — it writes prose about the founder's
own product — so the equivalent protection is refusing to store the claim.

**Fix.** An explicit prompt prohibition, plus `_evidence_claims`, which drops any
asset pairing a number with evidential language when that number is not in the
uploaded material. Dropped rather than flagged: this is copy a founder may
publish verbatim as their own claim, and unlike a competitor name there is no
partial version worth keeping — the asset's whole argument rests on the invented
figure.

The detector is deliberately narrow, and the prompt rule is the first line. A
price the team sets passes; a correlation coefficient does not.

### 3. Agent generation truncated again — bug #3, third occurrence

`_context_block` made the generation prompt richer, the model matched it with a
longer answer, and one profile in 96 ran past `max_tokens=900` into a topic-less
stub. Mean output is 376 tokens, so this is tail variance — and **the tail gets
fatter as the ICP gets richer**, meaning the failure rate rises exactly as
synthesis gets better.

Raised to 1,400. The Phase 1 guard test pinned the literal `900`, so it failed on
the *fix* rather than on the regression; it now asserts a floor.

### 4. Canonicalization ran at exactly its ceiling

`completion_tokens` came back as exactly `CLUSTER_MAX_TOKENS`. It survived only
because the JSON closed before the cut and `_extract_json` discards trailing
prose. The adversarial cohort is what pushed it: **728 distinct phrasings**
against Phase 1's 601 at a comparable event count, because incumbent-aligned
agents raise objections buyers do not.

Raised to 16,000 — and the re-canonicalization in fix #1 then used **13,955**,
which the old ceiling would have truncated outright. A near-ceiling warning now
fires at 90%.

### What the run confirmed

- **Adversarial allocation: 30 of 96 = 31.2%** against 30% configured — the
  weight-rebalancing risk in HANDOFF §1b holds at the standard shape.
- **96 of 96 distinct usernames**, 480 events, **0 orphaned** — the Phase 1
  identity fix holds on a compiled ICP pack, a new agent-creation path.
- Measurement 480/480, 100% coverage, zero batch failures, both runs.
- **The cohort split did its job**: headline −0.146, buyers −0.049 (CI −0.155 to
  **+0.057**, spanning zero), adversarial −0.359 (CI −0.425 to −0.293). The
  intervals do not overlap. The entire negative headline is the cohort the run
  was configured to include, and without `by_cohort` a founder reads it as a
  market verdict.
- The grounding guardrail held live: two adversarial archetypes named Remesh
  **with** the competitor document cited, two argued unnamed. The drafted
  comparison page cited only what the material says and concedes "most teams
  should not replace real-audience research with Saibyl".
- Pre-positioning reaches agents: **20–28% of events per round** reference the
  published material, confirming `topic_block` delivery.
- `report_progress_publish_failed` did not kill the report with Redis absent —
  Phase 1's bug #4 fix working.

### The measured delta, and why its magnitude is not trustworthy

Three of six assets moved their objection beyond the bands; three did not, one of
those in the wrong direction. That mixed result is the loop behaving correctly.

**The headline swing of −0.146 → +0.457 is contaminated**, because three of the
six assets carried the fabricated ρ = 0.74 claim, so the swarm was partly
reacting to invented proof. The mechanism is validated; the effect size is not.
A re-run under the fabricated-evidence guard would drop those assets. Do not
cite this delta as a calibration figure.

---

## [PHASE 2 | 2026-08-04] The re-simulation was being under-charged, and three profiles re-derived

HANDOFF §0 items 3 and 4 — re-derive the estimated and ceiling-capped stages from
`llm_usage`. That was the assignment. The ledger answered it and then volunteered
something nobody had asked about.

### What the assignment found

**`ICP_SYNTHESIS` and `INOCULATION_DRAFT`** were the two stages in the model that
had never been measured. One live pass each, which is a check and not a
calibration, and the check is worth having:

| Stage | Estimated | Measured | Action |
|---|---|---|---|
| `icp_synthesis` | 14,000 / 4,500 | 2,419 / **4,487** | output confirmed; input held |
| `inoculation_draft` | 4,500 / 5,000 | 2,532 / **5,641** | output raised to 5,700 |

Both outputs were derived from the response schema and both landed near it, which
is the part that matters — the schema is what bounds the response. `INOCULATION_DRAFT`
was *under*-estimated on a run that drafted the maximum twelve assets, so there is
no larger case above it and the figure moved.

Both inputs are held at their ceilings for the reason `AGENT_GENERATION` is:
the measured runs did not fill the material budget. Calibrating a
document-dependent input to a thin-document run under-quotes every project that
uploads a real deck.

**`OBJECTION_CANONICALIZATION`** was flagged as a floor rather than a measurement,
because its one large observation was truncated at the old 8,000 ceiling. It is
neither — it is a ceiling, and the reason it looked like a floor is now legible.
Input bought 728 phrasings at 13,950 tokens, and `MAX_DISTINCT_STRINGS` truncates
the shortlist at 800, so no run can present materially more. Output cannot be
measured directly, but the clusterer returns members as *indices*, which makes the
response size reconstructable: fitting the two untruncated runs (124 phrasings /
19 groups → 2,587; 601 / 17 → 4,972) gives ~88 tokens per group plus ~7.4 per
phrasing, predicting **9,435** for the truncated run — consistent with a response
cut off at 8,000, and under the 10,000 already priced. Left unchanged; two points
do not justify tuning three significant figures.

**`EVENT_MEASUREMENT`** was not on the list and should have been. Its profile was
78 in / 87 out, calibrated on `03de92ef` alone. Across four runs the per-event
input measures 78 / 81 / 99 / 88 — the profile sat at the *minimum* of its own
observations, so every Founder-lens run under-quoted it by ~26%. Raised to 99/92,
the maximum on each axis. This is $0.02 on a standard run; a profile sitting at
the floor of its range is a calibration error regardless of size.

### What the ledger volunteered

**A re-simulation carries its inoculation assets in every single agent action
prompt, and nothing charged for it.**

The pair that shows it is the cleanest controlled comparison in the ledger:
`f980fe0d` and `fa28d899` are the same 96 agents, the same 5 rounds, the same two
adapters, differing only in the six assets the child pre-positions.

| | parent | child |
|---|---:|---:|
| agent action, input | 312 | **1,654** |
| agent action, output | 175 | 216 |
| canonicalization, output | 8,000 *(capped)* | **13,955** |
| measured COGS | $2.307 | **$2.553** |
| quoted | $2.674 | **$2.378** |

Figures exclude the drafting pass, which is quoted on its own, and count one
clustering call per run. The child's raw ledger total is $2.660 because it was
re-clustered after the key-carryover fix; that second call is a repair, not what
the run costs — and note the quote was under *both* numbers.

Assets ride in `topic_block()` and `topic_block()` is rebuilt per call, so six
assets at `ASSET_BODY_IN_PROMPT` = 700 characters each are re-sent across all
2,880 action prompts. 224 tokens per asset per action, corroborated by
construction at ~205. The canonicalization figure has a second cause: a
re-simulation's clustering call carries the parent's objections as priors, and the
*same run* measured 3,162 output tokens without that block against 13,955 with it.

The child was quoted **$2.378** against $2.553 of measured spend — a **78.5%**
margin where the model targets 80%, and 77.6% against the as-billed total. Above
the 70% floor, so `reconcile_run_cost` logged nothing and nothing alarmed. The
size of the miss is not the point; its direction is, and so is the fact that the
only run in the product that had *never* been checked against its own bill was
the one the Founder lens is sold on.

**The failure was in a comment.** `_stage_costs` asserted that dropping the
generation stage "makes the second run of the loop cheaper than the first — which
is exactly the right incentive for the step the product is sold on." Pleasing,
load-bearing, and false. A re-simulation skips generation and then spends more
than it saved. `DECISIONS §4` carried the same claim, and `test_reuse_does_not_
change_any_other_stage` asserted it — a green test pinning a belief the ledger
contradicts. All three are corrected.

This is Phase 1's bug #6 in a new place. There, objection canonicalization was 24%
of measured spend and 0% of the quote. Here, an entire stage's *unit of work*
changed underneath a profile that still looked calibrated, and the thing that
concealed it was a plausible story about why the number should be lower.

### Changes

- `INOCULATION_ASSET_ACTION` — 225 in / 7 out, charged per asset **per action**.
- `OBJECTION_CANONICALIZATION_RESIM` — 14,000 / 16,000, selected when the run has
  a parent. Priced at `CLUSTER_MAX_TOKENS` rather than at the single observation,
  which already sat at 87% of it with an unusually small phrasing set.
- `estimate_simulation_cost` and `check_credit_budget` take `inoculation_assets`;
  `POST /simulations/{id}/start` derives it from `inoculation_asset_ids`.
- **A re-simulation cannot be started against a quote.** `issue_quote` knows
  neither flag and `consume_quote` validates only agents/rounds/platforms/variants,
  so a parent-shaped quote would validate cleanly against the child and charge for
  the wrong run. Refused with a 409 rather than silently ignored.
- Five tests, including the measured loop as a floor: the quote for either run of
  `f980fe0d`/`fa28d899` must not fall below what that run actually cost.

### Effect on published numbers

Standard run COGS **$2.71 → $2.74**, blended agency mix **$7.35 → $7.46**, tier
run counts **7/22/73 → 7/21/73**. Only Growth moves, and only because it sat at
21.9. All tables regenerated from `scripts/quote.py`.

A re-simulation of the reference shape is now **$3.13**, and the full loop —
parent, drafting pass, re-simulation — is **$5.97**, or 2.18 standard runs.

**The free grant now has 20 credits of headroom** on a 1,180-credit free run.
That is 1.7%, it has been under 30 since the grant moved to 1,200, and it is not
caused by this pass — the previous revision left 24. Any stage repricing consumes
it and the symptom is a signup that cannot complete its one promised run.
Unresolved; the grant is a commercial number.

### Reconciliation — every measured run against the corrected model

No live run was made for this pass; it is a pricing change, and the ledger
already holds four runs to check it against. Quote versus what each actually
cost, one clustering call per run, drafting priced separately:

| Run | Quoted | Measured | Ratio |
|---|---:|---:|---:|
| `05f1d879` 24ag/3rd | $1.168 | $1.191 | **0.98×** |
| `03de92ef` 100ag/5rd | $2.736 | $2.418 | 1.13× |
| `f980fe0d` 96ag/5rd Founder | $2.674 | $2.307 | 1.16× |
| `fa28d899` re-simulation | $3.127 | $2.553 | 1.22× |

The over-quoting is `AGENT_ACTION` held at 750 tokens against runs that measured
312 and 633 — deliberate, and the reason is in the profile's comment.

**`05f1d879` quotes below its bill, and it is a legacy artifact rather than a live
defect.** That run made **9 Opus report calls on 72 events** — more than the
497-event run's 8 — because it predates the depth-scaling fix by 46 minutes.
Today's `report_section_count(72)` gives 2 sections, so 4 written; that run wrote
about 6. Re-running the same shape on current code would land near 1.1×. It is
the oldest run in the ledger and the only one whose report stage does not match
the code that would produce it, which is worth remembering before citing it for
anything else.

### What this does not fix

`AGENT_ACTION` is still one number across twelve adapters, and the split is now
measured rather than inferred: **748 input tokens per action on Reddit +
Twitter/X against 312 on Hacker News + LinkedIn**, same shape. The profile is the
higher one, so compact adapters are over-quoted on purpose. A per-adapter profile
needs a `platform` dimension on `llm_usage`, which does not exist — action calls
are not attributable to an adapter today — and it makes platform choice change
price, which contradicts "adding a platform is close to cost-neutral" in the
direction customers will notice. **Deferred by decision on 2026-08-04** — the
cost model is closed and the remaining precision is pennies. HANDOFF §8 item 15.

---

## [PHASE 3 | 2026-08-04] The Marketing lens — N-way matched swarms

DECISIONS §5 and §6, built. Three commits: the arenas, the scoreboard, the
surfaces that configure and read it.

### Arena isolation was already there

The expected work was building isolated arenas. It turned out not to exist:
`get_adapter()` returns a fresh `cls()` per call, and an adapter instance owns
its feed, its posts and its `_agent_history`. **One adapter instance per
`(platform, variant)` gives each variant its own world with no change to any of
the twelve adapters.**

The swarm is shared by handing the same agent rows, by id, to every arena — that
sharing is the entire basis of the comparison, and the reason agent generation
cost does not scale with variant count. An 8-variant run on 2 platforms builds 16
adapter instances over one generated audience.

Two guards, because both failures are invisible in a run that looks fine:

- **The runner stamps the arena's key on the event**, rather than echoing back
  `event.variant`. Trusting twelve adapters to return what they were handed
  means one of them forgetting merges two variants into one column of the
  scoreboard — which renders as a result.
- **A test asserts `get_adapter` returns distinct instances.** A shared adapter
  would put every variant in one conversation while still labelling the events
  apart. Every number would compute; none would mean anything.

`MAX_RUNNABLE_VARIANTS` 1 → 8, and the test that pinned it at 1 now asserts the
runner actually branches on arena, so the constant cannot run ahead of the
engine again — which is exactly what it existed to prevent.

### The propagation graph

The adapters have always emitted `SimulationEvent.target_id` and the runner has
always dropped it on write. That is why cascade metrics were not computable from
stored data.

Resolved in a second pass at write time, because the adapter's id (`post_3`)
means nothing outside the instance that minted it and only the runner knows the
database ids. A `post` event's `target_id` is the id it just minted — registered
in the map. A `comment` or `react` carries its parent's — resolved against it.

**The map is keyed on `(platform, variant, adapter_id)`, not on the id alone.**
Every arena mints its own `post_1`, so a global map would attach variant B's
comment to variant A's post: silently merging two isolated conversations and
inflating the exact metric virality weights most heavily. Children are grouped by
parent so one UPDATE covers a whole reply set rather than one per child.

> ⚠️ **Graph depth is structurally capped at 2.** `BasePlatformAdapter.comment()`
> takes a *post id* across all twelve adapters — there is no reply-to-reply. The
> metric is therefore named `cascade_branching` and measures replies per post,
> not depth. A depth figure would read 2.0 for every variant that got one reply
> and tell a marketer nothing. Raising it means changing the adapter contract.

### The scoreboard, and its three refusals

The measurement layer did most of the work: `event_measurement` has emitted
`intent` with exactly the PRD §6 taxonomy since Phase 1, so objective metrics are
a mapping onto values the classifier already produces rather than a change to the
agent action schema. Second time this phase that Phase 1's groundwork turned a
build into a wiring job.

What matters is what the scoreboard declines to say:

1. **`winner_variant_key` is None whenever the top two intervals overlap**, and
   `verdict` says so in words. A marketer acts on the top row; an ordering drawn
   from overlapping bands launders sampling noise into a spend decision. This is
   the inoculation loop's `unresolved` verdict applied to a comparison, and it is
   the single thing in Phase 3 most likely to be "improved" away by someone who
   finds a blank winner unsatisfying.
2. **Unmeasurable virality components are None and are dropped from the
   weighting**, with the remaining weights renormalised — not counted as zero,
   which would penalise a variant for a gap in the instrumentation.
   `components_used` records how many contributed, so a score built from three is
   not read as one built from six.
3. **An arena that produced nothing keeps its row.** A variant nobody engaged
   with is a finding. Deriving the variant list from the events rather than from
   the configuration would delete it instead of showing it scoring nothing.

Intent rates are proportions over **agents**, and zero observed carries the
rule-of-three upper bound — "no agent clicked, in 40 agents" reports a band up to
7.5% rather than a confident zero, the same convention the inoculation loop uses
so the two read consistently in one report.

Cross-archetype reach carries the heaviest weight (0.35). A share count cannot
tell virality from an echo chamber.

**Takeaway accuracy is lexical overlap, and is labelled approximate everywhere it
renders.** A per-variant main-model pass would price the lens out of the tier it
sells in; asserting accuracy without measuring it would be worse than a stated
approximation. The classifier gained a `takeaway` field inside the same batched
call, so it costs no extra request.

### The surfaces

`PUT /api/variants/{id}` replaces the whole set rather than offering per-variant
CRUD: keys are positional, so deleting the second of four renumbers the rest and
a per-row endpoint can leave a run half-keyed. It refuses once the run has
started, and refuses a single variant.

It also writes `simulations.variants`. `estimate_simulation_cost` charges
`agent_count × rounds × variants`, so a run whose column disagreed with its
variant rows would be **quoted for a different experiment than the one that
executes** — the Phase 2 defect class, caught before it shipped this time.

The viewer puts the verdict *above* the table and marks no row as leading when
the server named no winner. On a multi-variant run the scoreboard displaces the
headline, which averages every arena into one number describing none of them.

**The report writer was the piece most likely to undo all of it.**
`build_lens_context` gains a scoreboard block whose central rule is a
prohibition: when the server declined to name a winner, the writer must not name
one. A model handed six ranked rows with no instruction calls the top one the
winner, because that is what a ranked list reads like. This is Phase 1's bug #5
in its Marketing-lens form — not inventing a number, inventing a conclusion the
numbers do not carry.

### Migrations

**022** *(applied 2026-08-04)* — `simulation_variants` with org-isolation RLS;
`simulations.objective` with a CHECK on the six PRD objectives, nullable so
Founder and Crisis runs never acquire one; `simulation_events.target_event_id`
with a partial index.

**023** *(applied 2026-08-04)* — `simulation_events.takeaway`.

Both additive. Verified after: 68 simulations / 2,704 agents / 11,765 events / 8
orgs unchanged, **zero rows backfilled**, column types checked against
`information_schema` per the 017 lesson, `get_advisors` reports no RLS lint on
the new table.

### `SCHEMA_VERSION` 2 → 3

With `SUPPORTED_SCHEMA_VERSION` in `frontend/src/lib/analysis.ts` moved **in the
same commit**. The version moves for more than the added field: on a
multi-variant run the `headline` stops being the thing to read, so a client
rendering v3 without the scoreboard would show a marketer one confident sentiment
figure for a test whose whole purpose was to separate six alternatives.

### Verification, and what the live runs found

ruff clean · pytest **270 passed** (187 at the start of the day) · `tsc --noEmit`
clean · `eslint --quiet` clean · `vite build` OK · app boots, 119 routes, no
duplicate registrations.

**Two live runs, both 3 variants / 26 agents / 3 rounds, deliberately
underpowered** so the overlap refusal had a real chance to fire rather than being
proved only by unit tests.

`398bf601` — the first. It proved the arenas and broke the graph:

- **234 events = 26 agents × 3 rounds × 3 arenas.** The arenas are genuinely
  separate; a shared adapter would have produced 78.
- **`winner: None`.** The refusal fired live.
- **193 of 193 replies failed to link.** Cause below.
- Measured $1.44 against $1.70 quoted — margin held.

`37530696` — after the fix:

- **`unresolved_parents=0` across every round and every arena.** 77 events → 23
  posts + 54 links in round one, and 77 of 78 linked in rounds two and three,
  which also proves the map spans rounds.
- **`winner: None` again** — and the *ordering changed between the two runs*
  (Fear/Speed/Proof → Proof/Speed/Fear) on the same copy and the same audience.
  That is the refusal being right rather than cautious: the ranking is noise, and
  two runs put it in two different orders.

### The defect the first run found, which predates Phase 3

Every adapter renders its feed as `[<id>] @author: text` and asks for
`COMMENT <post_id>: …`. **The model copies the id with the brackets it was shown
in, inconsistently** — a five-sample check returned five bare ids and read as
healthy; the same adapter over twelve actions returned ten bracketed.

The graph was the visible casualty. The real one is older: `if p.id == post_id`
appears in `react()` in **all twelve adapters**, so reactions never found their
post, `upvotes`/`likes` never incremented, and `_hot_score` ranked every feed by
recency alone — on every run ever made, with nothing ever erroring. Phase 3 only
surfaced it because it is the first code that compares a model-supplied reference
against a stored id.

Fixed at source: `BasePlatformAdapter.post_ref` strips the decoration, applied in
`comment()` and `react()` across all twelve, and in the runner for the graph.
Tests are parameterised over the whole registry — the defect was identical in
twelve places, so proving a fix in one proves nothing.

### A threshold that was invented rather than measured

`viral_but_off_message` compared takeaway accuracy against an absolute **0.25**.
The first live run measured 0.07, 0.07 and 0.14, so it fired on two of three
variants. **A flag that fires on almost everything is noise wearing the clothes
of a finding** — the failure class this codebase keeps catching, shipped this
time by the code that was supposed to catch it.

Lexical overlap between a twelve-word paraphrase and a marketing sentence is
inherently low; there is no absolute level at which it means off-message. It is
now **relative**: a variant is off-message when it is understood materially worse
than its peers, which the matched swarm makes a legitimate comparison since all
of them faced the same audience. It needs three or more arenas, and it stays
silent when the variants sit together — the honest reading of "this metric did
not separate them", and the true reading of both live runs.

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
9. **`llm_usage` has no platform dimension**, so agent-action spend cannot be
   attributed to an adapter. This is what blocks a per-adapter `AGENT_ACTION`
   profile: the split is measured at the *run* level (748 tokens per action on
   Reddit + Twitter/X against 312 on Hacker News + LinkedIn) only because those
   two runs happened to be single-family. A mixed run tells you nothing. Fixing
   it is a column plus a `usage_context` argument — the harder half is the
   product question above it. **Deferred by decision 2026-08-04**; HANDOFF §8
   item 15.
10. **`issue_quote` cannot price a re-simulation.** It takes a bare shape and
    knows neither `reuse_agents` nor `inoculation_assets`, and `consume_quote`
    validates only agents/rounds/platforms/variants — so a parent-shaped quote
    validates cleanly against a child and charges for the wrong run. Closed for
    now by refusing a quote on any run with a parent (409); the real fix is
    carrying both fields on `run_quotes` and into the signature, which is a
    migration. Not urgent: no client issues a quote for a child today.
11. **The free grant has 20 credits of headroom.** A free run costs 1,180 of the
    1,200 granted. Not caused by the 2026-08-04 pass — the previous revision left
    24 — but any stage repricing at all consumes it, and the failure lands at
    signup. 1,400 costs $0.22 a trial and ends it. Needs a decision, because the
    grant is a published commercial number.
