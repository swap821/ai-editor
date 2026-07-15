# PRODUCTION CONVERGENCE LEDGER

**Directive:** GAGOS Sovereign Intelligence AI-OS V1.0 Master Convergence Directive  
**Baseline date:** 2026-07-12  
**Audited baseline SHA:** `5e73a3712f965b902c57afc180c34e165699b591`
**Ledger keeper:** operator + Codex (solo continuation; Claude / Kimi unavailable)

**Status vocabulary:** `VERIFIED` means the stated slice has evidence at its
declared boundary; `PARTIAL` means source or bounded tests exist but production
wiring/proof remains open; `DORMANT` means intentionally unreachable from the
production path; `BLOCKED` means a required authority or invariant is absent.

## Slice Status

> **Superseded:** On 2026-07-13 the operator issued `docs/architecture/MASTER_CONVERGENCE_DIRECTIVE.md`, which redefines the canonical 24-slice convergence roadmap. The work below is retained as historical evidence; future execution follows the new directive's numbering and acceptance gates.

| Slice | Name | Status | Evidence |
|-------|------|--------|----------|
| 0 | Truthful Baseline | **VERIFIED** | `docs/architecture/*.md`, green backend + frontend gates |
| 1 | Edge Security Hardening | **VERIFIED** | `aios/interfaces/http/edge_security.py`, refactored `aios/api/main.py`, `tests/test_edge_security.py` (24 passing), adversarial tests; backend 91.71% coverage, frontend gates green |
| 2 | Authority Centralization | **VERIFIED** | `aios/policy/kernel.py`, refactored `aios/api/main.py` + `aios/core/executor.py` + `aios/api/deps.py`, `tests/test_policy_kernel.py` (21 passing); backend 91.72% coverage; frontend build green |
| 3 | Execution Isolation | **VERIFIED** | `aios/policy/kernel.py` execution-policy methods, `aios/core/executor.py` kernel-routed runner selection, hardened `DockerRunner` (`bind-propagation=private`), `tests/test_policy_kernel.py` + `tests/test_executor.py`; backend 91.75% coverage, frontend build green |
| 4 | Runtime Profiles | **VERIFIED** | `aios/runtime/profiles.py` + `aios/runtime/data/profiles.json`, kernel profile authority + singleton, router/executor routed through kernel, `GET /api/v1/system/runtime-profile`, `tests/test_runtime_profiles.py`; backend 91.77% coverage, frontend build green |
| 5 | Action Envelope & Deterministic Policy Kernel | **VERIFIED** | `aios/domain/actions/envelope.py`, `aios/domain/policy/decision.py`, `aios/application/action_broker.py`, extended `aios/policy/kernel.py` with full route registry + `decide()`, `tests/test_action_*.py` + `tests/test_policy_kernel_decide.py` + `tests/test_route_registry_conformance.py`; backend 91.84% coverage, frontend build green |
| 6 | TurnCoordinator | **VERIFIED** | `aios/application/turns/turn_context.py` + `turn_result.py` + `turn_coordinator.py`, unified `/api/v1/chat` and `/api/generate` through canonical `TurnContext`/`turn_id`/`mode`, `tests/test_turn_coordinator.py` + extended `tests/test_chat.py`/`tests/test_generate_input_shield.py`/`tests/test_cortex_bus_w2.py`; backend 91.88% coverage, frontend build green |
| 7 | Living Interface | **VERIFIED** | `frontend/src/superbrain/lib/activeBrain.ts`, `frontend/src/workbench/GagosChrome.jsx` + `.css` + `.status.test.tsx`, `frontend/src/superbrain/components/ui/SuperbrainHUD.tsx`, `frontend/src/superbrain/components/canvas/IdentityReadout.tsx`; frontend tests + build green, CSS canon 4 pre-existing violations, texture canon OK, backend 91.87% coverage |
| 8 | Distribution & Bootstrap | **VERIFIED** | `aios/bootstrap.py`, `aios/__main__.py` bootstrap subcommand, `install.ps1`, `aios/api/routes/system.py` `GET /api/v1/system/bootstrap`, `tests/test_bootstrap.py`; backend 91.80%+ coverage, frontend build green, CSS/texture canon same as baseline, `install.ps1` syntax OK |

