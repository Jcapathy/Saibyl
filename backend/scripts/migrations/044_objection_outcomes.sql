-- Migration 044: did the predicted objection actually happen?
--
-- APPLIED to production (txmvwuekkiedgxwovorp) 2026-08-28 via the Supabase
-- migration API as `objection_outcomes_close_the_loop`. Recorded here so the
-- repo matches production; re-running it is a no-op.
--
-- ---------------------------------------------------------------------------
-- WHY THIS TABLE IS THE MOST IMPORTANT ONE IN THE SCHEMA
-- ---------------------------------------------------------------------------
-- Two independent evaluations of saibyl.com, run the same day by different
-- methods, made the same finding their most severe: nothing shows that
-- synthetic objections predict real ones. Saibyl's own check calls it a
-- critical — "the team controls both the input and the AI output, so the
-- [evidence proves nothing]" — and an outside review called it "the elephant
-- in the room".
--
-- No copy change closes that. The sentence that closes it is
--
--     "Saibyl predicted this objection; 17 of 24 real prospects raised it."
--
-- and the only way to earn it is to ask founders after launch and count. That
-- is what this table stores: one row per predicted objection per run, holding
-- a human's verdict on whether a real buyer raised it.
--
-- It is also the moat. A competitor can copy "25 AI buyers argue about your
-- pitch" in a weekend. What they cannot copy is a record of which simulated
-- objections turned out to be real across N launches.
--
-- ---------------------------------------------------------------------------
-- THE ONE COLUMN TO GET RIGHT
-- ---------------------------------------------------------------------------
-- `occurred` is nullable, and NULL is a real state: asked, not yet answered.
-- Reading NULL as false would score every unanswered prediction as a miss,
-- which measures our follow-up rate and reports it as prediction quality — a
-- number that falls when somebody ignores an email. `outcomes.py` filters on
-- `IS NOT NULL` before it counts anything, and a test pins that.
--
-- Deliberately thin otherwise. Modelling confidence, partial matches and
-- severity is unfalsifiable dressing on a question that is binary and asked of
-- a human: did a real buyer raise this?

create table if not exists public.objection_outcomes (
    id                uuid primary key default gen_random_uuid(),
    organization_id   uuid not null references public.organizations(id) on delete cascade,
    simulation_id     uuid not null references public.simulations(id) on delete cascade,
    -- Stored by key rather than by `canonical_objections.id` so an outcome
    -- survives a re-analysis of the same run.
    objection_key     text not null,

    occurred          boolean,

    -- Free text on purpose: "two sales calls", "a reply to the launch email".
    -- A taxonomy here would cost more answers than it would buy structure.
    evidence          text,
    observed_count    integer check (observed_count is null or observed_count >= 0),

    asked_at          timestamptz not null default now(),
    answered_at       timestamptz,
    answered_by       uuid references auth.users(id),

    -- One verdict per objection per run. A founder who corrects themselves
    -- updates the row; two contradictory rows make the rate unanswerable.
    unique (simulation_id, objection_key)
);

create index if not exists objection_outcomes_org_idx
    on public.objection_outcomes (organization_id);
create index if not exists objection_outcomes_answered_idx
    on public.objection_outcomes (occurred) where occurred is not null;

alter table public.objection_outcomes enable row level security;

-- The same tenancy rule as every other table here, through the same function.
-- Migration 043's header explains why `user_organization_ids()` keeps its
-- EXECUTE grant: thirty-seven policies including this one call it, and
-- revoking it ends tenant reads everywhere at once.
create policy objection_outcomes_org_isolation on public.objection_outcomes
    for all
    using (organization_id = any (public.user_organization_ids()))
    with check (organization_id = any (public.user_organization_ids()));

comment on table public.objection_outcomes is
    'Did a predicted objection actually occur? One row per objection per run. '
    'occurred IS NULL means asked-but-unanswered and must never be scored as a miss.';
