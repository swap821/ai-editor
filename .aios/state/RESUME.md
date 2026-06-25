# RESUME MANIFEST

Last updated: 2026-06-25T11:15:00Z

## Current Session — P0-4 hotfix + P1-9 cleanup + P1-10 doc-accuracy hotfix ✅ COMPLETE

**Goal:** Close all open Codex inbox findings and finish doc-currency cleanly.

### P0-4 proxy-header env/CLI inconsistency
- Claimed worktree lease for `p0-4-token-auth-proxy-header` as builder.
- Updated `aios/__main__.py` to compute one canonical `trust_proxy_headers = bool(args.proxy_headers or config.TRUST_PROXY_HEADERS)`, store it in `config.TRUST_PROXY_HEADERS`, and pass the same value to `uvicorn.run(..., proxy_headers=...)`.
- Added entrypoint regression tests in `tests/test_entrypoint.py` for default, flag-only, and env-only paths.
- Fixed `tests/test_token_auth_proxy_header.py` to use a `proxy_token_app` fixture with `TRUST_PROXY_HEADERS=True` for the loopback-must-present-token case.
- Codex approved post-hoc.

### P1-9 focused-test coverage gate
- Claimed worktree lease for `p1-9-ci-typecheck` as builder.
- Removed `--cov=aios`, coverage report, and `--cov-fail-under=85` from `pytest.ini` `addopts` so focused subsets run cleanly without extra flags.
- Moved the full-suite coverage gate into `.github/workflows/ci.yml` (the only place it needs to be enforced).
- Updated `AGENTS.md` to document the local full-suite coverage command and the focused-subset command.
- Codex approved at `8046c97`.

### P1-10 doc-accuracy hotfix (Codex changes requested)
- Re-claimed worktree lease for `p1-10-doc-currency-sweep` as builder.
- Updated `.aios/state/RENOVATION_PLAN.md` P1-9 row: coverage gate is now in CI, not `pytest.ini`.
- Updated `.aios/state/PLAN.md` S3: marked deployment auth/CORS/proxy-header hardening as done with pointers to `P0-1`/`P0-4`.
- Updated `.aios/state/PLAN.md` S5: marked test/coverage/cross-suite runner as done, noted 326 product tests and CI coverage `89.50%`.
- Updated `.aios/state/BACKEND_TRUE_PICTURE.md` superseded banner: removed stale hardcoded `516 passed / 1 skipped` and pointed to live counts in `RESUME.md`/`AGENTS.md`.

**Verified all gates locally:**
- Backend full suite: `654 passed, 1 skipped`.
- `git diff --check`: clean (only CRLF conversion warnings).

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
- [x] P1-9 cleanup: moved `--cov-fail-under=85` out of `pytest.ini` global addopts and into the CI command so focused test runs succeed without `--no-cov`; updated `AGENTS.md` with the local coverage command
- [x] P0-5 hotfix: `tests/test_legacy_quarantine.py` now runs `vector_memory_setup.py --yes` from `tmp_path`
- [x] P0-4 token-auth proxy-header policy implemented, regression-tested, and documented (`TRUST_PROXY_HEADERS`, `--proxy-headers`, `testclient` removed from production allowlist), committed, and pushed (`2c781c5`)
- [x] P0-4 hotfix: `aios/__main__.py` now reconciles env `AIOS_TRUST_PROXY_HEADERS` and `--proxy-headers` CLI flag into a single `trust_proxy_headers` value passed to both AI-OS policy and uvicorn; added entrypoint regression tests and corrected proxy-token fixture in `tests/test_token_auth_proxy_header.py`
- [x] P1-10 doc-currency sweep: adopted "report live counts" pattern, reconciled PLAN.md bearer-token contradiction, added superseded banners to dated snapshots, confirmed `frontend/README.md` is project-specific, committed, and pushed (`53b9f08`)
- [x] P1-10 doc-accuracy hotfix: corrected RENOVATION_PLAN.md P1-9 coverage wording, marked PLAN.md S3/S5 as done, and removed stale hardcoded count from BACKEND_TRUE_PICTURE.md superseded banner

## Single Next Action
**Operator to choose one of:**
1. Pick the next RENOVATION_PLAN.md item (P1-7 workbench, P1-8 classic IDE a11y, P2-x, P3-x).
2. Review/approve the recently landed slices (P0-4, P1-9, P1-10).
3. Continue autonomous backlog burn-down.

I recommend **(1)** because the open Codex findings are now addressed and the backlog is ready to advance.

## Open Approvals / Blockers
- Frozen core (`aios/security/*`) untouched.
- Agent-coord verdicts for P0-5, P1-6, P1-9, P0-4, and P1-10 are pending formal review/approval (work is implemented/handoff; tasks are in `review` or released).
- No remaining builder-blockers. Master is green.

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