## New Directive Slice Inventory

| New Slice | Name | Status | Evidence / Note |
|-----------|------|--------|-----------------|
| 0 | Establish executable truth | **VERIFIED** | Baseline docs, subsystem registry, green gates |
| 1 | Repair edge trust boundary | **PARTIAL** | Strict peer/Host/Origin/CSRF/session rules and adversarial tests are green; production authority proof is unavailable and no independent reviewer verdict exists |
| 2 | Real Human Sovereign principal | **PARTIAL** | Durable single-operator enrollment, hashed generated credential/recovery material, durable device records, bounded login/strong-reauth authentication events, opaque sessions, rotation/revocation, and principal dependencies now cover privileged mutations; an isolated real `AIOS_PROFILE=production` HTTP process proved health, enrollment, login, strong re-authentication/session rotation, and authenticated session status on temporary data. Full packaged production authority proof remains open |
| 3 | Exact capabilities | **PARTIAL** | Server-issued SQLite capability authority now issues exact capabilities across generate, terminal, execute, both rollback routes, and Council rollback; payload/resource bindings, durable replay-chain cursors, verifier, atomic consume/revoke, and adversarial route/method tests are green. Production HTTP routes no longer import or consume the legacy store; dormant legacy units remain explicitly quarantined. An isolated real production-profile HTTP process proved exact issue, consume/reject, and one-time replay refusal; full production Compose lifecycle proof remains open. Full backend coverage gate passed with 3,087 tests collected, 3,082 passed, 5 skipped, and 89.37% coverage above the 85% floor |
| 4 | Runtime profiles | **VERIFIED** | `aios/runtime/profiles.py`, runtime-profile endpoint |
| 5 | ActionEnvelope & Policy Kernel | **VERIFIED** | `aios/domain/actions/`, `aios/application/action_broker.py`, route registry |
| 6 | Unify `/chat` and `/generate` under TurnCoordinator | **VERIFIED** | `aios/application/turns/turn_coordinator.py`, `conversation_pipeline.py`, and `generate_pipeline.py` own both production SSE pipelines behind the coordinator; focused handler/approval/conformance proof, full backend coverage, and an isolated real production-profile lifecycle/approval probe are green |
| 7 | MissionContract v1 and transactional mission state | **VERIFIED** | `aios/domain/missions/` v1 `MissionContract`/`MissionState`/`MissionTransition`/`MissionRepository`, `aios/infrastructure/missions/sqlite_mission_repository.py` authoritative SQLite store with WAL + transition audit, `aios/infrastructure/storage/migrations/0001_mission_state.py`, `aios/application/missions/mission_service.py` state machine + double-approve guard + legacy migration + export, `aios/council/council_orchestrator.py` integrated with `MissionService` (dual-write with JSON ledgers), `tests/test_mission_contract_v1.py` (12 passing), full backend + frontend gates green. |
| 8 | Converge the Queen Council | **VERIFIED** | `aios/council/participation.py` deterministic adaptive `CouncilParticipationPolicy` (required + optional Queens, full-Council only when justified), deterministic adapter Queens `RoutingQueen`/`ReflectionQueen`/`ProjectUnderstandingQueen`, `aios/runtime/contracts.py` extended `QueenVerdict`/`QueenEvidence`, `aios/council/queen_service.py` real service registry with `init_queen_services()` + all 8 Queen service classes, `aios/council/council_orchestrator.py` consumes participation policy, invokes optional Queens in deliberation, gates Critique by policy in execution, optionally routes reviews through `QUEEN_SERVICES` when `AIOS_QUEEN_SERVICES=true`, records Council cost/latency metrics; tests `tests/test_council_participation.py`, `tests/test_queen_services.py`, updated `tests/test_council_orchestrator.py`; full backend + frontend gates green. |
| 9 | Worker Foundry unification | **VERIFIED** | `8a62b59`; focused worker tests `18 passed`, full backend `2951 passed/4 skipped`, frontend typecheck/lint/tests/build green; scripted prover regression `7 passed` |
| 10 | Privacy Broker and model routing | **VERIFIED** | `64fd241`; focused privacy/router/provider tests `65 passed`, full backend `2956 passed/4 skipped`, frontend typecheck/lint/tests/build green; prover regression `8 passed` |
| 11 | Isolated Executor Service | **PARTIAL** | `4d12ac1`; source and focused tests exist, but production control-plane invocation and live isolation proof remain open |
| 12 | Staged workspaces / dormant worktree | **VERIFIED** | `2789ddd`; focused staged-workspace/worktree tests `8 passed/1 skipped`, full backend `2962 passed/5 skipped`, frontend typecheck/lint/tests/build green |
| 13 | Evidence and Verification Authorities | **VERIFIED** | `f567446`; focused evidence/verification tests `24 passed`, full backend `2965 passed/5 skipped/2 warnings`, frontend typecheck/lint/tests/build green |
| 14 | Atomic Promotion and Recovery | **VERIFIED** | R10 now wires production/demo Council promotion through PromotionAuthority; focused authority/evidence proof, production-profile staged-to-enrolled integration, rollback recovery checks, and the authoritative full backend gate are green |
| 15 | Durable Cortex consumer semantics | **VERIFIED** | `94ec847`; focused Cortex/stream tests `23 passed`, full backend `2975 passed/5 skipped/2 warnings`, frontend typecheck, lint `122 warnings/0 errors`, `588 tests`, and build green; CI run `29255612887` green across Ubuntu/Windows/macOS/frontend |
| 16 | Incremental system read models | **VERIFIED** | `7825654`; focused read-model/Cortex tests `26 passed`, full backend `2978 passed/5 skipped/1 warning`, frontend typecheck, lint `122 warnings/0 errors`, `588 tests`, and build green; CI run `29257186345` green across Ubuntu/Windows/macOS/frontend |
| 17 | One Memory Authority | **VERIFIED** | `93f8699`; focused memory/migration tests `68 passed/2 skipped`, full backend `2986 passed/5 skipped/1 warning`, frontend typecheck, lint `122 warnings/0 errors`, `588 tests`, and build green; CI run `29258754146` green across Ubuntu/Windows/macOS/frontend |
| 18 | Learning and earned autonomy loop | **VERIFIED** | `7299f05`; focused autonomy safety tests `61 passed`, full backend `2992 passed/5 skipped/1 warning`, frontend typecheck, lint `122 warnings/0 errors`, `588 tests`, and build green; CI run `29260138344` green across Ubuntu/Windows/macOS/frontend |
| 19 | Four product spaces (Living Mind, Workbench, Governance, History) | **VERIFIED** | `f3d8fe6`; focused product-space tests `4 passed`, full backend `2992 passed/5 skipped/1 warning`, frontend typecheck, lint `122 warnings/0 errors`, `592 tests`, and build green; CI run `29261640630` green across Ubuntu/Windows/macOS/frontend |
| 20 | Constitutionally truthful Living Mirror | **VERIFIED** | `361f11e`; focused mirror tests frontend `5 passed` plus backend `10 passed`, full backend `2992 passed/5 skipped/1 warning`, frontend typecheck, lint `122 warnings/0 errors`, `597 tests`, and build green; CI run `29263138253` green across Ubuntu/Windows/macOS/frontend |
| 21 | Operations, observability and recovery | **VERIFIED** | `1b2553a`; focused operations/read-model/Cortex tests `12 passed`, full backend `2996 passed/5 skipped/1 warning`, frontend typecheck, lint `122 warnings/0 errors`, `597 tests`, and build green; Compose config passes with explicit secret and refuses missing secret; CI run `29264970507` green across Ubuntu/Windows/macOS/frontend |
| 22 | CI as production release authority | **VERIFIED** | `dccf072`; focused release checks `11 passed`, security scan clean, SBOM `449 components`, full backend `3007 passed/5 skipped/1 warning`, frontend typecheck, lint `122 warnings/0 errors`, `597 tests`, and build green; warning budget `122/124`; CI run `29268027117` green across all platform, frontend, and release-authority jobs |
| 23 | Package the single-developer product | **VERIFIED** | `9ca0534`; launcher/release checks `21 passed`, full backend `3019 passed/5 skipped/2 warnings`, frontend typecheck/lint/coverage/build green; CI run `29271483280` green across all platform, frontend, and release-authority jobs |
| 24 | Controlled autonomy and v1.0 declaration | **PARTIAL** | `796bbeb`; source, CI and focused checks exist, but Human Sovereign identity, exact capabilities, EmergencyStopController production wiring, and strict runtime proof remain blocked |

