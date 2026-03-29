"""Seed script: creates demo organization, user, and sample project."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.database import get_supabase_admin


def seed():
    admin = get_supabase_admin()

    # 1. Create demo organization
    org_result = (
        admin.table("organizations")
        .upsert(
            {
                "name": "Saibyl Demo",
                "slug": "saibyl-demo",
                "plan": "pro",
                "max_simulations_per_month": 100,
                "max_team_members": 10,
            },
            on_conflict="slug",
        )
        .execute()
    )
    org = org_result.data[0]
    print(f"Organization: {org['name']} ({org['id']})")

    # 2. Create demo user via Supabase Auth
    demo_email = os.environ.get("DEMO_USER_EMAIL", "demo@saibyl.ai")
    demo_password = os.environ.get("DEMO_USER_PASSWORD", "demo-password-change-me")

    try:
        user_result = admin.auth.admin.create_user(
            {"email": demo_email, "password": demo_password, "email_confirm": True}
        )
        user_id = user_result.user.id
        print(f"User created: {demo_email} ({user_id})")
    except Exception as e:
        if "already" in str(e).lower():
            users = admin.auth.admin.list_users()
            user_id = next(u.id for u in users if u.email == demo_email)
            print(f"User already exists: {demo_email} ({user_id})")
        else:
            raise

    # 3. Link user to organization
    admin.table("organization_members").upsert(
        {
            "organization_id": org["id"],
            "user_id": user_id,
            "role": "owner",
        },
        on_conflict="organization_id,user_id",
    ).execute()
    print("Linked user to org as owner")

    # 4. Create sample project
    project_result = (
        admin.table("projects")
        .insert(
            {
                "organization_id": org["id"],
                "created_by": user_id,
                "name": "Sample Prediction Project",
                "description": "A demo project to explore Saibyl's prediction capabilities.",
            }
        )
        .execute()
    )
    print(f"Project created: {project_result.data[0]['name']}")

    print("\nSeed complete.")


if __name__ == "__main__":
    seed()
