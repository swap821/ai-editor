# GAGOS v10 Integration Audit

Date: 2026-07-09
Task: `v10-integration-audit`
Repo head inspected: `17858d2`
Scaffold inspected: `gagos_v10_scaffold.zip`
Plan reference inspected: `GAGOS_ULTRA_PLAN_v10_COMPLETE.md`

## Executive Verdict

v10 is a strong architectural direction, but it is not safe to execute as
written. Its best contribution is the three-pillar framing:

- Cage: deterministic action prevention, scope, approval, audit, rollback.
- Immune system: internal rot detection, quarantine, anti-parasite checks.
- Ecosystem: dependency, model, API, git, and config-environment scanning.

That framing is useful because it names real missing defensive layers. The
uploaded scaffold, however, is mostly interface stubs. Several modules raise
`NotImplementedError`, and some safety-critical stubs return allow/pass by
default, including the scaffold `SecurityGanglion` and `TestingGanglion`. Those
files must not be copied into the live package or imported into production.

Honest opinion: v10 is worth pursuing as a contract, but the plan overstates how
much is missing because v7 integration has already made RepoMap/Project
Passport, pheromones, caste contracts, Royal Decree, resource ecology,
hibernation, and sovereignty UI surfaces real. The next useful work is not
"fill empty files"; it is a truth/safety Phase 0 that reconciles docs with the
post-v7 code, expands machine drift checks, and gates any frozen-core immune or
ecosystem implementation behind explicit Section VIII approval.

## Current Live System Already Stronger Than The Scaffold

- Security cage: `aios/security/gateway.py`, `scope_lock.py`,
  `secret_scanner.py`, `audit_logger.py`, and `injection_shield.py` are the
  frozen deterministic spine. RED remains unapprovable; YELLOW goes through
  approval or exact earned-autonomy rules; unknown fails closed.
- Self-apply: `aios/core/self_apply.py` already implements proposal -> human
  approval -> diff confinement -> audit before write -> apply -> verify ->
  rollback on failure. It refuses frozen core.
- Router/cloud policy: `aios/core/router.py`, `router_wiring.py`, and
  `aios/runtime/intelligence_gateway.py` provide deterministic cloud policy
  gates. Live config default is `AIOS_ROUTER_CLOUD_TASKS=reasoning,coding`;
  setting `AIOS_ROUTER_CLOUD_TASKS=""` forces local-only.
- Policy evolution: `aios/policy/engine.py` already provides a tested
  additive-only policy proposal/vote/enact/suspend store. The v10
  `policy_evolution.py` scaffold duplicates it in weaker form.
- Pheromones: `aios/memory/pheromones.py` is real, typed, SQLite-backed,
  decaying, queryable, and already wired into council contracts when enabled.
  The v10 pheromone scaffold is a non-functional duplicate.
- Caste contracts: `aios/runtime/castes.py` defines Forager, Builder, Scout,
  Soldier, and Nurse as contract clamps over the existing worker runtime.
  Tests prove forbidden tools, builder scope, and Soldier read-only behavior.
- Royal Decree: `aios/council/royal_decree.py` adds scout-first advisory
  complex-task planning without bypassing security, approval, or verification.
- Project Passport: `aios/memory/project_passport.py` already scans locally and
  emits proposal/evidence only, not trusted memory.
- Resource ecology and hibernation: `aios/runtime/resource_ecology.py`,
  `aios/runtime/budget_guard.py`, and `aios/runtime/hibernation.py` already
  support local-only maintenance posture and fail-closed cloud blocking by mode.
- UI truth surface: `frontend/src/workbench/SovereignStatePanel.jsx` already
  reads backend-backed status for RepoMap, resource mode, hibernation,
  pheromones, caste workers, autonomy, and pending proposals.

## What The v10 Scaffold Duplicates

- `aios/memory/pheromones.py`: duplicates the live `PheromoneStore` but raises
  `NotImplementedError`.
