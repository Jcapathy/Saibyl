import type { CSSProperties, ElementType, ReactNode } from 'react';

import { cn } from '@/lib/utils';

import { cardSurface, dealDelayMs, type CardCarries } from './surfaces';

import './design.css';

/**
 * The design system, as the six pieces every screen is built from.
 *
 * The system was approved on the canvas (`design/canvas.json`) and drawn in
 * `design/Main.dc.html`; it came from the landing page (`pages/landing.css`).
 * The founder wrote four rules, and these components are how the app keeps
 * them without every page re-deciding:
 *
 *   1. Radial washes on the ground              → `Ground` (and <body>)
 *   2. Soft shadows on cards that carry meaning,
 *      hairlines on dense lists                 → `Card carries=…`
 *   3. The dotted eyebrow on every mono label   → `Eyebrow`
 *   4. One Playfair italic phrase per heading    → `PageHeader phrase=…`
 *
 * And the motion note: "the rail deals its five steps, then the open stage
 * arrives. Every artboard collapses its animation under prefers-reduced-motion,
 * exactly as the landing page does." → `Deal`, `Rise`, and `design.css`.
 *
 * There is a fifth rule the canvas states as a constraint rather than a change,
 * and it is the one most likely to be broken by a shared component library:
 *
 *   "Density is deliberately unchanged. Same type sizes, same 13px body, same
 *    row rhythm — warmth comes from ground, depth and one accent phrase, not
 *    from spacing things further apart. An app that reads like a marketing page
 *    is the opposite failure."
 *
 * So nothing here sets padding or a row height, and the two heading sizes below
 * are the app's existing `.text-h1` / `.text-h2` values spelled out. A page
 * adopting these primitives should look warmer and take up exactly as much
 * room as it did before.
 *
 * This supersedes `components/capital/CapitalPrimitives.tsx`'s `MonoLabel` and
 * `capital.css`, which ported the same system to one page while the app-wide
 * restyle was in other hands.
 */

/* ------------------------------------------------------------------ */
/*  Rule 1 — the ground                                                */
/* ------------------------------------------------------------------ */

/**
 * The washed ground, for an element that paints its own page background.
 *
 * `index.css` already washes <body>, so most screens need nothing. This is for
 * the ones that lay an opaque panel over it — a full-bleed page root, a modal
 * surface — where the wash would otherwise be covered and the screen would go
 * back to the flat `#f8fbff` the canvas is complaining about.
 */
export function Ground({
  children,
  className,
  as = 'div',
}: {
  children?: ReactNode;
  className?: string;
  as?: ElementType;
}) {
  const Tag: ElementType = as;
  return <Tag className={cn('sb-ground', className)}>{children}</Tag>;
}

/* ------------------------------------------------------------------ */
/*  Rule 3 — the dotted eyebrow                                        */
/* ------------------------------------------------------------------ */

/**
 * A mono label wearing its dot. Canvas rule 3: "the dotted eyebrow on every
 * mono label."
 *
 * "Every" wants one qualifier, and it is the same one the capital module
 * settled on: the dot marks where a *block begins*. A section label gets one;
 * the 9.5px captions inside a card — a stat's term, the speaker above a quote —
 * do not, because dotting each of them turns a dense record into a
 * constellation while the density constraint says not to. Every section label
 * in the app should come through here, so there is one place to change if that
 * reading is ever overruled.
 *
 * `live` is the artboard's pulsing dot over an open stage. It is a state — "this
 * is running" — not decoration, and it stops meaning anything the moment a
 * static surface wears it.
 */
export function Eyebrow({
  children,
  live = false,
  className,
}: {
  children: ReactNode;
  live?: boolean;
  className?: string;
}) {
  return (
    <p
      className={cn(
        'sb-eyebrow font-mono text-[10px] uppercase tracking-[0.16em] text-saibyl-muted',
        live && 'sb-eyebrow-live',
        className,
      )}
    >
      {children}
    </p>
  );
}

