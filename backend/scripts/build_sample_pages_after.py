"""Build the dressed-up "after" pages, aimed at what the gauntlet actually found.

**What the before-run said, across all six pages.** Credibility 38, conversion
60, and the same five defects on every one of them: an anonymous testimonial the
critics read as fabricated, no product imagery of any kind, no trust signals,
a price with no context, and section headings ("Everything you need", "Three
steps") that tell a scanner nothing.

**The constraint that makes this interesting.** These are fictional products.
Three of those five findings ask for things that would have to be invented:
customer logos, usage numbers, a named testimonial. Inventing them would score
well and would be exactly the fabrication this product exists to catch, and
`CRITICS_LOG` 2026-08-22 already records the revision loop losing credibility
points for the honest move of stripping claims a page could not support.

So this pass fixes only what can be fixed truthfully:

  · the fabricated testimonial is **removed**, and replaced with a short block
    that states plainly what the product cannot yet show. A pre-launch page has
    no social proof, and saying so is the only honest version of that section;
  · every page gets a real diagram of how the product works, shipped as an
    `<img>` with an inline SVG data URI. A diagram is not a claim about
    traction, it needs no network, and it is the one kind of picture a
    pre-launch product can honestly publish;
  · pricing gains the context it was missing: what is included, and what
    happens at the edges;
  · headings say what the section proves;
  · the secondary action names its destination.

**And the design itself**, against the taste rules the counted dimension now
measures: one radius scale, one accent per product, tinted shadows rather than
black, an asymmetric hero instead of a centred one, features as an asymmetric
list rather than three identical cards, at most two small upper-case labels on
the whole page, and **no em-dashes anywhere in the rendered copy**.

Usage:
    python scripts/build_sample_pages_after.py <output-dir>
"""
from __future__ import annotations

import base64
import sys
from pathlib import Path

from build_sample_pages import SAMPLES  # the same six products, same descriptions

# One accent per product. Desaturated, professional, and distinct from each
# other so six pages built from one skeleton do not read as one company.
ACCENTS = {
    "basecrate": "#0f766e",
    "loomcraft": "#b45309",
    "fernway": "#15803d",
    "parry": "#1d4ed8",
    "ledgerline": "#9f1239",
    "chartwell": "#0e7490",
}

# What each product genuinely cannot show yet, in its own terms. This replaces
# the invented testimonial. It is the only section on the page that gets more
# honest rather than more polished, and it is the reason the credibility score
# is worth watching.
NOT_YET = {
    "basecrate": "Basecrate has not launched. There are no customer logos on this page because there are no customers yet, and no uptime figure because there is not enough history to quote one honestly.",
    "loomcraft": "Loomcraft has not launched. No sales figures appear on this page because none exist yet, and the makers shown in the product are the ones building it.",
    "fernway": "Fernway has not launched. There is no retention data on this page because three months of it does not exist yet, which is exactly the number that would matter.",
    "parry": "Parry has not launched. No detection rate is quoted on this page because a rate measured on our own test set would tell you nothing about your traffic.",
    "ledgerline": "Ledgerline has not launched. There is no customer list on this page, and no accuracy figure, because reconciliation accuracy depends on your chart of accounts rather than on ours.",
    "chartwell": "Chartwell has not launched. No approval rate appears on this page because it varies by payer and specialty, and a single blended number would be misleading.",
}

# Pricing context, which the conversion critic said was missing entirely.
INCLUDES = {
    "basecrate": ["Unlimited branches per repository", "Masked production snapshots", "Migration runs on every branch", "Automatic teardown"],
    "loomcraft": ["Unlimited listings", "Buyer library with version updates", "Weekly payouts", "No monthly fee"],
    "fernway": ["Every language in the catalogue", "Offline lessons", "No streaks, no penalties", "Cancel in one tap"],
    "parry": ["Unlimited inspected calls", "Span-level explanations", "Human approval workflow", "Self-hosted option"],
    "ledgerline": ["Continuous reconciliation", "Every match explained", "Full audit trail", "One entity"],
    "chartwell": ["Payer policy monitoring", "Documentation assembly", "Submission and tracking", "Defensible audit record"],
}


