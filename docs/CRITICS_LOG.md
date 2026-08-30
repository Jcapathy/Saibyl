# Critic's Log — lessons learned

Standing rule (founder directive, 2026-08-16): this is the lessons-learned
document. Every defect class discovered, every check that could have passed
for the wrong reason, every critic-round finding worth carrying forward —
dated, with the transferable lesson stated so the next session doesn't pay
for it twice. Newest at the top. The founding lesson, inherited from the V2
polish pass, still governs: *look at the running product, then at what it
exports, then query the database before you explain either — and make sure
your check could only have passed for the reason you think it did.*

---

## 2026-08-30 — Half the intent never reached the PRD, and nothing noticed for ten days

**The failure class: an intent that lives in one person's head is not a
requirement, and a codebase cannot drift from something it never had.**

The founder's stated goal for the website check has always had two halves —
make the page better for a **human**, and make it legible to the **machines**
buyers now ask. The first half is six vision critics and two counted rubrics.
The second half did not exist. Not partially, not badly: a grep of the whole
website service for structured data, crawler directives, alt text or any of the
relevant acronyms returned zero hits, and the capture collected only
`description` and `og:*`, so the raw material was never gathered either.

**It was absent from `PRD_V3.md` too.** §4b specifies five critics by name and
machine readability is not among them. So every session that built faithfully
to the PRD built half the product, correctly, and no review caught it — because
every review was also reading the PRD.

**What made it findable at all was the founder saying the goal out loud.** He
described the outcome he wanted and asked whether we had drifted from it. The
answer was that we had not drifted; we had never started. **A drift can be
caught by comparing code to a document. An absence of this kind can only be
caught by comparing a document to somebody's intent** — which means the
question *"what did you think this was for?"* is a real audit instrument and
should be asked at phase boundaries, not only when something feels wrong.

**A second, smaller instance of the same class, found in the same pass.**
PRD_V3 names critic five *"Accessibility & mobile — responsiveness, contrast,
tap targets"*. The implementation is keyed `mobile` and labelled "mobile
experience". Contrast and tap targets survived inside the prompt; the word
accessibility did not survive into anything with a name, and hours earlier the
rubric had been caught **penalising WCAG skip links** as a design defect. A
concern with no name in the code is a concern nothing defends.

**The check on the fix, and the reason it is not self-congratulation.** The new
dimension was validated against five real sites, and it disagrees with the
visual dimension on four of them — linear.app and anthropic.com score 100 on
`standard` and 82 and 75 on `found`; stripe.com is the reverse at 73 and 100.
**A new dimension that agreed with the existing ones would have been measuring
something already measured.** The disagreement is the evidence that it reads a
different audience.

**And the gate caught the thing the tests did not.** `vitest` passed 149 green
while `tsc -b` failed: a test importing a `.tsx` file breaks the
project-references pass with *"--jsx is not set"*. This is the exact failure
`CLAUDE.md` warns about in bold, and it was found by running `npm run build`
rather than trusting the suite. The fix moved the function under test into a
`.ts` file, which it should have been in anyway.

---

## 2026-08-30 — A limit applied to the wrong unit, and the reason it survived so long

**The defect.** `SHADOW_LIMIT = 4` was compared against the number of distinct
computed `box-shadow` *strings* on a page. Its own comment says what it is
about: *"shadow encodes how far off the page a surface sits, and elevation has
levels."* Elevation. But a CSS `box-shadow` is a comma-separated list of
layers, and a layer can be any of four devices — an **elevation**, an **inset
highlight**, a **ring**, or a **glow**. Only the first is a height.

Measured across five real pages:

| page | distinct shadow strings | elevations | inset | ring | glow |
|---|---|---|---|---|---|
| linear.app | 8 | **3** | 3 | 2 | 0 |
| vercel.com | 4 | **0** | 1 | 3 | 0 |
| saibyl.com | 10 | **8** | 0 | 1 | 1 |
| stripe.com | 3 | 3 | 0 | 0 | 0 |

**linear.app is the proof this was not special-pleading for our own page.** It
carries a clean three-step elevation scale, three inset hairlines and two focus
rings, and the check told it that it was *"claiming more levels of depth than
the page has things to put on them."*

**A second defect underneath the first: layers that paint nothing were counted.**
Tailwind emits its shadow and ring custom properties as four zeroed
placeholders — `rgba(0, 0, 0, 0) 0px 0px 0px 0px` — on every element carrying
a shadow utility. vercel.com's four shadow values are 5- and 6-layer tokens
that reduce to **one or two** visible layers each. Every Tailwind page was
being inflated by shadows that render nothing at all.

**Why it survived.** Because the number it produced was never obviously wrong.
"10 distinct shadows" on a page with 10 distinct shadow strings is a true
sentence; it is just not an answer to the question the limit was asking. **A
count is only meaningful with its unit attached, and the unit lived in a
comment while the code counted whatever was cheapest to count.** The same
module had already learned this once — the radius check ignores `50%` and
`999px` because *"a circle and a pill are not rungs on a px scale"* — and the
lesson was not carried across to the check directly below it.

