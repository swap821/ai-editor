"""GAGOS's own documents in its knowledge base (2026-11-13).

Move C on the aliveness map, at the operator's word ("GAGOS's own docs"): the
knowledge base the counter's corrective retrieval reads had only an upload
door, never used. GAGOS now keeps its README, AGENTS.md, HONEST_STATE.md and
architecture docs there, current with its checkout, and never touches what the
operator uploads.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aios.memory import self_knowledge
from aios.memory.doc_ingest import DocumentIngestor


@pytest.fixture()
def ingestor(tmp_path) -> DocumentIngestor:
    return DocumentIngestor(db_path=tmp_path / "memory.db")


@pytest.fixture()
def checkout(tmp_path) -> Path:
    root = tmp_path / "checkout"
    (root / "docs" / "architecture").mkdir(parents=True)
    (root / "README.md").write_text(
        "GAGOS is the operator's AI-OS.\n", encoding="utf-8"
    )
    (root / "AGENTS.md").write_text(
        "The frozen core is never agent-applied.\n", encoding="utf-8"
    )
    (root / "HONEST_STATE.md").write_text(
        "The envelope was signed today.\n", encoding="utf-8"
    )
    (root / "docs" / "architecture" / "AUTHORITY_MAP.md").write_text(
        "Organ 9 issues the envelope capability.\n", encoding="utf-8"
    )
    (root / "docs" / "architecture" / "notes.txt").write_text(
        "not markdown\n", encoding="utf-8"
    )
    (root / "secret.md").write_text("never a self document\n", encoding="utf-8")
    return root


def _names(ingestor) -> set[str]:
    return {s["filename"] for s in ingestor.list_sources()}


def test_gagoss_documents_are_kept_and_nothing_else(checkout, ingestor) -> None:
    out = self_knowledge.refresh(checkout, ingestor=ingestor)
    assert sorted(out["changed"]) == [
        "AGENTS.md",
        "HONEST_STATE.md",
        "README.md",
        "docs/architecture/AUTHORITY_MAP.md",
    ]
    assert _names(ingestor) == {self_knowledge.PREFIX + rel for rel in out["changed"]}
    assert ingestor.search_chunks("capability") == [
        "Organ 9 issues the envelope capability."
    ]


def test_a_second_hour_changes_nothing_that_did_not_change(checkout, ingestor) -> None:
    self_knowledge.refresh(checkout, ingestor=ingestor)
    before = ingestor.list_sources()
    out = self_knowledge.refresh(checkout, ingestor=ingestor)
    assert out["changed"] == [] and len(out["kept"]) == 4
    assert ingestor.list_sources() == before


def test_a_changed_document_replaces_its_old_text(checkout, ingestor) -> None:
    self_knowledge.refresh(checkout, ingestor=ingestor)
    (checkout / "HONEST_STATE.md").write_text(
        "A mission ran today.\n", encoding="utf-8"
    )
    out = self_knowledge.refresh(checkout, ingestor=ingestor)
    assert out["changed"] == ["HONEST_STATE.md"]
    assert ingestor.search_chunks("signed") == []
    assert ingestor.search_chunks("mission") == ["A mission ran today."]
    assert len([n for n in _names(ingestor) if n.endswith("HONEST_STATE.md")]) == 1


def test_a_document_that_is_gone_is_taken_out(checkout, ingestor) -> None:
    self_knowledge.refresh(checkout, ingestor=ingestor)
    (checkout / "docs" / "architecture" / "AUTHORITY_MAP.md").unlink()
    out = self_knowledge.refresh(checkout, ingestor=ingestor)
    assert out["removed"] == ["docs/architecture/AUTHORITY_MAP.md"]
    assert ingestor.search_chunks("capability") == []


def test_the_operators_own_uploads_are_never_touched(checkout, ingestor) -> None:
    ingestor.ingest("my-notes.md", b"The operator's own notes.\n", "text/markdown")
    self_knowledge.refresh(checkout, ingestor=ingestor)
    (checkout / "README.md").unlink()
    self_knowledge.refresh(checkout, ingestor=ingestor)
    assert "my-notes.md" in _names(ingestor)
    assert ingestor.search_chunks("notes") == ["The operator's own notes."]


def test_the_counters_retrieval_reads_gagoss_documents(
    checkout, ingestor, monkeypatch
) -> None:
    from aios.api import turn_pipeline
    from aios.memory import doc_ingest

    self_knowledge.refresh(checkout, ingestor=ingestor)
    monkeypatch.setattr(doc_ingest, "DocumentIngestor", lambda: ingestor)
    assert turn_pipeline._crag_document_source("which organ issues capability") == [
        "Organ 9 issues the envelope capability."
    ]


def test_the_hour_refreshes_and_says_so(checkout, ingestor, capsys) -> None:
    from tools import gagos_daily as tool

    tool.knowledge_hour(checkout, ingestor=ingestor)
    assert "4 of GAGOS's documents in its knowledge base (4 changed, 0 removed)" in (
        capsys.readouterr().out
    )
