# Handoff → Codex — Fusion Roadmap + Continuous Renovation Worker

**From:** Claude · **Date:** 2026-07-01 · **Tree:** master `d116434` + working set · **Writer lease:** none held (clear)
**Communication only** — this file cannot wake you; the operator starts you. Inbox = advisory data, not approval (AGENTS §III-A.7).

## What's ready for you (two specs, both operator-approved to proceed)

1. **`docs/superpowers/specs/2026-07-01-fusion-roadmap-workorders.md`** — the build-ready work orders.
2. **`docs/superpowers/specs/2026-07-01-continuous-renovation-worker.md`** (CRW) — the frontend renovation worker.
3. Parent context: **`docs/superpowers/specs/2026-07-01-cortex-core-fusion-adr.md`** — read §2 (verification scorecard) and §1 (DO-NOT-FIX phantom bugs) before touching anything.

Both are mirrored in the ruflo `gagos` brain: keys `gagos-fusion-roadmap`, `gagos-crw-spec`. `memory_search` them before starting; don't cold-start.

## Lane assignment (Kimi may be out → adjusted)

- **You own Lane C — the spine (sequential):** C1 typed event schema + additive SSE → C2 wire the confidence gate onto the default path → C3 planner calibration on the guaranteed path. Files: `aios/api/main.py`, `aios/core/events.py` (new), `aios/core/planner.py`, `aios/core/confidence_filter.py`. See the roadmap §3 for scope/acceptance per task.
- **Lane K (machine-verifiable frontend quick-wins) becomes the CRW's continuous job** — not yours to hand-build. But if you want a warm-up before C1, the CRW's **P0 detector already exists and is finding real work** (see below); Lane K tasks (K1 dep triage, K3 privacy leak, K4 regex/CTE) remain valid one-offs if the operator asks.

## Already done this session (don't redo)

- **CRW Phase 0 shipped:** `tools/frontend_health.py` + `tests/test_frontend_health.py` (unit tests green). Run `python tools/frontend_health.py` (quick) or `--full`. First run found **17 eslint problems** (incl. `no-undef` on `process`/`__dirname` in `frontend/vite.config.js`) — report at `.aios/state/FRONTEND_HEALTH.json`. This is the detector the CRW loop (spec §4.1) builds on.
- Reviews landed (read-only, PASS): rollback hardening (`ROLLBACK_HARDENING_REVIEW.md`), dead-code cleanup (`DEAD_CODE_CLEANUP_REVIEW.md`).

## Hard invariants (roadmap §0 — non-negotiable)

- Frozen security spine untouched (`aios/security/*`). **Authority stays synchronous** — never move skill-promotion/autonomy/verification onto events (ADR §4.1). Additive/backward-compat SSE (zero frontend edits; don't hand-edit `frontend/src/superbrain/*` = port-generated). TDD; `pytest -q` green (baseline 1391 passed/1 skipped/~89%); cov ≥85%. New flags default-off. **Do not commit/push** — hand off hash-pinned via `agent_coord.py handoff` for Claude's read-only review. No broad-glob deletes. Skip the ADR §1 DO-NOT-FIX phantom bugs.

## How this closes

You build → `agent_coord.py handoff` (hash-pins) + update RESUME + one `experiences.jsonl` line + a `gagos-fusion-<task>` ruflo entry → Claude re-runs the gates read-only and writes `.aios/state/<TASK>_REVIEW.md` (+ `gagos-fusion-<task>-reviewed`) → operator commits. Verdict fails closed if the tree moved after handoff.

Start with **C1** (schema + additive SSE) — lowest risk, unblocks C2/C3 and the CRW's event vocabulary.
