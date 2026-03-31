"""Apply all migration SQL files directly to Supabase Postgres with correct ordering."""
import os

import psycopg2


def run():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise ValueError("Set DATABASE_URL env var before running")
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    cur = conn.cursor()

    # Step 1: Helper function (must exist before RLS policies in migrations 002+)
    print("1. Creating helper function public.user_organization_ids()...")
    cur.execute("""
        CREATE OR REPLACE FUNCTION public.user_organization_ids()
        RETURNS UUID[] AS $$
            SELECT ARRAY(
                SELECT organization_id FROM public.organization_members
                WHERE user_id = auth.uid()
            )
        $$ LANGUAGE sql STABLE SECURITY DEFINER;
    """)
    print("   OK")

    # Step 2: api_keys
    print("2. Creating api_keys...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            created_by UUID NOT NULL REFERENCES auth.users(id),
            name TEXT NOT NULL,
            key_hash TEXT NOT NULL UNIQUE,
            key_prefix TEXT NOT NULL,
            last_used_at TIMESTAMPTZ,
            expires_at TIMESTAMPTZ,
            revoked_at TIMESTAMPTZ,
            scopes TEXT[] DEFAULT '{"simulations:read","simulations:write"}',
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;
    """)
    _safe_policy(cur, "api_keys_org_isolation", "api_keys",
                 "organization_id = ANY(public.user_organization_ids())")
    print("   OK")

    # Step 3: projects
    print("3. Creating projects...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            created_by UUID NOT NULL REFERENCES auth.users(id),
            name TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );
        ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
    """)
    _safe_policy(cur, "projects_org_isolation", "projects",
                 "organization_id = ANY(public.user_organization_ids())")
    print("   OK")

    # Step 4: documents, ontologies, knowledge_graphs
    print("4. Creating documents, ontologies, knowledge_graphs...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            organization_id UUID NOT NULL REFERENCES organizations(id),
            filename TEXT NOT NULL,
            file_type TEXT NOT NULL,
            storage_path TEXT NOT NULL,
            file_size_bytes INT,
            processing_status TEXT DEFAULT 'pending',
            error_message TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS ontologies (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            organization_id UUID NOT NULL REFERENCES organizations(id),
            entity_types JSONB NOT NULL DEFAULT '[]',
            relationship_types JSONB NOT NULL DEFAULT '[]',
            pydantic_models TEXT,
            refinement_round INT DEFAULT 1,
            human_approved BOOLEAN DEFAULT FALSE,
            approved_by UUID REFERENCES auth.users(id),
            approved_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS knowledge_graphs (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            organization_id UUID NOT NULL REFERENCES organizations(id),
            node_count INT DEFAULT 0,
            edge_count INT DEFAULT 0,
            build_status TEXT DEFAULT 'pending',
            built_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
        ALTER TABLE ontologies ENABLE ROW LEVEL SECURITY;
        ALTER TABLE knowledge_graphs ENABLE ROW LEVEL SECURITY;
    """)
    for tbl in ["documents", "ontologies", "knowledge_graphs"]:
        _safe_policy(cur, f"{tbl}_org_isolation", tbl,
                     "organization_id = ANY(public.user_organization_ids())")
    print("   OK")

    # Step 5: simulations, simulation_agents, simulation_events
    print("5. Creating simulations, simulation_agents, simulation_events...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS simulations (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            organization_id UUID NOT NULL REFERENCES organizations(id),
            created_by UUID NOT NULL REFERENCES auth.users(id),
            name TEXT NOT NULL,
            prediction_goal TEXT NOT NULL,
            status TEXT DEFAULT 'draft',
            is_ab_test BOOLEAN DEFAULT FALSE,
            variant_a_config JSONB,
            variant_b_config JSONB,
            max_rounds INT DEFAULT 10,
            platforms TEXT[] DEFAULT '{}',
            timezone TEXT DEFAULT 'America/New_York',
            scheduled_start_at TIMESTAMPTZ,
            winner_variant TEXT,
            completed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS simulation_agents (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            simulation_id UUID NOT NULL REFERENCES simulations(id) ON DELETE CASCADE,
            organization_id UUID NOT NULL REFERENCES organizations(id),
            entity_id TEXT NOT NULL,
            entity_name TEXT NOT NULL,
            persona_pack_id TEXT,
            variant TEXT DEFAULT 'a',
            platform TEXT NOT NULL,
            profile JSONB NOT NULL,
            username TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS simulation_events (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            simulation_id UUID NOT NULL REFERENCES simulations(id) ON DELETE CASCADE,
            organization_id UUID NOT NULL REFERENCES organizations(id),
            event_type TEXT NOT NULL,
            agent_id UUID REFERENCES simulation_agents(id),
            platform TEXT,
            variant TEXT DEFAULT 'a',
            round_number INT,
            content TEXT,
            metadata JSONB DEFAULT '{}',
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_simulation_events_sim_id
            ON simulation_events(simulation_id, created_at DESC);
        ALTER TABLE simulations ENABLE ROW LEVEL SECURITY;
        ALTER TABLE simulation_agents ENABLE ROW LEVEL SECURITY;
        ALTER TABLE simulation_events ENABLE ROW LEVEL SECURITY;
    """)
    for tbl in ["simulations", "simulation_agents", "simulation_events"]:
        _safe_policy(cur, f"{tbl}_org_isolation", tbl,
                     "organization_id = ANY(public.user_organization_ids())")
    print("   OK")

    # Step 6: reports, report_sections
    print("6. Creating reports, report_sections...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            simulation_id UUID NOT NULL REFERENCES simulations(id) ON DELETE CASCADE,
            organization_id UUID NOT NULL REFERENCES organizations(id),
            title TEXT,
            status TEXT DEFAULT 'pending',
            variant TEXT DEFAULT 'a',
            react_config JSONB DEFAULT '{}',
            section_count INT DEFAULT 0,
            markdown_content TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            completed_at TIMESTAMPTZ
        );
        CREATE TABLE IF NOT EXISTS report_sections (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            report_id UUID NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
            organization_id UUID NOT NULL REFERENCES organizations(id),
            section_index INT NOT NULL,
            title TEXT NOT NULL,
            content TEXT,
            tool_calls JSONB DEFAULT '[]',
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        ALTER TABLE reports ENABLE ROW LEVEL SECURITY;
        ALTER TABLE report_sections ENABLE ROW LEVEL SECURITY;
    """)
    for tbl in ["reports", "report_sections"]:
        _safe_policy(cur, f"{tbl}_org_isolation", tbl,
                     "organization_id = ANY(public.user_organization_ids())")
    print("   OK")

    # Step 7: webhooks, usage_records
    print("7. Creating webhooks, usage_records...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS webhooks (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            created_by UUID NOT NULL REFERENCES auth.users(id),
            url TEXT NOT NULL,
            events TEXT[] NOT NULL,
            secret TEXT NOT NULL,
            custom_headers JSONB DEFAULT '{}',
            is_active BOOLEAN DEFAULT TRUE,
            last_triggered_at TIMESTAMPTZ,
            failure_count INT DEFAULT 0,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS usage_records (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            organization_id UUID NOT NULL REFERENCES organizations(id),
            month TEXT NOT NULL,
            simulations_run INT DEFAULT 0,
            llm_tokens_used BIGINT DEFAULT 0,
            storage_bytes_used BIGINT DEFAULT 0,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(organization_id, month)
        );
        ALTER TABLE webhooks ENABLE ROW LEVEL SECURITY;
        ALTER TABLE usage_records ENABLE ROW LEVEL SECURITY;
    """)
    for tbl in ["webhooks", "usage_records"]:
        _safe_policy(cur, f"{tbl}_org_isolation", tbl,
                     "organization_id = ANY(public.user_organization_ids())")
    print("   OK")

    # Step 8: Triggers
    print("8. Creating triggers...")
    cur.execute("""
        CREATE OR REPLACE FUNCTION public.update_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    for tbl in ["organizations", "user_profiles", "projects",
                "ontologies", "simulations", "usage_records"]:
        _safe_trigger(cur, "set_updated_at", tbl, "public.update_updated_at()")

    # New user profile trigger
    cur.execute("""
        CREATE OR REPLACE FUNCTION public.handle_new_user()
        RETURNS TRIGGER AS $$
        BEGIN
            INSERT INTO public.user_profiles(id) VALUES(NEW.id);
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql SECURITY DEFINER;
    """)
    _safe_trigger(cur, "on_auth_user_created", "auth.users",
                  "public.handle_new_user()", when="AFTER INSERT")
    print("   OK")

    # Final verification
    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' ORDER BY table_name
    """)
    tables = [r[0] for r in cur.fetchall()]
    print(f"\n=== Public tables ({len(tables)}) ===")
    for t in tables:
        print(f"  {t}")

    cur.execute("""
        SELECT tablename, rowsecurity FROM pg_tables
        WHERE schemaname = 'public' ORDER BY tablename
    """)
    print("\n=== RLS Status ===")
    all_ok = True
    for name, rls in cur.fetchall():
        s = "ENABLED" if rls else "DISABLED"
        if not rls:
            all_ok = False
        print(f"  {name}: {s}")
    print(f"\nAll RLS enabled: {all_ok}")

    cur.close()
    conn.close()
    print("\nAll migrations applied successfully.")


def _safe_policy(cur, name, table, using_expr):
    """Create policy, skip if already exists."""
    try:
        cur.execute(
            f'CREATE POLICY "{name}" ON {table} USING ({using_expr});'
        )
    except psycopg2.Error:
        pass  # already exists


def _safe_trigger(cur, name, table, func, when="BEFORE UPDATE"):
    """Create trigger, skip if already exists."""
    try:
        cur.execute(
            f"CREATE TRIGGER {name} {when} ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION {func};"
        )
    except psycopg2.Error:
        pass  # already exists


if __name__ == "__main__":
    run()
