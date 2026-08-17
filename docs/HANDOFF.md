# Saibyl V2 — Session Handoff

**Saido Labs LLC** · Updated 2026-08-05 (early) — **Phases 0–3 complete and
deployed, plus the staged rail. Migrations 017–030 all applied. `master` and
`v2` are the same commit and both services are live and verified by content.
Still no live end-to-end run since the 2026-08-04 sweep — see §1.**

Read this first in a new session. It is written to be read cold, with no memory
of previous sessions.

> ### ▶ 2026-08-16 — V3 Phase A landed on branch `v3-prd` (not yet merged)
>
> The product re-aimed: **`docs/PRD_V3.md` supersedes PRD_V2** (signed off by
> the founder; the vision doc is `05_PRD/Saibyl-V3-Vision.html`). Phase A ships:
> crisis shelved behind `CRISIS_ENABLED` (default false, 404), the tiered
> idea-brief intake (five-question form → document → same pipeline; the
> synthesizer's 1,000-char floor exempts idea briefs or they'd be silently
> dropped), the report register rewritten for a founder reader, audit items
> 19 (GC half) / 39 (executed, −1,138 lines) / 40 (variant removed) closed,
> the three run-setup share bugs fixed, index.html metadata moved off the V1
> story, and deploy.yml now actually gated on the suite.
>
> **Ops — all complete as of 2026-08-16 (later the same day):**
> 1. Merged to master (`6441204`), deployed, and verified serving via
>    discriminators that only pass on the new build (new index title; the
>    rebuild route answering auth-required instead of 404).
> 2. Migration **033 applied before** the deploy; migration **032 applied
>    after** it was verified serving — the ordering both headers demand.
> 3. The Tallyhook demo org's 35 stray test credits were deducted (balance 0).
> 4. Both customer-facing artifacts (**Tallyhook pre-launch** and **Parry
>    pre-launch**) were rebuilt with the post-fix composer, so their frozen
>    vocabulary is gone. The internal Phase 1–3 verification artifacts were
>    left as-is on purpose — they document what those gates saw.
>
> The landing-page gauntlet redesign (prototype + two-round critique + 
> CC-PROMPT 10) lives in `Saibyl Management/Saibyl Redesign/` — implementation
> awaits the founder's approval of the direction.

> ### ▶ If you are the overnight build session, read `docs/AUTONOMOUS_BUILD.md` instead.
>
> It carries standing authority to build, commit, deploy and verify without
> asking, the staged-IA design the user approved, the short list of hard stops,
> and the verification gate. Come back to this file for §1a (agent identity),
> §2 (standing rules) and §2a (the failure classes this codebase produces) —
> those still apply and are not repeated there.

## Cold start in five minutes

You do **not** need to read the backend to be useful. Read this file's §0 and §1,
then `docs/V1_AUDIT.md`, and start working the top of the queue. Everything else
below is reference you read *when a task points you at it*, not upfront.

| | |
|---|---|
| Where the code is | `master` and `v2` are the **same commit** and both deployed. Work on either; keep them aligned. |
| What works | Phases 0–3: measurement layer, Founder lens + inoculation loop, Marketing lens + N-way matched swarms — all verified by live runs. **Static-green only, never run live**: one upload surface feeding ICP synthesis, multi-pack + org library, `services/gtm/` candidate discovery, and the staged rail (`/app/home`, `/app/products/:id/*`). |
| What to do next | **A live end-to-end run through the new rail** — nothing has been run live since 2026-08-04 and the rail has never had a real run pass through it. Then the tier migration (§0 item 2 — payment is impossible from the UI until it lands) and the Marketing-lens calibration (§0 item 4). `docs/V1_AUDIT.md`: 1–18 and 20–38 fixed, **19/25/39/40 open**. |
| How to verify | `cd backend && python -m pytest -q && ruff check app tests scripts` · `cd frontend && npm run build && npx eslint . --quiet && npx vitest run`. **1,012 backend tests** and **15 frontend tests** should pass. ⚠️ `npm run build`, never `tsc --noEmit` — they are different checks. |
| What a live run costs | ~$1.70 for a 3-variant gate run. `python scripts/live_run_marketing.py --dry-run` prices it without spending. A standard run costs **$3.01** to serve. |

**Three things that will save you a day each:**

1. **Disbelieve a perfect score.** Phase 2's worst defect reported every asset as
   effective from a comparison that had matched nothing. §1b.
2. **A comment is not evidence.** A re-simulation was under-charged because a
   plausible sentence said it should be cheaper — repeated in DECISIONS and
   pinned by a passing test. Three layers agreed; the ledger disagreed. §1c.
3. **Grep before you claim, query before you assert.** §2. Two confident claims
   about V1 were wrong within twenty minutes of each other on 2026-08-04, and
   both were one command away from being checked.
4. **Look at the running product.** The 2026-08-05 pass took the suite from 973
   to 1,012 tests and *none* of them caught any of the five defects that pass
   found. Three came from screenshotting the deployed page, one from reading an
   API response against seeded data, one from rasterising a chart. The best of
   them: the jargon test was green because `\bsimulation\b` does not match
   **"Simulations"**, and the plural is the form that ships.

**Read on demand, not upfront:**

- `docs/V1_AUDIT.md` — **the work queue.** Open findings, ranked, with what is
  verified and what is only reasoned.
- `docs/PRD_V2.md` — *what* V2 is. §1 is the market and integrity argument.
- `docs/DECISIONS_V2.md` — ***why***, with rejected alternatives and, per
  decision, what would justify reopening it. **Read before proposing any product
  design change** — it exists so you can disagree from an informed position.
- `docs/ARCHITECTURE_V2.md` — implementation decisions in commit order, plus the
  known-issues list at the bottom. Read the entry for the subsystem you are
  touching, not the whole file.
- `docs/PRICING_GUIDE.md` — Part 1 is the disclosure copy the Run Configurator
  implements; Part 2 is enterprise quoting. Generated by `scripts/quote.py`.
  ⚠ **Parts of it are stale** — audit item on the `MAX_RUNNABLE_VARIANTS = 1`
  claim, which is now 8.

Six files in `docs/`, nothing else to hunt for.

---

## 0. Start here — the work queue, in order

> ### ✅ Decided, and standing. Do not reopen these.
>
> **Tier names and prices — decided 2026-08-04 by the user.** The product ships
> **`founder` / `growth` / `agency` at $99 / $299 / $999.** Three vocabularies
> currently exist in the codebase and this one wins; the other two are migrated
> *to* it, not debated. `PRD_V2` §8 and `agent_pricing.TIER_CREDIT_GRANTS`
> already use these names. `stripe_service` (`starter`/`pro`/`enterprise`) and
> `SettingsPage.tsx` (`analyst`/`strategist`/`war_room`) do not, and until they
> do **payment is impossible from the UI** — V1_AUDIT item 25. This needs new
> Stripe Products and Price IDs, so it is real work, not a rename.
>
> **The cost model is closed — decided 2026-08-04.** The calibration thread is
> finished; the last pass moved the standard run $0.03. **Stop tuning token
> profiles.** Reopen only on a `margin_floor_breached` log from a real run, a
> stage changing its *unit of work*, or a prompt edit moving a stage by half.
>
> **The additive build was the right call — settled 2026-08-04.** Rewriting V2
> clean was raised and rejected on evidence: Phase 3's arena isolation needed
> *zero* adapter changes because V1's adapter design was already right, and the
> intent taxonomy the whole Marketing lens scores on was already there. The V1
> defects found are shallow — one-line fixes once located. The expensive part was
> *finding* them, and a rewrite relocates that cost rather than removing it.
> **The fix for the drip is the §2a sweep, not a rewrite.** `DECISIONS_V2` §11.
>
> Deferred by that decision: the per-adapter `AGENT_ACTION` profile and the free
> grant's headroom, both now in §8 rather than in this queue. Neither is wrong;
> both are pennies, and pennies is why they are not here.
>
> **What would reopen it**, and nothing less: `reconcile_run_cost` logging
> `margin_floor_breached` on a real run, a stage changing its *unit of work*
> rather than its size (that is what the re-simulation defect was — §1c), or a
> prompt edit large enough to move a stage by more than half. A future session
> that finds itself re-deriving a profile for accuracy's sake has misread this.

