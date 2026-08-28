# Architecture Log

Standing rule (founder directive, 2026-08-16): whenever the system's shape
changes — a new package, a new pipeline, a moved boundary, a new external
dependency — the change lands here, dated, with the why. Newest entries at the
top. `ARCHITECTURE_V2.md` remains the deep design document; this is the
running delta record.

---

## 2026-08-27 — Account recovery exists

`POST /auth/forgot-password` and `POST /auth/reset-password` in
`api/auth.py`, and `pages/ForgotPasswordPage.tsx` / `pages/ResetPasswordPage.tsx`
on `/forgot-password` and `/reset-password`.

**The shape that changed.** There was no recovery path. Not a broken one —
none: no route, no email, no token. `LoginPage` offered "Forgot password?" as a
`mailto:info@saidolabs.com`, Settings → Account said password changes were
handled by email, and both were accurate descriptions of a product where being
locked out meant waiting on somebody reading a mailbox. Found on 2026-08-27,
alongside the signup 409 that was telling people the same thing.

No new dependency: GoTrue already mints and mails recovery tokens. What was
missing was asking it to, pointing the link at our own page rather than
Supabase's default, and having a page at the other end.

**Three decisions worth inheriting**, all in `DECISIONS_LOG.md` in full:

- The reply to a reset request never varies with whether the address has an
  account — including when GoTrue itself is down. A route that answers
  differently for real addresses is an account-existence oracle.
- The account acted on is named by the **verified token** and by nothing else.
  `ResetPasswordRequest` carries the token and the new password, and a test
  asserts those are the only two fields it will ever carry.
- A completed reset revokes every other session for that user. Somebody
  resetting a password usually believes somebody else has it.

**One thing outside the repo.** `redirect_to` is only honoured for URLs on the
Supabase project's Redirect URL allow-list; `https://saibyl.com/reset-password`
has to be on it or GoTrue silently falls back to SITE_URL. Noted in
`INFRA_LOG.md`. The Render side needs nothing — the existing `/*` rewrite
already serves both routes.

---

## 2026-08-25 — The website check gets a counted half

`services/website/measured.py`, wired into `run_critic_gauntlet` as a seventh
dimension keyed `measured` and labelled **counted** to the founder.

**The shape that changed.** The gauntlet was six vision reviewers and nothing
else, so every finding it produced was an opinion. Some of what makes a page
read as assembled rather than designed is not an opinion — it is arithmetic:
how many corner radii, how many typefaces, whether there is exactly one `<h1>`,
how dense the copy is with em-dashes. Arithmetic run by a vision model can be
wrong, cannot be reproduced and costs money each time it is asked.

Everything in the new module is computed from what the capture already
measured, `dom_text` and `style_census`, with no model call, no network and no
randomness. It is also the only part of the website check with **zero
correlation exposure** — the objection that has dominated every dogfood run is
fair against a reaction and irrelevant against a count, which makes this the
website check's equivalent of the prior-art search.

**Live-checked, not just unit-tested.** Run against Saibyl's own landing page it
returns 33 em-dashes in 2,109 words, 15.6 per 1,000 against a limit of 6.

**Two design decisions worth inheriting:**

- **It returns `None` when nothing could be measured.** An empty census on a
  page with almost no text used to score 100 and lift the gauntlet's mean, which
  rewards a page for having defeated the census. This codebase already names the
  inverse — a zero meaning "we did not look" — as the defect it produces most
  often; a hundred meaning the same thing is that bug with the sign flipped.
  Caught by two existing gauntlet tests rather than by review.
- **Counts that hit the census cap are reported as "at least N".** `_top()` in
  `capture` keeps ten rows, so forty radii and ten radii are indistinguishable
  downstream. Stating the exact number would be reporting a figure the capture
  never established.

**⚠ Overall scores from before this date are not comparable with scores after
it.** `overall_score` is a mean across dimensions and there are now seven, so a
stored 77 from a six-dimension run is a different quantity. The
`CRITICS_LOG` 2026-08-22 figures (77 → 77, credibility 78 → 72) are
six-dimension numbers. **Deltas inside one revision run are unaffected** — the
before and after are both measured the same way, and the delta is what
`revise.py` reads.

**The census was then extended, same day, to make two of those measurable.**
`_STYLE_CENSUS_JS` now also reports `structure.sections`, a `labels` tally
(small, wide-tracked, upper-case, leaf-level text, and the subset of it sitting
immediately before a heading), and `actions` — the label and destination *path*
of every button and every anchor painted like one. Both additions reuse the
computed style and rect already read for each element, so they add no layout
work to what the file itself calls the most expensive step in a capture.

Two decisions inside that:

- **Actions group by destination, never by apparent intent.** Two buttons
  pointing at one path with different words are demonstrably the same ask.
  Deciding that "Get started" and "Try free" mean the same thing would be a
  measurement guessing, which is the vision reviewers' job.
- **Path only, never the full URL.** A query string can carry a token or an
  email, and the census rides inside prompts.

**Verified by execution, not only by fixtures.** Playwright is not installed
locally and the capture tests use a fake runtime, so the new script had never
run. It was extracted and executed under Node against a stub DOM: it returns the
section count, detects an eyebrow *and* that it sits above a heading, captures
the painted calls to action with their paths, and correctly excludes an
unpainted body link. Feeding that output through `_normalize_census` into
`measure_page` reproduces, unprompted, the same three defects a manual audit of
the landing page had found by hand. This matters because `capture` swallows a
census failure by design — a syntax error in that script would have made the
counted dimension disappear in production in silence.

