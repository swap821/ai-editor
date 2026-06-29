# CRAG for GAGOS — Corrective Retrieval as the Organism's Metacognitive Gate

**Status:** Draft for operator review
**Date:** 2026-06-29
**Author:** Claude (Opus 4.8) with operator (swap821)
**Scope:** Add a Corrective-RAG layer to the organism's retrieval path — opt-in,
fail-closed, privacy-first, TDD'd in ablation-priority order.

---

## 1. Motivation

The organism already has real **RAG** (hybrid BM25 + FAISS + temporal decay,
`aios/memory/retrieval.py`) feeding generation context via `_recall_memory`
(`aios/api/main.py`). But like all plain RAG, it **trusts whatever the retriever
returns**. One noisy or irrelevant hit is injected verbatim into the prompt, and
the generator conditions on it — the exact mechanism behind retrieval-induced
hallucination.

CRAG (Yan et al., 2024) inserts a *metacognitive gate* between retrieval and
generation:

1. A lightweight **evaluator** scores the retrieved context for actual relevance
   (not just vector proximity).
2. A **tripartite router** acts on that score: **Correct** → refine locally,
   **Incorrect** → go external, **Ambiguous** → both.
3. **Decompose-then-Recompose** shatters context into sentences, drops the noise,
   and keeps only the "golden strips."

The published ablation is the load-bearing fact for our build order: removing
**knowledge refinement** cost **−5.1%** accuracy — *more than any routing pathway*
and more than adding web search. Refinement, not routing, is the prize.

## 2. Why this fits GAGOS specifically (the alignment)

Two of CRAG's own documented weaknesses are precisely GAGOS's constraints — and
that turns them into design clarity, not problems:

- **The T5-large evaluator needs expensive per-domain fine-tuning.** GAGOS's house
  style is *deterministic-first, local, transparent, fail-closed* (see
  `relevance.py`, the Council Queens). We will **not** ship a fine-tuned T5. The
  evaluator starts as the existing deterministic relevance score, with an *optional*
  injected local-LLM escalation for ambiguous cases — same pattern as
  `PlannerQueen`/`reason_king` (opt-in, clamped, fail-closed).

- **Web-search fallback breaks air-gapped / privacy-constrained systems.** GAGOS is
  local-first and privacy-first. So CRAG's "Incorrect → external" pathway maps onto
  the **privacy-gated cloud/`browse` burst we just shipped** — never a mandatory web
  call, opt-in, and skipped entirely in local-only mode. Because the ablation says
  *local refinement is the biggest win anyway*, the privacy-first path is also the
  highest-accuracy path. Rare alignment.

And the routing already exists in shape: **CRAG's tripartite routing is the same
machine as the local↔cloud privacy router** (`router_wiring.py`). *Correct* = refined
local memory; *Incorrect* = privacy-gated cloud/web; *Ambiguous* = both.

## 3. Honest current-state map

| CRAG component | GAGOS today | Gap |
|---|---|---|
| Retriever | ✅ hybrid BM25+FAISS+decay, explainable sub-scores (`retrieval.py`) | none |
| Relevance scoring | ✅ deterministic lexical `relevance(q,d)∈[0,1]` (`relevance.py`); evaluative Queens | exists, **not wired as a pre-generation gate** |
| Tripartite routing | 🟡 privacy local↔cloud router (just shipped) | not applied to *retrieval* |
| Decompose→Recompose | ❌ retrieved memory injected whole (`_recall_memory`) | **#1 ROI gap** |
| External corrective + query-rewrite | 🟡 `browse` tool + cloud burst | not wired as "Incorrect → external" |

**Integration seam:** `_recall_memory(query, top_k)` in `aios/api/main.py:2470`.
It calls `hybrid_search`, already splits **verified-trusted** vs **unverified**
hits, and returns a prompt-ready block. CRAG slots in *between* `hybrid_search` and
that block assembly. This is the one function the slices wrap.

## 4. Architecture

New module: **`aios/memory/crag.py`** — pure, deterministic-first, optional injected
LLM. No I/O, no globals; testable in isolation. Orchestration that touches external
providers stays in the api/core layer (privacy boundary unchanged).

```
                       ┌─────────────────────────────────────────────┐
 query ──► hybrid_search ─► hits ─► evaluate_retrieval(query, hits)   │
                       │                    │  RetrievalVerdict        │
                       │       ┌────────────┼────────────┐            │
                       │   CORRECT       AMBIGUOUS     INCORRECT       │
                       │      │              │             │           │
                       │  refine_context  refine + ext   external      │
                       │      │              │             │           │
                       │      └──────► recompose ◄─────────┘           │
                       │                    │                          │
                       └────────────► prompt-ready block ──► generation
```

### 4.1 Components & interfaces

```python
# aios/memory/crag.py
class CragAction(enum.Enum):
    CORRECT = "correct"        # local retrieval is good → refine & use
    AMBIGUOUS = "ambiguous"    # partial → refine local AND seek external
    INCORRECT = "incorrect"    # local is junk → drop, go external

@dataclass(frozen=True)
class RetrievalVerdict:
    action: CragAction
    score: float                       # max per-hit confidence in [0, 1]
    per_hit: list[float]               # explainable, like RetrievalResult sub-scores

def evaluate_retrieval(
    query: str,
    hits: Sequence[RetrievalResult],
    *,
    upper: float,                      # CORRECT if max >= upper
    lower: float,                      # INCORRECT if max <  lower
    judge: Callable[[str, str], float] | None = None,  # optional local-LLM escalation
) -> RetrievalVerdict: ...

def refine_context(
    query: str,
    documents: Sequence[str],
    *,
    keep: Callable[[str, str], bool] | None = None,  # None → deterministic relevance filter
    min_chars: int = 20,
) -> str:
    """Decompose into sentences (excerption), drop sub-min_chars fragments and
    non-relevant strips, recompose surviving strips. Pure; deterministic by default."""
```