/* ------------------------------------------------------------------ */
/*  Rule 4 — one accent phrase, and where a screen says what it is     */
/* ------------------------------------------------------------------ */

/**
 * The top of a screen: what it is called, how far along it is, and the one
 * serif line that carries the warmth.
 *
 * Canvas rule 4 is "One Playfair italic phrase per major heading", and `phrase`
 * is how that stays true. It is typed as a single optional `string` — not a
 * `ReactNode`, not an array — so "one" is a fact about the type rather than a
 * convention somebody remembers. The accent budget for a heading is spent here;
 * no other primitive in this module renders Playfair, and a page should not add
 * a second serif line beside a `PageHeader` that already has one.
 *
 * It sits on its own line under the heading rather than inside it, which is the
 * artboard's arrangement ("Audience" over *"Who is going to react to this?"*).
 * The landing page can put an `<em>` mid-sentence because its headings are
 * sentences; the app's are mostly proper nouns — a product name, "Your reports"
 * — and there is nowhere inside those for a clause to go.
 *
 * `mark` is the artboard's line beside the title: "2 of 5 steps have what they
 * need". `children` is the explanatory paragraph — what this stage is for, in
 * the words a founder arriving on it would use.
 *
 * **Order: eyebrow, title, explanation, then the phrase.** The phrase is the
 * tagline the explanation earns, so it reads last and it reads large. See the
 * comment at the render site for why this is the one place the canvas's density
 * constraint is deliberately not applied.
 */
export function PageHeader({
  eyebrow,
  live = false,
  title,
  phrase,
  mark,
  children,
  level = 1,
  className,
}: {
  /** The dotted mono label above the title. */
  eyebrow?: ReactNode;
  /** Pulse the eyebrow's dot — only where the surface is genuinely live. */
  live?: boolean;
  title: ReactNode;
  /** The one Playfair italic line. One per heading; the type enforces it. */
  phrase?: string;
  /** Progress or scope, beside the title: "2 of 5 steps have what they need". */
  mark?: ReactNode;
  /** The explanatory paragraph, at the app's 13px body size. */
  children?: ReactNode;
  level?: 1 | 2;
  className?: string;
}) {
  const Heading: ElementType = level === 1 ? 'h1' : 'h2';

  /*
    The app's existing `.text-h1` / `.text-h2` values, spelled out as utilities
    rather than used by name. Two reasons, and neither is taste: `cn` runs
    `twMerge`, which reads `text-h1` as a text *colour* and would silently drop
    it next to `text-saibyl-ink`; and spelling the numbers here makes it
    obvious that this primitive changed nothing about type size, which is the
    density constraint's whole point.
  */
  const headingClass =
    level === 1
      ? 'text-[2rem] font-extrabold tracking-[-0.035em]'
      : 'text-[1.375rem] font-bold tracking-[-0.02em]';

  return (
    <header className={className}>
      {eyebrow && <Eyebrow live={live}>{eyebrow}</Eyebrow>}

      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 mt-2">
        <Heading className={cn('font-display text-saibyl-ink', headingClass)}>
          {title}
        </Heading>
        {mark && <span className="text-[12px] text-saibyl-muted">{mark}</span>}
      </div>

      {/* The explainer comes first, and the accent phrase lands under it.
          Reversed until 2026-08-23, when the founder read the live pages: a
          15px serif line sitting above a 13px paragraph reads as a subtitle to
          the heading rather than as the thing the page is about, and he could
          not comfortably read either on his own monitor. Explanation, then the
          line that sums it up — the arrangement of a page that has to teach a
          stage to someone who has just arrived on it. */}
      {children && (
        <div className="mt-3 max-w-2xl text-[14px] sm:text-[15px] leading-relaxed text-saibyl-muted">
          {children}
        </div>
      )}

      {phrase && (
        /* The one density exception in the system, and a deliberate one.
           The canvas's constraint — "same type sizes, same 13px body" — is
           about the app's dense surfaces: rows, cards, lists, where growing
           the type would turn a record into a brochure. A stage page's opening
           block is not a dense surface. It is the page's front door, and the
           canvas itself names the accent phrase as where warmth is allowed to
           come from. Sized down rather than fixed, because the complaint named
           mobile first. */
        <p className="mt-4 max-w-3xl font-serif text-[20px] sm:text-[23px] lg:text-[26px] italic leading-snug text-saibyl-violet">
          {phrase}
        </p>
      )}
    </header>
  );
}