## Ordered GAGOS V1 Final Repair Waves

| Wave | Name | Status | Current evidence |
|------|------|--------|------------------|
| R0 | Executable truth reset | **VERIFIED** | Baseline pinned to `5e73a3712f965b902c57afc180c34e165699b591`; release claims reconciled to source/runtime evidence |
| R1 | Edge trust boundary | **PARTIAL** | Origin/Host/CSRF/session hardening and adversarial tests are green; independent production authority proof remains open |
| R2 | Human Sovereign identity | **PARTIAL** | Durable identity/device/session authority and isolated real-process HTTP proof exist; packaged production authority matrix remains open |
| R3 | Exact capabilities | **PARTIAL** | Durable exact issue/consume/replay/revocation semantics and isolated real-process proof are green; full packaged runtime proof remains open |
| R4 | Universal ActionEnvelope → PolicyKernel → ActionBroker boundary | **VERIFIED** | `aios/api/action_guard.py` is attached to all ordinary mutating routers/main routes; exact streaming/approval/rollback routes retain bespoke broker entry; route conformance, adversarial guard tests, full backend `89.25%` coverage gate, frontend typecheck/lint/tests/build, and texture canon pass |
| R5 | TurnCoordinator application spine | **VERIFIED** | Named production handlers and application-owned `/api/v1/chat` + `/api/generate` pipelines are live; explicit mission/governance mode fields, preparation/approval-resume handling, and lifecycle-start/terminal mapping are green. Focused handler/chat/generate/approval/conformance proof is `49 passed`; plan-stage, telemetry, and Council origination are `7`, `5`, and `8 passed`; the latest full backend coverage gate exits `0` at `89.28%` with `3,094` tests collected and five expected skips. A real isolated production-profile process proved identity/session rotation, chat success/failure, generate lifecycle, two exact approval pauses/resumes, no-write-before-approval, final verification, and durable Cortex lifecycle sequences; targeted files were removed after the probe |
| R6 | Human Sovereign mission approval authority | **VERIFIED** | SQLite mission repository is authoritative for approval/rejection; serialized transitions bind the real principal, consumed capability digest, authentication event, session, contract digest, and runtime contract digest, while JSON decisions/reports are written only after the authoritative transition. Focused mission/council proof is `36 passed`, broader council/action/release regression is `102 passed`, and the real Council-originated worker path succeeds. Race, rejection-terminality, restart durability, altered-contract, synthetic-actor, and duplicate-execution defenses are green. Cross-store capability-consume/mission-transition atomicity remains a bounded follow-up risk |
| R7 | WorkerFoundry convergence | **VERIFIED** | Default production selection exposes only deterministic; tool-loop/role-pass/swarm/research/code/test/inspection adapters require explicit injection instead of advertising handler-less `StrategyUnavailable` paths. Direct generation `rolePass`/`swarm` requests fail closed as experimental until Foundry owns their lifecycle. Worker lifecycle events use canonical `worker.requested`, `worker.admitted`, `worker.started`, `worker.awaiting_capability`, `worker.completed`, `worker.failed`, `worker.killed`, and `worker.dissolved` vocabulary with principal/mission/contract/tools/scope/budget/classification/executor-policy context. Focused WorkerFoundry/projection/runtime proof is `39 passed`; Council/API/runtime regression is `35 + 174 passed`; full backend gate is `3,096 passed, 5 skipped` at `89.22%` coverage |
| R8 | Private Executor Service mandatory boundary | **VERIFIED** | `StructuredExecutorClient` authenticates `/v1/jobs`, validates job identity/isolation proof, and refuses timeout/unavailable/malformed responses; production/demo runner selection is private-service-only, worker defaults fail closed, and Compose/CI encode control-plane-without-Docker-socket topology. Focused gate is `119 passed, 3 skipped`; a live source-bearing no-socket control-plane probe reached the private service and disposable worker, proving UID 65534, no network, staged-workspace confinement, bounded/truncated output, timeout refusal, and missing-service refusal. The host-visible workspace mapping fixes Docker Desktop socket semantics. Overall v1 remains partial |
| R9 | Staged workspaces mandatory boundary | **VERIFIED** | `StagedWorkspaceManager` now owns collision-safe mission leases, durable markers, symlink/path/enrollment checks, deterministic baselines/diffs, and bounded cleanup. Production/demo Council wiring stages the project before WorkerFoundry admits a mutable worker; the worker receives only the staged root, terminal success cleans it, and failed verification retains it for evidence. Focused R9 gate is `59 passed, 1 skipped`; the authoritative full backend gate exits `0` at `88.99%` coverage. Promotion, evidence, memory, mirror, and emergency waves remain open |
| R10 | Evidence, verification, promotion and rollback | **VERIFIED** | `EvidenceBundle` binds mission/worker/contract/workspace/diff/executor/environment/commands/output digests/strength/targets/timestamps; VerificationAuthority rejects weak, stale, partial, or mismatched evidence; production/demo Council routes staged worker results through PromotionAuthority, checkpoint, exact apply, post-promotion exact-copy smoke, completion, or rollback. Focused R10 gate is `66 passed, 1 skipped`; authoritative full backend gate exits `0` with all tests passing at `88.94%` coverage |
| R11 | One Memory Authority | **PARTIAL** | MemoryAuthority now maps recall status to truthful event trust, the memory route uses canonical Cortex phases and no longer emits unverified recall as verified, episodic turn writes/session restore cross authority adapters, semantic chat indexing crosses the authority seam, production fact/skill/lesson/development-history/self-model recall routes through specialized adapters, and production fact/development/skill/lesson/reflection/consolidation/planner/compaction paths now dispatch through authority adapters. Council lesson recall and mission-scoped append-only deliberation evidence also route through scoped adapters. The consolidator's contradiction reconciliation, supersession, and bulk status reads, plus default-chat confidence calibration and reflection lesson reads, now dispatch through MemoryAuthority. Advisory pheromone query/deposit/reinforcement/decay, Council context, hibernation preview, and system onboarding episodic counts now use authority-owned adapters; process-wide working/semantic compactor facades, Cortex self-model production wiring, consolidation and semantic-indexer dependencies, development metrics/skills/trails reads, system metrics reads, and mirror snapshot development/skill reads are authority-owned too. Specialist dependency providers now return canonical facts/development/skills/lessons stores while explicit injected fakes remain supported. Planner, ReflectionAgent, and the authority bootstrap's consolidator now reuse registered specialist stores; only explicit standalone/injected-fake paths construct legacy stores. A CI architecture guard freezes the remaining documented legacy-construction seams. The focused planner/reflection/authority regression is `89 passed` before the follow-on ownership regressions; the package-wide gate exits `0` with `3,159` collected, `3,151 passed, 8 skipped`, `91.04%` line coverage (`21,129/23,209`), and `80.57%` branch coverage (`5,016/6,226`), combined `88.82%`. Packaged runtime proof stays open |

