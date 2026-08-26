"""Build the six sample landing pages — the "before" half of the gauntlet demo.

**These are deliberately ordinary.** They are what a founder ships on a weekend
with a coding agent: Tailwind off the CDN, a centred hero, three equal feature
cards, a three-step "how it works", a plain pricing block, and no photography.
Nothing here is a strawman — every one of these choices is what the default
looks like, which is exactly why the page needs a read.

**Why we own them.** The six sample products previously had their website checks
run against real companies' sites — Stripe, Duolingo, Supabase, Gumroad,
SimplePractice — because there was nothing of our own to point at. Those runs are
real and stored, and none of them can appear in Saibyl's marketing: they are
other companies' page designs, and publishing a before/after of them asserts we
improved someone else's brand. These pages exist so the demo is ours.

The output is self-contained HTML, so `capture_html()` can render it without
anything being hosted.

Usage:
    python scripts/build_sample_pages.py <output-dir>
"""
from __future__ import annotations

import sys
from pathlib import Path

# The six sample products, as they are described in the database. Copy is kept
# close to those descriptions so the page is about the product it claims to be.
SAMPLES: list[dict] = [
    {
        "slug": "basecrate",
        "name": "Basecrate",
        "tagline": "A database branch for every pull request.",
        "sub": "Point Basecrate at your Postgres and every PR gets an isolated copy with production-shaped data, seeded and migrated, torn down when the branch closes.",
        "features": [
            ("Real data shapes", "Branches are seeded from a masked snapshot, so the rows look like production without being production."),
            ("Migrations run first", "Every branch applies your migration chain before anyone opens it, so a broken migration fails in CI and not on Friday."),
            ("Torn down automatically", "The branch dies with the pull request. Nobody pays for forty forgotten databases."),
        ],
        "steps": ["Connect your Postgres", "Open a pull request", "Get a branch URL in the checks"],
        "price": "$40",
        "unit": "per developer / month",
    },
    {
        "slug": "loomcraft",
        "name": "Loomcraft",
        "tagline": "Where independent designers sell the small things.",
        "sub": "Icon sets, Figma kits, LUTs, sample packs, Notion templates. Buyers get a library that stays organised instead of forty zip files in a downloads folder.",
        "features": [
            ("A library, not a receipt", "Everything a buyer has ever bought stays in one place, versioned, and updates when the maker ships a fix."),
            ("Made for small work", "Listing takes a minute. No store to design, no theme to pick, no subdomain to configure."),
            ("Paid out weekly", "Makers are paid on a schedule they can plan around rather than on a threshold they have to reach."),
        ],
        "steps": ["Upload the files", "Set a price", "Share one link"],
        "price": "8%",
        "unit": "per sale, nothing monthly",
    },
    {
        "slug": "fernway",
        "name": "Fernway",
        "tagline": "Learn a language in the gaps of your day.",
        "sub": "Three minutes at a time, built around the moments you already waste. The queue, the lift, the wait for coffee. No streaks to guilt you.",
        "features": [
            ("Three minutes is the unit", "Every lesson is designed to finish before the coffee does, so there is nothing to abandon halfway."),
            ("No streaks", "Missing a day costs nothing. The thing that makes people quit an app is the thing that punishes them for living."),
            ("Speaks first", "You hear the sentence before you read it, because that is the order you will meet it in."),
        ],
        "steps": ["Pick a language", "Tell it when your gaps are", "Answer when it asks"],
        "price": "$9",
        "unit": "per month",
    },
    {
        "slug": "parry",
        "name": "Parry",
        "tagline": "Stop prompt injection before the agent acts.",
        "sub": "Parry inspects every model input and output in line, scores it for injection and exfiltration patterns, and blocks or flags before anything runs.",
        "features": [
            ("In line, not after", "The check happens between the model and the tool call, which is the only place a block still prevents something."),
            ("The span is shown", "Every score points at the exact text that triggered it, so an engineer can judge the call rather than trust it."),
            ("Human approval for the worst", "Anything that could be catastrophic waits for a person, and the request tells them what it would have done."),
        ],
        "steps": ["Wrap your model client", "Set what needs approval", "Watch what gets caught"],
        "price": "$199",
        "unit": "per month, unlimited calls",
    },
    {
        "slug": "ledgerline",
        "name": "Ledgerline",
        "tagline": "A cash position that is current, not a week old.",
        "sub": "Ledgerline connects the banks and the ledger, reconciles every transaction continuously, and produces a cash position an auditor can follow.",
        "features": [
            ("Continuous, not monthly", "Reconciliation runs as transactions land, so close is a review rather than a reconstruction."),
            ("Every match is explained", "Each reconciled pair carries the rule that matched it, and the ones that did not match are listed rather than buried."),
            ("Built for the audit", "The trail is the product. Every adjustment has an author, a reason, and a timestamp."),
        ],
        "steps": ["Connect the banks", "Connect the ledger", "Review what did not match"],
        "price": "$450",
        "unit": "per entity / month",
    },
    {
        "slug": "chartwell",
        "name": "Chartwell",
        "tagline": "Prior authorization, submitted automatically.",
        "sub": "Chartwell reads the payer's published policy, assembles the clinical documentation from the EHR, and submits the request with an audit trail a compliance officer can defend.",
        "features": [
            ("Reads the actual policy", "Requirements come from the payer's own published criteria, not from a rule somebody typed in two years ago."),
            ("Assembles the evidence", "The chart notes, the imaging, the prior therapies. Pulled from the record and attached in the order the payer asks for."),
            ("Defensible afterwards", "Every submission keeps what was sent, what the policy said that day, and who approved it."),
        ],
        "steps": ["Connect the EHR", "Pick the payers", "Approve what it drafts"],
        "price": "Talk to us",
        "unit": "priced per specialty",
    },
]


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{name} - {tagline}</title>
<meta name="description" content="{sub}">
<style>
/* The utilities this page uses, written out.
 *
 * The obvious thing is `<script src="https://cdn.tailwindcss.com">`, which is
 * what a founder actually ships. It does not work here, and not by accident:
 * `capture_html` denies the rendered document the network on purpose, because
 * the HTML is user-supplied and its subresources are not to be trusted. The
 * first run of these pages came back in Times New Roman with no colours and no
 * radii at all, which would have had six critics reviewing an unstyled
 * document and calling it a design.
 *
 * So the class names stay — the markup is the markup a coding agent writes —
 * and the styles they refer to ship inline. */
