# Handoff — launch readiness, 27–30 August 2026

Nineteen commits, `2e4745d` … `3cc00c6`, all on `master` and deployed. This is
the session in which Saibyl **took its first real money** and grew the surfaces a
founder needs after they have paid.

`HANDOFF.md` is unchanged and still governs — §2 and §2a hold the standing rules
CLAUDE.md points at. This file covers only what moved in these three days.

---

## 0. Read this first — three things that look like bugs and are not

A future session that "fixes" any of these makes the product worse. Each is a
founder decision with the reasoning in `DECISIONS_LOG.md`.

1. **The trust card's team-information critical stays open.** The website check
   reports, as a critical, that saibyl.com has no founder names, no LinkedIn, no
   About page. The founder's answer: *"I don't want any personal name to appear
   on it. If it becomes an issue we'll work on it later."* Consistent with
   CLAUDE.md's standing rule. **Do not add an About page.** If it is ever
   revisited, the shape that satisfies both is a company page about Saido Labs.

2. **Runs realise 80% margin and modules realise 96%.** Not a rounding error —
   `credits_for(cogs)` for runs, `credits_for(cogs / 0.2)` for modules, so the
   margin is taken once when credits are sold at 200/dollar and again in the
   module formula. `_clearance_price_credits`'s docstring says "at the target
   margin", which makes the second application look unintended. **The founder
   decided to keep it.** Priced at parity, the website check would be 1,218
   credits instead of 1,750.

3. **`/app/admin` is absent from the navigation on purpose.** `require_platform_admin`
   answers **404, not 403**, so a probe cannot confirm the surface exists; a
   sidebar entry would announce it to exactly the people that hides it from.
   Recorded in `ia.test.ts`'s `NOT_CLICKABLE` map. **If a link to it appears,
   that is the bug.**

---

## 1. Current state

**Live and verified in production.** Every item below was confirmed by a
discriminator only the new build could produce — not by a green deploy.

| Area | State |
|---|---|
| Payments | **Live.** First real charge 28 Aug: `cs_live_…`, $10 → 2,000 credits, webhook verified, balance moved. |
| Password recovery | Live, and **exercised by the founder on a real account** (30 Aug). |
| LLM | **Opus 5**, `LLM_EFFORT=medium`. Fast path stays Haiku 4.5. |
| Website check | Graded against `taste.py`, not against a competitor. |
| Work index | `/app/work` — one chronology across runs, reports, checks, rewrites, clearances. |
| Admin console | `/app/admin`, gated on `ADMIN_ORGANIZATION_ID` (set to Saido Labs). |
| Supabase advisors | 19 → 4, and the 4 are documented decisions. |

**Migrations applied this session** (repo copies in `backend/scripts/migrations/`):

- `043_pin_function_search_path.sql` — 12 functions, plus the `handle_new_user`
  EXECUTE revoke
- `044_objection_outcomes.sql` — did a predicted objection actually happen
- `045_followup_sends.sql` — idempotency for the follow-up cron
- `046_credit_grants.sql` — who granted credits, to whom, why

---

## 2. Open work, in the order I would take it

### 2.1 The follow-up cron — built, deployed, **inert**

`services/engine/followup.py` and `scripts/send_followups.py` are on master and
nothing runs them. This is the loop that fills `objection_outcomes`, and until
it runs, **the credibility critical both evaluators put first stays open
permanently** — there is no other path to "N of M predicted objections were
raised by real buyers".

Three human steps, all in `INFRA_LOG.md` under *"The follow-up cron"*:

1. Create the `saibyl-followups` cron service in Render. **Do not connect
   `render.yaml` as a Blueprint** — the services were created by hand, and a
   Blueprint would stand up duplicates of backend, frontend and Redis. Create
   the cron job manually with the Docker settings in that log entry.
2. Set its env vars. **A cron service inherits nothing** from the web service —
   all four Supabase vars, `RESEND_API_KEY`, `EMAIL_FROM`, `EMAIL_REPLY_TO`,
   `FRONTEND_URL`.
3. **Verify `saibyl.com` in Resend.** Until then Resend accepts only
   `onboarding@resend.dev` to the account owner — which looks exactly like
   working software until the first real founder gets nothing.

Verify with `python -m scripts.send_followups --dry-run`, which counts who is
due and sends nothing. It returned `1 due` on 28 Aug.

### 2.2 Cross-organisation grounding — needs a sentence, not code

`grounding.py` is wired at `GroundingScope.OWN`: the room reads that founder's
own past runs and nobody else's. `SHARED` is written, tested, and **off**.

It is worth most to a founder with **no** history — their first run — and those
are exactly the people who have contributed nothing to the pool. Enabling it
needs `/privacy` to say so first; today it promises *"nothing you upload is
visible to other customers"*. Suggested wording is in `DECISIONS_LOG.md`.

### 2.3 Calibrate `taste.py`'s weights

`standard` returned **93** on saibyl.com across three runs. Against a stripped
page scoring **0** the ordering is right, but 93 on a page carrying seven
credibility findings suggests the weights are lenient. Worth tuning against two
or three more real pages before trusting it.

### 2.4 The orphan-shaped things

- `admin@saidolabs.com` and `jesse@saidolabs.com` are **both owners of the same
  org** (Saido Labs, `231b7f17-…`). Nothing is orphaned. The `admin@` address is
  not a real mailbox, so it cannot recover; `jesse@` can. Deleting `admin@` is
  optional tidy-up, not urgent.
- Test accounts hold real credits and distort "credits outstanding" on the
  console. 189,495 of the 523,227 sit in Saido Labs alone.

