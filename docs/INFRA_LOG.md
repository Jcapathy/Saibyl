# Infra Log

Standing rule (founder directive, 2026-08-16): every infrastructure action —
migration applied, deploy shipped, env var added, service changed, key
rotated — lands here, dated, with the ordering constraints that mattered.
Newest at the top. Production project: Supabase `txmvwuekkiedgxwovorp`
(Saibyl, us-west-2); Render services `saibyl-backend` / `saibyl-frontend`.

**How a deploy happens, so nobody re-derives it (corrected 2026-08-22).** Push
to GitHub `master`. **Render's own GitHub integration watches the branch and
deploys it** — that is the whole mechanism and it is what it is meant to be.
Nothing here calls Render, holds a Render credential, or needs one.

## 2026-08-28 — The follow-up cron, and what it needs before it can send

Migration `followup_sends_idempotency` (repo: `045_followup_sends.sql`), a new
`saibyl-followups` cron service in `render.yaml`, and Saibyl's first
mail-sending code (`services/email/sender.py`, Resend over `httpx` — no SDK,
since the send endpoint is one POST and a dependency added for one call is a
dependency to patch forever).

**Daily at 15:00 UTC, not fortnightly.** The due check is a window (7 days at
the two-week ask, 14 at the four-week), so a day lost to a deploy or an outage
is caught the next morning. An exact fortnightly schedule would skip that
founder permanently and nobody would ever know.

**It runs the same Docker image as the API**, not Render's native Python
runtime. `uv sync` on a different base would build a second, subtly different
environment, and a mail job that only fails in production at 15:00 unattended is
the worst place to find a dependency skew. The Dockerfile already copies
`scripts/` and puts `.venv/bin` on PATH, so nothing about the image changed.

**Verified before shipping** by running the entrypoint against production with
`--dry-run`: `1 due, 0 sent`. That exercises the window query, the owner-email
lookup and the entrypoint without sending anything.

### What it needs from a human before a single email goes out

A **Blueprint sync in Render** — pushing `render.yaml` to master does not create
a cron service by itself — and then, on the `saibyl-followups` service:

| Var | Note |
|---|---|
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY`, `DATABASE_URL` | **A cron service inherits nothing from the web service.** Every one must be set again here. |
| `RESEND_API_KEY` | Already exists on the backend; needs copying to this service. |
| `EMAIL_FROM` | e.g. `Saibyl <hello@saibyl.com>`. |
| `EMAIL_REPLY_TO` | Where a founder's reply lands. The follow-up is a question, so somebody has to be able to answer it. |

And the one that is not an environment variable: **a verified sending domain in
Resend.** Until `saibyl.com` is verified there (DNS records Resend supplies),
Resend accepts only `onboarding@resend.dev` and only to the account owner's own
address — which looks exactly like working software until the first real
founder. `sender.py` surfaces Resend's own rejection text verbatim for this
reason, and the failure lands on the `followup_sends` row rather than in a log
nobody reads.

Until all of that is done the job runs green and sends nothing, by design:
`email_is_configured()` is false, the report says so, and no rows are claimed.

## 2026-08-28 — `objection_outcomes`, and the number that is not on the site yet

Migration `objection_outcomes_close_the_loop` on `txmvwuekkiedgxwovorp`,
recorded in the repo as `044_objection_outcomes.sql`.

One row per predicted objection per run, holding a founder's verdict on whether
a real buyer raised it. `occurred` is nullable and NULL means asked-not-answered;
`outcomes.py` filters `IS NOT NULL` before counting, so an ignored follow-up
email cannot show up as a failed prediction. RLS is the same `*_org_isolation`
policy every other table uses, which is now the thirty-seventh caller of
`user_organization_ids()` — see migration 043 for why that function keeps its
EXECUTE grant.

**Nothing goes on the landing page yet, deliberately.** `MIN_ANSWERS_TO_REPORT`
is 30, and `accuracy_for()` returns `None` below it rather than a rate. The
table is empty today, so the honest public claim is still none. When it has
thirty answered predictions, the sentence it produces —
*"N of M predicted objections were raised by real buyers"* — is the one that
answers the credibility critical both evaluators put first.

**Operational note for whoever wires the asking:** the follow-up has to reach
founders 4-8 weeks after a run, which is a scheduled job that does not exist
yet. Until it does, rows only arrive if somebody asks by hand.

## 2026-08-27 — Saibyl takes its first real payment

**Live Stripe is on.** `saibyl-backend` now carries a live `STRIPE_SECRET_KEY`
and the live `STRIPE_WEBHOOK_SECRET`, both from **Saido Labs LLC ·
live** (`acct_1T6Yx0RShwt3K1Q6`) — a different account from the sandbox used to
rehearse (`acct_1TLcl9IqFuuRAGd4`, "Saibyl · sandbox"). The three dead
`STRIPE_PRICE_ID_*` vars were deleted from the dashboard at the same time.

Live webhook endpoint: `checkout.session.completed` →
`https://saibyl-backend.onrender.com/api/billing/webhook`. Account preflight
before going live: `charges_enabled`, `payouts_enabled` and `details_submitted`
all true, USD, bank account attached.

