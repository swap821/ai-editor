# RESUME MANIFEST

## Current goal
Ship a trustworthy local-first AI-OS MVP: supervised actions, evidence-backed
writes, reliable local-model routing, durable memory, and honest failure modes.

## Last completed and verified
2026-06-09 honest-gap closure and whole-system release gate:
- Approved arbitrary-code execution has an optional fail-closed Docker backend:
  no network, read-only root, dropped capabilities, resource limits, non-root
  user, and one scoped read-write mount. Default remains `host` because the local
  Docker Desktop Linux daemon is unavailable.
- Server-issued approval capabilities and replay grants are durable, hashed,
  expiring, exact-payload, session-bound, one-use, and restart-safe. Direct API,
  chat, and UI terminal approval/rejection paths are complete.
- New durable approval, rate-limit, and episodic records hash caller-supplied
  session identifiers; over-limit caution actions require a fresh human decision
  without permanently locking an expired session. Startup migrates legacy raw
  session keys in place.
- Same-host workers coordinate approval state, sensitive-action rate limits,
  audit appends, FAISS mutation/refresh, fact contradiction checks, reflection
  recurrence, self-apply, and rollback Git operations.
- Writes use atomic publication: approved edit/create and self-apply restoration
  cannot leave partially written target files. Self-apply and rollback operations
  are serialized and fail closed.
- Command length and retained output are bounded; every real subprocess path,
  including self-apply verification and `git apply`, drains output without
  retaining an unbounded response in backend memory.
- Chat, facts, mistakes, semantic memory, episodic memory, and self-analysis
  evidence redact credential-like data before persistence.
- API/schema surfaces require bearer auth when configured; non-loopback startup
  requires a token of at least 32 characters. Explicit unavailable cloud routes
  fail clearly and never silently switch providers.
- The live local gallery applies an evidence-backed compatibility policy because
  Ollama metadata alone can overstate tool support. Auto additionally avoids
  unreliable tool users. No additional model download is needed for this host.
- Frontend removed the large Three.js chunk, completes terminal approvals, records
  rejection decisions server-side, and renders preview errors as text rather than
  HTML. Live Preview has a no-egress CSP and no CDN dependency.
- Obsolete root `memory.db` and `vector_index.faiss` are no longer tracked, remain
  preserved locally, and contained no detected credentials.

## Evidence
- Backend: `331 passed, 1 skipped`; 90% application / 94% total coverage;
  compileall, pip check, and pip-audit clean.
- Frontend: eslint clean; Vitest `16 passed`; Vite production build 324 kB JS,
  no large-chunk warning; npm audit reports zero vulnerabilities.
- Self-analysis: 34 modules, 22 maintainability findings, zero missing-test and
  zero TODO false positives; Radon average complexity A.
- Live backend healthy at `http://127.0.0.1:8000`.
- Live Auto routes: coding `qwen2.5-coder:7b`, reasoning/general `llama3.1:8b`,
  fast `qwen2.5-coder:3b`.
- Live compatible gallery: qwen2.5-coder 7B/3B, qwen2.5 7B, llama3.1 8B,
  llama3.2 3B, Mistral 7B. DeepSeek R1 is hidden/refused because Ollama rejects
  the tool schema.
- Tool smoke: qwen2.5-coder 7B/3B, qwen2.5 7B, llama3.1 8B, and llama3.2 3B
  completed; qwen2.5-coder 7B used `read_file` in three repeated final probes.
- Live adversarial probes: shell composition blocked; GREEN echo works; YELLOW
  command issued a capability; over-limit caution action issued fresh
  re-authorisation; rejection consumed it; oversized command blocked without
  echoing its payload; pending capability survived backend restart; unavailable
  cloud returned 503.
- Active durable databases scan with zero credential/high-entropy findings.
- Audit chain valid at 93 entries before final documentation gate.

## Bounded external/runtime limitations
- Docker CLI is installed, but the Docker Desktop Linux daemon is not running, so
  the isolated executor image cannot be built or exercised on this host yet.
  Container selection validates at startup and fails closed when unavailable.
- Default `host` mode is not OS isolation; approved arbitrary-code commands run as
  the backend OS user. Use container mode when Docker is available.
- TLS termination, external identity/authorization, and secret management are
  deployment responsibilities. A browser bearer token is not multi-user identity.
- Same-host coordination is implemented. Multi-host deployments still need a
  distributed lock/vector service and shared security-state design.
- Git history still contains the obsolete legacy DB/vector artifacts from the
  initial commit; the scanned DB had no detected credentials. History rewriting
  would be a separate coordinated operation.

## Single next action
Start Docker Desktop, build `aios-executor:local`, select
`AIOS_APPROVED_EXECUTION_BACKEND=container`, and run the isolated live smoke.

## Runtime
Backend: `.venv\Scripts\python -m uvicorn aios.api.main:app --port 8000`
Frontend: `cd frontend; npm run dev`
Tests: `.venv\Scripts\python -m pytest -q`
