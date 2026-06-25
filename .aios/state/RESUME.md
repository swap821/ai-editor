# RESUME MANIFEST

Last updated: 2026-06-25T10:55:00Z

## Current Session — P0-4 proxy-header hotfix ✅ COMPLETE (pending Codex re-review)

**Goal:** Fix the env/CLI inconsistency Codex flagged in the P0-4 token-auth proxy-header policy.

**What happened this session:**
- Read `RESUME.md`, `warnings.md`, and unread Codex inbox for P0-4.
- Claimed worktree lease for `p0-4-token-auth-proxy-header` as builder.
- Updated `aios/__main__.py` so the proxy-header trust flag is computed once as `bool(args.proxy_headers or config.TRUST_PROXY_HEADERS)`, stored back into `config.TRUST_PROXY_HEADERS`, and passed identically to `uvicorn.run(..., proxy_headers=...)`.
- Added entrypoint regression tests in `tests/test_entrypoint.py`:
  - default (no env, no flag) → `proxy_headers=False`;
  - `--proxy-headers` flag → `proxy_headers=True` and `config.TRUST_PROXY_HEADERS=True`;
  - `AIOS_TRUST_PROXY_HEADERS=true` with no CLI flag → `proxy_headers=True` and `config.TRUST_PROXY_HEADERS=True`.
- Fixed the secondary test gap in `tests/test_token_auth_proxy_header.py`: `test_proxy_headers_trusted_loopback_must_present_token` now uses a dedicated `proxy_token_app` fixture with `TRUST_PROXY_HEADERS=True` instead of the non-proxy `token_app` fixture.
- Verified all gates locally:
  - Backend full suite: `654 passed, 1 skipped`; coverage `89.50%` (floor `85%`).
  - Frontend: `npm run typecheck` green; `npm test -- --run` `326 passed`; `npm run build` green.

**What happened this session:**
- Read `RESUME.md`, `warnings.md`, last ~10 `experiences.jsonl` entries, and `agent_coord.py status` (clean tree, no active writer).
- Claimed worktree lease for `p1-10-doc-currency-sweep` as builder.
- Adopted the "report live counts" pattern in living docs:
  - `README.md` — removed hardcoded `556/65` counts; now instructs readers to trust the live run.
  - `START_HERE.md` — removed hardcoded `556` from the pytest command comment.
  - `AGENTS.md` — removed hardcoded `556` from the test baseline note.
- Reconciled contradictions:
  - `PLAN.md` top banner now points to live counts + notes current `654/326` as of 2026-06-25.
  - `PLAN.md` H1 row updated to reflect the adopted live-counts pattern and corrected bearer-token claim.
  - `PLAN.md` S3 row corrected: `aiosAdapter.ts` now sends `Authorization: Bearer` when `VITE_AIOS_API_TOKEN` is set.
- Added superseded banners to dated snapshots (body unchanged, kept as records):
  - `HIDDEN_KNOWLEDGE.md`, `BACKEND_TRUE_PICTURE.md`, `CEO_LOG.md`, `FRONTEND_RENOVATION_BLUEPRINT.md`, `ARCHITECT_REVIEW_2026-06-14.md`.
  - `SYSTEM_TRUE_PICTURE.md` got an "evolving document" note instead (it remains the canonical whole-system map).
- Confirmed `frontend/README.md` is already project-specific (GAGOS, the points-being), not stock Vite boilerplate.
- Verified all gates locally:
  - Backend full suite: `654 passed, 1 skipped`; coverage `89.49%` (floor `85%`).
  - Frontend: `npm run typecheck` green; `npm test` `326 passed`; `npm run build` green.
- Committed the post-sweep RESUME hash update as `7b64b92` and pushed to `master`.

**Test counts as of this run (trust live count):**
- Backend: `654 passed, 1 skipped` (Windows symlink privilege; coverage `89.49%`).
- Frontend product: `326 passed`; `vite build` green; `tsc --noEmit` green.
- Lab: not re-run this session (no lab changes).
- Canon guards (`check_css_canon.py`, `check_canon_frozen.py`): not re-run this session (no visual changes).

