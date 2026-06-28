# RESUME MANIFEST

Last updated: 2026-06-27T22:30:00Z

## Current Goal
Build Council Runtime v0.1 from the sovereign roadmap. The roadmap remains the near-term canon: Phase 0 foundation lock, 30-day First Heartbeat, then 24-week v1.0.

## Last Completed + Verified
- Dashboard-lite is implemented, committed, pushed, and CI-verified on branch `council-runtime-v01`.
- Implementation commit: `852e3c89e4d0aa5b86fbdca6933a5c6659fdac8d` (`Add Council Runtime dashboard lite`).
- Added `AIOS_COUNCIL_RUNTIME_DIR` / `config.COUNCIL_RUNTIME_DIR` as the shared artifact root for stored Council missions.
- Added read endpoints:
  - `GET /api/v1/council/missions`
  - `GET /api/v1/council/missions/{mission_id}`
  - `GET /api/v1/council/reports/{mission_id}`
- Added King decision endpoints:
  - `POST /api/v1/council/approve`
  - `POST /api/v1/council/reject`
- The decision endpoints record `king_decision.json`; when a pending worker approval request is supplied, they write the matching single-use `*.response.json` file for the existing `WorkerRuntime.request_approval()` protocol.
- Added product-owned `frontend/src/workbench/CouncilDashboard.jsx` + CSS and mounted it in `GagosChrome`.
- Dashboard shows mission, risk, recommendation, approval/rollback state, Council verdicts, touched files, blocked attempts, verification state, model route, pending approval, and King approve/reject buttons.
- Added backend tests in `tests/test_council_api.py` for list/detail/report, corrupt artifact skip, path-escape rejection, King report decision recording, pending approval response writing, and single-use refusal.
- Added frontend test `frontend/src/workbench/CouncilDashboard.test.tsx` covering the report display plus approve action payload.
- Local verification:
  - `$env:AIOS_ROUTER_CLOUD_TASKS=''; .venv\Scripts\python.exe -m pytest tests\test_council_api.py tests\test_council_orchestrator.py -q` -> 8 passed.
  - `cd frontend; npm run test -- CouncilDashboard` -> 1 test passed.
  - `cd frontend; npm run typecheck` -> pass.
  - `$env:AIOS_ROUTER_CLOUD_TASKS=''; .venv\Scripts\python.exe -m pytest -q --cov=aios --cov-report=term-missing --cov-report=xml --cov-fail-under=85` -> pass, 1 skipped, 87.03% coverage, 1 known httpx warning.
  - `cd frontend; npm run test` -> 59 files passed, 359 tests passed.
  - `cd frontend; npm run build` -> pass.
  - `git diff --check` -> pass, CRLF warnings only.
  - Protected foundation modules were not modified.
- GitHub Actions CI run `28291759265` succeeded for pushed head `852e3c89e4d0aa5b86fbdca6933a5c6659fdac8d`:
  - `frontend` -> success in 58s.
  - `backend` -> success in 3m41s.

## Security Hotfix (2026-06-27, after deep review) — DONE + VERIFIED
Deep review (19-agent workflow + direct source verification) found 3 worker-isolation regressions that contradicted the project's fail-closed thesis. All three fixed on `council-runtime-v01` (no frozen-spine files touched), each with new adversarial tests:
- `worker_api.py` `run_command` was unguarded arbitrary host exec → now FAIL-CLOSED to `MissionContract.verification_commands` (argv normalized via the same `shlex.split` as `worker_entry`); command output is redacted via `SecretPolicy` + capped at 50k before persisting to the evidence ledger.
- `config.py` `load_dotenv` re-injected scrubbed secrets into the worker → now gated behind `_worker_sandbox_active()`; `backends._restricted_environment()` sets `AIOS_WORKER_SANDBOX=1` on the worker env.
- `main.py` `_validate_council_mission_id`/`_validate_council_request_id` admitted `..` → now reject `.`/`..`/`..`-substring, plus `_mission_dir` resolve-confirms inside `missions/`.
- New tests: `test_council_routes_reject_dotdot_traversal`, `test_run_command_is_fail_closed_to_verification_allowlist`, `test_restricted_environment_sets_worker_sandbox_flag`, `test_config_skips_dotenv_inside_worker_sandbox`.
- Verified: `pytest -q --cov=aios --cov-fail-under=85` → exit 0, 1156 passed / 1 skipped, 87.11%. Diff: 6 files, +166/-4. NOT yet committed (awaiting operator go).

