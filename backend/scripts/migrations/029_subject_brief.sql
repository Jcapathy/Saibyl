-- Migration 029: the subject brief — what a run's agents actually react to
--
-- NOT APPLIED. Highest applied is 025; 026 and 027 exist unapplied and neither
-- touches anything below, so the three may be applied in any order.
--
-- SAFE TO APPLY WHILE master IS DEPLOYED. One new table, nothing altered,
-- nothing dropped. `master` neither reads nor writes it, and a v2 deploy that
-- lands before this migration degrades to running without briefs and says so
-- (`subject_brief_unresolved`) rather than failing — so the ordering hazard
-- migration 019 documented (a constraint that outruns the code satisfying it)
-- does not arise here in either direction.
--
-- **What was and was not checked.** `grep -i subject_brief scripts/migrations/`
-- returns nothing outside this file, so no earlier migration in this repository
-- creates any of these objects. This was *not* verified against the live
-- `information_schema` — this session has no production database access — so the
-- IF NOT EXISTS guards below are real guards rather than formalities, and
-- migration 017's lesson applies in full: **before applying, confirm no
-- `subject_briefs` relation already exists.** A guard that silently no-ops over
-- a table of the same name with different types is exactly how type drift ships.
--
-- ---------------------------------------------------------------------------
-- WHY THIS TABLE EXISTS
-- ---------------------------------------------------------------------------
--
-- A founder uploaded a 14,029-character deck. It extracted cleanly
-- (`processing_status = 'complete'`, `extracted_char_count = 14028`). The run
-- then put `doc_context[:2000]` — 14% of it — into the *agent-generation*
-- prompt, where it shaped who the agents were, and handed those agents a
-- subject consisting of the one-line `prediction_goal`. Ninety-six agents spent
-- five rounds arguing about a sentence, and the report was about the sentence.
--
-- The material is now distilled once per run into a bounded brief that rides in
-- every action prompt through `topic_block()`. This table is where that brief
-- lives, and it is a table rather than a column on `simulations` for three
-- reasons, in order of weight:
--
--   1. **The failures have to be on the record too.** "This project uploaded
--      nothing" and "this project uploaded a deck that never reached the
--      agents" are opposite facts that used to produce identical logs. `status`
--      plus `reason` is what separates them a month later, when the founder
--      asks why their report was about their tagline.
--   2. **Provenance.** `source_document_ids` is which uploads grounded the
--      subject. A brief nobody can trace to a document is the same object as a
--      number nobody can trace to a measurement (HANDOFF §2a).
--   3. **One row per run, re-read not regenerated.** The UNIQUE constraint is
--      what makes "the subject does not change between rounds" an invariant of
--      the database rather than a convention in the worker — the same argument
--      migration 019 makes for agent usernames.
--
-- Cost: the distillation is metered under stage `subject_distillation` in
-- `llm_usage`, and the per-action surcharge inside `agent_action`. See
-- `SUBJECT_DISTILLATION` and `SUBJECT_BRIEF_ACTION` in `agent_pricing.py`.

