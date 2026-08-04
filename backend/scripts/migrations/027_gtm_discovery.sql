-- Migration 027: go-to-market candidate discovery
--
-- NOT APPLIED. Highest applied is 025; 026 exists unapplied and is unrelated to
-- this file — neither touches the other's objects, so they may be applied in
-- either order.
--
-- SAFE TO APPLY WHILE master IS DEPLOYED. Everything here is additive: three
-- new tables and one new column on `organizations` with a NOT NULL DEFAULT that
-- reproduces today's behaviour (no contact discovery, because there is no
-- contact discovery today). `master` reads none of it and writes none of it.
--
-- Verified against `information_schema` before writing, per migration 017's
-- lesson that `IF NOT EXISTS` guards hide type drift rather than preventing it:
-- no table named `gtm%` exists, and `organizations` has no column matching
-- `%gtm%`. Every guard below is therefore a formality on a first application
-- rather than a silent no-op over something already there with a different type.
--
--   Part A  gtm_discovery_runs — one discovery. Queries, counts, spend.
--   Part B  gtm_candidates     — a company, with the source that evidenced it.
--   Part C  gtm_contacts       — a named person. Personal data. Gated.
--   Part D  organizations.gtm_contact_discovery_enabled — the gate itself.
--   Part E  RLS, the established org-isolation pattern (018 / 020 / 021).

-- ---------------------------------------------------------------------------
-- Part A: discovery runs
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS gtm_discovery_runs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id          UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    organization_id     UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    -- ON DELETE SET NULL, matching simulations.icp_profile_id: candidates found
    -- from an ICP that was later deleted are still real companies with real
    -- sources, and destroying them because the audience definition was tidied
    -- up would lose the asset this feature exists to build.
    icp_profile_id      UUID REFERENCES icp_profiles(id) ON DELETE SET NULL,

    -- running | completed | partial | failed.
    --
    -- `partial` is a first-class outcome, not a polite failure: the deadline
    -- was reached or some queries errored, and the candidates already found
    -- were written as each query completed. A run that stays `running` with a
    -- NULL completed_at is one whose API process died — there is no worker to
    -- reap it (HANDOFF §8 item 2), and that is the honest state to leave it in
    -- rather than a status that claims knowledge nothing has.
    status              TEXT NOT NULL DEFAULT 'running',

    -- The compiled queries, verbatim. The compiler is deterministic, so storing
    -- them is not redundancy with the ICP: the profile is editable, and a run
    -- has to stay explainable after the founder corrects the archetype that
    -- produced it.
    queries             JSONB NOT NULL DEFAULT '[]'::jsonb,
    query_count         INTEGER NOT NULL DEFAULT 0,
    queries_completed   INTEGER NOT NULL DEFAULT 0,
    queries_failed      INTEGER NOT NULL DEFAULT 0,
    queries_empty       INTEGER NOT NULL DEFAULT 0,

    -- Whether this run was authorised to collect named people. Recorded per run
    -- rather than read from the org at display time: the setting can be turned
    -- off later, and "was this record collected under an opt-in" has to stay
    -- answerable afterwards.
    contacts_enabled    BOOLEAN NOT NULL DEFAULT FALSE,

    candidates_found    INTEGER NOT NULL DEFAULT 0,
    contacts_found      INTEGER NOT NULL DEFAULT 0,

    -- Credits are charged at the start, like a run. Stored so a partial run's
    -- charge against its delivery is visible rather than argued about.
    credits_charged     INTEGER NOT NULL DEFAULT 0,
    estimated_cost_usd  NUMERIC(12, 6) NOT NULL DEFAULT 0,

    -- Web searches actually performed, and what they cost at $10/1,000.
    --
    -- These two columns exist because `llm_usage` cannot hold them.
    -- `record_llm_call` derives cost from token counts through `model_pricing`
    -- and has no parameter for a flat per-search fee, so `reconcile_run_cost`
    -- understates stage `gtm_discovery` by exactly `search_fee_usd`. This is
    -- the only place that spend is recorded, and `gtm_search_fee_unmetered` is
    -- logged once per run with the same figure. See services/gtm/pricing.py.
    searches_performed  INTEGER NOT NULL DEFAULT 0,
    search_fee_usd      NUMERIC(12, 6) NOT NULL DEFAULT 0,

    error               TEXT,

    -- Set when the org purged its candidates. The run survives a purge: it
    -- holds queries, counts and spend — the billing record that reconciles
    -- against llm_usage — and none of that is personal data.
    purged_at           TIMESTAMPTZ,

    created_by          UUID REFERENCES auth.users(id),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at        TIMESTAMPTZ
);

