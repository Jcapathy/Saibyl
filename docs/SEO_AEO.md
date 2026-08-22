# SEO and AEO — being found by people, and cited by machines

**Written 2026-08-20**, from primary sources (crawler docs from OpenAI,
Anthropic, Perplexity and Google; Google's rich-results gallery and JavaScript
SEO docs; the IETF AIPREF drafts; the KDD 2024 GEO paper) plus live checks
against the deployed site. Where a claim is contested or rests on one study,
it says so — this file is meant to be actionable, not confident.

**Part 4 added 2026-08-22**, from the arXiv papers cited in it — read directly,
not via the curated lists that index them. Full identifiers: Sielinski
2603.08924 · Watanabe & Nakayashiki 2606.04362 · Sharma 2601.00912 · Jack et
al. 2605.27439 · Vishwakarma et al. 2605.25517 · Zhang et al. 2604.25707.
Vendor-published material is labelled as such wherever it is used.

---

## The blocker, above everything else

**`saibyl.com` serves a GoDaddy "Launching Soon" page.** The product is at
`saibyl-frontend.onrender.com`. Meanwhile `index.html` sets `canonical`,
`og:url` and `og:image` to `saibyl.com` — so every identity signal the product
emits points at a parking page, and `og-image.png` does not exist there either.

Also verified live: every path returns HTTP 200 with the same 2,846-byte SPA
shell (the `/*` rewrite in `render.yaml`), which manufactures unlimited
soft-404s.

**Pointing the domain at the Render frontend is the highest-value action
available and nothing else counts until it is done.** It is the founder's to
take.

---

## Part 1 — AEO

### The crawler distinction that decides whether we can be cited

Most "block the AI bots" advice conflates two different jobs. Blocking the
wrong one deletes the product from the surface its buyers use.

| Agent | Job | Blocking it costs |
|---|---|---|
| `GPTBot` | Training only | Nothing, citation-wise |
| **`OAI-SearchBot`** | ChatGPT's search index | **Citation in ChatGPT** |
| `ChatGPT-User` | Live user-triggered fetch | Not guaranteed to obey robots.txt |
| `ClaudeBot` | Training only | Nothing |
| **`Claude-SearchBot`, `Claude-User`** | Claude's index / live fetch | Visibility in Claude's search |
| **`PerplexityBot`** | Perplexity's index | Appearing in Perplexity |
| **`Googlebot`** | Search **and** AI Overviews / AI Mode | Everything — no separation exists |
| `Google-Extended` | A *control token*, not a crawler | Gemini training/grounding only |

Two traps worth naming: **Google-Extended has never controlled AI Overviews**
(Google states it is not a ranking signal and does not affect Search
inclusion), and `Google-Extended` issues no requests of its own — Googlebot
fetches, which is why Gemini grounding inherits full JavaScript rendering.

**Our position: allow everything, including training crawlers.** Saibyl has no
content moat and needs recall inside the models more than it needs leverage.
Shipped in `frontend/public/robots.txt`.

Do **not** add `nosnippet` or a tight `max-snippet`: Google documents that
these prevent content being used as input to AI Overviews and AI Mode, and
snippet eligibility is a precondition for citation.

**Owed, and it gates all Google AI citation:** since 2026-06-03 there is a
Search Console toggle (Settings → Search generative AI). Google's AI
optimization guide now states a site must be *included* via that toggle to be
eligible for generative AI features at all. Verify it is set to include the
day DNS moves.

### The SPA problem — the real constraint

**No major AI crawler executes JavaScript.** The app is client-rendered, so an
answer engine sees `<div id="root"></div>` and nothing else.

Evidence, stated honestly: this rests mainly on **one rigorous study**
(Vercel/MERJ, December 2024) which used a beacon that fires only if JS
actually runs, and named OAI-SearchBot, ChatGPT-User, GPTBot, ClaudeBot and
PerplexityBot as non-rendering. It has never been updated, and the vendor
sells server-side rendering. Two smaller 2025–2026 log studies corroborate it,
and Anthropic's own docs say its fetch tool "does not support websites
dynamically rendered with JavaScript." **Zero contrary evidence exists.** Only
Google documents rendering, affirmatively, via headless Chromium.

Exceptions worth knowing: **AppleBot renders**, Bingbot renders partially, and
**agentic browser modes run real Chromium** — but those are user-driven
sessions, not crawlers, and cannot be optimized for like one.

**The fix, in order:**

1. Real `robots.txt`, `sitemap.xml`, `og-image.png` as files — **shipped**
   except the image, which does not exist yet.
