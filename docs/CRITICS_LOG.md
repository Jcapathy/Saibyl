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