**Still named as not-yet-measurable:** whether one layout repeats down the page
(no honest DOM signature for "this section looks like the last one") and whether
navigation wraps at desktop (the census records no per-element geometry).

## 2026-08-24 — Validate runs retrieval-first: the stage registry re-cut and the page reordered

Implements PRD_V3 §12c. The shape that moved is which instrument answers the
first question a founder asks.

**`engine/founder_stages.py`.** `concept_validation`'s question changes from
*"Does this pain exist, who feels it most, and would they pay?"* to **"Is it
just me — and has anyone already built it?"** Two of its five
`report_questions` came out because they were empirical questions put to a
room: *"Do agents recognise this pain unprompted?"* (a synthetic proxy for
real-world prevalence) and *"Is there stated willingness to pay?"* (contradicted
by this stage's own `cannot_conclude` in the same object). Three limits were
added and they are the point of the change — the report now states out loud
that a run cannot establish whether the pain is real, how many people have it,
or whether somebody already built it.

The module docstring carries the rule the registry is now governed by:
**empirical questions go to retrieval, reaction questions go to the room**, and
a room cannot answer an empirical one at any sample size. Its old rationale —
"five stages are five purchase occasions" — was replaced per §12e; retention
comes from the record accumulating, not from the stage count.

**Blast radius was small because the frontend does not copy the registry.**
`lib/founder.ts` fetches `/api/simulations/founder-stages`, so there was no
second copy to drift. Backend: 2020 passed, ruff clean.

**`pages/ValidatePage.tsx`.** The clearance chapter moved from last to first and
the room chapter follows it; the hero's one gradient action is now the check
rather than the room, which also makes it the first thing on the page that works
with no product created. `ValidateSteps`'s three cards were titled with the
three questions the stage was sold on — all three asserted facts about the
market — and are now titled with what each step does.

**Deliberately not stubbed:** §12c's middle step (real evidence that other
people have this pain) has no surface, so the page has no chapter for it. A
chapter promising something unbuilt is a dead end, and a dead end is a defect.
`gtm/discovery` is the nearest machinery when it gets built — re-point its query
compiler rather than starting over.

**Ratchets added** (`test_icp_synthesis.py`): `concept_validation`'s report
questions are checked against a list of empirical markers, its three new limits
are pinned, and a registry-wide test fails any stage that asks what a buyer
would pay while also declaring it cannot conclude a price.

**Known divergence, not fixed here.** `LandingPage.tsx` still sells Validate with
the old question. Public marketing copy is the founder's call, and the app and
the landing are now telling two different stories — which the 2026-08-23
decision names as the defect to avoid.

## 2026-08-23 — The longform shape goes to all eleven nav pages

Four agents, disjoint file sets, hero copy written centrally so eleven pages
speak in one voice. `ia.test.ts` §8 derives the obligation from `AppLayout`'s own
nav arrays, so a page added to the nav later inherits it rather than relying on
somebody remembering.

**Three bugs the rollout surfaced, all mine, all fixed:**

- **`useReveal` captured its targets once.** Correct for the static landing page
  and for `GuidePage`; wrong for every page that renders a list after a fetch —
  those nodes would have mounted with nothing watching them and stayed at
  `opacity: 0` **permanently**, on a page reporting no error. Now re-queried, with
  a `MutationObserver` tracking arrivals and a latching fallback so anything
  appearing after the 2.5s give-up is revealed rather than handed to a dead
  observer. Two agents found this independently.

- **`TOP_LEVEL_HEADING` did not know about `<Hero>`.** The same hole that was
  closed for `PageHeader` three hours earlier reopened the moment a second
  heading primitive existed: `GuidePage` silently left the design scan when it
  converted, and by the time the agents reported, four pages were unchecked. The
  fix was applied to one primitive rather than to the concept.

- **A search matching nothing locked the founder out of the search box.** Server-
  side filtering (added earlier the same day) makes a non-matching search return
  `total = 0`, which took the empty-workspace branch and replaced the entire
  toolbar — including the input just typed into. No way back but a reload. An
  empty *filter* and an empty *workspace* now render differently, and the filter
  case carries a "Clear the filters" control. The chip counts and the summary
  line were mixing page-scope and workspace-scope numbers in the same sentence;
  both now state only what they can actually see.

- Also: `EmptyState`'s action was the last flat-blue primary in the app —
  missed when `StagePrimitives` was converted, and the one that mattered most,
  since on an empty screen it is the only button there is.

**One rule qualified rather than enforced:** "one gradient action per screen"
was written for a page you see at once. The landing page carries nine, because a
reader a thousand pixels down should not scroll back. One primary per *viewport*
now, with the same ask allowed at the foot.

## 2026-08-23 — Every page behind the login is a landing page

The founder read the swept app against the public site: **"very sterile,
mechanical, and looks AI-generated."** The instruction was to give each nav page
the landing page's own shape — hero, large type, then scroll, with content
fading in as the reader reaches it. `How this works` is the built example and
the pattern for the rest.

- **New in `components/design/`:** `Longform` (the measure, and it runs the
  reveal observer over its own subtree), `Hero` (eyebrow, `clamp(3rem, 5.9vw,
  5.5rem)` heading with one Playfair phrase, lead, actions), `Chapter` (kicker,
  `clamp(2.2rem, 4.2vw, 4rem)` title with an `<em>` accent, copy) and `Reveal`.

