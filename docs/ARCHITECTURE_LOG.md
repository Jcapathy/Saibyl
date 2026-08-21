# Architecture Log

Standing rule (founder directive, 2026-08-16): whenever the system's shape
changes — a new package, a new pipeline, a moved boundary, a new external
dependency — the change lands here, dated, with the why. Newest entries at the
top. `ARCHITECTURE_V2.md` remains the deep design document; this is the
running delta record.

---

## 2026-08-20 — The redesign becomes a deliverable the founder keeps

Founder's ask: *"clients who we render a new website for should be able to
see the new site in HTML, that file should be downloadable and the
style/branding guide should go along with it… A medical SaaS start up's site
should look and feel radically different than a financial products start
up's."* Two gaps, one boundary change.

- **`services/website/verticals.py`** — the generator had no idea what kind of
  company it was designing for. It inherited the founder's existing design DNA
  and polished it, so a generic page came back as a better-executed generic
  page, and a clinical product and a payments product were designed by the
  same instincts. Six briefs (health, fintech, devtools, consumer, b2b_saas,
  marketplace) plus a general fallback, each written as a **buyer argument** —
  who signs the cheque, what they must believe, what the page must carry, what
  reads as a warning sign — never as a house style. `brief_section()` is now a
  block in `revise._generation_prompt`.
- **Classification refuses more than it guesses.** A winner needs ≥2 signals
  *and* a ≥2 margin over the runner-up; a medical-billing product that scores
  health and fintech nearly equally falls back to general. A confidently wrong
  brief pushes a page toward conventions its buyer does not hold, which is
  worse than no brief.
- **`services/website/style_guide.py`** — the design DNA was fed *into* the
  generator and never handed *out*. The guide is now rendered from the
  delivered file: colours, faces, radii and shadows extracted from the HTML
  itself, the category brief that shaped it, the measured after-scores, and
  the gallery's characterization of the old site. No model call on this path.
- **`GET /website/revision/{id}/bundle`** zips `index.html` +
  `STYLE_GUIDE.md`, named for the founder's own domain (sanitised — the string
  lands in a `Content-Disposition` header). Charges nothing: both files are
  already-produced artifacts.
- **Boundary note:** the guide classifies from the page's *visible copy*, not
  its markup. Left raw, a Tailwind page votes with its class names and a React
  bundle with its variable names.

---

## 2026-08-20 — The GTM module joins the pipeline (answer pack)

- New `services/gtm/answer_pack.py`: the objection matrix, built from
  `canonical_objections` ranked by load-bearing score with verbatim quotes
  attached. Four moves per objection (acknowledge / an explore **question** /
  respond / confirm) plus battlecards, and `when_to_walk` where the honest
  answer is that the objection cannot be talked away.
- **Deliberately not the inoculation loop.** Inoculation drafts published
  material and re-runs the room to prove the objection moved; this is the
  script for a live call, which no room can score. Same input, different
  artifact, and they are not substitutes.
- Three disciplines enforced in code rather than in the prompt: measured
  numbers are attached from the database (a model asked to echo a score
  eventually rounds it), a row for an objection nobody raised is dropped, and
  battlecards cover only founder-named rivals plus doing-nothing and
  build-in-house. Fact discipline follows `revise.py` — `[TODO: your number]`
  rather than an invented statistic.
- `workers/answer_pack_tasks.py` deliberately does **not** copy the clearance
  worker's failure handling, which writes raw exceptions into a
  founder-visible column (logged as P1-7). The exception goes to the log; the
  founder gets a sentence.
- New table `answer_packs` (migration 038), routes under `/api/answer-pack`,
  price published through `/billing/prices`, panel on the Answers step.
- Priced 1,500 credits — COGS $0.30 at the 80% target margin through the same
  helper as the website check and the clearance tiers. PROVISIONAL until the
  ledger confirms it.

## 2026-08-17 — The app-shell light restyle, waves 1–2: pages, charts, critics

