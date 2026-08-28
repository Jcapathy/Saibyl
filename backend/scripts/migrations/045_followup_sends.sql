-- Migration 045: what we have already asked, so a daily cron cannot nag.
--
-- APPLIED to production (txmvwuekkiedgxwovorp) 2026-08-28 via the Supabase
-- migration API as `followup_sends_idempotency`. Recorded here so the repo
-- matches production; re-running it is a no-op.
--
-- ---------------------------------------------------------------------------
-- WHY THE UNIQUE CONSTRAINT IS THE POINT
-- ---------------------------------------------------------------------------
-- The follow-up job (`services/engine/followup.py`) runs from a cron that fires
-- EVERY DAY, and a run stays inside its due window for a week or two. Without a
-- record of what was sent, every one of those days is "due", and a founder gets
-- the same email every morning until they stop reading anything we send.
--
-- The constraint is on (simulation_id, stage) rather than on anything
-- time-based so that a retry, a clock change, a mid-run redeploy, or two
-- overlapping cron instances all collapse to a single send.
--
-- ---------------------------------------------------------------------------
-- CLAIMED BEFORE SENDING, ON PURPOSE
-- ---------------------------------------------------------------------------
-- The row is written BEFORE the email is attempted. A crash in between then
-- costs one missing email, which a human can send by hand. The other ordering —
-- send, then record — costs the founder that same email every morning until
-- somebody notices, and nobody notices email that works.
--
-- `test_the_claim_is_written_before_the_send` pins this by killing the mail
-- service mid-send and asserting the claim survives.

create table if not exists public.followup_sends (
    id               uuid primary key default gen_random_uuid(),
    organization_id  uuid not null references public.organizations(id) on delete cascade,
    simulation_id    uuid not null references public.simulations(id) on delete cascade,
    stage            text not null check (stage in ('two_week', 'four_week')),

    claimed_at       timestamptz not null default now(),
    sent_at          timestamptz,
    -- Kept so a bounce can be traced without joining back to auth.users, and so
    -- we can still see who was asked if the account is later deleted.
    sent_to          text,
    -- Null while pending; a readable sentence when the send failed. The most
    -- likely value in the first weeks is Resend's "domain is not verified".
    error            text,

    unique (simulation_id, stage)
);

create index if not exists followup_sends_org_idx
    on public.followup_sends (organization_id);

alter table public.followup_sends enable row level security;

create policy followup_sends_org_isolation on public.followup_sends
    for all
    using (organization_id = any (public.user_organization_ids()))
    with check (organization_id = any (public.user_organization_ids()));

comment on table public.followup_sends is
    'One row per (run, stage) follow-up ask. The unique constraint is the '
    'idempotency guard for a daily cron; claimed before sending on purpose.';