- **`useReveal` is one implementation, and `LandingPage` now calls it too.** It
  was ~45 lines inside that page — observer, reduced-motion branch, and the
  2.5s post-load fallback that stops a full-page capture photographing a blank
  page (`CRITICS_LOG` 2026-08-16). A second copy behind the login is precisely
  the drift that produced this work, so there is one.

- **Every value is copied from `landing.css`, and §7 of
  `design_primitives.test.ts` asserts it property by property.** Thirteen
  pairings — width, hero padding, both heading ramps, both leads, the reveal's
  transition and transform. A hero size invented here would be a second brand
  inside a month, which is the risk this grant carries.

- **Not `.v3land` itself**, though that was the tempting shortcut. That scope
  carries `a { color: inherit }`, which outranks a Tailwind text colour on an
  element selector and would have turned every link inside an app component the
  colour of its body text. The values travel; the cascade does not.

- **`.sb-hero` was already taken** — by the gradient panel added earlier the
  same day — so that one is now `.sb-tinted`. Two different things under one
  class name is how a stylesheet starts lying.

- **Two rules in the density section were rewritten rather than deleted.**
  `design.css` could previously name no `font-size` and no `padding` at all;
  both now enumerate the exact selectors allowed to, so the page frame may size
  and space itself while padding a card from the stylesheet — the back door
  around the no-padding rule — still fails.

## 2026-08-23 — Four defects the sweep surfaced, fixed

Found by the agents restyling these pages; each is a claim the product made and
could not keep.

- **`GET /simulations` now filters.** `search` and `status` are new query
  parameters, applied in the query that also counts. They were applied in the
  browser, to whichever twenty rows the page held, while the pager reported the
  server's count of everything — so searching for a run on page 2 answered
  "Nothing matches what you have filtered to". `status=complete` matches both
  `complete` and `completed`, because the column holds both and neither was
  backfilled; `search` escapes `%` and `_` so a run named `Q3_pricing` does not
  also match `Q3-pricing`. Sorting stays page-local and the code says so.

  **A latent hazard came with it.** FastAPI substitutes a declared default on a
  real request; a *direct call* does not, and this module is tested by calling
  its endpoints directly — so an omitted parameter arrives as the `Query(...)`
  object, which is truthy. `project_id` had carried that since it was added and
  never fired because every caller passed it. All three optional parameters are
  now normalised once at the top of the function, so the next one added
  inherits the fix rather than the bug. Four tests, each mutation-checked.

- **`ProjectDetailPage` no longer empties its file list on a failed poll.** It
  was `.catch(() => setDocuments([]))` under a comment arguing `documentsLoaded`
  stays false — true on the first load only. After one success the flag is
  permanently true and the page polls every three seconds, so a single dropped
  poll rendered "Nothing uploaded yet" over files that exist. The last good list
  is kept and the failure is reported.

- **`SimulationDetailPage` stopped leaking its run timers.** A 4s poll, a 5m
  stop-timer and a 60×3s prepare loop were all local to `handleRunNow` with no
  unmount cleanup: leaving the page mid-run left an interval hitting the API for
  the rest of the session, calling `setSim` on an unmounted component each time.

- **The timezone picker is gone rather than plumbed.** `POST /simulations` never
  sent it, `CreateSimulationBody` has no such field, and the only backend reader
  of a run's timezone is `json_exporter` — which therefore always emitted the
  column default. Nothing in the swarm has a concept of time of day, so wiring
  it would have made the export truthful and left the *control* just as false.
  The column and the exporter line stay; a timezone-aware run is a feature.

## 2026-08-23 — The theme flipped in name only, and the app-wide sweep off it

The founder's word for the restyled app was **"sterile"**, and the cause was
mechanical rather than aesthetic. Two findings, both systemic.

**1. `canvas.json`'s annotations are a change list, not the specification.**
The text reads *"The four changes, applied everywhere"* — the delta between the
artboards and what shipped on 2026-08-20. `CLAUDE.md` had called it "the design
law", so every page built under that sentence carried exactly four things — a
washed ground, a card shadow, a dotted eyebrow, a serif phrase — applied to
flat white cards. The **artboards** are the specification, and they carry eight
gradients used structurally, layered depth with inset highlights, radii scaled
per element (11–36px), colour that carries state, hover lift, and continuous
motion alongside entrance motion. `CLAUDE.md` §1 now says so, and
`design_primitives.test.ts` asserts each gradient exists in `design/*.dc.html`
before it is allowed in `design.css` — so the system cannot invent one.

New in `components/design/`: **`Action`** (the gradient control with its blue
glow, plus a white `quiet` variant), **`Notice`** (violet blocked / amber thin /
cyan live), inset highlights on `.sb-stage` and `.sb-meaning`, and a class for a
panel with a ground of its own — added as `.sb-hero`, renamed `.sb-tinted` later
the same day when the longform work claimed that name for the page's opening. `Card` and `Action` are polymorphic via
`as` and now forward arbitrary props — `Card` could previously be told to render
as a `Link` and then had no way to be given the destination.

