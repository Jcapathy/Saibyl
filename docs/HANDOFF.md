# Saibyl V2 — Session Handoff

**Saido Labs LLC** · Updated 2026-08-02 (end of Phase 0)

Read this first in a new session. It is the current state, the standing rules,
and the next phase's scope. Update it at every phase boundary.

**Read in this order:**

1. This file — state, rules, next phase.
2. `docs/PRD_V2.md` — *what* V2 is.
3. `docs/DECISIONS_V2.md` — ***why***, with the alternatives that were rejected
   and, for each decision, what would justify reopening it. **Read this before
   proposing any change to the product design.** It exists so you can disagree
   from an informed position rather than either following the spec blindly or
   overturning a considered decision whose reasoning wasn't recorded.
4. `docs/ARCHITECTURE_V2.md` — implementation decisions and the known-issues
   list at the bottom, which is Phase 1's real backlog.

---

## 1. Current state

| | |
|---|---|
| Branch | `v2`, pushed to `origin/v2`, in sync |
| `master` | Untouched, still deployed to Render. **Do not merge without approval.** |
| Phase 0 | Complete — 4 commits, `6c67509`…`ef1e86e` |
| Verification | ruff clean · pytest 43 passed · `tsc --noEmit` clean · `eslint --quiet` clean · `vite build` OK · 79 routes, no duplicate registrations |
| Working tree | Clean (`.~lock.*` and `test_flow.py` are pre-existing untracked, ignore them) |

### Migration 017 — applied ✅

Applied to production (`txmvwuekkiedgxwovorp`) on 2026-08-02 and verified:
`llm_usage` created with RLS + org-isolation policy, 2 explicit indexes,
`simulation_llm_cost` callable. 63 simulations and 8 organizations unchanged;
the backfill touched 0 rows.

Applying it surfaced a type mismatch worth remembering: `persona_pack_ids` is
**`jsonb`** in production, not `text[]`. `ADD COLUMN IF NOT EXISTS` made the
ALTER a silent no-op, so only the backfill failed. The migration file now
matches production. The sibling `platforms` column *is* `text[]` — this table
genuinely mixes both conventions, so don't "normalize" it without a data
migration.

**Standing lesson:** `IF NOT EXISTS` guards hide type drift. When adding a
column that may already exist by hand, check `information_schema.columns` for
its actual type first.

---

## 2. Standing rules for this build

These came from the user directly and persist across sessions.

- **Authorship is Saido Labs LLC.** Commit with
  `--author="Saido Labs LLC <info@saidolabs.com>"`. **No Claude or Claude Code
  attribution** — no `Co-Authored-By`, no "Generated with", no 🤖. Committer
  stays the user's own git identity.
- **Billing descriptor is `SAIDO LABS LLC`** — set Stripe's statement descriptor
  and match it in receipt/invoice branding during Phase 1 billing work.
- **Branch `v2`.** Production stays on `master` and untouched until the user
  approves the merge.
- **Autonomy: run continuously within a phase, stop at phase boundaries.**
  Do not stop every 5 files. At each boundary: run the full verification gate,
  push, report, and wait.
- **Verification gate, every phase, before any push:** `pytest`, `ruff check app
  tests`, `tsc --noEmit`, `eslint . --quiet`, app boots, a live end-to-end run.
  From Phase 1 on, add: (a) no value rendered in the UI or a report lacks a
  corresponding field in `simulation_analysis`; (b) quoted price ≥ measured
  `llm_usage` cost × margin floor.
- **Logs are updated in the same commit as the work they describe** —
  `docs/ARCHITECTURE_V2.md` and `05_PRD/saibyl-prd/INFRA_LOG.md`. Not
  retroactively.
- **Nothing is deleted without first grepping** for direct calls, type
  references, string literals, dynamic imports, re-exports, and tests.
- Shell is PowerShell-primary; the Bash tool is also available. Note `git log`
  and heredocs behave differently between them — `@'…'@` is PowerShell, `<<'EOF'`
  is bash. Mixing them corrupts commit messages.
- `gh` is authenticated as `Jcapathy` with `repo` scope.

---

## 3. What Phase 1 is

**Goal: make every number real.** Nothing else in V2 is trustworthy until this
lands. Full spec in `docs/PRD_V2.md` §3 and §8.

### 3.1 Kill the formulaic sentiment

`backend/app/workers/simulation_tasks.py:336-341` computes

```python
drift_factor = 1.0 + (round_num / max_rounds) * 1.5
sentiment = clamp(agent.profile.sentiment_baseline * drift_factor, -1, 1)
```

— a function of the archetype preset and round index that never reads what the
agent said. Replace with a batched Haiku classifier scoring each event from its
actual content: `valence` (−1..1), `stance` (support/oppose/undecided/off-topic),
`intensity` (0..1), `objections[]`, `intent`, `is_novel_claim`. Batch ~25 events
per call.