**Rehearsed in the sandbox first, deliberately.** `credit_topups` had never held
a single row, so the payment path was not "working in test, needs promoting" —
it had never once run end to end. A sandbox purchase on `4242…` proved the whole
chain before a real card touched it. That rehearsal is also what planted the
stale-customer bug below, and finding it with a test card rather than a
customer's is the entire argument for doing it that way.

**Verified, both times, by the same three facts** — not by a green deploy:
the `credit_topups` row reaching `status = 'paid'` with `credited_at` stamped,
the `stripe_payment_intent` recorded so the charge is traceable, and the org's
`credits_balance` moving by exactly the quoted amount. Live run: `cs_live_…`,
$10 → 2,000 credits, balance 99,250 → 101,250.

**One manual repair, and its follow-up.** Two orgs held `stripe_customer_id`
values minted against the sandbox account; both were nulled so the next checkout
mints a live customer. That is no longer a manual repair — see the
`_checkout_recovering_stale_customer` fix and `CRITICS_LOG.md`.

**Still open:** the sandbox webhook endpoint `we_1U9J0mIqFuuRAGd4WYknzXQp` and
its signing secret should be rotated or deleted; the secret was printed into a
session transcript. It is sandbox-only and has no power over real money.

## 2026-08-27 — Security advisors taken from 19 to 4

Migration `pin_function_search_path_and_revoke_trigger_execute` on
`txmvwuekkiedgxwovorp`, plus one console toggle by the founder.

**What was done.**

- **Leaked Password Protection enabled** (founder, console). New passwords are
  now checked against HaveIBeenPwned. This matters most to the reset flow
  shipped the same day: before it, the 8-character floor in
  `api/auth.py` was the only thing between a reset and `password123`.
- **`search_path` pinned to `public, pg_temp` on all twelve flagged
  functions.** Clears lint 0011 everywhere.
- **`EXECUTE` on `handle_new_user()` revoked** from `PUBLIC`, `anon` and
  `authenticated`. It is a trigger function on `auth.users`
  (`on_auth_user_created`), returns `trigger`, and so could never actually be
  invoked through `/rest/v1/rpc` — the grant was noise, and is gone.

**What was deliberately NOT done, and must stay not-done.**

`REVOKE EXECUTE ON public.user_organization_ids()` **would take the product
down.** Thirty-six RLS policies call it — every `*_org_isolation` policy in the
schema — and a policy that calls a function requires the *querying* role to hold
EXECUTE. Revoking it from `authenticated` breaks tenant reads on every table at
once. The function is already safe: its body filters on `auth.uid()`, so `anon`
gets an empty array and a signed-in caller gets only their own organization ids.

Its two advisor warnings stay open on purpose. **They are not a to-do.**

The two `extension_in_public` warnings (`vector`, `pg_trgm`) also stay: moving
them risks every reference in the schema for no security gain.

**Verification.** Not "the migration applied" — that proves nothing about
whether the functions still work. All ten callable functions were invoked with
ids matching zero rows, which exercises table resolution without touching data;
none raised `relation does not exist`, and a follow-up count confirmed no row
was modified. Advisor re-run: 19 → 4.

## 2026-08-27 — Password recovery needs one Supabase console setting

**Console action, not a code change, and the flow is silently wrong without
it.** `POST /auth/forgot-password` asks GoTrue to send the recovery mail with
`redirect_to = {FRONTEND_URL}/reset-password`. GoTrue honours `redirect_to`
**only for URLs on the project's Redirect URL allow-list** — anything else is
dropped without an error and the link falls back to SITE_URL. So the mail
arrives, the link works, and it lands somewhere that cannot finish the reset.

Required in Supabase → Authentication → URL Configuration for
`txmvwuekkiedgxwovorp`:

```
https://saibyl.com/reset-password
```

`FRONTEND_URL` is already `https://saibyl.com` in `render.yaml`, set there for
Stripe's return path, so nothing on Render changes. The SPA routes need nothing
either: the existing `/*` rewrite already serves `/forgot-password` and
`/reset-password`.

**How to tell it is wrong rather than assuming it is right:** request a reset
and read the link in the mail. It should carry
`redirect_to=https%3A%2F%2Fsaibyl.com%2Freset-password`. If it points anywhere
else, the allow-list entry is missing — a green deploy proves nothing here.