## Current authority readiness at the audited baseline

The slice evidence above records what was tested or shipped; it does not by
itself prove production authority. The release evaluator exposes the same
two-layer distinction as `source_present` and `runtime_proven`.

| Authority boundary | Status | Current truth |
|---------------------|--------|---------------|
| Human Sovereign identity | **PARTIAL** | Durable operator/device/authentication-event/session authority and privileged route wiring exist; isolated real production-profile HTTP proof passed on temporary data, but the full packaged production authority matrix remains open |
| Exact capabilities | **PARTIAL** | `CapabilityAuthority` persists token digests plus server-owned exact action payload metadata and binds operator/device/auth-event/session/action/route/method/payload/resource/mission/contract/policy/scope/verification metadata; all production approval routes issue exact capabilities, and the legacy store is no longer in the production dependency graph. Isolated real HTTP proof passed exact issue/consume/replay behavior; full production Compose lifecycle and complete R14 proof matrix remain open |
| TurnCoordinator | **VERIFIED** | Both production routes delegate pipeline ownership to application handlers; local gates and real production chat/generate lifecycle, two exact approval pauses/resumes, no-write-before-approval, final verification, and canonical Cortex-bus evidence are green in an isolated real process |
| Isolated Executor Service | **PARTIAL** | Private client, production wiring, disposable-worker handling, and Compose/CI topology exist; control-plane-to-private-service isolation is not runtime-proven because the local Compose build was blocked by a Docker Hub `python:3.12-slim` layer-transfer EOF |
| PromotionAuthority | **PARTIAL** | Bounded R10 production/demo Council integration now sends only staged, evidence-bound diffs through PromotionAuthority; durable lease/baseline checks, checkpoint creation, exact apply, post-promotion smoke, rollback recovery, and terminal evidence recording are proven. The complete packaged R14 runtime-proof matrix remains open |
| EmergencyStopController | **PARTIAL** | Source exists; all real side-effect boundaries are not runtime-proven |
| Other source-only gates | **PARTIAL** | Source evidence is retained as advisory until a real runtime proof is recorded |

