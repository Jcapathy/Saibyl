# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# build_stylesheet(client_line: str) -> str
# BASE_PT, LEAD_PT
# ─────────────────────────────────────────────────────────
"""The print stylesheet: US Letter, real margins, real page furniture.

This is a *paged media* stylesheet, not a web stylesheet with a print block
bolted on. Everything below is something WeasyPrint implements from CSS Paged
Media and CSS Fragmentation, and nothing here has a screen equivalent:

* **`@page` with named margin boxes.** The running header and footer live in the
  page margin, outside the text block, so they cannot collide with content and
  do not consume flow. This is what "padding for header and footer" means on
  paper: the margin box is drawn in reserved space that the body never enters.

* **Named pages.** `page: cover` gives the front page its own geometry and
  suppresses the furniture, so page one is a cover rather than page one of the
  body with a bigger heading.

* **`counter(page)` / `counter(pages)`.** "Page 4 of 17" requires the formatter
  to know the document's final length, which only a paged renderer does.

* **`target-counter()`.** The contents page prints the page number each section
  actually landed on, resolved after pagination. A hand-maintained contents page
  is a contents page that is wrong by the second edit.

* **`break-*`, `orphans`, `widows`.** A figure, table or callout that splits
  across a page break is the defect the user reported. `break-inside: avoid` on
  every atomic block and `break-after: avoid` on every heading is the fix, and
  it is enforced by the fragmenter rather than by luck.

**Baseline rhythm.** Body text is 9.5pt on a 13.5pt line. Every vertical margin
in the document is a multiple of 6.75pt — half a line — so blocks land on a
consistent grid instead of drifting a few points per element. Type sized for a
screen (16px ≈ 12pt) is oversized on paper; 9.5pt with generous leading is the
size a printed report is actually set at.

**Greyscale.** The palette is a neutral ink scale with a single restrained navy
used for rules and section numbers. Nothing in the document distinguishes two
things by hue alone, so a greyscale print loses no information.
"""
from __future__ import annotations

BASE_PT = 9.5
LEAD_PT = 13.5

# ── The brand, on paper ──────────────────────────────────────────────────
#
# These are the Saibyl light-system values (`frontend/src/index.css`, and the
# landing page's own tokens), pulled toward print: the ink is the product's
# ink, and the accent is the product's blue rather than the generic navy this
# file shipped with. An exported report is the artifact a founder forwards to
# somebody who has never seen the app — it should look like it came from the
# same company as the page they signed up on.
#
# The greyscale rule from this module's docstring still governs: no two things
# are distinguished by hue alone, so a black-and-white print loses nothing.
# Colour here is identity, never information.
_INK = "#14294a"       # the product's ink
_INK_MID = "#44587a"
_INK_SOFT = "#60718e"  # the muted tier; ≥4.5:1 on white
_RULE = "#c5d2e4"
_RULE_SOFT = "#e2e9f3"
_ACCENT = "#286cf0"    # the one accent. Prints as a mid grey; never load-bearing.
_ACCENT_DEEP = "#1e5ad9"
_VIOLET = "#6a4fe0"    # the emphasis hue, for the cover's one serif phrase
_WASH = "#f4f7fc"      # the paper tint, on the ground

# Brand faces first, container-safe faces behind them.
#
# The Docker image installs `fonts-liberation` and `fonts-dejavu-core` and
# nothing else, so today these stacks resolve to the same faces they always
# did — naming the brand faces first costs nothing and means the real type
# appears anywhere they are present (local runs, and the container the day
# somebody installs them). The identity above does not depend on it.
_SERIF = '"Playfair Display", "Liberation Serif", "DejaVu Serif", Georgia, serif'
_SANS = 'Manrope, "Liberation Sans", "DejaVu Sans", Helvetica, Arial, sans-serif'
_MONO = '"DM Mono", "DejaVu Sans Mono", "Liberation Mono", monospace'


def _css_string(text: str) -> str:
    """Quote a value for use inside a CSS `content` declaration."""
    escaped = str(text).replace("\\", "\\\\").replace('"', '\\"')
    escaped = escaped.replace("\n", " ").replace("\r", " ")
    return f'"{escaped}"'


