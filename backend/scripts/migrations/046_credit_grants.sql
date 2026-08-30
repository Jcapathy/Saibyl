-- Migration 046: who granted credits, to whom, and why.
--
-- APPLIED to production (txmvwuekkiedgxwovorp) 2026-08-30 via the Supabase
-- migration API as `credit_grants_audit_trail`, and backfilled with the two
-- grants that predate it. Recorded here so the repo matches production.
--
-- ---------------------------------------------------------------------------
-- WHY IT EXISTS
-- ---------------------------------------------------------------------------
-- There was no record of a comped credit anywhere. `credit_topups` holds real
-- Stripe purchases, and writing a grant there would show as revenue that never
-- arrived — so two grants applied by hand (100,000 to the founder's own org on
-- 2026-08-28, 30,000 to New Vista Journeys on 2026-08-30) existed only as a
-- changed number on `organizations.credits_balance`, with no trace of who did
-- it or why.
--
-- That is fine exactly once. It stops being fine the moment somebody asks why
-- an account holds 33,250 credits and the only available answer is a balance.
-- Both were backfilled into this table when it was created.
--
-- `balance_after` is stored rather than derived because the balance moves for
-- other reasons — runs, top-ups, refunds — and a grant's meaning is what the
-- account held immediately afterwards. Recomputing it later from the current
-- balance would be arithmetic over a moving target.

create table if not exists public.credit_grants (
    id               uuid primary key default gen_random_uuid(),
    organization_id  uuid not null references public.organizations(id) on delete cascade,
    credits          bigint not null check (credits <> 0),
    -- Free text, and required by the API rather than by a constraint: a grant
    -- nobody can explain in three months is what this table exists to prevent.
    reason           text,
    granted_by       uuid references auth.users(id),
    granted_by_email text,
    balance_after    bigint,
    created_at       timestamptz not null default now()
);

create index if not exists credit_grants_org_idx
    on public.credit_grants (organization_id, created_at desc);

alter table public.credit_grants enable row level security;

-- An organisation may read grants made to it — a founder asking "where did
-- these come from" deserves an answer. Only the service role writes, through
-- `POST /api/admin/credits`.
create policy credit_grants_org_read on public.credit_grants
    for select
    using (organization_id = any (public.user_organization_ids()));

comment on table public.credit_grants is
    'Comped credits: who, how many, why. Never write a grant to credit_topups - '
    'that table is real revenue and a grant there overstates it.';
