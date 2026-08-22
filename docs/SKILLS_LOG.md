# Skills Log

Standing rule (founder directive, 2026-08-16): every skill — installed,
built, distilled from research, or productized — is recorded here with where
it lives and what it's for. Newest at the top. "Skill" here covers session
skills (`~/.claude/skills/`), MCP servers, distilled methodologies, and
product features that began as skills.

---

## 2026-08-22 — `ip-clearance-search`: the port now deviates from the skill

The clearance artifact still matches the skill's output contract **key for
key** — every key present on every run, `queries_run` complete, disclaimer
verbatim. It no longer matches it **value for value**: personal contact
channels (email, phone, postal address) inside `owner`, `assignee`, `title`,
`claim_requirements`, `differences`, `query` and the watch list are replaced
with `[contact detail removed]` by `services/clearance/privacy.py`. Names of
record are untouched.

Recorded here because the port's fidelity to the upstream contract is what
kept anyone from looking at what it was storing (see CRITICS_LOG, same date).
A future session comparing Saibyl's output against a raw skill run will see
this difference and should not "fix" it.

## 2026-08-17 — Authed-app screenshot rig (restyle proof harness)

Reusable playwright scripts for reading the deployed-quality app by eye,
kept in the session tmp this pass but worth reconstructing from this note:
- **Login + route walk**: fill the login form with a disposable account
  (HANDOFF_POLISH §6), wait for `**/app/**`, shoot each route at 1440 and
  390 full-page.
- **The scroll-container trap**: the app shell scrolls inside `<main>`, so
  before `screenshot(full_page=True)` run JS that sets every
  `overflow:auto` element to `visible` and `h-screen` to `auto` — otherwise
  you capture one viewport and call it the page.
- **CORS**: the deployed backend refuses a localhost origin; run
  `VITE_PROXY_TARGET=https://saibyl-backend.onrender.com npx vite dev` and
  point the app at `/api` (the proxy override added to vite.config.ts).
- **Critic gauntlet on the shots**: three blind sub-agents with distinct
  lenses (hierarchy/consistency; accessibility/craft; reference-anchored
  brand coherence with the landing screenshot as ground truth), each
  ordered to name elements and rank severity, each given a
  strengths-to-preserve requirement.

## 2026-08-16 — Distilled methodologies (Jack Roberts research corpus)

Transcripts pulled and distilled (saved in the session's tmp; distillations
summarized in PRD §4b² and CRITICS_LOG):
- **Site-evaluation playbook** (video NAumQObJEwM): reference-anchored
  evaluation — the site-you-like's extracted tokens as ground truth; "be
  ruthless"; named-gap output with both measured values; the five slop tells
  (typography, imagery, hierarchy, color, spacing). → productized as the
  sixth critic + census.
- **Claude design levels** (RDytbVDzMF4): font is the #1 slop tell; one
  asset family per piece; codify winning styles as standing instructions;
  real data over invented; Firecrawl `branding` format for cheap brand
  extraction. → font-slop signal, style-consistency signal, design-DNA
  persistence.
- **The 7 levels** (AFRL9dtUHeI): grab-and-go → references → design skills →
  media tools → UI snapping → data → design extraction. → the 1–7 maturity
  ladder (score = highest level whose signature the site exhibits); the
  winners-vs-losers L6 sweep flagged as a future paid feature (HANDOFF).
- **styles.refero.design**: the DESIGN.md model — characterization line,
  token tables with roles, do/don'ts, agent-prompt guide, Tailwind/CSS
  blocks. → the shape of Saibyl's extracted design-DNA artifact and the
  `design_gallery` schema. Also of note: the "gauntlet loop" from the
  earlier video (jq9LRwE0-GQ) drove the landing-page redesign method.

## 2026-08-16 — Installed session skills

- **ip-clearance-search** (`~/.claude/skills/ip-clearance-search/` +
  references: query-patterns, cpc-field-map, output-contract) — founder-built
  USPTO clearance methodology; ALSO the spec of record for the product's
  Phase IP (PRD §11). Source archive + sibling `provisional-patent.skill` in
  `Saido Labs LLC/Provisional Patent MCP and Skill/`.

## 2026-08-16 — MCP servers & reference implementations

- **uspto-patent-mcp** (founder-built, complete TypeScript, 20+ tools;
  zip + plugin in `Provisional Patent MCP and Skill/`) — the reference
  client whose quirks and anti-hallucination discipline were ported into
  `services/clearance/uspto_client.py`. Registered as a Cowork plugin
  (`uspto-patent-search@inline`).

## 2026-08-16 — Product features born from skills

- **Phase IP / IP Check tab**: the ip-clearance-search skill, productized.
- **Website check sixth critic + design gallery**: the Roberts playbooks +
  refero DESIGN.md model, productized (PRD §4b²).