def build_stylesheet(client_line: str) -> str:
    """The full stylesheet. `client_line` is the running header's left slot."""
    client = _css_string(client_line)
    return f"""
/* ── Page geometry ──────────────────────────────────────────────── */

@page {{
    size: Letter;
    /* Top margin is deep enough to hold the running head with air beneath it;
       the bottom holds the folio. The body never enters either. */
    margin: 0.92in 0.9in 0.82in 0.9in;

    @top-left {{
        content: {client};
        font-family: {_SANS};
        font-size: 6.8pt;
        letter-spacing: 0.055em;
        text-transform: uppercase;
        color: {_INK_SOFT};
        vertical-align: bottom;
        padding-bottom: 5pt;
        border-bottom: 0.5pt solid {_RULE};
        /* A running head is one line or it is not a running head. */
        white-space: nowrap;
        overflow: hidden;
    }}
    @top-center {{
        content: "";
        vertical-align: bottom;
        padding-bottom: 5pt;
        border-bottom: 0.5pt solid {_RULE};
    }}
    @top-right {{
        content: string(section);
        font-family: {_SANS};
        font-size: 6.8pt;
        letter-spacing: 0.055em;
        text-transform: uppercase;
        color: {_INK_SOFT};
        text-align: right;
        vertical-align: bottom;
        padding-bottom: 5pt;
        border-bottom: 0.5pt solid {_RULE};
        white-space: nowrap;
        overflow: hidden;
    }}

    @bottom-left {{
        content: "Confidential";
        font-family: {_SANS};
        font-size: 6.4pt;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        color: {_INK_SOFT};
        vertical-align: top;
        padding-top: 8pt;
    }}
    @bottom-center {{
        content: "Page " counter(page) " of " counter(pages);
        font-family: {_SANS};
        font-size: 7pt;
        color: {_INK_MID};
        vertical-align: top;
        padding-top: 8pt;
    }}
    @bottom-right {{
        content: "Saibyl · Saido Labs LLC";
        font-family: {_SANS};
        font-size: 6.4pt;
        color: {_INK_SOFT};
        text-align: right;
        vertical-align: top;
        padding-top: 8pt;
    }}
}}

/* The cover is a different kind of page, not a body page with a big title:
   its own margins, and every margin box suppressed. */
@page cover {{
    margin: 1.15in 0.9in 0.85in 0.9in;
    @top-left {{ content: none; }}
    @top-center {{ content: none; }}
    @top-right {{ content: none; }}
    @bottom-left {{ content: none; }}
    @bottom-center {{ content: none; }}
    @bottom-right {{ content: none; }}
}}

/* ── Baseline ───────────────────────────────────────────────────── */

html {{ font-size: {BASE_PT}pt; }}

body {{
    font-family: {_SANS};
    font-size: {BASE_PT}pt;
    line-height: {LEAD_PT}pt;
    color: {_INK};
    margin: 0;
    padding: 0;
}}

p {{
    margin: 0 0 {LEAD_PT / 2}pt;
    orphans: 3;
    widows: 3;
    text-align: justify;
    hyphens: auto;
}}

p:last-child {{ margin-bottom: 0; }}

strong {{ font-weight: 700; }}
em {{ font-style: italic; }}
code {{ font-family: {_MONO}; font-size: 8.4pt; }}

/* ── Headings ───────────────────────────────────────────────────── */

h1, h2, h3, h4, h5, h6 {{
    /* A heading is never the last thing on a page. */
    break-after: avoid;
    break-inside: avoid;
    page-break-after: avoid;
    margin: 0;
}}

h2.section-title {{
    font-family: {_SERIF};
    font-size: 15pt;
    line-height: 19pt;
    font-weight: 700;
    letter-spacing: -0.005em;
    color: {_INK};
    padding-bottom: 5pt;
    border-bottom: 1.2pt solid {_ACCENT};
    margin-bottom: {LEAD_PT}pt;
}}

h2.section-title .num {{
    font-family: {_SANS};
    font-size: 9pt;
    font-weight: 700;
    letter-spacing: 0.08em;
    color: {_ACCENT};
    display: block;
    margin-bottom: 2pt;
}}

/* Only the section's *name* feeds the running header. Setting the string from
   the whole `h2` swept the "Section 4" label in with it, and the top-right slot
   read "SECTION 4OBJECTIONS". */
h2.section-title .name {{
    string-set: section content(text);
}}

h3 {{
    font-family: {_SANS};
    font-size: 10.5pt;
    line-height: {LEAD_PT}pt;
    font-weight: 700;
    color: {_INK};
    margin: {LEAD_PT}pt 0 {LEAD_PT / 2}pt;
}}

h4 {{
    font-family: {_SANS};
    font-size: 9.5pt;
    line-height: {LEAD_PT}pt;
    font-weight: 700;
    color: {_INK_MID};
    margin: {LEAD_PT * 0.75}pt 0 {LEAD_PT / 4}pt;
}}

h5, h6 {{
    font-family: {_SANS};
    font-size: 9pt;
    line-height: {LEAD_PT}pt;
    font-weight: 700;
    font-style: italic;
    color: {_INK_MID};
    margin: {LEAD_PT / 2}pt 0 {LEAD_PT / 4}pt;
}}

.kicker {{
    font-family: {_SANS};
    font-size: 6.8pt;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: {_INK_SOFT};
    margin-bottom: 4pt;
}}

/* ── Sections ───────────────────────────────────────────────────── */

section.doc-section {{
    break-before: page;
    page-break-before: always;
}}

section.doc-section.flow {{
    break-before: auto;
    page-break-before: auto;
    margin-top: {LEAD_PT * 1.5}pt;
}}

/* ── Cover ──────────────────────────────────────────────────────── */

.cover {{
    page: cover;
    break-after: page;
    page-break-after: always;
}}

/* The lockup, as the product writes it: the gradient mark, the mixed-case
   wordmark, and the Saido Labs line underneath. It was set as spaced-out
   all-caps "SAIBYL", which is not how the brand is written anywhere else —
   and an exported report is the surface most likely to be forwarded to
   somebody who will never see the app. */
.cover .lockup {{
    display: flex;
    align-items: center;
    gap: 9pt;
}}

.cover .brand-mark {{
    display: inline-block;
    width: 26pt;
    height: 26pt;
    border-radius: 7pt;
    background: linear-gradient(135deg, #2f75ef 5%, #705ee3 95%);
    color: #ffffff;
    font-family: {_SERIF};
    font-size: 16pt;
    font-weight: 700;
    line-height: 26pt;
    text-align: center;
    /* Print-exact rather than a background WeasyPrint might drop when a
       driver strips backgrounds: the tile is decoration, and the wordmark
       beside it carries the identity on its own if it vanishes. */
    -weasy-print-color-adjust: exact;
}}

.cover .wordmark {{
    font-family: {_SANS};
    font-size: 15pt;
    font-weight: 800;
    letter-spacing: -0.03em;
    color: {_INK};
}}

.cover .wordmark-sub {{
    font-family: {_MONO};
    font-size: 5.6pt;
    letter-spacing: 0.09em;
    color: {_INK_SOFT};
    margin-top: 1.5pt;
}}

/* The one emphasised phrase, matching the product's use of the serif
   italic — once per major heading, never sprinkled. */
.cover h1 em {{
    font-family: {_SERIF};
    font-style: italic;
    color: {_VIOLET};
}}

.cover .top-rule {{
    border: none;
    border-top: 2.4pt solid {_ACCENT};
    margin: 10pt 0 0;
}}

.cover .doc-kind {{
    font-family: {_SANS};
    font-size: 7.4pt;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: {_INK_SOFT};
    margin-top: 148pt;
}}

.cover h1 {{
    font-family: {_SERIF};
    font-size: 27pt;
    line-height: 31pt;
    font-weight: 700;
    letter-spacing: -0.012em;
    margin: 8pt 0 0;
}}

.cover .subtitle {{
    font-family: {_SERIF};
    font-size: 12.5pt;
    line-height: 17pt;
    font-style: italic;
    color: {_INK_MID};
    margin-top: 8pt;
}}

.cover .cover-rule {{
    border: none;
    border-top: 0.6pt solid {_RULE};
    margin: {LEAD_PT * 1.5}pt 0;
}}

.cover .facts {{
    width: 100%;
    border-collapse: collapse;
    font-size: 8.2pt;
    line-height: 12pt;
}}

.cover .facts td {{
    padding: 3pt 12pt 3pt 0;
    vertical-align: top;
    width: 50%;
}}

.cover .facts .k {{
    font-family: {_SANS};
    font-size: 6.6pt;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: {_INK_SOFT};
    display: block;
}}

.cover .colophon {{
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    font-family: {_SANS};
    font-size: 6.6pt;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: {_INK_SOFT};
    text-align: center;
    border-top: 0.5pt solid {_RULE};
    padding-top: 7pt;
}}

/* ── Contents ───────────────────────────────────────────────────── */

.toc {{ margin: 0; padding: 0; list-style: none; }}

.toc li {{
    break-inside: avoid;
    margin-bottom: 5pt;
    font-size: 9.5pt;
    line-height: {LEAD_PT}pt;
}}

.toc li.lead-in {{ font-weight: 700; }}

.toc a {{
    color: {_INK};
    text-decoration: none;
}}

/* The leader and the resolved page number. `target-counter` reads the page the
   anchor actually landed on, after pagination — so the contents page cannot
   drift out of date the way a hand-written one does. */
.toc a::after {{
    content: leader(dotted) " " target-counter(attr(href), page);
    color: {_INK_MID};
    font-family: {_SANS};
    font-size: 8.6pt;
}}

.toc .toc-num {{
    font-family: {_SANS};
    font-size: 7.6pt;
    font-weight: 700;
    color: {_ACCENT};
    display: inline-block;
    width: 26pt;
}}

/* ── Figures ────────────────────────────────────────────────────── */

figure {{
    /* A chart never splits across a page. */
    break-inside: avoid;
    page-break-inside: avoid;
    margin: {LEAD_PT}pt 0;
}}

figure svg {{ display: block; width: 100%; height: auto; }}

figcaption {{
    font-family: {_SANS};
    font-size: 7.4pt;
    line-height: 10.5pt;
    color: {_INK_MID};
    margin-top: 5pt;
    text-align: left;
}}

.fig-title {{
    font-family: {_SANS};
    font-size: 8.6pt;
    font-weight: 700;
    color: {_INK};
    margin-bottom: 2pt;
}}

.fig-title .fig-num {{
    color: {_ACCENT};
    letter-spacing: 0.06em;
}}

/* ── Tables ─────────────────────────────────────────────────────── */

table.data, table.md-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 8.2pt;
    line-height: 11.5pt;
    margin: {LEAD_PT / 2}pt 0 {LEAD_PT}pt;
    break-inside: auto;
}}

/* Header rows repeat on every page a long table spans. */
table.data thead, table.md-table thead {{ display: table-header-group; }}
table.data tfoot, table.md-table tfoot {{ display: table-footer-group; }}
table.data tr, table.md-table tr {{ break-inside: avoid; page-break-inside: avoid; }}

table.data th, table.md-table th {{
    font-family: {_SANS};
    font-size: 6.8pt;
    font-weight: 700;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    color: {_INK_MID};
    text-align: left;
    padding: 4pt 6pt;
    border-bottom: 1pt solid {_INK_MID};
    vertical-align: bottom;
}}

table.data td, table.md-table td {{
    padding: 4pt 6pt;
    border-bottom: 0.5pt solid {_RULE_SOFT};
    vertical-align: top;
}}

table.data tbody tr:nth-child(even) td,
table.md-table tbody tr:nth-child(even) td {{ background: {_WASH}; }}

/* Numerals align on the decimal, not on the left edge. */
th.num, td.num {{
    text-align: right;
    font-variant-numeric: tabular-nums;
    font-feature-settings: "tnum" 1, "lnum" 1;
    white-space: nowrap;
}}

td.rowhead {{ font-weight: 700; }}

table.kv {{
    width: 100%;
    border-collapse: collapse;
    font-size: 8.4pt;
    line-height: 12pt;
    margin: {LEAD_PT / 2}pt 0 {LEAD_PT}pt;
}}
table.kv td {{
    padding: 3.5pt 6pt 3.5pt 0;
    border-bottom: 0.5pt solid {_RULE_SOFT};
    vertical-align: top;
}}
table.kv td.k {{
    width: 34%;
    font-family: {_SANS};
    font-size: 6.8pt;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    color: {_INK_SOFT};
    padding-top: 4.5pt;
}}
table.kv tr {{ break-inside: avoid; }}

/* ── Callouts, metrics, quotes ──────────────────────────────────── */

.callout {{
    break-inside: avoid;
    page-break-inside: avoid;
    border-left: 2.2pt solid {_ACCENT};
    background: {_WASH};
    padding: 8pt 11pt;
    margin: {LEAD_PT / 2}pt 0 {LEAD_PT}pt;
    font-size: 8.4pt;
    line-height: 12pt;
}}

.callout.warn {{ border-left-color: {_INK}; }}

.callout .callout-head {{
    font-family: {_SANS};
    font-size: 6.8pt;
    font-weight: 700;
    letter-spacing: 0.09em;
    text-transform: uppercase;
    color: {_INK_MID};
    margin-bottom: 3pt;
}}

.callout p {{ margin: 0 0 4pt; text-align: left; }}
.callout p:last-child {{ margin-bottom: 0; }}
.callout ul {{ margin: 2pt 0 0; padding-left: 12pt; }}

.metrics {{
    width: 100%;
    border-collapse: collapse;
    break-inside: avoid;
    margin: 0 0 {LEAD_PT}pt;
}}

.metrics td {{
    width: 25%;
    border: 0.5pt solid {_RULE};
    padding: 7pt 8pt;
    vertical-align: top;
}}

.metrics .m-label {{
    font-family: {_SANS};
    font-size: 6.4pt;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: {_INK_SOFT};
    margin-bottom: 3pt;
}}

.metrics .m-value {{
    font-family: {_SERIF};
    font-size: 17pt;
    line-height: 19pt;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
}}

.metrics .m-sub {{
    font-family: {_SANS};
    font-size: 6.6pt;
    line-height: 9pt;
    color: {_INK_MID};
    margin-top: 3pt;
}}

blockquote {{
    break-inside: avoid;
    margin: 5pt 0 8pt;
    padding-left: 10pt;
    border-left: 1.6pt solid {_RULE};
    font-family: {_SERIF};
    font-size: 8.8pt;
    line-height: 12.5pt;
    font-style: italic;
    color: {_INK_MID};
}}

blockquote .attribution {{
    display: block;
    font-family: {_SANS};
    font-size: 6.6pt;
    font-style: normal;
    color: {_INK_SOFT};
    margin-top: 3pt;
    letter-spacing: 0.03em;
}}

ul, ol {{ margin: 0 0 {LEAD_PT / 2}pt; padding-left: 14pt; }}
li {{ margin-bottom: 2.5pt; orphans: 2; widows: 2; }}

hr.md-rule {{
    border: none;
    border-top: 0.5pt solid {_RULE};
    margin: {LEAD_PT}pt 0;
}}

.note {{
    font-family: {_SANS};
    font-size: 7.6pt;
    line-height: 11pt;
    color: {_INK_MID};
    border: 0.5pt dashed {_RULE};
    padding: 7pt 9pt;
    margin: {LEAD_PT / 2}pt 0;
    break-inside: avoid;
}}

.lede {{
    font-family: {_SERIF};
    font-size: 11pt;
    line-height: 15.5pt;
    color: {_INK};
    margin-bottom: {LEAD_PT}pt;
    text-align: left;
}}

.provenance {{
    font-size: 7.6pt;
    line-height: 11pt;
    color: {_INK_MID};
}}

.smallcaps {{
    font-family: {_SANS};
    font-size: 6.8pt;
    letter-spacing: 0.09em;
    text-transform: uppercase;
    color: {_INK_SOFT};
}}
"""
