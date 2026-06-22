# `legacy/` — quarantined dead / orphaned code (NOT part of the live system)

> Quarantined 2026-06-15 (renovation P0-2 + P0-5, from `HIDDEN_KNOWLEDGE.md`).
> Nothing here is imported or run by the live AI-OS. Retained for history only.
> **Do not wire any of this back in without a deliberate, reviewed decision.**

The live system is the Python backend under `aios/` (FastAPI + the security spine,
cognition loop, memory tiers) and the React frontend under `frontend/`. Everything
in this folder is a vestige of an earlier generation or an orphaned standalone script
that operated on a **dead root database** (`orchestrator_memory.sqlite`), not the live
stores (`data/aios_memory.db`, `data/aios_audit.db`).

| Item | What it was | Why quarantined |
|------|-------------|-----------------|
| `legacy_node/` | A full parallel OLD Node implementation (security gateway, knowledge graph, reflection engine, its own `package-lock.json` + Node tests) | Zero live imports. It mirrors `aios/` closely enough to be mistaken for canon — and it holds the knowledge-graph feature the Python side downscoped (see `PLAN.md` G2 / the SQLite recursive-CTE path). |
| `reset_audit_chain.py` | "Reset the tamper audit chain" CLI | **Was a silent no-op on the LIVE ledger** — it cleared `tamper_audit_trail` in the orphaned root DB while the live chain lives in `data/aios_audit.db`, printing success while changing nothing the product verifies. Resetting the live, security-critical, hash-chained ledger is not a casual script; if ever needed, build a deliberate, audited operation. |
| `vector_memory_setup.py` | Builds `semantic_memory` + a FAISS index in the root DB | Guardless `DROP TABLE` on the orphaned legacy store; the live memory uses `data/aios_memory.db`. |
| `hybrid_search.py` | Standalone RAG CLI over the root DB/index | Dead duplicate; the live impl is `aios.memory.retrieval.hybrid_search`. |
| `ingest_knowledge.py`, `ingest_update.py` | Legacy ingest into the root store | Orphaned from the running system; `ingest_update.py` was hardwired to a single file. |
| `extract_text.py` | Older hardcoded PDF→md extractor (PyPDF2) | Dead duplicate of the live, argv-driven `pdf_util.py` (kept in the repo root). |

If you genuinely need one of these capabilities, port it into `aios/` against the
**live** stores with tests, rather than reviving the script in place.