---

## 3. What changed, and the reasoning worth keeping

### The website check stopped comparing founders to other companies

The second field read *"A site you admire"* over *"We'll measure yours against
theirs"*. The founder filled it in with **his own url**, so the check compared
saibyl.com to saibyl.com — and the design reviewer's rubric scored *"how close
this page's visual discipline comes to the reference's"*. His objection was the
premise, not the mistake: *"We're trying to give founders an honest evaluation
on their site."*

`taste.py` is the replacement. Its structural idea is worth carrying:

> **A rubric made only of penalties has its maximum at the empty page.**

Every rule in `measured.py` is a variety penalty — too many radii, colours,
shadows. The revision loop found that gradient and took it: `measured` 35 → 73
while `design` fell 95 → 72, netting +5 overall so the loop declared a win and
returned a page the founder described as having "not really much to it".
`taste.py` splits rules into **violations** and **requirements**; requirements
are the half deletion cannot satisfy. A stripped page scores **0**.

### `measured` and `standard` are the only reproducible dimensions

Across a model change *and* an effort change they returned **66 and 93, three
runs running**, while every vision dimension moved 4–20 points. **They are the
control.** When judging any future change: if those two hold and only the vision
scores drift, that is the ±10 noise band, not a regression.

### Opus 5 could not be an environment-variable change

`temperature` is rejected with a **400** on Opus 4.7+, and `llm_client` passed it
on every call with twelve call sites supplying their own. Flipping `LLM_MODEL`
first would have failed *every LLM call in the product*.

Found on the way: `config.py` defaulted to `claude-opus-4-7`, which rejects
`temperature`. Production only worked because the env var overrode it to 4.6 —
**an unset `LLM_MODEL` would have 400'd everything.**

Measured, same check, same 8 calls:

| | Opus 4.6 | Opus 5 `high` | Opus 5 `medium` |
|---|---|---|---|
| Cost | $0.6493 | $1.2177 | **$0.8749** |
| Overall score | 75 | 74 | **74** |

Input +29% is the tokenizer at 4.7 and cannot be tuned. Output +114% is thinking,
on by default and **79% of the bill** — which is why `effort` is the lever.
`medium` is 28% cheaper at the same score.

### Credits: measure before you price

`WEBSITE_CHECK_COGS_USD` still reads `$0.35`, an estimate. Measured is **$1.2177**
— 3.5× low. The price stays at 1,750 credits because at 200 credits per dollar
that is $8.75 of revenue against $1.22 of cost: **86% realised margin**, above
the 80% floor. The measured figure is recorded beside the constant rather than
replacing it, because `_clearance_price_credits` would take the price to ~6,100
credits.

---

## 4. Failure classes this session produced

Added to `CRITICS_LOG.md` in full. The three worth knowing before touching
anything:

**A missing capability hides behind copy that sounds decided.** There was no
password recovery at all — no route, no email, no token. Three surfaces said so
confidently (`mailto:`, a Settings rationale, a signup 409), each written as a
decision. **Confident copy describing an absence is indistinguishable from
confident copy describing a choice.** Grep for capabilities the way you grep for
claims: *what can a user not do, and does anything admit it?*

**The vendor's own remediation would have broken production.** Supabase's
advisor says set `search_path = ''`. Nine of twelve functions reference their
tables unqualified, so that would have broken signup, every run, and every Stripe
payment — and **not at migration time**: `ALTER FUNCTION` does not re-parse the
body, so it fails on the next call. A remediation is generic; a codebase is not.

**I overwrote a working module because I did not read it first.** Asked to build
an admin console, I used Write on `app/api/admin.py`, which already existed. It
was recovered from git within seconds, but only because it was committed. I had
grepped for `is_admin`/`require_admin`, found nothing, and concluded no admin
concept existed — while `admin,` sat in `main.py`'s import block. **grep for a
capability is not `ls` for a file.** Before Write on any path not read this
session, list it.

---

## 5. Environment variables set this session

On `saibyl-backend`:

```
LLM_MODEL              = claude-opus-5
LLM_FAST_MODEL         = claude-haiku-4-5
STRIPE_SECRET_KEY      = sk_live_…            (was sk_test)
STRIPE_WEBHOOK_SECRET  = whsec_…              (live endpoint)
ADMIN_ORGANIZATION_ID  = 231b7f17-d17c-4f6e-b530-f0196acd841b
```

`STRIPE_PRICE_ID_STARTER/_PRO/_ENTERPRISE` were **deleted** — leftovers from the
subscription tiers removed on 25 Aug, never read by any Python, and an active
trap: three empty slots named PRICE_ID invite pasting a Stripe product id into
something that ignores it. A top-up builds its price inline with `price_data`,
so **there is no Stripe product to create.**

`LLM_EFFORT` is not set; the code default is `medium`. Set it on Render only to
override.

---

## 6. Verification gate

Unchanged, and it held all session. From `frontend/`:

```
npm run build          # tsc -b && vite build && prerender
npx eslint src --quiet
npx vitest run         # 143
```

From `backend/`: `ruff check app tests scripts` and `pytest` (**2,112**).

**The gate does not catch what mattered most this session.** The favicon was a
valid SVG of the wrong mark; the missing recovery flow was three accurate
sentences about an absence; the deletion-gaming rubric passed every test it had.
Each needed somebody to look at the running product beside the thing it claims
to implement.

Deploy verification uses a discriminator only the new build can produce, in
**both** directions where possible — new string present *and* old string absent.
A health check goes green whether or not the route you shipped exists.
