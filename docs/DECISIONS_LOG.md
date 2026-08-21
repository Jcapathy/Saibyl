# Decisions Log

Standing rule (founder directive, 2026-08-16): every decision that shapes the
product or the build — who made it, what was decided, and the why that lets a
future session know whether it still holds. Newest at the top.
`DECISIONS_V2.md` holds the V2-era record and remains authoritative for those
choices.

---

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
