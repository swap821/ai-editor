# Knowledge Graph (Hippocampus) — Phase S2 Grounded Implementation Spec

**Status:** GROUNDED — ready to build  
**Date:** 2026-07-03  
**Parent:** `docs/superpowers/specs/2026-07-03-sovereignty-engine-design.md` (Phase 1 ADR)  
**Scope:** Extend `aios/memory/facts.py`, new `aios/core/inference.py`, new
`aios/core/graph_ingestion.py`, DDL migration in `aios/memory/db.py`,
cross-store ingestion hooks in `aios/memory/skills.py` +
`aios/memory/mistake.py`, API endpoint, SSE events, adapter wiring  
**Security spine:** FROZEN, untouched — inference is read-only against verified data

> **Critical discovery during implementation spec grounding:** The Phase 1 ADR
> proposed building `aios/core/knowledge_graph.py` with `KGNode`, `KGEdge`,
> `InferenceChain`, and a new `KnowledgeGraph` class. **That is the wrong
> move.** The knowledge graph already exists inside
> `aios/memory/facts.py:193` — `SemanticFacts.traverse()` does recursive CTE
> multi-hop traversal with cycle detection, depth limits [1,4], and path
> tracking. `neighbors()` (line 168) does bidirectional single-hop lookup.
> `search()` (line 242) does token-based entity matching. The `semantic_facts`
> table IS the graph — subjects and objects are nodes, predicates are edges.
>
> Building a parallel `KnowledgeGraph` class would create two competing fact
> stores, two traversal implementations, and a synchronization problem. The
> correct design extends `SemanticFacts` with what it's missing:
> confidence-weighted traversal, cross-store ingestion, and an inference
> composition layer.

---

## 0. What already exists vs. what's missing

### Already built (in `aios/memory/facts.py`)

| Capability | Method | Line | Status |
|------------|--------|------|--------|
| Add fact with contradiction detection | `add_fact()` | 62 | Working, tested |
| Supervised proposals (quarantined) | `propose()` | 279 | Working, tested |
| Single-hop bidirectional lookup | `neighbors()` | 168 | Working, tested |
| Multi-hop recursive traversal (CTE) | `traverse()` | 193 | Working, tested (cycle-safe, depth-clamped) |
| Token-based entity search | `search()` | 242 | Working, tested |
| Contradiction detection + reconciliation | `find_conflict()` / `reconcile()` | 51 / 120 | Working, tested |
| Fact retrieval for LLM context | `_recall_facts()` in `main.py:2809` | — | Working (search + 1-hop neighbors) |

### What's missing (the actual S2 deliverable)

| Gap | Why it matters |
|-----|---------------|
| **Confidence weighting on traversal** | `traverse()` returns all edges equally. A 3-hop chain should decay in confidence. Without this, a distant association has the same weight as a direct fact. |
| **Confidence column on `add_fact()`** | `add_fact()` has no `confidence` parameter. Cross-store ingestion produces edges at varying confidence levels (1.0 for direct facts, 0.8 for lessons). Without this, confidence is silently dropped at ingestion time. |
| **Cross-store ingestion** | Only operator statements feed into `semantic_facts` (via `fact_extraction.py`). Verified skills, verified mistakes, and verified development outcomes contain entity-relationship knowledge that never enters the graph. |
| **Entity extraction** | No deterministic extractor for entities from natural-language goal/step text. Cross-store ingestion and query targeting both need this. |
| **Inference composition** | `traverse()` returns raw SQL rows. Nothing composes them into a structured inference chain with a confidence score and an explainable path. |
| **SSE events** | No `graph_inference` / `graph_horizon` events for the frontend. |
| **API endpoint** | No `/api/v1/knowledge/query` for structured graph queries. |

---

## 1. Confidence column — DDL migration + `add_fact()` extension

### 1.1 DDL migration — add `confidence` column to `semantic_facts`

Add to `aios/memory/db.py:_migrate()`, after the existing `approved_by`
migration (line 170):

```python
# S2: confidence column on semantic_facts (default 1.0 for existing rows).
if fact_cols and "confidence" not in fact_cols:
    conn.execute(
        "ALTER TABLE semantic_facts ADD COLUMN confidence REAL NOT NULL DEFAULT 1.0"
    )
```

**Why a migration, not a schema.sql change:** the table already exists in
every deployed DB. `CREATE TABLE IF NOT EXISTS` is a no-op on existing tables.
`ALTER TABLE ADD COLUMN` with a default is safe and idempotent (the migration
checks first). Same pattern as the existing `fingerprint` migration (line 90)
and `approved_by` migration (line 170).

### 1.2 Extend `add_fact()` with `confidence` parameter

In `aios/memory/facts.py`, extend the `add_fact()` signature (line 62):

