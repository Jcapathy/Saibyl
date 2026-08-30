# Decisions Log

Standing rule (founder directive, 2026-08-16): every decision that shapes the
product or the build — who made it, what was decided, and the why that lets a
future session know whether it still holds. Newest at the top.
`DECISIONS_V2.md` holds the V2-era record and remains authoritative for those
choices.

---

## 2026-08-30 — What the destination key keeps, and where the icon/image line sits

Two decisions taken while calibrating `standard` against six real pages. Both
are recorded because each looks, from the code alone, like it could go the
other way — and one of them reverses a choice that was made on purpose.

**1. The destination key keeps the host and the fragment, and still drops the
query.** `where` — the key behind *"one destination wearing several labels"* —
was `URL.pathname`, and the comment beside it gave a real reason: *"A full URL
can carry a token or an email in its query, and the census rides inside
prompts."* That reason was verified, not assumed: `critics._census_text` does
`json.dumps(census)` of the whole dict into the design reviewer's prompt, and
`measured.py` renders `where` verbatim into founder-facing copy
(*"…all go to {where}"*). **So the query stays dropped.**

The host and the fragment carry no such risk and their loss was a defect: seven
origins on anthropic.com collapsed into one bucket keyed `/`, taking two WCAG
skip links with them. The key is now `origin + pathname + fragment`, with the
origin omitted when it matches the page's own — same-origin links stay bare
paths, which is both what a founder reads in the finding and the shape stored
censuses already carry.

One narrower guard: a fragment containing `=` is dropped like a query. A real
anchor is `#pricing` or `#main`; one carrying key=value pairs is an OAuth
implicit-flow payload, and falls under the same rule.

**2. `_CENSUS_MEDIA_MIN_PX = 64`, and the number is measured.** The new
`structure.visual_media` field counts visible imagery — `<img>`, inline `<svg>`,
`<video>`, `<canvas>`, a CSS `url()` background — at or above a minimum rendered
dimension. 64px is the lowest threshold at which all five designed pages in the
sample score ≥ 1 while news.ycombinator.com scores 0. Below it the count fills
with iconography: stripe.com ships **174 visible `<svg>` and exactly 2 of them
are 64px or larger**. The full table sits beside the constant.

**`images` was deliberately not repurposed.** It still means the literal `<img>`
tally. A field named `images` that quietly meant "imagery of any kind" is the
same defect one layer down — a name asserting something nobody checked — so the
judgment got its own field and the count kept its own meaning. The absence of
`visual_media` is what tells both rubrics a census predates 2026-08-30, and both
fall back to `images` for those rows: a stored capture cannot be re-measured,
and the narrower count is the evidence those rows were already scored under.

---

## 2026-08-28 — Three pricing and cost decisions, two of them "leave it"

Founder decisions, taken against measured numbers rather than estimates. Two of
the three are deliberate non-changes, written down so a future session finds a
decision rather than what looks like an oversight.

**1. `LLM_EFFORT=medium`, in production.** Two full checks of saibyl.com from
`llm_usage`: Opus 4.6 cost $0.6493, Opus 5 cost $1.2177 for the same eight
calls. Input rose 29% (the tokenizer change at 4.7, untunable); **output rose
114% and is 79% of the bill** — thinking is on by default on Opus 5 and billed
as output. Effort is the lever, so it is set rather than left at the API's
`high`.

This is an experiment running in production, and the way to judge it is
specific: **`measured` and `standard` are arithmetic and must not move at all**
(they returned 66 and 93 across a model change). If they hold and only the
vision dimensions drift a few points, that is the ±10 noise already measured on
identical inputs — not degradation.

**2. LEAVE the 80% / 96% margin asymmetry. Do not "fix" it.** A run is priced
`credits_for(cogs)` and realises exactly 80%. A module is priced
`credits_for(cogs / 0.2)` and realises **96%**, because the margin is taken once
when credits are sold at 200 per dollar and again in the module formula. The
docstring on `_clearance_price_credits` says "at the target margin", so the
second application reads as unintended — **and the founder has decided to keep
it.** Priced at parity with a run, the website check would be 1,218 credits
instead of 1,750. This is revenue, and it is a decision, not a bug to tidy.

**3. LEAVE the website check at 1,750 credits.** Measured COGS is $1.2177
against the $0.35 the constant still holds — 3.5x low. At 200 credits per
dollar the founder pays $8.75, so the realised margin is **86%**, above the 80%
floor. Updating `WEBSITE_CHECK_COGS_USD` to the measured value would take the
price to ~6,100 credits ($30.44) through the formula above, which is why the
measurement is recorded next to the constant rather than replacing it.

---

## 2026-08-28 — Opus 5, and why it could not be an environment-variable change

Founder decision: *"migrate to Opus 5 for the LLM model."*

**The migration was code, not config, and the reason is a 400.** `temperature`,
`top_p` and `top_k` are **rejected on Opus 4.7 and later**. `llm_client` passed
`temperature` on every call and twelve call sites across eight files passed their
own value. Changing `LLM_MODEL` to `claude-opus-5` without removing them first
would have failed *every LLM call in the product* — runs, critics, reports,
extraction — not degraded them.

**A latent bug found on the way.** `config.py` defaulted `llm_model` to
`claude-opus-4-7`, a model that rejects `temperature`. Production only worked
because the Render env var overrode it to `4.6`. **If `LLM_MODEL` had ever been
unset, every LLM call would have 400'd immediately** — the fallback was the
broken path. Default and deployment now agree.

**`max_tokens` went 4096 → 8192, and that is part of the migration rather than a
tuning choice.** On Opus 5 thinking is ON by default and `max_tokens` caps
thinking *plus* the answer. The old ceiling was sized around the answer alone on
a model that did not think, so the same request could now truncate mid-sentence —
which surfaces as a JSON parse failure in `llm_structured`, on work already paid
for. 8192 is also the largest value that keeps `llm_vision` on its existing
non-streaming path.