2. **Prerender the marketing routes to static HTML at build.** A short
   post-build script using `renderToString` + `StaticRouter` writing
   `dist/<route>/index.html` is enough; these pages fetch no data. This is the
   single biggest AEO unlock and it is not yet done.
3. **Only then** scope the `/*` rewrite so unmatched paths return true 404s.
   Doing this before prerendering would break `/privacy`, `/terms`, `/login`
   and `/signup`, which are client-side routes today.

JSON-LD must land in the prerendered HTML, not be injected by React.

### Structured data — what is actually still alive

- **FAQPage is dead as a rich result** (Google stopped showing them
  2026-05-07 and deleted the docs). Shipped anyway, deliberately: the Q&A
  shape is what answer engines quote.
- **SoftwareApplication** needs `aggregateRating` or `review` for a rich
  result. We have no legitimate ratings, so we get none, and inventing them is
  a manual-action risk.
- **Organization** is the highest-value type here and has no required
  properties. **BreadcrumbList** still works (desktop). **HowTo** and the
  sitelinks searchbox are gone.

Be skeptical of "schema helps AI." Google says it is not needed; the one study
was run by a schema vendor and measured a negligible effect. Ours is cheap and
truthful, not a lever.

### llms.txt — ship it, but not as a tactic

Google states outright that it ignores such files. No major lab documents
consuming it. A 137,210-domain study found **97% of published `llms.txt` files
got zero requests**, and most that did came from SEO audit tools. The one real
reason: Chrome Lighthouse audits it in the default config, so it is a
scored checkbox. Thirty minutes, `noindex` it, keep it out of the causal
chain. The genuine standards work is IETF AIPREF, still draft, no RFC.

### The content shape that gets quoted

From the GEO paper (KDD 2024), measured: adding quotations **+41%**, adding
statistics **+39.8%**, citing sources **+30%**; keyword stuffing ≈ 0. The most
relevant finding for us: **lower-ranked sites gained up to 115% from citing
sources**, while already-top sites slightly declined. That is exactly Saibyl's
position.

Practically: question-shaped H2s matching real query strings, the answer in
the first two sentences, one data table per page, sourced statistics, honest
`dateModified`.

---

## Part 2 — SEO

Observed SERPs, August 2026. Difficulty judged by who holds the slots.

| Query | Intent | Who holds it | Difficulty |
|---|---|---|---|
| is my startup idea taken | Info | **r/startups #1**, Medium, First Round | **Low** |
| how to know if my SaaS idea already exists | Info | SaaStr, r/startups, preuve.ai | Low–moderate |
| has someone already patented my idea | Info | Quora, r/startups, small law firms | Low–moderate |
| how to validate a startup idea without customers | Info | r/startups #1, First Round | Low–moderate |
| startup idea validation tool | Commercial | r/SaaS, validatorai.com, ideaproof.io | Moderate |
| free trademark / prior art search | Transactional | uspto.gov, Google Patents, LegalZoom | **Locked** |
| customer objection analysis tool | Commercial | Salesforce, Clari, Cognism | **Locked** |

**Reddit or Quora sits top-5 in seven of ten tested queries**, and takes #1–2
on the pure founder-worry questions. Those are long-tail, interrogative and
informational — the profile that maximizes AI Overview probability, where
~83% of searches are zero-click. **Plan to be cited on the informational
terms and to earn clicks on the commercial ones.**

**Two categories are closed; do not attempt them.** Free trademark/patent
search (government plus LegalZoom-scale incumbents) and objection-analysis
tooling (funded sales-enablement vendors — the wrong door entirely). Treat IP
clearance as a trust feature and target the *worry* framing instead — "do I
need a trademark before launching", "can I patent something I built with AI" —
never the tool framing.

**The competitive reality that should change the plan.** Artificial Societies
(YC W25) already ranks #1 for "synthetic market research" and has shipped the
exact architecture recommended below: a published method page, an eval report
benchmarked against 1,000 real surveys, an accuracy answer page, and five
comparison pages. ValidatorAI ships a free simulator that is roughly Saibyl's
free tier. Synthetic Users launched a rigorous-research property in July 2026
that **currently contains one post.** The rigorous-validation position is
being claimed right now and is not yet held.

---

## Part 3 — The unfair advantage, and its constraint

**Read the constraint first.** `PrivacyPage.tsx` currently promises uploads are
"never shown outside your account" and "It never trains models." Publishing any
user-derived aggregate contradicts the live promise. Four prerequisites, all
required: revise the privacy page; add an explicit run-time opt-in (not buried
in terms); enforce k-anonymity (n ≥ 50 per published cell); publish only
Saibyl-generated persona text and category labels, **never** founder-supplied
idea text.

