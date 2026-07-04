"""Tests for the document ingestion pipeline (RAG grounding)."""
from __future__ import annotations

from pathlib import Path

import pytest

from aios.memory.doc_ingest import DocumentIngestor, chunk_text, extract_text
from aios.memory.db import get_connection, init_memory_db


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "test.db"
    init_memory_db(db_path)
    return db_path


@pytest.fixture
def ingestor(tmp_db: Path) -> DocumentIngestor:
    return DocumentIngestor(db_path=tmp_db)


class TestChunkText:
    def test_empty_text_returns_empty(self):
        assert chunk_text("") == []
        assert chunk_text("   ") == []

    def test_short_text_single_chunk(self):
        chunks = chunk_text("hello world", max_tokens=10)
        assert len(chunks) == 1
        assert chunks[0].text == "hello world"
        assert chunks[0].index == 0

    def test_overlap_creates_expected_chunks(self):
        words = " ".join(f"w{i}" for i in range(20))
        chunks = chunk_text(words, max_tokens=10, overlap_tokens=3)
        assert len(chunks) >= 2
        assert chunks[0].index == 0
        assert chunks[1].index == 1
        first_words = set(chunks[0].text.split())
        second_words = set(chunks[1].text.split())
        assert first_words & second_words

    def test_all_words_covered(self):
        text = " ".join(f"word{i}" for i in range(50))
        chunks = chunk_text(text, max_tokens=10, overlap_tokens=2)
        all_chunk_words = set()
        for c in chunks:
            all_chunk_words.update(c.text.split())
        original_words = set(text.split())
        assert original_words == all_chunk_words


class TestExtractText:
    def test_plain_text(self):
        raw = b"Hello, this is plain text."
        result = extract_text("test.txt", raw, "text/plain")
        assert result == "Hello, this is plain text."

    def test_markdown(self):
        raw = b"# Title\n\nContent here."
        result = extract_text("doc.md", raw, "text/markdown")
        assert "Title" in result
        assert "Content" in result

    def test_unsupported_type_raises(self):
        with pytest.raises(ValueError, match="Unsupported"):
            extract_text("image.png", b"\x89PNG", "image/png")

    def test_utf8_decode_errors_replaced(self):
        raw = b"Hello \xff world"
        result = extract_text("bad.txt", raw, "text/plain")
        assert "Hello" in result
        assert "world" in result


class TestDocumentIngestor:
    def test_ingest_plain_text(self, ingestor: DocumentIngestor, tmp_db: Path):
        content = "This is a test document with enough words to verify chunking works properly."
        result = ingestor.ingest("test.txt", content.encode(), "text/plain")
        assert result["filename"] == "test.txt"
        assert result["chunks"] >= 1
        assert result["duplicate"] is False
        assert "source_id" in result

    def test_ingest_duplicate_detected(self, ingestor: DocumentIngestor):
        content = b"Exact same content here."
        ingestor.ingest("first.txt", content, "text/plain")
        result = ingestor.ingest("second.txt", content, "text/plain")
        assert result["duplicate"] is True

    def test_ingest_empty_text_raises(self, ingestor: DocumentIngestor):
        with pytest.raises(ValueError, match="no extractable text"):
            ingestor.ingest("empty.txt", b"   ", "text/plain")

    def test_ingest_too_large_raises(self, ingestor: DocumentIngestor):
        huge = b"x" * 11_000_000
        with pytest.raises(ValueError, match="too large"):
            ingestor.ingest("big.txt", huge, "text/plain")

    def test_list_sources(self, ingestor: DocumentIngestor):
        ingestor.ingest("a.txt", b"Document A content", "text/plain")
        ingestor.ingest("b.txt", b"Document B content", "text/plain")
        sources = ingestor.list_sources()
        assert len(sources) == 2
        filenames = {s["filename"] for s in sources}
        assert filenames == {"a.txt", "b.txt"}

    def test_delete_source(self, ingestor: DocumentIngestor, tmp_db: Path):
        result = ingestor.ingest("del.txt", b"Delete me please", "text/plain")
        source_id = result["source_id"]
        assert ingestor.delete_source(source_id) is True
        assert ingestor.list_sources() == []
        with get_connection(tmp_db) as conn:
            chunks = conn.execute(
                "SELECT COUNT(*) FROM knowledge_chunks WHERE source_id = ?",
                (source_id,),
            ).fetchone()[0]
        assert chunks == 0

    def test_delete_nonexistent_returns_false(self, ingestor: DocumentIngestor):
        assert ingestor.delete_source(999) is False

    def test_search_chunks(self, ingestor: DocumentIngestor):
        ingestor.ingest(
            "search.txt",
            b"The quick brown fox jumps over the lazy dog",
            "text/plain",
        )
        results = ingestor.search_chunks("quick fox")
        assert len(results) >= 1
        assert "quick" in results[0].lower() or "fox" in results[0].lower()

    def test_search_chunks_no_match(self, ingestor: DocumentIngestor):
        ingestor.ingest("doc.txt", b"hello world", "text/plain")
        results = ingestor.search_chunks("zzzznonexistent")
        assert results == []


class TestKnowledgeEndpoint:
    """Integration test for the API endpoint shape (import-level)."""

    def test_ingest_endpoint_exists(self):
        from aios.api.main import app

        routes = [r.path for r in app.routes]
        assert "/api/v1/knowledge/ingest" in routes
        assert "/api/v1/knowledge/sources" in routes
        assert "/api/v1/knowledge/sources/{source_id}" in routes
