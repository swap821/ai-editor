# Full knowledge graph — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional Neo4j backend for the semantic fact graph while keeping SQLite as the local-first default.

**Architecture:** Define a `GraphStore` protocol, implement `Neo4jSemanticFacts` with Cypher queries mirroring the SQLite behavior, add a `get_graph_store()` factory driven by `AIOS_NEO4J_URI`, wire it into `get_semantic_facts()`, and add unit + optional integration tests.

**Tech Stack:** Python 3.12, SQLite (existing), Neo4j 5.x Community, `neo4j` Python driver, Docker Compose.

---

## File structure

| File | Responsibility |
|------|----------------|
| `aios/config.py` | New Neo4j env vars. |
| `aios/memory/facts_protocol.py` | `GraphStore` protocol + row-wrapper helper. |
| `aios/memory/facts.py` | SQLite backend; adjusted to satisfy protocol. |
| `aios/memory/facts_neo4j.py` | Neo4j backend implementing the protocol. |
| `aios/memory/facts_store.py` | Factory returning SQLite or Neo4j store. |
| `aios/api/main.py` | `get_semantic_facts()` uses factory. |
| `docker-compose.yml` | Optional `neo4j` service + volume. |
| `requirements.txt` | Add `neo4j`. |
| `tests/test_facts_neo4j.py` | Neo4j backend unit tests with mocked driver. |
| `tests/test_facts_neo4j_integration.py` | Optional real-Neo4j integration tests. |
| `AGENTS.md` | Neo4j opt-in usage notes. |

---

## Task 1: Add Neo4j config and protocol

**Files:**
- Modify: `aios/config.py`
- Create: `aios/memory/facts_protocol.py`

- [ ] **Step 1: Add Neo4j env vars to `aios/config.py`**

Near the other `_env_str` calls, add:

```python
NEO4J_URI: Final[Optional[str]] = _env_str("AIOS_NEO4J_URI", None)
NEO4J_USER: Final[str] = _env_str("AIOS_NEO4J_USER", "neo4j")
NEO4J_PASSWORD: Final[str] = _env_str("AIOS_NEO4J_PASSWORD", "aios")
```

- [ ] **Step 2: Create `aios/memory/facts_protocol.py`**

```python
from __future__ import annotations

from typing import Any, Mapping, Optional, Protocol, runtime_checkable


class GraphRow(Mapping[str, Any]):
    """Dict-like row returned by any GraphStore implementation."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __iter__(self):
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)


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
```

- [ ] **Step 3: Update `aios/memory/facts.py` to return `GraphRow` and import `FactWriteResult` cleanly**

Change `facts_for`, `neighbors`, `traverse`, `search`, and `get` to wrap returned rows with `GraphRow(dict(row))`. Keep `sqlite3.Row` input but output `GraphRow`.

Also move `FactWriteResult` import into `facts_protocol.py`? No — keep it in `facts.py` and import it from there in the protocol module to avoid circular imports. Actually, the protocol references `FactWriteResult` as a string. Keep `FactWriteResult` in `facts.py`; `facts_protocol.py` only needs forward references.

---

## Task 2: Implement Neo4j backend

**Files:**
- Create: `aios/memory/facts_neo4j.py`

- [ ] **Step 1: Create `Neo4jSemanticFacts` class**

Implement all public methods from the protocol. Key Cypher snippets:

Schema initialization:
```cypher
CREATE CONSTRAINT entity_name IF NOT EXISTS
FOR (e:Entity) REQUIRE e.name IS UNIQUE;
```

Add fact (with contradiction check):
```cypher
MATCH (s:Entity {name: $subject})-[r:PREDICATE {predicate: $predicate, status: 'active'}]->(o:Entity)
WHERE o.name <> $obj
RETURN o.name AS conflict_object, r.id AS conflict_id LIMIT 1
```
If no conflict:
```cypher
MERGE (s:Entity {name: $subject})
MERGE (o:Entity {name: $obj})
CREATE (s)-[r:PREDICATE {predicate: $predicate, status: 'active', approved_by: $approved_by, created_at: datetime()}]->(o)
SET r.id = id(r)
RETURN r.id AS fact_id
```

Reconcile:
```cypher
MATCH (s:Entity {name: $subject})-[r:PREDICATE {predicate: $predicate, status: 'active'}]->(:Entity)
SET r.status = 'superseded'
MERGE (o:Entity {name: $new_obj})
CREATE (s)-[r2:PREDICATE {predicate: $predicate, status: 'active', approved_by: $approved_by, created_at: datetime()}]->(o)
SET r2.id = id(r2)
RETURN r2.id AS fact_id
```

Neighbors:
```cypher
MATCH (s:Entity {name: $subject})-[r:PREDICATE {status: 'active'}]->(o:Entity)
RETURN s.name AS subject, r.predicate AS predicate, o.name AS object, 'out' AS direction
UNION ALL
MATCH (o:Entity)-[r:PREDICATE {status: 'active'}]->(s:Entity {name: $subject})
RETURN o.name AS subject, r.predicate AS predicate, s.name AS object, 'in' AS direction
```

Traverse (depth-limited without APOC):
```cypher
MATCH path = (start:Entity {name: $start})-[:PREDICATE*1..$max_depth {status: 'active'}]->(end:Entity)
WHERE all(n IN nodes(path) WHERE single(x IN nodes(path) WHERE x = n))
RETURN start.name AS subject, [r IN relationships(path) | r.predicate] AS predicates, end.name AS object, length(path) AS depth
```

Note: The traverse row shape differs from SQLite. For parity, flatten each path into per-edge rows in Python or use a Cypher that returns one row per edge. Simpler: in Python, walk each path and yield per-hop edges.