## Merge-Gate Cleanup (2026-06-27, after security hotfix) — DONE + VERIFIED
Operator approved "do all remaining gate items"; all landed on `council-runtime-v01` (security hotfix committed `1c3b586`; gate items in a follow-up commit):
- Rollback de-scoped from the SURFACE (it was never functional): removed the Rollback row from `CouncilDashboard.jsx` (also kills the `?:`/`??` precedence bug that rendered it blank) and dropped `rollbackAvailable`/`rollbackId` from the product `_council_summary_from_artifacts`. KEPT the frozen `KingReport`/`RunLedger` rollback fields (inert, default False/None) — ripping frozen-schema fields is high-churn/risk at v0.1; build real rollback in the healing phase instead.
- Corrupt-artifact robustness: `council_mission_detail` + `council_report` now return 422 (not unhandled 500) on a corrupt stored artifact (list route was already guarded).
- Concurrency/collision guard: new `claim_mission()` in `spawner.py` does an atomic `mkdir(exist_ok=False)`; `WorkerSpawner.run` claims for the normal path and `CouncilOrchestrator._blocked_run` claims for the blocked path → a duplicate `mission_id` now fails closed with `MissionCollisionError` instead of silently clobbering artifacts.
- New tests: `test_council_detail_and_report_return_422_on_corrupt_artifact`, `test_spawner_refuses_duplicate_mission_id`.
- Verified: backend `pytest --cov` exit 0, 1158 passed / 1 skipped, 87.14%; frontend CouncilDashboard test + typecheck + build all pass.

## Council Runtime v0.1 — MERGED + STASHES RESCUED (2026-06-27)
- Council Runtime v0.1 (security-hardened) FAST-FORWARD MERGED to `master` + pushed (`2bc21ea`); CI GREEN (backend+frontend, run 28296559304). 20 zero-byte junk files swept from repo root.
- Both dangling stashes RESCUED into pushed branches (stash list now empty): `rescue/full-knowledge-graph-wip` (Neo4j facts backend WIP, base 1de1bac, 12 files) and `rescue/skills-ui-ux-pro-max` (design-taste-frontend + ui-ux-pro-max project skills, base 7eab53d, 51 files). Gotcha logged: `git stash branch` checks out the stash's OLD base whose .gitignore predates `coverage.xml`/`.gstack`, so `git add -A` swept those artifacts in — stage explicit stash paths (or amend them out) when rescuing onto an old base.

## Phase 3 — Thinking Queens — DONE + VERIFIED (2026-06-27)
Real Queen reasoning shipped (opt-in behind `AIOS_COUNCIL_REASONING`, default off → deterministic, CI-safe):
- `aios/council/reasoning.py`: `reconcile_plan` enforces the NARROW-ONLY privilege invariant (LLM may drop files / raise risk / add approval+verification, never widen scope, lower risk, or clear approval); `plan_with_llm`; `MistakeBackedRetriever` over the verified mistake pool. Hardened fail-closed: `_max_risk` → RED on malformed floor, `_clamp01` rejects NaN/inf.
- `PlannerQueen(llm=...)` does real plan decomposition (clamped); `MemoryQueen(retriever=...)` can DEFER/DENY on prior verified failures (never grant). Both fall back to today's deterministic behavior with no client / flag off.
- `aios/council/council_state.py` (roadmap Phase 3A): durable SQLite `queen_verdicts` + `council_events`; orchestrator persists every verdict/event best-effort (non-fatal).
- Spec: `docs/superpowers/specs/2026-06-27-thinking-queens-design.md`. Adversarial review (4-angle workflow): invariant HOLDS, zero exploitable escalations.
- Verified: backend `pytest --cov` exit 0, 1179 passed / 1 skipped, 87.24%. Frozen spine untouched.

