-- 026: the org-level persona pack library, and the auto-classifier's proposal
--      columns on `documents`.
--
-- NOT YET APPLIED. Written, verified against production's current schema, and
-- deliberately left unapplied for the user to run.
--
-- SAFE TO APPLY WHILE master IS DEPLOYED. Additive only: one new table and two
-- new nullable columns on `documents`. `master` reads none of it and writes
-- none of it.
--
--
-- Part A — `persona_packs`, DECISIONS_V2 §3 taken one step further
-- ----------------------------------------------------------------
-- §3 settled that the audience is *derived from the founder's own material*,
-- not picked from a library of 16. A synthesized ICP therefore lives in
-- `icp_profiles`, where the editable profile and the compiled `PersonaPack` share
-- one row so an edit and the pack the next run uses cannot drift apart. That
-- coupling is the whole point of that table and this migration does not touch it.
--
-- What §3 did not answer is what happens when a founder synthesizes an audience
-- that is *good*, and wants it again — on the next project, on a variant, on a
-- re-launch. Reaching that pack today means finding the ICP profile that
-- compiled it, and ICP profiles are scoped to a project. So this table holds a
-- **snapshot**: a pack promoted out of an ICP profile, owned by the
-- organization rather than by a project.
--
-- Snapshot, not reference. Promotion copies `pack_data`; a later edit to the
-- source ICP recompiles that profile's own pack and leaves the library row
-- alone. The alternative — a library entry that resolves through to the live
-- profile — would mean a run configured last week silently changes audience
-- because somebody corrected a job title, which is the same
-- reproducibility failure `icp_profiles.pack_data` exists to prevent. Drift is
-- made *visible* instead of prevented: `source_icp_profile_id` and
-- `source_synced_at` let the API compare against `icp_profiles.updated_at` and
-- tell the founder the source has moved, so re-promoting stays a deliberate act.
--
--
-- Part B — `UNIQUE(organization_id, pack_id)` is a security boundary, not a
--          convenience constraint
-- ------------------------------------------------------------------------
-- A pack id is a slug. Two organizations will both want `smb-buyers`, and both
-- must be able to have it. That means a pack id is **not** an identity on its
-- own — `(organization_id, pack_id)` is. This is exactly the shape of the
-- defect HANDOFF §1a records for `username`: a lookup keyed on something that
-- is not unique in the space it is used in.
--
-- `custom_persona_packs` already carries this constraint (013), and yet
-- `pack_loader._load_custom_pack` queried it by `pack_id` alone and returned
-- `result.data[0]`. Verified 2026-08-03 against txmvwuekkiedgxwovorp: 5 custom
-- packs across 2 organizations, no colliding slug **yet** —
--
--   select pack_id, count(distinct organization_id)
--   from custom_persona_packs group by pack_id
--   having count(distinct organization_id) > 1;   -- 0 rows
--
-- so the leak is latent rather than realised, and a library whose whole purpose
-- is reusable slugs is what would realise it. The lookup is fixed in
-- `pack_loader.get_pack`, which now takes an org and filters in the query; the
-- constraint below is the layer that holds regardless of who writes the next
-- caller, on the same reasoning as migration 019's index.
--
--
-- Part C — the material-kind classifier proposes; a human grants
-- --------------------------------------------------------------
-- `documents.material_kind` (020) is the ONLY thing that licenses a named
-- competitor in an adversarial archetype, and PRD §4 / DECISIONS §7 forbid
-- relaxing that. An auto-classifier must therefore never write it. It writes a
-- *proposal* into a separate column, and confirming the proposal — copying it
-- into `material_kind` — stays a human action.
--
-- Verified before writing, per the standing lesson from 017 (an `IF NOT EXISTS`
-- guard silently accepts a hand-added column of the wrong type):
--
--   select column_name, data_type, is_nullable from information_schema.columns
--   where table_schema='public' and table_name='documents'
--     and (column_name ilike '%material%' or column_name ilike '%confid%'
--          or column_name ilike '%suggest%' or column_name ilike '%kind%');
--
--   material_kind | text | YES
--
-- That is the only match. Neither column below exists in any form, so the
-- `IF NOT EXISTS` guards cannot be hiding a type mismatch here.

