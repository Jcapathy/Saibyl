-- 036: Design gallery — every check leaves a design record behind (PRD_V3 §4).
--
-- Additive only: two nullable columns on website_snapshots, one new table with
-- its indexes and RLS. No rows change, no constraints tighten, nothing is
-- backfilled.
--
-- SAFE to apply before the deploy that writes it, and REQUIRED to be: the
-- website worker inserts into design_gallery and writes the two new columns
-- the moment it ships, so the order is this migration first, then the code.
--
-- Why this exists
-- ---------------
-- PRD_V3 §4: alongside the critique a founder pays for, every website check
-- now also distils what the page's design *is* — a one-line characterization,
-- extracted design tokens, a maturity reading, the full design.md — plus the
-- mechanical style census the capture counted. That distillate outlives the
-- check: the gallery is the substrate for the future before/after showcase
-- (flagged, not built), and it only becomes one if every check contributes a
-- row from day one. The check row stays the founder's deliverable; the gallery
-- row is the platform's byproduct, which is why the worker treats its failure
-- as a log line, never as a failed check.
--
-- A founder may also name a site they admire; the check captures it too so the
-- critics can judge against it. The snapshot records that address and where
-- its screenshot landed — the reference is part of what was judged, and a
-- verdict that can't show what it compared against is a claim, not evidence.

ALTER TABLE website_snapshots
    ADD COLUMN IF NOT EXISTS reference_url TEXT;
ALTER TABLE website_snapshots
    ADD COLUMN IF NOT EXISTS reference_screenshot_path TEXT;

CREATE TABLE IF NOT EXISTS design_gallery (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    project_id               UUID REFERENCES projects(id) ON DELETE SET NULL,
    -- The check this row was distilled from. Cascades with it: a snapshot that
    -- is gone can no longer vouch for the distillate.
    snapshot_id              UUID REFERENCES website_snapshots(id) ON DELETE CASCADE,

    -- The page the design description is *about* — where the fetch landed.
    url                      TEXT NOT NULL,

    -- The design DNA: what the design is, in one line and in full.
    characterization         TEXT,
    summary                  TEXT,
    style_tags               JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- 1–7 on the design-maturity ladder, with the reading's reasoning kept
    -- beside it — a number without its rationale is a score nobody can audit.
    maturity_level           INT CHECK (maturity_level BETWEEN 1 AND 7),
    maturity_rationale       TEXT,
    tokens                   JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- The capture's mechanical style census, verbatim — measured, not judged.
    census                   JSONB NOT NULL DEFAULT '{}'::jsonb,
    design_md                TEXT,

    -- Lifted from the critique so the feed can rank without opening it.
    overall_score            INT,
    -- The snapshot's stored screenshots, denormalized: the gallery must be
    -- browsable as images even when the reader never joins back to the check.
    screenshot_desktop_path  TEXT,
    screenshot_mobile_path   TEXT,
    reference_url            TEXT,

    created_at               TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_design_gallery_org
    ON design_gallery (organization_id, created_at DESC);
-- The platform-admin feed reads newest-first across every organization.
CREATE INDEX IF NOT EXISTS idx_design_gallery_created
    ON design_gallery (created_at DESC);

-- ---------------------------------------------------------------------------
-- RLS — the established org-isolation pattern
-- ---------------------------------------------------------------------------

ALTER TABLE design_gallery ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS design_gallery_org_isolation ON design_gallery;
CREATE POLICY design_gallery_org_isolation ON design_gallery
    FOR ALL USING (organization_id = ANY(public.user_organization_ids()));
