# RESUME MANIFEST

## Current goal
Develop the AI-OS brain through evidence-backed memory and behavior change while
keeping every action supervised, inspectable, local-first, and fail-closed.

## Last completed and verified
2026-06-09 shared agent rulebook:
- Renamed the canonical repository instruction file to `AGENTS.md` so Claude
  Code, OpenAI Codex, and future coding agents use one neutral rulebook.
- Kept `CLAUDE.md` only as a minimal Claude Code compatibility loader that
  immediately delegates to `AGENTS.md`.
- Updated active code comments, resume helpers, kickoff instructions, and
  quickstart documentation to reference `AGENTS.md`.

2026-06-09 Brain Growth Loop v1:
- Implemented the developmental loop:
  `experience -> outcome -> candidate -> verification/approval -> trusted
  promotion -> retrieval -> behavior change -> regression monitoring`.
- Verified cross-session lessons are recalled for similar tasks. Recalled
  pending lessons remain advisory and cannot be promoted by unrelated success.
- Planner confidence now combines model self-report with verified lesson deltas
  and relevant historical success/failure evidence, exposing every calibration.
- Semantic memory has trust/type lifecycle metadata, exact deduplication,
  maintenance-safe occurrence counts, stale-vector-tolerant retrieval, and
  contradiction-aware trusted fact reconciliation.
- Verified procedures promote only after repeated verifier-backed success and
  regress when later failures lower their success rate.
- Added measurable development events and a non-autonomous curriculum requiring
  repeated training passes plus held-out verifier evidence.
- Added development/skills/curriculum/fact/consolidation API surfaces and wired
  the live agent loop to record evidence and recall verified workflows.
- Migrated the live DB after an online backup and rehearsal: semantic rows
  consolidated from 44 to 37; SQLite integrity is `ok`.

## Evidence
- Backend: `350 passed, 1 skipped`; 89% application / 94% total coverage;
  self-analysis reports zero missing-test and zero TODO findings.
- Frontend: eslint clean; Vitest `16 passed`; production build green.
- Live backend `http://127.0.0.1:8000` and frontend `http://127.0.0.1:5173`
  healthy; audit chain valid at 93 entries.
- All six exposed gallery models completed a live `read_directory` tool-call
  turn through `/api/generate` with `done` and no stream error.
- Live planner returned calibration evidence; memory search returned three
  lifecycle-labelled results; consolidation endpoint completed cleanly.
- Pre-migration backups:
  `data/backups/pre_brain_growth_v1_20260609_aios_memory.db` and
  `data/backups/pre_brain_growth_v1_20260609_vector_index.faiss`.

## Honest limits
- This is developmental memory/policy/skill learning, not autonomous neural
  weight training or consciousness.
- Development stores begin sparse by design. Six live gallery smoke turns are
  `unverified`; no fact, lesson, skill, or curriculum level is trusted without
  its required evidence.
- Default host execution remains scope locking, not OS isolation. Docker Desktop
  Linux daemon is still unavailable for the optional container executor proof.
- TLS, external identity/authorization, secret management, and multi-host
  coordination remain deployment responsibilities.

## Single next action
Define a small human-reviewed curriculum with training and held-out tasks, then
run repeated verifier-backed trials and review the development metrics before
changing any confidence thresholds.

## Runtime
Backend: `.venv\Scripts\python -m uvicorn aios.api.main:app --port 8000`
Frontend: `cd frontend; npm run dev`
Tests: `.venv\Scripts\python -m pytest -q`