**The fast model stays on Haiku 4.5**, against the suggestion to move it to
Sonnet or Opus. `llm_fast` carries agent actions and per-event measurement — the
dominant cost line, and the reason a large run is affordable at all. Sonnet 5 is
3× Haiku's rate and Opus 5 is 5×, and the run price was set deliberately at
$15-ish so that "why wouldn't I run it?" is the reaction. Tripling the dominant
line to chase quality nobody has measured is the wrong order. **The right way to
decide it is Saibyl itself**: run one product through the room on each model and
compare the objections. Its id was also corrected from
`claude-haiku-4-5-20251001` to `claude-haiku-4-5` — the dated form is a
training-data habit and only priced correctly by prefix luck.

**Open, and it needs a measurement rather than an opinion:** the tokenizer
changed at 4.7. The same eight-word prompt measured **16 tokens on 4.6 and 22 on
Opus 5** in a live check. Credits are derived from measured cost plus 80%, so
run economics move. Re-measure a full run before trusting the price table.

---

## 2026-08-28 — Grounding, not training; and an accepted finding on the trust card

Founder decisions, taken after the second website check on saibyl.com.

**1. The team-information critical is accepted, not fixed.** The check reports
as critical: *"No team information exists anywhere — no founders' names, no
LinkedIn links, no 'About' or 'Team' page."* The founder's answer:

> *"I agree we don't need any LinkedIn links about our team page. We don't need
> any of that stuff. I don't want any personal name to appear on it. If it
> becomes an issue we'll work on it later on."*

This is consistent with the standing rule in `CLAUDE.md` — *"No personal name
ever appears on it"* — and it is a **deliberate trade-off, not an oversight**.
A future session reading a critical on the trust card must not helpfully add an
About page. If it is ever revisited, the shape that satisfies both is a company
page about Saido Labs, not a personal byline.

**2. Grounding rather than training, and the reasoning behind the change.**
The founder's proposal was to train the buyers on scraped real-world data and
say so on the landing page. The objection to that, which he accepted:

The trust critical asks *"do synthetic objections predict real ones?"* — a
question about **outputs**. Training changes **inputs**. "Trained on real-world
data" is a process claim standing in for an outcome claim, and our own check
already flags two of those on the same page: an internal capacity number *"with
no external benchmark or outcome attached"*, and a privacy claim that *"has no
backing"*. A third would have been caught by our own product, correctly.

**What shipped instead** — and note that it serves both of the founder's stated
goals, *"improve the output quality as well as close the loop on the question
about the outputs"*:

- `engine/grounding.py` reads recurring objections out of **our own completed
  runs** (1,081 objections across 38 runs at the time of writing). Provenance is
  a database query — *"raised in 7 of your own runs"* — rather than a boast. No
  terms-of-service or GDPR exposure, and it compounds with every run.
- `engine/outcomes.py` and migration 044 record whether a predicted objection
  actually happened, which is the only thing that answers the critical.

**3. Cross-organisation grounding is off, and turning it on is a policy
decision.** `/privacy` tells founders their uploads are never visible outside
their account. Aggregate objection labels are derived data, but a founder would
reasonably read one org's runs informing another's as a breach of that sentence.
So `GroundingScope.OWN` is the default; `SHARED` carries a three-organisation
k-anonymity floor, never carries a quote or an org id, and **must not be enabled
in production until the privacy policy describes it.**

**4. No accuracy number until thirty answers.** `MIN_ANSWERS_TO_REPORT = 30`,
and below it `accuracy_for` returns `None` rather than `0`. A rate computed from
four answers is noise with a decimal point, and putting it on the landing page
would be the exact defect the whole exercise is meant to close.

---

## 2026-08-27 — Four decisions inside password recovery

Taken while building `/auth/forgot-password` and `/auth/reset-password`. None of
them is visible from the outside, and all four are the kind that is expensive to
retrofit.

**1. The reset request answers identically whether or not the address has an
account.** The alternative — "no account for that address" — is friendlier and
is a free account-existence oracle: anyone could feed it a list and read back
which addresses are registered. The cost is real and accepted: a founder who
mistypes their own address is told the mail is on its way. The confirmation
screen prints the address back so the typo is readable.

The neutrality extends to failure. If GoTrue is down the caller still gets the
same sentence and the reason goes to the log, because a 500 that only fires for
addresses that exist leaks exactly what the neutral message is hiding.

**2. The account is named by the verified token, never by the request body.**
`auth.get_user(jwt)` is a round trip to GoTrue that fails on a forged, expired
or already-spent token, and its answer is what selects the row to update.
`ResetPasswordRequest` carries two fields, and a test asserts it will only ever
carry those two: a `user_id` on the wire would let anyone holding any valid
recovery token reset anybody's password.

**3. A completed reset revokes every other session** —
`sign_out(token, "global")`. Somebody resetting a password is frequently doing
it because they think somebody else has it. Changing the password while the
attacker's refresh token stays live achieves nothing. A failure here is logged
loudly but is not fatal: the password is already changed, and failing the
request would strand the caller with a password they cannot be sure of.

**4. The recovery token is stripped from the URL on mount.** It arrives in the
fragment, which is never sent to a server — but it is written to browser
history and rides along on anything copied out of the address bar, and it is a
live credential until spent. `history.replaceState` runs before anything else on
`ResetPasswordPage`; the token lives in component state from then on.

**Still handled by a person: account deletion.** Settings now says only that,
having said "password and account deletion" as one sentence for as long as both
were true.

---

## 2026-08-25 — No subscription tiers. Founders top up as they go

Founder decision, taken while the journey rework was in progress and directly
connected to it.

**What prompted it.** `founder_stages.py` justified the five-stage journey in
its own docstring as *"five purchase occasions for the same account"* — a
recurring charge deciding the shape of the product. Three dogfood runs then
kept returning the same objection: buyers wanted proof that run two beats run
one before committing to $99/month. Removing the subscription removes the
question, and removes the pressure that bent the journey.