/* ------------------------------------------------------------------ */
/*  Rule 2 — depth means meaning                                       */
/* ------------------------------------------------------------------ */

/**
 * A card, which must say what it carries before it is given any depth.
 *
 * Canvas rule 2: "Soft blue shadows on cards that carry meaning — hairlines
 * stay on dense lists." `carries` is required and has no default, because a
 * default is the guess this prop exists to prevent: the first busy afternoon,
 * every card takes the default, and depth stops meaning anything.
 *
 *   `carries="stage"`    the one panel this screen is about — once per screen
 *   `carries="meaning"`  a card holding a claim a founder has to weigh
 *   `carries="density"`  a row in a dense list, or a step in the rail. Hairline.
 *
 * It paints border, radius, ground and depth — and no padding. Padding stays in
 * the caller's `className` exactly as it is today, because the canvas says
 * density does not change and a shared card that re-pads every call site is the
 * fastest possible way to break that everywhere at once.
 *
 * `lift` is the artboard's hover rise, and belongs only on a card that goes
 * somewhere. On a card that cannot be clicked the lift is a promise the surface
 * does not keep.
 */
export function Card({
  carries,
  lift = false,
  as = 'div',
  className,
  style,
  children,
}: {
  carries: CardCarries;
  lift?: boolean;
  as?: ElementType;
  className?: string;
  style?: CSSProperties;
  children?: ReactNode;
}) {
  const Tag: ElementType = as;
  return (
    <Tag className={cn(cardSurface(carries), lift && 'sb-lift', className)} style={style}>
      {children}
    </Tag>
  );
}

/* ------------------------------------------------------------------ */
/*  Motion — one arrival per screen                                    */
/* ------------------------------------------------------------------ */

/**
 * One item in a dealt sequence. The rail's five steps are what it was drawn for.
 *
 * "The rail deals its five steps, then the open stage arrives" — the canvas's
 * motion note. Each item is delayed by its `index`, at the artboard's own 70ms,
 * and the stagger is capped inside {@link dealDelayMs} so a long list never
 * makes a founder wait for its tail.
 *
 * Collapses to nothing under `prefers-reduced-motion` — see `design.css`.
 */
export function Deal({
  index = 0,
  as = 'div',
  className,
  style,
  children,
}: {
  /** Position in the sequence. Item 0 arrives immediately. */
  index?: number;
  as?: ElementType;
  className?: string;
  style?: CSSProperties;
  children?: ReactNode;
}) {
  const Tag: ElementType = as;
  return (
    <Tag
      className={cn('sb-deal', className)}
      style={{ animationDelay: `${dealDelayMs(index)}ms`, ...style }}
    >
      {children}
    </Tag>
  );
}

/**
 * The stage arriving, after the deal.
 *
 * `delayMs` is usually `dealDelayMs(n + 1)` where `n` is the number of items
 * dealt beside it — which is how the artboard gets its 420ms for a rail of
 * five. Left at 0 it simply rises on load, which is right for a screen with
 * nothing to wait for.
 *
 * Collapses to nothing under `prefers-reduced-motion` — see `design.css`.
 */
export function Rise({
  delayMs = 0,
  as = 'div',
  className,
  style,
  children,
}: {
  delayMs?: number;
  as?: ElementType;
  className?: string;
  style?: CSSProperties;
  children?: ReactNode;
}) {
  const Tag: ElementType = as;
  return (
    <Tag
      className={cn('sb-rise', className)}
      style={{ animationDelay: `${Math.max(0, delayMs)}ms`, ...style }}
    >
      {children}
    </Tag>
  );
}
