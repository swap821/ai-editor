"""FIX #4 — prove the suite runs against an isolated temp DATA_DIR, never live data/.

``tests/conftest.py`` sets ``AIOS_DATA_DIR`` to a throwaway temp directory before
``aios.config`` is imported, so every derived path (memory/audit DBs, FAISS index,
rollback DB) resolves under that temp dir and the real ``data/`` is untouched. With
an empty isolated index, ``hybrid_search`` also short-circuits to ``[]`` without
loading the embedder — which is why the API tests no longer need a stub.
"""
from __future__ import annotations

import os
from pathlib import Path

from aios import config


def test_data_dir_is_isolated_to_a_temp_dir() -> None:
    env = os.environ.get("AIOS_DATA_DIR")
    assert env, "conftest.py must set AIOS_DATA_DIR for the session"
    assert config.DATA_DIR == Path(env).expanduser().resolve()
    # It is NOT the real on-disk data/ under the project root.
    assert config.DATA_DIR != (config.PROJECT_ROOT / "data")
    assert (config.PROJECT_ROOT / "data") not in config.DATA_DIR.parents
    assert config.DATA_DIR.is_dir()


def test_derived_paths_live_under_the_temp_data_dir() -> None:
    for path in (
        config.MEMORY_DB_PATH,
        config.AUDIT_DB_PATH,
        config.FAISS_INDEX_PATH,
        config.ROLLBACK_DIR,
    ):
        assert path.parent == config.DATA_DIR, f"{path} must live under the temp DATA_DIR"
    # Concretely: none of them point at the real project data/ artifacts.
    real_data = config.PROJECT_ROOT / "data"
    assert config.MEMORY_DB_PATH != real_data / "aios_memory.db"
    assert config.FAISS_INDEX_PATH != real_data / "vector_index.faiss"


def test_hybrid_search_short_circuits_empty_without_loading_embedder(monkeypatch) -> None:
    # The contract that lets the API tests drop their hybrid_search stub: on an
    # empty (isolated) index, recall returns [] WITHOUT constructing the embedding
    # model. We make EmbeddingModel.instance() explode so any load fails loudly.
    from aios.memory import retrieval
    from aios.memory.embeddings import EmbeddingModel

    def _boom() -> object:
        raise AssertionError("the embedder must not load for an empty index")

    monkeypatch.setattr(EmbeddingModel, "instance", staticmethod(_boom))
    assert retrieval.hybrid_search("anything at all", top_k=3) == []