**Decided:**

1. **Credits are the only ration.** One balance, one price list, no plan that
   changes what anybody may do. The eight-tier grant and cap tables are gone.

2. **The free run is a 30-person room**, up from 25. It costs 1,335 credits
   against the 2,000-credit grant, leaving 665 — visibly some, and deliberately
   too little to buy a second service, which is the property the grant was
   sized for and which survives the change intact.

3. **The free run and the ceiling are two different things.** `FREE_RUN_SHAPE`
   is a product and a public promise; `RUN_CAPS` is an accident-stopper. The
   first attempt at this change collapsed them into one number and priced the
   "free run" at 65,107 credits against a 2,000 grant — caught by the tests,
   which is the whole reason the relationship was written down as one.

4. **No runs-remaining number anywhere.** `capped_run_credits` existed for that
   one sentence and needed to know the reader's tier to avoid lying. Founders
   are now shown what a *specific* run costs — this module, this size — quoted
   before they commit. `GET /billing/prices` already did this; it simply
   becomes the only pricing surface.

5. **The monthly run allowance goes.** It was derived from the tier grant, and
   under one grant it would have resolved to about ten runs a month — binding
   on the first founder to top up fifty thousand credits, which is exactly the
   failure its own comment was written to prevent. What remains is a flat,
   plan-free backstop against automation gone wrong.

**Safe to do because nobody is on a subscription.** Production on the day of
the decision: thirteen orgs, twelve `trialing`, one `canceled`, and exactly one
Stripe subscription id in the whole system — on the cancelled row. Queried, not
assumed.

