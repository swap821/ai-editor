# GAGOS v10 Integration Plan

Date: 2026-07-09
Audit: `.aios/state/V10_INTEGRATION_AUDIT.md`
Status: Phase 0, Phase 1, Phase 2, Phase 3, and Phase 4 implemented and verified
locally on 2026-07-09.

Goal: integrate the useful GAGOS v10 "Sovereign Organism" contract into the
real GAGOS repo without replacing the proven security, memory, router,
verifier, audit, council, worker, self-apply, pheromone, hibernation, resource,
or UI spine.

Core rule: v10 is vocabulary and contract, not production code. Scaffold files
with `NotImplementedError` or allow/pass defaults must not enter production.

## Global Invariants

- RED never auto-runs and cannot be earned.
- YELLOW still requires human approval unless already covered by exact-class,
  verifier-backed earned autonomy.
- Security gateway, scope lock, audit logger, secret scanner, and injection
  shield remain frozen core.
- No change under `aios/security/*` without explicit Section VIII approval.
- No cloud call unless existing router/intelligence policy permits it.
- No new module may become a parallel authority over gateway, verifier,
  approval, router, budget, or self-apply.
- All new outputs begin as proposal/evidence unless an existing authority
  explicitly accepts them.
- UI surfaces must be backend-backed and truthful.

## Phase 0 - Truth, Drift, And Safety Gate

Purpose: make the repo honest about the post-v7 state and prevent v10 plan drift
from becoming new dogma.
Status: Complete. `tools/thesis_audit.py`, docs, and focused tests now guard
post-v7 truth/config drift.

Files:
- Extend `tools/thesis_audit.py`.
- Extend `tests/test_thesis_audit.py`.
- Update stale canonical docs only after tests identify drift:
  - `README.md`
  - `.aios/state/AUDIT.md`
  - `.aios/state/GAGOS_ULTRA_PLAN.md`
  - `.aios/state/SYSTEM_TRUE_PICTURE.md` if required

Checks to add:
- Post-v7 Project Passport is not documented as purely roadmap/missing.
- Post-v7 pheromones/castes/Royal Decree/resource/hibernation/UI are not
  documented as empty scaffold if the live modules and tests exist.
- v10 "empty cloud_tasks means local-only" wording is accepted only when framed
  as an override, not as the live default.
- Frozen-core v10 target files under `aios/security/*` are documented as
  approval-gated.

Exit gate:
- `python tools/thesis_audit.py`
- `.venv\Scripts\python.exe -m pytest tests/test_thesis_audit.py -q`
- Related router/config focused tests still pass if cloud docs are touched.
- No runtime behavior changes.

## Phase 1 - Constitution Facade And Enforcer Adapter

Purpose: add executable constitutional vocabulary without creating a parallel
security authority.
Status: Complete. The facade snapshots live config/caste/resource defaults, and
the enforcer delegates to the existing security gateway, router policy, budget
guard, and caste contract checks.

Files:
- Add `aios/policy/constitution.py`.
- Add `aios/policy/constitution_enforcer.py`.
- Add `tests/test_constitution.py`.

Behavior:
- Read current invariants from `aios.config`, `aios.runtime.castes`,
  `aios.runtime.resource_ecology`, and policy defaults.
- Enforcer delegates to existing gateway/router/budget/caste/self-apply logic.
- It may add blocks, caution, or review requirements.
- It may not downgrade RED or auto-approve YELLOW.

Exit gate:
- Frozen paths are refused.
- Cloud checks reflect live router policy.
- Caste spawn checks reflect live caste profiles.
- Tests prove RED cannot be overridden by constitution output.

Verification:
- `.venv\Scripts\python.exe -m pytest tests/test_constitution.py -q` -> 5 passed
- `.venv\Scripts\python.exe -m pytest tests/test_constitution.py tests/test_castes.py tests/test_hibernation_resource.py tests/test_router.py tests/test_policy_engine.py tests/test_thesis_audit.py -q` -> 55 passed
- `.venv\Scripts\python.exe -m pytest -q` -> passed, 4 skipped, total coverage 92%

## Phase 2 - Immune System, Read-Only First

