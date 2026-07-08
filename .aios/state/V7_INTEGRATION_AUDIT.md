# GAGOS v7 Integration Audit

Date: 2026-07-08
Task: `v7-sovereign-integration`
Scaffold inspected: `gagos_v7_scaffold.zip`
Plan reference inspected: `GAGOS_ULTRA_PLAN_v7.md`

## Executive Finding

The scaffold is a blueprint/reference layer, not an implementation to copy. Its
modules are small skeletons that overlap heavily with working code already in
this repository. The safe integration path is to preserve the existing security,
memory, router, verifier, audit, council, worker, self-apply, and UI spine, then
add missing organs as typed, tested extensions.

Current live risk before v7 feature work: canonical docs still contradict
`aios/config.py` for cloud-routing defaults. Phase A must add a machine-checked
drift guard and update the stale cloud-egress claims before any RepoMap,
pheromone, caste, or hibernation feature work starts.

## What Already Exists

- Security spine: `aios/security/{gateway,scope_lock,secret_scanner,audit_logger,injection_shield}.py`.
  RED remains unapprovable; YELLOW routes through approval; scope locks and
  audit logging are already load-bearing. Do not modify frozen core in this
  integration without explicit Section VIII approval.
- Execution and mandibles-equivalent paths: `aios/core/executor.py`,
  `aios/core/verifier.py`, `aios/core/self_apply.py`, `aios/runtime/worker_api.py`,
  `aios/runtime/spawner.py`, and rollback/snapshot stores. Writes already have
  scope checks, audit-before-write patterns, verifier integration, and rollback
  paths in the relevant subsystems.
- Router: `aios/core/router.py` and `aios/core/router_wiring.py` implement a
  deterministic policy gate plus evidence calibration and optional local LLM
  picker. Live config default is
  `_ROUTER_CLOUD_TASKS_DEFAULT = ("reasoning", "coding")`; an empty
  `AIOS_ROUTER_CLOUD_TASKS` still forces local-only.
- Planning: `aios/core/planner.py`, `aios/core/native_planner.py`, and
  `AIOS_PLAN_STAGE` provide advisory planning without execution authority.
  Existing tests in `tests/test_plan_stage.py` pin fail-open and approval
  coexistence behavior.
- Pheromones/stigmergy: `aios/memory/pheromones.py` already provides typed
  SQLite-backed pheromones with decay, reinforcement, query, and
  `for_contract()`. Routes exist in `aios/api/routes/sovereignty.py`, gated by
  `AIOS_PHEROMONE_ENABLED`.
- Council/Ganglia: `aios/council/*` has `PlannerQueen`, `SecurityQueen`,
  `MemoryQueen`, `TestingQueen`, optional `CritiqueQueen`, King report storage,
  and optional King reasoning. `SecurityQueen` is deterministic and strongest.
- Worker runtime/castes: `aios/runtime/contracts.py` has `MissionContract` with
  allowed/forbidden tools, allowed/forbidden files, timeout, verification
  commands, `pheromone_context`, and required output. `WorkerRuntime` enforces
  allowed tools, path scope, verification command allowlists, and gateway
  re-checks. `aios/agents/swarm.py` and `aios/agents/role_pass.py` already use
  ephemeral castes with tool subsets.
- Resource budget: `aios/runtime/budget_guard.py` tracks in-process cloud-call,
  token, and cost budgets for Council Runtime intelligence. It is not yet a
  full host-resource ecology with normal/conservation/hibernation modes.
- Self-modification: `aios/core/self_apply.py` already implements proposal ->
  human approval -> diff confinement -> audit-before-write -> apply -> verify ->
  rollback on failure, and refuses frozen core.
- UI truth surfaces: `frontend/src/workbench/CouncilDashboard.jsx` and
  `SovereignStatePanel.jsx` show council missions, self-analysis proposals,
  earned autonomy, fact proposals, skill trails, and curriculum proposals.
  `swarmHUDStore.ts` and related bridge code already show live caste events.

## What Is Missing Or Partial

- RepoMap / Project Passport does not exist. There is no
  `aios/memory/project_passport.py`, no `/api/v1/projects/scan`, and no
  passport storage/approval flow. Scanned output must be proposal/evidence only,
  not trusted memory.