**2. Saibyl was dark once, and the token names never followed the theme.**
`tailwind.config.js` kept `void`, `white`, `platinum` and `gold` alive and
remapped their values (`void → paper`, `white/platinum → ink`, `gold → the blue
accent`). That was correct for the flip and is exactly how the problem hid:
**246 legacy aliases across 25 files** kept resolving to sensible light values,
so pages written for the dark theme rendered as ink on paper while never having
been *designed* as ink on paper. `bg-saibyl-void` on a page root actively
painted a flat panel over the radial wash `<body>` carries — canvas rule 1,
switched off, on Home and on Your reports.

- The aliases **stay** in the token file. Deleting them would turn every one a
  sweep missed into a class resolving to nothing, which fails invisibly.
  `ia.test.ts` §7 bans the *usage* instead, and asserts the aliases still exist
  so nobody "fixes" it the wrong way round.
- `'blue-hover'` is new. `gold-hover` existed and `blue-hover` did not, so the
  rename would have silently dropped the hover state on every button that had
  one.
- `StagePrimitives`' three buttons and `Guarded` now wear `sb-action`, which is
  why one edit moved the primary control on every stage page in the app.
- `Missing`'s `degrading` tone was rendering **wrong**: its colour was
  `saibyl-gold`, so a caution about a thinner answer had been rendering in the
  same blue as every ordinary link since the theme flipped. It is amber now,
  via `noticeSurface('thin')`.

**Two ratchets that had holes.** `ia.test.ts` §6 matched pages by `<h1>`, but
`PageHeader` renders the `<h1>` itself — so a converted page dropped out of the
scan entirely and left by the same door as a page with no heading. It matches
`<PageHeader>` too now. And §3's no-grey-button rule scanned `railFiles()` only;
widened to all source, it immediately found three live grey buttons in
`founder/` and `marketing/`, each greyed by a precondition with no reason beside
it. `disabled={busy}` stays allowed and is distinguished by name — a
double-submit guard is not a capability block.

## 2026-08-23 — The app behind the login becomes the journey, and gets a design layer

Front-end only. No endpoint, table or service changed; every module kept its
API and its behaviour, and what moved was where a founder finds it.

- **`components/design/` is new, and is the shared design layer** the four
  landing-page rules are expressed in once instead of per page: `Ground`
  (radial washes), `Card(carries='stage'|'meaning'|'density')`, `Eyebrow` (the
  dotted mono label), `PageHeader` (which owns the one Playfair-italic phrase
  per heading), and `Deal`/`Rise` for the deal-then-arrive motion. `Card`
  deliberately paints no padding — a primitive that sets its own spacing is a
  primitive every caller fights.

  The layer exists because prose pointing at `design/` had already failed:
  the canvas was approved 2026-08-20 and two new pages were built three days
  later without it. `test/ia.test.ts` §6 is the part that holds — a page
  rendering its own `<h1>` without composing these primitives fails the suite,
  and `AWAITING_THE_SWEEP` is asserted to match the tree **exactly in both
  directions**, so the debt list can shrink but never quietly grow.

- **Five stage pages, composed from modules that already existed.**
  `ValidatePage`, `PositionPage`, `LaunchPage`, `GrowPage` and `CapitalPage`
  (relabelled Raise) are the nav. Each carries the landing page's own copy and
  its mark — ◎ ✦ ⌁ ↗ ◈. `GrowPage` adds no backend at all: it composes runs,
  archetypes and the room the other stages already produce.

- **`components/room/` replaces `analysis/HeadlineStats`** on the report page.
  Same two props (`headline`, `quality`), same four measured stats, drawn as
  the room the landing page's hero promises rather than as a table of tiles.
  `model.ts` is pure and holds every number and label; `Room.tsx` holds only
  the animation schedule, so there is nowhere for a plausible-looking default
  to enter. `HeadlineStats` is deleted rather than left as a second renderer of
  the same figures.

- **Four routes became redirects, and their pages were deleted.**
  `/app/ip-check`, `/app/website`, `/app/sales`, `/app/marketing` now render
  `<Absorbed by="…">`, which carries the query string through — the inbound
  links all passed `?project=<id>`, and a plain `<Navigate to="…">` drops it.
  `LaunchPage` reads `?product=` and legacy `?project=` so those deep links
  still select the right product.

## 2026-08-22 — A verification stage between the generator and the founder

- **`services/website/claims.py`** is new: `unsupported_claims(page_text,
  html)` returns claim-shaped statements present in a generated page and
  absent from the source page, plus `claim_complaint(claims)` for the retry.
  Pure — no model call, no network — which is the entire point. It is the
  third instance of the extract/verify split (`gtm.extraction`,
  `capital.discovery.verify_firms`): the model writes, and a function that
  cannot hallucinate decides whether what it wrote is evidenced.

  Three families, ordered by what a false one costs: `certification` (a named
  standard, regulator, licence or audit regime), `figure` (money, percentages),
  `scale` (customer counts). Certifications are matched by a shared regex
  vocabulary applied to *both* texts, so a badge the founder already claims is
  never reported; figures and counts are compared as normalised keys, so a
  source that says "$1,200" covers a page that says "$ 1,200.00".

- **The boundary it creates.** `revise._generate_html` now returns
  `(html, claims)` and the loop carries claims per round;
  `RevisionResult.unsupported_claims` is the new public field. Round selection
  moved from "highest score" to `_is_better` — fewest forged certifications
  first, then score.

- **Import direction is deliberate:** `claims` imports `visible_copy` from
  `style_guide`, so `style_guide` renders its founder-facing section from
  plain dicts rather than importing `claims` back. The bundle endpoint passes
  the stored rows straight through.