**Done the same day.** The Stripe subscription paths (`/checkout`, `/portal`,
`get_subscription_status`, the webhook's subscription branches), `PLAN_LIMITS`,
`SubscriptionStatus` and `SettingsPage`'s plan panel are all removed —
including the alias that could print *"Your plan: Founder · $99/mo"* to an
account that had paid nothing. **Stripe stays** in `mode="payment"`: top-ups
and the one-off report are how founders pay, and neither needs a Price ID.

**Open, and worth real money: `TOPUP_MARGIN_PCT` is still 85%.**
`topups.py` prices a top-up five points above `TARGET_MARGIN_PCT` (80%)
*deliberately* — the docstring says so — so that subscribing would be
"visibly and arithmetically the better deal". It even published the gap to the
founder as `subscription_is_cheaper_by_pct`, which came out to **33%**.

With no subscription to steer anyone toward, that surcharge has no remaining
justification, and it is the difference between credits costing what they cost
and costing a third more. Lowering it to `TARGET_MARGIN_PCT` would make every
price on the new landing page ~25% cheaper. **Left at 85% and flagged rather
than changed**, because it is a pricing decision and revenue, not a cleanup.
The dead comparison field itself is gone.

**Still to do.** Prerendering the marketing routes — `SEO_AEO.md` names it as
"the single biggest AEO unlock" and it is still not done, which means no answer
engine can read any of the copy written today.

## 2026-08-24 — The evaluation logic was inverted: retrieval answers the world, the room answers the reader

Founder-directed, from his own account of building ParryAI. Written up as
`PRD_V3.md` §12, which governs where it conflicts with §2, §3 or §11.

**What prompted it.** Three dogfood runs of Saibyl against Saibyl kept returning
the same finding — buyers believed idea validation and positioning, then stopped
believing at go-to-market — and two sessions treated that as a pitch problem.
It is not. The founder named it as a system-design problem and gave the
counter-example: ParryAI began with a failure he hit inside his own business,
which he fixed for himself, and only *afterwards* did he ask whether Fortune 500
companies had it too and whether anyone had already patented it.

Saibyl's Validate stage asks *"Does this pain exist, who feels it most, and
would they pay?"* — and answers it with a synthetic room. A founder who built
their product out of a pain they personally hit has already answered that from
life. The questions they cannot answer — does this generalise, has someone
built it — are served today by a card at the bottom of the page.

**Decided:**

1. **Two instruments, two classes of question.** Empirical questions (does the
   pain exist beyond me, who else has it, has it been built, who funds it) are
   answered by **retrieval** — real records, cited. Reaction questions (how does
   the pitch read, which objection kills it) are answered by **the room**. The
   room cannot answer an empirical question; that is a category error, not a
   data gap, and no correlation study would close it.

2. **This retires the dominant objection rather than answering it.** *"Synthetic
   feedback doesn't correlate with real buyer behavior"* scored 6.56 load-bearing
   on run three and went unanswered across three rounds. It is correct against
   empirical claims and irrelevant against reaction claims. Narrowing the room to
   reaction is the fix; a validation study we cannot yet run is not.

3. **Validate is re-specified retrieval-first**, and its question becomes *"Is it
   just me — and has anyone already built it?"* Clearance opens the stage,
   prevalence evidence follows, competitor discovery follows that, and the room
   is last and optional. **This supersedes 2026-08-23 item 3** — clearance folds
   into Validate as the *opening move*, not as a card. It is the only capability
   in the product with zero correlation exposure, so it front-loads the
   credibility the room's later claims depend on.

4. **`concept_validation`'s report questions come out where they are empirical.**
   *"Do agents recognise this pain unprompted"* and *"Is there stated willingness
   to pay"* both put a world-question to the room — and the second contradicts
   the stage's own `cannot_conclude`, which already concedes pricing is direction
   and not a number. A stage may not list as a question the thing it declares it
   cannot conclude.

5. **Raise gates on declared recurring revenue.** The founder's sequence is
   explicit: raise comes after MRR. `capital/matching.py` already filters firms
   that do not invest pre-revenue, but nothing gates the founder, so today the
   platform will run a fundraise for an account with no customers. Per the
   standing rule this is not a `disabled` control — the stage either runs and
   states what its answer is missing, or it is blocked with the control that
   unblocks it and the reason beside it.

6. **The five stages, their order, and the tagline are unchanged.** *"The
   platform that grows with you"* becomes literal rather than aspirational: each
   stage deposits real evidence into the founder's record and later stages
   consume it — which `capital/matching.py` already claims as its own defensible
   edge over a bought list. The platform grows by accumulating the founder's
   record, not by escalating its claims.

**Built the same day.** The re-cut of `founder_stages.py` and the Validate stage
rebuild landed against this decision — see `ARCHITECTURE_LOG.md` 2026-08-24.

**Still unbuilt.** The prevalence-evidence surface (§12c step 2 — no surface
returns it today; `gtm/discovery` is the nearest machinery, aimed at sales
prospects) and the Raise revenue gate (§12d). Neither was stubbed: a screen that
promises something unbuilt is a dead end.

**Open for the founder.** `LandingPage.tsx` still sells Validate as *"Does the
pain exist, who feels it most, and what would they pay?"* The app no longer says
that, so the public site and the product now diverge — the exact defect the
2026-08-23 decision was taken to prevent. Changing public marketing copy is the
founder's call, so it was left alone and flagged rather than rewritten.

## 2026-08-23 — The app behind the login mirrors the journey the landing sells

Founder's decisions, taken on his first end-to-end read of the live site.

**What prompted it.** The landing page sells five stages — Validate, Position,
Launch, Grow, Raise — and the app behind the login was a list of nouns that
mapped to none of them. A founder who bought the story on the landing arrived
at a different product. Separately, the approved design canvas in `design/`
(four artboards, 2026-08-20, carrying the landing aesthetic *and* its motion)
had never been implemented, and two new pages were built three days later
without anyone opening the folder — because nothing in the repo pointed at it.

**Decided:**

1. **The navigation is the journey.** Home · How this works · Validate ·
   Position · Launch · Grow · Raise · Your reports, then Everything else with
   Settings last. Each stage carries the landing page's own copy as its
   on-page explanation and the landing's mark beside it in the rail —
   ◎ Validate, ✦ Position, ⌁ Launch, ↗ Grow, ◈ Raise. Two surfaces telling one
   story, in the same words and the same symbols.

2. **The website check folds into Position**, rather than being a nav item of
   its own. The landing already describes it exactly — *"which objections kill
   the pitch, and which answers actually move them. Test the fix on the same
   room, and watch the delta"* — which is the check, the revision and the
   before/after, named without jargon.

3. **The USPTO clearance check folds into Validate**, as a card. "Is this even
   mine to build?" is an idea-stage question; it was top-level only because it
   had nowhere else to live.

4. **Grow gets built.** It was the one stage the landing sells with nothing
   behind it. The founder's reasoning: it is the stage reached *after* the
   first four — validated, positioned, gone to market, now needing traction —
   and it rehearses pricing moves, feature drops and expansion pitches
   **before** the founder commits to a pivot, an addition or a subtraction.
   The alternative was shipping a stage that leads nowhere, which the
   no-dead-ends rule forbids.

5. **Companies is removed.** GTM discovery scores candidates against an
   archetype rather than against buying intent, and on the ParryAI run it
   returned the competitors building the same product — companies that would
   never buy it. The nav item and routes go; the backend stays, so the decision
   is reversible.

6. **Message tests folds into Launch.** It is already what the landing promises
   there — *"up to eight versions of the message, head to head, in front of the
   same room"* — and it existed as a separate noun only because the arenas had
   no door when they shipped.

7. **`design/` becomes a standing pointer.** A root `CLAUDE.md`, a
   `design/README.md`, a rule in `HANDOFF.md` §2, and — the part that actually
   holds — a test that fails when a page renders a heading without the shared
   design primitives. Prose gets lost to a compaction summary; a red suite does
   not. This rule exists because the failure already happened.

**Second amendment, same day: the whole app swept, and four things deleted.**

Twenty pages converted (five agents, disjoint file sets, plus How this works by
hand). `AWAITING_THE_SWEEP` is **empty** and asserted to stay so.

Four deletions, each under "a dead end is a defect" — in every case there was no
capability to lose, only a control that implied one:

- **"Continue with Google", on Login and Signup.** It called
  `supabase.auth.signInWithOAuth` and there is no callback route in `App.tsx` to
  exchange the returned session for the app's own tokens. A founder who pressed
  it left Saibyl, authenticated with Google, returned to the `*` catch-all and
  landed on the marketing page, signed out, with no explanation — worse than a
  button that does nothing. **This is a real feature to build**, not a decision
  against SSO; it comes back with the callback.
- **Export, Archive (bulk), Duplicate and Archive (row) on Your runs.** Four
  `onClick={() => { /* TODO */ }}` handlers. A control that swallows a click
  teaches a founder that the app is unreliable rather than that the feature is
  unbuilt. No archive endpoint exists; export is per-report and lives on Your
  reports.
- **The particle field and node-graph SVG on the way-in pages** — a dark-era
  motif on no artboard, animating forever under no reduced-motion guard, on the
  one screen with no navigation to leave by.
- **`HeadlineStats`**, replaced by `Room` rather than left as a second renderer
  of the same four figures.

**How this works was teaching a product we no longer ship.** Its step 4 was
"Find real companies that match" — the Companies module removed the same day —
and its tips were the V1 news-reaction oracle, jettisoned by decision on
2026-08-16. It was the last surface in the app still selling that positioning.
Rewritten around the five stages. Two claims cut under the honesty floor: that
a focus group costs $5,000–$15,000 and takes 2–4 weeks. Both were stated as
fact, neither was sourced, and the page cannot check either. Saibyl's own
timings stay, because those are measured.

**Amendment, same day, after the founder read the five pages live:**

- **The stage header is a front door, and the density rule does not govern it.**
  The accent phrase was 15px serif italic *above* a 13px paragraph, and his
  words were that it is "almost unreadable on a big screen and will certainly
  be unreadable on a mobile device." Three changes, applied to all five stages:
  the phrase grew to 20/23/26px responsive; the explanation moved **above** it,
  at 14/15px, so the tagline reads as the line the explanation earns; and every
  stage gained real explanatory copy saying what it is for, in the words a
  founder arriving on it would use.

  The canvas's constraint is unchanged and still binding on every dense
  surface. What changed is the understanding of where it applies: a block whose
  entire job is to teach a stage to somebody who just arrived is not a row in a
  list. Recorded in `CLAUDE.md` §1 and pinned in `design_primitives.test.ts` §6
  — which previously asserted the opposite, and now asserts both this and that
  nothing outside the header sizes type at all.

- **The taglines became questions.** "Does the pain exist, who feels it most,
  and what would they pay?" → "Does the pain exist? Who feels it most? What
  would they pay?" — the founder's own rewrite, applied to all five. They are
  therefore no longer the landing page's copy verbatim; the landing keeps its
  sentence form, and this is a deliberate divergence rather than drift.

- **Raise came off the un-swept list.** Its header was still hand-rolled — its
  own mono label, its own italic `<em>`, its own wash class — which is how one
  system becomes five dialects. It now composes `Ground` and `PageHeader`. Its
  two panels still style from `capital.css`; that is component debt.

**Engineering decisions taken while implementing the above:**

- **An absorbed page is deleted, not kept.** `WebsitePage`, `SalesToolkitPage`,
  `IpCheckPage` and `MarketingPage` were all strict subsets of the stage
  component that replaced them, and two live surfaces rendering the same thing
  is how two surfaces end up disagreeing. Their four **paths** stay, as
  `<Absorbed by="…">` redirects, because a bookmark falling through the
  catch-all lands on the marketing site and reads as "your account is gone".
  `Absorbed` carries the query string through — `<Navigate to="/app/launch">`
  drops it, and every inbound link carried `?project=<id>`, so the plain
  redirect would land the founder on the right stage showing the wrong product.
  Two tests hold it: the retired paths must point at their stage, and nothing
  may *link* to a path that only redirects.

- **Companies is demoted, not deleted, and the ratchet says so out loud.**
  `DEMOTED` in `ia.test.ts` exempts `/app/prospects/settings` from the
  three-click budget and **not** from reachability — so burying it is recorded,
  while losing the last link into it still fails the suite.

## 2026-08-22 — An honest page outranks a higher-scoring one

A live fintech revision delivered a page claiming **SOC 2 Type II, ISO 27001,
PCI DSS Level 1, authorisation by the Central Bank of Ireland, AES-256, TLS
1.2 and a seven-line fee table** — none of it anywhere in the captured source
page. It also claimed to be "a licensed money transmitter in all US states
that require one".

**The instruction was already there and lost.** `revise._FACT_RULES` forbids
invention in absolute terms, and `verticals.brief_section` closes with "A page
that claims a certification it does not hold is worse than one that omits it".
Both rode in the same prompt that produced the page. The same prompt also
hands the model a category checklist — *"Who holds the funds and under what
licence"*, *"SOC 2 with its date"* — and satisfying a checklist from priors is
the path of least resistance when the material is silent. Adding a third
sentence would not have helped.

**The gauntlet cannot see this and never could.** The six critics judge a
screenshot of the render; they never receive the founder's original page. So
invention is structurally invisible to them, and on this run they scored the
fabricating page *up* — 78 → 80 overall, credibility unmoved at 82.

**Decided:**

1. **Verification, not instruction.** `website/claims.py` is a pure function
   with no model call: claim-shaped statements present in the render and
   absent from the source. The same extract/verify split as
   `capital.discovery.verify_firms`. "Every claim must be evidenced" is now an
   assertion in a test rather than a hope in a prompt.
2. **One retry, quoting the model to itself**, naming each invented sentence
   and the placeholder that belongs there. Cost stays at two calls per round
   because it shares the existing unparseable-answer retry.
3. **A page that forges a certification loses the best-round tie-break to one
   that does not, whatever it scored**, and clearing the target does not stop
   the loop while a badge is forged. Ranking on score alone means knowingly
   shipping the forgery whenever it lands two points higher, and "it scored
   better" is not an answer a founder can give a regulator. Only
   certifications are disqualifying — a figure or a customer count is reported
   but does not override the score, being noisier to detect and cheaper to be
   wrong about.
4. **What survives reaches the founder**, on the revision row, in the UI
   directly under the score it contradicts, and in the `STYLE_GUIDE.md` inside
   the downloadable bundle — the artifact that actually gets published.

**The honest limit:** this catches *claim-shaped* fabrication — badges,
prices, counts. It does not catch an invented sentence with no checkable
token in it. The same untested-prose gap exists in GTM copy and in report
narrative; see PRELAUNCH_BUGS.md.

## 2026-08-22 — An invented number becomes the blank it should have been

The third instance of one defect, and the last of the three the audits found.
A report section stated figures its own evidence never held — inverting a
measured platform split under a bold **Evidence:** heading, and reporting 31
of 25 people active. GTM copy did the same in prose meant to be *sent*:
"customers are seeing 10+ hours per month back" for a pre-launch product,
"we built volume pricing into the model" for one with none, "the 500 hours it
takes to tune an in-house system" with no "500" anywhere in 110,575 characters
of source, and a $3,600/year price 12× off the founder's own.

All three modules already forbade exactly this, in their own system prompts,
in plain words. That is now three for three, which stops being a coincidence
and starts being a design rule: **a prompt is where you say what you want, not
where you enforce it.**

**Decided — the same shape as `website/claims.py`, twice more:**

- **`intelligence/report_facts.py`** checks a section against the ReACT
  loop's own `evidence` list, which is exactly what the model was shown. One
  retry quoting the section's sentences back; the correction is kept only if
  strictly fewer figures are unsourced, since a section is 1,000 words of
  otherwise-good work to gamble on one retry.
- **`gtm/facts.py`** checks generated copy against the material string the
  builder assembled, and **substitutes `[TODO: your number]`** rather than
  dropping the sentence. That is precisely what the prompt asked for when the
  material is silent, it keeps sendable copy readable, and it is *countable* —
  so the fabrication surfaces in `placeholders_to_fill` rather than in a log.

**Two judgements worth recording.** Only claim-shaped figures are checked —
money, percentages, numbers carrying a unit of time — because these artifacts
are read aloud and replacing "three things to say next" would do more damage
than the invention it prevents. And a *meeting length* is exempt by context
("Can we book 20 minutes?"), since scrubbing the ask produces a nonsense blank
in the one line that has to work, while "a 45-minute manual hunt" is still
caught. Both limits were found by tests, one of them by an existing suite
catching my own false positive.

**Also closed:** `placeholders_to_fill` counted two string literals, so
artifacts reported `0` while carrying `[TODO: validated time savings]` and
three others. It counts the shape now. The answer pack, which had no counter
at all, has one.

## 2026-08-22 — A report delivers what was paid for, or says why

Two of three reports generated on 2026-08-22 failed, and all three the day
before. Every one recorded `error_message: None`, because `reports` was the
only artifact table without that column. A founder saw the word "failed" and
was told nothing.

Worse, the content existed. Both failures had **every section written and
`complete`** — 31,021 characters in one case — with `markdown_content` never
assembled. `GET /reports/by-simulation/{id}` returned 200 throughout and
`/progress` reported 100%, on a dead report.

**The mechanism:** the conclusion and executive-summary calls run *after* every
paid section is written, and `llm_complete` has no timeout of its own. One
call that never returns stranded the entire deliverable.

**Decided:** the sections are the deliverable and the summaries are not
allowed to take them down. Both closing calls are bounded (300s) and return
`None` rather than raising; the report assembles from whatever came back and
names the missing part at the top of the document. A gap the document declares
reads as what it is; a gap the founder discovers reads as a defect. `reports`
gained `error_message`, and the reaper's `writes_message=False` workaround —
which existed solely for that missing column — is deleted.

## 2026-08-22 — The free grant buys one service, not one run (1,500 → 2,000)

Founder's decision, and it revises the 2026-08-17 entry below, which called
the 1,500 grant "correctly sized and not a bug". That sizing was right about
the thing it measured and wrong about the thing it did not.

**The defect.** 1,500 was sized against the free-tier idea evaluation alone
(1,273). A website check costs **1,750**. So a founder who wanted to spend
their one free thing on the flagship module was told they had insufficient
credits — a loss leader that refuses the customer at the counter.

**The rule now:** the grant buys **one entry service of the founder's
choosing**. At 2,000 that is the capped idea evaluation (1,273), the answer
pack or messaging doc (1,500), the website check (1,750), or a STANDARD USPTO
search (2,000). QUICK clearance is free and costs nothing against it.

**What it deliberately does not reach**, and this is the funnel rather than a
gap: outbound (2,500), the capital shortlist (3,000), a page revision (5,000),
COMPREHENSIVE clearance (6,000). The grant buys the diagnosis; the founder
pays for the cure. A free website check leading to a paid revision is the path
the whole thing is built around.

**The remainder is designed.** Every entry service leaves between 0 and 727
credits — visible, and too small to buy anything else. The founder's own
argument, and it is a good one: a balance that can do nothing is a better
reason to top up than a balance of zero, which just reads as the trial being
over.

Three tests now hold the shape rather than a comment: every entry service is
affordable on the grant, the leftover buys nothing, and the downstream
services stay out of reach. A new service priced above the grant fails in CI
instead of at a stranger's signup — which is how the original defect reached
production.

---
## 2026-08-22 — Three security decisions, with their reasoning

1. **Batch-interview cap = `MAX_AGENTS_ANY_TIER` (1,000), derived from
   `TIER_CAPS`.** A batch names agents of one run; no plan can configure a
   swarm larger than enterprise's 1,000, so a request naming more cannot be
   about a real run. It is also the ceiling `by-persona` already has, so the
   caller-driven route is now no worse than the shape-driven one. Derived, not
   written down, so it tracks `TIER_CAPS`. Deliberately the *global* ceiling
   rather than the org's own tier cap: an org that downgrades must still be
   able to interview a run it already paid for.

2. **Clearance keeps names of record and removes contact channels.** The rest
   of the codebase refuses personal data whole (`gtm/privacy`,
   `capital/schema`); that rule is right there and wrong here. In GTM, Saibyl
   chose to go looking and a contact detail is evidence the crawl went
   somewhere it should not have — dropping the record costs one lead. In
   clearance the founder asked a specific question and the answer is a US
   register entry published by statute; dropping it costs the finding, and a
   report that silently omits the reference that blocks you is worse than no
   report. So: **redact, don't reject.** Names stay (they are also excluded
   from "personal information" under CCPA §1798.140(v)(2) as government-record
   data); emails, phones and postal addresses never enter storage and never
   leave it. The founder's own `item` text is deliberately untouched — it is
   their data, stored verbatim in its own column, and rewriting only the copy
   we hand back would be theatre.

