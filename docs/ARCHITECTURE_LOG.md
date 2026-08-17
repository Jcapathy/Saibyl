# Architecture Log

Standing rule (founder directive, 2026-08-16): whenever the system's shape
changes — a new package, a new pipeline, a moved boundary, a new external
dependency — the change lands here, dated, with the why. Newest entries at the
top. `ARCHITECTURE_V2.md` remains the deep design document; this is the
running delta record.

---

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