- **A new surface for it in three places** — `page_revisions.unsupported_claims`
  (jsonb), the `ClaimsWarning` block in `SiteRevision.tsx` sitting directly
  under the score, and a "Claims to verify before you publish" section placed
  above everything else in `STYLE_GUIDE.md`.

## 2026-08-22 — The same verification stage, now on report sections

- **`services/intelligence/report_facts.py`** is new and mirrors
  `website/claims.py`: `unsourced_figures(evidence, answer)` plus
  `figure_complaint(figures)`, pure, no model call. The contract it checks is
  unusually clean — a section is written by a ReACT loop whose `evidence` list
  holds the seeded measured findings and every tool observation returned to
  it, so that string is *exactly* what the model saw, truncation included. A
  figure in the answer and not in the evidence is one the model supplied.

- **Three shapes only** — decimals, percentages, "N of M" counts. Bare
  integers are ignored deliberately (rounds, years, list positions, archetype
  counts), and all four live fabrications are caught by the three.

- **Matching is by rounding, not equality.** A stated `-0.47` is supported by
  a measured `-0.4653`; `81%` by `80.56`. Percentages additionally match a
  proportion, so `80.56%` is supported by `0.8056`.

- **Percentages check against shares only**, not against every number —
  `sourced_shares()` reads values written with `%` or held by a field named
  `*_pct|percent|rate|ratio|share`. Without that narrowing a run of 25 agents
  licenses "25%", which is exactly how one real fabrication passed. When the
  evidence holds no share at all, percentage checking is skipped rather than
  guessed.

- **`_figure_checked` wraps all three answer paths** of `_run_react_loop`
  (clean answer, format-violating answer, forced answer). One retry carrying
  the complaint and the evidence; the correction is accepted only if it has
  *strictly* fewer unsourced figures, otherwise the original stands.

## 2026-08-22 — The report's closing calls stop being able to kill it

- **`report_agent._closing_call`** wraps the conclusion and executive-summary
  generations: bounded at 300s (`llm_complete` has no timeout of its own) and
  returning `None` instead of raising. Assembly then builds from whatever came
  back and declares what is missing at the top of the document.
  The failure mode this removes: both calls run *after* every paid section is
  written, so one wedged call stranded the whole deliverable with
  `markdown_content` empty.

- **`reports` gains `error_message`**, making it the last artifact table to
  carry one. `StuckRule.writes_message` — a hand-maintained boolean that
  existed only because this column was missing — is deleted; the reaper's
  failed-update counter is the correct guard for a schema fact.

## 2026-08-22 — Two new boundaries: role gates, and clearance personal data

- **`core/auth.py` gains two dependencies**, `require_can_spend` and
  `require_can_destroy`, built by a shared `_role_gate` factory over
  `SPENDING_ROLES` / `DESTRUCTIVE_ROLES`. They are *dependencies*, not helpers
  a handler calls, so a route cannot hold `auth` without having passed one —
  the same "enforced by construction, not by convention" shape
  `capital/schema` uses. Applied to the 13 routes that spend and the 9 that
  destroy. `admin.py::require_platform_admin` is unchanged and stays
  cross-tenant (it gates on the platform owner's org id, so it is not a
  reusable in-org gate); the five pre-existing inline `auth["role"]` checks in
  `organizations.py` and `billing.py` are left as they are, and the invariant
  test accepts either form.
- **New `services/clearance/privacy.py`** — the clearance module's answer to
  `gtm/privacy.py`, and deliberately *not* the same rule. It redacts personal
  contact channels (email, phone, postal address) and keeps names of record,
  because an inventor or assignee name is the prior-art finding. Enforced at
  both ends of the artifact's life: `artifact.build_artifact` returns through
  it (so `clearance_runs.artifact`, `clearance_findings` and `report_markdown`
  are all clean at rest) and `GET /api/clearance/{run_id}` re-runs it (so rows
  written before this existed are served clean too). The pass is idempotent,
  so the two do not fight.
- **`agent_pricing.MAX_AGENTS_ANY_TIER`** — the ceiling of `TIER_CAPS`,
  derived. The bound for any surface whose fan-out is chosen by the caller
  rather than by a run's stored shape; today that is the batch-interview
  route, which was building one model call per id with nothing limiting the
  total.

## 2026-08-21 — The family-office bank fills itself, and three shapes change

**`services/capital/discovery.py`** — the bank had been deployed and empty
since migration 041. Founder chose route 1B: build the discovery pipeline, do
not license one. Same two-half split as `gtm/extraction` (`propose_firms`
makes the model call, `verify_firms` is pure and decides what survives), and
the same rule: a firm enters only if the search returned its source, and a
field is populated only when an evidence quote appears verbatim in that URL's
text.

**The open web forced a two-stage shape.** The category queries return
directories, trade journalism and competitors' listicles — measured, not
assumed. A listicle is a reliable source of *names* and an unacceptable source
of *theses*, because it paraphrases. So stage one harvests names from anything
that names firms, and stage two builds the record only from that firm's own
site, matched by domain label. First working pass: 15 names → 9 verified
firms, and 7 written to the bank on the run that followed.

**`core/llm_client.llm_structured` now retries.** It made exactly one attempt
and validated; one truncated brace destroyed a 2,500-credit artifact in
production. Two retries, each carrying the parser's own error back to the
model, and each attempt recorded to the cost ledger — a retry is real spend.
This is shared by every structured call in the codebase, which makes it the
highest-leverage change in this batch.