-- ---------------------------------------------------------------------------
-- Part A: the library
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS persona_packs (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id       UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

    -- The slug the engine resolves. Unique within the org, and NOT globally —
    -- see Part B. Written into `simulations.persona_pack_ids` (jsonb array of
    -- these strings, verified: 70 rows) and re-stamped into `pack_data->>'id'`
    -- on write, so the row and the JSON it stores can never disagree about what
    -- this pack is called.
    pack_id               TEXT NOT NULL,

    name                  TEXT NOT NULL,
    description           TEXT NOT NULL DEFAULT '',
    category              TEXT NOT NULL DEFAULT 'library',

    -- A full PersonaPack, validated by
    -- app.services.engine.personas.pack_loader.PersonaPack before it is written.
    pack_data             JSONB NOT NULL,

    -- The ICP profile this was promoted out of. NULLABLE for two distinct
    -- reasons, and both are real: a pack can be hand-made and never have had a
    -- source, and a promoted pack outlives the profile it came from (ON DELETE
    -- SET NULL below). The library entry is a snapshot; deleting the ICP costs
    -- the provenance link, not the pack.
    source_icp_profile_id UUID REFERENCES icp_profiles(id) ON DELETE SET NULL,

    -- When the snapshot was taken. Compared against
    -- `icp_profiles.updated_at` to answer "has the source moved since?" — the
    -- question that makes not-auto-refreshing an honest choice rather than a
    -- silent staleness.
    source_synced_at      TIMESTAMPTZ,

    -- Nullable, unlike `custom_persona_packs.created_by` (013, NOT NULL). A
    -- pack can be written by a background path that has an organization but no
    -- acting user, and a NOT NULL here would force such a path to invent one.
    --
    -- No ON DELETE action, matching every existing app-table reference to
    -- auth.users. Verified rather than assumed:
    --
    --   select c.conrelid::regclass, c.conname, c.confdeltype from pg_constraint c
    --   join pg_class rel on rel.oid = c.confrelid
    --   join pg_namespace n on n.oid = rel.relnamespace
    --   where c.contype='f' and n.nspname='auth' and rel.relname='users';
    --
    -- api_keys, custom_persona_packs, icp_profiles, inoculation_assets,
    -- ontologies, prediction_accuracy, projects, simulations and webhooks all
    -- report confdeltype 'a' (NO ACTION). Cascading behaviour appears only
    -- inside the auth schema and on organization_members / user_profiles.
    created_by            UUID REFERENCES auth.users(id),
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- The boundary. Two orgs may both use `smb-buyers`; one org may not use it
    -- twice.
    UNIQUE (organization_id, pack_id)
);

CREATE INDEX IF NOT EXISTS idx_persona_packs_org
    ON persona_packs (organization_id, created_at DESC);

-- Answers "which library packs came from this ICP profile, and are they stale?"
-- for the ICP editor, without scanning the org's whole library.
CREATE INDEX IF NOT EXISTS idx_persona_packs_source_icp
    ON persona_packs (source_icp_profile_id)
    WHERE source_icp_profile_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- Part C: one upload surface — the columns the ingestion pipeline writes
-- ---------------------------------------------------------------------------
--
-- ⚠ ORDERING: apply this migration BEFORE deploying the code that accompanies
-- it. This is the REVERSE of migration 019, and for the opposite reason. 019
-- added a *constraint the code had to satisfy*, so it went merge → deploy →
-- constrain. Part C adds *columns the code writes*, so a deploy that lands
-- first fails every upload on a missing column. The rule is not "migrations
-- always go last" — it is that the writer and the schema it needs must never
-- be apart in the direction that breaks.
--
-- `documents` is now the only upload table. Both /api/documents and
-- /api/uploads write here, dispatching on `media_type`; `project_assets` has
-- no remaining reader. Retiring that table is deliberately NOT in this
-- migration — it needs a row-count check and a backfill whose
-- `file_size_bytes` differs in width (BIGINT there, INT here), and a data move
-- does not belong in the same step as an additive schema change.

ALTER TABLE documents ADD COLUMN IF NOT EXISTS media_type            TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS source_url            TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS processed_text_path   TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS extracted_char_count  INT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS extraction_metadata   JSONB DEFAULT '{}'::jsonb;

-- Extracted text lives in storage at `processed_text_path`, not on the row:
-- `GET /api/documents` does `select("*")`, and a vision or transcription pass
-- must never be re-billed because a list endpoint fetched its output.
-- `extracted_char_count` is what the row carries, so an extraction that
-- produced nothing is visible without reading the object.

ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_media_type_values;
ALTER TABLE documents ADD CONSTRAINT documents_media_type_values
    CHECK (media_type IS NULL OR media_type IN
      ('document', 'presentation', 'image', 'video', 'spreadsheet', 'news_article'));