**The transferable rule: when a limit and its rationale disagree about the
unit, the rationale is the specification.** Do not adjust the limit to fit what
the code counts; make the code count what the limit is about.

**What the fix is checked against.** The three pages with no false finding are
unchanged — stripe.com 78, vercel.com 90, anthropic.com 95. linear.app's
shadow finding clears entirely, **85 → 90**. And saibyl.com **still fails**,
at 8 elevations against a system that specifies four, dropping only from major
to minor: **66 → 73**. A fix that made our own page's finding disappear would
have been the revision loop gaming `measured` all over again, one layer up.

---

## 2026-08-30 — The rubric was not lenient. It was measuring the wrong thing, and the score hid it

**The handoff asked the wrong question, and it was a reasonable question.**
`HANDOFF_LAUNCH_READINESS.md` §2.3 recorded that `standard` returned **93** on
saibyl.com across three runs and concluded *"the weights are lenient"*, with
the suggested remedy being to tune them against more real pages. Tuning the
weights would have been work spent on the wrong knob.

Calibrated against six real pages — saibyl.com, stripe.com, linear.app,
vercel.com, anthropic.com, news.ycombinator.com — the spread was not narrow at
all: **93, 73, 100, 82, 55, 22**. The ordering was the problem. anthropic.com
scored **55** and stripe.com **73** while the founder's own page scored 93.

Reading which rules fired, rather than the scores, found two defects — both in
the *census*, neither in the rubric:

1. **`requires_an_image` counted `<img>` elements only.** anthropic.com ships
   **zero `<img>` and sixteen visible inline SVGs**. It was failing a
   *requirement* — `18 × 1.5 = 27` points, the heaviest non-critical penalty in
   the rubric — and being told, in the founder-facing fix line, to *"show the
   product doing its job"*. Meanwhile news.ycombinator.com, which is genuinely
   all text, **passed** the same rule on a single 18×18 logo. The rule was
   inverted on the two pages that tested it.

2. **`one_destination_one_label` grouped by `URL.pathname`.** That discards the
   host *and* the fragment. On anthropic.com, **seven distinct origins**
   (`status.`, `trust.`, `platform.`, `support.`, `academy.`, `www.`) collapsed
   into one bucket keyed `/`, and the page's two WCAG **skip links** —
   `#main` and `#footer` — landed in it too. The page was charged 18 points and
   told to rename actions that had never been the same door.

**The transferable lesson: a score is a summary, and a summary of a wrong
measurement looks exactly like a summary of a right one.** Three runs returning
93 was read as evidence the rubric was stable and merely generous. It was
stable because arithmetic is stable. Nothing about the repetition spoke to
whether the inputs meant what their names said. **Read which rules fired, on
pages whose answer you already know, before you touch a weight.** The
diagnostic that worked was a verdict matrix across six pages — six rows, seven
columns — and the two defects were visible in it immediately.

**Two known failure classes, both already in HANDOFF §2a, both re-produced.**
*A string used as a key, unnormalised* — the same shape as the adapter defect
that lost 193 of 193 reply links, with a browser rather than a model as the
source. And *two sources of truth for one value*: `measured.py` carried the
same image check with the same false quote, so both halves of the report were
wrong in the same way, from the same field.

**Choosing the fix by measurement rather than by taste.** The icon/image
boundary is `_CENSUS_MEDIA_MIN_PX = 64`, and 64 is not a preference — it is the
lowest threshold at which every designed page in the sample scores ≥ 1 and
news.ycombinator.com scores 0. The table it came from sits beside the constant,
because §2a is explicit that a constant without a measured value in its comment
is a guess.

**What the fix is checked against.** The four pages with no false finding —
saibyl.com 93, stripe.com 73, linear.app 100, vercel.com 82 — are **unchanged**
after it. Only the two that were being scored wrongly moved: anthropic.com
**55 → 100**, news.ycombinator.com **22 → 0** (it now fails the imagery rule it
had been passing on a logo). vercel.com's *"Get a Demo" / "Talk to sales"* —
one genuine destination wearing two labels — still fails, so the fix did not
buy its false-negative reduction by discarding true positives.

---

## 2026-08-30 — I overwrote a working module because I did not read it first

**The mistake.** Asked to build an admin console, I wrote a new
`app/api/admin.py` with the Write tool. The file already existed — a
platform-owner surface over the design gallery, 153 lines — and the write
destroyed it. It was recovered whole from `git show HEAD:` seconds later, so
nothing was lost, but only because the work was committed.

The tool result said **"has been updated successfully"**, not "created". That
word was the only signal, and it arrived after the damage.

