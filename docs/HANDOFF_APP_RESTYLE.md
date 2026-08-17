# Handoff — the app-shell light restyle

**Written 2026-08-17 for a cold context window. Read this whole file before
touching anything, then read `docs/HANDOFF.md` §2/§2a (standing rules and
failure classes) and the five logs (`ARCHITECTURE_LOG`, `INFRA_LOG`,
`DECISIONS_LOG`, `CRITICS_LOG`, `SKILLS_LOG` — the critic's log is the
lessons-learned document and most of its lessons were paid for this week).**

## 0. The mission, in the founder's words

The founder (Jesse — no personal name ever appears on the product; it is a
Saido Labs LLC product) approved the light Saido aesthetic now live on the
public landing page and said: **"I love the new aesthetic and want the whole
site to have this look."** The job: restyle **everything behind the login**
— app shell, rail, every page — to the light system. **Ship this week, go
live in production.** He has explicitly pre-authorized autonomous execution
for this restyle: spin up multiple sub-agents, grind through it today while
he is out, commit, merge to master, and deploy without waiting for him.
(That authorization covers THIS restyle. Phase D of PRD_V3 still gates the
mailing-list launch and awaits his go.)

Standing founder orders that bind every line you produce:
- **Never** add Claude/Anthropic attributions to commits, PRs, or output.
- The 12 banned words never render (enforced by `frontend/src/test/ia.test.ts`:
  ICP, variant, A/B, adversarial, cohort, arena, lens, archetype, canonical,
  valence, simulation, project — plurals, case-insensitive). No `disabled`
  attributes. EmptyStates carry actions. Stated sentences, busy labels.
- Update whichever of the five logs a change touches, in the same batch.
- A check that can pass for the wrong reason is worse than no check: deploy
  verification uses discriminators only the new build can produce; visual
  claims are verified by reading rendered screenshots, not by green builds.

## 1. Where everything stands (state snapshot)

- Branch/flow: work in the worktree
  `C:\Users\jcapa\OneDrive\Personal\Saido Labs LLC\Saibyl\Saibyl Code Base\.claude\worktrees\v3-prd`
  (EnterWorktree with that path), branch `v3-prd`. Ship = commit there →
  `git push origin v3-prd` → from the MAIN checkout
  (`…\Saibyl Code Base`) `git merge --ff-only v3-prd` → `git push origin
  master`. Master push runs CI (gated) then Render deploys both services.
  master == v3-prd == `0a86082` at handoff time.
- Shipped and live: V3 Phase A (realignment), Phase IP (USPTO clearance
  tab), Phase B (website check: capture → six critics), design augmentation
  (style census, reference-anchored "The look" critic, design-DNA gallery,
  admin feed), Phase C (revision gauntlet loop, before/after, fix prompts,
  room re-run via inoculation), and the light **landing page** (+ /privacy,
  /terms). Migrations 032–037 all applied to production.
- The backend suite is 1,318 passing; frontend vitest 16 (ia acceptance
  scans). Local Python env: the OneDrive-shared `.venv` fights uv with file
  locks — use `UV_PROJECT_ENVIRONMENT=C:\Users\jcapa\.venvs\saibyl-v3`
  (has playwright + chromium). Frontend worktree has a node_modules
  junction to the main checkout.
- **Owed by the founder in Render env (repeat to him at the end):**
  `USPTO_ODP_API_KEY`, `USPTO_TSDR_API_KEY` (values in repo root `.env`),
  `ADMIN_ORGANIZATION_ID=231b7f17-d17c-4f6e-b530-f0196acd841b`.