Purpose: implement the vulture as local evidence and quarantine proposals
before any destructive sanitation.
Status: Complete. Implemented as `aios/maintenance/vulture_sanitation.py`, not
under frozen `aios/security/*`. It emits redacted proposal/evidence findings
only and performs no writes, cloud calls, memory mutation, pheromone mutation,
or policy mutation.

Files:
- Preferred staging: add `aios/maintenance/vulture_sanitation.py`.
- Add tests under `tests/test_vulture_sanitation.py`.
- Only use `aios/security/vulture_sanitation.py` after explicit Section VIII
  approval.

Behavior:
- Detect cognitive-parasite patterns in memory-like text, docs, and proposed
  lessons.
- Detect stale or contradictory policy/pheromone evidence.
- Emit structured findings and quarantine proposals.
- Do not delete, mutate memory, mutate pheromones, edit files, or suspend
  policy autonomously.

Exit gate:
- Findings are deterministic and redacted.
- Security-bypass advice is flagged.
- Vulture proposals cannot override gateway or verifier.
- No writes occur during read-only scans.

Verification:
- `.venv\Scripts\python.exe -m pytest tests/test_vulture_sanitation.py -q` -> 4 passed
- `.venv\Scripts\python.exe -m pytest tests/test_vulture_sanitation.py tests/test_constitution.py tests/test_hibernation_resource.py tests/test_thesis_audit.py tests/test_dead_code_hygiene.py tests/test_security.py -q` -> 70 passed, 2 skipped
- `python tools\thesis_audit.py` -> ok
- `.venv\Scripts\python.exe -m pytest -q` -> passed, 4 skipped, total coverage 92%

## Phase 3 - Ecosystem Scanner, Local-Only

Purpose: add environmental defense without network or secret exposure.
Status: Complete. Implemented as `aios/maintenance/ecosystem_scanner.py`, not
under frozen `aios/security/*`. It emits redacted proposal/evidence findings
only and performs no writes, cloud calls, or network calls.

Files:
- Preferred staging: add `aios/maintenance/ecosystem_scanner.py`.
- Add tests under `tests/test_ecosystem_scanner.py`.
- Only use `aios/security/ecosystem_scanner.py` after explicit Section VIII
  approval.

Behavior:
- Scan local dependency manifests and lockfiles.
- Scan API response strings for secrets and prompt-injection signals using
  existing scanners.
- Scan local git history or current tree only when explicitly invoked.
- Validate local model metadata only if present locally.
- Emit proposal/evidence findings only.

Exit gate:
- No network calls.
- Secrets are redacted before persistence.
- Findings cannot authorize blocking beyond existing security policy until
  explicitly wired.
- Tests prove cloud/network attempts are absent or blocked.

Verification:
- `.venv\Scripts\python.exe -m pytest tests/test_ecosystem_scanner.py -q` -> 5 passed
- `.venv\Scripts\python.exe -m pytest tests/test_thesis_audit.py -q` -> 4 passed
- `python tools\thesis_audit.py` -> ok after docs were corrected

## Phase 4 - Signal Ganglia And Council Memory

Purpose: evolve council deliberation from prose-heavy records toward typed
signals while preserving the call chain.
Status: Complete locally. Implemented as advisory adapters over the existing
queen/council chain, with route-level summary evidence and append-only council
memory persistence. Security remains the only deterministic veto-capable
signal; ganglia synthesis cannot authorize action.

Files:
- Add `aios/council/ganglia.py`.
- Add `aios/council/council_memory.py`.
- Modify `aios/council/council_orchestrator.py` narrowly.
- Modify `aios/api/routes/council.py` to surface backend-backed summary fields.
- Modify `aios/runtime/king_report.py` to carry ganglia evidence into reports.
- Add tests under `tests/test_ganglia.py` and `tests/test_council_memory.py`.

Behavior:
- Convert existing queen outputs into typed gradients/signals.
- Persist deliberation/verdict evidence append-only.
- Security signal remains deterministic and veto-capable.
- LLM/memory/reflection signals are strengthen-only.
- Council memory can suggest precedent, never authorize action.