**Two things made it avoidable, and both were already written down.** The
founder's standing note says *always read before write, inquire before
overwrite* — a previous session erased brand files the same way. And the import
block in `main.py` already read `admin,` three lines above where I was working.
I had grepped for `is_admin` and `require_admin` and found nothing, concluded
"no admin concept exists", and never grepped for the obvious noun.

**The lesson is narrower than "be careful".** `grep` for a *capability* is not
`ls` for a *file*. I searched for the mechanism I expected (a role check) and
took its absence as proof the feature was absent. The cheap check I skipped —
does a file with this name already exist — would have taken one command.
**Before Write on any path you have not read this session, list it.**

**What the mistake was worth.** The existing module gates on
`ADMIN_ORGANIZATION_ID` and refuses with **404 rather than 403**, so a probe
cannot confirm the surface exists. I had invented an email allow-list returning
403. Theirs is better and is the established pattern, so mine was reverted and
the new endpoints were appended to the existing router using
`require_platform_admin`. Two admin gates would have been two things to keep in
step and two ways to be wrong — which is the drift this codebase names as its
most common failure.

---

## 2026-08-28 — A rubric of penalties has its maximum at the empty page

**The defect.** The founder ran the revision loop on his own landing page. It
reported a win — overall 70 → 75 — and handed back a page he described as
having "not really much to it". The dimension scores say exactly what happened:

| | before | after |
|---|---|---|
| `design` (a model looking at the page) | **95** | **72** |
| `measured` (arithmetic) | **35** | **73** |

The loop raised the counted score by *removing* things: fewer radii, fewer
colours, fewer shadows, fewer em-dashes. Every rule in `measured.py` is a
variety penalty, and **a penalty is satisfied by deletion**. So the rubric's
maximum sits at a blank page, and the optimiser found that gradient the first
time it was pointed at anything.

**The lesson, and it generalises past this codebase.** A scoring function
assembled entirely from "too much of X" has its optimum at nothing at all. If
anything optimises against it — a loop, a model, a person paid on the number —
it will discover that, and it will look like progress the whole way down. The
counted half of a rubric needs **requirements** as well as **violations**:
things that must be *present*, which removal cannot satisfy.

`taste.py` is that fix, and the regression test is the honest one:
`test_a_stripped_page_scores_badly` builds a page with no images, no buttons, no
headings, one font and two colours — every variety penalty satisfied because
there is nothing left to vary — and asserts it scores below 50. Measured: it
scores **0**, against **100** for a sound page.

**The second lesson, from the same day.** Where a rubric has no absolute
standard, it borrows one. This check's fallback was another company's website:
with a reference named, the design reviewer scored *"how close this page's
visual discipline comes to the reference's"*. Nobody designed that as a
philosophy; it was what remained once "is this good?" turned out to be
unanswerable. The founder's objection — *"we're trying to improve upon what a
founder has already done, not try and make theirs like Linear's"* — is the
product argument, but the engineering one is the same: **a missing standard
does not leave a hole, it gets filled by whatever is nearest.**

**On keeping prose and data married.** The instinct was to move the standard
from prompt text to data for testability. The founder pushed back and was right:
the prose is the deliverable to the founder, the data is how it scores, and both
are needed. The resolution is one row carrying both, with the prompt section
*generated* from the rules table — because two copies of a rule are two rules,
and they drift. A founder told to fix something the score does not measure has
been given a worse report than no report.

---

## 2026-08-27 — A stored id is a hint, not a fact

**The defect.** Saibyl took its first real payment today. The attempt before it
failed, and the founder saw "network error".

His org held `stripe_customer_id = cus_V9cLNGxXbbzvOo`, minted minutes earlier
while the backend pointed at a Stripe *sandbox* for the end-to-end rehearsal.
When the keys moved to the live account, both checkout paths kept sending that
id, because each created a customer only `if not customer_id`. Stripe answered
`resource_missing`; the request raised; the browser reported a transport error.
Every retry re-sent the same dead id, so there was no way out from inside the
product. Nulling the column by hand was the only fix — **and a paying customer
cannot do that.**

**How it was located, which is the reusable part.** No `credit_topups` row
existed for the attempt. That insert is the last statement in
`create_topup_checkout`, so its absence placed the failure upstream of it, in
the Stripe calls — not in the webhook, not in the deploy, not in CORS, all of
which "network error" equally suggests. Health was 200 and the route answered
401 unauthenticated, which ruled out the deploy in one command. **Order of
writes is diagnostic information**: because the row is written last on purpose,
its presence or absence bisects the function.

**The lesson.** An identifier issued by an external system is only valid for the
account, mode and environment that issued it, and any of those can change under
you — sandbox to live, a key rotation, a restored backup, a second Stripe
account. Code that reads `if not stored_id: create()` has quietly assumed that a
stored id is a *valid* id. It is a hint. The recovery belongs at the point of
use: catch the vendor's own "no such thing" error, discard the hint, re-mint,
retry once.