- Launch blockers beyond this restyle (flag, don't solve unless told):
  saibyl.com domain in front of Render; formal privacy policy (current
  /privacy states practice and says a formal one is coming); the public
  Tallyhook sample report; PRD Phase D (the wow gate) before the mailing
  list.

## 2. The design system (source of truth)

- **Live reference:** `frontend/src/pages/landing.css` — the shipped light
  system, every selector scoped under `.v3land`. The prototype it was
  ported from (design intent, all sections):
  `Saibyl Management\Saibyl Redesign\Saibyl Redesign examples\saibyl-landing-v3-saido.html`.
- Tokens: paper `#f8fbff` ground (+ soft radial washes), ink `#14294a`,
  muted `#60718e`, line `rgba(38,79,139,.14)`, blue `#286cf0`, violet
  `#8b73ee`, cyan `#35c7d5`, green `#2fbf8a`, rose `#ff6e79`; radii 12–28px
  family; shadows soft (`0 22px 60px rgba(52,96,164,.12)`); glass cards
  (`rgba(255,255,255,.6-.85)` + hairline borders + backdrop-blur).
- Type: **Manrope** (UI + headings, tight negative tracking on display
  sizes), **Playfair Display italic** for at most one emphasized phrase per
  major heading (the landing page uses it sparingly after a critic called
  the overuse a metronome — do NOT sprinkle it through app chrome; in-app,
  use it only on big empty-state/hero moments, if at all), **DM Mono** for
  eyebrows/labels/metadata (replaces JetBrains Mono roles). Fonts already
  load in `index.html`.
- In-app adaptation rules (this is an APP, not a marketing page): calm
  paper surfaces, hairline borders over shadows for density, one accent
  (blue) owning actions, semantic status colors (green/amber/rose) distinct
  from the accent, contrast ≥4.5:1 for all reading text (the old muted tier
  failed this — a critic caught it; don't repeat it), `font-variant-numeric:
  tabular-nums` where digits align. Charts/visualizations need light-ground
  palettes (grid lines, area fills, endpoint emphasis re-tuned).

## 3. The restyle strategy (do it in this order)

**Wave 0 — the foundation (ONE agent or the main loop; verify + commit
BEFORE fanning out; everything else inherits it):**
1. Inventory the current theme: `frontend/tailwind.config.js` (the
   `saibyl-*` color tokens), `frontend/src/index.css` (globals), and the
   dark habits: grep for `#0B1120`, `#0A0F1C`, `bg-black`, `text-white`,
   `bg-white/`, `border-white/`, `saibyl-gold`, `dark`, hardcoded hexes.
   `index.html` has `class="dark"` on `<html>` — decide its fate
   deliberately (likely remove it and make light the only theme; the
   founder wants ONE look).
2. Remap the Tailwind theme tokens to the light palette so token-using
   components flip wholesale; keep the SAME token names where possible
   (`saibyl-muted` etc. become light-appropriate values) to minimize
   file churn; add tokens the light system needs (paper, ink, line, glass).
   `saibyl-gold` (the old dark-theme accent riding many components,
   e.g. `accent-saibyl-gold` sliders): remap to the blue accent at the
   token level — that single remap converts every slider/CTA.
3. Restyle the shared chrome: `AppLayout.tsx` (nav → the landing page's
   glass-bar language), `components/stages/ProductLayout.tsx` + rail,
   `StagePrimitives.tsx`, `StageHeader.tsx`, `chips.tsx` files, `Guarded`,
   form input base styles. Keep the landing page working — its `.v3land`
   scope protects it, but check nothing global (body bg, fonts) now
   double-applies oddly.
4. Gate: tsc + eslint + vitest + build, then `npx vite preview` +
   playwright screenshots of ONE authed page and the landing page, read
   them by eye. Commit wave 0.

**Wave 1 — the pages (PARALLEL sub-agents, disjoint file ownership — the
proven pattern; pin the token vocabulary in every prompt; each agent runs
tsc/eslint/vitest on its files and reports verbatim):**
- Agent A: auth — `LoginPage.tsx`, `SignupPage.tsx` (currently the dark
  split-panel with stats; re-imagine on paper with the landing's language).
- Agent B: home + intake — `ProductHomePage.tsx`, `NewProductPage.tsx`,
  `pages/product/AudienceStagePage.tsx`, `IdeaBriefForm.tsx`.
- Agent C: the rest of the rail — `ReactionsStagePage.tsx`,
  `AnswersStagePage.tsx`, `BuyersStagePage.tsx`, `MessagesStagePage.tsx`.
- Agent D: run setup — `NewSimulationPage.tsx`, `RunConfigurator.tsx`,
  `founder/FounderLensStep.tsx`, `founder/AudienceReview.tsx`.
- Agent E: IP Check — `IpCheckPage.tsx` + `components/clearance/*`.
- Agent F: website intel — `components/website/*` (SiteCheckForm,
  SiteCritique, SiteRevision, SiteRevisionPanel, chips).
- Agent G: dashboard/guide/settings — `DashboardPage.tsx`, `GuidePage.tsx`,
  `SettingsPage.tsx`.
- Agent H: simulations surfaces — live run page, report viewer page,
  compare page, `components/analysis/*` charts (light-ground palettes!),
  `MarketingPage.tsx`, legacy `ProjectsPage/ProjectDetailPage`,
  `PackLibraryPage`, prospects/discover pages.
  (`ReportPrintPage` prints to PDF via the browser — check its print CSS
  assumptions; the *exported* PDF is backend WeasyPrint and out of scope.)
Check `App.tsx`/router for any page missed; grep for remaining dark hexes
tree-wide after the wave.

**Wave 2 — proof (main loop, not agents):**
1. Full gates: backend suite (nothing should change but run it), tsc,
   eslint, vitest, `npm run build`.
2. **Visual verification with eyes, not exit codes**: build + `npx vite
   preview --port 4273`; the SPA needs env at build (`VITE_SUPABASE_URL`
   etc. — build with placeholder env for preview or reuse the throwaway
   pattern in the restyle-port agent's report; `src/lib/supabase.ts` throws
   at import when unset — a blank dark page means THAT, not a style bug).
   For authed pages: run `npx vite dev` (proxies /api to localhost… the
   proxy targets localhost:8000; instead point `VITE_API_URL` at the
   production backend for a read-only look) and log in with a disposable
   production account from `docs/HANDOFF_POLISH.md` §6 (e.g. the
   ia-acceptance account) via a small playwright script (fill login form,
   screenshot each key route at 1440 and 390). Read every screenshot.
   Key screens: login, home, audience (all three intake paths visible),
   a complete site check + revision, IP Check with a past report, run
   setup, dashboard, settings, a report page.
3. Run 2–3 fresh visual critic sub-agents on the screenshots (the gauntlet
   pattern — blind, harsh, named elements; see CRITICS_LOG for the format).
   Fix what they find. Re-shoot.
4. Commit waves as coherent chunks (plain conventional messages, detailed
   bodies, NO attributions), push v3-prd, ff master, push. Deploy watcher
   discriminator: grep the served JS/CSS bundle for a marker only the new
   build carries (e.g. a new token name), 404→marker flip. Screenshot the
   LIVE site and read it before declaring done.
5. Update the five logs + `~/.claude/projects/C--Users-jcapa/memory/saibyl.md`.
6. Send the founder the before/after screenshots and the report. Repeat the
   three owed Render env vars.

## 4. Traps that already bit this week (do not pay for them again)

- Full-page screenshots + IntersectionObserver reveals = invisible
  sections; the landing page has a load-fallback now — reuse the pattern
  if you add reveals; screenshot with generous wait.
- Parallel agents: pin file ownership per agent (never two agents in one
  file); pin interface contracts in prompts; expect seam bugs where
  fixtures were written by the same author as the code — verify seams
  yourself after landing.
- The jargon scan covers the WHOLE tree including attributes; "project" is
  banned (say product/workspace).
- OneDrive locks: never run `uv sync` against the shared `.venv`;
  the local venv path above is canonical.
- `git worktree` metadata may print `failed to delete …saibyl-pre:
  Permission denied` on every commit — harmless, ignore.
- Keep `landing.css`'s `.v3land` scope intact; the app-wide light theme
  must not double-style the landing page (visual-check it after wave 0).
- Contrast: every muted text token ≥4.5:1 on its surface. Slider/range
  inputs use the updater form (see RunConfigurator's comment) — don't
  regress it while restyling.

## 5. Definition of done

Every route behind `/app` renders the light system with no dark remnants
(tree-wide grep for the dark hexes is clean), all gates green, key screens
read by eye at both widths, critic pass addressed, deployed to production
with the bundle discriminator verified and a live screenshot read, logs and
memory updated, founder report sent with before/afters. This week's clock
matters: bias to shipping waves as they're proven rather than one giant
drop.