Ranked by citability per unit of risk:

1. **The synthetic-accuracy reconciliation table** — *start here; needs no
   proprietary data and no consent work.* Nobody has reconciled the competing
   accuracy claims in this field (85–92%, 86% against a 91% human ceiling,
   94–95% gated, an unsubstantiated 89%) against the academic record, which
   ranges from r=.85 on a large Stanford study to **52% on genuinely unseen
   items**. These use incompatible metrics and undisclosed methods. Building
   that table *is* Saibyl's confidence-interval positioning, and it is the
   format answer engines cite.
2. **USPTO crowding reports** — 100% public data, zero consent exposure, and
   it is precisely the founder's narrative: you built it in a weekend, and
   four hundred people already filed.
3. **The Objection Index** — quarterly, top objections by category with
   frequency, severity and intervals. Statistics are the #2 measured GEO
   lever; this is a statistics factory.
4. **Objection taxonomy pages** — one per canonical objection, each carrying
   real measured data.
5. **A public methodology page** — engage the skeptics directly, including
   NN/g, which ranks on head terms.

---

## Part 4 — Knowing whether any of it worked

Everything above is a hypothesis. This part is how it gets tested, and why most
of what is sold as "AI visibility tracking" is measuring noise.

### This is not rank tracking

A SERP is near-deterministic: query it twice, get the same ten links. An answer
engine samples from a distribution. The question is not *did we rank* but **at
what rate are we cited, and how wide is the interval.**

The only paper that has quantified this properly is Sielinski, *Quantifying
Uncertainty in AI Visibility* (arXiv 2603.08924, v1 2026-03-09, v2 2026-06-09),
which repeatedly sampled Perplexity, SearchGPT and Gemini over nine days plus
ten-minute-interval bursts. Three findings that should govern everything below:

- Citation distributions are **power-law / heavy-tailed**, with log-space
  standard deviations of 0.378–0.504 by platform. The paper publishes **no
  exponent** — any summary quoting you an α for it is inventing one.
- **Differences below 5–7 percentage points in citation share sit inside the
  noise floor.** Overlapping intervals at that scale are, in the paper's words,
  "the norm rather than the exception."
- Single-run visibility metrics give "a misleadingly precise picture."

Any dashboard reporting a single-run score with no interval is reporting a coin
flip to three decimal places.

### Sample sizes that actually buy an interval

From the same paper (§5.7), for a 95% CI **width** of 0.05:

| Platform | n for citation share | n for citation prevalence |
|---|---|---|
| Gemini | ≈ 30–50 | ≈ 140–150 |
| Perplexity | ≈ 90–100 | ≈ 140–150 |
| SearchGPT | ≥ 150 | ≈ 60–80 |

Per platform, per topic. A defensible multi-engine panel is therefore **~150
distinct prompts per engine** — not the ten a founder actually runs.

**Spend the budget on distinct prompts, not reruns.** Between-question variance
(different prompts yielding 60% vs 20% mention rates) dominates within-question
variance (the same prompt rerun). Reruns only average out model stochasticity:
**K = 3 is enough**, and every call after that belongs in prompt coverage.
Discovered Labs' free LLM Eval Calculator returns 353 prompts × K=3 = 1,059
calls at 95% / ±2%, which is a useful order-of-magnitude check — but it is **a
vendor tool with an undisclosed formula, published by a company selling a
tracker.**

### The baseline problem, which is our actual problem

Two 2026 audits put a number on where a product like this starts:

- **Sharma, arXiv 2601.00912** (112 Product Hunt startups, 2,240 queries):
  recognition when named is **99.4%** on ChatGPT — but organic discovery, the
  "best tools for X" query, is **3.32%** on ChatGPT and 8.29% on Perplexity. A
  ~30:1 gap. Referring domains (+0.319), Reddit presence (+0.395) and launch
  rank (−0.286) predicted Perplexity visibility; **GEO tactics showed no
  meaningful correlation.**
- **Jack et al., arXiv 2605.27439** (37,000 runs, 215 commercial prompts, 19
  sectors): L4/L5 brands — specialists and regional players — **never surface in
  48–52% of runs.**

Saibyl is L5 with a parked domain. Expect a true non-branded citation rate near
zero, and understand what that does to measurement (Wilson intervals):

| Observed | Sample | 95% interval |
|---|---|---|
| 3 hits | n = 100 | **1.0% – 8.5%** |
| 30 hits | n = 1,000 | **2.1% – 4.3%** |