## 2026-08-25 — `npm run build` now prerenders the public pages, and Render routes them

**Two coupled changes, and neither works alone.**

`frontend/package.json`'s build gained a third step: `node scripts/prerender.mjs`
after `vite build`. It renders `/`, `/privacy` and `/terms` to static HTML and
writes `dist/<route>/index.html`. Render's build command is unchanged — it runs
`npm run build`, so it picks this up with no dashboard action.

`render.yaml` gained two explicit rewrites **before** the `/*` catch-all. Routes
are evaluated in order, and without them every request for `/privacy` would be
handed the empty SPA shell no matter what file exists. Whether Render would have
matched the real file first is not something worth relying on; stated
explicitly, it is correct either way.

**Why:** no major AI crawler executes JavaScript, so until now ChatGPT, Claude
and Perplexity fetched this site and received `<div id="root"></div>`.
`SEO_AEO.md` names this the single biggest AEO unlock. Measured after the
change: the landing page ships **2,082 extractable words** where it previously
had none, with the pricing figures and the new question-shaped FAQ answers all
present in the raw HTML.

**Ordering constraint that still stands:** this changes nothing until DNS moves.
`saibyl.com` still serves a GoDaddy parking page while every canonical and
`og:url` points at it, so the prerendered pages are being crawled at
`saibyl-frontend.onrender.com` under identity signals that point somewhere else.
The Search Console generative-AI toggle has to be set to *include* the same day.

**Build risk, assessed rather than assumed.** The script imports `vite`, which
is already required for `vite build` in the same command, so it cannot be
present for one and absent for the other. It fails the build loudly rather than
warning: a prerender that quietly skips deploys green with the files missing and
nobody finds out until someone asks why the site is not cited anywhere.

`frontend/src/test/prerender.test.ts` fails if the two halves drift, in either
direction. Verified by removing a rewrite and watching it fail with the reason.

---

