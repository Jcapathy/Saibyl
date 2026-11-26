# Saibyl design rules

Moved word for word from section 1 of the previous CLAUDE.md on 2026-11-26. CLAUDE.md imports this file, so it loads every session.

## 1. Any UI or frontend work reads `design/` first

**Before writing a line of frontend code — a new page, a new panel, a restyle,
a chart — open `design/` and read it.** Start with `design/README.md`, then the
four artboards. They are self-contained HTML: open them in a browser.

### The artboards are the spec. The annotations are a change list.

**Read the four `.dc.html` files, not just `canvas.json`.** This distinction is
the whole of this section, and getting it wrong has already cost two rounds of
work.

`canvas.json`'s `annotations` array says *"The four changes, applied
everywhere"* — **changes**, meaning the delta between the artboards and what
shipped on 2026-08-20. It is not the specification. The artboards are, and they
carry far more than four rules: eight distinct gradients, layered depth with
inset highlights, radii scaled per element from 11px to 36px, colour that
carries state, hover lift on anything touchable, and continuous motion
alongside entrance motion.

An earlier version of this file called the annotations "the design law". Every
page built under that sentence came out with washes, shadows, a dotted eyebrow
and a serif phrase applied to flat white cards — and the founder's word for the
result, on 2026-08-23, was **"sterile."** He was right, and the sentence was
wrong. If you only apply the four rules below, you will reproduce that.

This section exists at all because the folder was ignored outright once: three
days after the canvas was approved, a session built two brand-new app pages
without ever opening it, because nothing in the repo pointed at it. The founder
found the drift himself. **You are the reason this file exists.**

### The four changes, quoted from the canvas annotation

The floor, not the ceiling — what was missing that day:

> The four changes, applied everywhere:
>
> 1. Radial washes on the ground (the app is flat #f8fbff today)
> 2. Soft blue shadows on cards that carry meaning — hairlines stay on dense lists
> 3. The dotted eyebrow on every mono label
> 4. One Playfair italic phrase per major heading

### The vocabulary the artboards carry beyond those four

Read off the artboards themselves. These are what stop a page reading as a
wireframe wearing a wash:

- **Gradients are structural, not decorative.** The primary action is
  `linear-gradient(135deg,#286cf0,#5268e9)` with a coloured glow
  (`0 8px 18px rgba(40,108,240,.22)`), never a flat fill. Accents are
  `(135deg,#35c7d5,#2f8fef)` and `(135deg,#8b73ee,#6a4fe0)`. A card that
  matters has a ground of its own — the room is
  `linear-gradient(180deg,#edf5ff 0%,#f8fbff 87%)`, not white.
- **Depth is layered.** Outer shadow *plus* an inset highlight
  (`inset 0 1px rgba(255,255,255,.35..42)`), at four different intensities
  depending on how much the element matters.
- **Colour carries state.** A missing input is a violet block —
  `rgba(139,115,238,.07)` on `rgba(139,115,238,.30)`, heading `#6a4fe0` — not
  grey text. Live things pulse cyan `#35c7d5` behind a ring. Accent dots glow
  (`0 0 15px`).
- **Anything touchable lifts**: `transform: translateY(-2px)` over 220ms.
- **Radii scale with the element**: 11–14px chips, 16–20px cards, 28px on a
  full-width stage, 36px on the pitch itself.
- **Some things sit off-axis.** The buyer chips and the console are rotated a
  degree or two. Nothing in a real room is aligned to a grid.

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

**Superseded for the page frame, later the same day. Read this before you
"restore" anything.**

The canvas closes with *"An app that reads like a marketing page is the opposite
failure."* The founder read the swept app against the public site and reversed
that, in these words: the app was **"very sterile, mechanical, and looks
AI-generated"**, and the instruction was to *"treat each clickable page like a
landing page that has the same feel as the primary landing page. Hero section,
large type font, then scroll for information. As a user is scrolling, various
cards, text, information, or graphics will fade in."*

So a page opens like the landing page: `Longform` → `Hero` → `Chapter`, with
`Reveal` on anything that should arrive on scroll. **`How this works`
(`GuidePage.tsx`) is the built example — copy its shape.**

What did **not** change is everything inside a chapter. A card, a row, a table
and a list are exactly as dense as they were, and the canvas's constraint still
governs them. The frame grew; the work did not. `design_primitives.test.ts` §6
enumerates every selector in `design.css` allowed to set a size or a padding —
adding a card to that list is a failure, not a fix.

**On "one gradient action per screen":** that rule was written for a page you
see all of at once, and a longform page is not one. The landing page carries
nine call-to-action buttons — one pair in the hero and the same ask again at the
close — because a reader who has scrolled a thousand pixels should not have to
scroll back. So: **one primary per viewport, and the same ask may be repeated at
the foot of the page.** Two different gradient actions competing in one chapter
is still the failure the rule is about.

Every hero and chapter value is **copied from `pages/landing.css`**, and §7
asserts it value-for-value. Do not invent a hero size; if the landing page
changes, that test tells you what to update. The scroll reveal is one shared
implementation — `components/design/useReveal` — which `LandingPage` also calls,
so the public site and the app cannot drift.

**The earlier exception, granted the same day: `PageHeader`.**
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