Three hits in a hundred runs means "somewhere between 1% and 8.5%" — an
eightfold range, which is not an answer. **Detecting a real move off a ~0%
baseline needs roughly n ≥ 700 per arm.** That is out of reach here, and
pretending otherwise is how founders end up paying for trackers that tell them
nothing.

**So for the first 90 days, do not try to measure our own citation rate.**
Measure the two things that are measurable at this size:

1. **The cited set** — *who else* gets cited on our prompts. Their rates are
   high, so they are precisely estimable at small n. That tells us what must be
   displaced, and it is the only prompt-panel output worth the API spend before
   the domain has any authority.
2. **Server-side facts**, below, which are not samples at all.

### Separating our change from the platform's growth

The most important methodological result in this literature, and the cheapest
to copy. **Watanabe & Nakayashiki, arXiv 2606.04362** (2026-06-03) ran a
log-based natural experiment on glasp.co: AEO work concentrated on one subset
of pages, with the untreated remainder of the same domain as a contemporaneous
control.

| Measure | Value |
|---|---|
| Raw site-wide ChatGPT referral growth | **5.7×** |
| Untreated control pages | 3.5× |
| **Treated effect (interrupted time series)** | **1.82× (95% CI 1.31–2.54, HAC p = 0.001)** |
| Engagement-filtered | 2.27× |
| Placebo test | p = 0.16 — the authors flag their own pre-period as short |

Read the first row again. **The headline number was roughly three times the
real effect**, and the difference was platform growth. Nearly every AEO case
study in circulation reports its 5.7× and calls it a result.

**This design is free and it fits a one-person company, because it only
requires not changing everything at once.** Concretely: Part 5 item 4
prerenders the marketing routes — **prerender half, hold half back three to
four weeks**, then compare treated against untreated on the same domain over
the same window. Stagger items 8 and 9 the same way.

Honest limit: at our traffic an interrupted time-series will itself be
underpowered, and there is no pre-period at all until the domain moves. The
control-group *discipline* still earns its keep — it is what stops us
attributing a Google index refresh to our own work.

### What to record

One row per prompt × engine × run. The last three fields are the ones tools
routinely drop:

| Field | Definition | Why it matters |
|---|---|---|
| `cited` | Our domain appears in the citation list | The headline metric, and the noisiest |
| `position` | Index of our citation among sources | List position is a dominant driver of being cited first (Vishwakarma et al., arXiv 2605.25517 — 252,000 trials, six LLMs) |
| `mentioned_unlinked` | "Saibyl" in the answer text with **no** link | Drives branded search; most trackers never record it, so it is invisible in every dashboard |
| `verbatim` | Longest shared span with our page, in words | Separates *selection* from *absorption*: ChatGPT cites fewer sources but shows substantially higher citation influence per fetched page (Zhang et al., arXiv 2604.25707 — 21,143 citations, 602 prompts) |
| `cited_set` | Every other domain cited | The real scoreboard while our own rate is zero |
| `run_index` | Which of K reruns | Without it the two variances cannot be separated |

### Two traps particular to this measurement

**1. Logged-out testing measures the wrong product.** Discovered Labs — a
vendor selling the alternative, and not peer-reviewed — reports that incognito
ChatGPT has the web tool disabled, so domains reading 0% in incognito tests
read 5–8% under logged-in conditions. The mechanism costs nothing to verify
yourself: ask logged-out and logged-in, and watch whether it browses. The
consequence is structural. **Testing without browsing measures the model's
parametric memory, not the search index.** For a brand with no parametric
presence, that reads 0.00% forever and teaches us nothing.

**2. The two largest content experiments disagree.** Part 1 takes its
content-shape numbers from the GEO paper (KDD 2024). Vishwakarma et al. (arXiv
2605.25517, 2026-05-25; 252,000 trials, 18 factors, paired head-to-head
comparisons) finds that **"formatting-only edits have little impact,"** with
topical relevance and list position dominating. These are not the same
experiment — one edits a document in isolation, the other puts two documents in
competition for one slot — but **treat Part 1's content levers as a hypothesis
to test, not a settled lever.**

### Free versus paid, honestly

**Free, and they are facts about our own server rather than samples from a
model:**

- **Referral logs / GA4** — `chatgpt.com`, `perplexity.ai`, `claude.ai`,
  `gemini.google.com`, `copilot.microsoft.com`. ChatGPT appends
  `?utm_source=chatgpt.com` to links it cites, so attribution survives in raw
  logs even where the referrer header is stripped. **This is the
  highest-quality signal available to us and it costs nothing.**