## Real Worker — think/act/react — DONE + VERIFIED (2026-06-28)
LLM-driven worker shipped (opt-in behind `AIOS_WORKER_REASONING`, default off → today's deterministic heartbeat):
- `aios/runtime/worker_entry.py` `_run_llm_worker`: bounded think→act(scoped write_file)→verify(allowlisted run_command)→repair(`purpose="repair"`) loop, capped by `WORKER_MAX_REPAIRS` (default 2) + `max_steps`. `worker_api.request_change` is the gateway wrapper.
- Reuses ALL existing isolation (scoped FS, command allowlist, secret-scrubbing gateway, scrubbed subprocess). Honest: gateway-unavailable → `failed`, never false success.
- Adversarial 4-angle review: containment HELD (no scope escape, no command injection, no secret/provider leak, guaranteed termination). Two findings FIXED before merge: [HIGH] empty `verification_commands` → false completed (now raises ContractViolation — unverifiable edit can't be "completed"); [MEDIUM] DoS (added `WORKER_MAX_FILE_BYTES` cap, default 1 MB).
- Spec: `docs/superpowers/specs/2026-06-28-real-worker-design.md`. Verified: backend `pytest --cov` exit 0, 87.27% (7 new real-worker tests). Frozen spine untouched.

## Mission Origination — chat → council end-to-end — DONE + VERIFIED (2026-06-28)
The supervised loop is closed: dashboard form → `POST /api/v1/council/missions` → background `deliberate()` → `awaiting_approval` → King `POST /approve` → background `execute()` (worker acts) → King report. Opt-in `AIOS_COUNCIL_ORIGINATION` (default off → 404).
- `CouncilOrchestrator` split into `deliberate()` (sync, claims mission, Queens, no worker) + `execute()` (async, `spawner.run(claim=False)`); `run()` = deliberate→execute (unchanged behavior). `build_deliberation_report` = awaiting_approval report. Scope EXPLICIT + confined to `COUNCIL_WORKSPACE_ROOT` (`_validate_mission_scope`), never LLM-inferred.
- Frontend: origination form in `CouncilDashboard.jsx` (goal + allowed files → POST).
- Adversarial 4-angle review: containment held; **4 findings FIXED before merge** — [HIGH] double-execute TOCTOU + [HIGH] non-binding reject → one-shot atomic `decision.lock` (2nd decision = 409); [HIGH] no rate limit → `/council/*` added to `_RATE_LIMIT_ENDPOINTS` (IP-keyed 20/30/30); [MED] glob scope → reject `*?[]`; + defense-in-depth `has_blocking_verdict` re-check at execute. Spec: `docs/superpowers/specs/2026-06-28-mission-origination-design.md`.
- Verified: backend `pytest --cov` exit 0, 87%+ (9 origination + 3 orchestrator deliberate/execute tests); frontend 360 + form test + build.

## Global subprocess semaphore — DONE (2026-06-28)
`aios/runtime/concurrency.py` `WorkerPool` (threading BoundedSemaphore, fail-closed): caps concurrent worker subprocesses at `AIOS_COUNCIL_MAX_CONCURRENT_WORKERS` (default 4). `WorkerSpawner.run` holds a slot for the subprocess lifetime; at capacity raises `WorkerCapacityError` → surfaced as a visible failed King report (One-Law: no invisible governance). Thin primitive, not a service. 5 tests; 1201 passed/87.24%.

## Verification-Strength Taxonomy (roadmap Phase 1 keystone, vertical slice) — DONE + VERIFIED (2026-06-28)
"verified" now means ONE strength (floor STRONG). `aios/core/verification_strength.py`: STRONG/MEDIUM/WEAK/NONE, COMMAND-AWARE `derive_strength` (STRONG requires a recognized test runner in PROGRAM position or a structural pair like `-m pytest` — a token in arg position can't forge it), `meets_promotion_floor` (floor clamps below-WEAK→STRONG, fail-closed). `Verifier` stamps `result.strength`; `format_verifier_result` emits a `(strength=…)` token; `main.py` reads it → `SkillMemory.record_attempt(strength=)` gates promotion (below-floor success → `weak_success_count`, never the eligible `success_count` → can't become `verified`). Schema migrated (2 cols). `TestingQueen` stamps strength (parses worker pytest stdout from ledger). Adversarial review (Verifier-owned, §6): found + FIXED [HIGH] arg-position runner-token forge (`echo …pytest… 5 passed`→STRONG) + [LOW] NONE-floor clamp; stdout-injection/rate-math/laundering/consolidation all HELD. Spec: `docs/superpowers/specs/2026-06-28-verification-strength-taxonomy-design.md`. Verified: 1221 passed/1 skipped, 87.35%.

## Single Next Action — NEXT SLICE CHOSEN: extend the strength gate to the OTHER promotion sites
Operator chose: adopt `meets_promotion_floor` (from `aios.core.verification_strength`) at the remaining learning-calibration sites so ALL of them gate on strength, not just skills: `aios/agents/swarm_patterns.py` `record_attempt` (main.py:3023 caller), `curriculum` `record_matching` (main.py:3029), `aios/memory/development.py` (verified success-rate per task/model), and `mistake`→planner-confidence (`aios/memory/mistake.py` + planner). Each: add a `strength` param (default STRONG back-compat), gate the verified/eligible path on `meets_promotion_floor`, thread `result.strength` from the live callers (main.py already computes `strength_from_text(evidence)` — reuse it). Brainstorm → spec → build → adversarial review (Verifier owns Phase 1). Then consider flipping `record_attempt` strength default to fail-closed once all callers pass it. HONEST CONTEXT (unchanged): roadmap argues the council layer should be THIN functions over existing agents + rendered as anatomy; our build leans parallel + the dashboard violates The One Law. After Phase 1 fully lands: Phase 2 container-by-default execution (worker uses host subprocess.run); Phase 3 ledger/scanner hardening; render strength as anatomy.

## Open Approvals / Blockers
- Local `.env` sets `AIOS_ROUTER_CLOUD_TASKS=reasoning,coding`; mask it with `$env:AIOS_ROUTER_CLOUD_TASKS=''` when testing default local-first privacy behavior.
- The roadmap proof target `frontend/src/pages/Login.jsx` is stale in the current repo, so Phase 1A/1B/Dashboard tests use temp workspaces or seeded artifacts with that relative path. Do not wire a real product mission to that stale path without updating the target.
- Cloud reasoning is implemented as injectable clients plus policy evidence; no live cloud provider is invoked by tests, and workers still never see provider SDKs or API keys.
- Dashboard-lite is artifact-backed. It records report decisions and responds to file-backed worker approvals, but Phase 3A-lite must make Council verdicts/events durable and replayable.
- The preserved knowledge-graph WIP remains in `stash@{0}` from the prior sync task; do not drop it without explicit operator instruction.
- Kimi is currently off; proceed solo unless the operator re-enables a reviewer.

## Active Files
- `.aios/state/RESUME.md`
- `.aios/memory/experiences.jsonl`