- Machine-checked thesis/config drift guard does not exist. Known live drift:
  README/AGENTS and some code comments claim local-only cloud routing by
  default, while `config.py` defaults cloud-eligible tasks to reasoning/coding.
- Pheromone store is not consistently wired into council/worker contracts.
  `MissionContract.pheromone_context` and `PheromoneStore.for_contract()` exist,
  but no single planner/council path reliably populates context from the store.
- Named v7 caste contracts are not centralized. Existing castes are spread
  across swarm/role-pass prompts and `MissionContract` fields. There is no typed
  `Forager`, `Builder`, `Scout`, `Soldier`, `Nurse` policy table.
- Queen services are partial. Deterministic queen classes exist, but
  `queen_service.py` only ships a `SecurityQueenService`; no long-lived
  Memory/Plan/Verify/Reflect/Synthesis services are registered.
- Royal Decree flow is partial. The advisory planner and Council deliberation
  exist, but no named scout-first -> structured plan -> council review ->
  generated worker contracts -> verifier -> KingReport flow is exposed as a
  single complex-task path.
- Hibernation is not implemented as a local maintenance mode. Compaction,
  pheromone decay, audit summaries, and RepoMap rebuilds are manual endpoints or
  future work.
- Resource ecology is partial. BudgetGuard handles mission-scoped cloud/token
  budget, but not host CPU/memory pressure or system mode.
- UI truth surface is partial. Existing UI has council and sovereignty panels,
  but no backend-backed indicators for RepoMap status, resource mode,
  hibernation status, or pending passport proposals.

## What The Scaffold Duplicates

- `cognition/stigmergy_field.py` duplicates `aios/memory/pheromones.py` but is
  in-memory and unaudited.
- `cognition/ganglia_council.py` duplicates `aios/council/*` and lacks the
  existing deterministic Security Queen and verifier integration.
- `agents/caste_system.py` duplicates swarm/role-pass caste concepts but lacks
  allowed tool/file enforcement.
- `agents/mandibles.py` duplicates executor, worker runtime, and self-apply
  abstractions without security/audit/approval semantics.
- `planning/nest_expansion.py` duplicates `aios/core/self_apply.py` without the
  hardened proposal/apply/rollback contract.
- `learning/resource_ecology.py` overlaps `aios/runtime/budget_guard.py` but is
  only an unconstrained allocation sketch.
- `learning/hibernation.py` overlaps future maintenance flows but contains no
  compaction, pheromone decay, audit, or RepoMap work.
- `ui/environmental_interface.py` duplicates the existing React dashboard
  concept and has no backend event source.

## What Should Be Integrated

- Phase A: add a thesis/config drift audit and fix canonical cloud-routing
  documentation to match live config. This is the required safety gate.
- Phase B: implement `aios/memory/project_passport.py` as a local-only harvester
  that emits proposal/evidence, plus an API route and tests. Do not write scans
  into trusted memory automatically.
- Phase C: reuse `PheromoneStore`. Wire `for_contract()` into planner/council
  contract generation and tests proving pheromones cannot override RED/YELLOW
  authority.
- Phase D: add a typed caste policy table over existing `MissionContract` and
  worker runtime. Keep enforcement in `WorkerRuntime` and `SecurityQueen`.
- Phase E: add a named Royal Decree wrapper around existing planner/council
  phases. It must remain advisory and preserve `AIOS_PLAN_STAGE` behavior.
- Phase F: extend `BudgetGuard` into a resource ecology and add local-only
  hibernation maintenance. No cloud calls, writes, self-modification, git push,
  or credential access in hibernation.
- Phase G: add UI indicators only after backend status endpoints exist.

## What Should Be Ignored

- Do not copy `gagos_v7/aios/*` wholesale.
- Do not add a parallel `aios/cognition/` tree for systems already implemented.
- Do not replace `PheromoneStore`, `CouncilOrchestrator`, `WorkerRuntime`,
  `Executor`, `Verifier`, `SelfApplyEngine`, or router policy.
- Do not introduce unrestricted code execution under the "mandibles" name.
- Do not widen `SCOPE_ROOTS`, touch frozen security core, or make cloud egress
  depend on model reasoning.
