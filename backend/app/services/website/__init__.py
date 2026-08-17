# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# capture — WebsiteCapture, WebsiteCaptureError,
#           capture_website(url, *, timeout_s=45)
# store   — upload_screenshots(organization_id, snapshot_id, capture)
# ─────────────────────────────────────────────────────────
"""Website Intelligence ingestion (PRD V3 §4a): URL -> judgeable evidence.

Two modules, split along what can fail independently:

    capture   fetch + headless render -> screenshots, DOM text, meta tags
    store     the two PNGs -> Supabase storage, under website/{org}/{snapshot}/

Neither touches `website_snapshots` rows — the worker that orchestrates a
capture owns that lifecycle, so a retry at either step can never leave a
half-created snapshot behind.

`capture` imports Playwright lazily: only the Docker image carries a browser
runtime, and every other environment (local venvs, CI) must still import the
app. Nothing here may be imported at module scope that assumes a browser.
"""