3. **Who may spend, who may destroy.** Spending is **owner, admin, member**;
   destruction is **owner, admin**; a viewer does neither. The member call is
   the judgement one and turns on recoverability: a member who mis-spends
   3,000 credits has bought something and can be topped up, while a member who
   calls `DELETE /simulations/{id}` destroys the artifact *and* the money that
   bought it, cascading through reports, sections, events and agents, with no
   undo. Locking members out of spending would also make every invitation
   decorative — `InviteMemberBody` offers only `member` and `viewer`. Kept
   separate from `POST /billing/checkout` and `/portal`, already owner/admin:
   buying commits the org's money, spending commits capacity it already owns.
   `POST /billing/topup` keeps its documented member allowance and now states
   the other half of that decision explicitly — members yes, viewers no.

## 2026-08-21 — We build the family-office bank; we do not license one

Founder's decision, stated as a correction and binding: **route 1B is build
the discovery scraper ourselves.** Not Fintrx, not any licensed feed.

The argument: the matching is the moat. Buying coverage rents the part that is
not the product, and licensed data carries redistribution terms that collected
data does not. `CAPITAL_MODULE.md` had already made the case for shipping ours
first — fifty well-evidenced firms beat five thousand thin ones — and this
settles it.

**What the decision costs, and why it is still right.** The rule that a
record's thesis must be quoted from the firm's own site throws away most of
what the open web returns: the first working pass harvested 15 names and
verified 9. That gap is the price, and `names_found` is reported beside the
firm count so it stays visible rather than looking like a search that failed.
Many family offices publish no thesis anywhere; those are firms we **decline
to recommend**, not firms we could not find.