This header previously said deploys ran "from GitHub master via CI
(`deploy.yml`, gated on the test job)". That was **wrong**, and `deploy.yml`
was **deleted on 2026-08-22** (founder's call) rather than left to keep
saying it. What it contained: a `deploy` job posting to
`secrets.RENDER_DEPLOY_HOOK_BACKEND` / `_FRONTEND`, neither of which has ever
existed (`gh secret list` is empty), so it ran `curl -sS -X POST ""` and
failed with exit 3 on **every push in the workflow's entire history** while
Render deployed the commit correctly anyway — plus a `test` job that
duplicated `test.yml` in full.

**`.github/workflows/test.yml` is now the only workflow**, and it is a strict
superset of what was removed: identical gates (ruff, pytest, `npm run build`,
eslint, vitest, same Redis service), split into two parallel jobs, and it runs
on every push and pull request rather than master alone.

**Known and accepted: CI does not gate the deploy, and never did.** Render
ships whatever lands on `master` the moment it lands, pass or fail — the
deleted job's `needs: test` only ever gated a curl to an empty string. Treat
`master` as production. Verify a deploy against the service rather than a
checkmark: `GET /health` returns the live commit.

---

## 2026-08-22 — Deployed and verified against the service

`b7adc57` pushed to `master`; Render's GitHub integration deployed it.
Confirmed live rather than assumed:

```
GET https://saibyl-backend.onrender.com/health
{"status":"ok","commit":"b7adc57","environment":"production",
 "checks":{"database":"ok","redis":"ok","llm":"ok"}}
```

Frontend 200. The `Tests` workflow passed in 2m46s. The `Deploy to Render`
workflow failed, as it always did — and was deleted the same day; see the
corrected header above.

## 2026-08-22 — Two columns the founder-facing surfaces needed

**Migrations applied to `txmvwuekkiedgxwovorp` (production, direct):**

- `page_revisions_unsupported_claims` — `unsupported_claims jsonb`, nullable
  on purpose. `null` means the row predates the check; `[]` means the scan ran
  and found nothing. Only the second is a clean bill of health, and the bundle
  and the UI both need to tell them apart before promising one.
- `reports_error_message` — `error_message text`. `reports` was the only
  artifact table without it, which is why a failed report told a founder
  nothing at all. Measured before applying: **2 of 3 reports generated
  2026-08-22 failed, 3 of 3 on 2026-08-21**, every one with no reason
  recorded anywhere visible.

Both are additive and nullable, so they carry no ordering constraint against
the deploy — the columns can exist before the code that writes them, and old
rows stay readable.

**Verified against the live artifact, not reconstructed.** The delivered
Ledgerline revision (`9ccd1775-…`, 51,122 bytes) was downloaded from
`project-media` and run through the new detector: it reports SOC 2, ISO 27001,
PCI DSS, AES-256, TLS, Central Bank of Ireland and a money-transmitter licence,
plus the invented fee percentages. The scores on that row confirm the rest of
the account — 78 → 80 overall, credibility 82 → 82, design 82 → 78.

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

## 2026-08-22 — Standard plan, and the Website Gauntlet works

**`saibyl-backend` moved from `starter` (0.5 vCPU / 512 MB) to Standard
(1 vCPU / 2 GB).** Founder's action. Measured immediately after, against a
commit confirmed through `/health`:

- **stripe.com** — capture 11s, full check complete 136s, 12,084 chars, 79.
- **simplepractice.com** — capture 21s, full check complete 156s, 4,636
  chars, 67.

Neither had ever completed before, on any day, in the whole production table.

**The concurrency test that used to kill the box now passes.** Two heavy
captures started together: both completed (150s, 160s) while `/billing/credits`
was polled throughout — **48 calls, 0 failures**. On the old plan that
combination produced 502 on every endpoint. `WEBSITE_CAPTURE_CONCURRENCY`
default raised 1 → 2 to match the memory; still env-tunable, and it must come
back down if the plan ever does.

**What this settles about the diagnosis.** It took both halves and in this
order: the code fixes (synchronous storage off the event loop, bounded capture
steps, evidence before extras, a layout-free text fallback, the reaper) made
the failures legible and bounded, and the CPU is what moved a capture from
"never finishes" to eleven seconds. Until the loop was unblocked every symptom
pointed at the wrong cause — which is why "just raise the plan" would have
been the wrong first move even though the plan did need raising.

`WEBSITE_CAPTURE_DEADLINE_S` stays at 300. It only bites on failure, and a
generous ceiling costs nothing when captures take eleven seconds, while a
tight one would fail real customers on genuinely slow sites.

---

## 2026-08-21 (later) — "Do we need memory, or is something leaking?"

Founder's question, and the honest answer is neither — the first diagnosis in
the entry below was wrong and is corrected here.

**The 502s were synchronous I/O on the event loop, not memory.**
`get_supabase_admin()` is a *sync* client, and `store.py` called
`bucket.upload(...)` inside `async def`. A multi-megabyte screenshot upload
held the loop, so no request was served, Render's health check timed out, and
the platform returned 502 on every endpoint — indistinguishable from an OOM
from outside. Six storage call sites now run on threads. The same blockage is
why every capture deadline appeared not to work: a blocked loop cannot run its
own timers.

**`/health` now reports the running commit** (`RENDER_GIT_COMMIT`, seven
chars). This entry exists partly because a whole afternoon was spent testing
production against changes that may or may not have shipped, and once drawing
a wrong conclusion from it. That question now has an answer.

**Where it stands, measured against a confirmed commit on a fresh process:**
`example.com` completes the full check in 94 seconds with a real critique, so
the pipeline is healthy. `simplepractice.com` still wedges — once a Playwright
call stops responding, in-process cancellation cannot clear it, and the reaper
closes the row at 20 minutes with a refund.

**Recommendation: raise the plan and measure before building anything.** The
binding constraint is CPU — `starter` is half a vCPU, and layout and DOM work
are what run long. The 2 GB Standard plan doubles CPU and quadruples memory.
`WEBSITE_CAPTURE_CONCURRENCY` and `WEBSITE_CAPTURE_DEADLINE_S` are env-tunable
so the headroom can be used without a deploy. If wedges survive that, the
durable fix is a killable browser subprocess — see S-6 in PRELAUNCH_BUGS.

---

**The instance is the constraint, and this is the entry to read first.**
`render.yaml` puts `saibyl-backend` on the **starter** plan: 512 MB, half a
CPU. One headless Chromium wants 300–500 MB of that, while the API, the
concurrent runs and the analysis pipeline share the rest. Measured, not
assumed:

- Three sample products reaching their website checks together produced
  **502 Bad Gateway on every endpoint** — taking down run polling, billing
  calls and the capital shortlist, none of which involve a browser. Captures
  are now capped at one at a time (`WEBSITE_CAPTURE_CONCURRENCY`, default 1)
  precisely because the cost of getting that number wrong is paid by every
  *other* founder on the platform.
- A run's analysis that takes ~200 s alone took **1,800 s and did not finish**
  while a capture was running beside it.
- No website check has completed since 2026-08-17, and none has *ever*
  completed for a heavy commercial site. See S-6 in PRELAUNCH_BUGS: the
  recommendation is to raise the plan and re-test before building anything,
  because that is a config change that answers whether the larger fix (moving
  the browser out of the API process) is needed at all.

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
