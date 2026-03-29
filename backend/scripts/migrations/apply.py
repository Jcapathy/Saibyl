"""Apply all migration SQL files in order against Supabase."""

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.core.database import get_supabase_admin


def apply_migrations():
    admin = get_supabase_admin()
    migrations_dir = Path(__file__).parent

    sql_files = sorted(migrations_dir.glob("*.sql"))
    if not sql_files:
        print("No migration files found.")
        return

    for sql_file in sql_files:
        print(f"Applying {sql_file.name}...")
        sql = sql_file.read_text(encoding="utf-8")
        try:
            admin.postgrest.rpc("exec_sql", {"query": sql}).execute()
            print(f"  OK: {sql_file.name}")
        except Exception as e:
            print(f"  WARN: {sql_file.name} — {e}")
            print("  (Apply via Supabase Dashboard SQL Editor or MCP apply_migration)")

    print("\nMigration run complete.")


if __name__ == "__main__":
    apply_migrations()
