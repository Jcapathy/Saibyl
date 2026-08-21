# The Saibyl design guide

**One system, three surfaces: the public page, the app, and anything a founder
exports.** This file exists because the third surface kept drifting — an
exported report is the artifact most likely to be forwarded to somebody who has
never seen the app, and it was the only surface with no brand on it at all.

Written 2026-08-20. The source of truth for values is
`frontend/src/pages/landing.css` (the approved system) and
`frontend/tailwind.config.js` (its app-wide token remap). **When they disagree
with this file, they win and this file is stale — fix it.**

---

## The tokens

| Role | Value | Notes |
|---|---|---|
| Paper (ground) | `#f8fbff` | plus radial washes — see below |
| Ink (primary text) | `#14294a` | |
| Secondary text | `#44587a` | |
| Muted text | `#60718e` | **the floor.** 4.7:1 on paper; never lighter for reading text |
| Hairline | `rgba(38,79,139,.14)` | borders, dividers |
| **Blue — the one accent** | `#286cf0` | actions, and only actions |
| Blue, deep | `#1e5ad9` | hover |
| Violet | `#8b73ee` fill · `#6a4fe0` text | emphasis, the serif phrase |
| Cyan | `#35c7d5` | the eyebrow dot, data series |
| Green | `#2fbf8a` fill · `#0e7d55` text | positive |
| Amber | `#f59e0b` fill · `#b45309` text | caution (app only — the landing page has none) |
| Rose | `#ff6e79` fill · `#d92d3c` text | negative |

**The bright/dark pairs are not interchangeable.** The bright value is a fill,
a dot or a bar; the dark value is the same meaning as *text*. Using a fill hue
for small text is the contrast failure this system has already shipped twice.

**Colour is identity and meaning, never decoration.** A tinted number is a
claim that the number means something. When in doubt, ink.

## The type

- **Manrope** — everything, with tight negative tracking on display sizes
  (`-.045em` at 34px, `-.055em` at 38px).
- **Playfair Display, italic** — *at most one phrase per major heading.* This
  is the brand's signature and its scarcity is the point; a critic called its
  overuse "a metronome" and the landing page was cut back because of it.
- **DM Mono** — eyebrows, labels, metadata, and any column of digits (with
  `tabular-nums`).

## The four things that make a surface feel like Saibyl

Applied to the app on 2026-08-20 after the founder's read that the modules were
"sterile — a doctor's exam room" while the landing page looked right. The gap
was measurable: the landing page used 4 radial washes, 6 serif accents and 37
soft shadows; the app's rail used **zero of each**.

1. **A washed ground, not flat paper.**
   ```css
   radial-gradient(circle at 87% 1%, rgba(127,184,255,.19), transparent 22rem),
   radial-gradient(circle at 2% 26%, rgba(143,119,245,.10), transparent 26rem),
   #f8fbff
   ```
2. **Soft blue shadows on cards that carry meaning** —
   `0 22px 60px rgba(52,96,164,.12)` for a hero card,
   `0 14px 44px rgba(57,91,146,.06)` for a panel. **Hairlines stay** on dense
   lists and tables: shadow every row and the page turns to soup.
3. **The dotted eyebrow.** Every mono label gets it:
   ```css
   width: 7px; height: 7px; border-radius: 50%;
   background: #35c7d5; box-shadow: 0 0 0 5px rgba(53,199,213,.12);
   ```
4. **One serif italic phrase** in the biggest heading on the screen. One.

**What does not change: density.** Same 13px body, same row rhythm, same
control heights. Warmth comes from ground, depth and one accent phrase — not
from pushing things apart. An app that reads like a marketing page is the
opposite failure.

## Motion

Reuse the landing page's own keyframes; do not invent a second vocabulary.
Durations and easing live in `landing.css` and are mirrored in
`design/*.dc.html`:

| Motion | Spec |
|---|---|
| Orbits | 20s and 25s linear, counter-rotating |
| Floating card | 6s ease-in-out |
| Drifting chips | 5s ease-in-out, staggered by negative delay |
| Live dot | 1.7s blink |
| Arrival | `.5s cubic-bezier(.22,.61,.36,1)`, staggered ~70–120ms |
| Hover lift | `translateY(-2px)`, `.22s ease` |

**One orchestrated moment per screen, not scattered micro-interactions.** And
every surface collapses under `prefers-reduced-motion: reduce` — the landing
page does, so everything does. This is not optional.

---

## Exported reports — the surface that gets forwarded

A founder's exported PDF is read by their co-founder, their investor and their
customer. It carries the brand or it carries nothing.

