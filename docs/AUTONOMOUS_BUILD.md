# Autonomous build — the staged IA, and everything still open

**Saido Labs LLC** · Written 2026-08-05 for a cold context window · **You have
standing authority to build, commit, deploy and verify without asking.**

Read this file and `HANDOFF.md` §1a, §2, §2a. Nothing else upfront.

The user is asleep. They have pre-authorised everything in §2 and want to wake
to a deployed system. **Do not stop to ask permission for anything in the
authorised list.** Do stop for anything in §3, which is short and absolute.

---

## 0. Where things stand right now

Deployed and live on `master` (frontend + backend both on Render, auto-deploy on
push). Migrations **017–029 applied**; `025` is the only unapplied one and §2.6
covers it.

Shipped today: the V1 audit worked down (~35 defects), prediction markets
removed, one upload surface feeding ICP synthesis, multi-pack + org library,
GTM candidate discovery with UI, the paired variant estimator, a purpose-built
PDF report, GTM refunds, and real caps on every marketing surface.

Test suite: **973 passing**. Do not let it go backwards.

**The user's own words on what they are building**, because it decides every
judgement call you will make tonight:

> My target user is a SaaS startup founder. Some don't know what an ICP is.
> Some don't know what a prototype is. But they have Claude and Claude Code and
> they can spin something up. I want a platform that grows with them — validate
> the idea, generate the go-to-market, test the marketing copy — so they don't
> waste money running real campaigns to find out.

Stickiness comes from ongoing usefulness, not from a one-time idea validator.

---

## 1. The work, in dependency order

Each item has acceptance criteria. An item is done when the criteria are
demonstrably true, not when the code looks right.

### 1.1 The staged IA — the main build

Full design, already approved by the user:
**https://claude.ai/code/artifact/ddcbeb65-d975-4c8c-a3a0-28854ebbe6a8**

Four decisions are settled. Do not reopen them:

| Decision | Settled as |
|---|---|
| Vocabulary | **Product**, never "Project", in all user-facing copy |
| Company moment (Axis B) | Asked **per run**, defaulting to last time |
| Stage rail | **Open**, never a grey button — see the binding rule below |
| Home | Leads with **products**; attention lives on the product card |

**The two axes.** Conflating them is the whole problem being fixed.

- **Axis A — the steps**, within one product. This is the navigation:
  1. **Audience** — who reacts to this
  2. **Reactions** — what they said, and what they object to
  3. **Answers** — what to say back, and whether it worked
  4. **Buyers** — real companies that match
  5. **Messages** — which version wins
- **Axis B — the moment.** Already built as data in
  `services/engine/founder_stages.py`: concept / pre-launch / launch_gtm /
  growth / fundraise, each with its own adversarial default (0% → 40%). It is
  currently a dropdown buried in the run wizard. Surface it per run.

**The binding rule — this is the part the user specifically asked for.**

> Never a grey button. A stage either runs and states what the answer will be
> missing, or it is blocked with the button that unblocks it.