## Completed
- [x] Backend intent-preview endpoint + onboarding-state endpoint + tests
- [x] Frontend adapter helpers for the new endpoints
- [x] Product-only 3D reactive effects (cloud lightning, verify aurora, worker motes)
- [x] Backend-driven intent preview in the command dock
- [x] Milestone-driven onboarding coach
- [x] Product tests for intent, onboarding, reactive effects, approval reconciliation, session-id resolver, and Jarvis voice loop
- [x] Live visual pass via kimi-webbridge confirms the dock + coach render correctly
- [x] Aurora state/decay bug fixed and re-tested
- [x] All gates green (pytest, vitest product, vitest lab, tsc, vite build, canon guards)
- [x] First-cloud-route spine-flash hint implemented, tested, live verified, and pushed
- [x] P0-3 approval single-source-of-truth verified, regression-tested, and documented
- [x] P1-3 session-id unification verified, regression-tested, and documented
- [x] P1-2 Jarvis voice Slice 2 (STT + TTS + push-to-talk + mute) implemented, regression-tested, documented, and CI-green
- [x] P0-7 prompt input-shield implemented, regression-tested, and documented
- [x] P1-4 structured logging + diagnostics implemented, regression-tested, and documented
- [x] P1-5 observability surface (`/metrics` + Docker) implemented, regression-tested, and documented
- [x] P0-1 CORS guard already implemented (`_validate_cors_origins`, narrowed methods/headers, `tests/test_cors_guard.py`)
- [x] P0-6 app entrypoint already implemented (`aios/__main__.py` binds `config.API_HOST`/`API_PORT`)
- [x] P2-5 config robustness (unparseable env-var warnings + startup security banner) implemented, regression-tested, committed, and pushed
- [x] P0-5 legacy quarantine completed (`legacy/` banner + `--yes` guard on `vector_memory_setup.py` + regression tests)
- [x] P0-2 `reset_audit_chain.py` misleading no-op neutralised (quarantined/disabled + regression tests)
- [x] P1-6 knowledge-graph traversal + recall into forge prompt implemented, regression-tested, committed, and pushed
- [x] P1-9 cross-suite CI + coverage/typecheck gate implemented, regression-tested, committed, and pushed
- [x] P0-5 hotfix: `tests/test_legacy_quarantine.py` now runs `vector_memory_setup.py --yes` from `tmp_path`
- [x] P0-4 token-auth proxy-header policy implemented, regression-tested, and documented (`TRUST_PROXY_HEADERS`, `--proxy-headers`, `testclient` removed from production allowlist), committed, and pushed (`2c781c5`)
- [x] P0-4 hotfix: `aios/__main__.py` now reconciles env `AIOS_TRUST_PROXY_HEADERS` and `--proxy-headers` CLI flag into a single `trust_proxy_headers` value passed to both AI-OS policy and uvicorn; added entrypoint regression tests and corrected proxy-token fixture in `tests/test_token_auth_proxy_header.py`
- [x] P1-10 doc-currency sweep: adopted "report live counts" pattern, reconciled PLAN.md bearer-token contradiction, added superseded banners to dated snapshots, confirmed `frontend/README.md` is project-specific, committed, and pushed (`53b9f08`)

## Single Next Action
**Operator to choose one of:**
1. Fix P1-9 focused-test coverage gate (Codex post-push finding).
2. Pick the next RENOVATION_PLAN.md item (P1-7 workbench, P1-8 classic IDE a11y, P2-x, P3-x).
3. Review/approve the recently landed slices (P0-4, P1-9, P1-10).

I recommend **(1)** because it resolves the remaining open Codex finding before starting new features.

## Open Approvals / Blockers
- Frozen core (`aios/security/*`) untouched.
- Agent-coord verdicts for P0-5, P1-6, P1-9, P0-4, and P1-10 are pending formal review/approval (work is implemented; tasks were released as builder).
- **Remaining open finding:**
  - **P1-9 cross-suite CI + coverage/typecheck gate:** Codex post-push finding. Global `pytest.ini` coverage `--cov-fail-under=85` causes focused test commands to exit 1 even when targeted tests pass (coverage total is too low). Need to either document "focused tests always use `--no-cov`" or move the coverage gate out of global `addopts` into the full-suite/CI command.
- This does not block master (CI is green), but should be addressed before P1-9 is considered closed.

## Active Files
- `README.md`
- `START_HERE.md`
- `AGENTS.md`
- `.aios/state/PLAN.md`
- `.aios/state/RENOVATION_PLAN.md`
- `.aios/state/HIDDEN_KNOWLEDGE.md`
- `.aios/state/BACKEND_TRUE_PICTURE.md`
- `.aios/state/CEO_LOG.md`
- `.aios/state/FRONTEND_RENOVATION_BLUEPRINT.md`
- `.aios/state/ARCHITECT_REVIEW_2026-06-14.md`
- `.aios/state/SYSTEM_TRUE_PICTURE.md`
- `.aios/state/JARVIS_VOICE_PLAN.md`
- `frontend/README.md`
- `.aios/state/RESUME.md`
