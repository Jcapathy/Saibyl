-- 037: Page revisions — the revised page and its proof (PRD_V3 §4d).
--
-- Additive only: one new table with its indexes and RLS. No rows change, no
-- existing columns move, nothing is backfilled.
--
-- SAFE to apply before the deploy that writes it, and REQUIRED to be: the
-- revision API inserts into page_revisions the moment it ships, and its worker
-- updates the row through the whole generate-and-judge loop — so the order is
-- this migration first, then the code.
--
-- Why this exists
-- ---------------
-- PRD_V3 §4d: a founder whose page survived the critic gauntlet asks for the
-- fixed version. The pipeline regenerates the page's HTML through revise →
-- re-judge rounds until it clears the bar or runs out of rounds, and this row
-- is what that loop leaves behind: the scores it started from, the scores it
-- ended on, the winning round's critique, the paste-ready fix prompts, and
-- storage refs for the new page and its rendered screenshots.
--
-- A revision is also the before/after substrate for the flagged-not-built
-- showcase (PRD_V3 §4b²): the original's screenshots live on the snapshot it
-- points at, the after lives here, and the pair reads as one exhibit without
-- either side copying the other's images.

CREATE TABLE IF NOT EXISTS page_revisions (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    project_id               UUID REFERENCES projects(id) ON DELETE SET NULL,
    -- The check this revision fixes. Cascades with it: a revision whose
    -- "before" is gone can no longer prove anything.
    snapshot_id              UUID NOT NULL REFERENCES website_snapshots(id) ON DELETE CASCADE,

    status                   TEXT NOT NULL DEFAULT 'queued'
                             CHECK (status IN ('queued', 'generating', 'judging',
                                               'complete', 'failed')),

    -- How many revise-and-judge rounds ran, and which one the stored page
    -- came from — the loop keeps the best round, not necessarily the last.
    rounds                   INT NOT NULL DEFAULT 0,
    best_round               INT,

    -- Overall + per-dimension, before from the snapshot's stored critique and
    -- after from the winning round's re-judge — the measured delta the
    -- before/after presentation renders.
    scores_before            JSONB NOT NULL DEFAULT '{}'::jsonb,
    scores_after             JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- The critics' verdict on the winning round, whole: what still stands
    -- after the fix is part of the proof, not a footnote.
    critique_after           JSONB,
    -- Paste-ready prompt blocks for the founder's coding tool (PRD_V3 §4d) —
    -- a first-class deliverable, not an appendix.
    fix_prompts              JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- Storage refs: the revised page itself, and its rendered screenshots at
    -- the same two widths the critics judged the original at.
    html_path                TEXT,
    screenshot_desktop_path  TEXT,
    screenshot_mobile_path   TEXT,

    credits_charged          BIGINT NOT NULL DEFAULT 0,
    error_message            TEXT,
    created_at               TIMESTAMPTZ DEFAULT NOW(),
    completed_at             TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_page_revisions_org
    ON page_revisions (organization_id, created_at DESC);
-- The check's own reads, and the admin feed's latest-per-check join.
CREATE INDEX IF NOT EXISTS idx_page_revisions_snapshot
    ON page_revisions (snapshot_id);

-- ---------------------------------------------------------------------------
-- RLS — the established org-isolation pattern
-- ---------------------------------------------------------------------------

ALTER TABLE page_revisions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS page_revisions_org_isolation ON page_revisions;
CREATE POLICY page_revisions_org_isolation ON page_revisions
    FOR ALL USING (organization_id = ANY(public.user_organization_ids()));
