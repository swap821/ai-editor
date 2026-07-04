"""Document ingestion pipeline for grounding answers in user-uploaded docs.

Chunks uploaded documents (plain text, markdown, PDF) into sized fragments,
stores them in the knowledge tables, and exposes them as a CRAG external source
so the conversational endpoint can ground answers in user docs.

Privacy: ingested content stays local (SQLite + optional FAISS). The pipeline
never sends doc content to any external service.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from aios import config
from aios.memory.db import get_connection, init_memory_db


@dataclass(frozen=True)
class Chunk:
    """A sized fragment of a document."""

    text: str
    index: int
    source_offset: int


def chunk_text(
    text: str,
    *,
    max_tokens: int = 300,
    overlap_tokens: int = 40,
) -> list[Chunk]:
    """Split *text* into overlapping chunks of approximately *max_tokens* words.

    Uses whitespace tokenisation (word count) as a cheap proxy for token count.
    Overlap ensures continuity across chunk boundaries.
    """
    words = text.split()
    if not words:
        return []

    chunks: list[Chunk] = []
    start = 0
    idx = 0
    while start < len(words):
        end = min(start + max_tokens, len(words))
        chunk_words = words[start:end]
        chunk_text = " ".join(chunk_words)
        source_offset = len(" ".join(words[:start]))
        chunks.append(Chunk(text=chunk_text, index=idx, source_offset=source_offset))
        idx += 1
        step = max_tokens - overlap_tokens
        if step <= 0:
            step = max_tokens
        start += step
    return chunks


def extract_text(filename: str, raw: bytes, mime_type: str) -> str:
    """Extract plain text from an uploaded file.

    Supports:
      - text/plain, text/markdown: decode as UTF-8
      - application/pdf: extract via pypdf (optional dependency)

    Raises ValueError for unsupported types.
    """
    if mime_type in ("text/plain", "text/markdown", "text/x-markdown"):
        return raw.decode("utf-8", errors="replace")

    if mime_type == "application/pdf" or filename.lower().endswith(".pdf"):
        try:
            from pypdf import PdfReader  # type: ignore[import-untyped]
        except ImportError as e:
            raise ValueError(
                "PDF ingestion requires the 'pypdf' package. "
                "Install with: pip install pypdf"
            ) from e
        import io

        reader = PdfReader(io.BytesIO(raw))
        pages: list[str] = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                pages.append(page_text)
        return "\n\n".join(pages)

    raise ValueError(f"Unsupported document type: {mime_type} ({filename})")


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class DocumentIngestor:
    """Manages document ingestion into the knowledge tables."""

    def __init__(self, db_path: Path = config.MEMORY_DB_PATH) -> None:
        self.db_path = db_path

    def ingest(
        self,
        filename: str,
        raw: bytes,
        mime_type: str,
    ) -> dict[str, Any]:
        """Ingest a document: extract text, chunk, and store.

        Returns metadata about the ingested source.
        """
        if len(raw) > config.KNOWLEDGE_MAX_UPLOAD_BYTES:
            raise ValueError(
                f"File too large: {len(raw)} bytes "
                f"(max {config.KNOWLEDGE_MAX_UPLOAD_BYTES})"
            )

        text = extract_text(filename, raw, mime_type)
        if not text.strip():
            raise ValueError("Document contains no extractable text")

        doc_hash = _content_hash(text)
        chunks = chunk_text(
            text,
            max_tokens=config.KNOWLEDGE_CHUNK_MAX_TOKENS,
            overlap_tokens=config.KNOWLEDGE_CHUNK_OVERLAP_TOKENS,
        )

        init_memory_db(self.db_path)
        with get_connection(self.db_path) as conn:
            # Check for duplicate
            existing = conn.execute(
                "SELECT id FROM knowledge_sources WHERE content_hash = ?",
                (doc_hash,),
            ).fetchone()
            if existing:
                return {
                    "source_id": existing["id"],
                    "filename": filename,
                    "chunks": 0,
                    "duplicate": True,
                }

            now = datetime.now(timezone.utc).isoformat()
            cursor = conn.execute(
                "INSERT INTO knowledge_sources "
                "(filename, mime_type, content_hash, chunk_count, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (filename, mime_type, doc_hash, len(chunks), now),
            )
            source_id = cursor.lastrowid

            for chunk in chunks:
                conn.execute(
                    "INSERT INTO knowledge_chunks "
                    "(source_id, chunk_index, text_content, source_offset) "
                    "VALUES (?, ?, ?, ?)",
                    (source_id, chunk.index, chunk.text, chunk.source_offset),
                )

        return {
            "source_id": source_id,
            "filename": filename,
            "chunks": len(chunks),
            "duplicate": False,
        }

    def list_sources(self) -> list[dict[str, Any]]:
        """List all ingested document sources."""
        init_memory_db(self.db_path)
        with get_connection(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, filename, mime_type, chunk_count, created_at "
                "FROM knowledge_sources ORDER BY id DESC"
            ).fetchall()
        return [
            {
                "id": row["id"],
                "filename": row["filename"],
                "mime_type": row["mime_type"],
                "chunk_count": row["chunk_count"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def delete_source(self, source_id: int) -> bool:
        """Delete a knowledge source and its chunks. Returns True if found."""
        init_memory_db(self.db_path)
        with get_connection(self.db_path) as conn:
            existing = conn.execute(
                "SELECT id FROM knowledge_sources WHERE id = ?", (source_id,)
            ).fetchone()
            if not existing:
                return False
            conn.execute(
                "DELETE FROM knowledge_chunks WHERE source_id = ?", (source_id,)
            )
            conn.execute(
                "DELETE FROM knowledge_sources WHERE id = ?", (source_id,)
            )
        return True

    def search_chunks(self, query: str, *, limit: int = 5) -> list[str]:
        """Simple keyword search over knowledge chunks for CRAG integration.

        Uses a basic LIKE query across chunk text. A future version could use
        FAISS vector search on chunk embeddings.
        """
        init_memory_db(self.db_path)
        keywords = [w for w in query.lower().split() if len(w) > 2]
        if not keywords:
            return []

        conditions = " OR ".join(
            "LOWER(text_content) LIKE ?" for _ in keywords
        )
        params = [f"%{kw}%" for kw in keywords[:5]]

        with get_connection(self.db_path) as conn:
            rows = conn.execute(
                f"SELECT text_content FROM knowledge_chunks "  # noqa: S608
                f"WHERE {conditions} LIMIT ?",
                (*params, limit),
            ).fetchall()
        return [row["text_content"] for row in rows]
