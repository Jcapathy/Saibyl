# Saibyl

Saibyl, by Saido Labs LLC, is a synthetic-market SaaS: an AI-builder founder pastes an idea or a site, a swarm of synthetic buyers reacts, and the product returns specific objections and paste-ready fixes (V3 direction; the V1 "oracle" positioning is dead). Good means the "wow standard": brutal specificity, voices that feel real, paste-ready fixes, proof of the delta.

This file extends the global CLAUDE.md. It holds only facts specific to this project.

## Stack & commands

- Stack: FastAPI (Python >=3.12, uv, ruff, pytest) + React 19 / TypeScript / Vite 8 / Tailwind 3 + Supabase (Postgres, Auth, Storage) + Anthropic via LiteLLM (vision calls use the Anthropic SDK directly) + Playwright/chromium + Stripe (live since 2026-08-28) + Redis. Deploys to Render (`render.yaml`, Docker for the backend). Repo: github.com/Jcapathy/Saibyl.
- Install: `cd backend && uv sync --dev`; `cd frontend && npm ci`
- Run: `cd backend && uv run uvicorn app.main:app --reload`; `cd frontend && npm run dev`
- Test: `cd backend && uv run pytest -q`; `cd frontend && npx vitest run`
- Lint: `cd backend && uv run ruff check app tests scripts`; `cd frontend && npx eslint src --quiet`
- Before "done", run, from `frontend/`: `npm run build` (`tsc -b && vite build`, plus prerender; what Render runs), `npx eslint src --quiet`, `npx vitest run`. From `backend/`: `pytest` and `ruff check app tests scripts` (the original gate states `ruff check app tests`). Gate the frontend with `npm run build`, never `tsc --noEmit` alone (see Overrides). Last recorded counts (docs/HANDOFF_LAUNCH_READINESS.md §6, 2026-08-30): 2,112 backend, 143 frontend.
- Migrations: `backend/scripts/migrations/NNN_*.sql` (latest 046), applied with `backend/scripts/migrations/apply.py`.
- Windows/OneDrive: the repo `.venv` fights uv with file locks. Use `UV_PROJECT_ENVIRONMENT=C:\Users\jcapa\.venvs\saibyl-v3` (has playwright + chromium).
- Deploy verification: use a discriminator only the new build can produce, in both directions where possible (new string present and old string absent). A green health check proves nothing about the route you shipped.
- Release flow: work on branch `v3-prd` (worktree `.claude/worktrees/v3-prd`), fast-forward to `master`; `master` is what Render deploys. As of 2026-08-17 the session permission layer declined master pushes, so the founder may need to run `git push origin v3-prd:master`.

## Layout & off-limits