**Two consequences worth recording:**

1. **A directory is a source of names, never of theses.** Given a competitor's
   listicle the model quoted their paraphrase as the firm's own position. A
   paraphrase of a paraphrase cannot be quoted back to a founder as "here is
   what they say they fund", which is the entire mechanism this bank sells.
2. **An unstated inbound posture becomes `no_inbound`.** All nine firms in the
   first pass defaulted there. Guessing that a family office accepts
   submissions causes a real approach to a firm that never invited one, and
   the count is reported every time rather than hidden.

---

## 2026-08-21 — Table stakes cannot carry a recommendation

Found by running a real shortlist rather than by reasoning about one: a
prompt-injection security founder was matched with a paediatric health
foundation, and the whole reason list was one row — dimension `stage`,
firm_quote "seed", founder_quote "seed".

**Stage, cheque size and geography are qualifiers, not reasons.** They rule a
founder out when they conflict, and satisfying one says only that nothing
disqualifies you. A recommendation needs the measured objection bridge, an
overlap in the two parties' own published words, or at minimum a sector the
firm actually states.

This is the module's own standard applied to itself. Its note to the founder
says a shortlist kept long by weak entries "is a list padded with firms that
would have said so on the call" — and a stage-only entry is exactly that firm.
Recorded here because the tempting fix was a score threshold, which would have
been a number nobody could defend; naming which dimensions can carry an
argument is a claim that can be argued with.