**`services/streaming/publish.py`** — the live run feed's missing half (P0-3).
`ws.py` and `redis_bridge.py` both subscribed to `simulation:*:events` and
nothing in the backend ever published there. The wire vocabulary
(`agent_action`, `round_start`, `round_end`, `simulation_completed`) now owns
`event_type` and the adapters' `post|comment|react|dm` rides beside it as
`action`. They were never alternatives — one says what kind of moment this is
in the run, the other says what the agent did — and trying to pick a winner is
why a third vocabulary exists in `event_schema.py` that nothing produces.

**`services/website/capture.py` gained a ceiling, a pool, and bounds on every
step after the navigation.** The navigation was never the problem: `page.goto`
is bounded and a slow site fails cleanly at 45 seconds. Everything *after* it
was unbounded — `page.title()`, two `page.evaluate()` calls, the style census
and the full-page screenshot — and `page.evaluate` has no default timeout in
Playwright. Two heavy commercial pages never came back. Now: a
`set_default_timeout` on the context for Playwright's own actions, optional
steps (census, meta, title) that cost a field on overrun, and required steps
(the page's text, the screenshot) that end the capture with a sentence,
because a capture with no text would hand the critics a blank page to judge.
At most two browsers per process, since memory is what ran out.

**`services/maintenance/reaper.py` — a new boundary, and the one this batch
most needed.** Every worker writes a non-terminal status, works, then writes a
terminal one; a process that stops between the two leaves a row nobody will
ever close. Both ways of stopping were observed while testing this release: a
Render deploy killed three report writers mid-write, and a capture hung
somewhere `asyncio.wait_for` could not cancel. `gtm/discovery` had already
written the limitation down and named the query that finds the rows. The
reaper sweeps at startup and every five minutes, closes anything past a
generous deadline, and refunds only where the state itself proves nothing was
spent.

It also took two attempts to work, and the reason is worth keeping: the first
version named `credits_charged` in its select and the second wrote
`error_message` on update, and `reports` has neither column. Both times
PostgREST rejected the statement, the handler logged it, and that rule failed
on every sweep — indistinguishable from a table with nothing to clean. A sweep
now reports its failure count as one error-level fact. **The reaper exists
because a dead worker is silent; it needed fixing twice because a broken rule
was silent in exactly the same way.**

---

## 2026-08-21 — The capital module gets a surface

The bank, the matcher, the pricing and the routes shipped on 2026-08-20 and
were reachable by nobody: no page, no route, no nav entry, no price on the
`/billing/prices` screen. Built, deployed, priced and unbuyable — the same
defect as Audiences and Companies before the rail, and the reason
`ia.test.ts` asserts reachability at all.

- **`frontend/src/components/capital/`** — `ShortlistPanel` (buy, poll,
  render), `BankPanel` (browse what the match reads), `FirmRecord` (one
  record, whole), `CapitalPrimitives` (provenance, inbound route, people,
  both-sides quotes, the calm refusal), `capital.css` (the module's washed
  ground, dotted eyebrow and one arrival, all collapsing under
  `prefers-reduced-motion`). Types and readers in `lib/capital.ts`.
- **`/app/capital`**, global rather than a sixth step on the rail, for the
  clearance check's reason: "who would fund this" is asked before there is a
  product to hang it on. Nav entry in `coreNav`.
- **The three fields a list vendor would have dropped are rendered**:
  refusals quoting the firm's own published position, withheld-stale records
  named with their dates, and the denominator (`firms_considered`). A
  `warm_intro_only` or `no_inbound` record renders as a stated refusal
  carrying no route, never as a lead with a missing field —
  `lib/capital.inboundRoute` is the one reader, so no screen can spell it the
  other way.
- **No contact affordance anywhere on the path**, pinned by
  `src/test/capital.test.ts`: no `mailto:` on this surface, and app-wide no
  `mailto:` assembled from a stored value. A firm's published role address
  renders as text; a submission form renders as a link to their own page.
- **Backend, one line of it:** `GET /billing/prices` never published
  `capital_shortlist`, though `agent_pricing.capital_shortlist_credits()`
  priced it and `POST /capital/shortlist` charged it. The one endpoint whose
  purpose is "learn the price before doing the work" could not price this
  work, so the founder would have met it as a 402 at submit.
- **Known gap, not closed here:** `GET /capital/firms` returns validated
  `FamilyOffice` models, and pydantic drops the row's `id`. No client can
  therefore link to `GET /capital/firms/{firm_id}`, so that route is
  unreachable from the UI and no detail page was built (an unlinked route
  fails the reachability test, correctly). Add `id` to the model to open it.

---

## 2026-08-20 — The redesign becomes a deliverable the founder keeps

Founder's ask: *"clients who we render a new website for should be able to
see the new site in HTML, that file should be downloadable and the
style/branding guide should go along with it… A medical SaaS start up's site
should look and feel radically different than a financial products start
up's."* Two gaps, one boundary change.

- **`services/website/verticals.py`** — the generator had no idea what kind of
  company it was designing for. It inherited the founder's existing design DNA
  and polished it, so a generic page came back as a better-executed generic
  page, and a clinical product and a payments product were designed by the
  same instincts. Six briefs (health, fintech, devtools, consumer, b2b_saas,
  marketplace) plus a general fallback, each written as a **buyer argument** —
  who signs the cheque, what they must believe, what the page must carry, what
  reads as a warning sign — never as a house style. `brief_section()` is now a
  block in `revise._generation_prompt`.
- **Classification refuses more than it guesses.** A winner needs ≥2 signals
  *and* a ≥2 margin over the runner-up; a medical-billing product that scores
  health and fintech nearly equally falls back to general. A confidently wrong
  brief pushes a page toward conventions its buyer does not hold, which is
  worse than no brief.
- **`services/website/style_guide.py`** — the design DNA was fed *into* the
  generator and never handed *out*. The guide is now rendered from the
  delivered file: colours, faces, radii and shadows extracted from the HTML
  itself, the category brief that shaped it, the measured after-scores, and
  the gallery's characterization of the old site. No model call on this path.
- **`GET /website/revision/{id}/bundle`** zips `index.html` +
  `STYLE_GUIDE.md`, named for the founder's own domain (sanitised — the string
  lands in a `Content-Disposition` header). Charges nothing: both files are
  already-produced artifacts.