Every stage shows what it inherited as a clickable line ("Audience — 6 buyer
types, confirmed 4 Aug"), and states the cost of a missing input **before any
credits move**:

| Stage | Missing input | What it must say |
|---|---|---|
| 2 Reactions | no audience | "We'll use a general business audience. You'll get the objections any B2B product gets, not the ones yours will get." |
| 2 Reactions | no material | "Agents will only see your one-line description. Upload the deck and they argue about the product instead." |
| 3 Answers | no objections | **Blocked.** "There are no objections to answer yet — run stage 2 first," with the button that does it. |
| 4 Buyers | audience unconfirmed | "We'll search from our guess at your buyer. Confirm the audience first and the list gets sharper." |
| 5 Messages | fewer versions written than selected | "You picked 4 versions and wrote 2. You'd pay for 4 and two rooms would sit empty." Refused — this guard already exists server-side in `start_simulation`. |

**Home / product card.** One card per product carrying: name, the moment it was
last run at, how many stages have what they need, and attention lines drawn
from what the system actually knows — a completed run, an unresolved
scoreboard, a stale candidate list, a document still processing. **Invent
nothing to fill the card.** A product with nothing to report says so and offers
the next stage.

**Language.** No "ICP", "variant", "A/B", "adversarial cohort", "arena", or
"lens" in user-facing copy. `components/founder/AudienceReview.tsx` is the
register to match — read it before writing any copy.

**Crisis does not exist and must not appear.** Not as a nav item, not greyed
out, not "coming soon". The user has explicitly deferred it.

**Acceptance:** a founder who has never seen the product can get from signup to
an objection map without reading anything, and at every point where they could
skip a step the screen tells them what it will cost them.

⚠ **That criterion is a judgement, and you are the worst available judge of it** —
you will have spent the night in this code and every label will look obvious to
you because you wrote it. **§4a is how it gets proved instead of asserted, and it
is not optional.**

### 1.2 GTM query targeting — returns competitors instead of buyers

Reported from live use: searching for buyers returns vendors in the user's own
category. "Companies using Datadog" returns Datadog.

`services/gtm/query_compiler.py` builds from ICP archetypes but excludes
nothing. Fix so the compiler excludes the user's own category and known
competitors — the ICP already carries `competitors[]` and `category`, and
`documents.material_kind = 'competitor'` marks competitor material.

**Acceptance:** a test with a realistic ICP asserts the compiled queries exclude
the profile's own category vendors; the excluded terms are visible in the
`GET /gtm/estimate` preview so the founder can see what was filtered.

### 1.3 The in-app sentiment arc is unreadable

Reported: "mean valence per round R1–R5 only shows a difference in colour, and
it doesn't really translate to a human person's eye."

This is the **in-app** chart (`components/analysis/`), not the PDF — the PDF was
rebuilt today. Encode magnitude in position or length, not colour alone, and
show the confidence band. `services/export/vector_charts.py` solved the same
problem for print; read it for the approach.

**Acceptance:** the round-over-round trend is legible in greyscale and each
point carries its interval.

### 1.4 Landing page redesign

Audience: the SaaS founder above. **The free teaser is the primary CTA.**

The current page sells a different product — it leads with scale, lists "Sports
& Betting" and "Policy & Government", and never states the actual argument: your
audience is built from your own material, and every number traces to something
an agent said.

⚠ Every number on that page is an advertised claim. `TIER_CAPS` is the source of
truth (founder 100 / growth 150 / agency 250 / enterprise 1,000). Do not restore
a scale number the caps cannot back — that page carried a 1,000× overstatement
for months.

**Acceptance:** `npm run build` clean, no claim that contradicts `TIER_CAPS`, and
the primary CTA is starting a free run.

### 1.5 Regenerate the pricing numbers everywhere

Today's subject-brief change moved the cost model. `scripts/quote.py` already
emits the new tables. Propagate:

| | was | now |
|---|---:|---:|
| Standard run | $2.74 | **$3.01** |
| Blended agency mix | $7.46 | **$8.65** |
| Inoculation loop | $5.97 | **$6.44** |
| Tier runs | 7 / 21 / 73 | **6 / 19 / 66** |
| Free grant | 1,200 | **1,500** |

Files: `PRICING_GUIDE.md` (§1.5, §1.6, §2.3, §2.3b), `PRD_V2.md` §8,
`HANDOFF.md` §7, `DECISIONS_V2.md` §4 and §15d.

**Acceptance:** no stale figure survives a grep for `2.74`, `7.46`, `5.97`,
`7/21/73`, `1,200 credits`.

### 1.6 Close the docs out

- `V1_AUDIT.md` item 36 is fixed in code but still reads open. Close it with the
  evidence, including the two things the audit never recorded: `python:3.12-slim`
  ships zero fonts, and the storage upload had no `upsert`.
- `HANDOFF.md` — update §0 and §1 to today's state. It is the cold-start doc; a
  stale one is worse than none.
- `ARCHITECTURE_V2.md` — one dated entry for tonight's work.
- `05_PRD/saibyl-prd/INFRA_LOG.md` — outside the git repo, at
  `Saibyl/05_PRD/…`. Write it anyway.

### 1.7 If time remains

- **Agent count 27 → 50, unreproduced.** Both the quote row and the simulation
  row carry 50 from one submit, and the deployed slider is byte-identical to
  HEAD. Several defects of that class are fixed; the specific path is not found.
  **Do not invent a root cause.** If you reproduce it, fix it and say how.
- `V1_AUDIT` items 19 (fire-and-forget tasks) and 39 (no-caller subsystems).

---

## 2. Pre-authorised — do these without asking

1. **Write, refactor and delete code**, subject to the standing rule that
   nothing is deleted without grepping for direct calls, type references, string
   literals, dynamic imports, re-exports and tests.
2. **Commit** — author `Saido Labs LLC <info@saidolabs.com>`, committer
   `Jesse Crawford <jcapathy@gmail.com>` (set `-c user.name`; it is unset in the
   environment). **No Claude attribution anywhere.**
3. **Push to `master`, and keep `v2` aligned** (`git push origin master:v2`).
4. **Deploy.** Pushing to `master` auto-deploys both Render services. Follow the
   protocol in §4.
5. **Apply additive migrations** to `txmvwuekkiedgxwovorp` via the Supabase MCP
   `apply_migration` — new tables, new nullable columns, new indexes, new RLS
   policies, `CREATE OR REPLACE FUNCTION`. Verify against `information_schema`
   afterwards; `IF NOT EXISTS` guards hide type drift (migration 017's lesson).
6. **Apply migration `025`.** Verified safe: the two `p_project_id` asset-count
   functions already exist in production, so the `CREATE OR REPLACE` half is a
   no-op, and the `DROP FUNCTION increment_asset_count(UUID, INT)` removes an
   overload nothing calls (the single call site passes `p_project_id`). Its value
   is that a database rebuilt from migrations currently breaks upload and delete
   on day one.
7. **Spend on live runs** up to **$40 total** for verification. A gate run is
   ~$1.70. The user has funded this deliberately.
8. **Spawn as many agents as the work supports.** See §5.

---

## 3. Hard stops — wake up to a question, not a fait accompli

1. **Stripe. Anything.** No Products, no Price IDs, no webhook changes, no
   `PLAN_PRICE_MAP` edits that touch real price ids. The tier migration is
   parked by the user's explicit decision.
2. **Destructive SQL.** No `DROP TABLE`, `DROP COLUMN`, `TRUNCATE`, `DELETE
   FROM`, or `ALTER COLUMN` that narrows a type. The only authorised drop is
   `025`'s dead function overload.
3. **Anything that contacts a real person** — no emails, no outreach, no posting.
   GTM discovery *finds* companies; it does not contact them.
4. **Enabling contact discovery for any org.** `gtm_contact_discovery_enabled`
   stays FALSE. It stores personal data and needs counsel review first.
5. **Crisis lens.** Deferred by the user. Do not build it, do not stub it.
6. **Deleting or rewriting `DECISIONS_V2.md` entries.** Add, never revise —
   it exists so a future session can disagree from an informed position.
7. **Spending past $40** on live runs.

If you hit one of these, do everything else and leave it in the wake-up report.

---

## 4. The verification gate — non-negotiable

Run **before every push**. Not a subset, not an equivalent-looking command.

```bash
cd backend  && python -m ruff check app tests scripts && python -m pytest -q
cd frontend && npm run build && npx eslint . --quiet
```

**⚠ `npm run build`, never `npx tsc --noEmit`.** They are different checks.
Production runs `tsc -b && vite build`; `tsc -b` is project-references mode and
rejects things `--noEmit` accepts. On 2026-08-04 that gap hid **five** build
errors, the frontend service had been failing to build for weeks, and Render was
serving a stale bundle while every session reported a clean frontend. This is
the single most expensive lesson in this document.

**If `pyproject.toml` changes, run `uv lock` then `uv lock --check`.** The
Dockerfile runs `uv sync --frozen`, so a lock that disagrees fails the *build*.
This trap was hit twice in one day.

**Tests must not go backwards from 973.** A test that passes because it asserts
nothing is worse than a missing test — `structlog.testing.capture_logs`, never
`caplog`, and `tests/test_log_capture_canary.py` guards that.

---

## 4a. Proving the staged IA works, rather than believing it does

The self-assessment problem is not solved by better criteria. It is solved by
turning most of the judgement into assertions, and having the residue judged by
something that has not seen the build.

### Five tests that must exist and pass

Frontend suite. Each one is mechanical — no judgement, no screenshots.

1. **Jargon.** Scan user-facing strings (JSX text, `aria-label`, `title`,
   `placeholder`, button labels) for `ICP`, `variant`, `A/B`, `adversarial`,
   `cohort`, `arena`, `lens`, `archetype`, `canonical`, `valence`, and
   `simulation` used as a noun the founder must understand. Fail on a hit.
   Comments and type names are excluded — this is about what renders.
   **This is the test most likely to catch you**, because the jargon is what you
   will have been reading all night.
2. **No dead ends.** Every empty state renders at least one link or button. A
   screen that tells a founder there is nothing here and offers no way forward is
   where they close the tab.
3. **Never a grey button.** No `disabled` control without an explanation node
   adjacent to it. This is the binding rule from §1.1, asserted.
4. **Inheritance is declared.** Every stage renders either its inherited-state
   line ("Audience — 6 buyer types, confirmed 4 Aug") or an explicit
   missing-input notice. Never neither.
5. **Reachability.** Walk the route graph from `/app` and assert every built
   feature is reachable in **≤ 3 clicks**. This is the actual defect being
   fixed — Audiences, Companies and the whole scoreboard shipped with no route
   to them — so it is the one test that would have caught the original problem.

### Seed the states, or they will not get checked

Degraded states are the hard part to verify because they are the hard part to
*produce*. Seed a test org with four products so every state is a URL:

| Product | State |
|---|---|
| A | created, nothing uploaded |
| B | material uploaded, audience confirmed, no run |
| C | one completed run, objections found, no answers drafted |
| D | run, answers, buyers and a message test — the full rail |

### Look at it

Run the app and screenshot each stage against each seeded product. The most
valuable catch of the whole day came from an agent rasterising PDF pages and
*looking* — it found a hatch generator that clipped every bar not at the origin,
which no passing test would ever have surfaced. Reading your own markup is not
the same as seeing it render.

There is a `/run` skill for launching the app.

### The cold read

Spawn one agent that has **not** seen this document, the design artifact, or the
diff. Give it only the screenshots and one instruction:

> You are a SaaS founder. You have shipped something with Claude Code. You do
> not know what an ICP is. Get from here to a list of the objections that will
> kill your launch. Narrate every point where you are unsure what to click, and
> every word you do not understand.

Its confusion is the finding. **Do not explain the design to it and re-ask** —
an agent holding the design will always find the design obvious, which is
exactly the failure mode being tested for.

### The builder does not sign off

Whoever writes the IA does not run the acceptance pass. A second agent takes
§1.1's criteria, the five tests, the screenshots and the cold read, and reports
pass or fail with evidence. Separate roles, because the author cannot un-know
what they meant.

### Make being wrong cheap

Ship the new IA as **additive routes with the existing ones still working**. If
the morning review rejects it, the fix is a navigation change rather than a
revert of a night's work. This does not reduce the chance of being wrong; it
reduces what wrong costs, which is the better lever when nobody is awake.

---

## 5. Running agents in parallel

**Assign file ownership up front and never let two agents own one file.** Two
agents editing the same file is how a mid-write commit happens.

**Assign migration numbers centrally before dispatch.** Two agents both chose
`028` today and it had to be untangled by hand. Highest applied is `029`.

**Give every agent these, verbatim:**

- Do not run any git command. The coordinator commits.
- Verify before you fix. Several findings in this codebase are reasoned rather
  than observed; reject the ones that turn out to be wrong and say so.
- Never introduce a silently-swallowed exception. The governing defect class
  here is that a lookup miss and a legitimate absence share one value, so
  nothing logs and health reports success.
- Never render a fabricated number. Absent is absent — not zero, not a dash that
  reads as data.
- Gate the frontend with `npm run build`, not `tsc --noEmit`.
- Use `structlog.testing.capture_logs`, never `caplog`.

**Before committing an agent's work, check its claims.** Today an agent reported
a fix that was one step short — the select it told me to add was missing a
column, which would have left a 10% under-charge silently in place. Another
reported "PDF export writes no file" and was right, but for a different reason
than the audit recorded. Read the code, do not trust the summary.

---

## 6. Deploy protocol

1. Gate green (§4).
2. Push `master`, then `master:v2`.
3. **Watch for the switchover by content, not by asset hash.** A hash changes for
   build-environment reasons; content does not lie.

```bash
# backend: new code serving
curl -s -o /dev/null -w "%{http_code}\n" https://saibyl-backend.onrender.com/api/gtm/settings   # 401 = live
curl -s https://saibyl-backend.onrender.com/health

# frontend: grep the served bundle for a string only the new build contains
b=$(curl -s https://saibyl-frontend.onrender.com | grep -oE '/assets/index-[A-Za-z0-9_-]+\.js' | head -1)
curl -s "https://saibyl-frontend.onrender.com$b" | grep -o "<a-new-string>" | wc -l
```

⚠ `grep -c` exits 1 on zero matches, so `$(grep -c … || echo 0)` yields `"0\n0"`
and a `!= "0"` test passes. Use `grep -o … | wc -l`. My own deploy check gave a
false positive on exactly this today.

**Ordering.** The two services build independently and the Docker backend can
beat the static frontend. New-frontend-with-old-backend is harmless; the reverse
briefly renders empty lists. Nothing to do about it beyond knowing which way you
are exposed while it settles.

**Migrations that add columns the code writes go BEFORE the deploy.** Migrations
that add a constraint the code must satisfy go AFTER (that was `019`). The rule
is that a writer and its schema must never be apart in the direction that breaks.

**Rollback:** `git revert` the range, push, and let Render redeploy. Every
migration authorised tonight is additive, so a code rollback needs no schema
rollback.

---

## 7. The wake-up report

Leave it as the final message. The user reads this first:

1. **What is live** — with the verification output proving it, not asserted.
2. **What was built** — against the acceptance criteria in §1.
3. **The cold read, quoted verbatim.** Where the agent that had never seen the
   build got stuck, and which words it did not understand. Quote it even where
   it is unflattering — especially there. That transcript is the closest thing
   to a user test the user will have before showing this to real founders, and
   it is worth more than any summary you could write about it.
4. **What you could not do** — hard stops hit, things you could not reproduce,
   anything you deliberately left. Be specific; "mostly done" is not a status.
5. **What it cost** — live-run spend against the $40.
6. **What you would do next**, in priority order.

**Report faithfully.** If something is broken, say so with the output. If a test
was skipped, say that. This codebase's entire defect history is things that
reported success for the wrong reason — do not add to it at the last step.
