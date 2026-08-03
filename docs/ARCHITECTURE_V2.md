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

## Known issues carried into Phase 1

Recorded here so they are not rediscovered:

1. **Sentiment is not measured.** `simulation_tasks.py:336-341` computes
   `sentiment_baseline × (1 + round/max_rounds × 1.5)` — a function of the
   archetype preset and round index, never of agent content. Phase 1 replaces it.
2. **Frontend charts are fabricated.** `ReportViewerPage.tsx:156-253` regex-scrapes
   one scalar from the report markdown and synthesizes the timeline, per-platform
   sentiment, persona metrics, and risk matrix with `Math.sin()` and
   `Math.random()`. Risk likelihood is `0.3 + Math.random() * 0.5`.
3. **A/B never runs variant B.** `run_simulation_ab` in `workers/simulation_tasks.py`
   calls `run_simulation` once. Real N-way testing is net-new in Phase 3.
4. **The live WebSocket feed is empty.** The active runner publishes nothing to
   Redis, and `SimulationRunPage` filters on `event_type === 'agent_action'` while
   the backend schema emits `agent_post`/`agent_comment`. The UI silently falls
   back to 5-second polling.
5. **No org switcher.** `core/auth.py::get_current_org` takes the user's *first*
   organization membership, so multi-org users are silently locked to one.
6. **Background jobs are not durable.** Every job is `asyncio.create_task` inside
   the API process, with no queue and no worker service in `render.yaml`.
   Restarting the backend kills in-flight simulations with no resume.
7. **Report depth does not scale down** — see the cost-model entry above.
8. **Model upgrade available, deliberately deferred.** Config pins
   `claude-opus-4-7`; Opus 5 is available at the same $5/$25 rate. The upgrade is
   not free: on Opus 5 thinking is *on by default*, and agent action calls set
   `max_tokens=160`, so thinking would consume the budget and truncate every
   action. Migrating requires setting `thinking` explicitly and re-tuning
   `max_tokens` — Phase 1 work, not a config edit.
