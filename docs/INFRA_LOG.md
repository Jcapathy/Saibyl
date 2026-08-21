# Infra Log

Standing rule (founder directive, 2026-08-16): every infrastructure action —
migration applied, deploy shipped, env var added, service changed, key
rotated — lands here, dated, with the ordering constraints that mattered.
Newest at the top. Production project: Supabase `txmvwuekkiedgxwovorp`
(Saibyl, us-west-2); Render services `saibyl-backend` / `saibyl-frontend`
deploying from GitHub master via CI (`deploy.yml`, gated on the test job
since 2026-08-16).

---

## 2026-08-21 — The last build push, and three sample products against production

**Deploys (master → Render, in order):** `2f79676` (three module UIs, the
family-office discovery pipeline, the price-publication fix, P0-9, P0-6,
P0-3), `7187dcb` (the four defects the sample run found), `e3231c7` (the
browser concurrency cap).

**The bank is no longer empty.** `scripts/curate_family_offices.py` run under
the service role against production: 25 queries, 117 sources, 14 names
harvested, **7 firms written** — Cox Enterprises, Ascend (Interplay), Dolby
Family Ventures, Black Cliffs Partners, East Seattle Partners, Mitchell Family
Office, Charles H. Hood Foundation. All seven verified, all carrying a
six-month `stale_after`, theses of 121–570 characters quoted from each firm's
own site. Rejection counts on that pass:
`inbound_unevidenced_defaulted: 5`, `unknown_evidence_field: 2`.

**Three sample products driven through every module** (org
`26d46806-eba9-409b-be7c-465320014c29`, renamed **Saibyl Samples** and topped
up for the exercise): Chartwell (medical SaaS), Ledgerline (fintech), Parry
(prompt-injection security). Rooms completed in 217/218/263s with 22/24/31
objections and reports of 39k/36k/35k characters. Answer packs 3/3, messaging
docs 3/3, capital shortlists 3/3 (3 matches of 7 firms considered each, with
refusals reported rather than dropped).

**What the run found**, all fixed the same day and re-verified: a malformed
model response destroying a paid artifact; credits kept for a capture that
never loaded; the shortlist recommending on funding stage alone; and a website
check able to hang at `capturing` indefinitely. Details in PRELAUNCH_BUGS.

**Prices verified live** after deploy: `messaging_doc` 1,500,
`outbound_sequence` 2,500, `capital_shortlist` 3,000 all now served by
`GET /billing/prices`, which had omitted all three.

**Still owed by the founder, confirmed live rather than assumed:**
`USPTO_ODP_API_KEY` and `USPTO_TSDR_API_KEY` are unset in the Render backend,
so IP Check returned 503 on all three sample products. The route guards before
creating or charging, so no credits were lost — but the module cannot run. Also
still owed: `ADMIN_ORGANIZATION_ID=231b7f17-d17c-4f6e-b530-f0196acd841b`, and
saibyl.com's DNS.

**Housekeeping:** two website-check rows orphaned by the pre-fix hang were
marked failed and their 5,250 credits (3 × 1,750) returned by
`grant_credits`, which is what the new refund path would now do
automatically.

---

## 2026-08-20 — The GTM module's first artifact shipped

- Migration **038_answer_packs** applied to production BEFORE the deploy and
  verified against `information_schema` (12 columns, RLS on, two indexes).
  Additive; nothing backfilled.
- Deploy verified by the 404→401 flip on `POST /api/answer-pack`, then by a
  **real build against a real run**: 10 measured objections → 9 matrix rows +
  2 battlecards, charged exactly 1,500 credits, six `[TODO]` markers in the
  output (the fact discipline holding — it refused to invent numbers the
  input did not contain). Battlecards were doing-nothing and build-in-house
  only, correct for a run whose material named no competitors.