## Latest CI Repair Checkpoint — 2026-07-15

Commit `65d403b2707135f1f7d9dd30145591646ca7ca0c` is synchronized with
`origin/master`. Its cross-platform path/timeout repair passed CodeQL,
dependency audit, frontend, and all Ubuntu/macOS/Windows backend jobs in run
`29435327884`; its follow-on permission repair passed all backend matrix,
frontend, aggregate, and release-authority jobs in run `29436664457`, while
CodeQL run `29436664480` also passed. The workflow keeps only the lightweight
private executor resident, prepares the UID `65534` shared workspace, runs the
control-plane integration test in a one-shot Compose container, waits for
executor health, prints diagnostics, and supplies the required workspace-root
variable to teardown. Focused local release/integration tests pass `14 passed,
3 skipped`; the packaged isolation gate is now runtime-proven at its declared
CI boundary, while overall R11 and v1 readiness remain **PARTIAL**.

## New Directive Roadmap (post-save)

- Remaining roadmap follows `docs/architecture/MASTER_CONVERGENCE_DIRECTIVE.md`.
- R0 executable-truth reset and R1 edge-trust repair are complete in this
  checkout and self-verified by Codex; neither has an independent reviewer
  verdict.
- R2 identity foundation, strong re-authentication, caller-provenance removal,
  and privileged route migration are implemented and self-verified. The
  production runtime-proof layer remains open; isolated identity/capability HTTP
  proof now exists, but strict release status is not upgraded to ready by a
  partial probe.