**Where it lives:** `backend/app/services/export/print_stylesheet.py` (the
paged-media stylesheet) and `report_document.py` (the document, including the
cover). Both feed `pdf_exporter.py` → WeasyPrint.

**What the brand is on paper:**

- The lockup, exactly as the product writes it: the gradient mark tile, the
  mixed-case wordmark **Saibyl**, and `BY SAIDO LABS` in mono beneath. It was
  spaced-out all-caps `SAIBYL`, which appears nowhere else in the product.
- The palette above, pulled toward print: `_INK`, `_ACCENT`, `_VIOLET` in the
  stylesheet are the product's ink, blue and violet.
- One serif italic phrase on the cover heading, same rule as everywhere.

**Three constraints that are not style preferences:**

1. **Greyscale must lose nothing.** No two things may be distinguished by hue
   alone. Colour on paper is identity; meaning is carried by position, weight
   and label. A report is printed in black and white more often than anyone
   admits.
2. **Fonts degrade, identity does not.** The Docker image installs only
   `fonts-liberation` and `fonts-dejavu-core`, so Manrope / Playfair / DM Mono
   are named first in the stacks and fall back today. The identity rests on
   colour, layout and the lockup, which always render. *Open decision: install
   the three brand faces in the image (a Dockerfile change and ~2MB) and the
   exports become typographically on-brand too.*
3. **Body type never drops below 9pt**, and hairlines never below 0.4pt — they
   vanish on paper.

**When you add a new exportable artifact** — the messaging doc, the outbound
sequence, the capital shortlist all become documents a founder sends onward:

- Render it through `print_stylesheet.build_stylesheet()`. Do not write a
  second stylesheet; a second stylesheet is a second brand within a month.
- Reuse `_cover()`'s lockup markup verbatim.
- Add a test asserting the lockup and the accent are present in the built CSS,
  so the brand is a thing that fails a test rather than a thing somebody
  remembers.

## The one export that must NOT look like Saibyl

The redesigned page we hand a client is the exception, and the exception is
load-bearing. Every other artifact in this document carries our identity
because it is ours. The client's new homepage is *theirs* — stamping our
palette on it would be selling every founder the same website, which is the
failure the Website Gauntlet exists to fix.

So the split is:

- **`index.html`** — the client's page, in the client's design language. No
  Saibyl mark, no Saibyl palette, no attribution in the markup.
- **`STYLE_GUIDE.md`** — ours, and signed. It describes their page; the
  Saibyl line sits at the bottom where a colophon belongs.

**Where it lives:** `backend/app/services/website/style_guide.py` renders the
guide; `GET /website/revision/{id}/bundle` zips the pair; `SiteRevision.tsx`
offers the download. Nothing on that path calls a model — a founder who paid
for the revision pays nothing to take it away, and a guide that costs nothing
to regenerate stays true after the next edit.

**The rule that makes the guide worth shipping: every value is read out of
the delivered HTML.** Colours, faces, radii and shadows are extracted from the
file itself, so the guide and the page cannot disagree — which is the failure
mode of every style guide written *alongside* a design rather than *from* one.
Where a value is absent the section is omitted rather than filled with a
plausible default; a founder handing this to a designer has no way to tell an
invented line from a measured one, so there must be no invented lines.

**Category is an argument, not a lookup table.**
`backend/app/services/website/verticals.py` decides what a medical SaaS page
must prove versus a fintech page, and it does so in terms of *who signs the
cheque, what they must believe, and what the page has to carry* — never in
hex values or font names. A test asserts no brief contains a literal colour
or size, because the moment that file starts naming palettes per industry it
has become the stereotype generator it exists to prevent. When the copy spans
two categories or establishes none, it refuses and falls back to general:
a confidently wrong brief is worse than no brief.

**When you add another client-facing deliverable** (the messaging doc's
one-pager, an exported deck), decide first whose artifact it is. Ours gets the
lockup. Theirs gets their own design and a signed colophon — never both.

## The repeatable check, before any surface ships

1. Does it use the washed ground, or flat paper by accident?
2. Is every mono label wearing its dot?
3. Is there exactly one serif italic phrase — not zero, not four?
4. Is blue doing anything other than marking an action?
5. Is any small text using a fill hue instead of its text pair?
6. Does it collapse under `prefers-reduced-motion`?
7. If it can be exported: does it carry the lockup, and does it survive
   greyscale?
8. If it is the *client's* artifact rather than ours: does it carry none of
   our palette, and a signed colophon rather than a mark?

Failing one of these is the difference between "looks like Saibyl" and "looks
like a competent dialect of Saibyl", which is what a blind critic called the
app before this pass.