- **Evaluator** defaults to a deterministic score derived from `relevance.py` +
  the hit's existing sub-scores. `judge` is an *optional* local-LLM claim-aware
  escalation used **only for the AMBIGUOUS band** (cost discipline), validated and
  clamped — it can sharpen but never fabricate a CORRECT.
- **Refiner** defaults to the deterministic `relevance` filter (no model). An
  optional `keep` callback allows a constrained local-LLM binary strip filter
  later, behind the same opt-in.

### 4.2 Integration (api layer)

`_recall_memory` gains a CRAG branch, gated by `config.CRAG` (default off — byte-for-
byte unchanged behavior when off):

```python
hits = hybrid_search(query, top_k)
if config.CRAG and hits:
    verdict = evaluate_retrieval(query, hits, upper=config.CRAG_UPPER, lower=config.CRAG_LOWER, judge=...)
    local = refine_context(query, [h.text for h in hits]) if verdict.action != INCORRECT else ""
    external = _corrective_external(query) if (config.CRAG_EXTERNAL and verdict.action != CORRECT) else ""
    return _compose(local, external) or None
# ...else the existing verified/unverified path unchanged
```

`_corrective_external` (Slice 3) = privacy-gated query-rewrite → cloud/`browse` →
`refine_context` again → strips. Default **off** (`AIOS_CRAG_EXTERNAL`).

## 5. Configuration (opt-in, fail-closed)

| Flag | Default | Meaning |
|---|---|---|
| `AIOS_CRAG` | off | master switch for the corrective path |
| `AIOS_CRAG_UPPER` | 0.6 | CORRECT threshold (operator-tunable, like ROUTER_*) |
| `AIOS_CRAG_LOWER` | 0.2 | INCORRECT threshold |
| `AIOS_CRAG_EXTERNAL` | off | allow the privacy-gated external corrective pathway |
| `AIOS_CRAG_LLM_JUDGE` | off | allow optional local-LLM escalation for AMBIGUOUS |

The paper tunes its thresholds on a `[−1,1]` learned-confidence scale; ours live on
`[0,1]` from a *different* (deterministic) scorer, so `0.6 / 0.2` are GAGOS starting
points to be tuned against the operator's corpus — **not** a direct port of the
paper's numbers. All flags default off → zero behavior change until enabled.

## 6. Error handling / fail-closed posture

- Any evaluator/refiner error → fall back to the **current** `_recall_memory`
  behavior (recall is "best-effort, never fatal" — preserved).
- Refinement that would drop *everything* → return the original verified/unverified
  block (never silently blank the context).
- External pathway obeys the existing privacy filter + `browse` approval gate; in
  local-only mode it is simply never invoked.
- The LLM judge is clamped: it may downgrade CORRECT→AMBIGUOUS but never upgrade a
  below-`lower` retrieval to CORRECT (same strengthen-only spirit as `reason_king`).

## 7. Build order (ablation-prioritized) & acceptance

- **Slice 1 — `refine_context` (decompose-then-recompose).** The −5.1% driver.
  Pure, deterministic, local, no model, no new flag dependency. *Tests:* sentence
  excerption + min-char drop; non-relevant strip drop; recompose order; empty/blank
  safety; never-blank-when-input-nonempty. *Accept:* token reduction on a noisy doc
  with the golden sentence retained.
- **Slice 2 — `evaluate_retrieval` + tripartite gate, wired into `_recall_memory`
  behind `AIOS_CRAG`.** *Tests:* threshold routing (CORRECT/AMBIGUOUS/INCORRECT);
  deterministic score from `relevance` + sub-scores; off-by-default no-op; fail-soft
  to legacy path; optional judge clamp. *Accept:* a junk retrieval is gated to
  INCORRECT and excluded.
- **Slice 3 — corrective external pathway** (query-rewrite + privacy-gated
  cloud/`browse`, re-refined). *Tests:* off by default; privacy filter applied;
  rewrite shape; external text re-refined through Slice 1; air-gap → never called.
  *Accept:* on INCORRECT with external enabled, refined external strips replace the
  dropped local context.

Each slice: RED→GREEN→commit, opt-in, adversarially reviewed before merge (the
Council-Queen cadence).

## 8. Risks & limitations (honest)

- **Threshold calibration is a living precision/recall tradeoff** (the paper's own
  caveat). Mitigation: operator-tunable flags + explainable `per_hit` scores so the
  decision is inspectable, not a black box.
- **Deterministic evaluator is weaker than a fine-tuned T5** on semantic relevance.
  Accepted tradeoff for v1 (no fine-tuning cost, transparent, privacy-safe); the
  optional local-LLM judge is the escalation path, and a fine-tuned evaluator can
  drop in behind the same `judge` interface later.
- **External pathway inherits open-web noise + privacy exposure.** Mitigation:
  default off, privacy-filtered, approval-gated, and re-refined before use.
- **Latency.** The paper measures ~+0.15s/instance. Deterministic refinement is
  cheaper; the LLM judge (opt-in) is the only real cost, scoped to the AMBIGUOUS
  band only.

## 9. Out of scope (v1)

Fine-tuned T5 evaluator; LangGraph-style cyclic re-evaluation loops; multi-source
external consensus. All are post-v1 extensions that fit behind the same interfaces.