- Ten parallel agents with disjoint file ownership restyled every page
  behind the login on top of wave 0's token flip (auth re-imagined on
  paper; rail, run setup, IP Check, website intel, dashboard/guide/
  settings, simulations/reports/prospects). Charts retuned for a white
  ground (SentimentArcPlot, SectionRenderer, HeadlineStats and friends):
  rgba(99,139,202,.18) grids, ink labels, bright hues as fills only.
- Shared palettes nobody owned were remapped centrally: `CHART_COLORS`
  and `gtm.TONE_COLOR` now hold values that pass 4.5:1 as text on white
  (both color text directly). `ReportExport` was on no agent's list and
  was caught by the tree-wide sweep — the sweep is not optional.
- Three blind visual critics reviewed the rendered screenshots; their
  agreed findings were applied the same day (the color-grammar law now in
  DECISIONS_LOG; details and open debt in CRITICS_LOG).
- The jargon scanner (`src/test/source.ts`) now reads `title:`/`q:`/`a:`
  object keys — the GuidePage data arrays were rendering "A/B testing"
  under a green test.

## 2026-08-17 — The app-shell light restyle, wave 0: the theme foundation

- The whole app behind the login moves to the landing page's light system
  (founder order: "I love the new aesthetic and want the whole site to have
  this look"). Wave 0 is the token layer, so token-riding components flip
  wholesale: `tailwind.config.js`'s `saibyl-*` palette keeps its dark-era
  NAMES but now carries the light values — `void` means the paper ground
  (#f8fbff), `gold` means the blue accent (#286cf0), `platinum` means ink
  (#14294a). One remap converted every gold CTA/slider to blue and every
  void surface to paper without touching the ~290 call sites.
- Every text-bearing token value holds ≥4.5:1 on white and paper (the
  muted tier is #60718e at 4.7:1 — the old tier failed WCAG and a critic
  caught it). Bright hues (#2fbf8a green, #ff6e79 rose) are fills/dots
  only; chips pair them with darker same-hue text.
- `index.css` globals flipped (shadcn HSL vars, body, typography classes,
  `.glass`, `.bg-grid`, gradients); fonts move Aktiv Grotesk→Manrope,
  JetBrains Mono→DM Mono at the token level. `index.html` drops
  `class="dark"`; `ui/button.tsx` drops its `dark:` variants (Tailwind's
  media strategy would have re-darkened controls for dark-OS visitors).
- Shared chrome restyled by hand where values were hardcoded: `AppLayout`
  (glass sidebar, landing brand mark replacing the dark logo asset, mobile
  clearance under the fixed toggle), `ProductLayout` rail, `StagePrimitives`,
  `StatusBadge`, website chips.
- `vite.config.ts` proxy target is now `VITE_PROXY_TARGET`-overridable so a
  local session can screenshot authed pages against the deployed backend —
  browser CORS forbids a localhost origin calling it directly; the
  server-side proxy is origin-less.
- The landing page's `.v3land` scope verified untouched by screenshot.

## 2026-08-16 — Phase C: fix & prove (PRD §4d)

- `capture.py` gains `capture_html` — renders a provided HTML string through
  the same screenshot/census pipeline, with every outbound request aborted
  (a generated page must not beacon or stall on a dead CDN).
- New `services/website/revise.py`: the gauntlet loop — generate a complete
  self-contained page (32K streaming ceiling), render it, re-judge with the
  six critics, iterate to a target or 3 rounds; best round wins, strictly —
  a regression is recorded but never shipped. Fact discipline: the page's
  own words are the only fact source; missing facts render as
  `[OWNER: fill in]`. Plus the deterministic fix-prompt composer (one
  paste-ready block per dimension + a rebuild-to-DNA block).
- New `page_revisions` table (migration 037) + revision routes under
  `/api/website` (create/status/list, HTML download, before/after screenshot
  passthrough); revisions cost 5,000 credits (PROVISIONAL). Admin gallery
  feed now joins the latest complete revision — before/after-ready.
- The prove leg rides the EXISTING inoculation machinery untouched:
  `/api/website-room` files the revised page's text as an asset on the
  parent run's top objection and calls `create_resimulation` (same copied
  agents = same audience); charging stays at the simulation start route.
  Known compromises documented in `room_run.py`: one-objection filing,
  `disclosure` asset type, the 700-char asset prompt window.
- `llm_client.llm_vision` streams when max_tokens > 8192 — the SDK refuses
  non-streaming ten-minute-class requests (found live).

## 2026-08-16 — Design-intelligence augmentation (PRD §4b²)

- `capture_website` now collects a **style census** (deterministic
  computed-style aggregation: fonts/weights, letter-spacing, palette
  frequencies, radius/shadow vocabularies, spacing histogram) alongside
  screenshots and DOM text — the census is the receipt behind every design
  claim.
- New `services/website/design_dna.py`: one vision call turns capture +
  census into a refero-shaped DESIGN.md artifact + 1–7 maturity level.
- Critic gauntlet grows a sixth dimension, `design` ("The look"), with two
  modes: absolute (slop-tell checks) and reference-anchored (both sites'
  censuses measured against each other; findings carry both values).
- New `design_gallery` table (migration 036): every check persists its DNA,
  census, screenshots, scores. Platform-admin read routes at `/api/admin/*`,
  gated on `ADMIN_ORGANIZATION_ID`.

## 2026-08-16 — Phase B: website intelligence (PRD §4a–c)

- New `services/website/` package: `capture.py` (Playwright chromium,
  desktop 1440 + mobile 390 full-page, SSRF-validated before fetch and after
  redirects via `core/security.validate_external_url`), `store.py`
  (screenshots to the `project-media` bucket; no row ops), `critics.py`
  (five independent one-call vision reviewers, concurrent, five-or-nothing).
- `core/llm_client.py` gains `llm_vision` — **Anthropic SDK direct**, because
  litellm silently drops Anthropic-native image blocks (pinned by test).
- `api/website.py` + `workers/website_tasks.py`: check lifecycle
  queued→capturing→judging→complete/failed; the page's text becomes a
  document (`material_kind='website_url'`) and joins subject material.
- Docker image installs chromium at `/ms-playwright` (root-owned shared
  path, before USER drop).

## 2026-08-16 — Phase IP: USPTO clearance (PRD §11)

- New `services/clearance/` package: `uspto_client.py` (ODP/DSAPI/TSDR with
  the reference server's quirks: search-404 = zero hits, claims XML cached
  24h against the ~20/URL/year cap, key masking, host-check on
  fileLocationURI), `query_plan.py` (Stage 0+1 in one structured call),
  `claim_reader.py`, `tracks.py` (A–D orchestration with count triage),
  `artifact.py` (exact output-contract JSON + report renderer).
- `api/clearance.py` + `workers/clearance_tasks.py`; tables
  `clearance_runs`/`clearance_findings` (migration 034). Free QUICK tier is
  org-rate-limited; STANDARD/COMPREHENSIVE charge credits at creation.
- There is **no public USPTO word-mark search API** (TESS retired) —
  trademarks are status-by-serial + the official link; NOT_SEARCHED is a
  first-class honest status.

## 2026-08-16 — Phase A: V3 realignment

- `app/core/tasks.spawn` replaces four per-router `_safe_task` copies and
  holds strong task references (audit 19's GC half).
- Idea-brief intake: `POST /documents/idea-brief` composes five answers into
  a document through the normal `store_upload` path
  (`material_kind='idea_brief'`); the synthesizer's 1,000-char floor exempts
  idea briefs.
- Crisis lens shelved behind `CRISIS_ENABLED` (default false, 404 before DB).
- Deleted dead subsystems (audit 39): `/api/platforms` router, `/api/uploads`
  shim, the entire ontology/knowledge-graph chain including the report
  engine's three never-functional graph tools (−1,138 lines).
- Report engine reads the whole run (audit 40): the arena-filtering `variant`
  parameter removed; `simulation_analytics` defaults to `"all"`.
