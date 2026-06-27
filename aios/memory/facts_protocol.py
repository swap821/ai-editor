"""Shared protocol and row wrapper for semantic-fact graph stores.

The SQLite ``SemanticFacts`` class and the optional Neo4j backend both
implement :class:`GraphStore` so callers (the API, recall logic, tests) can
work against either engine without branching.
"""
from __future__ import annotations

from typing import Any, Iterator, Mapping, Optional, Protocol, runtime_checkable


class GraphRow(Mapping[str, Any]):
    """Dict-like row returned by any GraphStore implementation."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __repr__(self) -> str:
        return f"GraphRow({self._data!r})"


@runtime_checkable
class GraphStore(Protocol):
    """Common interface for SQLite and Neo4j semantic fact stores."""

    def add_fact(
        self, subject: str, predicate: str, obj: str, *, approved_by: Optional[str] = None
    ) -> "FactWriteResult": ...  # type: ignore[name-defined]
    def reconcile(
        self, subject: str, predicate: str, new_obj: str, *, approved_by: Optional[str] = None
    ) -> "FactWriteResult": ...  # type: ignore[name-defined]
    def get(self, fact_id: int) -> Optional[GraphRow]: ...
    def facts_for(self, subject: str, predicate: Optional[str] = None) -> list[GraphRow]: ...
    def neighbors(self, subject: str) -> list[GraphRow]: ...
    def traverse(self, start: str, max_depth: int = 2) -> list[GraphRow]: ...
    def search(self, query: str) -> list[GraphRow]: ...
