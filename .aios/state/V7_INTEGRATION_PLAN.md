# GAGOS v7 Integration Plan

> For agentic workers: execute one phase at a time. Do not start the next phase
> until the current phase has focused tests green and the phase result is
> recorded in `.aios/state/RESUME.md`.

Goal: integrate the useful GAGOS v7 "Sovereign Superorganism" concepts into the
real `ai-editor` architecture without replacing working safety, memory,
router, verifier, audit, council, worker, self-apply, pheromone, or UI systems.

Status as of 2026-07-08: Phases A through G have been implemented and verified
without replacing the existing safety spine. The plan remains here as the
integration contract and regression checklist.

Architecture: treat the scaffold as vocabulary and contract inspiration only.
Every change extends an existing module boundary unless there is no existing
owner. All new outputs are advisory/proposal/evidence until explicitly approved
or verified by the existing gates.

Global constraints:
- Do not modify frozen security core without explicit Section VIII approval.
- RED actions never auto-run.
- YELLOW actions require human approval unless already covered by exact-class,
  verifier-backed earned autonomy.
- No cloud call may happen unless the existing policy explicitly allows it.
- RepoMap/Project Passport scans are local-only and never trusted memory by
  default.
- Pheromones are typed, decaying, auditable suggestions only.
- Plans and Royal Decrees are advisory and must not bypass approval, gateway,
  scope lock, verifier, or human veto.

## Phase A - Truth/Safety Guard

Purpose: make cloud-routing and thesis claims machine-checkable before feature
work.

Files:
- Create `tools/thesis_audit.py`.
- Create `tests/test_thesis_audit.py`.
- Modify `README.md`, `AGENTS.md`, `.aios/state/PLAN.md`,
  `aios/core/router.py`, `aios/core/router_wiring.py`, and
  `tests/adversarial/test_cloud_privacy.py` prose as needed.

Steps:
- Write a failing test that imports `tools.thesis_audit` and asserts no drift
  findings for canonical docs.
- Implement the minimal audit script.
- Watch the test fail on the current stale cloud-routing docs.
- Update docs/prose to match `aios/config.py`:
  `_ROUTER_CLOUD_TASKS_DEFAULT == ("reasoning", "coding")`; setting
  `AIOS_ROUTER_CLOUD_TASKS=""` forces local-only; cloud still requires an
  actually configured provider and privacy filtering.
- Run focused and related tests.

Exit gate:
- `tests/test_thesis_audit.py` passes.
- Router/config related tests pass.
- No runtime security behavior is changed.

## Phase B - Project Passport / RepoMap

Purpose: add a local-only repo scanner that produces project evidence, not
trusted memory.

Files:
- Create `aios/memory/project_passport.py`.
- Add an API route under `aios/api/routes/`.
- Add focused tests.

Behavior:
- Scan a repo root and produce purpose, stack, folder map, key files, install
  commands, run commands, build commands, test commands, env vars, safe actions,
  risky actions, known issues, current goals, and suggested improvements.
- Read only local files and metadata.
- Ignore secrets and never send scanned data to cloud.
- Persist only as proposal/evidence, pending human review.

Exit gate:
- Tests prove RepoMap does not activate trusted memory automatically.
- Tests prove credential-like and ignored paths are not exposed in output.

## Phase C - Pheromone Wiring

Purpose: reuse `PheromoneStore` so trails inform planning/worker assignment
without becoming authority.

Files:
- Extend a narrow council/planner contract-building path.
- Add focused pheromone/security tests.

Behavior:
- Call `PheromoneStore.for_contract()` for allowed files when pheromones are
  enabled and add strings to `MissionContract.pheromone_context`.
- Positive trails may influence ordering or add hints.
- Failure-warning trails may add caution/defer constraints.
- No trail can turn RED into YELLOW/GREEN or skip approval.

Exit gate:
- Test proves pheromone suggestions cannot override RED security decisions.

## Phase D - Caste Contracts

Purpose: define v7 castes over existing worker runtime.

Files:
- Create `aios/runtime/castes.py`.
- Apply profiles where `MissionContract` is drafted.
- Add tests.

Castes:
- Forager: read-only discovery.
- Builder: scoped edits.
- Scout: tests/verification.
- Soldier: security inspection, read-only.
- Nurse: debugging/failure diagnosis.

Each caste has allowed tools, forbidden tools, allowed file scope, timeout,
verification requirements, and evidence output contract.

Exit gate:
- Tests prove forbidden tools are blocked, Builder cannot edit outside scope,
  and Soldier is read-only.

## Phase E - Royal Decree Flow

Purpose: add a named complex-task flow around existing planner/council runtime.

Behavior:
- For complex tasks: scout first -> structured plan -> council reviews ->
  worker contracts generated -> execution -> verifier -> KingReport.
- Plans remain advisory.
- Existing `AIOS_PLAN_STAGE` tests remain green.

Exit gate:
- Existing plan-stage tests pass.
- New tests show Royal Decree does not bypass approval/security.

## Phase F - Hibernation + Resource Ecology

Purpose: implement local-only maintenance and resource mode tracking.

Behavior:
- Track cloud calls, estimated cost, worker count, host pressure where
  available, and mode: normal/conservation/hibernation.
- Fail closed for expensive/cloud operations when budget or mode disallows.
- Hibernation may compact memory, decay pheromones, rebuild RepoMap, summarize
  audit state, and propose improvements.
- Hibernation may not write autonomously, call cloud, self-modify, git push, or
  access credentials.

Exit gate:
- Tests prove hibernation cannot perform cloud calls or writes.
- Tests prove resource ecology blocks cloud when budget/mode disallows.

## Phase G - UI Truth Surface

Purpose: expose truthful backend-backed indicators only.

Backend-backed indicators:
- RepoMap status.
- Current caste workers.
- Pheromone trails.
- Resource mode.
- Hibernation status.
- Pending proposals.

Exit gate:
- UI/API tests prove displayed values come from backend responses.
- No fake "alive" animation is added without real backend events.
