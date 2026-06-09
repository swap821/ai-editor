# RESUME MANIFEST

## Current goal
Ship a trustworthy local-first AI-OS MVP: supervised actions, evidence-backed
writes, reliable local-model routing, durable memory, and honest failure modes.

## Last completed and verified
2026-06-09 security/reliability hardening + live BREATHE proof are implemented
locally and uncommitted:
- Server-issued, expiring, session-bound, single-use approval capabilities replace
  client-authored `approvedCommands` / `approvedEdits` / `approvedCreations`.
  Redeemed grants exist server-side only for the paused replay chain and clear on
  completion/fresh turns.
- Frozen gateway now auto-executes only internally handled `echo`/`pwd`; unknown
  commands, shell composition, and interpreter/nested-shell escapes (`python -c`,
  PowerShell `-Command`, `cmd /c`, `node -e`, `sh -c`) are RED. Executor uses
  structured argv and `shell=False`.
- Self-apply rollback verifies restored bytes and reports rollback/status failures
  honestly; a successful source write is restored if status persistence fails.
- Semantic writes are serialized to prevent in-process FAISS lost updates.
  Chat-derived semantic memory is labeled/injected as unverified, never evidence.
- Frontend uses a stable per-browser session id, sends it to chat/terminal, resumes
  with capability tokens, and no longer overwrites the active virtual file when an
  ordinary fenced code block arrives.
- Prior uncommitted work remains: force-verify-after-write, BREATHE fixture fix,
  auto/task-aware local model routing, self-apply verifier fix, semantic
  compensation, frontend dependency cleanup.
- Live BREATHE is now proven end to end on Auto/qwen2.5-coder:7b:
  failing fixture → read real bytes → exact edit proposal → capability approval →
  pre-edit snapshot → write → `[VERIFY PASS] 1 passed`. During the proof, added
  safe recovery for Python-style literal tool mappings and deterministic project-
  venv preference for sandbox verification.

Evidence:
- Backend: `278 passed, 1 skipped`; 86% coverage; `git diff --check` clean.
- Frontend: eslint clean; Vitest `14 passed`; Vite build green (large-chunk warning).
- Live backend restarted and healthy at `http://127.0.0.1:8000`.
- Frontend running at `http://127.0.0.1:5173`.
- Live Auto: coding `qwen2.5-coder:7b`, reasoning `deepseek-r1:8b`, general
  `llama3.1:8b`, fast `qwen2.5-coder:3b`.
- Live classifier: `echo hello` GREEN; unknown and `python -c` RED.
- Raw client-authored approval live probe returns HTTP 400.
- Live command probes: composition and Git output attempts RED/BLOCKED; shell-free
  `echo` OK.
- Tool-use smoke: qwen2.5:7b, llama3.1:8b, and llama3.2:3b called `read_file`;
  mistral:7b completed without a tool call and remains a general fallback.
- Audit chain valid: 75 entries.

## Single next action
Commit and push the verified release-hardening changes so Claude Code can resume
from GitHub, then address the remaining non-blocking isolation and deployment
scaling gaps in a separate slice.

## Open risks / honest gaps
- Executor scope locking is not OS/container isolation. Human-approved pytest and
  other arbitrary-code commands run as the backend OS user.
- API bearer auth is enforced when configured and non-loopback startup requires a
  token, but production still needs TLS and external secret management.
- Approval capabilities/grants are process-local; backend restart invalidates a
  paused approval chain by design. Pending tokens and redeemed grants expire.
- Semantic-write locking is single-process only; multi-worker deployment needs a
  dedicated vector writer or inter-process lock.
- The frontend production build still warns about a ~966 kB SpatialScene chunk.
- Mistral 7B did not use `read_file` in the live smoke; do not route agentic work to
  it by default.
- Release evidence: backend 278/1 with 86% coverage; frontend lint/14/build; npm
  audit and pip check clean; audit chain valid at 75; live adversarial probes pass.

## Active files
`aios/core/approvals.py`, `aios/api/main.py`, `aios/security/gateway.py`,
`aios/core/executor.py`, `aios/core/self_apply.py`, `aios/memory/semantic.py`,
`aios/agents/tool_agent.py`, `frontend/src/App.jsx`,
`tests/test_{approvals,api,security,self_apply,memory}.py`, plus prior dirty work.

## Runtime
Backend: `.venv\Scripts\python -m uvicorn aios.api.main:app --port 8000`
Frontend: `cd frontend; npm run dev`
Tests: `.venv\Scripts\python -m pytest -q`
