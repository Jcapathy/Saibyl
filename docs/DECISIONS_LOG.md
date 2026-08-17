# Decisions Log

Standing rule (founder directive, 2026-08-16): every decision that shapes the
product or the build — who made it, what was decided, and the why that lets a
future session know whether it still holds. Newest at the top.
`DECISIONS_V2.md` holds the V2-era record and remains authoritative for those
choices.

---

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