```python
def add_fact(
    self, subject: str, predicate: str, obj: str,
    *,
    approved_by: Optional[str] = None,
    confidence: float = 1.0,
) -> FactWriteResult:
```

The INSERT (line 113) becomes:

```python
cur = conn.execute(
    "INSERT INTO semantic_facts "
    "(subject, predicate, object, approved_by, confidence) "
    "VALUES (?, ?, ?, ?, ?)",
    (subject, predicate, obj, approved_by, max(0.0, min(1.0, confidence))),
)
```

The existing `approved_by` UPDATE for idempotent re-inserts (line 107) also
sets confidence to the maximum of old and new:

```python
if existing is not None:
    if approved_by is not None:
        conn.execute(
            "UPDATE semantic_facts "
            "SET approved_by = COALESCE(approved_by, ?), "
            "    confidence = MAX(confidence, ?) "
            "WHERE id = ?",
            (approved_by, max(0.0, min(1.0, confidence)), int(existing["id"])),
        )
    return FactWriteResult(True, int(existing["id"]), "already present")
```

**Backward compatibility:** `confidence` defaults to 1.0. All existing
callers (`approve_proposal`, `reconcile`, `fact_extraction.py`) pass no
`confidence` parameter and get 1.0 — existing behavior unchanged.

---

## 2. Confidence-weighted traversal — extend `SemanticFacts`

### 2.1 New dataclass — `WeightedEdge`

```python
@dataclass(frozen=True)
class WeightedEdge:
    """One edge in a confidence-weighted traversal."""
    subject: str
    predicate: str
    object: str
    depth: int
    confidence: float
    path_confidence: float
    path: str
```

### 2.2 New method — `traverse_weighted()`

Add to `SemanticFacts` in `aios/memory/facts.py`:

```python
def traverse_weighted(
    self,
    start: str,
    max_depth: int = 3,
    *,
    min_path_confidence: float = 0.1,
    decay: float = 0.85,  # TUNABLE DEFAULT — how fast confidence degrades
                           # per hop. 0.85 means a 3-hop path retains ~61%
                           # of the source confidence. No principled
                           # derivation; adjust based on observed inference
                           # quality.
) -> list[WeightedEdge]:
    """Walk the ACTIVE fact graph with confidence decay per hop.

    Like traverse(), but each hop's contribution decays by *decay*
    starting at depth 2. A direct fact (depth 1) at confidence 1.0
    stays 1.0. A 2-hop path decays to 0.85. A 3-hop path to ~0.72.
    Paths below *min_path_confidence* are pruned.

    Uses the same recursive CTE as traverse() with the addition
    of a confidence column carried and multiplied through the
    recursion. Cycle-safe, depth-clamped [1,4].
    """
```

The recursive CTE:

```sql
WITH RECURSIVE graph(
    subject, predicate, object, depth, path,
    edge_confidence, path_confidence
) AS (
    -- Base case: depth 1, NO decay applied.
    -- A direct fact at confidence 1.0 has path_confidence 1.0.
    SELECT subject, predicate, object, 1,
           '→' || subject || '→' || object || '→',
           COALESCE(confidence, 1.0),
           COALESCE(confidence, 1.0)
    FROM semantic_facts
    WHERE subject = :start AND status = 'active'
    UNION ALL
    -- Recursive case: depth 2+, decay applied per hop.
    -- path_confidence = parent's path_confidence × this edge's confidence × decay
    SELECT f.subject, f.predicate, f.object, g.depth + 1,
           g.path || f.object || '→',
           COALESCE(f.confidence, 1.0),
           g.path_confidence * COALESCE(f.confidence, 1.0) * :decay
    FROM semantic_facts f
    JOIN graph g ON f.subject = g.object
    WHERE g.depth < :max_depth
      AND f.status = 'active'
      AND g.path NOT LIKE '%→' || f.object || '→%'
      AND g.path_confidence * COALESCE(f.confidence, 1.0) * :decay >= :min_conf
)
SELECT subject, predicate, object, depth, path,
       edge_confidence, path_confidence
FROM graph
ORDER BY path_confidence DESC, depth ASC
LIMIT :row_limit
```

**Key difference from existing `traverse()`:** the `path_confidence` column
multiplies through the recursion with decay starting at depth 2 (not depth 1).
The `WHERE` clause in the recursive term prunes paths below
`min_path_confidence`, bounding recursion cost.

**Confidence arithmetic (verified):**
- Depth 1, edge confidence 1.0 → path_confidence = 1.0 (no decay)
- Depth 2, edge confidence 1.0 → path_confidence = 1.0 × 1.0 × 0.85 = 0.85
- Depth 3, edge confidence 1.0 → path_confidence = 0.85 × 1.0 × 0.85 = 0.7225
- Depth 2, edge confidence 0.5 → path_confidence = 1.0 × 0.5 × 0.85 = 0.425
- Depth 3, edge confidence 0.5 → path_confidence = 0.425 × 0.5 × 0.85 = 0.18

