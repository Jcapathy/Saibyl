# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# upload_screenshots(*, organization_id, snapshot_id, capture)
#     -> {"desktop": storage_path, "mobile": storage_path}
# upload_revision(*, organization_id, revision_id, html, capture)
#     -> {"html": storage_path, "desktop": storage_path, "mobile": storage_path}
# read_stored(path) -> bytes
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


async def upload_revision(
    *,
    organization_id: str,
    revision_id: str,
    html: str,
    capture: WebsiteCapture,
) -> dict[str, str]:
    """Upload a revision's page and both viewport PNGs; return the paths.

    Same bucket, same mechanics as `upload_screenshots`, under a `revisions/`
    prefix so nothing that globs a snapshot's own images ever sees a revision's.
    `capture` is the revised page's re-render (the revision loop's
    `capture_after`) — the after-images come from what the critics actually
    re-judged, not from a render nobody scored. The page itself is stored with
    its real content type because the founder downloads it back through the
    API, and a browser handed `application/octet-stream` saves where it should
    show. Any storage failure propagates: the worker decides what a
    half-landed revision becomes.
    """
    admin = get_supabase_admin()
    base = f"website/{organization_id}/revisions/{revision_id}"
    paths = {
        "html": f"{base}/revision.html",
        "desktop": f"{base}/desktop.png",
        "mobile": f"{base}/mobile.png",
    }

    bucket = admin.storage.from_(_BUCKET)
    bucket.upload(paths["html"], html.encode("utf-8"), {"content-type": "text/html"})
    bucket.upload(paths["desktop"], capture.screenshot_desktop, {"content-type": "image/png"})
    bucket.upload(paths["mobile"], capture.screenshot_mobile, {"content-type": "image/png"})

    logger.info(
        "website_revision_stored",
        organization_id=organization_id,
        revision_id=revision_id,
        html_bytes=len(html.encode("utf-8")),
        desktop_bytes=len(capture.screenshot_desktop),
        mobile_bytes=len(capture.screenshot_mobile),
    )
    return paths


async def read_stored(path: str) -> bytes:
    """Read one stored object back, whole.

    The passthrough routes serve stored HTML and PNGs to the dashboard; they
    hold a storage path from a row and need its bytes, nothing more. Reading
    through this module rather than each route touching the bucket keeps the
    bucket name in one place — the same reason uploads live here.
    """
    return get_supabase_admin().storage.from_(_BUCKET).download(path)
