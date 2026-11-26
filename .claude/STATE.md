# State

Last updated: 2026-08-31 by CLAUDE.md migration session (read-only look at the `v3-prd` worktree)
Rewrite this file after every phase so it describes the state now, not a history.

## Goal
Launch readiness: Saibyl took its first real payment on 2026-08-28 and is growing the surfaces a founder needs after paying (website check, work index, admin console, follow-up loop).

## Done
- Payments live: first real charge 2026-08-28 ($10 for 2,000 credits, webhook verified). Evidence: docs/HANDOFF_LAUNCH_READINESS.md §1.
- Password recovery live and exercised on a real account (2026-08-30). Same source.
- LLM is Opus 5 at `LLM_EFFORT=medium`; the fast path stays Haiku 4.5. Same source.
- `taste.py` census fixes: anthropic.com 55 to 100, news.ycombinator.com 22 to 0, no weight changed. Evidence: commit `49763d5`.
- Rewrite draws its own graphics and credits motion; the check can see motion. Evidence: `f13ef1a`, `073d965`, `ecd4db7` (all on `origin/master`, the base of this worktree).
- Migrations through 046 are in the repo (043 to 046 applied this phase per the handoff).

## In progress
- Branch `v3-prd` is 2 commits ahead of `origin/master`, not yet merged: `8dfd534` (the open check links to its own report) and `59d9178` (a website check asks whose site it is, own / competitor / other, instead of assuming it is yours). Where it stands: the working tree was clean when last looked at; merge and deploy status is `<unknown: ask me>`.

## Next
1. Create the `saibyl-followups` cron service in Render by hand (not via Blueprint), set its env vars (a cron inherits nothing), and verify saibyl.com in Resend. Until it runs, `objection_outcomes` stays empty and the credibility critical stays open. Source: HANDOFF_LAUNCH_READINESS §2.1; check with `python -m scripts.send_followups --dry-run`.
2. Decide cross-organisation grounding (`GroundingScope.SHARED`, written and off); `/privacy` must say so first (§2.2).
3. If extending `taste.py`, the open question is coverage, not weights (§2.3).

## Open questions (need a decision from me)
- Is `v3-prd` still the working branch, and should `8dfd534` and `59d9178` merge to `master` now? Options: ff-merge and deploy / hold. `<unknown: ask me>`
- Delete the duplicate owner `admin@saidolabs.com` (not a real mailbox)? Optional tidy-up per the handoff.
- Is the "Phased execution" override in CLAUDE.md (autonomous within a phase) still wanted beyond the restyle? It came from an older draft and the restyle pre-authorization it cites is dated 2026-08-17.

## Verify
```
cd backend && uv run pytest -q && uv run ruff check app tests scripts
cd frontend && npm run build && npx eslint src --quiet && npx vitest run
```
Last recorded counts: 2,112 backend, 143 frontend (2026-08-30). Not re-run for this migration.

## Parking list (off the current goal; not acted on)
- Test accounts hold real credits: 189,495 of 523,227 outstanding sit in Saido Labs alone, which distorts the console's "credits outstanding".
- Supabase advisors went 19 to 4; the 4 left are documented decisions.
- `.omc/` and `.claude/launch.json` were not looked at.