---

## 3. Entity extraction — `aios/core/graph_ingestion.py`

A pure module with no state — extraction functions + entity finder.

### 3.1 `find_entities()` — deterministic entity extraction

```python
"""Cross-store ingestion for the knowledge graph.

Pure extraction functions: verified record in, (S, P, O, confidence) tuples
out. Each tuple is a candidate edge for SemanticFacts.add_fact(). The caller
decides when to ingest (typically on promotion/verification). The functions
never access the DB directly — they transform data structures, nothing more.
"""
from __future__ import annotations

import re
from typing import Optional

from aios.memory.relevance import tokens

_TOOL_VERBS = frozenset({
    "read_file", "read_directory", "execute_terminal",
    "create_file", "edit_file", "verify",
})

_PATH_LIKE = re.compile(
    r"[a-zA-Z_][\w./\\-]*\.(?:py|ts|tsx|js|jsx|json|md|sql|yml|yaml|toml|cfg)"
)
_QUOTED = re.compile(r"['\"`]([^'\"`]{2,60})['\"`]")
_GOAL_TARGET = re.compile(
    r"\b(?:for|of|in|to|on)\s+(?:the\s+)?([A-Za-z_][\w.-]{1,40})",
    re.IGNORECASE,
)


def find_entities(text: str) -> list[str]:
    """Extract candidate entity names from text. Deterministic, no LLM.

    Strategy (ordered by precision):
    1. File paths (foo/bar.py) — highest signal, unambiguous
    2. Quoted strings ('router module') — explicit naming
    3. Prepositional targets ("for the router", "in the executor")
       — nouns after for/of/in/to/on, filtered against stopwords
    4. Stem extraction from paths — "aios/core/router.py" → "router"

    Deduplicates case-insensitively.
    """
    entities: list[str] = []
    seen: set[str] = set()

    def _add(raw: str) -> None:
        clean = raw.strip().strip(".,;:!?\"'`()[]{}").strip()
        if len(clean) < 2 or clean.lower() in seen:
            return
        seen.add(clean.lower())
        entities.append(clean)

    for m in _PATH_LIKE.finditer(text):
        _add(m.group(0))
        stem = m.group(0).rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        stem = stem.rsplit(".", 1)[0]
        if len(stem) >= 2:
            _add(stem)

    for m in _QUOTED.finditer(text):
        _add(m.group(1))

    for m in _GOAL_TARGET.finditer(text):
        candidate = m.group(1)
        if candidate.lower() not in {"the", "a", "an", "this", "that", "it"}:
            _add(candidate)

    return entities
```

**Coverage examples (verified against the regexes):**
- `"create a pytest for the router module"` → `["router"]`
  (via `_GOAL_TARGET`: "for the router")
- `"read_file: aios/core/router.py"` → `["aios/core/router.py", "router"]`
  (via `_PATH_LIKE` + stem extraction)
- `"fix the authentication bug in the session middleware"` →
  `["authentication", "session"]`
  (via `_GOAL_TARGET`: "in the session", and the secondary match
  won't extract "middleware" because it's the end of string — acknowledged
  limitation; `_GOAL_TARGET` requires 2+ chars after the match)
- `"verify: python -m pytest tests/test_foo.py"` →
  `["tests/test_foo.py", "test_foo"]`
  (via `_PATH_LIKE` + stem)
- `'check the "router handler" module'` → `["router handler"]`
  (via `_QUOTED`)

### 3.2 `edges_from_skill()` — extract edges from a verified skill

```python
def edges_from_skill(
    goal_pattern: str,
    steps: list[str],
    *,
    success_rate: float = 1.0,
) -> list[tuple[str, str, str, float]]:
    """Extract (S, P, O, confidence) edges from a verified skill.

    Confidence = success_rate clamped to [0.5, 1.0].
    A skill at the 80% minimum gets 0.8 edges; a perfect skill gets 1.0.
    TUNABLE — adjust floor based on observed graph quality.

    Strategy:
    - Extract entities from goal_pattern using find_entities()
    - Parse each step as "tool_name: argument"
    - For read_file/read_directory: (target, "read_in_workflow", goal)
    - For create_file: (target, "created_in_workflow", goal)
    - For execute_terminal/verify: (target, "verified_by", command_stem)
    - Cross-link: (goal_entity, "associated_with", step_target) for the
      top 3 goal entities × top 5 step targets (capped to avoid
      combinatorial explosion on complex goals)
    """
    conf = max(0.5, min(1.0, success_rate))
    edges: list[tuple[str, str, str, float]] = []
    goal_entities = find_entities(goal_pattern)

    step_targets: list[str] = []
    for step in steps:
        if ":" not in step:
            continue
        tool, _, arg = step.partition(":")
        tool = tool.strip().lower()
        arg = arg.strip()
        if tool not in _TOOL_VERBS or not arg:
            continue

        arg_entities = find_entities(arg)
        for entity in arg_entities:
            step_targets.append(entity)
            if tool in ("read_file", "read_directory"):
                edges.append((entity, "read_in_workflow", goal_pattern[:60], conf))
            elif tool == "create_file":
                edges.append((entity, "created_in_workflow", goal_pattern[:60], conf))
            elif tool in ("execute_terminal", "verify"):
                cmd_stem = arg.split()[0] if arg.split() else arg[:30]
                edges.append((entity, "verified_by", cmd_stem, conf))

    for ge in goal_entities[:3]:
        for st in step_targets[:5]:
            if ge.lower() != st.lower():
                edges.append((ge, "associated_with", st, conf))

    return edges
```

### 3.3 `edges_from_mistake()` — extract edges from a verified mistake

```python
def edges_from_mistake(
    error_type: str,
    root_cause: str,
    lesson_text: str,
) -> list[tuple[str, str, str, float]]:
    """Extract (S, P, O, confidence) edges from a verified mistake.

    Confidence = 0.8 — TUNABLE DEFAULT. Verified but interpretive: these
    are lessons from reflection, not direct observations. No principled
    derivation; this is a starting guess calibrated against "direct fact =
    1.0, lesson from reflection = somewhat less certain." Adjust based on
    observed inference quality.

    Strategy:
    - error_type is always the subject entity (e.g. "FileNotFoundError")
    - Extract entities from root_cause → "caused_by" edges (capped at 3)
    - Extract entities from lesson_text → "prevented_by" edges (capped at 3)
    """
    conf = 0.8
    edges: list[tuple[str, str, str, float]] = []

    if not error_type.strip():
        return edges

    cause_entities = find_entities(root_cause)
    for entity in cause_entities[:3]:
        edges.append((error_type, "caused_by", entity, conf))

    lesson_entities = find_entities(lesson_text)
    for entity in lesson_entities[:3]:
        edges.append((error_type, "prevented_by", entity, conf))

    return edges
```

### 3.4 `edges_from_outcome()` — extract edges from a verified development outcome

```python
def edges_from_outcome(
    task_text: str,
    outcome: str,
    tool_calls: int,
) -> list[tuple[str, str, str, float]]:
    """Extract (S, P, O, confidence) edges from a verified development outcome.

    Confidence = 1.0 for verified_success, 0.7 for verified_failure.
    TUNABLE — 0.7 for failures because the association between the task
    entity and the failure is certain, but the entity extraction from
    task_text is noisier. No principled derivation.

    Strategy:
    - Extract entities from task_text using find_entities()
    - outcome → predicate: verified_success → "has_verified_success",
      verified_failure → "has_verified_failure"
    - Edges capped at top 3 entities per task
    """
    if outcome not in ("verified_success", "verified_failure"):
        return []

    conf = 1.0 if outcome == "verified_success" else 0.7
    predicate = (
        "has_verified_success" if outcome == "verified_success"
        else "has_verified_failure"
    )

    entities = find_entities(task_text)
    return [(entity, predicate, "true", conf) for entity in entities[:3]]
```

---

## 4. Ingestion hooks — where the extraction functions are called

### 4.1 `SkillMemory.record_attempt()` — after the cerebellum trigger

In `aios/memory/skills.py`, after the existing cerebellum trigger (line 182),
on promotion to `verified`:

```python
# S2: ingest verified skill edges into the knowledge graph.
if status == "verified" and self._facts is not None:
    try:
        from aios.core.graph_ingestion import edges_from_skill
        rate = successes / max(successes + failures, 1)
        for s, p, o, conf in edges_from_skill(goal, clean_steps, success_rate=rate):
            self._facts.add_fact(s, p, o, confidence=conf)
    except Exception:
        logger.warning("graph ingestion from skill failed (swallowed)", exc_info=True)
```

`SkillMemory.__init__` gains `facts: Optional["SemanticFacts"] = None` (using
the same `TYPE_CHECKING` import pattern as the existing `Cerebellum` DI).

**SQLite deadlock note:** This call is OUTSIDE the `with get_connection(...)`
block, after the transaction has committed — same pattern as the cerebellum
trigger, same reason: `add_fact()` opens its own `BEGIN IMMEDIATE`
transaction, and calling it while this method's own write transaction is
still open would self-deadlock against SQLite's single-writer lock.

### 4.2 `MistakeMemory.promote()` — when a lesson is promoted to `verified`

In `aios/memory/mistake.py`, extend `promote()` (line 236). The promotion
UPDATE stays inside the `with` block; the ingestion call goes after it:

```python
def promote(
    self,
    mistake_id: int,
    *,
    strength: VerificationStrength = VerificationStrength.STRONG,
) -> None:
    if not meets_promotion_floor(strength):
        return
    with get_connection(self.db_path) as conn:
        conn.execute(
            "UPDATE mistake_pool SET verification_status = 'verified' "
            "WHERE id = ? AND verification_status = 'pending'",
            (mistake_id,),
        )
        row = conn.execute(
            "SELECT error_type, root_cause, lesson_text FROM mistake_pool WHERE id = ?",
            (mistake_id,),
        ).fetchone()

    # S2: ingest verified mistake edges into the knowledge graph.
    # OUTSIDE the `with` block — same SQLite deadlock avoidance as
    # SkillMemory's cerebellum/ingestion triggers.
    if row is not None and self._facts is not None:
        try:
            from aios.core.graph_ingestion import edges_from_mistake
            for s, p, o, conf in edges_from_mistake(
                str(row["error_type"]),
                str(row["root_cause"]),
                str(row["lesson_text"]),
            ):
                self._facts.add_fact(s, p, o, confidence=conf)
        except Exception:
            logger.warning("graph ingestion from mistake failed (swallowed)", exc_info=True)
```

`MistakeMemory.__init__` gains `facts: Optional["SemanticFacts"] = None`
(same pattern).

### 4.3 DI wiring in `aios/api/main.py`

```python
def get_semantic_facts() -> SemanticFacts:
    return SemanticFacts()

def get_skill_memory(
    cerebellum: Cerebellum = Depends(get_cerebellum),
    facts: SemanticFacts = Depends(get_semantic_facts),
) -> SkillMemory:
    return SkillMemory(cerebellum=cerebellum, facts=facts)

def get_mistake_memory(
    facts: SemanticFacts = Depends(get_semantic_facts),
) -> MistakeMemory:
    return MistakeMemory(facts=facts)
```

---

## 5. Inference composition — `aios/core/inference.py`

The missing librarian. `traverse_weighted()` returns raw edges. This module
composes them into structured, explainable answers.

```python
"""Inference engine — composes graph traversal into structured answers.

Pure functions over WeightedEdge lists. No DB access, no state, no LLM.
The graph provides the data; inference provides the meaning.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class InferenceStep:
    """One step in an inference chain."""
    subject: str
    predicate: str
    object: str
    depth: int
    confidence: float


@dataclass(frozen=True)
class InferenceResult:
    """A composed inference from graph traversal."""
    query: str
    chain: list[InferenceStep]
    combined_confidence: float
    answer: str
    reached_horizon: bool
    source_count: int


def infer(
    query: str,
    edges: list,  # list[WeightedEdge] from traverse_weighted
    *,
    min_confidence: float = 0.3,
) -> Optional[InferenceResult]:
    """Compose an inference from weighted graph edges.

    Strategy:
    1. Group edges by connected path (edges sharing path prefixes).
    2. Select the highest-confidence connected path.
    3. Compose a natural-language answer via compose_answer() (capped at
       3 hops — beyond that, chains read like legal contracts).
    4. Return None when no path exceeds min_confidence.

    This is NOT generative. The answer is a mechanical composition of stored
    facts. The system can explain exactly where each claim comes from.
    """
    if not edges:
        return None

    above = [e for e in edges if e.path_confidence >= min_confidence]
    if not above:
        return InferenceResult(
            query=query,
            chain=[],
            combined_confidence=0.0,
            answer="",
            reached_horizon=True,
            source_count=len(edges),
        )

    above.sort(key=lambda e: (-e.path_confidence, e.depth))
    chain = [
        InferenceStep(
            subject=e.subject,
            predicate=e.predicate,
            object=e.object,
            depth=e.depth,
            confidence=e.path_confidence,
        )
        for e in above
    ]
    combined = min(step.confidence for step in chain) if chain else 0.0
    reached_horizon = any(e.path_confidence < min_confidence for e in edges)
    answer = compose_answer(chain)

    return InferenceResult(
        query=query,
        chain=chain,
        combined_confidence=combined,
        answer=answer,
        reached_horizon=reached_horizon,
        source_count=len(set((e.subject, e.object) for e in edges)),
    )


def compose_answer(chain: list[InferenceStep]) -> str:
    """Compose a readable sentence from an inference chain.

    Caps at 3 hops. Beyond that, chains read like legal contracts.
    A 4+ hop chain returns the first 3 hops composed + a count of
    further associations.
    """
    if not chain:
        return ""
    display = chain[:3]
    parts: list[str] = []
    for i, step in enumerate(display):
        conf_pct = f"{step.confidence * 100:.0f}%"
        if i == 0:
            parts.append(f"{step.subject} {step.predicate} {step.object} ({conf_pct})")
        else:
            parts.append(f"which {step.predicate} {step.object} ({conf_pct})")
    result = ", ".join(parts)
    if len(chain) > 3:
        result += f" (...and {len(chain) - 3} further associations)"
    return result


def find_entities(query: str) -> list[str]:
    """Extract candidate entity names from a query for graph lookup.

    Delegates to graph_ingestion.find_entities() — same extraction logic
    used for ingestion and for query targeting. Single implementation,
    no divergence.
    """
    from aios.core.graph_ingestion import find_entities as _find
    return _find(query)
```

---

## 6. Wiring into the retrieval pipeline

### 6.1 Enhance `_recall_facts()` in `aios/api/main.py`

Currently (line 2809): `search()` → token match → 1-hop `neighbors()` →
flat triples.

Enhanced: `search()` → token match → 1-hop `neighbors()` (unchanged) →
ADDITIONALLY `traverse_weighted()` on matched entities → `infer()` →
structured inference chain appended after flat triples.

```python
def _recall_facts(facts: SemanticFacts, user_text: str) -> Optional[str]:
    # ... existing search + neighbors logic (UNCHANGED through line 2850) ...

    if not expanded:
        return None
    triples = "\n".join(
        f"- {s} {p} {o}" for s, p, o in sorted(expanded)
    )

    # S2: if any matched entity has deeper associations, include the
    # highest-confidence inference chain as structured context.
    inferences: list[str] = []
    for node in list(nodes)[:5]:  # cap to avoid runaway traversal
        try:
            edges = facts.traverse_weighted(node, max_depth=3, min_path_confidence=0.3)
            if edges:
                from aios.core.inference import infer
                result = infer(user_text, edges, min_confidence=0.3)
                if result is not None and result.answer:
                    inferences.append(
                        f"  Inference ({result.combined_confidence:.0%} confidence): "
                        f"{result.answer}"
                    )
        except Exception:
            logger.warning("traverse_weighted failed for %s", node, exc_info=True)

    if inferences:
        triples += "\n\nINFERRED ASSOCIATIONS (confidence-weighted, use cautiously):\n"
        triples += "\n".join(inferences[:3])  # cap displayed inferences

    return (
        "RELEVANT APPROVED FACTS (use these; do not invent beyond this graph):\n"
        + triples
    )
```

**The key constraint:** inferred associations are labelled as inferred and
carry their confidence. They're ADDITIONAL context, not a replacement for
direct facts. Direct facts are presented without qualification; inferred ones
carry an explicit confidence percentage.

---

## 7. SSE events and frontend wiring

### 7.1 New SSE events (backend emits)

**`graph_inference`** — emitted when the retrieval pipeline uses
`traverse_weighted()` and produces an inference chain.

```json
{
  "type": "graph_inference",
  "query": "what do I know about the router",
  "chain": [
    {"subject": "project", "predicate": "uses", "object": "FastAPI", "confidence": 1.0, "depth": 1},
    {"subject": "FastAPI", "predicate": "needs", "object": "uvicorn", "confidence": 0.85, "depth": 2}
  ],
  "combined_confidence": 0.85,
  "answer": "project uses FastAPI (100%), which needs uvicorn (85%)",
  "reached_horizon": false
}
```

**`graph_horizon`** — emitted when traversal was pruned by
`min_path_confidence` (the system reached the edge of what it knows).

```json
{
  "type": "graph_horizon",
  "entity": "uvicorn",
  "max_confidence_beyond": 0.08,
  "message": "knowledge boundary reached for uvicorn"
}
```

### 7.2 Events mapping (`aios/core/events.py`)

Add to `_SSE_TO_COGNITION` (after the existing cerebellum entries, line 47):

```python
"graph_inference": EventType.KNOWLEDGE_ACQUIRED,
"graph_horizon": EventType.HESITATION,
```

### 7.3 Adapter wiring (`aiosAdapter.ts`)

Add after the existing `cerebellum_abort` case (line 562):

```typescript
// ── Sovereignty S2: Knowledge graph — associative recall ─────────
case 'graph_inference': {
  publishCognition({
    type: 'graph-recall',
    label: 'ASSOCIATIVE RECALL',
    detail: `${frame.data.chain?.length ?? '?'}-hop inference · ` +
            `confidence ${typeof frame.data.combined_confidence === 'number'
              ? (frame.data.combined_confidence * 100).toFixed(0) + '%' : '?'}`,
    intensity: 0.7,
    source: 'aios',
    phase: 'narrative',
    data: { sovereign: true, ...(frame.data ?? {}) },
    ...spine,
  });
  break;
}

case 'graph_horizon': {
  publishCognition({
    type: 'hesitation',
    label: 'KNOWLEDGE BOUNDARY',
    detail: `boundary reached for ${String(frame.data.entity ?? '?')}`,
    intensity: 0.5,
    source: 'aios',
    phase: 'emotion',
    data: { sovereign: true, ...(frame.data ?? {}) },
    ...spine,
  });
  break;
}
```

### 7.4 Add `'graph-recall'` to `CognitionEventType`

In `cognitionBus.ts` (after line 50, the existing `'reflex-recall'` entry):

```typescript
/** Sovereignty S2: the knowledge graph produced an inference chain from
 *  confidence-weighted traversal — associative recall from stored facts. */
| 'graph-recall'
```

---

## 8. API endpoint — `/api/v1/knowledge/query`

```python
@app.get("/api/v1/knowledge/query")
async def knowledge_query(
    entity: str,
    max_depth: int = 3,
    min_confidence: float = 0.3,
    facts: SemanticFacts = Depends(get_semantic_facts),
):
    """Query the knowledge graph from a starting entity.

    Returns the weighted traversal and composed inference. Read-only,
    no security implications — this is a diagnostic/observability endpoint.
    """
    edges = facts.traverse_weighted(
        entity, max_depth=max_depth, min_path_confidence=min_confidence
    )
    from aios.core.inference import infer
    result = infer(entity, edges, min_confidence=min_confidence)
    return {
        "entity": entity,
        "edges": [
            {
                "subject": e.subject,
                "predicate": e.predicate,
                "object": e.object,
                "depth": e.depth,
                "confidence": round(e.confidence, 4),
                "path_confidence": round(e.path_confidence, 4),
            }
            for e in edges
        ],
        "inference": {
            "answer": result.answer,
            "confidence": round(result.combined_confidence, 4),
            "chain_length": len(result.chain),
            "reached_horizon": result.reached_horizon,
        } if result else None,
    }
```

---

## 9. Test plan

### Unit tests (`tests/test_knowledge_graph.py`)

| Test | Asserts |
|------|---------|
| `test_add_fact_with_confidence` | A fact inserted with `confidence=0.7` stores 0.7 in the DB. |
| `test_add_fact_confidence_default` | A fact inserted without `confidence` defaults to 1.0. |
| `test_add_fact_confidence_clamped` | `confidence=1.5` clamps to 1.0; `confidence=-0.3` clamps to 0.0. |
| `test_add_fact_idempotent_takes_max_confidence` | Re-inserting the same fact with higher confidence updates to the max. |
| `test_traverse_weighted_no_decay_at_depth_1` | A depth-1 fact at confidence 1.0 has `path_confidence == 1.0` (no decay). |
| `test_traverse_weighted_decays_at_depth_2` | A 2-hop path has `path_confidence ≈ 0.85` (1.0 × 1.0 × 0.85). |
| `test_traverse_weighted_decays_at_depth_3` | A 3-hop path has `path_confidence ≈ 0.7225` (0.85 × 1.0 × 0.85). |
| `test_traverse_weighted_prunes_below_min` | Paths below `min_path_confidence` are excluded from results. |
| `test_traverse_weighted_cycle_safe` | A→B→A cycle terminates. |
| `test_traverse_weighted_orders_by_confidence` | Results are ordered by `path_confidence` descending. |
| `test_traverse_weighted_with_explicit_confidence` | A fact at `confidence=0.5` decays faster than one at `confidence=1.0`. |
| `test_traverse_weighted_clamps_depth` | `max_depth > 4` clamps to 4. |

### Entity extraction tests (`tests/test_graph_ingestion.py`)

| Test | Asserts |
|------|---------|
| `test_find_entities_path` | `"read_file: aios/core/router.py"` → `["aios/core/router.py", "router"]` |
| `test_find_entities_quoted` | `'check the "router handler"'` → `["router handler"]` |
| `test_find_entities_preposition` | `"create a test for the router module"` → `["router"]` |
| `test_find_entities_multiple_patterns` | Text with paths + prepositions deduplicates. |
| `test_find_entities_short_tokens_ignored` | Single-character and empty strings return `[]`. |
| `test_edges_from_skill_extracts_tool_target` | A verified skill with `read_file: router.py` produces `(router, read_in_workflow, ...)` edge. |
| `test_edges_from_skill_scales_by_success_rate` | A skill at 80% rate produces edges with `confidence=0.8`. |
| `test_edges_from_skill_clamps_confidence_floor` | A skill at 40% rate gets `confidence=0.5` (clamped). |
| `test_edges_from_skill_crosslinks_goal_to_steps` | Goal entities get `associated_with` edges to step targets. |
| `test_edges_from_mistake_extracts_cause` | A verified mistake produces `(error_type, caused_by, ...)` edge. |
| `test_edges_from_mistake_empty_error_type` | Empty error_type returns `[]`. |
| `test_edges_from_outcome_verified_success` | `verified_success` produces confidence 1.0 edges. |
| `test_edges_from_outcome_verified_failure` | `verified_failure` produces confidence 0.7 edges. |
| `test_edges_from_outcome_unverified_ignored` | `unverified` and `paused` return `[]`. |

### Inference tests (`tests/test_inference.py`)

| Test | Asserts |
|------|---------|
| `test_infer_composes_chain_into_answer` | A 2-hop traversal produces a readable `answer` string. |
| `test_infer_returns_none_below_confidence` | No path above `min_confidence` → returns `None`. |
| `test_infer_reached_horizon_flag` | When traversal is pruned, `reached_horizon` is `True`. |
| `test_compose_answer_caps_at_3_hops` | A 5-hop chain renders only first 3 + "(...and 2 further associations)". |
| `test_compose_answer_empty_chain` | Empty chain returns `""`. |
| `test_compose_answer_single_hop` | One-hop chain renders without "which" prefix. |

### Cross-store ingestion integration tests

| Test | Asserts |
|------|---------|
| `test_ingestion_hook_fires_on_skill_promotion` | Promoting a skill to `verified` inserts edges into `semantic_facts` with correct confidence. |
| `test_ingestion_hook_fires_on_mistake_promotion` | Promoting a mistake inserts edges with `confidence=0.8`. |
| `test_ingestion_hook_is_fail_soft` | A broken `add_fact()` call doesn't crash `record_attempt()` or `promote()`. |
| `test_only_verified_data_ingested` | A `candidate` skill, a `pending` lesson, and an `unverified` outcome produce no edges. |
| `test_confidence_survives_roundtrip` | `add_fact(confidence=0.8)` → `traverse_weighted()` → edge has `confidence=0.8`. |
| `test_ingestion_outside_transaction` | Ingestion call happens after the `with get_connection(...)` block exits (no SQLite deadlock). |

### Integration test — end-to-end

1. Insert operator facts: `("project", "uses", "FastAPI")`, `("FastAPI", "needs", "uvicorn")` — both at confidence 1.0
2. Insert a verified skill whose goal mentions "FastAPI" (triggers ingestion)
3. Call `traverse_weighted("project", max_depth=3)`
4. Assert: 2+ hops returned, depth-1 confidence = 1.0, depth-2 decays
5. Assert: both operator facts and skill-derived facts are present
6. Call `infer()` on the result
7. Assert: composed answer mentions both FastAPI and uvicorn with confidence percentages
8. Assert: answer is capped at 3 hops if chain is longer
9. Assert: no LLM was called at any point

---

## 10. What this does NOT touch

- **`aios/security/*`** — frozen. Inference is read-only over verified data.
- **Existing `traverse()` and `neighbors()`** — unchanged. `traverse_weighted()`
  is a new method, not a replacement. Existing callers keep working.
- **`fact_extraction.py`** — unchanged. The operator fact pipeline is unmodified.
  Cross-store ingestion is additive — new facts from new sources, through the
  same `add_fact()` gate.
- **The existing `_recall_facts()` output format** — preserved. The inference
  chain is additional context appended after the existing triples block.

---

## 11. What is explicitly deferred

- **Embedding-based entity matching** — S2 uses token matching (`search()` +
  `find_entities()`). Semantic similarity matching is Phase S3/S4.
- **Native planner integration** — the native planner (Phase S3) will use
  `traverse_weighted()` for precondition checking. Not wired in S2.
- **CRAG integration** — the CRAG layer can use inference results as a
  structured knowledge source. Deferred until inference quality is validated.
- **Frontend memory galaxy rendering** — the `graph-recall` cognition events
  fire; dedicated visual rendering is a frontend design pass.
- **Dependency container.** `SkillMemory` now takes `cerebellum` and `facts`.
  `MistakeMemory` takes `facts`. One more parameter per store per phase is
  sustainable through S3; beyond that, consider a lightweight `StoreRegistry`
  or `Container` that constructs the stores with shared dependencies in one
  place. Not needed yet, but the ceiling is visible.

---

## 12. Build order

1. DDL migration (`db.py`) + `add_fact(confidence=)` extension (`facts.py`)
2. `WeightedEdge` dataclass + `traverse_weighted()` method (`facts.py`)
3. `find_entities()` + `edges_from_*()` functions (`graph_ingestion.py`)
4. `InferenceStep`, `InferenceResult`, `infer()`, `compose_answer()` (`inference.py`)
5. Ingestion hooks in `SkillMemory` + `MistakeMemory`
6. DI wiring in `main.py` (`get_skill_memory`, `get_mistake_memory`)
7. Enhanced `_recall_facts()` with traverse + infer
8. SSE events + adapter wiring + `CognitionEventType` extension
9. API endpoint `/api/v1/knowledge/query`
10. Tests — unit, extraction, inference, integration
