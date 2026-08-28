-- Migration 043: close twelve advisor warnings without breaking the product
--
-- APPLIED to production (txmvwuekkiedgxwovorp) 2026-08-27 via the Supabase
-- migration API under the name
-- `pin_function_search_path_and_revoke_trigger_execute`. Recorded here so the
-- repo matches production; re-running it is a no-op.
--
-- Supabase's security advisor raised 19 warnings. This closes 15 of them
-- (twelve here, two by the revoke below, one by a console toggle). Four are
-- left open ON PURPOSE — see the bottom of this file. They are not a to-do.
--
-- ---------------------------------------------------------------------------
-- WHY NOT `search_path = ''`, WHICH IS WHAT THE ADVISOR SAYS
-- ---------------------------------------------------------------------------
-- Because it would have broken nine of these twelve functions in production.
--
-- The advisor's remediation assumes every reference inside a function is
-- schema-qualified. Ours are not: `apply_credit_topup`, `deduct_credits`,
-- `deduct_agent_credits`, `grant_credits`, `increment_storage`,
-- `refund_credits`, `refund_discovery_credits`, `simulation_llm_cost` and
-- `simulation_measurement_coverage` all name `organizations`, `credit_topups`,
-- `llm_usage`, `gtm_discovery_runs` or `simulation_events` bare. An empty
-- search_path resolves none of them.
--
-- The failure would not have shown up here. `ALTER FUNCTION … SET search_path`
-- does not re-parse the body, so the migration reports success and the function
-- raises `relation "organizations" does not exist` on its NEXT CALL — which for
-- `grant_credits` is every signup, for `deduct_credits` every run, and for
-- `apply_credit_topup` every Stripe payment.
--
-- `public, pg_temp` satisfies the lint, pins the path against the session-level
-- manipulation the lint is actually about, and cannot change any name that
-- resolves today. `pg_temp` is listed LAST deliberately: when it is not listed
-- at all, Postgres searches the temporary schema FIRST for relations, which is
-- precisely the shadowing route worth closing.

ALTER FUNCTION public.apply_credit_topup(text, text)            SET search_path = public, pg_temp;
ALTER FUNCTION public.deduct_agent_credits(uuid, bigint)        SET search_path = public, pg_temp;
ALTER FUNCTION public.deduct_credits(uuid, bigint)              SET search_path = public, pg_temp;
ALTER FUNCTION public.grant_credits(uuid, bigint)               SET search_path = public, pg_temp;
ALTER FUNCTION public.handle_new_user()                         SET search_path = public, pg_temp;
ALTER FUNCTION public.increment_storage(uuid, bigint)           SET search_path = public, pg_temp;
ALTER FUNCTION public.refund_credits(uuid, bigint)              SET search_path = public, pg_temp;
ALTER FUNCTION public.refund_discovery_credits(uuid, bigint)    SET search_path = public, pg_temp;
ALTER FUNCTION public.simulation_llm_cost(uuid)                 SET search_path = public, pg_temp;
ALTER FUNCTION public.simulation_measurement_coverage(uuid)     SET search_path = public, pg_temp;
ALTER FUNCTION public.update_updated_at()                       SET search_path = public, pg_temp;
ALTER FUNCTION public.user_organization_ids()                   SET search_path = public, pg_temp;

-- ---------------------------------------------------------------------------
-- The one grant that was genuinely wrong
-- ---------------------------------------------------------------------------
-- `handle_new_user` is the trigger behind `on_auth_user_created` on
-- `auth.users`. It returns `trigger`, so PostgREST could never have invoked it
-- through /rest/v1/rpc no matter who held EXECUTE — but PUBLIC, anon and
-- authenticated held it for no reason, and the advisor was right to say so.
--
-- Safe to revoke: EXECUTE on a trigger function is checked at CREATE TRIGGER
-- time, not per row, and the insert is made by GoTrue's own role.

REVOKE EXECUTE ON FUNCTION public.handle_new_user() FROM PUBLIC, anon, authenticated;

-- ---------------------------------------------------------------------------
-- DO NOT "FINISH THE JOB" — the four remaining warnings are decisions
-- ---------------------------------------------------------------------------
-- 1 & 2. `public.user_organization_ids()` is flagged as a SECURITY DEFINER
--        function executable by `anon` and by `authenticated`. DO NOT REVOKE
--        IT. Thirty-six RLS policies call it — every `*_org_isolation` policy
--        in the schema — and a policy calling a function requires the QUERYING
--        role to hold EXECUTE. Revoking from `authenticated` ends tenant reads
--        on every table at once.
--
--        It is already safe. Its body is
--            SELECT ARRAY(SELECT organization_id FROM public.organization_members
--                         WHERE user_id = auth.uid())
--        so `anon` receives an empty array and a signed-in caller receives only
--        their own organization ids. It returns nothing the caller did not
--        already have.
--
-- 3 & 4. `vector` and `pg_trgm` are installed in `public`. Moving them risks
--        every reference in the schema for no security gain.
--
-- ---------------------------------------------------------------------------
-- HOW THIS WAS VERIFIED, which is not "the migration applied"
-- ---------------------------------------------------------------------------
-- That check is exactly the one that would have passed while the product was
-- broken. Instead every callable function was invoked with ids matching zero
-- rows — which forces the body to RESOLVE its tables without touching data —
-- and none raised `relation does not exist`. A follow-up count confirmed no row
-- was modified. Advisor re-run afterwards: 19 warnings to 4.
