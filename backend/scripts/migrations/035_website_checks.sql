-- 035: Website checks — snapshots, plus documents that can carry a page (PRD_V3 §4a–c).
--
-- Additive only: one new table with its indexes and RLS, and one CHECK
-- constraint widened. No rows change, no existing columns are added, nothing
-- is backfilled.
--
-- SAFE to apply before the deploy that writes it, and REQUIRED to be: the
-- website API inserts into website_snapshots the moment it ships, and its
-- worker stores a document with material_kind = 'website_url' — so the order
-- is this migration first, then the code.
--
-- Why this exists
-- ---------------
-- PRD_V3 §4: a founder submits their live page's URL. The pipeline captures
-- the rendered page (full-page screenshots at desktop and mobile widths,
-- extracted DOM text, meta tags), a panel of five vision critics judges it,
-- and the page's own text is stored as a document so the audience reacts to
-- the page itself alongside the founder's uploaded material. A snapshot is
-- the charged unit and it is immutable: re-checking a site creates a new
-- snapshot, and a report always names the snapshot it judged.

CREATE TABLE IF NOT EXISTS website_snapshots (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    project_id               UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,

    -- The address the founder submitted, verbatim, and where the fetch
    -- actually landed after redirects — a check that judged the redirect
    -- target must be able to say so.
    url                      TEXT NOT NULL,
    final_url                TEXT,
    title                    TEXT,

    status                   TEXT NOT NULL DEFAULT 'queued'
                             CHECK (status IN ('queued', 'capturing', 'judging',
                                               'complete', 'failed')),

    -- Storage refs for the rendered page at the two widths the critics judge.
    screenshot_desktop_path  TEXT,
    screenshot_mobile_path   TEXT,

    -- The critic panel's verdict, whole: overall score, the page takeaway,
    -- per-dimension scores with findings and strengths.
    critique                 JSONB,
    -- The documents row the page's text was stored as (material_kind
    -- 'website_url'). Deliberately not a foreign key: the founder can delete
    -- that document like any other, and the snapshot's history should not
    -- block or be broken by it.
    document_id              UUID,
    dom_chars                INT,

    credits_charged          BIGINT NOT NULL DEFAULT 0,
    error_message            TEXT,
    created_at               TIMESTAMPTZ DEFAULT NOW(),
    completed_at             TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_website_snapshots_org
    ON website_snapshots (organization_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_website_snapshots_project
    ON website_snapshots (project_id);

-- ---------------------------------------------------------------------------
-- RLS — the established org-isolation pattern
-- ---------------------------------------------------------------------------

ALTER TABLE website_snapshots ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS website_snapshots_org_isolation ON website_snapshots;
CREATE POLICY website_snapshots_org_isolation ON website_snapshots
    FOR ALL USING (organization_id = ANY(public.user_organization_ids()));

-- ---------------------------------------------------------------------------
-- documents.material_kind gains 'website_url' and 'website_html'
-- ---------------------------------------------------------------------------
-- 020 defined this constraint over ('own', 'competitor', 'market'); 033
-- widened it for 'idea_brief'. Recreated here under the same name, with the
-- same NULL allowance, plus the two website kinds: text fetched from the
-- founder's live page, and a raw HTML file they uploaded. Like 'idea_brief',
-- both record provenance — how the material arrived, not what it is — and
-- downstream they read as the founder's own subject material.

ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_material_kind_values;
ALTER TABLE documents ADD CONSTRAINT documents_material_kind_values
    CHECK (material_kind IS NULL
           OR material_kind IN ('own', 'competitor', 'market', 'idea_brief',
                                'website_url', 'website_html'));

-- `documents_material_kind_suggested_values` (026) is left untouched, on
-- purpose — 033's reasoning holds unchanged. The classifier proposes kinds for
-- *uploaded* files and must never emit 'website_url' or 'website_html': those
-- kinds are written only by the website pipeline, and a suggestion carrying
-- one would be a claim about provenance no classifier can make. The narrower
-- constraint is what enforces that.
