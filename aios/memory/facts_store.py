"""Factory for choosing the active semantic-fact graph store backend.

SQLite is the local-first default. Neo4j is used only when ``AIOS_NEO4J_URI``
is configured.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from aios import config
from aios.memory.facts import SemanticFacts
from aios.memory.facts_neo4j import Neo4jSemanticFacts
from aios.memory.facts_protocol import GraphStore


def get_graph_store(db_path: Optional[Path] = None) -> GraphStore:
    """Return the configured graph store backend."""
    if config.NEO4J_URI:
        return Neo4jSemanticFacts(
            uri=config.NEO4J_URI,
            user=config.NEO4J_USER,
            password=config.NEO4J_PASSWORD,
        )
    return SemanticFacts(db_path=db_path or config.MEMORY_DB_PATH)
