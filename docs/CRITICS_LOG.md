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
