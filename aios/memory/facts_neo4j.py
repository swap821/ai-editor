"""Optional Neo4j backend for the semantic-fact graph store.

This module is only imported when ``AIOS_NEO4J_URI`` is set. It implements the
same public interface as :class:`aios.memory.facts.SemanticFacts` so the API and
recall logic work unchanged.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from aios.memory.facts import FactWriteResult
from aios.memory.facts_protocol import GraphRow

if TYPE_CHECKING:
    import neo4j


class Neo4jSemanticFacts:
    """CRUD + graph traversal over Neo4j for AI-OS semantic facts."""

    def __init__(self, uri: str, user: str, password: str) -> None:
        import neo4j as _neo4j

        self._driver: neo4j.Driver = _neo4j.GraphDatabase.driver(
            uri, auth=(user, password)
        )
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Create constraints/indexes idempotently."""
        with self._driver.session() as session:
            session.run(
                "CREATE CONSTRAINT entity_name IF NOT EXISTS "
                "FOR (e:Entity) REQUIRE e.name IS UNIQUE"
            )

    def _redact(self, value: Optional[str]) -> Optional[str]:
        from aios.security.secret_scanner import scan_and_redact

        if not value:
            return None
        return scan_and_redact(value.strip()).scrubbed or None

    def add_fact(
        self, subject: str, predicate: str, obj: str, *, approved_by: Optional[str] = None
    ) -> FactWriteResult:
        """Commit a fact unless it contradicts an existing active fact."""
        subject = self._redact(subject) or ""
        predicate = self._redact(predicate) or ""
        obj = self._redact(obj) or ""
        approved_by = self._redact(approved_by)
        if not (subject and predicate and obj):
            return FactWriteResult(False, None, "empty subject/predicate/object")

        with self._driver.session() as session:
            conflict = session.run(
                """
                MATCH (s:Entity {name: $subject})-[r:PREDICATE {predicate: $predicate, status: 'active'}]->(o:Entity)
                WHERE o.name <> $obj
                RETURN o.name AS conflict_object, id(r) AS conflict_id
                LIMIT 1
                """,
                subject=subject,
                predicate=predicate,
                obj=obj,
            ).single()
            if conflict is not None:
                return FactWriteResult(
                    committed=False,
                    fact_id=None,
                    reason="contradiction",
                    conflict_id=int(conflict["conflict_id"]),
                    conflict_object=str(conflict["conflict_object"]),
                )

            existing = session.run(
                """
                MATCH (s:Entity {name: $subject})-[r:PREDICATE {predicate: $predicate, status: 'active'}]->(o:Entity {name: $obj})
                RETURN id(r) AS fact_id
                LIMIT 1
                """,
                subject=subject,
                predicate=predicate,
                obj=obj,
            ).single()
            if existing is not None:
                fact_id = int(existing["fact_id"])
                if approved_by is not None:
                    session.run(
                        """
                        MATCH ()-[r:PREDICATE]->() WHERE id(r) = $fact_id
                        SET r.approved_by = COALESCE(r.approved_by, $approved_by)
                        """,
                        fact_id=fact_id,
                        approved_by=approved_by,
                    )
                return FactWriteResult(True, fact_id, "already present")

            result = session.run(
                """
                MERGE (s:Entity {name: $subject})
                MERGE (o:Entity {name: $obj})
                CREATE (s)-[r:PREDICATE {predicate: $predicate, status: 'active', approved_by: $approved_by, created_at: datetime()}]->(o)
                RETURN id(r) AS fact_id
                """,
                subject=subject,
                predicate=predicate,
                obj=obj,
                approved_by=approved_by,
            ).single()
            fact_id = int(result["fact_id"]) if result and result["fact_id"] is not None else None
            return FactWriteResult(True, fact_id, "committed")

    def reconcile(
        self, subject: str, predicate: str, new_obj: str, *, approved_by: Optional[str] = None
    ) -> FactWriteResult:
        """Resolve a contradiction: supersede old facts and commit *new_obj*."""
        subject = self._redact(subject) or ""
        predicate = self._redact(predicate) or ""
        new_obj = self._redact(new_obj) or ""
        approved_by = self._redact(approved_by)
        if not (subject and predicate and new_obj):
            return FactWriteResult(False, None, "empty subject/predicate/object")

        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (s:Entity {name: $subject})-[r:PREDICATE {predicate: $predicate, status: 'active'}]->(:Entity)
                SET r.status = 'superseded'
                WITH s
                MERGE (o:Entity {name: $new_obj})
                CREATE (s)-[r2:PREDICATE {predicate: $predicate, status: 'active', approved_by: $approved_by, created_at: datetime()}]->(o)
                RETURN id(r2) AS fact_id
                """,
                subject=subject,
                predicate=predicate,
                new_obj=new_obj,
                approved_by=approved_by,
            ).single()
            fact_id = int(result["fact_id"]) if result and result["fact_id"] is not None else None
            return FactWriteResult(True, fact_id, "reconciled")

    def get(self, fact_id: int) -> Optional[GraphRow]:
        """Return the active fact edge for *fact_id*, or ``None``."""
        with self._driver.session() as session:
            record = session.run(
                """
                MATCH (s:Entity)-[r:PREDICATE]->(o:Entity)
                WHERE id(r) = $fact_id
                RETURN s.name AS subject, r.predicate AS predicate, o.name AS object,
                       r.status AS status, id(r) AS id, r.approved_by AS approved_by
                """,
                fact_id=fact_id,
            ).single()
            return self._row(record) if record is not None else None

    def facts_for(self, subject: str, predicate: Optional[str] = None) -> list[GraphRow]:
        """Return active facts for *subject*."""
        subject = (subject or "").strip()
        if not subject:
            return []
        cypher = """
            MATCH (s:Entity {name: $subject})-[r:PREDICATE {status: 'active'}]->(o:Entity)
        """
        if predicate is not None:
            cypher += " WHERE r.predicate = $predicate"
        cypher += """
            RETURN s.name AS subject, r.predicate AS predicate, o.name AS object,
                   r.status AS status, id(r) AS id, r.approved_by AS approved_by
            ORDER BY r.created_at DESC
        """
        with self._driver.session() as session:
            return [self._row(r) for r in session.run(cypher, subject=subject, predicate=predicate)]

    def neighbors(self, subject: str) -> list[GraphRow]:
        """Return active edges adjacent to *subject* (incoming + outgoing)."""
        subject = (subject or "").strip()
        if not subject:
            return []
        cypher = """
        MATCH (s:Entity {name: $subject})-[r:PREDICATE {status: 'active'}]->(o:Entity)
        RETURN s.name AS subject, r.predicate AS predicate, o.name AS object,
               r.status AS status, id(r) AS id, r.approved_by AS approved_by, 'out' AS direction
        UNION ALL
        MATCH (o:Entity)-[r:PREDICATE {status: 'active'}]->(s:Entity {name: $subject})
        RETURN o.name AS subject, r.predicate AS predicate, s.name AS object,
               r.status AS status, id(r) AS id, r.approved_by AS approved_by, 'in' AS direction
        ORDER BY direction, subject, predicate
        """
        with self._driver.session() as session:
            return [self._row(r) for r in session.run(cypher, subject=subject)]

    def traverse(self, start: str, max_depth: int = 2) -> list[GraphRow]:
        """Walk active edges outward from *start* up to *max_depth* hops.

        Returns one row per edge in each path, with ``depth`` and ``path``
        fields matching the SQLite CTE output shape.
        """
        start = (start or "").strip()
        if not start:
            return []
        depth = max(1, min(int(max_depth), 4))
        cypher = """
        MATCH path = (start:Entity {name: $start})-[:PREDICATE {status: 'active'}*1..$max_depth]->(end:Entity)
        WITH path, length(path) AS path_len, nodes(path) AS ns, relationships(path) AS rels
        WHERE all(n IN ns WHERE single(x IN ns WHERE x = n))
        UNWIND range(0, length(rels) - 1) AS idx
        WITH rels[idx] AS r, nodes(path)[idx] AS s, nodes(path)[idx + 1] AS o, path_len, path
        RETURN s.name AS subject, r.predicate AS predicate, o.name AS object,
               idx + 1 AS depth,
               reduce(p = '→', n IN nodes(path) | p + n.name + '→') AS path,
               r.status AS status, id(r) AS id, r.approved_by AS approved_by
        ORDER BY depth, subject, predicate
        """
        with self._driver.session() as session:
            return [self._row(r) for r in session.run(cypher, start=start, max_depth=depth)]

    def search(self, query: str) -> list[GraphRow]:
        """Return active facts whose subject or object contains a token from *query*."""
        query = (query or "").strip().lower()
        tokens = [t for t in set(query.split()) if len(t) >= 3]
        if not tokens:
            return []
        # Use the first token for simplicity; union additional tokens in Python.
        results: list[GraphRow] = []
        seen: set[tuple[str, str, str]] = set()
        with self._driver.session() as session:
            for token in tokens:
                for record in session.run(
                    """
                    MATCH (s:Entity)-[r:PREDICATE {status: 'active'}]->(o:Entity)
                    WHERE toLower(s.name) CONTAINS $token OR toLower(o.name) CONTAINS $token
                    RETURN DISTINCT s.name AS subject, r.predicate AS predicate, o.name AS object,
                           r.status AS status, id(r) AS id, r.approved_by AS approved_by
                    """,
                    token=token,
                ):
                    row = self._row(record)
                    key = (str(row["subject"]), str(row["predicate"]), str(row["object"]))
                    if key not in seen:
                        seen.add(key)
                        results.append(row)
        return results

    @staticmethod
    def _row(record: Optional[object]) -> Optional[GraphRow]:
        if record is None:
            return None
        data: dict[str, object] = {
            "subject": record["subject"],
            "predicate": record["predicate"],
            "object": record["object"],
            "status": record.get("status", "active"),
            "id": record.get("id"),
            "approved_by": record.get("approved_by"),
        }
        for key in ("depth", "path", "direction"):
            if key in record.keys():
                data[key] = record[key]
        return GraphRow(data)