- `backend/app/` (api, core, models, services, workers), `backend/tests/`, `backend/scripts/` (migrations, seed, live-run scripts, `send_followups.py`), `backend/data/persona_packs/`.
- `frontend/src/` (pages, `components/design/` shared primitives, `test/ia.test.ts`, `test/design_primitives.test.ts`); `shared/` is empty.
- `design/`: README.md, four self-contained artboards (`Main`, `Answers`, `Next`, `Report` `.dc.html`) and `canvas.json`. See Frontend work.
- `docs/`: HANDOFF.md (read first; §2/§2a hold the standing rules and failure classes), HANDOFF_LAUNCH_READINESS.md (newest handoff, 2026-08-27 to 30), HANDOFF_APP_RESTYLE.md, HANDOFF_POLISH.md, PRD_V3.md (supersedes PRD_V2), ARCHITECTURE_V2.md, DECISIONS_LOG.md, DECISIONS_V2.md, DESIGN_GUIDE.md, the five living logs (ARCHITECTURE_LOG, INFRA_LOG, DECISIONS_LOG, CRITICS_LOG, SKILLS_LOG), PRICING_GUIDE, V1_AUDIT, AUTONOMOUS_BUILD.
- The five living logs, all in `docs/`: `ARCHITECTURE_LOG.md` (architecture changes), `INFRA_LOG.md` (infrastructure and deploy steps), `DECISIONS_LOG.md` (product and build rulings), `CRITICS_LOG.md` (critic passes and lessons), `SKILLS_LOG.md` (skills work).
- Parent folder `C:\Users\jcapa\OneDrive\Personal\Saido Labs LLC\Saibyl\` (outside the repo; context only, don't modify):
  - `05_PRD\saibyl-prd\` (README, specs\, phases\, INFRA_LOG.md: the original PRD), `05_PRD\saibyl-prd-v2\`, `05_PRD\saibyl-prd-v3\`, `05_PRD\Saibyl-V3-Vision.html`
  - `LOOP_STATE.md` (an unfilled template, last updated 2026-06-13)
  - `QA_Report_Saibyl_2026-03-29.md`, `QA_Retest_Report_SAI33_2026-03-29.md`, `SECURITY_AUDIT_SAI29.md`
  - `Saibyl Management\` (pitch decks, monetization playbook, `Saibyl Redesign\` prototypes, LinkedIn, CA GOP); `wiki\` (index, decisions, learnings); Branding, Launch strategy and other non-code folders
- Leave alone: `.env*`; `Saibyl Admin Login.docx` in the parent folder (credential, don't open); `.claude/settings*.json`; `frontend/dist/`; `.venv/`; `node_modules/`; `.claude/worktrees/` (agent worktrees and `v3-prd`).

## Domain rules

### Product and build
- Read `docs/HANDOFF.md` and the PRD before building, because past sessions built against the design and wasted days.
- Grep before you claim, query before you assert. Unverified statements written into docs, comments or migration comments become facts the next session inherits.
- Never run Celery (banned across all projects; use `asyncio.create_task`). Never use Zep Cloud or CAMEL-AI OASIS, and never target the Chinese academic market.
- No personal name on the product, Saido Labs LLC only. No fabricated customers or stats. Never cite a V1 report figure as measured (V1 sentiment was formulaic).
- A migration that adds a constraint goes: merge, deploy, verify live, then constrain.
- The cost model is closed: don't re-tune token profiles (reopen only on `margin_floor_breached`, a changed unit of work, or a prompt edit moving a stage by more than half).
- Production-first: deploy to Render, don't fight local Docker/Windows/OneDrive.
- Batch fixes and trace the full flow (frontend, POST body, API, DB, UI) before pushing. Be surgical with tokens.
- A check that can pass for the wrong reason is worse than no check. Visual claims are verified by reading a rendered screenshot, not by a green build.
- Frontend pitfalls: `VITE_*` vars are build-time only; Supabase JWTs expire after 1h (refresh or redirect on 401, never swallow it); `redirect_slashes=False`, so `/api/x/` and `/api/x` differ; map platform IDs to display names.
- Update whichever of the five living logs a change touches in the same batch (ARCHITECTURE_LOG, INFRA_LOG, DECISIONS_LOG, CRITICS_LOG, SKILLS_LOG). `05_PRD\saibyl-prd\INFRA_LOG.md` is outside the repo; write it anyway.
- Three things that look like bugs and are not (founder decisions, docs/HANDOFF_LAUNCH_READINESS.md §0): the trust card's team-information critical stays open and there is no About page; runs realise 80% margin and modules 96% on purpose; `/app/admin` is absent from navigation and answers 404, so a link to it is the bug.
- Rulings history: `docs/DECISIONS_LOG.md` (V3 era, newest first); `docs/DECISIONS_V2.md` (V2 era, still authoritative for those choices).

### Founder UI rules (enforced by `frontend/src/test/ia.test.ts`)
- Never render these 12 words: ICP, variant, A/B, adversarial, cohort, arena, lens, archetype, canonical, valence, simulation, project (plurals, case-insensitive). A founder has a product and a workspace.
- No `disabled` attributes on the rail: a control either runs and states what its answer will be missing, or is blocked with the button that unblocks it and the reason beside it.
- Every `EmptyState` carries an action (the prop is required). A dead end is a defect.

### Frontend work: read `design/` first
Any UI or frontend work follows the design rules below (the artboards, their vocabulary, motion and page frame).

@docs/DESIGN_RULES.md

## Overrides of global

- Overrides global "Forced verification" (`npx tsc --noEmit`): gate the frontend with `npm run build` (= `tsc -b && vite build`), because Render runs it and project-references mode rejects what `--noEmit` accepts (five `tsc -b` errors once hid behind a clean report while Render served a stale bundle). Backend gate is pytest + ruff. CI (`.github/workflows/test.yml`) now runs the same.
- Overrides global "Phased execution" (wait for approval between phases): run continuously within a phase, stop at phase boundaries (full gate, push, report, wait). `docs/HANDOFF_APP_RESTYLE.md` pre-authorizes autonomous execution, merge to master and deploy for the restyle only.
- Overrides the commit-attribution default: no `Co-Authored-By`, no "Generated with", no robot emoji, no Claude or Anthropic attribution in commits, PRs, code comments or output, ever. Commit with `--author="Saido Labs LLC <info@saidolabs.com>"`; the committer stays the user's own identity.
- Overrides global "Decision log" default (`docs/decisions.md`): rulings live in `docs/DECISIONS_LOG.md`, one of the five living logs (every decision that shapes the product or build: who, what, why; newest first; founder directive 2026-08-16).
- Billing descriptor is `SAIDO LABS LLC`.

## Current state

@.claude/STATE.md