- `aios/agents/caste_system.py`: duplicates `aios/runtime/castes.py` and the
  existing spawner contract model.
- `aios/cognition/royal_decree.py`: duplicates the live advisory council Royal
  Decree implementation.
- `aios/policy/policy_evolution.py`: duplicates `aios/policy/engine.py`.
- `aios/council/ganglia.py`: overlaps with `aios/council/council_orchestrator.py`
  and queen classes, but the scaffold stubs lack the live security/verifier
  authority.
- `aios/cognition/repo_map.py`: overlaps with Project Passport for project
  scanning but is useful as a future symbol-graph contract.

## What Remains Valuable Or Missing

- Executable constitution facade: the repo has policy evolution and config
  truth, but no single typed constitution facade that summarizes runtime
  invariants for file edits, cloud, castes, energy, amendments, and frozen-core
  posture.
- Constitution enforcer adapter: useful only as a wrapper over existing gateway,
  router, caste, budget, and self-apply checks. It must not become a parallel
  authority.
- Vulture/immune system: valuable, but must start as read-only finding and
  quarantine proposal logic. Direct purging, trail mutation, or frozen-core
  changes require explicit human approval and tests.
- Ecosystem scanner: valuable, but must start local-only and deterministic:
  dependency metadata checks, API-response prompt-injection scanning through
  existing scanners, config drift, and git history secret scanning. No network
  vulnerability feeds unless a later policy explicitly allows them.
- Signal-based ganglia: useful if added as a typed gradient layer around the
  current council, not as a replacement. Security remains deterministic and
  strongest.
- Council memory: useful if it records deliberation/verdict evidence durably,
  but it must not launder precedent into authority.
- Symbol-level RepoMap: Project Passport gives project-level context. v10's
  symbol graph, PageRank, patches, and query support remain useful future work.
- Meta-loop and council self-assessment: useful as local-only proposal
  generators. They must not self-apply, schedule cloud calls, or rewrite policy.
- Federation: unsafe and out of scope for now. Multi-instance sharing, remote
  messaging, pheromone federation, and structural reform need a separate threat
  model.

## Scaffold Parts To Ignore For Now

- Any direct "copy the code blocks" instruction.
- Any scaffold method that returns allow/pass by default in a security or
  verification role.
- Any unrestricted Code-as-Action or Mandibles path. Existing executor,
  worker runtime, gateway, audit, verifier, and self-apply remain the only
  approved execution paths.
- Any claim that autonomous code can touch frozen core. Frozen core stays
  protected by the existing Section VIII flow.
- Any federation/network sharing behavior before local immune/ecosystem layers
  are proven and threat-modeled.

## File-By-File Integration Plan

### Phase 0 - Truth, Drift, And Safety Gate

Risk: Medium. This is docs/tests plus configuration truth, not feature runtime.

Modify:
- `.aios/state/V10_INTEGRATION_AUDIT.md`: this audit.
- `.aios/state/V10_INTEGRATION_PLAN.md`: phase plan after audit lands.
- `tools/thesis_audit.py`: extend drift checks for post-v7 state and v10 claims.
- `tests/test_thesis_audit.py`: add failing cases for stale v10/local-only and
  post-v7 "designed not built" drift.
- `README.md`, `.aios/state/AUDIT.md`, `.aios/state/GAGOS_ULTRA_PLAN.md`,
  `.aios/state/SYSTEM_TRUE_PICTURE.md` as needed after tests identify stale
  claims.

Do not modify:
- `aios/security/*` in this phase.
- Runtime behavior.

Exit tests:
- `.venv\Scripts\python.exe -m pytest tests/test_thesis_audit.py -q`
- `.venv\Scripts\python.exe -m pytest tests/test_config.py tests/adversarial/test_cloud_privacy.py tests/test_route_wiring.py tests/test_router.py -q`
- `python tools/thesis_audit.py`

### Phase 1 - Constitution Facade And Enforcer Adapter