> ### ⚠️ State as of 2026-08-05, early — read before you touch anything
>
> **Everything is pushed, deployed and verified.** `master` and `v2` are the
> same commit. Migrations **017–030 are all applied**; there are no unapplied
> migrations and no local commits. The gate is green on both sides:
> ruff clean, **1,012 backend tests**, `npm run build` clean, eslint clean,
> **15 frontend tests**.
>
> **What is not verified: anything live.** No end-to-end run has happened since
> the 2026-08-04 sweep, and the staged rail has never had a real run pass
> through it. Under §2's own gate this is not "done" — it is "static-green and
> deployed". The $40 the user funded for verification is **entirely unspent**.
>
> **The staged rail is the headline change.** `/app/home` leads with products;
> `/app/products/:id/{audience,reactions,answers,buyers,messages}` are the five
> steps. It ships **additively** — every route that existed before still works
> and still returns the same rows, so backing it out is a navigation change
> rather than a revert. `/app/dashboard`, `/app/projects`, `/app/audiences`,
> `/app/prospects`, `/app/marketing`, `/app/simulations` and `/app/guide` are
> all still there, under "Also here" in the sidebar.
>
> **Two migrations applied 2026-08-05:**
>
> | | | |
> |---|---|---|
> | `025` | asset-count RPCs | A no-op on production, as its comment predicted. Verified before and after against `pg_proc`: the two single-argument functions were already there, and the dead two-argument overload is gone. |
> | `030` | `icp_profiles.confirmed_at` | Additive, nullable, nothing backfilled. Applied **before** the deploy, because the code writes it. |
>
> **A throwaway org holds seeded acceptance data.** Org
> `2cf27261-22d9-45b7-ab6d-316d255849b4` ("IA Acceptance 2026-08-05") carries
> four products covering every rail state — nothing uploaded, audience
> confirmed, one run with objections, and the full rail. It exists so the
> degraded states are URLs rather than something you have to produce by hand.
> **Delete it whenever you like**; nothing outside it refers to it.
>
> **Also true now:**
>
> - **Prediction markets (Kalshi/Polymarket) are gone**, by decision. The tables
>   remain in production; dropping them is a separate, unwritten migration.
> - **The buyer search no longer returns your own competitors.** `services/gtm/`
>   derives an exclusion set from the profile and `GET /gtm/estimate` shows what
>   was filtered and why. Still never run live.
> - **The landing page advertises only numbers `TIER_CAPS` can back.** SOC 2 is
>   gone from all three public pages — there is no audit and no report.
> - **Stripe still carries V1 prices** ($499/$1,499) while the page advertises
>   $99/$299/$999. Hard stop, untouched, and the highest-value thing to unblock.

Phases 0–3 are complete and verified live. Nothing is half-finished. **Start at
item 1 and work down.**

> **Queue status, 2026-08-05:** item 1 is **done** except audit items 19, 25,
> 39 and the newly-filed **40**. Item 2 (tiers) is **still blocked on Stripe
> Price IDs** and is now the highest-value thing a session can unblock, because
> payment remains impossible from the UI *and* the landing page now advertises
> prices Stripe cannot charge. Items 4, 5 and 6 are **untouched and still
> correct** — item 4, the Marketing lens calibration, is the one that gates
> selling that lens at all.
>
> **Audit item 40, filed 2026-08-05 and verified by reading, not observed
> live:** `report_agent.py:768` declares `_run_react_loop(..., variant="a")` and
> its only caller passes nothing, so the default stands on every report. The
> four artifact-backed branches are keyed on simulation and are correct; the
> three event-backed branches and the agent interviews are arena-filtered. On a
> matched-swarm run the report therefore presents whole-run statistics
> illustrated by quotes and examples drawn from one arena, **which reads as
> corroboration and is not**.

