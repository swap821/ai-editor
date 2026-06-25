# RESUME MANIFEST

Last updated: 2026-06-25T11:25:00Z

## Current Session — RENOVATION_PLAN.md burn-down (P1-1, P3-1 done; P1-7 in progress)

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

### P3-1 dead-code cleanup
- Deleted root cruft: `websocket_security_update.md`, `chat-ui.html`, `creator.txt`, `success.txt`, `.eslintrc.json`.
- Removed unused `websockets==16.0` pin from `requirements.txt` (no backend code imports it).
- Trimmed lab `constants.ts` to only `CAMERA` and `POST_FX`; dead `COLORS`, `LAYOUT_CONFIGS`, `SPRING_CONFIGS`, `AIState`, `TIMING`, `LIGHTS`, `PARALLAX`, `DRAG`, and `LayoutContext` removed.
- Re-ported lab to product; `npm run port` had dropped `previewIntent` and `fetchOnboardingState` from `frontend/src/superbrain/lib/aiosAdapter.ts`, so they were re-added in the lab source and re-ported.
- Verified: backend `654 passed, 1 skipped`; product `npm run typecheck && npm test -- --run && npm run build` → 54 files, 326 passed, build exit 0; lab tests unchanged at 370 passed.
- **Committed and pushed** as `48e27af` (P3-1 dead-code cleanup + adapter re-add after port).

### P1-7 workbench layer polish
- The original `ForgePorts.jsx` / `CommandLine.jsx` / `BuildFeed.jsx` / `Workbench.jsx` workbench layer was already collapsed into `GagosChrome` during the 2026-06-20 product pivot; no separate files remain.
- The command-bar state machine is already extracted as `deriveCommandDockState` (`frontend/src/superbrain/lib/commandDockState.ts`) and used by `GagosChrome`.
- Added shared `:focus-visible` + `:disabled` styles for all glyph buttons (mic / speaker / send) in `GagosChrome.css`.
- Hardened mic button keyboard/pointer semantics: `disabled={busy}`, `aria-disabled={busy}`, `aria-pressed={listening}`, and keyboard handler ignores activation while busy.
- Added `aria-pressed` to the speaker mute toggle and explicit `aria-disabled` to the send/stop toggle.
- Verified: product typecheck + 326 tests + build green; no lab impact (GagosChrome is product-only).
- **Committed and pushed** as `a9016ea`.

### P1-8 classic IDE approval/control accessibility
- The classic IDE (`App.jsx` / `App.css`) no longer exists in the product; the single-frontend collapse left only the GAGOS face (`GagosChrome`).
- The remaining approval surface is `ApprovalPanel.tsx`, which already lives in `superbrain.css` with hover/active/focus-visible styles and inherits the global reduced-motion block.
- Added an `aria-describedby` link from the `alertdialog` to the `approval-summary` (and `approval-explanation` when present) so screen readers announce the decision context immediately.
- Verified: product typecheck + 326 tests + build green.

## Single Next Action
**Start P2-1 test the highest-leverage untested logic** — read `aiosAdapter.ts` `processEvent` / pending-approval reconciliation, identify the SSE parser state machine, write focused unit tests for the parser and reconciliation, and run the frontend test suite before committing.

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
- [x] P1-1 branch hygiene: fast-forwarded `feat/jarvis-voice`, `feat/frontend-renovation`, and `feat/renovation-p0` to current `master` (`8b9f7d6`) and pushed to origin

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