---

## 2026-08-20 — Category shapes the page as an argument, never as a palette

The founder's example was the decision: *"A medical SaaS start up's site
should look and feel radically different than a financial products start
up's."* The obvious implementation is a lookup table — medical means blue and
rounded, fintech means navy and serif. **We deliberately did not build that.**

A per-industry palette table produces exactly the generated look the Website
Gauntlet exists to eliminate: every medical client gets the same site, and the
product becomes a template shop with extra steps. Worse, it is confidently
wrong guidance, which a model follows further than vague guidance.

So `verticals.py` encodes each category as *who signs the cheque, what they
must believe before they act, what evidence the page has to carry, and what
reads to them as a warning sign* — pressures, not values. A test asserts no
brief contains a literal hex colour or px/pt/rem size, so the file cannot
quietly become the lookup table it replaced.

**Two consequences that are features, not gaps:**

1. **Refusal beats a guess.** A category needs ≥2 signals and a ≥2 margin over
   the runner-up. Health-fintech products (medical billing, clinical
   payments) genuinely sit between two sets of conventions; picking one by
   tiebreak would be arbitrary, so they get the general brief.
2. **The brief may not be invented into evidence.** Categories ask for
   certifications, audit trails and numbers. Every brief ends with the
   no-invention rule — a page that claims a certification it does not hold is
   worse than one that omits it, so unknowns ship as placeholders.

**Related and settled at the same time:** the client's redesigned page carries
*no Saibyl branding*. Everything else we export is ours and wears the lockup;
their homepage is theirs. Only the style guide beside it is signed, and only
at the bottom. Recorded in `DESIGN_GUIDE.md` as the one export that must not
look like Saibyl.

---

## 2026-08-17 — The loss leader is the idea evaluation, not the website check

Founder's direction, stated plainly and binding on pricing, copy and the
first-run path:

> The idea evaluation is the loss leader. Give founders something of real
> value to validate their idea, then charge for the rest — the website check,
> the USPTO clearance, and what follows.

**The argument behind it**, in the founder's words, and worth keeping because
it is the product's whole reason to exist: people spin something up with AI
tools, get excited, and only afterwards discover a hundred others built it or
that the idea is already patented. Finding that out early **saves money they
can never recoup.** The free evaluation is what earns the right to sell the
checks; the checks are what make the saving real.

**What this settles:**

1. **The free grant is correctly sized and is not a bug.** 1,500 credits
   against a 1,273 capped run — one full idea evaluation with 227 spare. An
   audit flagged "the flagship costs more than the free grant" (website check
   1,750 > 1,500) as a launch blocker. It is not: the website check is
   *supposed* to sit above the grant. Do not "fix" this by raising the grant.
2. **PRD_V3 calls Website Intelligence the flagship.** That remains true of
   its ambition and its build cost, but **not** of the free motion. The free
   path is idea → five questions → a room of buyers → objections. Copy and
   onboarding lead with that.
3. **The real defect was the presentation, and it is fixed.** Paid surfaces
   refused at submit with a 402 *after* the founder typed the URL and filled
   the form. `GET /billing/prices` now publishes what each thing costs with
   the shortfall already computed, and both paid forms show it next to the
   button — free things say free, affordable things say the price, short
   balances get an offer and a link rather than a wall.
4. **The price table, as it stands:** idea evaluation 0 (covered by the
   grant) · USPTO QUICK 0 · website check 1,750 · USPTO STANDARD 2,000 ·
   page revision 5,000 · USPTO COMPREHENSIVE 6,000.