| # | Item | Type | Blocking |
|---|---|---|---|
| 1 | **Work down `docs/V1_AUDIT.md`** ← ~~**the work.**~~ **Largely done 2026-08-04** — 1–18, 20–38 fixed, one rejected on evidence. Remaining: **19** (fire-and-forget tasks, wants Phase 4's durable jobs), **25** (tiers, blocked on Stripe), **39** (no-caller subsystems, needs a per-subsystem decision). A systematic sweep found ~70 findings; 4 fixed, the rest ranked and open. Start at the top. Highest-value still open: **one dead key with six customer-visible readers** (`metadata.sentiment`, item 8) — the headline Saibyl Score returns 422 on every Phase 1+ run. Then **`frontend/src/types/index.ts` is imported by nothing** (item 26), which is the hole every frontend/backend mismatch drifted through. **Verify each item before fixing** — several are reasoned rather than observed. | Work | Everything |
| 2 | **Tier migration to `founder`/`growth`/`agency` at $99/$299/$999.** Decided; see the banner above. Needs new Stripe Products and Price IDs. **Until it lands, payment is impossible from the UI** — audit item 25 has the full scope. | Work | Revenue |
| 3 | **Phase 4** — Crisis lens, `clients` layer + org switcher, durable background jobs, calibration. One codebase now. Audit items 19–22 overlap durable jobs; do them together. | Phase | — |
| 4 | ⚠️ **The Marketing lens is measured but uncalibrated.** Two live runs put the *same* three messages in opposite orders — 42/42/35% then 23/15/8%, Proof-led last then first. The scoreboard correctly refused to name a winner both times, but that variance **is** the finding: at 26 agents this test cannot separate anything. Before the lens is sold, establish how many agents resolve a difference worth acting on. | Work | Selling the lens |
| 5 | **Re-check any contract quoted before 2026-08-03.** A deal signed against $2.26/run carries ~20% less margin than its band table claimed. A review, at renewal. | Review | Renewals |
| 6 | **Clean re-run of the inoculation loop** (~$6.44 COGS). The measured delta's *magnitude* is contaminated: 3 of 6 assets carried a fabricated statistic now blocked. Mechanism proven; effect size not citable. Do this when there is a reason to cite a delta, not before. | Decision | Citing any delta figure |

Everything in §8 is the older backlog. **Where §8 and `V1_AUDIT.md` overlap, the
audit is more current** — it was produced by a systematic sweep on 2026-08-04 and
several §8 entries understate what it found.

**If you do nothing else, read §1b and §1c.** Phase 2's worst defect reported a
perfect score. The 2026-08-04 defect was defended by a comment explaining why the
number was low. Both survived a green test suite; the second was *asserted* by
one. Neither was found by tuning a profile — which is the other half of the
argument for closing the cost model and building.

---

## 1. Current state

| | |
|---|---|
| Branch | **Merged.** `master` and `v2` are the same commit and both pushed. New work can go on either; keep them aligned or delete `v2`. |
| `master` | **Carries Phases 0–3 plus the staged rail, and is deployed.** Six commits landed 2026-08-05; both Render services confirmed serving the new code by content, not by asset hash. |
| Phase 0 | Complete — dead-code purge, route-collision fix, schema drift, cost model, usage ledger |
| Phase 1 | **Complete and verified end to end** |
| Phase 2 | Built and **verified end to end live**. Four defects found and fixed — see §1b. |
| Phase 3 | **Complete and verified live.** Two multi-variant runs: `398bf601` (found the graph defect) and `37530696` (confirmed the fix — 208/208 replies linked, 6/6 virality components). |
| Verification | ruff clean · **pytest 1,012 passed, 4 skipped** · **`npm run build` clean** · `eslint --quiet` clean · **vitest 15 passed** · both services live and verified by serving new content. ⚠️ **No live end-to-end run since the 2026-08-04 sweep** — static-green only, and the rail has never had a real run through it |
| Live runs | **Six.** Phase 1: `05f1d879`, `03de92ef`. Phase 2: `f980fe0d` (Founder lens, 30% adversarial) + `fa28d899` (its re-simulation). Phase 3: `398bf601` (3 variants — found the graph defect) + `37530696` (confirmed the fix, 208/208 replies linked). |
| Migrations | 017–**030, all applied.** 025 (asset-count RPCs) and 030 (`icp_profiles.confirmed_at`) went in 2026-08-05, both verified against `information_schema`/`pg_proc` afterwards. 030 preceded the deploy because the code writes the column. 019 went in at the 2026-08-04 merge in the only order that works: deploy first, index second. |
| Cost model | Re-derived 2026-08-05 after the subject-brief change. **Standard run COGS $3.01**; tier runs **6/19/66**; blended agency mix **$8.65**; a re-simulation **$3.34** and the full loop **$6.44**. **Free grant 1,500**, against a free run costing 1,273 — the 20-credit headroom problem is resolved. All tables regenerated from `scripts/quote.py`. §7. |
| Working tree | `.~lock.*` and `test_flow.py` are pre-existing untracked. Ignore them. |

Commit list: `git log --oneline master..v2` — deliberately not enumerated here,
because a hardcoded list goes stale on the next commit and a stale list is worse
than none. Phase 0 ends at `6c67509`; Phase 1 ends at `81d7aa9`; everything after
it is Phase 2.

### Migrations applied to production (`txmvwuekkiedgxwovorp`)

**017** — `llm_usage` ledger with RLS, 2 indexes, `simulation_llm_cost`.

**018** — the measurement layer. Eight measurement columns on
`simulation_events` with CHECK bounds and two partial indexes;
`simulation_analysis`, `canonical_objections`, `run_quotes` with org-isolation
RLS; the credit ledger on `organizations` plus `deduct_credits` /
`grant_credits`; `simulations.variants` and `simulations.depth`;
`simulation_measurement_coverage`. Verified after applying: 63 simulations and
10,236 events unchanged, 8 organizations seeded with credit balances.

**020** *(applied 2026-08-03)* — the Founder lens. `icp_profiles`;
`documents.material_kind`; `simulations.lens`, `founder_stage`,
`icp_profile_id`, `adversarial_share`; `simulation_agents.is_adversarial`,
`adversarial_role`.

**021** *(applied 2026-08-03)* — the inoculation loop. `inoculation_assets`,
`inoculation_results`; `simulations.parent_simulation_id`,
`inoculation_asset_ids`.

Both were additive only, and were verified after applying: 66 simulations /
2,512 agents / 10,805 events / 8 orgs / 23 documents unchanged, **zero rows
backfilled** — no historical run acquired a lens it was never configured with
and no historical agent became adversarial. Column types were checked against
`information_schema` (see the standing lesson below): `_uuid`, `float4`,
`bool NOT NULL DEFAULT false`, no drift. `get_advisors` reports no RLS lint on
any of the three new tables.

### 019 — applied at the merge, 2026-08-04

Agent-username uniqueness. **It was held back for three phases on purpose**, and
the interlock was real rather than caution: `master` had no generation-time dedup
(verified by `git show master:…/simulation_tasks.py` on the day), so creating the
unique index while `master` was deployed would have failed agent insertion on
every new simulation. Today's own 26-agent run logged three `agent_username_deduped`
events — a ~12% collision rate that becomes three insert failures, and a dead run,
without the dedup in front of it.

The order that matters, and the only order that works:

1. Merge `v2` → `master`
2. **Deploy** — this is what puts the dedup into production
3. *Then* apply 019

Executed in that order. Deploy confirmed live by probing `/api/variants/objectives`,
which returned **401 rather than 404** — the route exists, so the new code is
serving. Then applied: 377 rows renamed across 44 simulations, **0 duplicate
groups remaining**, 2,730 agents and 11,999 events intact, one pass as the
dry-run predicted.

**What it does not repair:** historical event attribution. There is no record of
which of nine identically-named agents produced a given event, so pre-fix runs
keep understated agent counts and confidence intervals wider than truth. **Do not
use any run created before 2026-08-04 as a calibration baseline for agent counts.**

**Standing lesson (from 017):** `IF NOT EXISTS` guards hide type drift. Before
adding a column that may already exist by hand, check
`information_schema.columns` for its actual type. On 017 this bit — production
had `persona_pack_ids` as `jsonb`, not `text[]`; the ALTER silently no-opped and
only the backfill failed.

---

## 1a. ⚠️ Read before writing any code that touches agents

**Agent identity is `agent_id`. `username` is a display handle and is not an
identity.** It is generated by an LLM and it collides.

This was the most consequential defect Phase 1 found, and it was structural
rather than incidental — the adapter boundary carried only a username, so agent
identity, per-agent memory and event attribution all routed through a string a
model made up. Asked for 100 handles it produced 45 distinct ones; nine agents
were called `mchen_itdir`. Those nine shared one memory and all their events
were attributed to one row. Because confidence intervals are computed across
agents, nine independent observations counted as one.

**Measured scope on production:** 248 colliding groups across **44 of 63
simulations**, 377 of 2,512 agent rows. Every simulation from April 2026 onward.
**This is a long-standing V1 defect, not a Phase 1 regression** — Phase 1 is
merely the first thing that depended on agent identity being real, and therefore
the first thing to notice. `master` has it today.

### The three layers that now prevent it

| Layer | Where | What it guarantees |
|---|---|---|
| 1. Dedupe at generation | `run_prepare_agents` | Usernames are unique when written. Re-checks after each suffix, so `mchen2` cannot collide with a literal `mchen2`. |
| 2. Identity flows as id | `base_adapter.py`, all 12 adapters, `run_simulation` | Adapters receive `agent_id`, key memory on it, and stamp it on every `SimulationEvent`. The runner attributes from `event.agent_id`. Collisions become cosmetic. |
| 3. Database constraint | migration `019` | A collision cannot be persisted even if a future code path forgets 1 and 2. |

Layer 3 exists because layers 1 and 2 are conventions enforced by code somebody
will eventually change. **If you add a new agent-creation path, a new adapter, or
an import, you get layer 3 for free and must not rely on the other two.**

### Migration 019 — applied 2026-08-04, layer 3 is live

All three layers are now in force. The constraint went in at the merge, after
the deploy that carries the dedup; the reasoning and the numbers are in §1
above. 377 rows renamed, 0 duplicate groups remaining.

Layer 3 is the one that matters going forward: layers 1 and 2 are conventions
enforced by code somebody will eventually change, and the index is the only
place the invariant holds regardless of who writes the next caller. **A new
agent-creation path gets it for free and must not rely on the other two.**

### What cannot be repaired

Renaming duplicates does not restore historical attribution — there is no record
of which of nine identically-named agents produced a given event. Every run
created before this fix has an understated agent count and confidence intervals
wider than truth. **Do not use any pre-fix run as a calibration baseline for
agent counts**, including the two Phase 1 live runs.

---

## 1b. Phase 2 has run live once, and it found four defects

Migrations **020** and **021** are applied. The full Founder-lens loop ran end to
end on 2026-08-03: parent `f980fe0d`, child `fa28d899`, 96 agents / 5 rounds /
2 platforms / 30% adversarial, ~$4.6 of measured COGS across both runs.

**All four defects were invisible to a green test suite.** That is now two phases
running. Detail in `ARCHITECTURE_V2.md`; the one that matters most:

> **Objection keys did not survive across runs.** Parent and child shared **zero**
> canonical objection keys, so every objection read as `died` or `emerged` and
> **all six assets scored effective**. The loop reported total success having
> matched nothing. Fixed by clustering the child against the parent's objections;
> keys carried 0 → 27 of 46 and `assets_effective` 6/6 → 3/6.

**The lesson worth carrying forward:** this bug's symptom was a perfect score.
Nobody investigates a perfect score, which is why `canonicalize_objections` now
logs at ERROR when a re-simulation carries no keys over. **If a future run
reports that every asset worked, disbelieve it before celebrating it.**

The other three, all fixed in `b6b99ab`:

- **The drafter fabricated evidence.** Asked to answer "there is no proof this
  works", it invented the proof — a 14-case dataset and a Spearman's ρ of 0.74 —
  and carried it into three assets. Neither exists. This is **publishable copy a
  founder could ship as their own claim**, which makes it worse than the
  competitor-naming risk the guardrails were built for. Phase 1's bug #5 one
  level over: the report was stopped from writing its own numbers, and the asset
  drafter never was.
- **Agent generation truncated again** — bug #3, third occurrence. The ICP
  context block made the prompt richer and the tail of the output distribution
  ran past `max_tokens`. The failure rate rises as the ICP gets *better*.
- **Canonicalization ran at exactly its ceiling** and parsed on luck. 728
  distinct phrasings against Phase 1's 601, because the adversarial cohort
  raises objections buyers do not.

### What the run proved works

Worth knowing so a future session does not re-litigate it:

- **The cohort split earns its place.** Headline −0.146; buyers −0.049 with a CI
  of −0.155 to **+0.057**, spanning zero; adversarial −0.359, CI −0.425 to
  −0.293. The intervals do not overlap. **The entire negative headline was the
  cohort the run was configured to include** — a founder reading −0.146 without
  the split reads a market verdict on their product.
- **The grounding guardrail holds live.** Two adversarial archetypes named Remesh
  *with* the competitor document cited; two argued unnamed. The drafted
  comparison page cited only what the material says and concluded "most teams
  should not replace real-audience research with Saibyl".
- **Adversarial allocation is accurate**: 30 of 96 agents = 31.2% against 30%
  configured. Weight-rebalancing survives rounding at the standard shape.
- **Agent identity holds on a new creation path**: 96 of 96 distinct usernames,
  480 events, 0 orphaned.
- **Pre-positioning reaches agents**: 20–28% of events per round referenced the
  published material, confirming `topic_block` delivery across adapters.
- Measurement 480/480 at 100% coverage on both runs, 0 batch failures.

**Follow-ups from this run are in §0.** They are decisions and calibration, not
unfinished code.

---

## 1c. The re-simulation was under-charged, and a comment is what hid it

The 2026-08-04 pass was assigned §0 items 3 and 4 — re-derive the two estimated
profiles and the one capped one from `llm_usage`. It did that (see
`ARCHITECTURE_V2.md`, the 2026-08-04 entry). The ledger then volunteered
something nobody had asked about, and it is the more important finding.

**A re-simulation carries its inoculation assets in every agent action prompt.**
Assets ride in `topic_block()`, which is rebuilt per call, so six assets at 700
characters each were re-sent across all 2,880 action prompts of the child run.
Nothing in the cost model charged for it.

The parent/child pair is the cleanest controlled comparison in the ledger — same
96 agents, same 5 rounds, same two adapters, six assets apart:

| | `f980fe0d` parent | `fa28d899` child |
|---|---:|---:|
| agent action, input tokens | 312 | **1,654** |
| canonicalization, output tokens | 8,000 *(capped)* | **13,955** |
| measured COGS | $2.31 | **$2.55** |
| quoted | $2.67 | **$2.38** |

Measured figures exclude the drafting pass, which is quoted separately, and count
one clustering call per run — the child's raw ledger total is $2.66 because it was
re-clustered after the key-carryover fix.

The child cost more than its parent and was quoted for less. 78.5% margin against
an 80% target — above the 70% floor, so `reconcile_run_cost` logged nothing. The
miss is small; what makes it worth a section is that the run the Founder lens is
sold on was the one run in the product never checked against its own bill.

The canonicalization line has its own cause: a re-simulation's clustering call
carries the parent's objections as priors, and the same run measured 3,162 output
tokens without that block against 13,955 with it. Both stages now have
re-simulation profiles.

### The transferable part

**The defect was defended by a comment.** `_stage_costs` explained that dropping
agent generation "makes the second run of the loop cheaper than the first — which
is exactly the right incentive for the step the product is sold on." True about
generation, false about the run, and satisfying enough that nobody checked. It
was repeated as fact in `DECISIONS §4` and **asserted by a passing test**
(`test_reuse_does_not_change_any_other_stage`).

That is three layers of documentation agreeing with each other and none of them
agreeing with the ledger. Phase 2's lesson was *disbelieve a perfect score*; this
one is narrower and worth having next to it:

> **A comment explaining why a number is favourable is a place to look, not a
> reason to stop looking.** When the pleasing story and the measurement disagree,
> the story is usually older.

### What is now true

- A re-simulation of the reference shape quotes at **$3.34**, above the $2.66 the
  measured one cost. The full loop — parent, drafting pass, re-simulation — is
  **$6.44**, or 2.14 standard runs. Quote the loop, not the run.

  > Both figures were **$3.13** and **$5.97** until the subject-brief change on
  > 2026-08-05, and this heading says "What is now true", so they were corrected
  > in place rather than dated. An acceptance reader found them still standing
  > here while §0 of the same file already quoted $6.44 — one document asserting
  > two current prices, which is the shape of the defect §1c exists to describe.
  >
  > The loop only reproduces at **96 agents**, not 100. That shape is in no
  > `SHAPES` entry; it comes from the two ledger runs the figure was measured on,
  > `f980fe0d` and `fa28d899`.
- `estimate_simulation_cost` takes `inoculation_assets`; the start endpoint
  derives it from `inoculation_asset_ids`.
- **A re-simulation cannot be started against a quote** (409). `issue_quote`
  knows neither flag and `consume_quote` checks only the shape, so a
  parent-shaped quote would validate against the child and charge the wrong
  price. §8 item 17 has the real fix.
- The measured pair is now a test floor: a quote for either run must not fall
  below what that run actually cost.

---

## 2. Standing rules for this build

From the user directly. These persist across sessions.

- **Grep before you claim, query before you assert.** Stated after a session in
  which two confident claims about V1 were both wrong within twenty minutes:
  "nothing deployed reads these columns" (nine call sites) and "no row has ever
  used them" (two rows). Each was one `grep` and one `SELECT` away. **A statement
  about the codebase that has not been checked is a guess, and writing it into a
  doc or a migration comment turns a guess into a fact the next session
  inherits.** This is not a style preference — every V1 defect this build has hit
  was found by measurement and hidden by assumption.
- **Audit a subsystem before building on it, not after it bites.** V1 remnants
  interrupted the Phase 3 gate run twice. Every one of them — bracketed post
  references, a NOT NULL `created_by`, an RPC parameter named `sim_uuid` and
  called as `sim_id` — would have come out of one systematic sweep at the start
  of the phase for a fraction of what they cost discovered one at a time. **Run
  the sweep at the phase boundary.** The failure classes worth sweeping for are
  in §2a, because they are the ones this codebase actually produces.
- **Authorship is Saido Labs LLC.** Commit with
  `--author="Saido Labs LLC <info@saidolabs.com>"`. **No Claude or Claude Code
  attribution** — no `Co-Authored-By`, no "Generated with", no 🤖. The committer
  stays the user's own git identity.
- **Billing descriptor is `SAIDO LABS LLC`** — Stripe statement descriptor and
  receipt/invoice branding, during the tier migration.
- **Branch `v2`.** Production stays on `master`, untouched until the user
  approves the merge.
- **Autonomy: run continuously within a phase, stop at phase boundaries.** Do
  not stop every five files. At each boundary: run the full gate, push, report,
  wait.
- **Verification gate, every phase, before any push:** `pytest`, `ruff check app
  tests`, **`npm run build`** (frontend), `eslint . --quiet`, app boots, **and a
  live end-to-end run**.

  > ⚠️ **Gate the frontend with `npm run build`, never `tsc --noEmit`.** They are
  > not the same check. Render runs `tsc -b && vite build`, and `tsc -b` is
  > project-references build mode which rejects things `--noEmit` accepts.
  >
  > On 2026-08-04 the deploy exposed **five pre-existing `tsc -b` errors** the
  > documented gate had been stepping over. The frontend service had been
  > failing to build and Render was serving a **stale bundle**, while every
  > session reported a clean frontend and believed it had shipped. A gate that
  > does not run what production runs reports success for the wrong reason —
  > the same shape as the margin gate passing on an empty ledger, one layer out. Plus (a) no value rendered in the UI or a report lacks a
  corresponding field in `simulation_analysis`; (b) quoted price ≥ measured
  `llm_usage` cost × margin floor — `reconcile_run_cost` logs
  `margin_floor_breached` when it does not.
- **Logs are updated in the same commit as the work they describe** —
  `docs/ARCHITECTURE_V2.md` and `05_PRD/saibyl-prd/INFRA_LOG.md` (the latter is
  outside the git repo, at `Saibyl/05_PRD/…`, so it cannot be committed with the
  code — write it anyway).
- **Nothing is deleted without first grepping** for direct calls, type
  references, string literals, dynamic imports, re-exports, and tests.
- Shell is PowerShell-primary; the Bash tool is also available. `git log` and
  heredocs behave differently between them — `@'…'@` is PowerShell, `<<'EOF'` is
  bash. Mixing them corrupts commit messages.
- `gh` is authenticated as `Jcapathy` with `repo` scope.

---

## 2a. The sweep — failure classes this codebase actually produces

Run at each phase boundary, before building on a subsystem. Not a generic
checklist: every class below is here because it has already shipped a defect in
this repo, and the example is the real one.

| Class | The defect it produced | How to find it |
|---|---|---|
| **A model-supplied string used as a key or compared to stored data, unnormalised** | Adapters showed the feed as `[<id>]` and the model echoed the brackets, inconsistently. `if p.id == post_id` failed in all twelve adapters: reactions never landed, feed ranking silently degraded to recency-only, 193 of 193 reply links lost. **Months, no error.** | Grep every `re.match` / `.split()` / `startswith` on model output, and every model value used as a dict key, `==` operand, or DB identifier. `BasePlatformAdapter.post_ref` is the fix shape. |
| **A silently swallowed exception** | The class that hid every defect on this list. A failure that logs nothing is a failure nobody investigates. | `except Exception: pass`, `except: continue`, `or {}` masking an error, `.get()` chains over data that must exist. |
| **A number invented rather than measured** | `viral_but_off_message` compared takeaway accuracy to an absolute `0.25`; the live distribution was 0.07–0.14, so it fired on two of three variants. A flag that fires on everything is noise dressed as a finding. | Any threshold, cap or weight not traceable to a measurement. If a constant has no measured value in its comment, it is a guess. |
| **A comment or doc asserting something nobody checked** | `_stage_costs` explained that a re-simulation is cheaper than its parent. It is more expensive. The claim was repeated in DECISIONS and pinned by a passing test — three layers agreeing, none matching the ledger. | Read comments as claims. Where one states a fact about behaviour or cost, verify it against the ledger or the data. |
| **A parameter, column or field accepted but never used** | `run_generate_report(variant="a")` reached only a log line, which then announced `variant=a` on a three-arena run. `is_ab_test` branched between two identical functions. | Unused args; columns written but never read; a naive dead-code scan **plus** manual exclusion of framework-called route handlers. |
| **Two sources of truth for one value** | `isSupportedSchema` used `===` and a user-facing message hardcoded "version 1" while the constant had moved to 3. | Anything declared in both `backend/app/` and `frontend/src/`, or in both code and a migration. |
| **A constraint safe only after the code that satisfies it is serving** | Migration 019 would have failed agent insertion on every run had it landed before the deploy carrying the dedup. | Any migration adding a constraint. Order is merge → deploy → constrain, and the deploy must be *verified* live, not assumed. |

## 3. Where the product reasoning lives

Phase 1 is engineering; the product argument behind it was settled earlier and is
recorded, not remembered. If you need to know *why* something is the way it is:

| Question | Where |
|---|---|
| Why rebuild at all — market and integrity | `PRD_V2.md` §1 |
| Why three lenses over one workspace | `DECISIONS_V2.md` §2 |
| Why measurement before any feature | `DECISIONS_V2.md` §1 — *the load-bearing decision* |
| Why ICP synthesis instead of more packs | §3 |
| Why the inoculation loop must re-simulate | §4 |
| Why N-way, not a repaired A/B | §5 |
| Why intent metrics with virality on a separate axis | §6 |
| Why an adversarial/incumbent cohort, and its guardrails | §7 |
| Why five stage workflows | §8 |
| Why the free tier is scope-limited, never content-gated | §9 |
| Why calibration is the moat | §10 |
| Why additive build, not a rewrite | §11 |
| Why structured artifacts before narrative | §12 |
| Why per-stage pricing | §13 |
| Why Haiku for volume, Opus for judgment | §14 — **watch this in Phase 2** |
| Why regional pricing scales the grant | §15 |
| Why 99/299/999 and credits rather than caps | §15b |
| Why prices fell when the cost model was corrected | §15c |
| Why quote standard runs until Phase 3 | §15d |
| Deliberately unresolved questions | §17 |

**The V1 PRD** is at `05_PRD/saibyl-prd/` for historical reference only. Its
`TECH_STACK.md` describes CAMEL-AI and Zep Cloud, both removed in March 2026.
`05_PRD/saibyl-prd-v2/README.md` is just a pointer back to `docs/PRD_V2.md`.

**Banned across all Saido Labs work:** Celery (use native async), Zep Cloud,
CAMEL-AI OASIS.

---

## 4. What Phase 1 built

**The claim Phase 1 exists to make true:** every number rendered in the UI or
written into a report is measured from what agents actually said, and drills down
to the quotes that produced it.

### 4.1 The measurement pipeline

Order matters — each step depends on the one before.

| Step | File | What it does |
|---|---|---|
| 1. Measure | `services/intelligence/event_measurement.py` | Scores each event from its content on a batched Haiku classifier: `valence`, `stance`, `intensity`, `objections[]`, `intent`, `is_novel_claim`. ~25 events per call. |
| 2. Canonicalize | `services/intelligence/objection_canonicalizer.py` | Clusters raw objection phrasings on the main model; ranks by reach × intensity × cohort spread. |
| 3. Build | `services/intelligence/analysis_builder.py` | Writes the typed `simulation_analysis` artifact. |
| — schema | `services/intelligence/analysis_schema.py` | The artifact's shape. A field that is not here cannot be rendered. |
| — loader | `services/intelligence/analysis_data.py` | Shared run loader + `mean_interval()`, the clustering statistics. |
| 4. Orchestrate | `workers/analysis_tasks.py` | `run_analysis()` and `reconcile_run_cost()`. |

**Three rules encoded in that pipeline, each of which has already caught a bug:**

- **Confidence comes from agents, not events.** One agent posting ten times is
  one opinion repeated. `mean_interval()` averages per agent first, then takes
  the interval across agents. Event-weighting would shrink bands by ~√(events per
  agent) — manufacturing precision from verbosity.
- **Reactions are engagement, never sentiment.** A like has no text, so it is
  marked measured with a null valence and excluded from sentiment aggregates
  rather than assigned an invented number.
- **Gaps stay gaps.** A round with no measurable opinion is omitted, not
  interpolated. Groups whose intervals overlap are reported as unresolved, not
  ranked.

### 4.2 The frontend, rebuilt

`ReportViewerPage.tsx` and `ReportPrintPage.tsx` both previously regex-scraped
one scalar out of the report markdown and generated the timeline, per-platform
sentiment, persona metrics and risk matrix with `Math.sin()` and `Math.random()`
— risk likelihood was literally `0.3 + Math.random() * 0.5`. Both are rebuilt on
the artifact.

Eight components that existed only to render generated data were deleted after
grepping: `SentimentTimeline`, `PlatformBreakdown`, `PersonaAnalysis`,
`ThemeCloud`, `RiskMatrix`, `SampleResponses`, `ExecutiveSummary`, `SentimentBar`.
Replacements live in `frontend/src/components/analysis/`. Types are in
`frontend/src/lib/analysis.ts` — the single mirror of the backend schema.

An unknown `schema_version` renders **nothing** rather than the fields it
recognises. Partial rendering is how a chart quietly loses a series.

### 4.3 Pricing, credits and quotes

| Concern | File |
|---|---|
| Cost model, credits, tier caps | `services/billing/agent_pricing.py` |
| Signed single-use quotes | `services/billing/run_quote.py` |
| Per-call token ledger | `services/billing/usage_ledger.py` |
| Configurator UI | `frontend/src/components/RunConfigurator.tsx` |

**1 credit = $0.001 of COGS.** Credits, not agent-rounds, are the metered unit
(DECISIONS §15b) — a run varies 23× in cost across the tier caps, so agent-rounds
ration nothing. Conversion always rounds **up**.

Quotes are priced server-side, HMAC-signed, single-use, expire in 30 minutes, and
are checked against the simulation's stored shape at redemption. **Credits are
charged at start, not completion** — otherwise one balance funds ten concurrent
runs. `reconcile_run_cost` then compares the quote against measured `llm_usage`
after the report and charges any shortfall.

### 4.4 API surface added

- `GET /api/simulations/{id}/analysis` — the artifact
- `GET /api/simulations/{id}/objections` — canonical objections, ranked
- `GET /api/simulations/{id}/evidence?event_ids=…` — the drill-down
- `POST /api/billing/quote` — signed quote
- `POST /api/billing/estimate-cost` — unsigned, for live slider display
- `GET /api/billing/credits` — balance, grant, tier caps

---

## 5. The ten defects Phase 1's live runs found

*(Phase 2's four are in §1b. This section is Phase 1 history, kept because the
patterns recur — two of Phase 2's four were repeats of #3 and #5 below.)*

**None were visible to static verification. Four appeared only at the reference
scale.** This is the most transferable thing in this document: a 25-agent run is
not a proxy for a real one.

Detail and reasoning for each is in `ARCHITECTURE_V2.md`.

| # | Defect | Why it mattered |
|---|---|---|
| 1 | No adapter told its agents the subject — all twelve stored `prediction_goal`, none read it | The topic reached agents only via the persona bio, so the sim depended on the bio generator succeeding |
| 2 | Cold-start deadlock — empty round-1 feed, every agent picks NOTHING | Zero events across every round, **no error raised anywhere** |
| 3 | Agent generation truncated at `max_tokens=400` on Haiku | 20 of 25 profiles fell back to topic-less stubs, which made #1 fatal rather than merely degrading |
| 4 | Unguarded Redis publish inside `asyncio.gather` | Killed the entire report when Redis was unreachable |
| 5 | The report wrote its own numbers | Zero interval citations across 48,000 chars, inventing "~58% of all SMB objections on Reddit" |
| 6 | Objection canonicalization was not priced at all | 24% of measured spend invisible to the quote |
| 7 | Canonicalization collapsed at scale — output hit `max_tokens` exactly | **300 objections, 265 single-event.** The Founder lens ranks on this object |
| 8 | **Agent usernames collided** — 100 agents, 45 distinct handles. Structural: the adapter boundary carried only a username | Nine agents shared one memory and one identity; every confidence band drawn from half the real swarm. **44 of 63 historical sims affected. See §1a.** |
| 9 | Report ignored `simulations.depth` | Run quoted at 4 sections was written at 6 |
| 10 | Report spend never metered | The largest main-model stage missing from the ledger the margin gate reads |

**Bugs 1, 2 predate Phase 1** — moving generation to Haiku removed the accident
hiding them. **Bug 5 is the original defect one level up:** V1 generated numbers
in the frontend because the backend had none; the report generated them in prose
because the ReACT loop had none in context. Both fixed by making the measured
object impossible to route around.

**Permanent data consequence:** every run created before the identity fix has an
understated `n` and **cannot be repaired** — there is no record of which of nine
identically named agents produced a given event. Intervals are wider than truth,
which is the safe direction, but wrong. Do not cite any pre-fix run as a
calibration baseline for agent counts. Scope and the three-layer fix: **§1a**.

---

## 6. What the standard run proved

Simulation `03de92ef` — 100 agents / 5 rounds / 2 platforms, 497 events, 100%
measurement coverage, 0 failures, confidence `high`.

**The decisive test:** does valence vary between agents of the *same* archetype?
The drift formula could not do that by construction — every agent of an archetype
got an identical score in a given round. It passed on every archetype, spreads
0.6–1.2.

Headline −0.049 (95% CI −0.109 to +0.012, n=45 — understated, see bug 8), 23%
support / 37% oppose / 40% undecided. 601 distinct raw objection phrasings
clustered into 17 canonical objections, zero single-event, top one spanning 18
agents and 8 cohorts.

**Sanity-check this again next run:** the top objection by load-bearing weight
was "doesn't surface integration debt" (18 agents, 8 cohorts), outranking
alternatives with similar raw frequency. Cohort spread is what separated them.
That is the ranking rule working as designed, and it is the single most
product-critical piece of judgment in the artifact.

---

## 7. The cost model is measured

Recalibrated from `llm_usage` across both runs. Profiles are in
`agent_pricing.py` with their measured values and units documented inline.

Recalibration found **two errors in the model itself**, not just stale numbers:

- **Agent-action cost was multiplied by the platform count.** `agent_count` is
  the whole swarm and `run_prepare_agents` *splits* it across platforms — 100
  agents over 2 platforms is 50 on each. Measured 500 action calls against a
  predicted 1,000. **Consequence worth internalising: adding a platform is close
  to cost-neutral.** It spreads the same swarm thinner rather than buying more
  simulation. Platforms cannot be sold as volume.
- Only ~80% of actions were assumed to produce events. Measured 497 of 500.

Standard run COGS **$3.23 → $2.26**; blended agency mix **$11.77 → $6.88**.
Margins untouched, so tier run counts rose (Founder 6→8, Growth 20→26, Agency
69→88) and enterprise quotes fell ~40%. That was a deliberate decision to pass
the corrected cost base through rather than bank the margin — DECISIONS §15c.

### The 2026-08-03 recalibration, from the Founder-lens run

The aggregate estimate came in at 0.955x of measured, which looked fine and was
hiding two errors that cancelled.

- **The report writes six sections and was quoted for four.** It appends an
  executive summary and a conclusion, neither of which comes out of
  `report_section_count`. A third of the largest main-model stage in every run
  was never quoted. `REPORT_FIXED_SECTIONS = 2` closes it and `REPORT_SECTION`
  is recalibrated per *written* section — $0.8715 estimated against $0.8709
  measured.
- **Canonicalization was under-quoted**, and its measured output was capped by
  the old token ceiling, so the figure in the model is a floor rather than a
  measurement. Backlog §0 item 4.

**Two profiles were deliberately not recalibrated**, and a future session should
not "fix" them without reading this. `AGENT_ACTION` measured 312 input against a
profile of 750, and `AGENT_GENERATION` 1,459 against 1,900 — neither is a shifted
mean. Agent-action input is **platform-dependent**: Hacker News and LinkedIn
carry a compact `[id] title (points)` feed line, where the adapters Phase 1
calibrated on put post bodies in the feed. Calibrating down would under-quote
every Twitter and Reddit run to make Hacker News runs exact. Agent-generation
input is **document-dependent** — the prompt carries `doc_context[:2000]` and
that project's short Markdown files did not fill the slice a PDF deck would.

Net effect: standard run COGS **$2.26 → $2.71**, tier runs **8/26/88 → 7/22/73**.
The 2026-08-04 ledger pass took it to **$2.74** and **7/21/73**. The
subject-brief change later the same day redefined the reference run itself and
took it to **$3.01** and **6/19/66** — that is the base every table is now
regenerated at.

**Re-derive whenever prompts change.** Every prompt edit moves these:

```sql
SELECT stage, model,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY input_tokens)  AS med_in,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY output_tokens) AS med_out,
       count(*)
FROM llm_usage GROUP BY stage, model;
```

Units differ per stage: `agent_action` and `agent_generation` are per call,
`event_measurement` is per **event** (batched ~25 per call), `report` is per
**written section** — outline sections *plus* `REPORT_FIXED_SECTIONS`, at
several LLM calls each — canonicalization is once per run, and `icp_synthesis`
and `inoculation_draft` are once per invocation rather than per run.

To scope the query to one run, add `WHERE simulation_id = '…'`. The reference
runs are in §1: `03de92ef` for a Phase 1 standard run, `f980fe0d` for the
Founder-lens run these figures came from, and `fa28d899` for a re-simulation
(which pays no `agent_generation`).

### Enterprise quoting, as of now

**Quote the standard-run table** (`PRICING_GUIDE.md` §2.3) for every contract
starting before Phase 3, and write the variant entitlement in as a dated addition
using the clause in §2.6a. The blended table (§2.3b) assumes 45% multi-variant
runs and the engine runs one arena — quoting it today over-charges against what a
customer can execute. Reasoning and rejected alternatives: DECISIONS §15d. **The
sample contract language needs counsel review before use.**

> ✅ **Regenerated 2026-08-04 at $3.01/run COGS — the current base.** The
> reference run now carries a **subject brief**: its agents react to the
> customer's uploaded material rather than to a description of it, which costs
> one main-model distillation pass per run plus a surcharge on every action.
> Standard run $2.74 → **$3.01**, blended agency mix $7.46 → **$8.65**, tier run
> counts 7/21/73 → **6/19/66**, the full inoculation loop $5.97 → **$6.44**.
> This is a change to the *definition* of the reference, not a recalibration —
> the same shape with nothing to distil still costs $2.74, and
> `standard_run_credits()` is the only correct source for the reference, because
> the `STANDARD_RUN` shape tuple does not carry the brief. DECISIONS §15e.
>
> **The free grant moved 1,200 → 1,500 credits**, its third rise, for the third
> time because a grant must cover one free run. A free run at the tier cap now
> costs **1,273**; at 1,200 a founder uploading their deck would have hit "not
> enough credits" at signup. Headroom goes from 20 credits (1.7%) to **227
> (15%)**. The 20-credit warning below was correct and this is it landing.
>
> ✅ **Regenerated 2026-08-04 at $2.74/run COGS.** Standard run $2.71 → $2.74,
> blended agency mix $7.35 → $7.46, tier run counts 7/22/73 → **7/21/73**. Only
> Growth moves, and only because it sat at 21.9 runs. Driven by `EVENT_MEASUREMENT`,
> which had been calibrated on the lowest of four measured runs. The larger change
> in the same pass does not touch the standard run at all: a **re-simulation** goes
> $2.38 → $3.13. §1c.
>
> ✅ **Regenerated 2026-08-03 at $2.71/run COGS.** Every table in the guide, the
> PRD's tier and reference tables, and DECISIONS §15d now come from
> `scripts/quote.py` against the current model. Verified by re-running the tool
> and diffing.
>
> **The choice made:** hold prices, grants and the 80% margin; publish the lower
> run counts (8/26/88 → 7/22/73). DECISIONS §15c set the precedent of passing a
> corrected cost base straight through, and this is that precedent applied in the
> uncomfortable direction. The grants and the margin floor are the promises the
> pricing rests on; the run count is the derived figure, and it was always
> disclosed as approximate and shape-dependent.
>
> **The free grant moved 800 → 1,200 credits.** A 25-agent trial cost 1,176 at
> that revision and 1,180 at the ledger pass above, so 800 would have failed the
> one run the free tier promises — at signup. (It is 1,273 against a 1,500 grant
> as of the subject-brief change; see the current entry at the top.) That
> relationship is pinned by
> `test_the_free_grant_covers_one_free_run`, and the advertised paid run counts by
> `test_paid_tier_run_counts_are_whole_runs`, because this is the second time the
> grant has silently gone stale. 20 credits of headroom is not enough to stop a
> third, and the test is the guard that catches it before a customer does — §8
> item 18, deferred by decision.
>
> ⚠️ **Contracts signed before this date** were quoted off $2.26/run and carry
> ~20% less margin than their band table showed. Review at renewal.

---

**Every profile is now derived from the ledger.** `icp_synthesis` and
`inoculation_draft` were the last two estimates and were checked against one live
pass each on 2026-08-04. Both *outputs* landed on their schema-derived estimates
(4,487 against 4,500; 5,641 against 5,000, which moved to 5,700). Both *inputs*
are held at their ceilings, because the measured runs did not fill the material
budget — the same document-dependence that keeps `AGENT_GENERATION` high. One
pass is a check, not a calibration; re-derive when a project with substantial
uploads runs.

**A re-simulation is quoted with `reuse_agents=True` and `inoculation_assets=N`.**
It pays no `agent_generation` — its agents are copied and it provably makes zero
generation calls — and it pays a per-asset surcharge on **every action**, plus a
larger canonicalization profile because its clustering call carries the parent's
objections as priors. **It is the more expensive of the two runs, not the
cheaper.** §1c. Anything in an older document that says otherwise predates the
measurement.

---

## 8. Open items — the backlog

Full detail in `ARCHITECTURE_V2.md` → *Known issues carried into Phase 2*. The
Phase 2 follow-ups live in §0; this list predates them and is unchanged except
where noted.

**Blocking or high-consequence:**

1. ~~A/B never runs variant B.~~ **Resolved in Phase 3, 2026-08-04.**
   `MAX_RUNNABLE_VARIANTS` is **8**, the runner builds one adapter instance per
   `(platform, variant)`, and `run_simulation_ab` plus the whole V1 A/B
   subsystem was deleted in migration 024 and the commit alongside it. Verified
   by two live 3-variant runs. §9.5.
2. **Background jobs are not durable.** Every job is `asyncio.create_task` in the
   API process — no queue, no worker in `render.yaml`. Phase 1 made this slightly
   worse: measurement, analysis and the report now run inside the same task, so a
   restart late in a run loses the artifact too.
3. **No org switcher.** `core/auth.py::get_current_org` takes the user's *first*
   membership. Blocks the agency client layer.
4. **Stripe tiers are still V1.** `PLAN_PRICE_MAP` maps `starter`/`pro` to
   $149/$499 Price IDs. `TIER_CREDIT_GRANTS` and `TIER_CAPS` map both V1 and V2
   names so nothing breaks, but new Products, regional Price IDs and
   card-country gating on `organizations.pricing_region` are unbuilt.

4a. ~~Migration 019 is written but not applied~~ **Applied 2026-08-04 at the
   merge.** The unique index on `(simulation_id, username)` is live. §1a.

**Quality and correctness:**

5. **The classifier is unvalidated against human judgment.** Nothing checks that
   Haiku's valence agrees with a person's. Calibration (Phase 4) is the real
   answer; hand-scoring 50 events from a live run and correlating is the cheap
   interim check.
6. **Objection diversity looks healthy** (DECISIONS §14). Agent actions run on
   Haiku, and the concern was blandness. The Founder-lens run produced **728
   distinct objection phrasings from 480 events**, clustering into 46 canonical
   objections with only one single-event. That is not bland. Keep watching, but
   the model-tier worry has evidence against it now.
7. **The live WebSocket feed is empty.** The runner publishes nothing to Redis and
   `SimulationRunPage` filters on `event_type === 'agent_action'` while the
   backend emits `post`/`comment`/`react`. Falls back to 5s polling. Not
   addressed — measurement took priority. Confirmed again on the live run:
   `report_progress_publish_failed` fired repeatedly with Redis absent and the
   report completed anyway, which is Phase 1's bug #4 fix working.
8. **`MAX_DISTINCT_STRINGS = 800` is now close, not theoretical.** ⚠️ The
   Founder-lens run produced **728 distinct phrasings at 96 agents** — 91% of the
   cap. The adversarial cohort is why: incumbent-aligned agents raise objections
   buyers do not. A 150-agent run will exceed it and the tail will be dropped
   (loudly, but dropped). **Batched clustering has moved from "eventual fix" to
   the next thing that will bite.** Note `CLUSTER_MAX_TOKENS` was raised 8k → 16k
   for the same reason and is a separate ceiling.
9. **Opus 5 available at the same $5/$25 as the pinned Opus 4.7** — but on Opus 5
   thinking is on by default and agent actions set `max_tokens=160`, so thinking
   would consume the budget and truncate every action. Requires setting
   `thinking` explicitly and re-tuning. Less urgent now actions run on Haiku; the
   report stages would still benefit. Note `.env` currently pins
   `claude-opus-4-6`, not the `4-7` the older docs mention.
10. **10,236 historical events carry `metadata.sentiment`** from the removed drift
    formula. Nothing reads it, but it will read as real to anyone querying the
    table directly.
11. **`SECRET_KEY` is unset in the local `.env`.** Quote signing falls back to an
    empty key in development. Production/staging config validation already
    rejects keys under 32 characters, so this cannot weaken a live deployment —
    but set it locally before testing quotes. Still empty as of 2026-08-03; the
    live-run scripts set it in `os.environ` rather than editing the file.

**New from Phase 2's live run:**

12. **19 of 46 objection keys did not carry over** into the re-simulation. Some
    of those objections genuinely were not raised again; some may be the same
    objection the model declined to match. The `keys_carried_over` field in the
    `objections_canonicalized` log is the number to watch, and a low ratio means
    the delta is measuring less than it appears to.
13. **`_converted_agents` pairs agents across runs on username.** Sound only
    because `create_resimulation` copies agent rows verbatim. If that copy ever
    changes, the "agents who changed their mind" list silently becomes wrong
    rather than empty. It is illustrative only — every number in a delta comes
    from `canonical_objections` — but it reads as evidence.
14. **The fabricated-evidence detector is narrow by design.** `_evidence_claims`
    catches a number paired with evidential language that is absent from the
    uploaded material. It will miss a fabricated claim phrased without numbers
    ("independently audited", "used by major banks"). The prompt prohibition is
    the first line; this is a floor under it, not a filter.

**New from the 2026-08-04 ledger pass:**

15. **Per-adapter `AGENT_ACTION`, deferred 2026-08-04.** Measured at **748**
    input tokens per action on Reddit + Twitter/X against **312** on Hacker News
    + LinkedIn. Two things block it and neither is urgent: `llm_usage` has no
    platform dimension, so action spend is not attributable to an adapter (the
    748/312 split is legible only because those two runs each used one adapter
    family — a mixed run tells you nothing); and per-adapter pricing makes
    **platform choice change the price**, which cuts against "adding a platform
    is cost-neutral". The profile is held at the higher figure, so compact
    adapters are over-quoted, which is the safe direction. **Left as-is by
    decision, not by omission.**
16. **`AGENT_ACTION` output is one observation for the asset surcharge.** Input
    is corroborated by construction (`ASSET_BODY_IN_PROMPT` = 700 characters
    bounds it at ~205 tokens against 224 measured); output, +7 tokens per asset,
    is a single parent/child difference of +41 across six assets. Carried per
    asset rather than flat so it fails safe as the count grows, but it is the
    thinnest number in the model. Re-derive on the next loop.
17. **`issue_quote` cannot price a re-simulation.** It takes a bare shape and
    knows neither `reuse_agents` nor `inoculation_assets`; `consume_quote`
    validates only agents/rounds/platforms/variants, so a parent-shaped quote
    validates cleanly against a child. Closed for now by refusing a quote on any
    run with a parent (409). The real fix carries both fields on `run_quotes`
    and into the HMAC canonical string, which is a migration. Not urgent — no
    client issues a quote for a child today — but it is a **silent
    under-charge** if one ever does, which is the failure class this model
    exists to prevent.
18. ~~**The free grant has 20 credits of headroom.**~~ **Closed 2026-08-05.**
    The grant moved 1,200 → 1,500 in the same pass that repriced the standard
    run, against a free run that now costs 1,273 — 227 credits of headroom
    rather than 20. The symptom it was going to produce, a signup that cannot
    complete its one promised run, no longer has a path.
    `test_the_free_grant_covers_one_free_run` remains the guard and remains the
    right way to find out: act when it goes red, not before.

**Open product questions** (DECISIONS §17): which countries fall in which
regional tier; the blended agency run mix (55/30/13/2) is still an assumption;
whether the adversarial cohort share should be fixed or scale with market
maturity; report depth scaling needs a validated curve, not just a lower floor.

---

## 9. What Phase 2 built, and what is next

Built, and **verified end to end against production** — see §1b for what that
verification found and fixed.

### 9.1 The audience is derived, not picked

| Concern | File |
|---|---|
| The editable ICP object | `services/engine/personas/icp_schema.py` |
| Synthesis + compilation to a pack | `services/engine/personas/icp_synthesizer.py` |
| The five stages, as data | `services/engine/founder_stages.py` |
| API | `api/icp.py`, `GET /api/simulations/founder-stages` |

One main-model pass over the project's uploaded material proposes an ICP; the
founder corrects it. The profile and the `PersonaPack` it compiles to live in
**one row** so an edit and the pack the next run uses cannot drift apart, and
`get_pack` resolves the `icp_` prefix out of `icp_profiles` — nothing downstream
of `run_prepare_agents` learns that ICPs exist. The 16 built-in packs supply
psychometrics as priors; `ArchetypeContext` carries what they have nowhere to
put (incumbent tooling, switching cost, skepticism triggers) into the
agent-generation prompt, without which a synthesized ICP is a relabelled generic
pack.

**The adversarial guardrail is enforced in data at two layers**, and DECISIONS §7
forbids relaxing it to improve output. `documents.material_kind` records which
upload is competitor material (`NULL` reads as `own`, so an unlabelled document
can never license a name); the schema refuses a `competitor_name` with empty
`grounded_in`; and the builder strips the name from any archetype citing a
document outside that set. **The name is stripped, not the archetype** — an
unnamed category skeptic is what PRD §4 asks for when there is no competitor
material.

### 9.2 The headline says what it measured

`SCHEMA_VERSION` is **2**. The artifact gains `by_cohort` (buyers vs
incumbent-aligned) and `adversarial` (the disclosure sentence, composed once and
rendered verbatim by the viewer, print page, PDF, PPTX and JSON export). Per
objection it records `originated_adversarial` and `buyer_agent_count`, so
"competitor advocates start the narrative decline" is checkable rather than
asserted.

`SUPPORTED_SCHEMA_VERSION` in `frontend/src/lib/analysis.ts` must move in the
same commit as any future bump. The frontend refuses to render an unknown
version, so a bump without the mirror blanks every report in the product.

### 9.3 The inoculation loop

| Concern | File |
|---|---|
| Before/after shape and verdicts | `services/intelligence/inoculation_schema.py` |
| Draft, re-simulate, prove | `services/intelligence/inoculation.py` |
| API | `api/inoculation.py` |
| UI | `frontend/src/components/founder/InoculationWorkbench.tsx` |

A re-simulation is an ordinary simulation with a `parent_simulation_id`, so both
numbers come out of one builder. **Its agents are copied, never regenerated** —
regenerating produces different people, and the claim is that only the material
changed. Assets are **pre-positioned, not posted**: they ride in `topic_block()`
as material published alongside the subject, which one hook on
`BasePlatformAdapter` delivers to all twelve adapters.

**The verdict logic exists to be able to say no.** Reach is a share of agents
with an interval on the proportion; zero observed carries a 3/n upper bound, so
"nobody raised it in 40 agents" is a band up to 7.5% and an objection is called
dead only when the bands separate. `unresolved` is a verdict and does **not**
count toward `assets_effective`. Do not "improve" that — it is the whole product.

> ⚠️ **The load-bearing invariant: the two runs must share objection keys.**
> Clustering labels are generated per run, so the same objection gets a different
> name — and therefore a different key — the second time. `canonicalize_objections`
> takes the parent's objections as priors and the prompt instructs the model to
> reuse a key when a group is the same objection said again.
>
> Without this the comparison matches nothing and **reports that every asset
> worked**, which is exactly what happened on the first live run: 46 and 39
> objections, zero shared keys, 6/6 effective. Migration 021's comment claims the
> key is "stable and deterministic from the label" — the key is, the label is
> not, and that distinction is the entire defect.
>
> `keys_carried_over` in the `objections_canonicalized` log is the health metric.
> **A ratio below `MIN_CARRYOVER_RATIO` (0.30) fires an ERROR** — it was
> zero-only until 2026-08-04, which made the realistic "12 of 46 carried" case
> invisible. The event is `objection_keys_carried_over_too_few`. A low ratio
> means the delta measured less than it appears.

**Assets are dropped, not flagged, when they fabricate evidence.** The drafter
invented a validation statistic on the first live run and put it in three assets.
`_evidence_claims` refuses any asset pairing a number with evidential language
when that number is absent from the uploaded material — this is copy a founder
may publish as their own claim, so there is no partial version worth keeping.

---

## 9.5 What Phase 3 built — the Marketing lens

Built and static-green. **Not yet run live** — §0 item 1. Full detail in
`ARCHITECTURE_V2.md`, 2026-08-04 entry.

| Concern | File |
|---|---|
| The arenas | `services/engine/variants.py` |
| Arena execution + the event graph | `workers/simulation_tasks.py` |
| Scoreboard + Virality Potential Score | `services/intelligence/variant_scoreboard.py` |
| Artifact shape | `services/intelligence/analysis_schema.py` (`SCHEMA_VERSION` 3) |
| API | `api/variants.py` |
| UI | `frontend/src/components/analysis/VariantScoreboard.tsx`, `components/marketing/VariantSetup.tsx` |

**Arena isolation was already in the codebase.** `get_adapter()` returns a fresh
instance and an adapter owns its feed, posts and per-agent memory, so one
instance per `(platform, variant)` isolates the variants with **no change to any
of the twelve adapters**. The swarm is shared by handing the same agent rows, by
id, to every arena — which is why generation cost does not scale with variants.

> ⚠️ **If adapters ever become singletons or acquire class-level state, matched
> swarms break silently.** Every arena would read one feed, every variant would
> be scored on a conversation they were all in together, and every number would
> still compute. `test_each_arena_gets_its_own_adapter_instance` is the guard.

**The event graph is written now.** Adapters always emitted `target_id`; the
runner always dropped it. It is resolved in a second pass at write time, keyed on
`(platform, variant, adapter_id)` — every arena mints its own `post_1`, so a
global map would attach one variant's reply to another's post.

> ⚠️ **Cascade is branching, not depth.** `BasePlatformAdapter.comment()` takes a
> *post id* across all twelve adapters — there is no reply-to-reply, so the graph
> is structurally two levels. The metric is named `cascade_branching` for that
> reason. Do not rename it to depth without changing the adapter contract.

**The scoreboard's value is its refusals**, and all three are the kind a future
session will be tempted to remove:

- `winner_variant_key` is **None whenever the top two intervals overlap**. A
  marketer acts on the top row, so an ordering drawn from overlapping bands
  launders sampling noise into a spend decision. Same rule as the inoculation
  loop's `unresolved`.
- **Unmeasurable virality components are None, not zero**, and are dropped from
  the weighting with the rest renormalised. Zero would penalise a variant for a
  gap in the instrumentation.
- **A silent arena keeps its row.** A variant nobody engaged with is a finding.

The report writer is handed the same prohibition in words: when the server named
no winner, the writer must not name one. **That is Phase 1's bug #5 in
Marketing-lens form** — not inventing a number, inventing a conclusion the
numbers do not carry.

### 9.6 Next

| Phase | Scope |
|---|---|
| **4** | Crisis lens migration, `clients` layer + org switcher, durable background jobs, calibration loop, V2 README. **The merge and migration 019 landed 2026-08-04**, so Phase 4 begins on a single codebase — and the legacy `is_ab_test` / `variant_a_config` / `variant_b_config` / `winner_variant` columns can now be dropped, since nothing deployed reads them. |

**Before starting Phase 4:** the Crisis lens wants propagation velocity, which is
what the event graph added in Phase 3 now makes measurable — but it will also
want real cascade *depth*, and that needs `BasePlatformAdapter.comment()` to
accept a comment id. That is a twelve-adapter change and it is the natural moment
to make it.
