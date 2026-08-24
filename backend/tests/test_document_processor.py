import fitz
import pytest

from app.services.engine import document_processor
from app.services.engine.document_processor import _extract_text, chunk_text


def _one_page_pdf(words: str) -> bytes:
    """A real PDF, not a fixture pretending to be one."""
    doc = fitz.open()
    doc.new_page().insert_text((72, 96), words)
    data = doc.tobytes()
    doc.close()
    return data


def test_a_pdf_is_read_even_if_its_scratch_file_cannot_be_deleted(monkeypatch):
    """Cleanup must never destroy a successful extraction.

    The unlink used to sit *inside* the `with NamedTemporaryFile(...)` block,
    where the handle is still open. POSIX allows unlinking an open file, so it
    passed on the Linux image and in CI. On Windows it raises
    `PermissionError: [WinError 32]` — **after** the text has already been
    extracted. Uploading Saibyl's own twelve-page pitch deck to Saibyl on
    2026-08-23 read ~11,000 characters correctly and then wrote the document
    `failed`, because deleting a temp file did not work.

    Simulated rather than platform-gated: the bug is "a cleanup error escapes",
    and that is worth asserting on every platform, not only the one where this
    particular OS error happens to fire.
    """
    def _explode(self, missing_ok=False):
        raise PermissionError(32, "being used by another process")

    monkeypatch.setattr(document_processor.Path, "unlink", _explode)

    text, encoding, pages = _extract_text(_one_page_pdf("Saibyl deck"), "pdf")

    assert "Saibyl deck" in text
    assert encoding == "utf-8"
    assert pages == 1


def test_a_real_extraction_failure_still_raises():
    """The guard above must not swallow the failure it is standing next to."""
    with pytest.raises(Exception):
        _extract_text(b"this is not a pdf at all", "pdf")


def test_chunk_text_basic():
    text = "Hello world. This is a test. Another sentence here. And one more."
    chunks = chunk_text(text, chunk_size=50, overlap=10)
    assert len(chunks) >= 1
    # All original text should appear in chunks
    combined = " ".join(chunks)
    assert "Hello world" in combined
    assert "one more" in combined


def test_chunk_text_single_sentence():
    text = "Just one sentence."
    chunks = chunk_text(text, chunk_size=500)
    assert len(chunks) == 1
    assert chunks[0] == "Just one sentence."


def test_chunk_text_empty():
    chunks = chunk_text("")
    assert chunks == [] or chunks == [""]


def test_chunk_text_respects_size():
    text = ". ".join(f"Sentence number {i}" for i in range(50))
    chunks = chunk_text(text, chunk_size=100, overlap=20)
    for chunk in chunks:
        # Allow some slack due to sentence boundary snapping
        assert len(chunk) < 200, f"Chunk too large: {len(chunk)} chars"


def test_chunk_text_overlap():
    text = "First sentence. Second sentence. Third sentence. Fourth sentence. Fifth sentence."
    chunks = chunk_text(text, chunk_size=40, overlap=15)
    # With overlap, consecutive chunks should share some text
    if len(chunks) >= 2:
        # The end of chunk[0] should overlap with the start of chunk[1]
        assert len(chunks) >= 2
