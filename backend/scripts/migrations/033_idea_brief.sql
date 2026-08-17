-- 033: Let `documents.material_kind` carry 'idea_brief'.
--
-- Additive only: one CHECK constraint widened. No rows change, no columns are
-- added, nothing is backfilled.
--
-- SAFE TO APPLY BEFORE the code that writes idea_brief deploys — additive
-- allowance only. MUST be applied before that deploy, or every idea-brief
-- insert violates the CHECK.
--
-- Why this exists
-- ---------------
-- PRD_V3 §3: a founder with only an idea — nothing to upload — fills a
-- five-field guided form, and the backend composes the answers into a small
-- markdown document stored through the same path as an upload. The existing
-- pipeline (ingestion → subject brief → audience synthesis) then consumes it
-- unchanged. That document carries its own kind, 'idea_brief', rather than
-- 'own', because it records provenance: the text was generated from the form,
-- not uploaded, and the PATCH route refuses to re-label it in either
-- direction. Downstream it reads as the founder's own subject material.
--
-- 020 defined this constraint over ('own', 'competitor', 'market'); recreated
-- here under the same name, with the same NULL allowance, plus 'idea_brief'.

ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_material_kind_values;
ALTER TABLE documents ADD CONSTRAINT documents_material_kind_values
    CHECK (material_kind IS NULL
           OR material_kind IN ('own', 'competitor', 'market', 'idea_brief'));

-- `documents_material_kind_suggested_values` (026) is left untouched, on
-- purpose. The classifier proposes kinds for *uploaded* files and must never
-- emit 'idea_brief': that kind is written only by the idea-form route, and a
-- suggestion carrying it would be a claim about provenance no classifier can
-- make. The narrower constraint is what enforces that.