ALTER TABLE gtm_discovery_runs DROP CONSTRAINT IF EXISTS gtm_discovery_runs_status_values;
ALTER TABLE gtm_discovery_runs ADD CONSTRAINT gtm_discovery_runs_status_values
    CHECK (status IN ('running', 'completed', 'partial', 'failed'));

CREATE INDEX IF NOT EXISTS idx_gtm_runs_project
    ON gtm_discovery_runs (project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_gtm_runs_org
    ON gtm_discovery_runs (organization_id, created_at DESC);

-- ---------------------------------------------------------------------------
-- Part B: candidates
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS gtm_candidates (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    discovery_run_id      UUID NOT NULL REFERENCES gtm_discovery_runs(id) ON DELETE CASCADE,
    project_id            UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    organization_id       UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

    company_name          TEXT NOT NULL,

    -- EVERY FIELD BELOW IS NULLABLE ON PURPOSE.
    --
    -- NULL means no retrieved source stated it. It does not mean unknown-and-
    -- probably-small, and nothing may render it as a band, a guess or an
    -- "estimated". A fabricated firmographic is the same defect as Phase 1's
    -- report writing its own numbers, and the founder's whole reason to act on
    -- this list is that the numbers in it came from somewhere. Enforced above
    -- the database too: extraction.verify_candidates blanks any field whose
    -- evidence quote does not appear in the source it cites.
    domain                TEXT,
    one_liner             TEXT NOT NULL DEFAULT '',
    employee_count_range  TEXT,
    industry              TEXT,
    hq_location           TEXT,
    incumbent_tooling     TEXT[] NOT NULL DEFAULT '{}',

    -- Which archetype matched this company, and why. NOT NULL because a
    -- candidate a founder cannot trace back to an archetype is a lead they
    -- cannot act on — there is no valid row without it.
    archetype_id          TEXT NOT NULL,
    archetype_label       TEXT NOT NULL DEFAULT '',
    angle                 TEXT NOT NULL,
    query                 TEXT NOT NULL DEFAULT '',
    match_reasons         JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- A rank ordering against the archetype, 0..1. NOT a probability, and
    -- nothing may render it as one. `score_components` carries the five parts
    -- so the founder reads the arithmetic instead of a bare number, and so the
    -- weights can be re-derived from qualification feedback when there is any.
    match_score           REAL NOT NULL DEFAULT 0,
    score_components      JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- Provenance. NOT NULL on both, for the same reason as on gtm_contacts:
    -- a claim whose source and retrieval time are unknown cannot be defended,
    -- corrected, or removed on request.
    source_url            TEXT NOT NULL,
    source_title          TEXT NOT NULL DEFAULT '',
    retrieved_at          TIMESTAMPTZ NOT NULL,
    -- [{field, source_url, quote}] — every quote verified to appear in the
    -- source's text before this row was written.
    evidence              JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- Denormalised so a list view never has to read the contacts table. That
    -- keeps personal data out of the query that renders a 200-row grid.
    contact_count         INTEGER NOT NULL DEFAULT 0,

    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE gtm_candidates DROP CONSTRAINT IF EXISTS gtm_candidates_angle_values;
ALTER TABLE gtm_candidates ADD CONSTRAINT gtm_candidates_angle_values
    CHECK (angle IN ('firmographic', 'incumbent_tooling', 'pain_trigger'));

ALTER TABLE gtm_candidates DROP CONSTRAINT IF EXISTS gtm_candidates_score_range;
ALTER TABLE gtm_candidates ADD CONSTRAINT gtm_candidates_score_range
    CHECK (match_score >= 0 AND match_score <= 1);

CREATE INDEX IF NOT EXISTS idx_gtm_candidates_project
    ON gtm_candidates (project_id, match_score DESC);
CREATE INDEX IF NOT EXISTS idx_gtm_candidates_org
    ON gtm_candidates (organization_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_gtm_candidates_run
    ON gtm_candidates (discovery_run_id);
CREATE INDEX IF NOT EXISTS idx_gtm_candidates_archetype
    ON gtm_candidates (project_id, archetype_id);

-- ---------------------------------------------------------------------------
-- Part C: contacts — personal data, and the schema says so
-- ---------------------------------------------------------------------------
--
-- Storing a name with a job title and an employer makes Saibyl a controller of
-- personal data rather than a tool its customer points at a market. The
-- obligations that follow are answerable only if provenance is in the row, so
-- `source_url` and `retrieved_at` are NOT NULL and there is deliberately no
-- `deleted_at`: erasure is a DELETE. See services/gtm/privacy.py for the whole
-- argument, and read it before adding a column here.
--
-- What may be stored: name, role, employer, public professional profile URL.
-- What may not: personal email, phone, postal address, and anything inferred
-- or sensitive. There is no column for any of those and adding one is a
-- privacy decision, not a schema decision.

CREATE TABLE IF NOT EXISTS gtm_contacts (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id        UUID NOT NULL REFERENCES gtm_candidates(id) ON DELETE CASCADE,
    organization_id     UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

    full_name           TEXT NOT NULL,
    role_title          TEXT NOT NULL DEFAULT '',
    employer            TEXT NOT NULL DEFAULT '',
    public_profile_url  TEXT,

    source_url          TEXT NOT NULL,
    retrieved_at        TIMESTAMPTZ NOT NULL,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_gtm_contacts_candidate
    ON gtm_contacts (candidate_id);
CREATE INDEX IF NOT EXISTS idx_gtm_contacts_org
    ON gtm_contacts (organization_id, created_at DESC);

-- ---------------------------------------------------------------------------
-- Part D: the gate
-- ---------------------------------------------------------------------------
--
-- NOT NULL DEFAULT FALSE, so there is no "unset" state a reader could resolve
-- either way. Off is the working default and not a degraded mode: company
-- discovery is complete with this false, and turning it on adds contacts to
-- the same candidates rather than unlocking a fuller product. If contacts-off
-- were degraded, someone would eventually turn it on for everyone.

ALTER TABLE organizations
    ADD COLUMN IF NOT EXISTS gtm_contact_discovery_enabled BOOLEAN NOT NULL DEFAULT FALSE;

-- ---------------------------------------------------------------------------
-- Part E: RLS — the established org-isolation pattern
-- ---------------------------------------------------------------------------

ALTER TABLE gtm_discovery_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE gtm_candidates     ENABLE ROW LEVEL SECURITY;
ALTER TABLE gtm_contacts       ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS gtm_discovery_runs_org_isolation ON gtm_discovery_runs;
CREATE POLICY gtm_discovery_runs_org_isolation ON gtm_discovery_runs
    FOR ALL USING (organization_id = ANY(public.user_organization_ids()));

DROP POLICY IF EXISTS gtm_candidates_org_isolation ON gtm_candidates;
CREATE POLICY gtm_candidates_org_isolation ON gtm_candidates
    FOR ALL USING (organization_id = ANY(public.user_organization_ids()));

DROP POLICY IF EXISTS gtm_contacts_org_isolation ON gtm_contacts;
CREATE POLICY gtm_contacts_org_isolation ON gtm_contacts
    FOR ALL USING (organization_id = ANY(public.user_organization_ids()));