Note what was NOT done: validating the customer with a `Customer.retrieve`
before every checkout. That adds a round trip to every purchase forever to
defend against something that happens almost never, and the retry costs nothing
on the happy path.

**Both paths had it.** `create_flash_report_checkout` carried the identical
`if not customer_id`. Grepping for the shape rather than fixing the one that
broke is what turned one fix into two.

**The test had to be shown to fail.** With `_is_missing_customer` stubbed to
return `False`, the top-up raises — so the nine new tests in
`test_stripe_stale_customer.py` are guarding the fix and not passing for some
unrelated reason. A regression test never seen red is a guess.

---

## 2026-08-27 — The vendor's own remediation would have broken production

**The near-miss.** Supabase's security advisor raised twelve
`function_search_path_mutable` warnings, and its linked remediation says to set
`search_path = ''` and fully qualify every reference. Applied as written, that
would have broken **nine of the twelve functions**, because their bodies
reference `organizations`, `credit_topups`, `llm_usage`, `gtm_discovery_runs`
and `simulation_events` with no schema. An empty `search_path` resolves none of
those.

The three that would have failed first: `grant_credits` (every signup),
`deduct_credits` (every run) and `apply_credit_topup` (every Stripe payment).
It would not have failed at migration time. `ALTER FUNCTION … SET search_path`
does not re-parse the body, so the migration reports success and the function
raises `relation "organizations" does not exist` on its next call — in
production, on the paths that take money and create accounts.

A second item in the same batch was worse. `REVOKE EXECUTE ON
user_organization_ids()` reads like obvious hygiene and would have broken
**thirty-six RLS policies at once** — a policy that calls a function requires
the querying role to hold EXECUTE, so revoking it from `authenticated` ends
tenant reads on every table in the schema. Both were caught by reading the
function bodies and `pg_policies` before writing any DDL.

**The lesson, and it is not "advisors are wrong".** The advisor was right that
the setting was missing. What it could not know is what the bodies contain or
what depends on the grant. **A remediation is generic; a codebase is not.**
Before applying any linter's suggested fix to production, read the thing being
fixed and read what depends on it. Here that meant twelve
`pg_get_functiondef` calls and one `pg_policies` query — perhaps five minutes,
against an outage on signup and billing.

The safe form was `search_path = public, pg_temp`: it satisfies the lint, pins
the path against the session-level manipulation the lint is actually about, puts
`pg_temp` last so temp relations cannot shadow, and cannot change any name that
resolves today.

**On verifying it.** "The migration applied" proves nothing here — that is the
exact check that would have passed while the product was broken. Every callable
function was invoked with ids matching zero rows, which forces table resolution
without touching data. That is the check that could only pass for the right
reason.

**Related:** the two warnings left open on `user_organization_ids` are a
decision, recorded in `INFRA_LOG.md`. A future session reading a non-zero
advisor count should not "finish the job".

---

## 2026-08-27 — A missing capability can hide behind copy that sounds decided

**The defect.** Saibyl had no password recovery of any kind. The founder found
it the ordinary way — he could not get into his own account.

**Why nobody found it earlier, and this is the transferable part.** Every
surface that touched it read as a decision rather than as a gap:

- `LoginPage` had a comment explaining that the `mailto:` was deliberate, and
  it was a genuine improvement on the handler-less button before it.
- Settings said *"Both are handled by email rather than in the app… because
  neither is a button we would trust ourselves to build once and never look at
  again"* — a stated rationale, in the product's own voice.
- The signup 409 told people to email `info@saidolabs.com` for a reset.

Three places agreeing, each written confidently, none of them wrong about what
the product did. **Confident copy describing an absence is indistinguishable
from confident copy describing a choice**, and a reviewer reading any one of
those files finds a reason and moves on. There is no test that fails, because
there is nothing to test.

**The lesson.** Grep for capabilities the way we grep for claims. The question
that would have caught this is not "is any of this wrong?" — none of it was —
but *"what can a user not do, and does anything in the repo admit it?"* A
`mailto:` in a product surface is a capability gap wearing a sentence. So is
"handled by email", "contact us to", and "write to us and we will action it".
Each one is worth a moment's check that the human loop it names is deliberate
and still acceptable, rather than the residue of something never built.

**Related, same day:** the fix's own risk is of the same family. `redirect_to`
is dropped silently by GoTrue when the URL is not allow-listed, so the reset
mail sends, the link works, and it lands on the wrong page — a flow that is
broken in exactly the way a green deploy cannot show. Verified by reading the
link in the mail, not by the build. See `INFRA_LOG.md`.

---

## 2026-08-26 — The website check reports a point where it has a band

An accidental duplicate run gave us test-retest data on the gauntlet: five
competitor sites, scored twice, five minutes apart, same code, unchanged pages.

