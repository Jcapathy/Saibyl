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
