import structlog

from app.core.database import get_supabase_admin

logger = structlog.get_logger()


async def run_export_report(report_id: str, format: str = "pdf"):
    """Export report to PDF/PPTX/JSON and upload to Supabase Storage."""
    admin = get_supabase_admin()

    report = admin.table("reports").select(
        "organization_id"
    ).eq("id", report_id).single().execute().data
    org_id = report["organization_id"]

    logger.info("export_started", report_id=report_id, format=format)

    if format == "pdf":
        from app.services.export.pdf_exporter import export_report_pdf
        file_bytes = await export_report_pdf(report_id)
        content_type = "application/pdf"
        ext = "pdf"

    elif format == "pptx":
        from app.services.export.pptx_exporter import export_report_pptx
        file_bytes = await export_report_pptx(report_id)
        content_type = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        ext = "pptx"

    elif format == "json":
        from app.services.export.json_exporter import export_report_json
        file_bytes = await export_report_json(report_id)
        content_type = "application/gzip"
        ext = "json.gz"

    else:
        raise ValueError(f"Unsupported format: {format}")

    # Upload to Supabase Storage
    storage_path = f"exports/{org_id}/{report_id}/report.{ext}"
    admin.storage.from_("exports").upload(
        storage_path,
        file_bytes,
        {"content-type": content_type},
    )

    # Generate signed download URL (1 hour)
    signed = admin.storage.from_("exports").create_signed_url(storage_path, 3600)
    download_url = signed.get("signedURL", "")

    logger.info("export_complete", report_id=report_id, format=format, size=len(file_bytes))

    return {
        "report_id": report_id,
        "format": format,
        "status": "complete",
        "download_url": download_url,
        "file_size_bytes": len(file_bytes),
        "storage_path": storage_path,
    }


async def run_export_simulation(simulation_id: str):
    """Export full simulation data as gzipped JSON."""
    from app.services.export.json_exporter import export_simulation_json

    admin = get_supabase_admin()
    sim = admin.table("simulations").select(
        "organization_id"
    ).eq("id", simulation_id).single().execute().data
    org_id = sim["organization_id"]

    file_bytes = await export_simulation_json(simulation_id)

    storage_path = f"exports/{org_id}/{simulation_id}/simulation.json.gz"
    admin.storage.from_("exports").upload(
        storage_path,
        file_bytes,
        {"content-type": "application/gzip"},
    )

    signed = admin.storage.from_("exports").create_signed_url(storage_path, 3600)
    download_url = signed.get("signedURL", "")

    logger.info("simulation_export_complete", simulation_id=simulation_id, size=len(file_bytes))

    return {
        "simulation_id": simulation_id,
        "format": "json",
        "status": "complete",
        "download_url": download_url,
        "file_size_bytes": len(file_bytes),
    }
