-- 034: IP clearance — runs and findings (PRD_V3 §11).
--
-- Additive only: two new tables, their indexes, and RLS. No existing table,
-- row, or constraint changes.
--
-- SAFE to apply before the deploy that writes it, and REQUIRED to be: the
-- clearance API inserts into these tables the moment it ships, so the order is
-- this migration first, then the code.
--
-- Why this exists
-- ---------------
-- PRD_V3 §11: a founder submits a name, an invention description, or both, and
-- gets a tiered USPTO clearance report — trademarks, granted-patent and
-- published-application prior art, and the pending landscape. A run is the
-- charged unit and carries the versioned JSON artifact plus the rendered
-- report; findings are the per-reference rows behind it (one trademark hit,
-- one piece of prior art, one pending application each), stored flat so
-- drill-down and any later watch-list can query them without parsing the blob
-- — the same split 018 made between simulation_analysis and
-- canonical_objections, for the same reason.

CREATE TABLE IF NOT EXISTS clearance_runs (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id  UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    project_id       UUID REFERENCES projects(id) ON DELETE SET NULL,

    -- What the founder asked about, verbatim.
    item             TEXT NOT NULL,
    -- 'name' | 'invention' | 'both' when the founder said which. NULL means
    -- the planner classifies it itself (the skill's Stage 0).
    type_hint        TEXT,
    field            TEXT,
    competitors      JSONB NOT NULL DEFAULT '[]'::jsonb,

    tier             TEXT NOT NULL
                     CHECK (tier IN ('QUICK', 'STANDARD', 'COMPREHENSIVE')),
    status           TEXT NOT NULL DEFAULT 'queued'
                     CHECK (status IN ('queued', 'running', 'complete', 'failed')),

    -- The versioned JSON artifact (the skill's output contract) and the
    -- rendered report, on the run row — as simulation_analysis carries its
    -- artifact.
    artifact         JSONB,
    report_markdown  TEXT,

    credits_charged  BIGINT NOT NULL DEFAULT 0,
    error_message    TEXT,
    -- The date the registers were searched, stamped at creation. Every finding
    -- is a statement about the USPTO as of this date — empty ≠ cleared, and a
    -- clearance answer without its date is a claim with no expiry.
    search_date      DATE,

    created_at       TIMESTAMPTZ DEFAULT NOW(),
    completed_at     TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS clearance_findings (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id              UUID NOT NULL REFERENCES clearance_runs(id) ON DELETE CASCADE,
    organization_id     UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

    kind                TEXT NOT NULL
                        CHECK (kind IN ('trademark', 'patent', 'pending', 'examiner')),
    -- Registration / serial / application / patent number, exactly as the
    -- USPTO returned it. Never fabricated — the skill's non-negotiable rule; a
    -- reference the API did not return is not written.
    reference_number    TEXT,
    title               TEXT,
    owner               TEXT,
    dates               JSONB NOT NULL DEFAULT '{}'::jsonb,
    status              TEXT,
    risk                TEXT CHECK (risk IS NULL OR risk IN ('GREEN', 'YELLOW', 'RED')),
    claim_requirements  TEXT,
    differences         TEXT,
    -- The response the row was distilled from, kept whole so a disputed
    -- finding can be reconstructed after the fact.
    raw                 JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_clearance_runs_org
    ON clearance_runs (organization_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_clearance_findings_run
    ON clearance_findings (run_id);

-- ---------------------------------------------------------------------------
-- RLS — the established org-isolation pattern
-- ---------------------------------------------------------------------------

ALTER TABLE clearance_runs     ENABLE ROW LEVEL SECURITY;
ALTER TABLE clearance_findings ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS clearance_runs_org_isolation ON clearance_runs;
CREATE POLICY clearance_runs_org_isolation ON clearance_runs
    FOR ALL USING (organization_id = ANY(public.user_organization_ids()));

DROP POLICY IF EXISTS clearance_findings_org_isolation ON clearance_findings;
CREATE POLICY clearance_findings_org_isolation ON clearance_findings
    FOR ALL USING (organization_id = ANY(public.user_organization_ids()));
