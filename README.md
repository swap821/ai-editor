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

Current local verification target: Python suite `278 passed, 1 skipped`, plus
frontend Vitest `14 passed`.

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
- Commands are parsed into structured argv, shell composition is rejected, and
  child processes launch with `shell=False`.
- Scope locking is not OS/container isolation. Human-approved arbitrary-code
  commands run as the backend OS user.
- Unauthenticated API requests are accepted only from loopback. Non-loopback API
  deployment requires `AIOS_API_TOKEN`; configure the same value as
  `VITE_AIOS_API_TOKEN` only for a trusted/private frontend deployment.

## Local Model Gallery

The system works best with several Ollama models installed. A good local set is:

- `qwen2.5-coder:7b` - primary coding/tool-loop model
- `qwen2.5:7b` - general/reasoning-capable tool model
- `deepseek-r1:8b` - reasoning reference model, not preferred for tool calls
- `mistral:7b` - general fallback
- `llama3.2:3b` or `qwen2.5-coder:3b` - small RAM-friendly fallback
- `nomic-embed-text:latest` - embedding utility

The backend filters embedding/vision/base-only models out of chat routing and
keeps the agent loop on tool-capable models.
