# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# check_storage_quota(org_id, file_size_bytes) -> StorageCheckResult
# update_org_storage_usage(org_id, delta_bytes) -> None
# get_storage_packs_for_org(org_id) -> list[StoragePack]
# ─────────────────────────────────────────────────────────
from __future__ import annotations

from uuid import UUID

import structlog
from pydantic import BaseModel

from app.core.database import get_supabase_admin

logger = structlog.get_logger()

# Storage limits in bytes
PLAN_STORAGE_LIMITS = {
    "starter": 5 * 1024**3,       # 5 GB
    "pro": 25 * 1024**3,          # 25 GB
    "enterprise": 100 * 1024**3,  # 100 GB
}

STORAGE_PACK_SIZES = {
    "storage_pack_s": 50 * 1024**3,    # +50 GB
    "storage_pack_m": 200 * 1024**3,   # +200 GB
    "storage_pack_l": 1000 * 1024**3,  # +1 TB
}


class StorageCheckResult(BaseModel):
    allowed: bool
    current_used_bytes: int
    total_limit_bytes: int
    available_bytes: int
    overage_bytes: int = 0
    message: str


class StoragePack(BaseModel):
    pack_id: str
    size_bytes: int
    size_label: str


def _get_total_limit(plan: str, pack_ids: list[str]) -> int:
    """Calculate total storage limit from plan + packs."""
    base = PLAN_STORAGE_LIMITS.get(plan, PLAN_STORAGE_LIMITS["starter"])
    extra = sum(STORAGE_PACK_SIZES.get(p, 0) for p in pack_ids)
    return base + extra


def check_storage_quota(org_id: UUID, file_size_bytes: int) -> StorageCheckResult:
    """Check if org has enough storage for an upload."""
    admin = get_supabase_admin()
    org = admin.table("organizations").select(
        "plan, storage_bytes_used, storage_pack_ids"
    ).eq("id", str(org_id)).single().execute().data

    used = org.get("storage_bytes_used", 0) or 0
    total = _get_total_limit(org.get("plan", "starter"), org.get("storage_pack_ids") or [])
    available = total - used

    if file_size_bytes <= available:
        return StorageCheckResult(
            allowed=True,
            current_used_bytes=used,
            total_limit_bytes=total,
            available_bytes=available,
            message="Upload allowed",
        )
    else:
        return StorageCheckResult(
            allowed=False,
            current_used_bytes=used,
            total_limit_bytes=total,
            available_bytes=available,
            overage_bytes=file_size_bytes - available,
            message=f"Storage limit exceeded. Need {file_size_bytes - available:,} more bytes. Upgrade your plan or add a storage pack.",
        )


def update_org_storage_usage(org_id: UUID, delta_bytes: int) -> None:
    """Update org storage usage atomically (+delta for upload, -delta for delete)."""
    admin = get_supabase_admin()
    admin.rpc("increment_storage", {
        "org_uuid": str(org_id),
        "delta": delta_bytes,
    }).execute()

    logger.info("storage_updated", org_id=str(org_id), delta=delta_bytes)


def get_storage_packs_for_org(org_id: UUID) -> list[StoragePack]:
    """Get active storage packs for an org."""
    admin = get_supabase_admin()
    org = admin.table("organizations").select(
        "storage_pack_ids"
    ).eq("id", str(org_id)).single().execute().data

    pack_ids = org.get("storage_pack_ids") or []
    packs = []
    labels = {"storage_pack_s": "+50 GB", "storage_pack_m": "+200 GB", "storage_pack_l": "+1 TB"}
    for pid in pack_ids:
        if pid in STORAGE_PACK_SIZES:
            packs.append(StoragePack(
                pack_id=pid,
                size_bytes=STORAGE_PACK_SIZES[pid],
                size_label=labels.get(pid, pid),
            ))
    return packs