- Frontend verified by reading the live pages: the panel renders on the
  Answers step stating "1,500 credits, charged once when it starts", and the
  three-card offer block is live (confirmed by grepping the served JS bundle
  for a string only the new build carries).
- `frontend/public/robots.txt` and `sitemap.xml` now ship — there were none.
  **Both name saibyl.com, which serves a GoDaddy parking page**; see
  `docs/SEO_AEO.md`. Pointing DNS at the Render frontend is owed and is the
  highest-value action for visibility.
- Credits granted to the Beta Test Org (+5,000) to fund the live verification
  of the paid path. Test org; noted so the balance is not read as revenue.

## 2026-08-17 (night) — Shipped to production, and the deploy gate was broken

- **Master pushed and LIVE.** `master` = `ab0dc98`. Verified by discriminator
  on the served CSS: `5268e9` (the new primary-gradient stop) present,
  `0A0F1C` (the dark ground) absent. Backend verified too — the deployed
  `/billing/credits` now returns `capped_run_credits`. Live screenshots of a
  free account read by eye: plan "Free", cap 25, sidebar "About 1 more run".
- **The CI gate had never once run.** Both workflows ran `uv sync --dev`,
  which installs a PEP 735 `[dependency-groups]` table; this project declares
  its dev tools under `[project.optional-dependencies]`, so uv installed none
  and the step died at `Failed to spawn: ruff` before any test. Proven, not
  reasoned: `uv export --extra dev` resolves ruff/pytest/black/pypdf, the old
  form resolves zero. Fixed to `--extra dev`.
- Then the suite ran and found the second gap: **CI had no Redis**, so seven
  export tests errored on a refused connection (1,325 passed). Both workflows
  now run a `redis:7-alpine` service, matching production. `test.yml` also
  ran the weaker `tsc --noEmit` instead of `npm run build` — the exact gap
  that shipped five errors past a "clean" frontend once before; it now runs
  the same four gates as the deploy workflow. **Tests workflow is green.**
- **⚠ OWED (founder): the Render deploy-hook secrets are empty.** The deploy
  job runs `curl -sS -X POST ""` and fails with "URL rejected: Malformed
  input" — `RENDER_DEPLOY_HOOK_BACKEND` / `..._FRONTEND` are not set in the
  repo. Production updates anyway because **Render auto-deploys from GitHub
  on its own**, which is why deploys have appeared to work while this job has
  never succeeded. Decide one: add the two secrets, or delete the deploy job
  and record that Render's own integration is the deploy path. As it stands
  the repo shows a red Deploy workflow on every push to a healthy production.

## 2026-08-17 — The app-shell light restyle: built, proven, push to master OWED

- Branch `v3-prd` pushed at `ac28cb4` — four commits: wave 0 (token
  foundation), dead-landing cleanup, wave 1 (60 files, every page), the
  critic pass. Frontend-only; no migrations; backend suite re-run anyway
  (1,318 passed, 4 skipped).
- **OWED (founder, one command): `git push origin v3-prd:master`** — the
  session's permission layer declined pushes to master, so the deploy step
  stops here despite the handoff's authorization. `origin/master`
  (`64bc513`) is this branch's direct base, so the push is a pure
  fast-forward; CI (gated) then Render deploys both services. The main
  checkout's local master will need a `git pull` afterwards.
- **Deploy discriminator, once pushed**: the served CSS bundle must
  contain `5268e9` (the new primary-gradient stop) and must NOT contain
  `0A0F1C` (the dark ground) — grep the CSS asset referenced by the live
  index.html, then screenshot the live /login and read it.
- Still owed in Render env (unchanged): `USPTO_ODP_API_KEY`,
  `USPTO_TSDR_API_KEY` (values in repo root `.env`),
  `ADMIN_ORGANIZATION_ID=231b7f17-d17c-4f6e-b530-f0196acd841b`.

## 2026-08-16 — Phase C shipped