CREATE TABLE IF NOT EXISTS subject_briefs (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- UNIQUE, not merely indexed. One run has one subject. Two rows here would
    -- mean two arenas of one run could be handed different subjects, which
    -- would make the variant comparison — the entire artifact — a comparison of
    -- two things that were never the same.
    simulation_id        UUID NOT NULL UNIQUE
                             REFERENCES simulations(id) ON DELETE CASCADE,

    -- Nullable, matching `simulations.project_id`: a run can exist without a
    -- project, and that is one of the reasons a brief can legitimately be empty.
    project_id           UUID REFERENCES projects(id) ON DELETE SET NULL,
    organization_id      UUID REFERENCES organizations(id) ON DELETE CASCADE,

    -- ready              distilled from this project's own material
    -- inherited          copied from the parent run of a re-simulation
    -- no_material        the project has no uploads at all
    -- material_unusable  it has uploads, and none of them may describe the
    --                    subject: competitor-labelled, market-labelled, still
    --                    processing, or empty after extraction
    -- distillation_failed the pass ran and produced nothing usable
    --
    -- The last two are the ones worth having a name for. They are what a run
    -- looks like when material was uploaded and did not reach the agents, which
    -- is the defect this whole table exists to make impossible to miss.
    status               TEXT NOT NULL DEFAULT 'no_material',

    -- The brief exactly as agents see it. Bounded by SUBJECT_BRIEF_CHARS
    -- (1,200) in the renderer; the CHECK below is the floor under that, because
    -- this string is re-sent with every one of a run's ~500 action prompts and
    -- a renderer regression that let it grow would multiply the largest cost
    -- line in the product with nothing failing. 2,000 rather than 1,200 so a
    -- deliberate budget change is a code change, not a migration.
    brief                TEXT NOT NULL DEFAULT '',

    -- Why, in a sentence a human can act on, for every status except `ready`.
    -- "no material found" is not an answer: the founder in the originating
    -- defect *had* uploaded a deck.
    reason               TEXT NOT NULL DEFAULT '',

    -- Which uploads grounded it. Not a foreign key array by design — a document
    -- deleted after the run still explains what the agents saw, and cascading a
    -- delete into this column would erase the run's provenance to tidy up a
    -- file.
    source_document_ids  UUID[] NOT NULL DEFAULT '{}',

    -- Set on a re-simulation, which takes its parent's subject verbatim —
    -- including taking its absence. Distilling afresh for the child would change
    -- the subject as well as the published material, and every before/after
    -- delta in the inoculation artifact would then be measuring two changes at
    -- once. DECISIONS §4.
    inherited_from       UUID REFERENCES simulations(id) ON DELETE SET NULL,

    char_count           INTEGER NOT NULL DEFAULT 0,
    -- The model that wrote it, so a brief can be re-read against the model that
    -- produced it after a model change. NULL for inherited and failed rows.
    model                TEXT,

    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE subject_briefs DROP CONSTRAINT IF EXISTS subject_briefs_status_values;
ALTER TABLE subject_briefs ADD CONSTRAINT subject_briefs_status_values
    CHECK (status IN ('ready', 'inherited', 'no_material',
                      'material_unusable', 'distillation_failed'));

-- A brief that is not `ready` or `inherited` must be empty, and one that is
-- empty must carry a reason. Without this, "the subject is missing" and "the
-- subject is present" become distinguishable only by reading the text — which
-- is how the originating defect stayed invisible for a whole phase.
ALTER TABLE subject_briefs DROP CONSTRAINT IF EXISTS subject_briefs_empty_is_explained;
ALTER TABLE subject_briefs ADD CONSTRAINT subject_briefs_empty_is_explained
    CHECK (
        (status = 'ready'     AND brief <> '')
        OR (status = 'inherited' AND reason <> '')
        OR (status IN ('no_material', 'material_unusable', 'distillation_failed')
            AND brief = '' AND reason <> '')
    );

ALTER TABLE subject_briefs DROP CONSTRAINT IF EXISTS subject_briefs_bounded;
ALTER TABLE subject_briefs ADD CONSTRAINT subject_briefs_bounded
    CHECK (char_length(brief) <= 2000);

CREATE INDEX IF NOT EXISTS idx_subject_briefs_project
    ON subject_briefs (project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_subject_briefs_org
    ON subject_briefs (organization_id, created_at DESC);
-- Answers "which runs inherited from this parent", which is the query the
-- inoculation loop's audit asks.
CREATE INDEX IF NOT EXISTS idx_subject_briefs_inherited
    ON subject_briefs (inherited_from) WHERE inherited_from IS NOT NULL;

-- ---------------------------------------------------------------------------
-- RLS — the established org-isolation pattern (018 / 020 / 021 / 027)
-- ---------------------------------------------------------------------------

ALTER TABLE subject_briefs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS subject_briefs_org_isolation ON subject_briefs;
CREATE POLICY subject_briefs_org_isolation ON subject_briefs
    FOR ALL USING (organization_id = ANY(public.user_organization_ids()));