Search:
```cypher
MATCH (s:Entity)-[r:PREDICATE {status: 'active'}]->(o:Entity)
WHERE toLower(s.name) CONTAINS $token OR toLower(o.name) CONTAINS $token
RETURN DISTINCT s.name AS subject, r.predicate AS predicate, o.name AS object
```

- [ ] **Step 2: Lazy import `neo4j`**

Inside `__init__` or module-level guarded import so the backend starts even if `neo4j` is not installed, as long as SQLite is used.

---

## Task 3: Create factory and wire API

**Files:**
- Create: `aios/memory/facts_store.py`
- Modify: `aios/api/main.py`

- [ ] **Step 1: Create `aios/memory/facts_store.py`**

```python
from pathlib import Path
from typing import Optional

from aios import config
from aios.memory.facts import SemanticFacts
from aios.memory.facts_neo4j import Neo4jSemanticFacts
from aios.memory.facts_protocol import GraphStore


def get_graph_store(db_path: Optional[Path] = None) -> GraphStore:
    if config.NEO4J_URI:
        return Neo4jSemanticFacts(
            uri=config.NEO4J_URI,
            user=config.NEO4J_USER,
            password=config.NEO4J_PASSWORD,
        )
    return SemanticFacts(db_path=db_path or config.MEMORY_DB_PATH)
```

- [ ] **Step 2: Update `aios/api/main.py` `get_semantic_facts()`**

Change:
```python
def get_semantic_facts() -> SemanticFacts:
    return SemanticFacts()
```

To:
```python
from aios.memory.facts_store import get_graph_store

def get_semantic_facts() -> GraphStore:
    return get_graph_store()
```

Update type hints on endpoints that depend on `SemanticFacts` to `GraphStore`.

---

## Task 4: Add Neo4j to Docker Compose and requirements

**Files:**
- Modify: `docker-compose.yml`
- Modify: `requirements.txt`

- [ ] **Step 1: Add `neo4j` service to `docker-compose.yml`**

Append to services:

```yaml
  neo4j:
    image: neo4j:5.25-community
    ports:
      - "${AIOS_NEO4J_BOLT_PORT:-7687}:7687"
      - "${AIOS_NEO4J_HTTP_PORT:-7474}:7474"
    environment:
      - NEO4J_AUTH=${AIOS_NEO4J_USER:-neo4j}/${AIOS_NEO4J_PASSWORD:-aios}
    volumes:
      - neo4j-data:/data
    networks:
      - aios-net
```

Add volume:
```yaml
volumes:
  prometheus-data:
  grafana-data:
  neo4j-data:
```

- [ ] **Step 2: Add `neo4j` to `requirements.txt`**

Add `neo4j==5.28.4` (or latest 5.x LTS).

- [ ] **Step 3: Validate compose syntax**

```bash
docker compose config > /dev/null
```

---

## Task 5: Add tests

**Files:**
- Create: `tests/test_facts_neo4j.py`

- [ ] **Step 1: Mock-based unit tests**

Create a fake Neo4j driver/session/transaction that stores nodes/relationships in Python data structures. Implement the same test matrix as `tests/test_facts.py` using `Neo4jSemanticFacts` backed by the fake.

```python
class FakeNeo4jDriver:
    def session(self):
        return FakeSession()

# tests mirror test_facts.py
```

- [ ] **Step 2: Optional integration tests**

Create `tests/test_facts_neo4j_integration.py` marked with `pytest.mark.neo4j_integration` that skips unless `AIOS_NEO4J_URI` is set, then runs the matrix against the real Neo4j.

---

## Task 6: Update docs and verify

**Files:**
- Modify: `AGENTS.md`

- [ ] **Step 1: Add Neo4j usage note**

In `AGENTS.md` §XI, add:

```markdown
- **Knowledge graph backend:** SQLite is the default. To use Neo4j, set `AIOS_NEO4J_URI=bolt://localhost:7687` (or `bolt://neo4j:7687` inside Docker) and `AIOS_NEO4J_PASSWORD`. The `neo4j` service in `docker-compose.yml` is optional and only starts when included.
```

- [ ] **Step 2: Run tests**

```bash
.venv\Scripts\python -m pytest tests/test_facts.py tests/test_facts_neo4j.py -q
.venv\Scripts\python -m pytest -q
```

Expected: full suite green.

---

## Task 7: Commit

- [ ] **Step 1: Commit**

```bash
git add -A
git commit -m "knowledge-graph: optional Neo4j backend behind GraphStore protocol

- GraphStore protocol + GraphRow wrapper for backend parity
- Neo4jSemanticFacts implementing add/reconcile/get/facts_for/neighbors/traverse/search
- get_graph_store() factory driven by AIOS_NEO4J_URI
- get_semantic_facts() uses factory; SQLite remains default
- Optional neo4j service in docker-compose.yml
- Mock-driver unit tests for Neo4j backend
- AGENTS.md usage notes"
```

---

## Self-review

**Spec coverage:**
- Neo4j config → Task 1.
- Protocol/wrapper → Task 1.
- Neo4j backend → Task 2.
- Factory/API wiring → Task 3.
- Docker/requirements → Task 4.
- Tests → Task 5.
- Docs → Task 6.

**Placeholder scan:** No TBD. Cypher snippets are concrete. Mock driver code is described; actual fake implementation will be written in the step.

**Type consistency:** `GraphStore` protocol used everywhere; `SemanticFacts` and `Neo4jSemanticFacts` both satisfy it.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-26-full-knowledge-graph-plan.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — Dispatch a fresh subagent per task.
2. **Inline Execution** — Execute tasks in this session.

Which approach?