- R3 exact-capability core and production issuance paths are implemented and
  self-verified: `CapabilityBinding`, canonical payload/resource digests,
  durable `CapabilityAuthority`, server-owned replay payloads, durable
  same-session grant cursors, `CapabilityVerifier`, atomic single-use/revocation
  semantics, and ActionBroker complete payload/route/method comparison are green.
  Generate, terminal, execute, rollback, and Council rollback now issue exact
  capabilities; the legacy ApprovalStore remains only as an explicit
  compatibility adapter outside the production dependency graph.
- R4 is verified in the current tree: ActionEnvelope carries the complete
  immutable binding; the method-aware PolicyKernel fails closed on unknown
  route/action/version metadata; and `aios/api/action_guard.py` submits every
  ordinary mutation to the production ActionBroker before handler dispatch.
  GREEN conversation/session routes preserve their local session contract,
  YELLOW routes challenge with exact capabilities, and RED routes stop before
  side effects. The exact streaming/approval/rollback family remains on its
  bespoke broker flow. Full R14 runtime proof and strict readiness remain open.
- R5 application extraction and its declared runtime proof are complete in the
  current tree: both production turn routes call registered `TurnCoordinator`
  handlers, `/api/v1/chat` and `/api/generate` own their pipelines in
  application modules, generation preparation/capability/approval-resume
  handling is behind the boundary, and lifecycle frames map to canonical
  events. The isolated proof covered two approval pauses/resumes,
  no-write-before-approval, final verification, and Cortex delivery.
