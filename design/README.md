# `design/` — the approved canvas

**This folder is the source of truth for every surface behind the login.**

The founder approved it on 2026-08-20. Four artboards plus `canvas.json`, whose
`annotations` array states the rules in his words. Read `canvas.json` first; it
is short, and it is the spec. Everything below is a guide to the artboards that
illustrate it.

Three days after this was approved, a session shipped two brand-new app pages
without opening this folder, because nothing in the repo pointed here. The
founder found the drift himself on his first read-through of the site. That is
why the root `CLAUDE.md` now points at this file, and why
`frontend/src/test/ia.test.ts` fails when a page renders a heading without
composing the shared design primitives.

---

## The rules, quoted

From the `brief` annotation in `canvas.json`:

> The four changes, applied everywhere:
>
> 1. Radial washes on the ground (the app is flat #f8fbff today)
> 2. Soft blue shadows on cards that carry meaning — hairlines stay on dense lists
> 3. The dotted eyebrow on every mono label
> 4. One Playfair italic phrase per major heading
>
> The rail artboard has a Warm toggle above it — flip it off to see exactly
> what ships today.
>
> MOTION: reload an artboard to replay it. The rail deals its five steps, then
> the open stage arrives. Every artboard collapses its animation under
> prefers-reduced-motion, exactly as the landing page does.

From the `density` annotation:

> Density is deliberately unchanged. Same type sizes, same 13px body, same row
> rhythm — warmth comes from ground, depth and one accent phrase, not from
> spacing things further apart. An app that reads like a marketing page is the
> opposite failure.

**Motion is part of the approval, not a garnish on top of it.** Each artboard
declares its keyframes at the top of its `<style>` block, and they are the
landing page's own — same names, same durations, same easing. A screen that
adopts the palette and drops the movement has implemented half the design. Every
artboard also carries the `prefers-reduced-motion: reduce` block that collapses
all of it; so does every screen you build.

---

## What each artboard specifies

### `Main.dc.html` — the rail, with a step open

The app shell: glass sidebar, the lockup with `BY SAIDO LABS` in mono beneath
it, the credits meter, the five steps as a column of cards, and one step opened
beside them.

It is the only artboard with a **`warm` toggle** (a boolean prop, top of the
`renderVals()` block). Flipped off, every one of the four changes reverts and
you are looking at exactly what shipped before the approval — flat `#f8fbff`,
no card shadow, no eyebrow dot, the step's question in sans rather than serif
italic. That comparison is the artboard's real payload: the change is
demonstrable rather than described.

Motion: the five steps **deal** in sequence, 70ms apart (`sb-deal`), then the
open stage **rises** at `.42s` (`sb-rise`). The live dot pulses. Steps lift
`translateY(-2px)` on hover, because the rail is navigation and navigation
should feel touchable.

### `Report.dc.html` — the report, the room made visible

The one worth arguing about. From the `the-room` annotation:

> The landing page's hero is a room of buyers orbiting a pitch. Inside the app,
> where the founder has actually paid for a room, the room has always been a
> table of numbers.
>
> This puts it where it was bought. Same measured values underneath — nothing
> here is decoration standing in for data.
>
> It moves the way the landing page moves: the same keyframes, same durations.
> Orbits turn (20s and 25s, counter-rotating), the pitch floats at its centre,
> the buyers drift, the live dot blinks. Then the objections land underneath,
> one at a time, and the measured numbers follow.
>
> **That sequence IS the product: the room assembles, argues, and reports — in
> that order.**

Concretely: a washed hero card holds two counter-rotating orbits, a floating
gradient core carrying the pitch, buyer chips drifting on staggered negative
delays, and a tilted card listing what the room pushed back on with a blinking
live dot. Four stat cards land underneath, last. The heading carries the single
serif italic phrase; the eyebrow carries its cyan dot.

### `Answers.dc.html` — the objection matrix

Objections in the order the room said they matter, hardest first. Each row is a
soft-shadow card: a colour chip, the objection, how many buyers raised it, then
**the buyer's own sentence** set in italic behind a violet rule, then the moves
to make in a two-column grid, then an amber "when to walk" strip where one
applies. Below the rows, a "what they are really choosing between" pair, each
naming honestly where the rival wins.

Motion: the quote is the moment. The row rises, then the quote writes itself in
from the left (`sb-quote`) while the violet rule draws downward (`sb-sweep`) —
because the quote is what makes the row credible.

### `Next.dc.html` — what this room could not tell you

The offer block that follows a run: one washed card, the serif italic phrase in
the heading, and three cards — the ownership check, the answers, the page read
— each with a glyph tile, a plain-language title, the price in mono, and a
gradient action. Prices are stated on the card, charged once when the work
starts.

Motion: the three cards arrive in sequence (60/160/260ms) and lift when a hand
comes near. An offer's motion is an invitation, not a flourish.

---

## How to read a `.dc.html`

Each artboard is one standalone HTML file that holds both its markup and its
data. Reading it top to bottom:

1. **`<helmet><style>`** — the keyframes and classes for that board, with the
   `prefers-reduced-motion` collapse at the bottom. Read this first: it is the
   motion spec in the smallest possible form.
2. **The markup**, inside `<x-dc>`. Ordinary HTML with inline styles, so every
   value the design uses is visible in place rather than hidden behind a class
   name. `{{token}}` placeholders bind to the data below. `<sc-for list="{{xs}}"
   as="x">` repeats its child once per item; `<sc-if value="{{flag}}">` renders
   its child conditionally.
3. **`<script data-dc-script>`** — a `DCLogic` subclass whose `renderVals()`
   returns every `{{token}}`. The `data-props` attribute declares the editable
   knobs (`Main`'s `warm` boolean, the others' accent colours). The comments in
   here explain *why* a value is what it is; they are the most useful prose in
   the folder.

**To see them rendered and animated**, open `saibyl-warmth.html` in a browser —
the published canvas, which packages the runtime and all four artboards in one
self-contained page, laid out per `canvas.json`. It is **gitignored** (2MB, and
regenerable), so a fresh clone will not have it; ask the founder for the file,
or read the artboards as source. The four `.dc.html` files and `canvas.json`
are what is tracked, and they are what is authoritative.

The `.dc.html` files reference `./support.js`, the canvas runtime, which lives
inside `saibyl-warmth.html` rather than beside them — so opening a single
artboard file on its own shows unresolved `{{token}}` markup, not the design.
That is expected; read it as source.

---

## Where this system came from, and where the values live

`frontend/src/pages/landing.css` is the origin. The light editorial system was
built there for the public page, the founder approved it there, and then said he
wanted the whole site to have that look. **It is the source of truth for
values** — tokens, durations, easing. Where this folder, `docs/DESIGN_GUIDE.md`
and `landing.css` disagree, `landing.css` wins and the other two are stale.

- `docs/DESIGN_GUIDE.md` — the written-out system: the token table with its
  bright-fill / dark-text pairs, the type rules, the motion table, the export
  and client-artifact rules, and the eight-point check to run before any
  surface ships.
- `frontend/src/components/design/` — the shared primitives that carry the four
  rules in code. New pages compose these. Do not hand-roll a washed ground, a
  dotted eyebrow, a soft-shadow card or a serif-italic heading in page code.
- `frontend/src/test/ia.test.ts` — the ratchet. Pages that predate the sweep
  are named in an allow-list that may only ever shrink.
