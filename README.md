# AI-OS - Supervised, Security-Gated, Memory-Driven Agent

A local-workspace AI operating system modeled on the Jarvis pattern: an LLM agent
that can inspect, plan, execute, edit, verify, and learn inside an IDE workspace,
while every risky action passes through deterministic security gates and explicit
human approval.

> Honest status: this is an active Python/FastAPI MVP with a React/Vite UI. The
> current runtime is local-first Ollama with optional AWS Bedrock fallback. The
> older Node/Express implementation is retained under `legacy_node/` for history,
> but it is not the active backend.

## Architecture

```text
React/Vite UI + Monaco
        |
        | HTTP + SSE
        v
FastAPI backend (`aios.api.main`)
        |
        +-- ToolAgent: read, edit/create sandbox files, execute, verify, plan
        +-- Security gateway: deterministic GREEN/YELLOW/RED, fail-closed
        +-- Scope lock: path canonicalization against configured roots
        +-- Audit ledger: SHA-256 hash chain, secret-scrubbed payloads
        +-- Memory: SQLite episodic/semantic/mistake/facts + FAISS retrieval
        +-- Reflection: failed command -> structured lesson
        +-- Self-analysis: scan -> propose diffs -> human apply -> verify/rollback
        |
        +-- Ollama local models by default
        +-- Bedrock Converse when cloud inference is explicitly configured
```

## Core Modules

| File | Responsibility |
|------|----------------|
| `aios/api/main.py` | FastAPI routes, SSE chat bridge, dependency injection |
| `aios/agents/tool_agent.py` | Bounded tool loop, approval pause/resume, auto-verify after writes |
| `aios/security/gateway.py` | Deterministic fail-closed zone classifier |
| `aios/security/scope_lock.py` | Path and command scope enforcement |
| `aios/security/audit_logger.py` | Tamper-evident audit ledger |
| `aios/core/executor.py` | Gated, scope-constrained command execution |
| `aios/core/verifier.py` | Evidence-based verification of test/build commands |
| `aios/core/model_selector.py` | Task-aware local model auto-selection |
| `aios/core/self_apply.py` | Human-approved self-analysis proposal apply/verify/rollback |
| `aios/memory/` | Episodic, semantic, mistake, fact, and retrieval layers |
| `frontend/src/App.jsx` | Main IDE/chat shell |

## Run

```powershell
# Backend
.venv\Scripts\python -m uvicorn aios.api.main:app --port 8000

# Frontend
cd frontend
npm run dev
```

Open `http://localhost:5173`. The model picker defaults to `Auto`, which lets
the backend choose the best installed Ollama model for the task. Optional Bedrock
usage is configured with env vars such as `AIOS_BEDROCK_REGION` and
`AWS_BEARER_TOKEN_BEDROCK`; secrets stay server-side.

## Tests

```powershell
.venv\Scripts\python -m pytest -q
cd frontend
npm test
npm run build
```

Current local verification target: Python suite `331 passed, 1 skipped` at 90%
application / 94% total coverage, plus frontend Vitest `16 passed`.

## Security Invariants

- Fail-closed: empty, ambiguous, exception, or out-of-scope actions do not run.
- Deterministic gateway: no LLM decides whether a command is safe.
- Scope-locked writes/exec: the agent writes and runs only inside configured roots
  unless a narrower human self-apply path is used.
- RED cannot be one-click approved.
- YELLOW pauses for human approval and resumes the same turn with the approved
  command/edit/create payload.
- Audit-before-write on guarded edits and self-apply.
- Verification is evidence-based; model narration does not count as success.
- Semantic FAISS writes are coordinated across local worker processes with a
  shared file lock; writers reload before mutation and long-lived readers
  refresh after another process persists.
- Approval capabilities, redeemed grants, sensitive-action rate limits, audit
  appends, facts, reflection recurrence, self-apply, and rollback Git operations
  coordinate across local worker processes.
- New durable approval, rate-limit, and episodic records hash caller-supplied
  session identifiers instead of storing them raw.
- Approved edits/creates and self-apply rollback restoration publish atomically;
  a failed write cannot leave a partially written target.
- Commands are parsed into structured argv, shell composition is rejected, and
  child processes launch with `shell=False`.
- Oversized commands are refused and command output is drained with a bounded
  retained prefix, preventing unbounded response-memory growth.
- Live Preview runs in a script-only sandbox with a restrictive CSP and no CDN
  or network egress.
- Default `host` execution is scope locking, not OS isolation. Set
  `AIOS_APPROVED_EXECUTION_BACKEND=container` after building `Dockerfile.executor`
  to run approved arbitrary-code commands in a fail-closed, no-network,
  read-only-root Docker container with a single scoped read-write mount.
- Unauthenticated API requests are accepted only from loopback. Non-loopback API
  deployment requires a random `AIOS_API_TOKEN` of at least 32 characters;
  configure the same value as
  `VITE_AIOS_API_TOKEN` only for a trusted/private frontend deployment.

For production-style exposure, terminate TLS in a maintained reverse proxy and
keep AI-OS bound to a private interface. A browser-delivered bearer token is
recoverable by that browser's user; it is not multi-user identity or authorization.

## Local Model Gallery

The system works best with several Ollama models installed. A good local set is:

- `qwen2.5-coder:7b` - primary coding/tool-loop model
- `qwen2.5:7b` - general/reasoning-capable tool model
- `mistral:7b` - general fallback
- `llama3.1:8b` - strong general/reasoning tool-loop model
- `llama3.2:3b` or `qwen2.5-coder:3b` - small RAM-friendly fallback
- `nomic-embed-text:latest` - embedding utility

The live gallery exposes only models considered compatible by the tested local
policy. Ollama capability metadata alone is insufficient: some models advertise
tools but reject or ignore this agent's actual tool request. Auto additionally
avoids models such as legacy Mistral that accept tools but do not use them
reliably. `deepseek-r1:8b` remains useful directly in Ollama, but is hidden from
AI-OS because its live request rejected this agent's tool schema.