Risk: Medium. It touches policy vocabulary but must not replace authority.
Status: Implemented 2026-07-09 as a typed facade plus strengthen-only enforcer
adapter. It delegates to the existing gateway/router/budget/caste contracts and
does not modify frozen security code.

Add or modify:
- `aios/policy/constitution.py`: typed, executable description of current
  invariants using `aios.config` and existing profile tables.
- `aios/policy/constitution_enforcer.py`: wrapper that delegates to existing
  gateway/router/budget/caste/self-apply policy instead of reimplementing them.
- Tests under `tests/test_constitution.py` or `tests/test_policy.py`.

Rules:
- Constitution may add caution or block. It may not downgrade RED or approve
  YELLOW.
- Docs/config disagreement must fail tests.
- No cloud default changes.

### Phase 2 - Immune System, Read-Only First

Risk: High. The target path is under frozen security territory.
Status: Implemented 2026-07-09 as `aios/maintenance/vulture_sanitation.py`.
The frozen `aios/security/*` target remains deferred. The live scanner is
local-only, redacts secrets, reports proposal/evidence findings, and does not
mutate files, memory, pheromones, or policy.

Preferred safe staging:
- Start outside frozen core as a read-only proposal layer, for example
  `aios/maintenance/vulture_sanitation.py`, unless the operator grants explicit
  Section VIII approval to create `aios/security/vulture_sanitation.py`.
- Add structured findings, quarantine proposals, and audit entries.
- Wire no automatic purge.

Future target after approval:
- `aios/security/vulture_sanitation.py`

Tests:
- Cognitive-parasite phrases are detected as findings.
- Security-bypass lessons are quarantined as proposals, not deleted.
- Vulture cannot modify pheromones, memory, files, or policy without explicit
  approved maintenance action.
- Frozen core remains protected.

### Phase 3 - Ecosystem Scanner, Local-Only

Risk: High if placed under `aios/security`; Medium if staged as read-only
maintenance first.
Status: Implemented 2026-07-09 as `aios/maintenance/ecosystem_scanner.py`.
The frozen `aios/security/*` target remains deferred. The live scanner is
local-only, redacts secrets, reports proposal/evidence findings, and does not
perform writes, cloud calls, or network calls.

Preferred safe staging:
- Start as `aios/maintenance/ecosystem_scanner.py` or similar unless explicit
  Section VIII approval is granted for `aios/security/ecosystem_scanner.py`.

Integrate:
- `secret_scanner.scan_and_redact()` for API-response and git-history content.
- Existing injection shield/gateway semantics for suspicious text.
- Dependency metadata from local lock/config files only.
- Config drift checks from `tools/thesis_audit.py`.

Tests:
- No network calls.
- No secret persistence.
- Suspicious API responses are reported, not executed.
- Git-history scanning redacts secrets.
- Dependency findings are evidence/proposals only.

### Phase 4 - Signal Ganglia And Council Memory

Risk: Medium/High. It touches orchestration.
Status: Implemented 2026-07-09 as advisory signal adapters and append-only
council memory. It preserves the existing queen/council call chain and does not
replace security, approval, verifier, or human authority.

Add:
- `aios/council/ganglia.py`: typed `Gradient`/`GanglionSignal` DTOs and adapters
  over existing queens.
- `aios/council/council_memory.py`: durable verdict/deliberation evidence store.

Modify narrowly:
- `aios/council/council_orchestrator.py`: signal emission, non-authoritative
  contract metadata, final post-testing synthesis, and memory persistence.
- `aios/runtime/king_report.py`: includes ganglia evidence in King reports.
- `aios/api/routes/council.py`: exposes backend-backed summary evidence and
  wires `CouncilMemory` through the background mission path.

Rules:
- Security gradient is deterministic and veto-capable.
- LLM or memory gradients are strengthen-only.
- Precedent is evidence, never authority.

Verification:
- `tests/test_ganglia.py`: security veto wins and non-security signals cannot
  authorize.