| Site | Overall | Counted | Conversion |
|---|---|---|---|
| AskReplicas | 69 → 69 | 78 → 78 | 62 → 62 |
| Outset | 67 → 67 | 83 → 83 | 62 → 62 |
| Aaru | 66 → 66 | 73 → 73 | 52 → 52 |
| Qualtrics | 72 → 71 | 100 → 100 | **62 → 52** |
| Prolific | 66 → 69 | 85 → 85 | **42 → 52** |

**The counted dimension returned identical scores on all five.** Zero variance,
which is what a check with no model call in it should do and now demonstrably
does. That is worth knowing as a fact rather than as a design intention.

**Overall moved a point or less on four of five.** Also reassuring.

**Individual vision dimensions moved up to ten points on pages that did not
change.** Conversion swung ten twice, in both directions. Copy moved six twice.
Mobile moved six.

**The defect is not the variance. It is reporting a point.** A founder who runs a
check, edits nothing, and runs it again can watch conversion fall from 62 to 52
and reasonably conclude they broke something. Nothing on the screen tells them
the number has a width.

This codebase already knows how to say this. Every room-based report carries
intervals, `analysis_schema` refuses a proportion without one, and
`formatReach` prints "0% (up to N% at this swarm size)" rather than a bare zero.
The website check is the one surface that states a model's opinion as a scalar.

**The fix is not to suppress the variance**, which is real and is information: a
dimension that moves ten points between identical runs is telling you its rubric
is underdetermined for that page. It is to report what the room reports — a
band, or a score averaged across runs with the spread shown — and to say plainly
that the counted dimension is the one that will not move.

**And the transferable lesson.** We shipped seven dimensions on one screen with
identical visual weight, six of which are opinions with a width and one of which
is arithmetic. Presenting them the same way is a claim that they are the same
kind of thing, and they are not.

## 2026-08-25 — The critics think the present is the future

Six sample pages, run through the full gauntlet. The credibility reviewer
flagged this on every one of them:

> **"© 2026 Basecrate"** — *the copyright year is 2026, which is in the future.
> This signals either a template placeholder or carelessness, both of which
> undermine trust.*

It is not in the future. It is this year. The reviewer is a vision model
reasoning from a training cutoff, and it will make the same accusation against
every correctly-dated footer on every real customer's page, in confident
language, under the heading "credibility".

**Why this is worse than an ordinary wrong finding.** It is unfalsifiable to the
reader in the moment: a founder who sees "your copyright year is in the future"
has no way to know the reviewer is the one holding a stale calendar, and the
obvious fix is to *back-date their own footer*. A critique that talks a founder
into making their page worse is the failure mode this whole module is built to
avoid.

**The transferable lesson.** A model does not know what day it is, and any
rubric that invites it to reason about "current", "recent", "outdated",
"upcoming" or "still supported" is asking a question its weights cannot answer.
Anything time-relative in a prompt needs the date supplied as an input, exactly
as `clearance/tracks.py` already does with `search_date` rather than reading
`datetime.now()` deep in the logic. That precedent existed and this rubric did
not follow it.

**Not yet fixed.** The date is not currently passed to the critics. Doing so is
the fix; suppressing the finding is not, because the same blindness will surface
as "this framework is outdated" or "this integration is deprecated" wherever a
page happens to mention a version.

## 2026-08-25 — Deleting a feature can silently delete a test's only lever

Removing the subscription tiers took `check_simulation_quota` out of the run
path, because credits are the only ration now. It also removed the **last
`await` between the status read and the compare-and-set guard** in
`start_simulation` — and `test_two_starts_in_one_window_charge_once_and_run_one_engine`
was using that await as its synchronisation point to hold two concurrent
requests inside the race window.

