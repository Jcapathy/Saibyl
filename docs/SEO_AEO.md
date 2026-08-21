# SEO and AEO — being found by people, and cited by machines

**Written 2026-08-20**, from primary sources (crawler docs from OpenAI,
Anthropic, Perplexity and Google; Google's rich-results gallery and JavaScript
SEO docs; the IETF AIPREF drafts; the KDD 2024 GEO paper) plus live checks
against the deployed site. Where a claim is contested or rests on one study,
it says so — this file is meant to be actionable, not confident.

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

## Part 4 — The 30-day plan

| # | Action | Effort | Payoff |
|---|---|---|---|
| **1** | **Point saibyl.com at the Render frontend** | S | **Blocking — nothing else counts** |
| 2 | Search Console: verify, and set the generative-AI toggle to *include* | S | **Gates all Google AI citation** |
| 3 | `robots.txt`, `sitemap.xml` — **done**; create `og-image.png` | S | High |
| 4 | Prerender marketing routes to static HTML | M | **Highest AEO unlock** |
| 5 | Then scope the `/*` rewrite so unmatched paths 404 | M | High |
| 6 | Per-page title/description/canonical (one title serves every route today) | S | High |
| 7 | JSON-LD into the prerendered HTML — **written**, needs #4 to be seen | S | Medium |
| 8 | The synthetic-accuracy reconciliation table | M | **Highest, no consent needed** |
| 9 | Three IP-worry pages, question-shaped, sourced | M | High |
| 10 | Brand SERP: `/about`, `/method`, one comparison page | S | Medium |
| 11 | `llms.txt`, `noindex`ed | S | Low — a Lighthouse checkbox |
| 12 | Bing Webmaster Tools + IndexNow | S | Medium |
| 13 | Community presence, per-subreddit rules | M | Medium |
| 14 | Objection Index v1 — **only after** the privacy revision and opt-in ship | L | Highest long-term |

**Items 1–3 are all Small and are the difference between invisible and
crawlable. Do them this week.**

Three cautions. **Skip Hacker News** — at least ten near-identical
validation-tool launches since early 2025, none gaining traction. **Reddit's
citation value is contested**: one source has it as the most-cited domain in
ChatGPT, another reported an ~86% collapse in mid-August 2026 after a
retrieval change — do not build on one surface. And the mailing list of tens of
thousands of founders will outperform everything here for the next 90 days.
**AEO compounds; it does not launch.**
