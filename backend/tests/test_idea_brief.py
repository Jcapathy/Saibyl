"""A founder with only an idea gets the same pipeline as a founder with files.

PRD_V3 §3: the five-field guided form is composed into a markdown document and
stored through `store_upload`, so ingestion, the subject brief and audience
synthesis consume it unchanged. Three places have to agree for that to hold,
and these tests pin all three: the endpoint stores through the one upload path
with the `idea_brief` kind, the subject brief reads that kind as the founder's
own material, and `gather_material` buckets it with `own` — without dropping a
short brief below the source floor, which for an idea-stage project would
ground the synthesis in nothing at all.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api import documents as documents_api
from app.api.documents import DocumentUpdate, update_document
from app.core.auth import get_current_org
from app.services.engine.personas import icp_synthesizer as icp
from app.services.intelligence import subject_brief as sb

ORG = "11111111-1111-1111-1111-111111111111"
PROJECT = "33333333-3333-3333-3333-333333333333"

BRIEF = {
    "project_id": PROJECT,
    "problem": "Founders spend months building things nobody asked for.",
    "who": "A pre-seed founder with an idea and no customer conversations yet.",
    "solution": "A panel that argues with your pitch before real buyers do.",
    "alternatives": "Asking friends, posting on forums, or just building it.",
    "price": "Around $99 a month.",
}
ANSWERS = [v for k, v in BRIEF.items() if k != "project_id"]


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

@pytest.fixture
def authed_client(app):
    app.dependency_overrides[get_current_org] = lambda: {"org_id": ORG}
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_current_org, None)


def _capture_store_upload(monkeypatch) -> dict:
    """Swap `store_upload` for a recorder.

    The composition and the kind are this endpoint's whole job; validating,
    billing and queueing the result is `store_upload`'s, and it has its own
    coverage. Capturing the call asserts the former without faking storage.
    """
    captured: dict = {}

    async def fake_store_upload(**kwargs):
        captured.update(kwargs)
        return {"id": "doc-1", "material_kind": kwargs["material_kind"]}

    monkeypatch.setattr(documents_api, "store_upload", fake_store_upload)
    return captured


class _Query:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def execute(self):
        return SimpleNamespace(data=[dict(r) for r in self._rows])


class _Admin:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    def table(self, _name: str):
        return _Query(self._rows)


# ---------------------------------------------------------------------------
# The endpoint stores through the one upload path
# ---------------------------------------------------------------------------

def test_a_complete_brief_is_stored_through_the_upload_path(authed_client, monkeypatch):
    captured = _capture_store_upload(monkeypatch)

    response = authed_client.post("/api/documents/idea-brief", json=BRIEF)

    assert response.status_code == 200, response.text
    assert response.json()["material_kind"] == "idea_brief"
    assert captured["material_kind"] == "idea_brief"
    assert captured["project_id"] == PROJECT
    assert captured["org_id"] == ORG
    assert captured["file"].filename == "idea-brief.md"


def test_the_composed_markdown_carries_all_five_answers(authed_client, monkeypatch):
    captured = _capture_store_upload(monkeypatch)

    authed_client.post("/api/documents/idea-brief", json=BRIEF)

    text = captured["file"].file.read().decode("utf-8")
    for answer in ANSWERS:
        assert answer in text, f"missing answer: {answer}"
    for heading in (
        "## The problem",
        "## Who has it",
        "## The solution",
        "## What they use today",
        "## Rough price",
    ):
        assert heading in text, f"missing heading: {heading}"
    # The title is the first line of the solution — the closest thing an
    # idea-stage founder has to a product name.
    assert text.splitlines()[0] == f"# {BRIEF['solution']}"


@pytest.mark.parametrize("field", ["problem", "who", "solution", "alternatives", "price"])
def test_a_blank_answer_is_refused_and_nothing_is_stored(authed_client, monkeypatch, field):
    """Whitespace strips to nothing: a form of five spaces is not a brief."""
    captured = _capture_store_upload(monkeypatch)

    response = authed_client.post("/api/documents/idea-brief", json={**BRIEF, field: "   "})

    assert response.status_code == 422, response.text
    assert not captured, "a blank answer reached store_upload"


def test_an_answer_over_the_cap_is_refused(authed_client, monkeypatch):
    captured = _capture_store_upload(monkeypatch)

    response = authed_client.post(
        "/api/documents/idea-brief", json={**BRIEF, "problem": "x" * 2001}
    )

    assert response.status_code == 422, response.text
    assert not captured


def test_the_route_requires_an_organisation(app, monkeypatch):
    """No dependency override: unauthenticated must not compose or store."""
    captured = _capture_store_upload(monkeypatch)

    response = TestClient(app).post("/api/documents/idea-brief", json=BRIEF)

    assert response.status_code in (401, 403), response.text
    assert not captured


# ---------------------------------------------------------------------------
# An idea brief's kind records provenance, and provenance is not correctable
# ---------------------------------------------------------------------------

async def test_an_idea_brief_cannot_be_relabelled(monkeypatch):
    """The PATCH route's Literal refuses relabelling *to* idea_brief; this pins
    the other direction. Generated form text must never acquire the standing
    of an uploaded competitor or market document."""
    monkeypatch.setattr(
        documents_api,
        "get_supabase_admin",
        lambda: _Admin([{
            "id": "d1",
            "organization_id": ORG,
            "project_id": PROJECT,
            "material_kind": "idea_brief",
        }]),
    )

    with pytest.raises(HTTPException) as exc:
        await update_document(
            id="d1",
            body=DocumentUpdate(material_kind="competitor"),
            auth={"org_id": ORG},
        )

    assert exc.value.status_code == 409
    assert "idea brief" in exc.value.detail


# ---------------------------------------------------------------------------
# The subject brief reads an idea brief as the founder's own material
# ---------------------------------------------------------------------------

def test_an_idea_brief_is_subject_material():
    assert "idea_brief" in sb._SUBJECT_MATERIAL_KINDS


def test_a_processed_idea_brief_row_is_usable_as_the_subject():
    rows = [{"id": "d1", "material_kind": "idea_brief", "processing_status": "complete"}]
    assert [d["id"] for d in sb._subject_material_rows(rows)] == ["d1"]


def test_an_unprocessed_idea_brief_is_not_yet_the_subject():
    """Same rule as every other kind: only a completed extraction counts."""
    rows = [{"id": "d1", "material_kind": "idea_brief", "processing_status": "pending"}]
    assert sb._subject_material_rows(rows) == []


# ---------------------------------------------------------------------------
# gather_material buckets an idea brief with `own`
# ---------------------------------------------------------------------------

def _idea_brief_row(**overrides) -> dict:
    row = {
        "id": "d1",
        "filename": "idea-brief.md",
        "file_type": "md",
        "media_type": "document",
        "storage_path": f"{ORG}/{PROJECT}/d1_idea-brief.md",
        "processed_text_path": f"{ORG}/{PROJECT}/d1_idea-brief.txt",
        "extracted_char_count": 400,
        "material_kind": "idea_brief",
        "material_kind_suggested": None,
        "processing_status": "complete",
    }
    row.update(overrides)
    return row


def test_gather_material_buckets_an_idea_brief_with_own(monkeypatch):
    """400 characters on purpose: below `_MIN_SOURCE_CHARS`.

    The floor exists to drop a fragment of a big upload that would arrive as
    noise. An idea brief is short because the form is short, and for an
    idea-stage project it is the *only* material — excluded, the synthesis
    would run on nothing while the founder believes their form was heard.
    """
    monkeypatch.setattr(icp, "get_supabase_admin", lambda: _Admin([_idea_brief_row()]))
    monkeypatch.setattr(
        icp, "source_text", lambda _admin, _doc: "The founder's own idea, in brief."
    )

    material = icp.gather_material(PROJECT)

    assert material.own_ids == ["d1"]
    assert "The founder's own idea" in material.own
    assert material.competitor_ids == []
    assert material.market_ids == []
    assert material.excluded == []


def test_an_unprocessed_idea_brief_is_excluded_by_name(monkeypatch):
    """The one-upload-surface rule: nothing is dropped with a bare continue."""
    monkeypatch.setattr(
        icp,
        "get_supabase_admin",
        lambda: _Admin([_idea_brief_row(processing_status="pending")]),
    )

    material = icp.gather_material(PROJECT)

    assert material.own_ids == []
    assert [e["document_id"] for e in material.excluded] == ["d1"]
