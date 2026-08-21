-- 041 — family_offices + capital_shortlists (the capital module's bank)
--
-- Additive. No column is added to an existing table and nothing is backfilled,
-- so this is safe to apply before the deploy that writes it — which is the
-- order this repo uses, because a deploy that writes a column the database does
-- not have fails on the customer's first click.
--
-- **The constraints below are the point of this file, not decoration.**
-- `services/gtm/privacy.py` says the three things that make a data-protection
-- position answerable are "enforced here or in the migration rather than by
-- convention". The Pydantic models in `services/capital/schema.py` enforce them
-- on every write this codebase makes; these constraints enforce them on the
-- writes it does not make — a manual INSERT during curation, a restored
-- backup, a later ingestion path written by somebody who did not read the
-- module. A rule that lives only in application code is a rule the database
-- will happily let you break at 2am.

-- ---------------------------------------------------------------------------
-- The bank
-- ---------------------------------------------------------------------------
--
-- **No organization_id, deliberately.** This is curated reference data about
-- public firms, shared by every founder on the platform — it holds nothing
-- about any customer, and partitioning it per org would mean researching the
-- same fifty firms once per customer. Read access is granted to any signed-in
-- member; writes have no policy at all, so they can only be made by the service
-- role. Curation is an editorial act with Saido Labs' name on the
-- recommendation, not a customer one.

CREATE TABLE IF NOT EXISTS family_offices (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    firm_name           TEXT NOT NULL,
    domain              TEXT,
    -- single_family | multi_family | foundation
    firm_type           TEXT NOT NULL,

    -- The firm's own published words, quoted rather than paraphrased. A
    -- paraphrase cannot be compared against a founder's material and quoted
    -- back to them, which is the entire mechanism of the match.
    thesis              TEXT NOT NULL DEFAULT '',
    sectors             JSONB NOT NULL DEFAULT '[]'::jsonb,
    stages              JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- NULL when the firm publishes no range. NULL beats a guess: a founder who
    -- finds one invented cheque range has no reason to believe any other field.
    check_size_low      BIGINT,
    check_size_high     BIGINT,

    geography           JSONB NOT NULL DEFAULT '[]'::jsonb,
    notable_investments JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- The firm's OWN published route: {"kind", "value", "source_url"} where
    -- kind is submission_form | firm_address | warm_intro_only | no_inbound.
    -- The two refusal kinds carry no value, because a route stored next to
    -- "they take no inbound" is a route somebody uses anyway.
    inbound_path        JSONB NOT NULL,

    -- Named people, restricted to privacy.ALLOWED_CONTACT_FIELDS. See the
    -- constraints below — this column is the one that would carry personal
    -- data if anything here did.
    people              JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- Provenance, per the rule gtm_candidates already carries: a firm a founder
    -- cannot trace back to a published page is a recommendation they cannot
    -- check.
    source_url          TEXT NOT NULL,
    source_title        TEXT NOT NULL DEFAULT '',
    retrieved_at        TIMESTAMPTZ NOT NULL,

    -- Freshness, as data rather than as a habit. A record past stale_after is
    -- withheld or re-verified, never shown as current: withheld is honest,
    -- stale is a wrong pitch sent to a real firm with our name on it.
    verified_at         TIMESTAMPTZ,
    stale_after         TIMESTAMPTZ NOT NULL,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT family_offices_firm_type_known
        CHECK (firm_type IN ('single_family', 'multi_family', 'foundation')),

    -- The gtm_candidates rule, restated: NOT NULL alone would admit ''.
    CONSTRAINT family_offices_source_url_present
        CHECK (length(btrim(source_url)) > 0),

    CONSTRAINT family_offices_check_size_ordered
        CHECK (
            check_size_low IS NULL
            OR check_size_high IS NULL
            OR check_size_low <= check_size_high
        ),

    -- A record with no expiry never goes stale, which is how an investor list
    -- launders decay into confidence.
    CONSTRAINT family_offices_expires_after_retrieval
        CHECK (stale_after > retrieved_at),

    CONSTRAINT family_offices_inbound_kind_known
        CHECK (
            inbound_path ->> 'kind' IN (
                'submission_form', 'firm_address', 'warm_intro_only', 'no_inbound'
            )
            AND length(btrim(coalesce(inbound_path ->> 'source_url', ''))) > 0
        ),

    -- A stated refusal carries no route.
    CONSTRAINT family_offices_refusal_carries_no_route
        CHECK (
            inbound_path ->> 'kind' NOT IN ('warm_intro_only', 'no_inbound')
            OR coalesce(inbound_path ->> 'value', '') = ''
        ),

    -- ── The rule this module exists to keep ────────────────────────────────
    --
    -- No personal email address and no phone number, in the firm's free text or
    -- against any named person. `inbound_path` is exempt and only it: a firm's
    -- own published role address is firm contact information, and the
    -- allowlist that decides which local parts qualify lives in
    -- `schema.FIRM_INBOUND_LOCAL_PARTS` (nobody is named `submissions`).
    -- Postgres cannot express that allowlist here without a function, so the
    -- Python model is the enforcement for that one field and this file is the
    -- enforcement for every other.
    --
    -- The patterns are the ones `gtm/schema.contains_personal_contact_detail`
    -- applies. They are deliberately over-broad — a thesis containing
    -- "2020-2024" reads as a phone number and the row is refused — which is the
    -- trade `privacy.py` already made and argued: a false positive costs one
    -- dropped record, a false negative puts a personal email address in
    -- Saibyl's database. Refusing the insert is also what the application does,
    -- so the two agree rather than one silently permitting what the other bans.
    CONSTRAINT family_offices_thesis_carries_no_contact_detail
        CHECK (
            thesis !~ '[[:alnum:]._%+-]+@[[:alnum:].-]+\.[[:alpha:]]{2,}'
            AND thesis !~ '\+?[[:digit:]][[:digit:] ().-]{7,}[[:digit:]]'
        ),
    CONSTRAINT family_offices_name_carries_no_contact_detail
        CHECK (
            firm_name !~ '[[:alnum:]._%+-]+@[[:alnum:].-]+\.[[:alpha:]]{2,}'
            AND firm_name !~ '\+?[[:digit:]][[:digit:] ().-]{7,}[[:digit:]]'
        ),

    -- Only the six fields privacy.ALLOWED_CONTACT_FIELDS permits may appear on
    -- a stored person. A seventh key — `email`, `phone`, `mobile`, whatever the
    -- ticket calls it — is rejected by the database, not merely by the model
    -- that happens to be in front of it today.
    CONSTRAINT family_offices_people_fields_are_permitted
        CHECK (
            NOT jsonb_path_exists(
                people,
                '$[*].keyvalue() ? (@.key != "full_name" && @.key != "role_title" && @.key != "employer" && @.key != "public_profile_url" && @.key != "source_url" && @.key != "retrieved_at")'
            )
        ),

    -- No email address against a person, in any of their fields. Safe to scan
    -- every value because an ISO timestamp contains no '@'.
    CONSTRAINT family_offices_people_carry_no_email
        CHECK (
            NOT jsonb_path_exists(
                people,
                '$[*].keyvalue().value ? (@ like_regex "[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+[.][A-Za-z]{2,}")'
            )
        ),

    -- And no phone number — scoped to the three free-text fields rather than to
    -- every value, because `retrieved_at` is an ISO date and an ISO date
    -- matches any pattern loose enough to catch a phone number ("2026-08-20" is
    -- ten digits with separators). A constraint that rejects every valid row is
    -- a constraint somebody drops.
    CONSTRAINT family_offices_people_carry_no_phone
        CHECK (
            NOT jsonb_path_exists(
                people,
                '$[*] ? (@.full_name like_regex "[+]?[0-9][-0-9 ().]{7,}[0-9]" || @.role_title like_regex "[+]?[0-9][-0-9 ().]{7,}[0-9]" || @.employer like_regex "[+]?[0-9][-0-9 ().]{7,}[0-9]")'
            )
        ),

    -- Every stored person carries their own provenance, so an erasure or
    -- subject-access request is answerable per person and not only per firm.
    CONSTRAINT family_offices_people_carry_provenance
        CHECK (
            NOT jsonb_path_exists(
                people,
                '$[*] ? (!exists(@.source_url) || !exists(@.retrieved_at) || @.source_url == "")'
            )
        )
);

-- The reader's queries: browse by name, filter by type, and the freshness
-- partition that runs on every read.
CREATE INDEX IF NOT EXISTS idx_family_offices_name ON family_offices (firm_name);
CREATE INDEX IF NOT EXISTS idx_family_offices_type ON family_offices (firm_type, firm_name);
CREATE INDEX IF NOT EXISTS idx_family_offices_freshness ON family_offices (stale_after DESC);

ALTER TABLE family_offices ENABLE ROW LEVEL SECURITY;

-- Readable by any signed-in member; writable by nobody through a user token.
-- There is deliberately no INSERT, UPDATE or DELETE policy: the service role
-- bypasses RLS and is the only thing that curates this table.
DROP POLICY IF EXISTS family_offices_readable_by_members ON family_offices;
CREATE POLICY family_offices_readable_by_members ON family_offices
    FOR SELECT
    USING (auth.uid() IS NOT NULL);


-- ---------------------------------------------------------------------------
-- The artifact
-- ---------------------------------------------------------------------------
--
-- One row per build, not one per project: a founder who rebuilds after running
-- a new room wants to compare, and UNIQUE (project_id) would make the second
-- build destroy the evidence of the first. The reader takes the newest complete
-- row.

CREATE TABLE IF NOT EXISTS capital_shortlists (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id          UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    organization_id     UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    -- The run whose measured objections built the objection bridge. NULL is a
    -- real state: a founder can ask who would fund this before they have run a
    -- room, and the shortlist's notes say what it was missing.
    simulation_id       UUID REFERENCES simulations(id) ON DELETE SET NULL,

    -- building | complete | failed
    status              TEXT NOT NULL DEFAULT 'building',

    -- What was asked, kept so a stored shortlist can be read back without the
    -- request that produced it.
    sector              TEXT NOT NULL DEFAULT '',
    stage               TEXT NOT NULL DEFAULT '',
    check_size_needed   BIGINT,

    -- Ranked firms, each with its reasons quoting both sides' actual language.
    matches             JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- Firms that publish a position ruling this founder out, reported rather
    -- than dropped. A shorter list padded back to length with firms that would
    -- have said the same thing on the call is the failure this column prevents.
    refusals            JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- Records we hold and would not assert, named with their dates.
    withheld_stale      JSONB NOT NULL DEFAULT '[]'::jsonb,
    notes               JSONB NOT NULL DEFAULT '[]'::jsonb,

    firms_considered    INTEGER NOT NULL DEFAULT 0,
    matches_count       INTEGER NOT NULL DEFAULT 0,
    refusals_count      INTEGER NOT NULL DEFAULT 0,

    -- The instant every freshness decision was made against, stored so a
    -- re-read can say what "current" meant when this was built.
    as_of               TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    credits_charged     BIGINT NOT NULL DEFAULT 0,
    -- A founder-readable sentence, never a Python exception.
    error_message       TEXT,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at        TIMESTAMPTZ,

    CONSTRAINT capital_shortlists_status_known
        CHECK (status IN ('building', 'complete', 'failed'))
);

CREATE INDEX IF NOT EXISTS idx_capital_shortlists_project
    ON capital_shortlists (project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_capital_shortlists_org
    ON capital_shortlists (organization_id, created_at DESC);

ALTER TABLE capital_shortlists ENABLE ROW LEVEL SECURITY;

-- Org isolation, matching every other artifact table in this schema. The API
-- reads through the service role and filters by org itself; this is the
-- backstop for anything that ever reaches the table with a user token.
DROP POLICY IF EXISTS capital_shortlists_org_isolation ON capital_shortlists;
CREATE POLICY capital_shortlists_org_isolation ON capital_shortlists
    USING (
        organization_id IN (
            SELECT organization_id FROM organization_members
            WHERE user_id = auth.uid()
        )
    );