- `tests/test_council_memory.py`: deliberation evidence is append-only and
  survives reload.
- `tests/test_council_orchestrator.py`: reports and ledgers carry ganglia
  evidence; final synthesis includes Testing Queen verdicts.
- `tests/test_council_origination.py`: API mission detail exposes real
  ganglia summary fields and persisted council memory.

### Phase 5 - Symbol RepoMap

Risk: Medium.

Status: Complete locally as of 2026-07-09. The implemented slice is the core
local-only Python symbol/import graph and worker-contract scope hints. API/UI
exposure remains intentionally out of this slice.

Add:
- `aios/cognition/repo_map.py`: AST/import symbol graph and PageRank using
  existing dependencies before adding any heavy parser.

Integrate:
- Project Passport as high-level project context.
- Royal Decree and worker contracts as advisory symbol-scope hints.

Tests:
- Local-only scan.
- Secret paths skipped.
- Symbol graph queries are deterministic.
- RepoMap context cannot widen worker file scope.
- Project Passport trusted-memory safety still holds under Symbol RepoMap.

Verification:
- Red-first `.venv\Scripts\python.exe -m pytest tests\test_repo_map.py -q`
  failed before `aios.cognition` existed.
- `.venv\Scripts\python.exe -m pytest tests\test_repo_map.py tests\test_project_passport.py -q`
  -> 10 passed.
- `python tools\thesis_audit.py` -> ok.
- `.venv\Scripts\python.exe -m pytest -q` -> passed, 4 skipped, total coverage
  92%.
- GitHub CI run `29010330538` on commit `34a529d` -> success.
- GitHub CodeQL Advanced run `29010330572` on commit `34a529d` -> success.

### Phase 6 - Meta-Loop And Council Self-Assessment

Risk: Medium.

Status: Complete locally as of 2026-07-09. The implemented slice is a read-only
assessment layer that turns supplied reflection, mistake, skill, audit, policy,
hibernation, and council evidence into local proposal/evidence. It cannot
authorize action, mutate policy, self-apply, write files, or call cloud.

Add:
- `aios/learning/meta_loop.py`: typed local-only snapshot, source summaries,
  blockers, and human-review proposals with secret redaction.
- `tests/test_meta_loop.py`: proposal-only contract tests.

Integrate:
- Policy engine evidence via read-only `policy_chain()` snapshots.
- Hibernation report evidence as a safety input; unsafe hibernation evidence is
  blocked and never converted into authority.
- Council/memory/audit evidence as summaries, not active memory or approvals.

Ignore:
- Scaffold-style autonomous self-rewrite loops.
- Cloud reflection, self-apply, file writes, policy mutation, or approval
  shortcuts from meta-assessment output.

Tests:
- Meta-loop output is proposal/evidence only.
- Policy evidence collection does not mutate the policy engine.
- Unsafe hibernation evidence is blocked without authorizing action.
- Secret-like evidence is redacted.
- Thesis audit catches docs that still describe Phase 6 as planned or as UI
  work once the meta-loop code exists.

Verification:
- Red-first `.venv\Scripts\python.exe -m pytest tests\test_meta_loop.py -q`
  failed before `aios.learning` existed.
- `.venv\Scripts\python.exe -m pytest tests\test_meta_loop.py -q`
  -> 4 passed.
- `.venv\Scripts\python.exe -m pytest tests\test_meta_loop.py tests\test_hibernation_resource.py tests\test_policy_engine.py tests\test_ganglia.py -q`
  -> 23 passed.
- `.venv\Scripts\python.exe -m pytest tests\test_meta_loop.py tests\test_hibernation_resource.py tests\test_policy_engine.py tests\test_ganglia.py tests\test_thesis_audit.py -q`
  -> 28 passed.
- `python tools\thesis_audit.py` -> ok.
- `.venv\Scripts\python.exe -m pytest -q` -> passed, 4 skipped, total coverage
  92%.