- Strict release remains blocked by missing durable identity/capabilities and
  unproven production authority; source presence and green tests do not change
  that status.

## Baseline Evidence

### Backend
- Command: `.venv\Scripts\python -m pytest -q --cov=aios --cov-report=term-missing --cov-report=xml --cov-fail-under=85`
- Result: passing, backend coverage 91.80%+
- Log: `coverage.xml`

### Frontend
- Build: passing (`npm run build`)
- CSS canon: 5 pre-existing violations in untouched `GagosChrome.css`, `ProductSpaces.css`, and `TrustHalo.css`; out of scope for this R3 authority wave
- Texture canon: OK (`tools/check_canon_frozen.py`)

### Installer
- Script: `install.ps1`
- Syntax check: passed (`[System.Management.Automation.PSParser]::Tokenize`)

## Authority & Ownership

- Policy Kernel is the future single authority (Slice 2).
- Frozen core: `aios/security/` modules — RED changes only via §VIII.
- Operator owns all data; egress is opt-in.

## Next Action

R11 is partial: recall trust semantics are corrected, episodic route/turn
access and semantic chat indexing now cross MemoryAuthority adapters, production
fact/skill/lesson/development-history/self-model recall uses the authority, and
production writes/planner/compaction plus Council lesson/deliberation paths use
scoped adapters. Contradiction reconciliation, supersession, consolidator
bulk status reads, default-chat calibration reads, reflection lesson reads,
advisory pheromone operations, hibernation preview, and system onboarding
episodic counts now use the authority in production, with explicit tests that
fail if those paths call the legacy stores directly. Process-wide
working/semantic compactor facades, Cortex self-model production wiring,
consolidation and semantic-indexer dependencies, and development
metrics/skills/trails reads also use the authority. The current documented
compatibility construction seams are frozen by an architecture guard. Planner,
ReflectionAgent, and the authority bootstrap's consolidator reuse registered
specialist stores; direct construction remains only in explicit standalone or
injected-fake compatibility paths. The latest authoritative backend gate is
`3,161` collected, `3,153 passed, 8 skipped`, exit `0`, at `91.04%` line
coverage (`21,145/23,225`) and `80.58%` branch coverage (`5,022/6,232`),
combined `88.83%`. Checkpoint `9cff773` passed CodeQL, the dependency audit,
frontend, and Windows backend jobs, while Ubuntu/macOS exposed the existing
explicit Windows daemon-path test after the POSIX host-platform gate was
tightened. The runner resolves POSIX paths at the mount boundary, preserves
integral timeout values while retaining fractional precision, and now accepts
explicit drive/UNC Windows paths without reclassifying ordinary POSIX roots.
The
bounded
packaged runtime probe now proves the authenticated
MemoryAuthority/generate entry boundary with exact Origin, session-bound CSRF,
and strong re-authentication; it returned `200 text/event-stream` and reached
`human_required` without writing a file. Continue R11 by keeping this runtime
evidence separate from the still-open full production matrix. The old
daily-use probe remains incompatible and receives the expected `403`. Leave Human Sovereign,
exact-capability, mirror, and emergency-stop runtime authority gates open. Do
not infer overall production readiness from completed waves.
