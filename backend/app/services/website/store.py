# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# upload_screenshots(*, organization_id, snapshot_id, capture)
#     -> {"desktop": storage_path, "mobile": storage_path}
# ─────────────────────────────────────────────────────────
"""Screenshot storage for website snapshots (PRD V3 §4a).

Storage only, deliberately: the `website_snapshots` row lifecycle — creating
the row, recording these paths on it, marking failures — belongs to the worker
that orchestrates a capture. Keeping row writes out of this module means a
storage retry can never half-create a snapshot, and the worker owns the one
place where "a snapshot exists" becomes true.

Uses the same bucket and admin-client mechanics as document uploads
(`api/documents.py::store_upload`): one bucket, org-scoped path prefixes, the
service-role client. Screenshots differ from documents in one way — documents
are only ever downloaded back by the pipeline, so their content type never
mattered, while screenshots are served to the dashboard and to vision calls,
so the PNG content type is declared explicitly.
"""
from __future__ import annotations

import structlog

from app.core.database import get_supabase_admin
from app.services.website.capture import WebsiteCapture

logger = structlog.get_logger()

# The documents bucket. Website screenshots live under their own `website/`
# prefix so nothing that globs document paths ever sees them.
_BUCKET = "project-media"


async def upload_screenshots(
    *,
    organization_id: str,
    snapshot_id: str,
    capture: WebsiteCapture,
) -> dict[str, str]:
    """Upload both viewport PNGs; return their storage paths by viewport name.

    Paths are deterministic (`website/{org}/{snapshot}/…`), so a retried upload
    for the same snapshot overwrites nothing surprising — it targets the same
    two objects. Any storage failure propagates: a snapshot without its
    screenshots is not a snapshot, and the worker decides what a failed
    capture attempt becomes.
    """
    admin = get_supabase_admin()
    base = f"website/{organization_id}/{snapshot_id}"
    paths = {"desktop": f"{base}/desktop.png", "mobile": f"{base}/mobile.png"}

    bucket = admin.storage.from_(_BUCKET)
    bucket.upload(paths["desktop"], capture.screenshot_desktop, {"content-type": "image/png"})
    bucket.upload(paths["mobile"], capture.screenshot_mobile, {"content-type": "image/png"})

    logger.info(
        "website_screenshots_stored",
        organization_id=organization_id,
        snapshot_id=snapshot_id,
        desktop_bytes=len(capture.screenshot_desktop),
        mobile_bytes=len(capture.screenshot_mobile),
    )
    return paths