### Phase 7 - Runtime Wiring And UI Truth

Risk: Medium.

Modify only after backend evidence exists:
- `aios/api/routes/sovereignty.py` or a focused route module for v10 status.
- `frontend/src/workbench/SovereignStatePanel.jsx`.
- Frontend tests for real backend-backed fields.

Expose:
- Constitution status.
- Immune findings count.
- Ecosystem scanner last-run status.
- Council memory status.
- Symbol RepoMap status.
- Meta-loop proposal status.

Do not expose:
- Fake liveliness.
- Speculative federation state.
- Claimed protection that is not enforced.

### Deferred - Federation And Structural Reform

Risk: Very High.

Do not implement until:
- Local vulture and ecosystem scanners are proven.
- A federation threat model exists.
- Operator approves remote sharing boundaries.
- Tests prove no secrets, memory, or project data leave the machine without
  explicit policy.

## Current Documentation Drift To Fix In Phase 0

- `README.md` still describes Project Passport as roadmap, while
  `aios/memory/project_passport.py` and tests now exist.
- `.aios/state/AUDIT.md` predates the v7 integration and still lists Project
  Passport as designed, not built.
- The v10 uploaded plan says empty `cloud_tasks` means local-only. That is true
  only as an override statement; the live default is `reasoning,coding`.
- The v10 uploaded plan calls the current codebase "larva" and says the
  nervous system / RepoMap / castes / pheromones are missing. That is stale
  after v7 and must not become canonical repo documentation without a
  superseded banner or audit test.
- The v10 scaffold suggests `aios/security/vulture_sanitation.py` and
  `aios/security/ecosystem_scanner.py`; those are frozen-core-adjacent paths in
  this repo and need explicit approval before implementation there.

## Risk And Rollback Plan

- Phase 0 rollback: revert the docs/test commit. No runtime behavior changes.
- Policy/constitution rollback: remove the facade/enforcer imports and
  `tests/test_constitution.py`; no existing gateway/router/budget/caste
  authority was replaced.
- Immune rollback: remove `aios/maintenance/vulture_sanitation.py` and
  `tests/test_vulture_sanitation.py`; no security authority or mutable runtime
  state was changed.
- Ecosystem rollback: begin read-only. If a finding pipeline is noisy, disable
  the route/config flag and keep collected reports as audit evidence.
- Council memory rollback: remove the ganglia/council-memory adapters and tests;
  existing verdict logs and security approval paths remain authoritative without
  them.
- RepoMap rollback: keep symbol context advisory; worker scopes remain enforced
  by contracts and runtime checks.
- UI rollback: remove panels/status rows without changing backend decisions.

## Test Plan

Required baseline before implementation:
- `python tools/thesis_audit.py`
- `.venv\Scripts\python.exe -m pytest tests/test_thesis_audit.py -q`
- `.venv\Scripts\python.exe -m pytest -q` before any runtime phase is called
  complete.

Required targeted tests by feature:
- Constitution facade blocks frozen paths and cannot auto-run RED/YELLOW actions.
- Constitution enforcer delegates to existing gateway/router/budget/caste checks.
- Vulture detects cognitive-parasite lessons and creates quarantine proposals
  without deleting or mutating state automatically.
- Ecosystem scanner performs local-only dependency/API/git/config checks and
  redacts secrets.
- Pheromone-vulture or immune findings cannot override security decisions.
- Council memory records verdicts but cannot authorize future work by itself.
- Ganglia signal synthesis respects deterministic security veto.
- Symbol RepoMap does not activate trusted memory and cannot widen worker scope.
- UI/API status reflects actual backend state.

## Immediate Recommendation

Phase 0, Phase 1, Phase 2, Phase 3, and Phase 4 are complete locally. After
full-suite and CI verification, the next safe implementation scope is Phase 5:
Symbol RepoMap over Project Passport. Keep it local-only, proposal/evidence
only, and prove it cannot activate trusted memory or widen worker scope.