Exit gate:
- Security veto wins over positive plan/memory signals.
- Council memory persistence survives reload.
- No existing council API breaks.

Verification:
- Red-first API gap:
  `.venv\Scripts\python.exe -m pytest tests\test_council_origination.py::test_originate_deliberates_to_awaiting_approval -q`
  failed before route summary/council-memory wiring.
- Red-first execution gap:
  `.venv\Scripts\python.exe -m pytest tests\test_council_orchestrator.py::test_council_orchestrator_runs_full_loop_and_records_report -q`
  failed before post-testing ganglia refresh.
- `.venv\Scripts\python.exe -m pytest tests\test_ganglia.py tests\test_council_memory.py tests\test_council_orchestrator.py tests\test_council_origination.py -q`
  -> 21 passed.
- `python tools\thesis_audit.py` -> ok.
- `.venv\Scripts\python.exe -m pytest -q` -> passed, 4 skipped, total coverage
  92%.
- GitHub CI run `29000047721` -> success.
- GitHub CodeQL Advanced run `29000047695` -> success.

## Phase 5 - Symbol RepoMap

Purpose: add symbol-level project map on top of Project Passport.

Status: Complete locally as of 2026-07-09 for the core scanner and contract
scope hints. No API/UI exposure was added in this slice.

Files:
- Add `aios/cognition/repo_map.py`.
- Add tests under `tests/test_repo_map.py`.
- Optionally add status/query API after the core is tested.

Behavior:
- Build AST/import graph using stdlib first.
- Compute deterministic symbol ranking with existing `networkx` if needed.
- Produce patch/scope hints for Royal Decree and worker contracts.
- Remain local-only and proposal/evidence only.

Exit gate:
- Scans skip secrets and ignored paths.
- Symbol queries are deterministic.
- RepoMap hints cannot widen worker scope.
- Project Passport trusted-memory safety still passes.

Verification:
- Red-first `.venv\Scripts\python.exe -m pytest tests\test_repo_map.py -q`
  failed before `aios.cognition` existed.
- `.venv\Scripts\python.exe -m pytest tests\test_repo_map.py tests\test_project_passport.py -q`
  -> 10 passed.
- `python tools\thesis_audit.py` -> ok.
- `.venv\Scripts\python.exe -m pytest -q` -> passed, 4 skipped, total coverage
  92%.

## Phase 6 - Meta-Loop And Council Self-Assessment

Purpose: convert v10 self-assessment into local proposals, not autonomous
self-rewrite.

Files:
- Add `aios/learning/meta_loop.py` only if it composes existing reflection,
  mistake, skill, audit, policy, and hibernation evidence.
- Add tests under `tests/test_meta_loop.py`.

Behavior:
- Summarize evidence.
- Propose improvements.
- Never run cloud, edit files, self-apply, or mutate policy by itself.

Exit gate:
- Outputs are proposals.
- Hibernation local-only tests still pass.
- Policy evolution remains additive/reviewed.

## Phase 7 - UI Truth Surface

Purpose: show v10 state only after backend evidence exists.

Files:
- Add or extend backend status endpoints.
- Modify `frontend/src/workbench/SovereignStatePanel.jsx`.
- Add frontend tests beside existing workbench tests.

Indicators:
- Constitution status.
- Vulture findings count and last scan.
- Ecosystem scanner status.
- Council memory health.
- Symbol RepoMap freshness.

Exit gate:
- UI reads real backend endpoints.
- Offline/error state is honest.
- No fake "alive" animation.

## Deferred - Federation, CodeAgent Mandibles, Structural Reform

Do not implement until all earlier phases are proven and separately approved.

Reasons:
- Federation sends or receives data outside the local operator boundary.
- Unrestricted Code-as-Action would duplicate and weaken existing executor,
  worker, approval, audit, verifier, and rollback contracts.
- Structural reform can become self-modification and must use the existing
  self-apply approval path.

## Recommended Immediate Work

After Phase 4 full-suite and CI verification, the next safe scope is Phase 5:
Symbol RepoMap. Keep it local-only and advisory over Project Passport, and prove
it cannot activate trusted memory or widen worker scope.
