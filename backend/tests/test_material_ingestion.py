"""Every kind of upload reaches ICP synthesis, and a guess never labels one.

Two claims are tested here, and both were false before this work.

**Every upload kind is visible to `gather_material`.** Images, video,
spreadsheets, decks and linked articles went to `project_assets`, which
`gather_material` never read. The file uploaded, the processor ran, the text was
written — and the audience was synthesized as if none of it had been sent, with
nothing in any log saying so.

**An auto-classification never licenses a competitor name.** DECISIONS_V2 §7:
an unlabelled document cannot authorise naming a competitor, and the classifier
added in this work proposes only. If a suggestion could reach
`ProjectMaterial.competitor_ids`, a cheap model's guess would license a named
comparison a founder could publish.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
import structlog

from app.services.engine.personas import icp_synthesizer
from app.services.engine.personas.icp_synthesizer import ProjectMaterial, gather_material
from app.services.ingestion.media_types import (
    ALL_EXTENSIONS,
    EXTENSIONS_BY_MEDIA_TYPE,
    MEDIA_TYPES,
    extension_of,
    max_upload_bytes,
    media_type_for_extension,
)

PROJECT = "33333333-3333-3333-3333-333333333333"


# ---------------------------------------------------------------------------
# A Supabase stand-in
# ---------------------------------------------------------------------------

class _FakeQuery:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, *_args):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def execute(self):
        return SimpleNamespace(data=list(self._rows))


class _FakeBucket:
    def __init__(self, objects: dict[str, str]):
        self._objects = objects
        self.downloads: list[str] = []

    def download(self, path: str) -> bytes:
        self.downloads.append(path)
        if path not in self._objects:
            raise FileNotFoundError(path)
        return self._objects[path].encode("utf-8")


class _FakeStorage:
    def __init__(self, bucket: _FakeBucket):
        self._bucket = bucket

    def from_(self, _name: str) -> _FakeBucket:
        return self._bucket


class _FakeAdmin:
    def __init__(self, rows: list[dict], objects: dict[str, str]):
        self._rows = rows
        self.bucket = _FakeBucket(objects)
        self.storage = _FakeStorage(self.bucket)

    def table(self, name: str) -> _FakeQuery:
        assert name == "documents", f"gather_material queried {name!r}"
        return _FakeQuery(self._rows)


def _row(doc_id: str, media_type: str, filename: str, chars: int, **overrides) -> dict:
    row = {
        "id": doc_id,
        "filename": filename,
        "file_type": filename.rsplit(".", 1)[-1],
        "media_type": media_type,
        "storage_path": f"org/proj/{filename}",
        "processed_text_path": f"org/proj/{filename}_extracted.txt",
        "extracted_char_count": chars,
        "material_kind": "own",
        "material_kind_suggested": None,
        "processing_status": "complete",
    }
    row.update(overrides)
    return row


def _install(monkeypatch, rows: list[dict], objects: dict[str, str]) -> _FakeAdmin:
    admin = _FakeAdmin(rows, objects)
    monkeypatch.setattr(icp_synthesizer, "get_supabase_admin", lambda: admin)
    return admin


# ---------------------------------------------------------------------------
# The media-type table
# ---------------------------------------------------------------------------

def test_every_media_type_has_at_least_one_extension():
    assert set(EXTENSIONS_BY_MEDIA_TYPE) == set(MEDIA_TYPES)
    for media_type, exts in EXTENSIONS_BY_MEDIA_TYPE.items():
        assert exts, f"{media_type} maps to no extension"


def test_no_extension_is_claimed_by_two_media_types():
    """Two claims on one extension makes the dispatch order-dependent."""
    seen: dict[str, str] = {}
    for media_type, exts in EXTENSIONS_BY_MEDIA_TYPE.items():
        for ext in exts:
            assert ext not in seen, f"{ext} claimed by {seen.get(ext)} and {media_type}"
            seen[ext] = media_type


def test_every_allowed_extension_resolves_to_a_processor():
    """The upload route accepts `ALL_EXTENSIONS`; each must have a reader."""
    for ext in ALL_EXTENSIONS:
        assert media_type_for_extension(ext) is not None, ext


def test_an_unmapped_extension_is_a_miss_not_a_document():
    """A default here would file an unreadable file as a processed document."""
    assert media_type_for_extension("key") is None
    assert media_type_for_extension("") is None
    assert media_type_for_extension(None) is None


@pytest.mark.parametrize(
    ("filename", "expected"),
    [("deck.PPTX", "pptx"), ("a.b.csv", "csv"), ("noext", ""), (None, "")],
)
def test_extension_of(filename, expected):
    assert extension_of(filename) == expected


def test_every_media_type_has_a_size_ceiling():
    for media_type in MEDIA_TYPES:
        assert max_upload_bytes(media_type) > 0


# ---------------------------------------------------------------------------
# Every upload kind reaches gather_material
# ---------------------------------------------------------------------------

_ALL_KINDS = [
    ("document", "prd.pdf"),
    ("presentation", "deck.pptx"),
    ("image", "slide-3.png"),
    ("video", "demo.mp4"),
    ("spreadsheet", "customers.csv"),
    ("news_article", "coverage.html"),
]


def test_every_upload_kind_reaches_gather_material(monkeypatch):
    """The whole point of the change, asserted per media type.

    A regression here does not raise and does not log: the ICP is simply
    synthesized from less material than the founder uploaded.
    """
    rows = [
        _row(f"doc-{i}", media_type, filename, 2_000)
        for i, (media_type, filename) in enumerate(_ALL_KINDS)
    ]
    objects = {
        row["processed_text_path"]: f"CONTENT OF {row['filename']} " + "x" * 2_000
        for row in rows
    }
    _install(monkeypatch, rows, objects)

    with structlog.testing.capture_logs() as logs:
        material = gather_material(PROJECT)

    for media_type, filename in _ALL_KINDS:
        assert filename in material.own, f"{media_type} did not reach the synthesis pass"
        assert f"({media_type})" in material.own, f"{media_type} not declared to the model"

    assert len(material.own_ids) == len(_ALL_KINDS)
    assert material.excluded == []

    gathered = next(entry for entry in logs if entry["event"] == "icp_material_gathered")
    assert set(gathered["chars_by_media_type"]) == {m for m, _ in _ALL_KINDS}
    assert all(count > 0 for count in gathered["chars_by_media_type"].values())


def test_a_source_that_contributes_nothing_is_named_and_logged(monkeypatch):
    """The governing defect: zero characters that read as success.

    Sixty market documents cannot each get a usable slice of a 6,000-character
    bucket. The ones left out are returned by name with a reason and reported at
    warning — the previous version dropped them with a bare `continue`.
    """
    rows = [_row(f"doc-{i}", "document", f"paper-{i}.pdf", 5_000, material_kind="market")
            for i in range(60)]
    objects = {row["processed_text_path"]: "y" * 5_000 for row in rows}
    _install(monkeypatch, rows, objects)

    with structlog.testing.capture_logs() as logs:
        material = gather_material(PROJECT)

    assert material.excluded, "every source was silently included or silently dropped"
    assert len(material.market_ids) + len(material.excluded) == 60
    excluded_event = next(entry for entry in logs if entry["event"] == "icp_material_excluded")
    assert excluded_event["count"] == len(material.excluded)
    assert all("filename" in item and "reason" in item for item in material.excluded)

    # The bucket must still contribute. Excluding *everything* because no source
    # clears the floor would be the same zero-characters defect in a new shape.
    assert material.market_ids, "the whole market bucket contributed nothing"
    assert len(material.market) >= 6_000 - len(material.market_ids) * 40


def test_the_budget_is_shared_so_a_large_upload_cannot_starve_a_small_one(monkeypatch):
    """First-come-first-served let one CRM export consume the whole bucket."""
    rows = [
        _row("huge", "spreadsheet", "crm-export.csv", 500_000),
        _row("small", "document", "landing-page.md", 3_000),
    ]
    objects = {
        rows[0]["processed_text_path"]: "a" * 500_000,
        rows[1]["processed_text_path"]: "b" * 3_000,
    }
    _install(monkeypatch, rows, objects)

    material = gather_material(PROJECT)

    assert material.own_ids == ["huge", "small"]
    assert "b" * 3_000 in material.own, "the small source was truncated by the large one"


def test_truncation_is_declared_to_the_model_and_logged(monkeypatch):
    rows = [_row("big", "document", "prd.pdf", 100_000)]
    objects = {rows[0]["processed_text_path"]: "z" * 100_000}
    _install(monkeypatch, rows, objects)

    with structlog.testing.capture_logs() as logs:
        material = gather_material(PROJECT)

    included = next(e for e in logs if e["event"] == "icp_material_source_included")
    assert included["truncated"] is True
    assert included["included_chars"] < included["available_chars"]
    assert "of 100000 characters" in material.own


def test_an_unprocessed_document_is_excluded_with_its_status(monkeypatch):
    rows = [
        _row("ok", "document", "prd.pdf", 2_000),
        _row("bad", "video", "demo.mp4", 0, processing_status="failed"),
        _row("waiting", "image", "slide.png", 0, processing_status="pending"),
    ]
    objects = {rows[0]["processed_text_path"]: "c" * 2_000}
    _install(monkeypatch, rows, objects)

    material = gather_material(PROJECT)

    reasons = {item["document_id"]: item["reason"] for item in material.excluded}
    assert reasons["bad"] == "processing_status=failed"
    assert reasons["waiting"] == "processing_status=pending"
    assert material.own_ids == ["ok"]


def test_a_row_with_no_extracted_text_falls_back_and_says_so(monkeypatch):
    """Documents uploaded before the pipeline existed still contribute."""
    rows = [_row("legacy", "document", "old.pdf", None, processed_text_path=None,
                 extracted_char_count=None)]
    objects = {"org/proj/old.pdf": "RAW BYTES"}
    _install(monkeypatch, rows, objects)
    monkeypatch.setattr(
        "app.services.engine.document_processor._extract_text",
        lambda file_bytes, file_type: ("legacy extracted text", "utf-8", None),
    )

    with structlog.testing.capture_logs() as logs:
        material = gather_material(PROJECT)

    assert "legacy extracted text" in material.own
    assert any(entry["event"] == "icp_material_legacy_extraction" for entry in logs)


def test_a_failed_read_is_recorded_rather_than_skipped(monkeypatch):
    rows = [_row("gone", "document", "prd.pdf", 2_000)]
    _install(monkeypatch, rows, {})  # storage object missing

    with structlog.testing.capture_logs() as logs:
        material = gather_material(PROJECT)

    assert material.own_ids == []
    assert material.excluded[0]["document_id"] == "gone"
    assert "read failed" in material.excluded[0]["reason"]
    assert any(entry["event"] == "icp_material_read_failed" for entry in logs)


# ---------------------------------------------------------------------------
# DECISIONS §7 — a suggestion is not a label
# ---------------------------------------------------------------------------

def test_a_suggested_competitor_is_not_bucketed_as_competitor(monkeypatch):
    """The guardrail, at the only place it can be enforced in data.

    `competitor_ids` is the licence to name a company. A classifier's proposal
    must not reach it, at any confidence.
    """
    rows = [
        _row("rival", "document", "rival-pricing.pdf", 4_000,
             material_kind=None, material_kind_suggested="competitor"),
    ]
    objects = {rows[0]["processed_text_path"]: "Their pricing page. " * 200}
    _install(monkeypatch, rows, objects)

    with structlog.testing.capture_logs() as logs:
        material = gather_material(PROJECT)

    assert material.competitor_ids == []
    assert material.has_competitor_material is False
    assert material.own_ids == ["rival"], "an unlabelled document reads as 'own'"
    assert material.unconfirmed_competitor_ids == ["rival"]
    # Reported, because "nobody confirmed the competitor material" and "there is
    # no competitor material" are otherwise the same observation.
    assert any(
        entry["event"] == "icp_competitor_material_unconfirmed" for entry in logs
    )


def test_a_human_label_still_buckets_as_competitor(monkeypatch):
    """The confirmation path works — the guardrail is not a blanket refusal."""
    rows = [
        _row("rival", "document", "rival-pricing.pdf", 4_000,
             material_kind="competitor", material_kind_suggested="competitor"),
    ]
    objects = {rows[0]["processed_text_path"]: "Their pricing page. " * 200}
    _install(monkeypatch, rows, objects)

    material = gather_material(PROJECT)

    assert material.competitor_ids == ["rival"]
    assert material.has_competitor_material is True
    assert material.unconfirmed_competitor_ids == []


def test_a_suggestion_alone_cannot_license_a_named_competitor(monkeypatch):
    """End to end: classifier proposes, the name is still stripped.

    This is the failure the guardrail exists for — a swarm of incumbent-aligned
    agents arguing against a *named real company* on the strength of a cheap
    model's guess about a file in the founder's upload folder.
    """
    rows = [
        _row("rival", "document", "rival-pricing.pdf", 4_000,
             material_kind=None, material_kind_suggested="competitor"),
    ]
    objects = {rows[0]["processed_text_path"]: "Datadog pricing. " * 200}
    _install(monkeypatch, rows, objects)
    material = gather_material(PROJECT)

    model_output = {
        "name": "x",
        "archetypes": [{"id": "a", "label": "Buyer", "role": "buyer", "weight": 1.0}],
        "adversarial": [{
            "id": "dd",
            "label": "Datadog power user",
            "role": "incumbent_power_user",
            "competitor_name": "Datadog",
            # The model cites the document the classifier flagged.
            "grounded_in": ["rival"],
            "talking_points": ["migration cost"],
        }],
    }
    profile = icp_synthesizer._build_profile(model_output, material, adversarial=True)

    assert profile.adversarial[0].competitor_name is None
    assert profile.adversarial[0].grounded_in == []
    # The cohort survives; only the unlicensed name went.
    assert profile.adversarial[0].talking_points == ["migration cost"]


def test_the_classifier_never_writes_material_kind(monkeypatch):
    """Asserted at the write site, not only at the read site.

    `ingest_document` is the one place a suggestion could be promoted to a
    label. It writes `material_kind_suggested` and must leave `material_kind`
    out of the payload entirely — an absent key cannot be a wrong value.
    """
    import asyncio

    from app.services.ingestion import classifier, pipeline
    from app.services.ingestion.classifier import MaterialSuggestion

    updates: list[dict] = []

    class _Table:
        def select(self, *_a, **_k):
            return self

        def eq(self, *_a):
            return self

        def single(self):
            return self

        def update(self, payload):
            updates.append(payload)
            return self

        def execute(self):
            return SimpleNamespace(data={
                "id": "doc-1",
                "project_id": PROJECT,
                "filename": "rival-pricing.pdf",
                "file_type": "pdf",
                "media_type": "document",
                "storage_path": "org/proj/rival.pdf",
                "material_kind": None,
            })

    class _Bucket:
        def download(self, _path):
            return b"whatever"

        def upload(self, *_a, **_k):
            return None

    class _Admin:
        storage = SimpleNamespace(from_=lambda _name: _Bucket())

        def table(self, _name):
            return _Table()

    monkeypatch.setattr(pipeline, "get_supabase_admin", _Admin)
    monkeypatch.setattr(
        "app.services.engine.document_processor._extract_text",
        lambda file_bytes, file_type: ("Their pricing page says $99." * 40, "utf-8", 1),
    )

    async def _suggest(_text, *, filename, media_type):
        return MaterialSuggestion(kind="competitor", confidence=0.99, rationale="theirs")

    monkeypatch.setattr(pipeline, "suggest_material_kind", _suggest)
    assert classifier.MATERIAL_KINDS == {"own", "competitor", "market"}

    asyncio.run(pipeline.ingest_document("doc-1"))

    final = updates[-1]
    assert final["material_kind_suggested"] == "competitor"
    assert final["material_kind_confidence"] == pytest.approx(0.99)
    assert "material_kind" not in final, (
        "ingest wrote material_kind — a model's guess would license a competitor name"
    )


# ---------------------------------------------------------------------------
# Fair-share allocation
# ---------------------------------------------------------------------------

def test_fair_share_gives_everything_when_the_budget_covers_it():
    assert icp_synthesizer._fair_share([100, 200], 1_000) == [100, 200]


def test_fair_share_splits_a_contested_budget_evenly():
    assert icp_synthesizer._fair_share([500, 500], 600) == [300, 300]


def test_fair_share_reallocates_what_a_small_source_does_not_need():
    # 1,000 to split: the 100-char source takes 100, the rest goes to the other.
    assert icp_synthesizer._fair_share([100, 5_000], 1_000) == [100, 900]


def test_fair_share_never_exceeds_the_budget():
    allocation = icp_synthesizer._fair_share([9_999] * 7, 1_000)
    assert sum(allocation) <= 1_000


# ---------------------------------------------------------------------------
# The deck
#
# A `.pptx` was accepted by both upload routes and readable by neither: the old
# dispatcher handed it to the DOCX extractor, which looks for a member no PPTX
# archive contains, and stored the literal "[Unable to extract text from this
# DOCX file]" as the deck's contribution to the ICP.
# ---------------------------------------------------------------------------

def _pptx(slides: list[tuple[str, str]]) -> bytes:
    """A minimal PPTX: [(slide text, speaker notes), ...]."""
    import io
    import zipfile

    ns = 'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for i, (body, notes) in enumerate(slides, start=1):
            runs = "".join(f"<a:t>{part}</a:t>" for part in body.split("|") if part)
            zf.writestr(f"ppt/slides/slide{i}.xml", f"<root {ns}>{runs}</root>")
            if notes:
                zf.writestr(
                    f"ppt/notesSlides/notesSlide{i}.xml",
                    f"<root {ns}><a:t>{notes}</a:t></root>",
                )
    return buffer.getvalue()


def test_a_deck_is_read_slide_by_slide():
    import asyncio

    from app.services.ingestion.presentation_processor import process_presentation

    result = asyncio.run(process_presentation(
        _pptx([("Series A pitch|We sell tracing", "Lead with the migration story"),
               ("Pricing|$99 per seat", "")]),
        "deck.pptx",
    ))

    text = result["extracted_text"]
    assert "Series A pitch" in text
    assert "$99 per seat" in text
    assert "Lead with the migration story" in text, "speaker notes were dropped"
    assert result["metadata"]["slides"] == 2


def test_slides_are_ordered_numerically_not_lexicographically():
    """`slide10` before `slide2` reorders the argument the deck is making."""
    import asyncio

    from app.services.ingestion.presentation_processor import process_presentation

    result = asyncio.run(process_presentation(
        _pptx([(f"slide-{i}-content", "") for i in range(1, 12)]), "deck.pptx"
    ))

    text = result["extracted_text"]
    assert text.index("slide-2-content") < text.index("slide-10-content")


def test_an_image_only_deck_fails_loudly_rather_than_extracting_nothing():
    """The exact failure this replaces: a `complete` document holding an error."""
    import asyncio

    from app.services.ingestion.presentation_processor import process_presentation

    with pytest.raises(ValueError, match="image-only deck"):
        asyncio.run(process_presentation(_pptx([("", ""), ("", "")]), "deck.pptx"))


def test_a_file_that_is_not_a_pptx_raises():
    import asyncio

    from app.services.ingestion.presentation_processor import process_presentation

    with pytest.raises(ValueError, match="readable PPTX"):
        asyncio.run(process_presentation(b"not a zip at all", "deck.pptx"))


# ---------------------------------------------------------------------------
# The classifier's misses
# ---------------------------------------------------------------------------

def test_classification_below_the_text_floor_is_a_recorded_absence(monkeypatch):
    import asyncio

    from app.services.ingestion.classifier import suggest_material_kind

    with structlog.testing.capture_logs() as logs:
        result = asyncio.run(
            suggest_material_kind("short", filename="x.txt", media_type="document")
        )

    assert result is None
    assert any(entry["event"] == "material_kind_not_classified" for entry in logs)


def test_a_kind_outside_the_vocabulary_is_a_miss_not_a_guess(monkeypatch):
    """An unrecognised value silently becoming `own` is the defect class."""
    import asyncio

    from app.services.ingestion import classifier

    async def _fake(*_a, **_k):
        return '{"kind": "rival-ish", "confidence": 0.9, "rationale": "hm"}'

    monkeypatch.setattr(classifier, "llm_fast", _fake)

    with structlog.testing.capture_logs() as logs:
        result = asyncio.run(classifier.suggest_material_kind(
            "x" * 500, filename="x.txt", media_type="document"
        ))

    assert result is None
    assert any(entry["event"] == "material_kind_unrecognised" for entry in logs)


def test_a_restated_kind_still_resolves(monkeypatch):
    import asyncio

    from app.services.ingestion import classifier

    async def _fake(*_a, **_k):
        return '{"kind": "[Competitor]", "confidence": 0.7, "rationale": "theirs"}'

    monkeypatch.setattr(classifier, "llm_fast", _fake)

    result = asyncio.run(classifier.suggest_material_kind(
        "x" * 500, filename="x.txt", media_type="document"
    ))

    assert result is not None
    assert result.kind == "competitor"
    assert result.confidence == pytest.approx(0.7)


def test_a_failed_classification_does_not_fail_the_upload(monkeypatch):
    import asyncio

    from app.services.ingestion import classifier

    async def _boom(*_a, **_k):
        raise RuntimeError("rate limited")

    monkeypatch.setattr(classifier, "llm_fast", _boom)

    with structlog.testing.capture_logs() as logs:
        result = asyncio.run(classifier.suggest_material_kind(
            "x" * 500, filename="x.txt", media_type="document"
        ))

    assert result is None
    failure = next(
        entry for entry in logs if entry["event"] == "material_kind_classification_failed"
    )
    assert failure["error_type"] == "RuntimeError"


# ---------------------------------------------------------------------------
# ProjectMaterial
# ---------------------------------------------------------------------------

def test_material_defaults_carry_no_unconfirmed_competitors():
    material = ProjectMaterial(own="a", own_ids=["1"])
    assert material.unconfirmed_competitor_ids == []
    assert material.excluded == []
    assert material.all_ids == ["1"]
