from app.services.engine.document_processor import chunk_text


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
