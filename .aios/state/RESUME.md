# RESUME MANIFEST — .aios/state/RESUME.md
<!--
  Claude Code OVERWRITES this file at every checkpoint (see CLAUDE.md §IV).
  It is the single source of truth a future session reads first.
  Keep it under one screen. Long history belongs in experiences.jsonl, not here.
-->

## Current goal
Drive the local-first AI-OS (Python `aios/` backend + React `frontend/`) from its
current state to a polished, demoable MVP per the v4 blueprint — memory-driven,
security-gated, human-supervised, self-correcting.

## Status  (read from the CODE, not the blueprint's "~35%")
- **Reality: the backend is ~75–80% of the blueprint MVP, well past the doc's estimate.**
- Stack: Python 3.12 `.venv`, FastAPI + uvicorn, SQLite (WAL) + FAISS, Ollama (local LLM). Node backend archived on branch `legacy-node` / tag `legacy-node-v1`.
- Tests: **89 passed, 1 skipped** (`.venv/Scripts/python -m pytest -q`). The 1 skip = Windows symlink-privilege case (environmental, not a failure).
- Last completed + verified step: **Phase 4g committed (`b380b6b`)** — cross-session lesson recall.

### BUILT & committed (per-phase commits on `master`)
- **Memory L2/L3/L4** — episodic, semantic (FAISS `IndexIDMap`), mistake pool; hybrid BM25+FAISS+decay retrieval `R = 0.25·BM25 + 0.45·FAISS + 0.30·e^(−0.05·Δt)`. `[aios/memory/]`
- **Security gateway** — deterministic fail-closed 3-zone (regex + scope-lock canonicalization + Shannon-entropy secret scan). `[aios/security/]`
- **Audit log** — SHA-256 hash chain, secret-scrubbed payloads, O(n) verify endpoint. `[aios/security/audit_logger.py]`
- **Reflection agent** — LLM post-mortem → Mistake pool (strict JSON, delta clamp, recurrence, pending→verified). `[aios/agents/reflection_agent.py]`
- **Planner** (0.72 confidence gate) · **Executor** (gateway-guarded, sandboxed, audited) · **Rollback** (GitPython snapshots). `[aios/core/, aios/agents/]`
- **FastAPI** — `/health`, `/api/v1/{memory/search, security/classify, audit/verify, reflect, plan, execute, approval/req, rollback, models/local}`, `/api/generate` (SSE), `/api/terminal`. `[aios/api/main.py]`
- **React frontend wired to FastAPI** (`:8000`, CORS), model picker lists installed Ollama models, Local/Cloud badge. `[frontend/]`
- **Agentic chat that acts + learns** — `/api/generate` runs a security-gated tool loop (read_file / read_directory / execute_terminal), recalls memory, persists + consolidates each turn into L2/L3, reflects on failures (🧠 lesson), promotes lessons pending→verified on a corrective success, and recalls a session's pending lessons across turns. `[aios/agents/tool_agent.py]`

## Next action  → do this first on resume
1. Decide the next build target. Recommended (highest leverage first):
   **(a) Live end-to-end demo pass** — start uvicorn + `npm run dev`, pull a small model (`ollama pull llama3.2:3b`), and exercise the full loop on a real task; capture any rough edges as experiences.
   Then candidate features: **(b)** resumable YELLOW approval inside the chat loop (currently "needs approval / not run"); **(c)** offline voice (Whisper STT + Piper TTS); **(d)** Docker compose + Prometheus/Grafana.

## Open approvals / blockers
- Live happy-path is gated by host RAM (7.5 GB). Close other apps so `llama3.2:3b` fits (~4 GB free). `AIOS_INDEX_CHAT` and `AIOS_REFLECT_ON_FAILURE` each add an extra model load — set them `false` on tight runs.

## Active files
- (idle — last work was `aios/agents/tool_agent.py`, `aios/api/main.py`, and the three test files, all committed in `b380b6b`.)

## Notes not yet promoted to memory
- Run backend: `.venv\Scripts\python -m uvicorn aios.api.main:app --port 8000`. Run frontend: `cd frontend; npm run dev` (:5173). Tests: `.venv\Scripts\python -m pytest -q`.
- The repo uses per-phase commits on `master` (not `main`). Keep that cadence.

---
_Last updated: 2026-06-02 by Claude Code (Phase 4g checkpoint)_
