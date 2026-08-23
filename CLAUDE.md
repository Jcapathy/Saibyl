# Saibyl — read this before you write code

Saibyl is a Saido Labs LLC product. No personal name ever appears on it.

---

## 1. Any UI or frontend work reads `design/` first

**Before writing a line of frontend code — a new page, a new panel, a restyle,
a chart — open `design/` and read it.** Start with `design/README.md`, then the
four artboards. They are self-contained HTML: open them in a browser.

`design/canvas.json` — the `annotations` array — **is the design law.** It was
approved by the founder on 2026-08-20. It is not a mood board and not a
suggestion; it is the specification, written in his words, for every surface
behind the login.

This rule exists because it was already broken. Three days after the canvas was
approved, a session built two brand-new app pages without ever opening the
folder, because nothing in the repo pointed at it. The founder found the drift
himself on his first read-through of the site. **You are the reason this file
exists.**

### The four rules, quoted from the canvas annotation

> The four changes, applied everywhere:
>
> 1. Radial washes on the ground (the app is flat #f8fbff today)
> 2. Soft blue shadows on cards that carry meaning — hairlines stay on dense lists
> 3. The dotted eyebrow on every mono label
> 4. One Playfair italic phrase per major heading

### Motion is part of the design, not a garnish

> MOTION: reload an artboard to replay it. The rail deals its five steps, then
> the open stage arrives. Every artboard collapses its animation under
> prefers-reduced-motion, exactly as the landing page does.

Reuse the landing page's own keyframes, durations and easing. A second motion
vocabulary reads as a second product. `prefers-reduced-motion: reduce`
collapsing every animation is not optional.

### Density does not change

> Density is deliberately unchanged. Same type sizes, same 13px body, same row
> rhythm — warmth comes from ground, depth and one accent phrase, not from
> spacing things further apart. An app that reads like a marketing page is the
> opposite failure.

**The one exception, granted by the founder on 2026-08-23: `PageHeader`.**
He read the five live stage pages and could not comfortably read them on his
own monitor — the accent phrase was 15px serif italic sitting *above* a 13px
paragraph, on a block whose whole job is to teach a stage to somebody who has
just arrived on it. His instruction: expand the block with explanatory copy,
and put the tagline underneath it, larger.

So the header block is a front door, not a dense surface. The lead is
14/15px and the phrase is 20/23/26px responsive, and the explanation reads
*before* the phrase it earns. **Do not "restore" these to 13px.** Everywhere
else — rows, cards, lists, every record — the constraint above is unchanged
and still binding. `design_primitives.test.ts` §6 pins both halves: the
header's sizes and order, and that nothing outside it sizes type at all.

### New pages use the shared design primitives

Every new page composes **`frontend/src/components/design/`** — the shared
primitives that carry the four rules. Do not hand-roll a washed ground, a
dotted eyebrow, a soft-shadow card or a serif-italic heading in page code; that
is how the system forks into dialects. If a primitive you need is missing, add
it there rather than inline.

`frontend/src/test/ia.test.ts` asserts this. Pages not yet converted are named
in an allow-list inside it that **may only ever shrink** — converting a page
means deleting its line from that list in the same change.

### Where the system came from

`frontend/src/pages/landing.css` is the origin: the approved light system was
built there first, and its values are the source of truth. `docs/DESIGN_GUIDE.md`
is the written-out version (tokens, type, motion table, export rules, and the
pre-ship checklist). When any of them disagree with `landing.css`, `landing.css`
wins and the other is stale — fix it.

---

## 2. Standing founder rules

These come from the founder directly and persist across sessions. Full text and
the reasoning behind each: `docs/HANDOFF.md` §2 and §2a.

- **No Claude or Anthropic attribution, anywhere.** Not in commits, not in PR
  bodies, not in code comments, not in any output. No `Co-Authored-By`, no
  "Generated with", no 🤖. Authorship is
  `--author="Saido Labs LLC <info@saidolabs.com>"`; the committer stays the
  user's own git identity.

- **The twelve banned words never render.** `ICP`, `variant`, `A/B`,
  `adversarial`, `cohort`, `arena`, `lens`, `archetype`, `canonical`,
  `valence`, `simulation`, `project` — plurals and case-insensitive. A founder
  has a *product* and a *workspace*; a consultant has projects, and the noun
  decides who the page thinks it is talking to. Enforced by
  `frontend/src/test/ia.test.ts`.

- **No `disabled` attributes on the rail.** A control either runs and states
  what its answer will be missing, or it is blocked with the button that
  unblocks it, and the reason beside it. There is no third rendering, so there
  is no grey button.

- **Every `EmptyState` carries an action.** The prop is required and the type
  refuses a screen without one. A dead end is a defect.

- **Update the five living logs in the same batch as the change they describe** —
  `docs/ARCHITECTURE_LOG.md`, `docs/INFRA_LOG.md`, `docs/DECISIONS_LOG.md`,
  `docs/CRITICS_LOG.md`, `docs/SKILLS_LOG.md`. Whichever ones a change touches,
  updated with it, not afterwards.

- **Grep before you claim, query before you assert.** A statement about this
  codebase that has not been checked is a guess, and writing it into a doc or a
  comment turns a guess into a fact the next session inherits.

- **Nothing is deleted without first grepping** for direct calls, type
  references, string literals, dynamic imports, re-exports and tests.

---

## 3. Verification gate

Frontend, from `frontend/`:

```
npm run build          # tsc -b && vite build — what Render runs
npx eslint src --quiet
npx vitest run
```

> ⚠️ Gate the frontend with `npm run build`, **never `tsc --noEmit` alone.**
> They are not the same check. Render runs `tsc -b && vite build`, and project-
> references build mode rejects things `--noEmit` accepts. A deploy once
> exposed five pre-existing `tsc -b` errors the documented gate had been
> stepping over, while Render served a stale bundle and every session reported
> a clean frontend.

Backend, from `backend/`: `pytest` and `ruff check app tests`.

**A check that can pass for the wrong reason is worse than no check.** Deploy
verification uses a discriminator only the new build can produce. Visual claims
are verified by reading a rendered screenshot, not by a green build.
