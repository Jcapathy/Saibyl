-- 030: Record that a founder confirmed an audience, as distinct from editing it.
--
-- Additive only: one nullable column. Nothing is backfilled.
--
-- Why this exists
-- ---------------
-- The staged rail states, before any credits move, what a missing input will
-- cost the answer. Stage 4 (Buyers) has to say:
--
--   "We'll search from our guess at your buyer. Confirm the audience first
--    and the list gets sharper."
--
-- which requires knowing whether the audience was confirmed. Until now the only
-- signal was `icp_profiles.edited_by_user`, and that answers a different
-- question. DECISIONS_V2 §3 settled that synthesis proposes and the founder
-- corrects *only what looks wrong* — so the intended, common path is a founder
-- who reads the audience, agrees with all of it, and changes nothing. Under
-- `edited_by_user` that founder reads as unconfirmed forever, and every later
-- stage would tell them their list is a guess when they had in fact confirmed
-- it. Agreement and silence are not the same thing, and one column cannot mean
-- both.
--
-- `confirmed_at` is written only by an explicit act: pressing the confirm
-- control, or saving an edit (saving an edit is a stronger confirmation than
-- pressing the button, so it counts as one).
--
-- Standing lesson from 017: `IF NOT EXISTS` hides type drift, so the column was
-- checked against `information_schema.columns` before this was written —
-- `icp_profiles` had no `confirmed_at` of any type on 2026-08-05.
--
-- Historical rows keep NULL. NULL means "nobody was ever asked", which is the
-- truth for every profile created before this column existed, and the rail
-- states that rather than assuming either answer.

ALTER TABLE icp_profiles
    ADD COLUMN IF NOT EXISTS confirmed_at TIMESTAMPTZ;

COMMENT ON COLUMN icp_profiles.confirmed_at IS
    'When the founder explicitly confirmed this audience (pressed confirm, or '
    'saved an edit). NULL means never confirmed - which is not the same as '
    'rejected, and is the correct value for profiles created before 030.';
