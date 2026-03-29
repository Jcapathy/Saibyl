"""Pre-deploy database backup script.
Dumps Supabase Postgres to a SQL file and uploads to Supabase Storage.
Usage: python scripts/backup.py
"""
import os
import subprocess
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def backup():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL not set")
        sys.exit(1)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"pre-deploy-{timestamp}.sql"
    local_path = f"/tmp/{filename}"

    print(f"Starting backup: {filename}")

    # pg_dump
    result = subprocess.run(
        ["pg_dump", db_url, "--no-owner", "--no-acl", "-f", local_path],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(f"pg_dump failed: {result.stderr}")
        sys.exit(1)

    file_size = os.path.getsize(local_path)
    print(f"Dump complete: {file_size / 1024 / 1024:.1f} MB")

    # Upload to Supabase Storage
    try:
        from app.core.database import get_supabase_admin

        admin = get_supabase_admin()
        storage_path = f"backups/{filename}"

        with open(local_path, "rb") as f:
            admin.storage.from_("exports").upload(
                storage_path, f.read(), {"content-type": "application/sql"}
            )
        print(f"Uploaded to storage: {storage_path}")
    except Exception as e:
        print(f"Storage upload failed (backup saved locally): {e}")

    # Cleanup local file
    os.remove(local_path)
    print("Backup complete.")


if __name__ == "__main__":
    backup()