- **Search Console generative-AI reports** (shipped 2026-06-03, alongside the
  toggle in Part 1). Know the limits first: **impressions only** — no queries,
  clicks, CTR, position or citation placement — and rolled out to a subset of
  properties, so we may not have it. Google's own AI-features developer docs
  still describe AI traffic as folded into the `Web` search type, i.e. the
  documentation lags the product. A diagnostic, not a scoreboard.
- **Self-hosted trackers**, if a panel ever justifies itself: `elmohq/elmo`
  (MIT) and `Canonry/canonry` (FSL-1.1-ALv2, converting to Apache 2.0), the
  latter ingesting server logs and connecting GSC/GA4. Both are free to license
  and run on **our own API keys**, so the true cost is calls — a 150-prompt ×
  K=3 × 4-engine cycle is ~1,800 of them.

**Paid rank-trackers: not yet.** One is worth money only once a 5–7pp move
would be meaningful — that is, once we are cited at all. Below that we are
paying a subscription to watch the noise floor. **Do not buy one in the first
90 days.**

### Decision rules

- **Never** act on a single run, on a move smaller than **7 percentage
  points**, or on a before/after with no untreated control.
- Report every rate with an interval. A rate without one is not a number.
- Call a change real only after it holds across **three consecutive cycles**.
- Re-baseline after any confirmed model or index update. Those are not our
  results either, in either direction.

**What would falsify the strategy:** if, 90 days after the domain moves,
prerendered pages show no referral advantage over the untreated ones, the
problem is not content volume — it is that Part 3's citability thesis is wrong
for this category, and the effort belongs on the mailing list instead.

---

## Part 5 — The 30-day plan

Every row carries its own check, so the plan can tell whether it worked. The
thresholds behind these checks are in Part 4 — in particular, **nothing here
counts as a result on one run or on a move under 7 percentage points.**

| # | Action | Effort | Payoff | How you'll know |
|---|---|---|---|---|
| **1** | **Point saibyl.com at the Render frontend** | S | **Blocking — nothing else counts** | `curl -I saibyl.com` returns the Render app, not GoDaddy |
| 2 | Search Console: verify, and set the generative-AI toggle to *include* | S | **Gates all Google AI citation** | Property verified, toggle reads *include*; confirm whether we are in the AI-report rollout at all |
| 3 | `robots.txt`, `sitemap.xml` — **done**; create `og-image.png` | S | High | All three fetch as files at 200 |
| 4 | Prerender marketing routes to static HTML | M | **Highest AEO unlock** | Copy visible in `curl` output — **ship half, hold half as control (Part 4)** |
| 5 | Then scope the `/*` rewrite so unmatched paths 404 | M | High | Junk path returns 404; the four real routes still 200 |
| 6 | Per-page title/description/canonical (one title serves every route today) | S | High | Each route's `<title>` differs in view-source |
| 7 | JSON-LD into the prerendered HTML — **written**, needs #4 to be seen | S | Medium | Rich Results Test parses it from the *served* HTML |
| 8 | The synthetic-accuracy reconciliation table | M | **Highest, no consent needed** | Referral baseline captured before publish; treated vs untreated at 30 days |
| 9 | Three IP-worry pages, question-shaped, sourced | M | High | Same — **stagger against #8**, never the same week |
| 10 | Brand SERP: `/about`, `/method`, one comparison page | S | Medium | Brand query returns our pages, not the parking page |
| 11 | `llms.txt`, `noindex`ed | S | Low — a Lighthouse checkbox | Lighthouse stops flagging it |
| 12 | Bing Webmaster Tools + IndexNow | S | Medium | Bing index count > 0; IndexNow returns 200 |
| 13 | Community presence, per-subreddit rules | M | Medium | `reddit.com` referrals appear in logs |
| 14 | Objection Index v1 — **only after** the privacy revision and opt-in ship | L | Highest long-term | Cited-set tracking (Part 4), not our own citation rate |

**Items 1–3 are all Small and are the difference between invisible and
crawlable. Do them this week.** Item 1 also starts the clock: there is no
pre-period, and therefore no measurable anything, until the domain moves.

Three cautions. **Skip Hacker News** — at least ten near-identical
validation-tool launches since early 2025, none gaining traction. **Reddit's
citation value is contested**: one source has it as the most-cited domain in
ChatGPT, another reported an ~86% collapse in mid-August 2026 after a
retrieval change, and a third argues that collapse is partly an artifact of
incognito-mode trackers rather than a real retrieval change (Part 4) — do not
build on one surface. And the mailing list of tens of
thousands of founders will outperform everything here for the next 90 days.
**AEO compounds; it does not launch.**