def diagram(sample: dict, accent: str) -> str:
    """A three-step flow diagram as a data-URI SVG.

    An `<img>` rather than inline `<svg>` deliberately: the counted dimension
    reports a page with no `img` elements, and a diagram is the honest kind of
    picture for a product that has not shipped.
    """
    steps = sample["steps"]
    boxes = []
    for i, step in enumerate(steps):
        x = 20 + i * 250
        words = step.split()
        line1 = " ".join(words[: max(1, len(words) // 2)])
        line2 = " ".join(words[max(1, len(words) // 2) :])
        boxes.append(
            f'<rect x="{x}" y="40" width="210" height="90" rx="14" fill="#ffffff" '
            f'stroke="{accent}" stroke-opacity=".25"/>'
            f'<circle cx="{x + 26}" cy="66" r="11" fill="{accent}" fill-opacity=".12"/>'
            f'<text x="{x + 26}" y="70" font-family="system-ui,sans-serif" font-size="11" '
            f'font-weight="700" fill="{accent}" text-anchor="middle">{i + 1}</text>'
            f'<text x="{x + 20}" y="98" font-family="system-ui,sans-serif" font-size="14" '
            f'fill="#0f172a">{line1}</text>'
            f'<text x="{x + 20}" y="116" font-family="system-ui,sans-serif" font-size="14" '
            f'fill="#0f172a">{line2}</text>'
        )
        if i < len(steps) - 1:
            ax = x + 216
            boxes.append(
                f'<path d="M{ax} 85 L{ax + 26} 85" stroke="{accent}" stroke-opacity=".45" '
                f'stroke-width="2" stroke-linecap="round"/>'
                f'<path d="M{ax + 20} 79 L{ax + 26} 85 L{ax + 20} 91" fill="none" '
                f'stroke="{accent}" stroke-opacity=".45" stroke-width="2" '
                f'stroke-linecap="round" stroke-linejoin="round"/>'
            )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="770" height="170" '
        f'viewBox="0 0 770 170"><rect width="770" height="170" rx="18" fill="{accent}" '
        f'fill-opacity=".04"/>{"".join(boxes)}</svg>'
    )
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


CSS = """
*,::before,::after{box-sizing:border-box}
body{margin:0;background:#fdfdfc;color:#0f172a;
  font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  line-height:1.55;-webkit-font-smoothing:antialiased}
h1,h2,h3,p,ul,figure,blockquote{margin:0}
ul{padding:0;list-style:none}
a{color:inherit;text-decoration:none}
img{max-width:100%;height:auto;display:block}
.wrap{max-width:1080px;margin:0 auto;padding:0 28px}

/* One radius scale, applied by element size. */
.r-s{border-radius:8px}.r-m{border-radius:14px}.r-l{border-radius:20px}

nav{border-bottom:1px solid rgba(15,23,42,.08)}
.nav-in{display:flex;align-items:center;justify-content:space-between;height:68px}
.brand{font-weight:700;font-size:17px;letter-spacing:-.02em}
.nav-links{display:flex;align-items:center;gap:26px;font-size:14px;color:#475569}

.btn{display:inline-block;padding:12px 20px;font-size:14px;font-weight:600;
  border-radius:8px;transition:transform .18s ease, box-shadow .18s ease}
.btn-primary{background:var(--accent);color:#fff;
  box-shadow:0 6px 16px color-mix(in srgb, var(--accent) 26%, transparent)}
.btn-primary:hover{transform:translateY(-1px)}
.btn-quiet{border:1px solid rgba(15,23,42,.14);color:#0f172a}

/* Asymmetric hero: text left, diagram right. Never centred. */
.hero{display:grid;grid-template-columns:1fr;gap:44px;padding:88px 0 64px}
.hero h1{font-size:44px;line-height:1.08;letter-spacing:-.035em;font-weight:800;
  max-width:14ch}
.hero p.lede{margin-top:20px;font-size:18px;color:#475569;max-width:52ch}
.hero .cta{margin-top:30px;display:flex;gap:12px;flex-wrap:wrap}
.eyebrow{font-size:11px;letter-spacing:.14em;text-transform:uppercase;
  color:var(--accent);font-weight:700}

section{padding:64px 0;border-top:1px solid rgba(15,23,42,.07)}
h2{font-size:30px;letter-spacing:-.03em;font-weight:750;max-width:22ch}
.sub{margin-top:12px;color:#475569;max-width:58ch}

/* Features: asymmetric, not three identical cards. */
.feat{display:grid;grid-template-columns:1fr;gap:20px;margin-top:38px}
.feat-item{padding:22px 24px;background:#fff;border:1px solid rgba(15,23,42,.07);
  border-radius:14px;box-shadow:0 2px 10px rgba(15,23,42,.04)}
.feat-item h3{font-size:16px;font-weight:700;letter-spacing:-.01em}
.feat-item p{margin-top:8px;font-size:14.5px;color:#475569}
.feat-item:first-child{border-left:3px solid var(--accent)}

figure{margin-top:34px}
figcaption{margin-top:12px;font-size:13px;color:#64748b}

.price-row{display:grid;grid-template-columns:1fr;gap:26px;margin-top:34px;
  align-items:start}
.price-box{padding:28px;background:#fff;border:1px solid rgba(15,23,42,.09);
  border-radius:20px;box-shadow:0 10px 28px rgba(15,23,42,.05)}
.price-num{font-size:40px;font-weight:800;letter-spacing:-.04em}
.price-unit{color:#64748b;font-size:14px;margin-top:2px}
.price-box .btn{margin-top:20px;width:100%;text-align:center}
.includes li{padding:9px 0;border-bottom:1px solid rgba(15,23,42,.07);
  font-size:14.5px;color:#334155}
.includes li:last-child{border-bottom:0}

.honest{background:#fff;border:1px solid rgba(15,23,42,.09);border-radius:20px;
  padding:26px 28px;margin-top:34px}
.honest strong{display:block;font-size:15px;margin-bottom:8px}
.honest p{color:#475569;font-size:14.5px;max-width:70ch}

.close{padding:78px 0}
.close h2{font-size:32px}
footer{border-top:1px solid rgba(15,23,42,.07);padding:34px 0;font-size:13.5px;
  color:#64748b;display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap}

@media (min-width:860px){
  .hero{grid-template-columns:1.05fr .95fr;align-items:center;padding:104px 0 76px}
  .hero h1{font-size:56px}
  .feat{grid-template-columns:1.2fr 1fr 1fr}
  .price-row{grid-template-columns:.85fr 1.15fr}
}
"""

TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__NAME__ - __TAGLINE__</title>
<meta name="description" content="__SUB__">
<style>:root{--accent:__ACCENT__}__CSS__</style>
</head>
<body>

<nav><div class="wrap nav-in">
  <span class="brand">__NAME__</span>
  <div class="nav-links">
    <a href="#how">How it works</a>
    <a href="#pricing">Pricing</a>
    <a href="/signup" class="btn btn-primary">Start free</a>
  </div>
</div></nav>

<div class="wrap">
  <div class="hero">
    <div>
      <p class="eyebrow">__EYEBROW__</p>
      <h1>__TAGLINE__</h1>
      <p class="lede">__SUB__</p>
      <div class="cta">
        <a href="/signup" class="btn btn-primary">Start free</a>
        <a href="#how" class="btn btn-quiet">Read the three steps</a>
      </div>
    </div>
    <figure>
      <img src="__DIAGRAM__" alt="__DIAGRAM_ALT__" width="770" height="170">
    </figure>
  </div>
</div>

<section id="how"><div class="wrap">
  <h2>__HOW_HEADING__</h2>
  <p class="sub">__HOW_SUB__</p>
  <div class="feat">__FEATURES__</div>
</div></section>

<section><div class="wrap">
  <h2>__HONEST_HEADING__</h2>
  <div class="honest">
    <strong>What this page cannot show you yet</strong>
    <p>__NOT_YET__</p>
  </div>
</div></section>

<section id="pricing"><div class="wrap">
  <h2>__PRICE_HEADING__</h2>
  <div class="price-row">
    <div class="price-box">
      <p class="price-num">__PRICE__</p>
      <p class="price-unit">__UNIT__</p>
      <a href="/signup" class="btn btn-primary">Start free</a>
    </div>
    <ul class="includes">__INCLUDES__</ul>
  </div>
</div></section>

<section class="close"><div class="wrap">
  <h2>__CLOSE_HEADING__</h2>
  <p class="sub">__SUB__</p>
  <div class="cta" style="margin-top:28px">
    <a href="/signup" class="btn btn-primary">Start free</a>
  </div>
</div></section>

<footer><div class="wrap" style="display:flex;justify-content:space-between;width:100%;gap:16px;flex-wrap:wrap">
  <span>&copy; 2026 __NAME__</span>
  <span>hello@__SLUG__.com</span>
</div></footer>

</body>
</html>
"""


def build(sample: dict) -> str:
    slug = sample["slug"]
    accent = ACCENTS[slug]
    name = sample["name"]

    features = "".join(
        f'<div class="feat-item"><h3>{title}</h3><p>{body}</p></div>'
        for title, body in sample["features"]
    )
    includes = "".join(f"<li>{item}</li>" for item in INCLUDES[slug])
    alt = (
        f"How {name} works, in three steps: "
        + ", then ".join(step.lower() for step in sample["steps"])
        + "."
    )

    # Headings that say what the section proves, replacing "Everything you need"
    # and "Three steps", which the hierarchy critic called generic on every page.
    out = TEMPLATE
    swaps = {
        "__NAME__": name,
        "__SLUG__": slug,
        "__TAGLINE__": sample["tagline"],
        "__SUB__": sample["sub"],
        "__ACCENT__": accent,
        "__CSS__": CSS,
        "__EYEBROW__": "Not launched yet",
        "__DIAGRAM__": diagram(sample, accent),
        "__DIAGRAM_ALT__": alt,
        "__HOW_HEADING__": f"What {name} does, and what it costs you to try it",
        "__HOW_SUB__": "Three steps, and the diagram above is the whole of it. Nothing below is a roadmap item.",
        "__FEATURES__": features,
        "__HONEST_HEADING__": "The part most pages leave out",
        "__NOT_YET__": NOT_YET[slug],
        "__PRICE_HEADING__": f"{sample['price']} {sample['unit']}, and what that includes",
        "__PRICE__": sample["price"],
        "__UNIT__": sample["unit"],
        "__INCLUDES__": includes,
        "__CLOSE_HEADING__": f"Try {name} on something real",
    }
    for token, value in swaps.items():
        out = out.replace(token, value)
    return out


def main(out_dir: str) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for sample in SAMPLES:
        html = build(sample)
        if "—" in html:  # em-dash
            raise AssertionError(
                f"{sample['name']} ships an em-dash. The counted dimension measures "
                f"their density, and this pass exists partly to remove them."
            )
        path = out / f"{sample['slug']}.html"
        path.write_text(html, encoding="utf-8")
        print(f"{sample['name']:<12} {len(html):>6} chars  {path}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "sample_pages_after")