- **Boundary note:** the guide classifies from the page's *visible copy*, not
  its markup. Left raw, a Tailwind page votes with its class names and a React
  bundle with its variable names.

---

## 2026-08-20 — The GTM module joins the pipeline (answer pack)

- New `services/gtm/answer_pack.py`: the objection matrix, built from
  `canonical_objections` ranked by load-bearing score with verbatim quotes
  attached. Four moves per objection (acknowledge / an explore **question** /
  respond / confirm) plus battlecards, and `when_to_walk` where the honest
  answer is that the objection cannot be talked away.
- **Deliberately not the inoculation loop.** Inoculation drafts published
  material and re-runs the room to prove the objection moved; this is the
  script for a live call, which no room can score. Same input, different
  artifact, and they are not substitutes.
- Three disciplines enforced in code rather than in the prompt: measured
  numbers are attached from the database (a model asked to echo a score
  eventually rounds it), a row for an objection nobody raised is dropped, and
  battlecards cover only founder-named rivals plus doing-nothing and
  build-in-house. Fact discipline follows `revise.py` — `[TODO: your number]`
  rather than an invented statistic.
- `workers/answer_pack_tasks.py` deliberately does **not** copy the clearance
  worker's failure handling, which writes raw exceptions into a
  founder-visible column (logged as P1-7). The exception goes to the log; the
  founder gets a sentence.
- New table `answer_packs` (migration 038), routes under `/api/answer-pack`,
  price published through `/billing/prices`, panel on the Answers step.
- Priced 1,500 credits — COGS $0.30 at the 80% target margin through the same
  helper as the website check and the clearance tiers. PROVISIONAL until the
  ledger confirms it.

## 2026-08-17 — The app-shell light restyle, waves 1–2: pages, charts, critics

- Ten parallel agents with disjoint file ownership restyled every page
  behind the login on top of wave 0's token flip (auth re-imagined on
  paper; rail, run setup, IP Check, website intel, dashboard/guide/
  settings, simulations/reports/prospects). Charts retuned for a white
  ground (SentimentArcPlot, SectionRenderer, HeadlineStats and friends):
  rgba(99,139,202,.18) grids, ink labels, bright hues as fills only.
- Shared palettes nobody owned were remapped centrally: `CHART_COLORS`
  and `gtm.TONE_COLOR` now hold values that pass 4.5:1 as text on white
  (both color text directly). `ReportExport` was on no agent's list and
  was caught by the tree-wide sweep — the sweep is not optional.
- Three blind visual critics reviewed the rendered screenshots; their
  agreed findings were applied the same day (the color-grammar law now in
  DECISIONS_LOG; details and open debt in CRITICS_LOG).
- The jargon scanner (`src/test/source.ts`) now reads `title:`/`q:`/`a:`
  object keys — the GuidePage data arrays were rendering "A/B testing"
  under a green test.

## 2026-08-17 — The app-shell light restyle, wave 0: the theme foundation