### 3.2 Objection canonicalization

Second pass clustering raw objections across the run into canonical objections
with a stable ID, label, verbatim quotes, originating cohort, first-round-seen,
and propagation curve. This is the object the whole Founder lens is built on, so
get the schema right here rather than in Phase 2.

### 3.3 The `simulation_analysis` artifact

New table + typed schema. Sentiment timeline **with confidence bands derived
from actual agent count**, per-platform and per-archetype breakdowns, canonical
objections, flashpoints, propagation graph, `quality` block. Every finding
carries `event_ids[]` for drill-down.

**Rule: every number in the UI or a report must come from this artifact.**

### 3.4 Delete the fabricated frontend

`frontend/src/pages/ReportViewerPage.tsx:156-253` regex-scrapes one scalar from
the report markdown and then *generates* the sentiment timeline, per-platform
sentiment, persona metrics, and sample-response sentiments with `Math.sin()` and
`Math.random()`. Risk likelihood is literally `0.3 + Math.random() * 0.5`
(lines 239-253). `ReportPrintPage.tsx` has its own copy of the same scraping
logic — both go. Rebuild against `simulation_analysis` with evidence drill-down.

### 3.5 Switch agent actions to Haiku

Adapters call `llm_complete`, which resolves to `settings.llm_model` (Opus).
Agent actions are the highest-volume, lowest-judgment stage — ~5× cheaper on
Haiku and the whole reason N-way swarms are affordable. Keep Opus for ICP
synthesis, canonicalization, variant scoring rationale, and report writing.

### 3.6 Run Configurator + signed quote

Sliders for agents/rounds/variants, platform multi-select, depth preset. Live
readout: agent-rounds → estimated cost → credits → price → runtime. Tier caps
clamp the maxima. Server-side signed quote so the client can't tamper with
price. Replaces the fake estimator at `NewSimulationPage.tsx:52`
(`agents*rounds*platforms/200`, shows no cost at all). Wire
`deduct_agent_credits` on completion — it exists and has never been called.

Billing decisions already made: **Founder tier is $99/mo (US anchor)**;
statement descriptor is `SAIDO LABS LLC`; regional tiers discount the price
*and* scale the grant proportionally, gated on the card's billing country, never
IP. Bands and margin math are in `docs/PRD_V2.md` §8 and `DECISIONS_V2.md` §15.

### 3.7 Sovereign palette

Obsidian `#0A0F1C` · Graphite `#111827` · Sovereign Gold `#C9A227` · Signal Blue
`#2563EB` · Insight Violet `#8B5CF6`. Replaces Indigo/Neon Cyan.

### 3.8 Fix report depth scaling *(cost bug found in Phase 0)*

`report_agent.py:606` — `min(7, max(4, event_count // 30 + 2))`. The floor of 4
means a 25-agent free-trial run still generates 6 Opus-written sections: $1.07
of that run's $1.27 total. Scale depth with run size; ~2 sections for a 25-agent
run drops the free run to roughly $0.35.

---

## 4. Do not rediscover these

Full detail in `docs/ARCHITECTURE_V2.md` → *Known issues carried into Phase 1*.

1. A/B never runs variant B — `run_simulation_ab` calls `run_simulation` once.
   Real N-way is net-new in Phase 3, not a repair.
2. The live WebSocket feed receives nothing. The active runner publishes no
   Redis events, and `SimulationRunPage` filters on `event_type ===
   'agent_action'` while the backend emits `agent_post`/`agent_comment`. The UI
   silently falls back to 5s polling. The streaming contract is being redefined
   in Phase 1 anyway.
3. No org switcher — `core/auth.py::get_current_org` takes the user's *first*
   membership. Blocks the agency client layer (Phase 4).
4. Background jobs are not durable: `asyncio.create_task` in-process, no queue,
   no worker in `render.yaml`. Restarting the backend kills in-flight runs.
5. **Opus 5 is available at the same $5/$25 as the pinned Opus 4.7 — but the
   upgrade is not a config edit.** On Opus 5 thinking is *on by default*, and
   agent action calls set `max_tokens=160`; thinking would consume the budget and
   truncate every action. Requires setting `thinking` explicitly and re-tuning
   `max_tokens`.

---

## 5. Phases after this one

| Phase | Scope |
|---|---|
| **2** | Founder lens — ICP synthesis, adversarial cohort, 5 stage workflows, inoculation loop (detect → draft → **re-simulate** → prove delta). First sellable milestone. |
| **3** | Marketing lens — N-way matched swarms (seed-locked shared audience), per-objective intent metrics, Virality Potential Score. |
| **4** | Crisis lens migration, `clients` layer + org switcher, calibration loop, V2 README on the repo, merge to `master` on approval. |
