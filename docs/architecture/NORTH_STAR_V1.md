# NORTH STAR V1 — GAGOS Sovereign Intelligence AI-OS

**Version:** 1.0  
**Scope:** local-first, supervised, memory-driven AI Operating System  
**Interface:** GAGOS (Graphical Agent General Operating Shell) — the only public UI path (`/`).  

## Purpose

A sovereign agentic OS that runs on the operator's machine, keeps authority exact, keeps execution isolated, and tells the truth about itself. It is not a chatbot wrapper; it is a runtime that can think, remember, act, and be audited.

## Core Principles

1. **Local-first by default.** The canonical runtime is on the operator's hardware. Egress to cloud providers is gated by explicit policy, never accidental.
2. **Authority is centralized.** A single Policy Kernel decides what an agent or tool is allowed to do. No subsystem invents its own permissions.
3. **Execution is isolated.** Untrusted or high-impact work runs inside sandboxed workers (WASM / managed / process). The host kernel never executes arbitrary code.
4. **Memory is structured.** Experience, decisions, and failures are written to durable stores, not prompt context. The system learns from evidence, not repetition.
5. **Interface is alive and truthful.** GAGOS reflects real state. It does not animate fake progress or claim actions it did not take.
6. **Security is fail-closed.** Unknown risk → deny → escalate to operator. Guardrails are never disabled to make a test pass.

## Logical Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      GAGOS Frontend                          │
│  (React / Vite — single UI at /, no ?ui= legacy routes)     │
└───────────────────────┬─────────────────────────────────────┘
                        │ HTTP / SSE
┌───────────────────────▼─────────────────────────────────────┐
│                   AI-OS HTTP Edge                            │
│  CORS · origin validation · API token · session binding     │
└───────────────────────┬─────────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────────┐
│                   Policy Kernel                              │
│  GREEN (read/analyze) · YELLOW (edit/mutate) · RED (danger) │
│  scopes · authority · approval gate · audit log             │
└───────────────────────┬─────────────────────────────────────┘
                        │
┌──────────┬────────────┼────────────┬──────────┐
│  Memory  │  Agents    │  Tools     │  Router  │
│  Engine  │  Runtime   │  Registry  │  (LLM)   │
└──────────┴────────────┴────────────┴──────────┘
                        │
┌───────────────────────▼─────────────────────────────────────┐
│              Sandboxed Execution / Workers                   │
│  WASM agents · managed cloud agents · subprocess workers    │
└─────────────────────────────────────────────────────────────┘
```

## Slice Roadmap (Master Convergence Directive)

| Slice | Goal | Deliverable |
|-------|------|-------------|
| 0 | Establish truthful baseline | This doc + runtime map + registry + green gates |
| 1 | Harden HTTP edge | `aios/interfaces/http/edge_security.py` + adversarial tests |
| 2 | Centralize authority | Policy Kernel module + scope-of-action ledger |
| 3 | Isolate execution | Worker sandbox registry + per-action sandbox selection |
| 4 | Runtime profiles | Profiles: `minimal`, `developer`, `sovereign`, `enterprise` |
| 5 | Converge subsystems | Refactor routes/agents/tools to use kernel + sandbox |
| 6 | Living interface | GAGOS truthfulness audit + real-state telemetry |
| 7 | Distribution + bootstrap | Installer, migration, rollback, self-test |

## Canonical Run Commands

- Backend: `.venv\Scripts\python -m aios`
- Frontend: `cd frontend && npm run dev`
- Full stack: `AIOS_API_TOKEN=<32-char-token> docker compose up --build`
- Tests: `.venv\Scripts\python -m pytest -q` (current baseline: green, 92% backend coverage)

## Open Convergence Goals

- Frontend coverage is currently ~39-46%; raise it as slices land.
- Frontend lint warning budget is `max-warnings=124`; reduce monotonically.
- Move route handlers from `aios/api/routes/*.py` to domain modules orchestrated by the Policy Kernel.