- Migration **037_page_revisions** applied to production BEFORE the deploy.
- Live gate: revision `6205bfbc-…` on the piaa snapshot — 3 rounds, best 2,
  57→64 overall (credibility 42→58), HTML + screenshots stored, 7 fix
  prompts; room-run eligibility confirmed against a real parent run
  (creation free; starting the child run is the founder's credit action, by
  the machinery's own design). One row backfilled after the
  scores-shape fix (see CRITICS_LOG).
- Revisions priced 5,000 credits (PROVISIONAL — recalibrate from llm_usage).

## 2026-08-16 — Design augmentation shipped

- Migration **036_design_gallery** applied to production BEFORE the deploy
  (design_gallery table + website_snapshots reference columns).
- Live gate (third attempt; see CRITICS_LOG for the lessons the first two
  taught): reference-anchored check of piaa-shield.vercel.app vs
  tailwindcss.com — six dimensions, measured both-value gaps, DNA extracted
  (maturity 6, 7,998-char DESIGN.md), gallery row `928dfbb8-…` stored.
- **OWED (founder-only, Render backend env): `ADMIN_ORGANIZATION_ID` set to
  the Saido Labs org id `231b7f17-d17c-4f6e-b530-f0196acd841b`** to enable
  the design-gallery admin feed (`GET /api/admin/design-gallery`); empty
  keeps the routes hidden (404). Joins the still-owed USPTO keys.

## 2026-08-16 — Phase B ship

- Migration **035_website_checks** applied to production BEFORE the deploy
  (website_snapshots + material_kind CHECK widened for website kinds).
- Deploy `b7defff` verified serving via the 404→401 flip on
  `POST /api/website/check`. Docker image now builds chromium into
  `/ms-playwright` (several minutes longer per build).
- Live-gate artifacts in prod: snapshot `e544eda3-…` (piaa-shield.vercel.app,
  Saido Labs org).

## 2026-08-16 — Phase IP ship

- Migration **034_ip_clearance** applied BEFORE the deploy.
- Deploy `ab25c99` verified via 404→401 on `POST /api/clearance`.
- **OWED (founder-only step): `USPTO_ODP_API_KEY` + `USPTO_TSDR_API_KEY` in
  Render backend env** — until set, the clearance route 503s honestly.
  Values live in the repo root `.env` and `Provisional Patent MCP and
  Skill/`. Both keys probe-validated 2026-08-16 (ODP 200; TSDR 404-not-401).
- Live-gate rows in prod: clearance runs `596ab7f7-…` (STANDARD) + one QUICK,
  Saido Labs org.

## 2026-08-16 — Phase A ship + merge ops

- Order that mattered: migration 033 (idea_brief CHECK) applied BEFORE the
  deploy; master fast-forwarded and pushed (`6441204`); deploy verified by
  discriminators (new index title; rebuild route 401-not-404); THEN migration
  **032** (drop projects.asset_count + RPCs) applied — reversed order breaks
  every upload on the old code.
- Both stale customer-facing analysis artifacts rebuilt with the new
  composer (Tallyhook + Parry pre-launch) via local worker against prod.
- Tallyhook demo org's 35 stray test credits deducted to 0.
- `deploy.yml`: removed `continue-on-error` on tests, added `needs: test` —
  a red suite now blocks deploys; frontend CI runs the canonical
  `npm run build` + eslint + vitest.

## 2026-08-16 — Local environment

- The OneDrive-synced shared `.venv` (main checkout, junctioned into the
  worktree) fights `uv sync` with file locks on dist-info dirs; it was
  damaged and then repaired (quarantine-by-rename + fresh installs; suite
  green after). Canonical local env going forward:
  `UV_PROJECT_ENVIRONMENT=C:\Users\jcapa\.venvs\saibyl-v3` (off OneDrive,
  has playwright + chromium). Note: shared venv's pytest-asyncio drifted to
  1.4.0 vs lock 1.3.0 — functional; next clean sync reconciles.
