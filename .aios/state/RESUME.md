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
**IN PROGRESS — Phase 4h: resumable in-chat YELLOW approval** (started, no code written yet; design locked below). Goal: when the agent hits a YELLOW command in the chat loop, pause and ask the human; on approval the command actually runs (instead of today's "needs approval / not run"). Backend-first + fully fake-tested; minimal frontend wire-up.

Exact plan (build in this order, `pytest` green before commit):
1. `aios/core/executor.py` already has `execute_approved(command)` (runs GREEN/YELLOW, still refuses RED) — reuse it. `ExecutionResult.status` ∈ OK/BLOCKED/REQUIRE_APPROVAL/TIMEOUT/ERROR.
2. `aios/agents/tool_agent.py`:
   - `__init__(..., approved_commands: Optional[list[str]] = None)` → `self.approved_commands = set(approved_commands or [])`.
   - Refactor `_execute`: add helper `_format_exec_result(result)` → maps OK→(out,"ok",bool(exit_code)), TIMEOUT/ERROR→(reason,"blocked",True), BLOCKED→(reason,"blocked",False). In `_execute(command)`: if `command in self.approved_commands` → `_format_exec_result(self.executor.execute_approved(command))`; else `r=self.executor.execute(command, session_id=...)`; if `r.status=="REQUIRE_APPROVAL"` → return `(r.reason, "approval", False)` (NEW status); else `_format_exec_result(r)`.
   - In `run()` tool-call block: after `output,status,failed = self._dispatch(...)`, if `status == "approval"` → `yield {"type":"human_required","tool":name,"command":args.get("command",""),"reason":output,"id":call_id}` then `return` (pause turn). Keep existing blocked/result/reflect branches for other statuses.
3. `aios/api/main.py`:
   - `GenerateRequest`: add `approved_commands: list[str] = Field(default_factory=list, alias="approvedCommands")` (+ keep `populate_by_name`).
   - Pass `approved_commands=req.approved_commands` into `ToolAgent(...)`.
   - In the SSE map, handle agent event `human_required` → `yield _sse("human_required", {"input": {"commands": [ev["command"]], "explanation": ev["reason"]}, "text": f"Authorization required: {ev['reason']}", "requiresApproval": True})`. (Frontend already handles `human_required` → `setPendingAction(data.input)`.)
4. Tests:
   - `tests/test_tool_agent.py`: unapproved YELLOW (`_tool_call("execute_terminal", {"command":"pip install flask"})`) → events contain a `human_required` and loop stops (no `done`); with `approved_commands=["pip install flask"]` → runs via FakeRunner → `tool_result`. (`classify("pip install flask")` = YELLOW.)
   - `tests/test_api.py`: a `FakeOllama.chat` variant that calls execute_terminal with a YELLOW command → `/api/generate` SSE contains `event: human_required`.
5. Frontend (minimal, lint+build): `App.jsx` — add `approvedCommands` state (array); include `approvedCommands` in the `/api/generate` body; extract a `streamGenerate(messages)` helper from `handleSendMessage`; on `handleApproveAction`, append `pendingAction.commands` to `approvedCommands`, clear pendingAction, and re-call `streamGenerate(convHistory)` to resume the turn with the command now whitelisted. (convHistory ends at the last user msg because the paused assistant turn was never recorded on `done`.)

After: 89→~93 tests green, commit "Phase 4h: resumable in-chat YELLOW approval", append an Experience Object, update this file.

Deferred (not this step): (a) live e2e demo pass (RAM-gated — needs `llama3.2:3b` loaded); (c) offline voice Whisper+Piper; (d) Docker + Prometheus/Grafana.

## Open approvals / blockers
- Live happy-path is gated by host RAM (7.5 GB). Close other apps so `llama3.2:3b` fits (~4 GB free). `AIOS_INDEX_CHAT` and `AIOS_REFLECT_ON_FAILURE` each add an extra model load — set them `false` on tight runs.

## Active files  (Phase 4h — none edited yet; will touch:)
- `aios/agents/tool_agent.py` · `aios/api/main.py` · `tests/test_tool_agent.py` · `tests/test_api.py` · `frontend/src/App.jsx`

## Notes not yet promoted to memory
- Run backend: `.venv\Scripts\python -m uvicorn aios.api.main:app --port 8000`. Run frontend: `cd frontend; npm run dev` (:5173). Tests: `.venv\Scripts\python -m pytest -q`.
- The repo uses per-phase commits on `master` (not `main`). Keep that cadence.

---
_Last updated: 2026-06-02 by Claude Code (Phase 4g checkpoint)_