**The test did not fail loudly. It failed informatively:** with no interleave,
the second request was caught by the *plain read* at the top of the handler
("Simulation is already running") instead of the compare-and-set ("has already
been started"). Two different guards, and only one of them is the one that
protects money against genuinely concurrent processes. Had the assertion been
looser — status code only — the coverage would have evaporated in silence and
the suite would still have been green.

**The lesson, transferable.** A test's *fixture* can depend on production
behaviour that has nothing to do with what the test asserts. Removing a network
call is not only a behaviour change; it is a change to what can be interleaved,
mocked, delayed or observed. Before deleting an `await`, a network call or a
hook, grep the tests for it as a **lever**, not just as a subject — the greps
this codebase's rules already mandate (calls, types, string literals, re-exports)
would not have found this, because the test never asserted anything about
quotas at all.

**Left honest rather than quietly patched.** The test now accepts either guard
and says in its own docstring that the compare-and-set is no longer exercised
in-process, with a pointer here. The guard itself is unchanged and still
correct; what is gone is the proof. Restoring it needs either a genuine
concurrency harness or an await in that window that earns its place on its own
merits — not one added to please a test.

## 2026-08-22 — Honesty has a price, and the gauntlet charges it to the founder

Three brand-new sample products (devtools, consumer, marketplace) run end to
end against the shipped verifiers. The verifiers worked. **The product got
worse.**

| Product | check → revision | credibility |
|---|---|---|
| Basecrate (devtools) | 77 → **77** | 78 → 72 |
| Loomcraft (marketplace) | 68 → **67** | 62 → 52 |
| Fernway (consumer) | 76 → **63** | 68 → **32** |

Not one improved. The cause is not subtle, and the after-critique says it
outright:

> "The three most important trust signals on the page — app store rating,
> review count, and total user count — are unfilled placeholders. A visitor
> sees literal bracket text instead of social proof, which instantly destroys
> credibility."

**The Fernway run is the cleanest experiment we will ever get.** Its critic
panel explicitly instructed the generator to invent — *"e.g., 'Over 500
million learners worldwide'"*, *"e.g., '34 hours of Duolingo equals a full
university semester (City University of New York study, 2012)'"*. The
generator refused both and wrote `[OWNER: fill in]`. Then the same panel
marked credibility down from 68 to **32** for the blanks it had just demanded
be filled with fabrications.

So the loop now contains a genuine contradiction: **one half of the module
asks for evidence the material does not contain, and the other half is
forbidden to supply it.** The founder pays 5,000 credits and receives a
measured −13 with a before/after that argues against the purchase.

**The transferable lesson is not "the verifier is wrong".** It is that a
quality score measured by a judge who cannot see the source will always
reward the fabricating artifact, so any honesty control you add shows up as a
regression in the number you were using to sell the feature. Either the judge
learns that a declared blank is not a defect, or the number stops being the
headline. Both are product decisions, not engineering ones — recorded here
because the next person to look at these scores will otherwise read them as
the revision module getting worse.

## 2026-08-22 — A prompt is not a control, and a blind judge cannot catch invention

Three lessons from a live fintech revision that shipped invented compliance
badges, each of which transfers well past the website module.

**1. An instruction the model overrides is not a safeguard, and repeating it
does not make it one.** The prompt forbade inventing facts *twice* — once
absolutely (`_FACT_RULES`), once with the consequence spelled out ("a page
that claims a certification it does not hold is worse than one that omits
it"). The model invented seven certifications anyway. The reason is
instructive: the same prompt also carried a category checklist naming the
evidence a fintech page must show, and **a checklist is a demand while a
prohibition is only a rule**. When the material cannot satisfy the checklist,
priors will. If you find yourself adding a third sentence to a prompt, the
answer is a verifier, not a sentence.

**2. Ask what your judge can physically see.** The six-critic gauntlet reads a
screenshot of the *new* page. It never receives the old one. So no critic,
however well prompted, could ever have caught a fabricated fact — and the
scores prove it: 78 → 80 overall with credibility *unmoved at 82* while being
handed invented ISO and PCI claims. Before trusting any evaluator, enumerate
its inputs and ask which failure modes are outside them. Those need a
different mechanism, not a better prompt.

**3. A quality score is not a safety score, so do not rank on it alone.** The
loop selected the best round by `overall_score`. That is a decision to ship a
forgery whenever the forgery scores two points higher — which is exactly what
happened. Wherever a pipeline ranks candidates by a model's judgement, check
whether a *disqualifying* property exists that no score should be able to
outweigh.

**And the near-miss worth naming:** the deterministic scan caught a claim the
careful manual diff had missed — *"is a licensed money transmitter in all US
states that require one."* A reviewer reading for the badges they expected
found six; a function that does not get tired found seven.

**Corollary, and the shape of the remaining risk.** The scan catches
*claim-shaped* fabrication — a badge, a price, a count — because those have a
token to compare. The same runs showed identical behaviour in prose that has
nothing checkable in it: a pre-launch product's answer pack asserting
"customers are seeing 10+ hours per month back", an outbound sequence claiming
"we built volume pricing into the model", a report inverting a measured
platform split under a bolded **Evidence:** label. Across both runs
**159 of 159 and 80 of 80 structured quotes were verbatim** — the schema
boundary works exactly as designed — and the free prose beside them was
unpoliced. Structured evidence being perfect is not evidence that the artifact
is honest; it only proves the fields you constrained are the fields that held.

## 2026-08-22 — Three defect classes an audit found, and what transfers

**A concurrency limit is not a spend limit.** `interview_batch` held a
`Semaphore(5)` and read as bounded. It bounds how many calls run *at once*,
not how many run — ten thousand ids meant twenty thousand model calls, five
at a time, all of them on Saibyl's account and none of them metered. Transfer:
whenever a request body carries a list that becomes work, find the thing that
limits the *total*. If the only limit you can point at is a semaphore, a pool
size, or a rate limiter, there isn't one.

**A field that carries a value nobody asked for is still a field you now own.**
The clearance artifact was "the skill's output contract byte for byte", which
was true and beside the point: `owner` and `assignee` come from USPTO records
that also carry inventor and attorney addresses, and nothing scanned. The
codebase already had the right instinct twice (`gtm/privacy`,
`capital/schema`) and clearance simply never inherited it — because it was
built as a faithful port of a skill, and fidelity to an upstream contract
reads as a reason not to change the payload. Transfer: **a port inherits the
source's shape, not its data-protection posture.** Ask separately what the new
system is now storing.

**And the fix can be worse than the defect.** The obvious remedy — apply
`rejects_as_personal_data` and drop anything that trips it — would have
deleted prior-art findings, silently, on the exact runs where the finding
mattered most. The two rules look identical and are not: refusing is right
when Saibyl chose to collect, redacting is right when the user asked a
question whose answer is a public register. Transfer: before reusing a rule
from another module, check whether its *premise* holds, not just whether its
shape fits.

**A returned field that nothing reads is a permission nobody granted.**
`get_current_org` had returned `role` since V1. Five routes read it; forty-odd
did not, so a `viewer` could spend 5,000 credits or purge the org's GTM data.
Nothing was broken — the data was simply never consulted, which no test could
notice because every test fixture built its auth dict as `{"org_id": ORG}` and
the absence of `role` was itself the assertion. Transfer: **grep for the
readers of a security-relevant field, not for its writers**, and treat a test
fixture that omits a field as a claim that the field does not matter.

## 2026-08-17 — The app-shell restyle (waves 0–2): lessons and the critic round

- **A name-stable token remap flips an app wholesale.** Keeping the dark-era
  token NAMES (`void`, `gold`, `platinum`) and changing only their values
  converted ~290 call sites without touching them; ten agents then only had
  to chase hardcoded remnants. The corollary: hardcoded hexes are the debt,
  tokens are the leverage.
- **The jargon scanner's third blind spot, same class as the first two.**
  GuidePage's tips/FAQ live in data arrays; the scanner read `body:` but not
  `title:`/`q:`/`a:`, so "A/B testing" shipped in two rendered strings under
  a green jargon test. Copy fixed (message test / versions) and the scanner
  widened to those keys. Prior instances: `label=` attributes, entity-bearing
  sentences. Lesson stands: every copy-carrying key the codebase invents
  must be added to `renderedStrings` the day it is invented.
- **Full-page screenshots of the app capture one viewport.** The shell
  scrolls inside `<main>` (h-screen + overflow-auto), so `full_page=True`
  sees only the fold; every below-the-fold chart went unverified until the
  scroll containers were expanded via JS before the shot. Companion to the
  IntersectionObserver lesson from the landing page: know what your capture
  can actually see.
- **Tailwind's media-strategy `dark:` variants are a sleeper.** With
  `class="dark"` removed and no `darkMode` config, `dark:` classes bind to
  `prefers-color-scheme` — dark-OS visitors would have gotten re-darkened
  controls. Strip `dark:` variants when committing to one light look.
- **CORS makes localhost → production API impossible from the browser;**
  the dev-server proxy (server-side, origin-less) is how authed pages get
  screenshot against the deployed backend (`VITE_PROXY_TARGET`).
- **The critic round** (three blind reviewers on the shots: hierarchy/
  consistency, accessibility/craft, brand-vs-landing): the shared verdict
  was "typography coherent, color grammar not." Fixed the same day: the
  landing's gradient-pill primary restored app-wide via one stylesheet rule;
  stat numerals de-tinted (ink; icons carry accents); passive chips left
  action-blue; one green "Finished" idiom; the 390px wizard overflow (the
  one true layout bug); the wordmark corrected to mixed-case + BY SAIDO
  LABS; "1 person" pluralized; truncated persona labels wrap; auth labels
  a contrast tier up; signup's Terms/Privacy links pointed at the real
  routes (they were `href="#"`).
- **Open debt the critics named, deliberately not fixed in this pass** (IA/
  copy/product, not styling): the credits module reading "1,500 · About 0
  more runs" (free grant < paid-shape run price — product tension, not a
  bug); "how they took it: 0.00" repeated on every feed item; platform
  chips rendering "R"/"x"; sidebar labels vs page titles ("Home" → "Your
  products", "Every run" → "Your runs"); "Start simulating in minutes" on
  signup (verb form skirts the banned-noun scan); the audience step's four
  upload entry points; equal-height dead air on the report's "Where they
  were" card; money format drift on Settings ("$20" vs "$20.00").

## 2026-08-17 — A parked deliverable reads as shipped

The founder approved the light redesign ("this is the look and feel of
exactly what I was going for") and the prototype + implementation prompt
went into the backlog awaiting an explicit "implement it" — while phases
shipped around it. The founder then opened the live site and found the old
dark page. Lesson: **when the founder approves a deliverable whose whole
point is to be seen, implementation is the default next step, not a new
decision.** A prototype accepted with enthusiasm is an order.

## 2026-08-16 — Phase C live gate (two catches)

- **SDK guards are features you meet in production**: the Anthropic SDK
  refuses non-streaming requests whose max_tokens could run ten minutes —
  the 32K revision ceiling tripped it live. Large ceilings stream and
  accumulate; the mocked tests could never see it.
- **Symmetry between paired artifacts is a contract**: scores_before nested
  its dimensions, the generator's scores_after was flat — every
  after-dimension rendered as None. Both sides now go through one lifter
  from full critiques. When two fields exist to be compared, derive them
  through the same function or they will drift.
- The gate's result, for the record: a real page improved 57→64 overall in
  three rounds (best: 2), credibility +16, with seven verbatim-pasteable fix
  prompts — the §5 proof-of-delta standard, live.

## 2026-08-16 — The design-augmentation live gates (three attempts, four lessons)

- **Validation strictness must match the receipt's nature.** Forcing
  non-empty quotes on every reviewer broke honest prose reviewers (a spacing
  observation has nothing to quote) while the design reviewer — whose quote
  IS the measurement — needed the force. One schema per meaning:
  `_MeasuredFinding` for design only.
- **A retry that repeats the question gets the same wrong answer.** The
  generic "return valid JSON" nudge re-failed identically when the JSON was
  valid but a field was rejected; carrying the validation complaint into the
  retry ("findings.0.quote: too short") is what changes the model's answer.
- **Bot walls fail successfully.** linear.app returned an 18KB challenge
  page with HTTP 200 — the critics would have measured a CAPTCHA as the
  admired design. A near-empty reference is now a failed reference with an
  honest sentence.
- **Size ceilings are per-artifact, not per-default.** A DESIGN.md inside a
  JSON payload truncates at the default 4,096 max_tokens and fails parsing
  twice in a row; the ceiling must be sized for the largest honest artifact
  (16K), found only live.

## 2026-08-16 — Integration seams are where green tests lie

- **The fixture written by the bug's author validates the bug.** Twice in
  one night: the clearance worker read artifact keys that don't exist
  ("trademarks"/"pending" vs the contract's "trademark"/
  "pending_landscape") and its own test fixture used the same invented keys
  — 15 findings rows would have been silently empty forever. Then migration
  035's comment promised the captured page "reads as subject material" while
  `_SUBJECT_MATERIAL_KINDS` still excluded it. Lesson: at every seam between
  parallel workstreams, verify the *actual* contract artifact against the
  *actual* reader — never both against a shared assumption.
- **A 200 is not a success.** litellm returns HTTP 200 while silently
  dropping Anthropic-native image blocks — every vision critic would have
  judged a page it never saw, with no error anywhere. Found only by
  verifying the conversion layer against the installed version. Lesson:
  when a payload passes through a translation layer, test what arrives on
  the wire, not what the call returns.
- **Full-page screenshots lie about scroll-reveal pages.** IntersectionObserver
  never fires during a virtual-scroll capture, so every `.reveal` section
  screenshots at opacity 0 — the page looked built and empty at once.
  Lesson: capture from a JS-stripped copy (now standard in the prototype
  workflow and worth remembering for the product's own capture pipeline).

## 2026-08-16 — Critic-round findings worth keeping (landing redesign)

- Round 1 (live dark site, five critics, 58–66): the tab title sold a
  different product than the page; the page asked for a confidential deck
  with zero privacy language; the differentiator (synthetic buyers) was a
  delayed reveal that read as bait-and-switch; credits arithmetic was
  un-computable; the muted-gray text tier failed WCAG while carrying the
  no-card promise.
- Round 2 (redesign, 78–82): fixes verified by delta, and the round caught
  what the redesign itself introduced — the over-correction from confession
  to invisibility on the sample run, an uncited drifting statistic, a
  number-contradiction heading. Lesson: **the re-critique exists to catch
  the defects the fix creates.**
- Round 3 (Saido-aesthetic rebuild, 74–81 on pixels + brief): validated the
  light system ("zero dark-crypto residue"); caught synthetic buyers being
  counted as "people", "Unlock next" naming no price, and a mobile chip
  collision invisible in code. Lesson: critique rendered pixels, not source.
- **Every critic run needs the "preserve" list.** Strengths-to-protect kept
  three rounds of edits from sanding off what worked (the Tallyhook receipt,
  the no-card wording, the single-gold-CTA system).

## 2026-08-16 — Ops lessons

- **A check that can pass for the wrong reason is worse than no check**:
  deploy verification uses discriminators that only the new build can
  produce (a route flipping 404→401; a title only the new bundle carries).
- **OneDrive and virtualenvs are enemies**: its scanner locks dist-info dirs
  mid-operation, corrupting installs into namespace-package corpses whose
  metadata still satisfies the resolver ("Checked 161 packages" over a
  broken pluggy). Repair = quarantine-by-rename (renames succeed where
  deletes fail), then fresh installs; prevention = keep venvs off synced
  folders.
- **Free-tier honesty is a product defect class**: QUICK's GREEN vs
  STANDARD's YELLOW (zero deep reads can't evaluate the GREEN bar) — logged
  in DECISIONS_LOG for the founder's ruling.
