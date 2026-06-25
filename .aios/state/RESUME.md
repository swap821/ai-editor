# RESUME MANIFEST

Last updated: 2026-06-25T09:55:00Z

## Current Session — P0-4 Token-auth proxy-header policy ✅ COMPLETE

**Goal:** Close the last remaining RENOVATION_PLAN P0 hazard: require `AIOS_API_TOKEN` when a reverse proxy is trusted, remove `testclient` from the production loopback allowlist, and document `--proxy-headers`.

**What happened this session:**
- Read `RESUME.md`, `warnings.md`, last ~10 `experiences.jsonl` entries, and `agent_coord.py status` (clean tree, no active writer).
- Claimed worktree lease for `p0-4-token-auth-proxy-header` as builder.
- Added `TRUST_PROXY_HEADERS` config (`AIOS_TRUST_PROXY_HEADERS`) in `aios/config.py`, included it in `startup_banner()` and `__all__`.
- Updated `aios/__main__.py` to accept `--proxy-headers` and pass it to uvicorn; runtime override of `config.TRUST_PROXY_HEADERS` so policy and bind stay consistent.
- Hardened `aios/api/main.py`:
  - `lifespan` now requires a >=32-char token when `TRUST_PROXY_HEADERS` is enabled, even on loopback binds.
  - `require_api_token` middleware removed `testclient` from the production loopback set; added an explicit `_LOOPBACK_HOSTS` constant; returns 403 for unauthenticated requests when proxy headers are trusted.
- Wrote TDD-first regression tests in `tests/test_token_auth_proxy_header.py` (7 tests).
- Updated existing `TestClient(app)` usages across 7 test files to use explicit loopback client `("127.0.0.1", 12345)` so the suite no longer depends on the `testclient` production backdoor.
- Verified all gates locally:
  - Backend full suite: `654 passed, 1 skipped`; coverage `89.49%` (floor `85%`).
  - Frontend: `npm run typecheck` green; `npm test` `326 passed`; `npm run build` green.

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

## Single Next Action
**TBD — operator to pick next task from RENOVATION_PLAN.md.**

## Open Approvals / Blockers
- None blocking. Frozen core (`aios/security/*`) untouched.
- Agent-coord verdicts for P0-5, P1-6, P1-9, and now P0-4 are pending formal review/approval (work is implemented; tasks were released as builder).

## Active Files
- `aios/config.py`
- `aios/__main__.py`
- `aios/api/main.py`
- `tests/test_token_auth_proxy_header.py`
- `tests/test_api.py`
- `tests/test_chat.py`
- `tests/test_chat_input_shield.py`
- `tests/test_generate_input_shield.py`
- `tests/test_logging.py`
- `tests/test_metrics.py`
- `tests/e2e/e2e_cloud_burst.py`
- `tests/e2e/e2e_yellow_verify.py`
- `.aios/state/RESUME.md`
- `.aios/state/RENOVATION_PLAN.md`