*,::before,::after{{box-sizing:border-box;border:0 solid #e5e7eb}}
body{{margin:0;font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;line-height:1.5}}
h1,h2,h3,p,blockquote{{margin:0}}
a{{color:inherit;text-decoration:none}}
.antialiased{{-webkit-font-smoothing:antialiased}}
.bg-white{{background-color:#fff}}
.bg-gray-900{{background-color:#111827}}
.text-gray-900{{color:#111827}}
.text-gray-600{{color:#4b5563}}
.text-gray-500{{color:#6b7280}}
.text-white{{color:#fff}}
.border{{border-width:1px}}
.border-b{{border-bottom-width:1px}}
.border-t{{border-top-width:1px}}
.border-gray-200{{border-color:#e5e7eb}}
.border-gray-300{{border-color:#d1d5db}}
.rounded-md{{border-radius:.375rem}}
.rounded-lg{{border-radius:.5rem}}
.max-w-6xl{{max-width:72rem}}.max-w-3xl{{max-width:48rem}}.max-w-md{{max-width:28rem}}
.mx-auto{{margin-left:auto;margin-right:auto}}
.px-6{{padding-left:1.5rem;padding-right:1.5rem}}
.py-24{{padding-top:6rem;padding-bottom:6rem}}
.py-20{{padding-top:5rem;padding-bottom:5rem}}
.py-10{{padding-top:2.5rem;padding-bottom:2.5rem}}
.py-3{{padding-top:.75rem;padding-bottom:.75rem}}
.py-2{{padding-top:.5rem;padding-bottom:.5rem}}
.p-8{{padding:2rem}}.p-6{{padding:1.5rem}}
.px-4{{padding-left:1rem;padding-right:1rem}}
.h-16{{height:4rem}}
.flex{{display:flex}}.grid{{display:grid}}.block{{display:block}}
.items-center{{align-items:center}}
.justify-between{{justify-content:space-between}}
.justify-center{{justify-content:center}}
.gap-8{{gap:2rem}}.gap-6{{gap:1.5rem}}.gap-4{{gap:1rem}}
.text-center{{text-align:center}}
.font-bold{{font-weight:700}}.font-semibold{{font-weight:600}}.font-medium{{font-weight:500}}
.text-5xl{{font-size:3rem;line-height:1}}
.text-4xl{{font-size:2.25rem;line-height:2.5rem}}
.text-3xl{{font-size:1.875rem;line-height:2.25rem}}
.text-2xl{{font-size:1.5rem;line-height:2rem}}
.text-lg{{font-size:1.125rem;line-height:1.75rem}}
.text-sm{{font-size:.875rem;line-height:1.25rem}}
.text-xs{{font-size:.75rem;line-height:1rem}}
.uppercase{{text-transform:uppercase}}
.tracking-widest{{letter-spacing:.1em}}
.tracking-tight{{letter-spacing:-.025em}}
.mb-12{{margin-bottom:3rem}}.mb-8{{margin-bottom:2rem}}.mb-6{{margin-bottom:1.5rem}}
.mb-4{{margin-bottom:1rem}}.mb-3{{margin-bottom:.75rem}}.mb-2{{margin-bottom:.5rem}}
.mt-6{{margin-top:1.5rem}}.mt-4{{margin-top:1rem}}.mt-1{{margin-top:.25rem}}
@media (min-width:768px){{.md\\:grid-cols-3{{grid-template-columns:repeat(3,minmax(0,1fr))}}}}
</style>
</head>
<body class="bg-white text-gray-900 antialiased">

<nav class="border-b border-gray-200">
  <div class="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
    <span class="font-semibold text-lg">{name}</span>
    <div class="flex items-center gap-6 text-sm text-gray-600">
      <a href="#features" class="hover:text-gray-900">Features</a>
      <a href="#how" class="hover:text-gray-900">How it works</a>
      <a href="#pricing" class="hover:text-gray-900">Pricing</a>
      <a href="/signup" class="bg-gray-900 text-white px-4 py-2 rounded-md">Get started</a>
    </div>
  </div>
</nav>

<section class="max-w-3xl mx-auto px-6 py-24 text-center">
  <p class="text-xs uppercase tracking-widest text-gray-500 mb-4">Now in beta</p>
  <h1 class="text-5xl font-bold tracking-tight mb-6">{tagline}</h1>
  <p class="text-lg text-gray-600 mb-8">{sub}</p>
  <div class="flex items-center justify-center gap-4">
    <a href="/signup" class="bg-gray-900 text-white px-6 py-3 rounded-md font-medium">Start free</a>
    <a href="#how" class="border border-gray-300 px-6 py-3 rounded-md font-medium">See how it works</a>
  </div>
</section>

<section id="features" class="max-w-6xl mx-auto px-6 py-20 border-t border-gray-200">
  <p class="text-xs uppercase tracking-widest text-gray-500 mb-3">Features</p>
  <h2 class="text-3xl font-bold tracking-tight mb-12">Everything you need</h2>
  <div class="grid md:grid-cols-3 gap-8">
    {feature_cards}
  </div>
</section>

<section id="how" class="max-w-6xl mx-auto px-6 py-20 border-t border-gray-200">
  <p class="text-xs uppercase tracking-widest text-gray-500 mb-3">How it works</p>
  <h2 class="text-3xl font-bold tracking-tight mb-12">Three steps</h2>
  <div class="grid md:grid-cols-3 gap-8">
    {step_cards}
  </div>
</section>

<section class="max-w-6xl mx-auto px-6 py-20 border-t border-gray-200">
  <p class="text-xs uppercase tracking-widest text-gray-500 mb-3">Testimonial</p>
  <blockquote class="text-2xl font-medium max-w-3xl">
    "We put {name} in on a Tuesday and stopped thinking about it by Friday. That is
    about the highest praise infrastructure gets."
  </blockquote>
  <p class="text-sm text-gray-600 mt-4">Engineering lead, a company that asked not to be named</p>
</section>

<section id="pricing" class="max-w-6xl mx-auto px-6 py-20 border-t border-gray-200">
  <p class="text-xs uppercase tracking-widest text-gray-500 mb-3">Pricing</p>
  <h2 class="text-3xl font-bold tracking-tight mb-12">Simple pricing</h2>
  <div class="border border-gray-200 rounded-lg p-8 max-w-md">
    <p class="text-4xl font-bold">{price}</p>
    <p class="text-sm text-gray-600 mt-1">{unit}</p>
    <a href="/signup" class="mt-6 block text-center bg-gray-900 text-white px-6 py-3 rounded-md font-medium">Get started</a>
  </div>
</section>

<section class="max-w-3xl mx-auto px-6 py-24 text-center border-t border-gray-200">
  <h2 class="text-3xl font-bold tracking-tight mb-4">Ready to try {name}?</h2>
  <p class="text-gray-600 mb-8">{sub}</p>
  <a href="/signup" class="bg-gray-900 text-white px-6 py-3 rounded-md font-medium">Start free</a>
</section>

<footer class="border-t border-gray-200">
  <div class="max-w-6xl mx-auto px-6 py-10 text-sm text-gray-600 flex justify-between">
    <span>&copy; 2026 {name}</span>
    <span>hello@{slug}.com</span>
  </div>
</footer>

</body>
</html>
"""

FEATURE_CARD = """<div class="border border-gray-200 rounded-lg p-6">
      <h3 class="font-semibold mb-2">{title}</h3>
      <p class="text-sm text-gray-600">{body}</p>
    </div>"""

STEP_CARD = """<div>
      <p class="text-xs uppercase tracking-widest text-gray-500 mb-2">Step {n}</p>
      <h3 class="font-semibold mb-2">{title}</h3>
    </div>"""


def build(sample: dict) -> str:
    features = "\n    ".join(
        FEATURE_CARD.format(title=title, body=body) for title, body in sample["features"]
    )
    steps = "\n    ".join(
        STEP_CARD.format(n=i + 1, title=title) for i, title in enumerate(sample["steps"])
    )
    return TEMPLATE.format(feature_cards=features, step_cards=steps, **sample)


def main(out_dir: str) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for sample in SAMPLES:
        path = out / f"{sample['slug']}.html"
        path.write_text(build(sample), encoding="utf-8")
        print(f"{sample['name']:<12} {len(path.read_text(encoding='utf-8')):>6} chars  {path}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "sample_pages")
