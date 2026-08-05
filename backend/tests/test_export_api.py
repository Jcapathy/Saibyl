"""The export endpoint returns a file, or an error. Never "started" with neither.

The endpoint used to hand the work to `asyncio.create_task` behind a wrapper
that logged and swallowed every exception, and answer `{"status": "started"}`.
Two consequences, both tested here:

* a broken exporter reported success — the PDF path had been broken since
  `simulation_analytics` was refactored and this endpoint never noticed;
* a *working* exporter was still useless, because `run_export_report` returns
  the signed download URL and `create_task` discards the return value.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api import exports as exports_api
from app.core.auth import get_current_org
from app.main import create_app
from app.services.export.pdf_exporter import ExportError

ORG_ID = "org-1"
REPORT_ID = "report-1"
SIM_ID = "sim-1"


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, data):
        self._data = data

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def execute(self):
        return _Result(self._data)


class _Admin:
    def __init__(self, tables):
        self._tables = tables

    def table(self, name):
        return _Query(self._tables.get(name, []))


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(
        exports_api,
        "get_supabase_admin",
        lambda: _Admin(
            {
                "reports": [
                    {"id": REPORT_ID, "simulations": {"organization_id": ORG_ID}}
                ],
                "simulations": [{"id": SIM_ID}],
            }
        ),
    )
    app = create_app()
    app.dependency_overrides[get_current_org] = lambda: {"org_id": ORG_ID}
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_a_successful_export_returns_the_download_url(client, monkeypatch):
    async def _export(report_id, fmt):
        return {
            "report_id": report_id,
            "format": fmt,
            "status": "complete",
            "download_url": "https://storage.example/report.pdf?token=abc",
            "file_size_bytes": 94_023,
        }

    monkeypatch.setattr(exports_api, "run_export_report", _export)

    response = client.post(f"/api/reports/{REPORT_ID}/export", json={"format": "pdf"})
    assert response.status_code == 200
    body = response.json()
    assert body["download_url"].startswith("https://")
    assert body["file_size_bytes"] == 94_023
    assert body["status"] != "started", "'started' is not an outcome the caller can use"


def test_a_failed_export_is_a_500_with_a_reason(client, monkeypatch):
    async def _export(_report_id, _fmt):
        raise ExportError("PDF rendering produced 0 bytes")

    monkeypatch.setattr(exports_api, "run_export_report", _export)

    response = client.post(f"/api/reports/{REPORT_ID}/export", json={"format": "pdf"})
    assert response.status_code == 500
    assert "PDF rendering produced 0 bytes" in response.json()["detail"]


def test_an_unexpected_failure_is_still_a_500_not_a_success(client, monkeypatch):
    async def _export(_report_id, _fmt):
        raise KeyError("simulation_id")

    monkeypatch.setattr(exports_api, "run_export_report", _export)

    response = client.post(f"/api/reports/{REPORT_ID}/export", json={"format": "pdf"})
    assert response.status_code == 500


def test_a_file_with_no_signed_url_is_a_failure(client, monkeypatch):
    """Uploaded but unreachable is the same outcome, to the caller, as absent."""

    async def _export(_report_id, _fmt):
        return {"status": "complete", "download_url": "", "file_size_bytes": 94_023}

    monkeypatch.setattr(exports_api, "run_export_report", _export)

    response = client.post(f"/api/reports/{REPORT_ID}/export", json={"format": "pdf"})
    assert response.status_code == 500
    assert "download URL" in response.json()["detail"]


def test_an_unknown_format_is_rejected_before_any_work(client):
    response = client.post(f"/api/reports/{REPORT_ID}/export", json={"format": "docx"})
    assert response.status_code == 400


def test_another_org_report_is_not_found(client):
    client.app.dependency_overrides[get_current_org] = lambda: {"org_id": "other-org"}
    response = client.post(f"/api/reports/{REPORT_ID}/export", json={"format": "pdf"})
    assert response.status_code == 404


def test_simulation_export_returns_its_url(client, monkeypatch):
    async def _export(simulation_id):
        return {
            "simulation_id": simulation_id,
            "status": "complete",
            "download_url": "https://storage.example/simulation.json.gz",
            "file_size_bytes": 4_211,
        }

    monkeypatch.setattr(exports_api, "run_export_simulation", _export)

    response = client.post(f"/api/simulations/{SIM_ID}/export")
    assert response.status_code == 200
    assert response.json()["download_url"].endswith(".json.gz")