- Do not add fake UI "alive" states that are not backed by backend events.

## Exact Files To Modify

Phase A:
- Create `tools/thesis_audit.py`.
- Create `tests/test_thesis_audit.py`.
- Update `README.md`, `AGENTS.md`, `.aios/state/PLAN.md`,
  `aios/core/router.py`, `aios/core/router_wiring.py`, and stale test/doc
  prose in `tests/adversarial/test_cloud_privacy.py`.
- Update `.aios/state/RESUME.md` after the phase result.

Phase B:
- Create `aios/memory/project_passport.py`.
- Add API route under `aios/api/routes/` and include it from `aios/api/main.py`.
- Add tests, likely `tests/test_project_passport.py` and API coverage.
- Add storage under `.aios/projects/` or `data/` only as proposal/evidence.

Phase C:
- Modify `aios/council/queens/planner.py` or a narrow helper that constructs
  `MissionContract`.
- Modify tests around `tests/test_council_orchestrator.py`,
  `tests/test_pheromones.py`, or new focused tests.

Phase D:
- Create `aios/runtime/castes.py`.
- Modify `aios/council/queens/planner.py` or route origination to apply caste
  profiles.
- Add tests for forbidden tools and scopes.

Phase E:
- Create or extend a planning module, preferably `aios/core/royal_decree.py`
  or a small council wrapper, without altering `AIOS_PLAN_STAGE` semantics.
- Add tests beside planner/council tests.

Phase F:
- Create `aios/runtime/resource_ecology.py` only if it extends
  `BudgetGuard` cleanly.
- Create `aios/runtime/hibernation.py` for local-only maintenance orchestration.
- Add tests for no cloud/no writes/no credentials.

Phase G:
- Add backend status endpoints first, then update
  `frontend/src/workbench/SovereignStatePanel.jsx` and tests.

## Risk Level Per Change

- Phase A thesis/config guard: Medium. It touches docs and a new test script,
  but no runtime behavior. Risk is false positives in doc scanning.
- Phase B Project Passport: Medium/High. It scans arbitrary repos and must avoid
  secrets, cloud egress, and trusted-memory activation.
- Phase C pheromone wiring: Medium. It influences planning, so tests must prove
  suggestions never override security or approval.
- Phase D caste contracts: Medium. It constrains existing worker contracts; risk
  is breaking legitimate missions if defaults are too narrow.
- Phase E Royal Decree: Medium. It changes complex-task orchestration; risk is
  accidentally turning advisory plans into authority.
- Phase F hibernation/resource ecology: Medium/High. It touches maintenance and
  budget decisions; risk is accidental writes/cloud calls during low-power mode.
- Phase G UI: Low/Medium after backend endpoints exist. Risk is showing stale or
  fabricated state.

## Test Plan

- Phase A:
  - `tests/test_thesis_audit.py` must fail on stale cloud-routing docs before
    docs are updated.
  - Focused run: `.venv\Scripts\python.exe -m pytest tests/test_thesis_audit.py -q`.
  - Related run: `.venv\Scripts\python.exe -m pytest tests/test_config.py tests/adversarial/test_cloud_privacy.py tests/test_route_wiring.py tests/test_router.py -q`.
- Phase B:
  - Unit tests for stack/command/env/risky-file detection.
  - API tests proving scans are proposal/evidence only and do not write trusted
    memory.
  - Fixtures for Python app, Node app, monorepo, empty dir, and non-git dir.
- Phase C:
  - Tests that pheromone context appears in contracts.
  - Tests that RED security verdicts remain RED even with positive pheromones.
- Phase D:
  - Tests for each caste's allowed/forbidden tools, file scope, timeout, and
    evidence output.
  - Builder cannot edit outside scope; Soldier is read-only.
- Phase E:
  - Tests for scout-first planning, council review, generated contracts, and
    KingReport output.
  - Existing `AIOS_PLAN_STAGE` tests stay green.
- Phase F:
  - Tests that hibernation cannot cloud-call, write, self-modify, git push, or
    read credentials.
  - Resource ecology blocks cloud when mode/budget disallows.
- Phase G:
  - API/UI tests that indicators reflect backend state, not animation-only
    placeholders.
