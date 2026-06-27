# Full knowledge graph — design spec

**Date:** 2026-06-26  
**Scope:** Close the `RENOVATION_PLAN.md` / `FUTURE_FRONTIER.md` knowledge-graph gap beyond the MVP SQLite recursive-CTE traversal. Deliver an optional Neo4j backend that respects the existing human-approved write path and keeps SQLite as the local-first default.  
**Constraint:** Local-first by default; Neo4j is opt-in via `AIOS_NEO4J_URI`; no behavior change when unset.

---

## Goal

The MVP already stores contradiction-aware `(subject, predicate, object)` triples in SQLite and can walk them deterministically with `traverse()`. The deferred "full" gap is the ability to scale the graph beyond single-operator SQLite limits without redesigning the approved write path. This slice adds an optional Neo4j backend behind a common store interface so the same API, tests, and recall logic work against either engine.

Honest target: **~90% interface parity between SQLite and Neo4j** — all read operations (facts_for, neighbors, traverse, search) plus approved writes and reconciliation. SQLite remains the default; Neo4j is an opt-in container service.

## Current state (from investigation)

- `aios/memory/facts.py` implements `SemanticFacts` with SQLite CRUD, contradiction detection, `neighbors()`, `traverse()` (recursive CTE), and `search()`.
- `aios/api/main.py` exposes `POST /api/v1/memory/facts`, `GET /api/v1/graph`, and `_recall_facts()` for forge prompt enrichment.
- `tests/test_facts.py` covers add, reconcile, facts_for, neighbors, traverse, search.
- There is no Neo4j driver, container, or config.

## Approaches

### Option A — Optional Neo4j backend with adapter pattern (Recommended)
Keep `SemanticFacts` as the SQLite default. Add a `Neo4jSemanticFacts` class implementing the same public methods, plus a small `GraphStore` factory that returns SQLite unless `AIOS_NEO4J_URI` is set. Update `aios/api/main.py` `get_semantic_facts()` to use the factory. Add an optional `neo4j` service to `docker-compose.yml` and tests that exercise the Neo4j implementation when a container is available.

*Trade-offs:* Respects local-first (SQLite default), closes the deferred Neo4j gap, and does not force a new dependency. Requires maintaining two backends in parallel.

### Option B — Enhanced SQLite graph + frontend visualization
Keep SQLite as the only backend. Add graph-analysis queries (shortest path, node degree), a `/api/v1/graph/visualization` endpoint, and a minimal D3 force-directed graph view in the product UI. No Neo4j.

*Trade-offs:* Better single-operator UX and no new dependency. Does not close the Neo4j gap the user explicitly named as deferred/full.

### Option C — Full Neo4j-only migration
Replace SQLite `semantic_facts` with Neo4j as the canonical store, migrate existing facts on startup, and drop the SQLite path.

*Trade-offs:* Cleanest for a graph-native future, but violates local-first-by-default and forces every install to run Neo4j. Rejected.

**Recommendation: Option A.** It is the honest "full completion" of the deferred gap while preserving the existing SQLite default.

## Design

### 1. Common interface

Define a `GraphStore` protocol in `aios/memory/facts_protocol.py` (or reuse `SemanticFacts` as the interface). Methods:

- `add_fact(subject, predicate, object, *, approved_by=None) -> FactWriteResult`
- `reconcile(subject, predicate, new_obj, *, approved_by=None) -> FactWriteResult`
- `get(fact_id) -> Optional[sqlite3.Row]` (returns a dict-like row; Neo4j returns a Record wrapped to look the same)
- `facts_for(subject, predicate=None) -> list[Row]`
- `neighbors(subject) -> list[Row]`
- `traverse(start, max_depth=2) -> list[Row]`
- `search(query) -> list[Row]`

Return rows must expose `subject`, `predicate`, `object`, `status`, `id`, `approved_by`, `depth`, `path`, and `direction` keys via `__getitem__` so existing callers keep working.

### 2. Neo4j implementation

Create `aios/memory/facts_neo4j.py`:

- `Neo4jSemanticFacts` initialized with `uri`, `user`, `password` (from config/env).
- Schema: each fact is a relationship `(s:Entity {name})-[r:PREDICATE {id, approved_by, status, created_at}]->(o:Entity {name})`. A status property allows soft-delete/supersede without losing history.
- Reads use Cypher `MATCH` queries; traversal uses `apoc.path.expandConfig` if APOC is available, otherwise recursive Cypher with depth limit and path string cycle guard.
- Writes require `approved_by` to be set (or at least stored); reconciliation sets `status='superseded'` on old edges and inserts a new edge.
- Contradiction detection: check for an active edge with same `(s,p)` but different `o`.

### 3. Factory

Create `aios/memory/facts_store.py`:

```python
def get_graph_store(db_path: Optional[Path] = None) -> GraphStore:
    if config.NEO4J_URI:
        return Neo4jSemanticFacts(uri=config.NEO4J_URI, user=config.NEO4J_USER, password=config.NEO4J_PASSWORD)
    return SemanticFacts(db_path=db_path or config.MEMORY_DB_PATH)
```

### 4. Config

Add to `aios/config.py`:

- `NEO4J_URI: Final[Optional[str]] = _env_str("AIOS_NEO4J_URI", None)`
- `NEO4J_USER: Final[str] = _env_str("AIOS_NEO4J_USER", "neo4j")`
- `NEO4J_PASSWORD: Final[str] = _env_str("AIOS_NEO4J_PASSWORD", "aios")`

### 5. API wiring

Change `aios/api/main.py` `get_semantic_facts()` to return `get_graph_store()`.

### 6. Docker Compose

Add optional `neo4j` service to `docker-compose.yml`:

```yaml
  neo4j:
    image: neo4j:5.25-community
    ports:
      - "${AIOS_NEO4J_BOLT_PORT:-7687}:7687"
      - "${AIOS_NEO4J_HTTP_PORT:-7474}:7474"
    environment:
      - NEO4J_AUTH=${AIOS_NEO4J_USER:-neo4j}/${AIOS_NEO4J_PASSWORD:-aios}
      - NEO4J_PLUGINS=["apoc"]
    volumes:
      - neo4j-data:/data
    networks:
      - aios-net
```

Add `neo4j-data` volume. The `aios` service only connects when `AIOS_NEO4J_URI` is set.

### 7. Tests

Add `tests/test_facts_neo4j.py`:

- A fixture that starts a Neo4j container via `testcontainers` (or skips if Docker unavailable).
- Runs the same test matrix as `tests/test_facts.py` against `Neo4jSemanticFacts`.
- Asserts parity with SQLite behavior.

If `testcontainers` is not desired, mock the Neo4j driver with a tiny in-memory graph for unit tests, plus an integration marker for real Docker.

## Files touched

- `aios/config.py` — Neo4j env vars.
- `aios/memory/facts.py` — ensure return rows implement the shared protocol (already close).
- `aios/memory/facts_neo4j.py` — new Neo4j backend.
- `aios/memory/facts_store.py` — factory.
- `aios/api/main.py` — `get_semantic_facts()` uses factory.
- `docker-compose.yml` — optional neo4j service.
- `requirements.txt` — add `neo4j`.
- `tests/test_facts_neo4j.py` — new tests.
- `AGENTS.md` — document Neo4j opt-in usage.

## Testing plan

1. SQLite regression: `tests/test_facts.py` still passes unchanged.
2. Neo4j unit tests with mocked driver exercise all public methods.
3. Docker integration test (optional, marked) spins up real Neo4j and repeats the facts matrix.
4. API tests with `get_semantic_facts` overridden to Neo4j verify endpoint wiring.
5. Backend full suite green.

## Security notes

- Neo4j credentials come from env only, never committed.
- The human-approved write path is unchanged: `add_fact` and `reconcile` still require/expose `approved_by`.
- Secret scanner redacts credentials before audit logging.

## Out of scope

- Graph visualization UI (a future frontend slice).
- Migration of existing SQLite facts into Neo4j (can be added later; not required because Neo4j is opt-in for new installs).
- APOC-dependent advanced graph algorithms beyond traversal.

## Rollout

Default: nothing changes. SQLite remains the store.

To opt into Neo4j:

```bash
AIOS_NEO4J_URI=bolt://localhost:7687 AIOS_NEO4J_PASSWORD=secret docker compose up --build
```