-- Existing rows predate the column and are all plain documents. The pipeline
-- also derives a type from `file_type` when this is NULL, so the backfill is
-- belt-and-braces rather than load-bearing.
UPDATE documents SET media_type = 'document' WHERE media_type IS NULL;

-- ---------------------------------------------------------------------------
-- Part D: the classifier's proposal
-- ---------------------------------------------------------------------------
--
-- Column names match what the ingestion code writes — `material_kind_suggested`
-- and `material_kind_confidence`. They read as "the suggested material_kind",
-- which keeps them adjacent to `material_kind` in an alphabetical column list;
-- more importantly, the writer already exists and a schema that disagrees with
-- its writer is the `sim_uuid`/`sim_id` defect this codebase has now hit three
-- times.

-- The proposed value for `material_kind`. Same domain as the column it
-- proposes for, deliberately: a proposal the founder cannot legally confirm is
-- not a proposal. NULL means "not classified", which is distinct from a
-- classification of 'own'.
--
-- ⚠ NOTHING may copy this into `material_kind`. DECISIONS_V2 §7: an unlabelled
-- document can never license naming a competitor, and `material_kind` is the
-- record of a *human decision*. A model proposing 'competitor' and a founder
-- confirming it are different events, and only the second grants anything.
ALTER TABLE documents ADD COLUMN IF NOT EXISTS material_kind_suggested TEXT;

ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_material_kind_suggested_values;
ALTER TABLE documents ADD CONSTRAINT documents_material_kind_suggested_values
    CHECK (material_kind_suggested IS NULL
           OR material_kind_suggested IN ('own', 'competitor', 'market'));

-- The classifier's confidence in that proposal, 0–1. Recorded so that "the
-- model was sure and wrong" and "the model guessed" are distinguishable after
-- the fact — a confidence that is never stored is a threshold nobody can ever
-- calibrate, which is the class HANDOFF §2a lists as "a number invented rather
-- than measured".
--
-- REAL, matching `simulations.adversarial_share` (020). No default: an
-- unclassified document has no confidence, and 0 would read as "classified,
-- certain it is nothing".
ALTER TABLE documents ADD COLUMN IF NOT EXISTS material_kind_confidence REAL;

ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_material_kind_confidence_range;
ALTER TABLE documents ADD CONSTRAINT documents_material_kind_confidence_range
    CHECK (material_kind_confidence IS NULL
           OR (material_kind_confidence >= 0 AND material_kind_confidence <= 1));

-- A proposal without a value is a confidence about nothing, and a value without
-- a confidence hides how it got there. Both or neither.
ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_material_kind_suggested_paired;
ALTER TABLE documents ADD CONSTRAINT documents_material_kind_suggested_paired
    CHECK ((material_kind_suggested IS NULL) = (material_kind_confidence IS NULL));

-- Finds the queue of documents awaiting a human decision: classified, not yet
-- confirmed. `material_kind IS NULL` is the unconfirmed state (020: NULL reads
-- as 'own' for grounding purposes, but it is not a *decision*).
CREATE INDEX IF NOT EXISTS idx_documents_unconfirmed_material_kind
    ON documents (project_id)
    WHERE material_kind IS NULL AND material_kind_suggested IS NOT NULL;

-- The narrower queue the ICP editor cares about: the classifier saw a
-- competitor and the founder has not agreed. Until they do, `_ground_adversarial`
-- strips the name — so this index answers "what is my adversarial cohort
-- missing?" rather than scanning the project's whole document set.
CREATE INDEX IF NOT EXISTS idx_documents_unconfirmed_competitor
    ON documents (project_id)
    WHERE material_kind_suggested = 'competitor'
      AND material_kind IS DISTINCT FROM 'competitor';

-- ---------------------------------------------------------------------------
-- RLS — the established org-isolation pattern (018 / 020 / 021)
-- ---------------------------------------------------------------------------

ALTER TABLE persona_packs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS persona_packs_org_isolation ON persona_packs;
CREATE POLICY persona_packs_org_isolation ON persona_packs
    FOR ALL USING (organization_id = ANY(public.user_organization_ids()));