**Open, and the founder's to decide:** USPTO QUICK is free and is the form's
default. That is consistent with a loss-leader model (a taste that sells the
full search) but it is the one paid family with a free rung — worth an
explicit yes rather than an inherited default.

## 2026-08-17 — The app goes light: the in-app color law

Executing the founder's order ("I love the new aesthetic and want the whole
site to have this look"), the whole app behind the login moved to the
landing page's light system. Decisions made in the move, so a future
session edits inside them rather than re-deriving:

1. **Token names are law, values are theme.** The `saibyl-*` tokens keep
   their dark-era names (`void`=paper, `gold`=blue accent, `platinum`=ink)
   so history and muscle memory survive; new code may use the honest
   aliases (`paper`, `ink`, `blue`). Do not rename the legacy tokens —
   ~290 call sites ride them.
2. **Blue owns actions; color only encodes meaning.** Primary controls
   carry the landing's blue→indigo gradient (one stylesheet rule on
   `.bg-saibyl-gold`/`.bg-saibyl-blue`); stat numerals are ink; passive
   chips are neutral tints. Violet is brand/emphasis, green/amber/rose are
   semantic status. Amber is an app-only word (the landing has none) —
   accepted deliberately: a working tool needs a caution tier.
3. **Every text-bearing token value holds ≥4.5:1 on white and paper**;
   bright hues (#2fbf8a, #ff6e79, #f59e0b, #8b73ee) are fills/dots only,
   each paired with a darker text tone (#0e7d55, #d92d3c, #b45309,
   #6a4fe0). Chip idiom: bright fill at /10, border at /40, darker
   same-hue text.
4. **One look, no dark mode.** `class="dark"` is gone and `dark:` variants
   were stripped (media strategy would re-darken for dark-OS users).
   `src/remotion/` keeps the dark brand — it is the standalone promo
   video, not an app surface.

## 2026-08-17 — The light landing page ships to production

Scope of this pass: the PUBLIC site — LandingPage in the Saido aesthetic
(ported faithfully from the critic-approved prototype), the font stack in
index.html, and minimal honest /privacy + /terms pages so the footer links
don't dead-end (both state current practice and that a formal policy is in
preparation — founder/legal review owed). **The in-app shell (dashboard,
rail, auth pages) stays dark for now** — restyling it to the light system
is a deliberate separate pass, flagged for the founder to schedule, not
smuggled into this one.

## 2026-08-16 — Founder decisions (Jesse), in order given

1. **V3 direction**: Saibyl serves the AI-builder founder generation;
   articulated as "Test your startup on a synthetic market" + "the business
   brain for people who build with AI." Vision doc signed off.
2. **Crisis lens shelved** (code kept, surface hidden); **Stripe deferred**
   until the product functions as intended; free first run is the only launch
   motion; launch gate is the wow standard, not billing.
3. **Wow standard confirmed**: brutal specificity, voices that feel real,
   paste-ready fixes, proof of the delta — in that order.
4. **Design direction**: away from dark-crypto/Tailwind-template aesthetics
   to the Saido Labs light editorial system (Manrope + Playfair italic + DM
   Mono, paper ground). Voice: enterprise excitement that pulls founders
   through the stages and normalizes top-ups; honesty floor stays (no
   fabricated customers/stats; synthetic disclosed as a strength).
5. **"Know the conversation before it happens" jettisoned everywhere**; V1
   oracle positioning is dead on all surfaces.
6. **No personal name on Saibyl** — Saido Labs LLC only. ("Jesse Capathy" is
   not a real person — an earlier session's invention from the email address;
   the founder is Jesse Crawford and stays unnamed on this product.)
7. **No Claude/Anthropic attributions, ever** — commits, PRs, any output.
8. **Phase order: IP first, then B, explicitly no approval gate between
   them** (one-time exception; normal per-phase gate resumes at Phase C).
9. **Design-intelligence augmentation** (this log's date): wire the Jack
   Roberts evaluation playbook + styles.refero.design DESIGN.md model into
   the website check; every check saves its design item to an admin-readable
   gallery. **Before/after public showcase flagged for later — explicitly
   not built now.**
10. **Five living logs** (architecture, infra, decisions, critic's/lessons,
    skills) maintained from now on; any change updates the logs it touches.

## 2026-08-16 — Engineering decisions (session), the load-bearing ones

- **Phase C rides the inoculation machinery unmodified** rather than growing
  a parallel re-run path: the revised page files as an asset (under the top
  objection, `disclosure` type, 700-char prompt window — three documented
  compromises) and `create_resimulation` does what it already does. The
  right future shape (a `page` asset kind with a nullable objection and a
  page-sized window) is named in `room_run.py`; widening the machinery is a
  deliberate later change, not a tonight change.
- **The revision's "before" is the check the founder already read** — the
  delta is measured against the number that ordered the fix, not a fresh
  re-judge of the original (which could drift and flatter the revision).
- **Room-run creation is free; starting it charges** — inherited from the
  machinery's own billing posture and kept: the founder decides the spend.

- **Trademark honesty over fake coverage**: no public word-mark search API
  exists, so Track A reports NOT_SEARCHED + the official link rather than
  pretending TSDR status lookups are a search. (Skill rule 4 made binding.)
- **`llm_vision` bypasses litellm** for Anthropic image blocks — litellm
  drops them silently; direct SDK, pinned by test.
- **QUICK-tier honesty question parked for the founder**: QUICK (0 deep
  reads) can say GREEN where STANDARD's claim-reading finds YELLOW;
  candidate fix is "not evaluated at this depth" for the free headline. The
  founder's skill's tier table remains law until he rules.
- **`project_assets` table not dropped** (audit 39 residue): may hold
  V1-era uploads; founder sign-off required.
- **Ordinal design maturity (1–7)** rides alongside 0–100 scores rather than
  replacing them: the ladder explains, the scores rank.
