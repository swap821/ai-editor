# AI-OS — Supervised, Security-Gated, Memory-Driven Agent

A local-workspace AI operating system modeled on the Jarvis paradigm: an LLM agent
that plans, executes, and edits inside an IDE workspace, but **never** modifies the
host without passing a deterministic security gateway and (for sensitive actions)
explicit human approval. Every gated action is recorded in a tamper-evident,
SHA-256 hash-chained audit ledger.

> **Honest status:** This is an actively-implemented MVP (~60%+ of the blueprint).
> Inference runs on **AWS Bedrock** (not local Ollama as the original blueprint
> described). The working story is "cloud inference + local-first memory & security."

## Architecture (what actually runs)

```
Frontend (React/Vite + Monaco)  ──HTTP──▶  Express server (server.js)
                                              │
        ┌──────────────┬──────────────┬──────┴───────┬──────────────┐
        ▼              ▼              ▼              ▼              ▼
 Security Gateway  Confidence    Memory (SQLite   Audit Log     Reflection
 (fail-closed,     Filter        + FAISS hybrid   (SHA-256      (LLM root-cause
  3-zone)          (0.72 gate)   retrieval)       hash chain)    → Mistake DB)
        │                                                          │
        ▼                                                          ▼
 Bedrock LLM (Converse API) ◀── agent tool-use loop (terminal, files, KB graph, web)
```

## Core modules

| File | Responsibility |
|------|----------------|
| `server.js` | Express API + agentic tool-use loop (Bedrock Converse) |
| `securityGateway.js` | Deterministic **fail-closed** 3-zone classifier (GREEN/YELLOW/RED), prompt-injection + secret + network + traversal detection, per-session rate limiting |
| `scopeLock.js` | Path canonicalization + scope-root enforcement (blocks `../../etc/passwd`, symlink escape, out-of-scope absolute paths) |
| `confidenceFilter.js` | Independent 0.72 confidence gate — low-confidence steps escalate to human review regardless of zone |
| `auditLogger.js` | Append-only SHA-256 hash-chained ledger + `verify_chain()` tamper detection |
| `secretScanner.js` | Entropy/regex credential redaction before any payload is logged |
| `reflectionEngine.js` | Post-failure root-cause analysis → structured lesson in the Mistake DB |
| `rollbackEngine.js` | git-stash / snapshot + restore |
| `knowledgeGraph.js` | SQLite entity-relation triples |
| `database.js` | SQLite schema: episodic, semantic, mistake_pool, audit ledger (WAL mode) |
| `hybrid_search.py` | BM25 + FAISS + temporal-decay hybrid retrieval (`R = 0.25·BM25 + 0.45·FAISS + 0.30·recency`) |

## API endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/generate` | Main agent loop (tool use, memory recall, security gating) |
| POST | `/api/terminal` | Human-issued command, security-gated + audited |
| POST | `/api/v1/security/classify` | Deterministic zone classification for an action |
| POST | `/api/v1/memory/search` | Hybrid BM25+FAISS memory retrieval |
| POST | `/api/v1/plan` | Goal → sub-tasks with per-step confidence, gated at 0.72 |
| POST | `/api/v1/reflect` | Analyse a failed command, store a lesson |
| GET  | `/api/v1/audit/verify` | Verify the hash chain has not been tampered with |

## Setup

```bash
# 1. Backend deps
npm install

# 2. Environment (.env)
#    AWS_REGION=us-east-1
#    AWS_BEARER_TOKEN_BEDROCK=...

# 3. (One-time) build the vector memory + ingest the blueprint
npm run memory:init      # python vector_memory_setup.py
npm run memory:ingest    # python ingest_knowledge.py

# 4. Run
npm start                # backend on :5000  (override with PORT=5077 npm start)
cd frontend && npm install && npm run dev
```

## Tests

```bash
npm test     # node --test: 23 cases across security, audit, confidence, scope
```

Covered: deterministic zoning, fail-closed defaults, prompt-injection/secret/traversal
blocking, rate limiting, hash-chain integrity + tamper detection, the 0.72 confidence
boundary (0.719 escalates, 0.720 passes), and scope enforcement.

## Security invariants (verified by tests)

- **Fail-closed:** empty/ambiguous/exception → RED, never permissive.
- **Deterministic:** same input always yields the same zone (no LLM judgement).
- **Immutable audit:** altering any ledger entry breaks `verify_chain()` at that entry.
- **Scope-locked:** all file paths resolved to absolute + real path before the scope check.
- **Orthogonal gating:** security zone and confidence (0.72) are independent layers.

## Notes

- `reset_audit_chain.py` — opt-in, non-destructive reset of the live ledger to a clean
  genesis (archives existing rows first). The app itself will **refuse** to clear the
  ledger via any agent action — audit immutability is enforced, not optional.
- `semantic_memory` schema is shared between `database.js` and the Python scripts; keep
  the columns (`text_content`, `vector_id`) in sync or FAISS retrieval breaks.