- The whole app behind the login moves to the landing page's light system
  (founder order: "I love the new aesthetic and want the whole site to have
  this look"). Wave 0 is the token layer, so token-riding components flip
  wholesale: `tailwind.config.js`'s `saibyl-*` palette keeps its dark-era
  NAMES but now carries the light values — `void` means the paper ground
  (#f8fbff), `gold` means the blue accent (#286cf0), `platinum` means ink
  (#14294a). One remap converted every gold CTA/slider to blue and every
  void surface to paper without touching the ~290 call sites.
- Every text-bearing token value holds ≥4.5:1 on white and paper (the
  muted tier is #60718e at 4.7:1 — the old tier failed WCAG and a critic
  caught it). Bright hues (#2fbf8a green, #ff6e79 rose) are fills/dots
  only; chips pair them with darker same-hue text.
- `index.css` globals flipped (shadcn HSL vars, body, typography classes,
  `.glass`, `.bg-grid`, gradients); fonts move Aktiv Grotesk→Manrope,
  JetBrains Mono→DM Mono at the token level. `index.html` drops
  `class="dark"`; `ui/button.tsx` drops its `dark:` variants (Tailwind's
  media strategy would have re-darkened controls for dark-OS visitors).
- Shared chrome restyled by hand where values were hardcoded: `AppLayout`
  (glass sidebar, landing brand mark replacing the dark logo asset, mobile
  clearance under the fixed toggle), `ProductLayout` rail, `StagePrimitives`,
  `StatusBadge`, website chips.
- `vite.config.ts` proxy target is now `VITE_PROXY_TARGET`-overridable so a
  local session can screenshot authed pages against the deployed backend —
  browser CORS forbids a localhost origin calling it directly; the
  server-side proxy is origin-less.
- The landing page's `.v3land` scope verified untouched by screenshot.

## 2026-08-16 — Phase C: fix & prove (PRD §4d)

- `capture.py` gains `capture_html` — renders a provided HTML string through
  the same screenshot/census pipeline, with every outbound request aborted
  (a generated page must not beacon or stall on a dead CDN).
- New `services/website/revise.py`: the gauntlet loop — generate a complete
  self-contained page (32K streaming ceiling), render it, re-judge with the
  six critics, iterate to a target or 3 rounds; best round wins, strictly —
  a regression is recorded but never shipped. Fact discipline: the page's
  own words are the only fact source; missing facts render as
  `[OWNER: fill in]`. Plus the deterministic fix-prompt composer (one
  paste-ready block per dimension + a rebuild-to-DNA block).
- New `page_revisions` table (migration 037) + revision routes under
  `/api/website` (create/status/list, HTML download, before/after screenshot
  passthrough); revisions cost 5,000 credits (PROVISIONAL). Admin gallery
  feed now joins the latest complete revision — before/after-ready.
- The prove leg rides the EXISTING inoculation machinery untouched:
  `/api/website-room` files the revised page's text as an asset on the
  parent run's top objection and calls `create_resimulation` (same copied
  agents = same audience); charging stays at the simulation start route.
  Known compromises documented in `room_run.py`: one-objection filing,
  `disclosure` asset type, the 700-char asset prompt window.
- `llm_client.llm_vision` streams when max_tokens > 8192 — the SDK refuses
  non-streaming ten-minute-class requests (found live).

## 2026-08-16 — Design-intelligence augmentation (PRD §4b²)

- `capture_website` now collects a **style census** (deterministic
  computed-style aggregation: fonts/weights, letter-spacing, palette
  frequencies, radius/shadow vocabularies, spacing histogram) alongside
  screenshots and DOM text — the census is the receipt behind every design
  claim.
- New `services/website/design_dna.py`: one vision call turns capture +
  census into a refero-shaped DESIGN.md artifact + 1–7 maturity level.
- Critic gauntlet grows a sixth dimension, `design` ("The look"), with two
  modes: absolute (slop-tell checks) and reference-anchored (both sites'
  censuses measured against each other; findings carry both values).
- New `design_gallery` table (migration 036): every check persists its DNA,
  census, screenshots, scores. Platform-admin read routes at `/api/admin/*`,
  gated on `ADMIN_ORGANIZATION_ID`.

## 2026-08-16 — Phase B: website intelligence (PRD §4a–c)

- New `services/website/` package: `capture.py` (Playwright chromium,
  desktop 1440 + mobile 390 full-page, SSRF-validated before fetch and after
  redirects via `core/security.validate_external_url`), `store.py`
  (screenshots to the `project-media` bucket; no row ops), `critics.py`
  (five independent one-call vision reviewers, concurrent, five-or-nothing).
- `core/llm_client.py` gains `llm_vision` — **Anthropic SDK direct**, because
  litellm silently drops Anthropic-native image blocks (pinned by test).
- `api/website.py` + `workers/website_tasks.py`: check lifecycle
  queued→capturing→judging→complete/failed; the page's text becomes a
  document (`material_kind='website_url'`) and joins subject material.
- Docker image installs chromium at `/ms-playwright` (root-owned shared
  path, before USER drop).

## 2026-08-16 — Phase IP: USPTO clearance (PRD §11)

- New `services/clearance/` package: `uspto_client.py` (ODP/DSAPI/TSDR with
  the reference server's quirks: search-404 = zero hits, claims XML cached
  24h against the ~20/URL/year cap, key masking, host-check on
  fileLocationURI), `query_plan.py` (Stage 0+1 in one structured call),
  `claim_reader.py`, `tracks.py` (A–D orchestration with count triage),
  `artifact.py` (exact output-contract JSON + report renderer).
- `api/clearance.py` + `workers/clearance_tasks.py`; tables
  `clearance_runs`/`clearance_findings` (migration 034). Free QUICK tier is
  org-rate-limited; STANDARD/COMPREHENSIVE charge credits at creation.
- There is **no public USPTO word-mark search API** (TESS retired) —
  trademarks are status-by-serial + the official link; NOT_SEARCHED is a
  first-class honest status.

## 2026-08-16 — Phase A: V3 realignment

- `app/core/tasks.spawn` replaces four per-router `_safe_task` copies and
  holds strong task references (audit 19's GC half).
- Idea-brief intake: `POST /documents/idea-brief` composes five answers into
  a document through the normal `store_upload` path
  (`material_kind='idea_brief'`); the synthesizer's 1,000-char floor exempts
  idea briefs.
- Crisis lens shelved behind `CRISIS_ENABLED` (default false, 404 before DB).
- Deleted dead subsystems (audit 39): `/api/platforms` router, `/api/uploads`
  shim, the entire ontology/knowledge-graph chain including the report
  engine's three never-functional graph tools (−1,138 lines).
- Report engine reads the whole run (audit 40): the arena-filtering `variant`
  parameter removed; `simulation_analytics` defaults to `"all"`.
