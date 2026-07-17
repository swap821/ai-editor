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
| 11 | Isolated Executor Service | **VERIFIED** | `4d12ac1` plus R14; hosted release-authority proved the live private service, UID 65534, no network, and workspace confinement |
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
| 24 | Controlled autonomy and v1.0 declaration | **PARTIAL** | `796bbeb` plus R14 hosted proof; strict declaration emitted `ready=true` and all runtime proofs passed, but final non-builder/operator handoff is still pending |

## Ordered GAGOS V1 Final Repair Waves

| Wave | Name | Status | Current evidence |
|------|------|--------|------------------|
| R0 | Executable truth reset | **VERIFIED** | Baseline pinned to `5e73a3712f965b902c57afc180c34e165699b591`; release claims reconciled to source/runtime evidence |
| R1 | Edge trust boundary | **VERIFIED** | R14 hosted runtime matrix rejected spoofed origin/host/wildcard credentialed CORS before mutation; source and adversarial gates remain green |
| R2 | Human Sovereign identity | **VERIFIED** | R14 hosted runtime matrix proved temporary enrollment, authentication, privileged reauthentication, and session rotation; prior HTTP route proof remains green |
| R3 | Exact capabilities | **VERIFIED** | R14 hosted runtime matrix proved exact issue/consume, replay refusal, and altered-payload refusal; production issuance paths remain exact-capability-bound |
| R4 | Universal ActionEnvelope → PolicyKernel → ActionBroker boundary | **VERIFIED** | `aios/api/action_guard.py` is attached to all ordinary mutating routers/main routes; exact streaming/approval/rollback routes retain bespoke broker entry; route conformance, adversarial guard tests, full backend `89.25%` coverage gate, frontend typecheck/lint/tests/build, and texture canon pass |
| R5 | TurnCoordinator application spine | **VERIFIED** | Named production handlers and application-owned `/api/v1/chat` + `/api/generate` pipelines are live; explicit mission/governance mode fields, preparation/approval-resume handling, and lifecycle-start/terminal mapping are green. Focused handler/chat/generate/approval/conformance proof is `49 passed`; plan-stage, telemetry, and Council origination are `7`, `5`, and `8 passed`; the latest full backend coverage gate exits `0` at `89.28%` with `3,094` tests collected and five expected skips. A real isolated production-profile process proved identity/session rotation, chat success/failure, generate lifecycle, two exact approval pauses/resumes, no-write-before-approval, final verification, and durable Cortex lifecycle sequences; targeted files were removed after the probe |
| R6 | Human Sovereign mission approval authority | **VERIFIED** | SQLite mission repository is authoritative for approval/rejection; serialized transitions bind the real principal, consumed capability digest, authentication event, session, contract digest, and runtime contract digest, while JSON decisions/reports are written only after the authoritative transition. Focused mission/council proof is `36 passed`, broader council/action/release regression is `102 passed`, and the real Council-originated worker path succeeds. Race, rejection-terminality, restart durability, altered-contract, synthetic-actor, and duplicate-execution defenses are green. Cross-store capability-consume/mission-transition atomicity remains a bounded follow-up risk |
| R7 | WorkerFoundry convergence | **VERIFIED** | Default production selection exposes only deterministic; tool-loop/role-pass/swarm/research/code/test/inspection adapters require explicit injection instead of advertising handler-less `StrategyUnavailable` paths. Direct generation `rolePass`/`swarm` requests fail closed as experimental until Foundry owns their lifecycle. Worker lifecycle events use canonical `worker.requested`, `worker.admitted`, `worker.started`, `worker.awaiting_capability`, `worker.completed`, `worker.failed`, `worker.killed`, and `worker.dissolved` vocabulary with principal/mission/contract/tools/scope/budget/classification/executor-policy context. Focused WorkerFoundry/projection/runtime proof is `39 passed`; Council/API/runtime regression is `35 + 174 passed`; full backend gate is `3,096 passed, 5 skipped` at `89.22%` coverage |
| R8 | Private Executor Service mandatory boundary | **VERIFIED** | `StructuredExecutorClient` authenticates `/v1/jobs`, validates job identity/isolation proof, and refuses timeout/unavailable/malformed responses; production/demo runner selection is private-service-only, worker defaults fail closed, and Compose/CI encode control-plane-without-Docker-socket topology. Focused gate is `119 passed, 3 skipped`; a live source-bearing no-socket control-plane probe reached the private service and disposable worker, proving UID 65534, no network, staged-workspace confinement, bounded/truncated output, timeout refusal, and missing-service refusal. The host-visible workspace mapping fixes Docker Desktop socket semantics. Overall v1 remains partial |
| R9 | Staged workspaces mandatory boundary | **VERIFIED** | `StagedWorkspaceManager` now owns collision-safe mission leases, durable markers, symlink/path/enrollment checks, deterministic baselines/diffs, and bounded cleanup. Production/demo Council wiring stages the project before WorkerFoundry admits a mutable worker; the worker receives only the staged root, terminal success cleans it, and failed verification retains it for evidence. Focused R9 gate is `59 passed, 1 skipped`; the authoritative full backend gate exits `0` at `88.99%` coverage. Promotion, evidence, memory, mirror, and emergency waves remain open |
| R10 | Evidence, verification, promotion and rollback | **VERIFIED** | `EvidenceBundle` binds mission/worker/contract/workspace/diff/executor/environment/commands/output digests/strength/targets/timestamps; VerificationAuthority rejects weak, stale, partial, or mismatched evidence; production/demo Council routes staged worker results through PromotionAuthority, checkpoint, exact apply, post-promotion exact-copy smoke, completion, or rollback. Focused R10 gate is `66 passed, 1 skipped`; authoritative full backend gate exits `0` with all tests passing at `88.94%` coverage |
| R11 | One Memory Authority | **PARTIAL** | MemoryAuthority now maps recall status to truthful event trust, the memory route uses canonical Cortex phases and no longer emits unverified recall as verified, episodic turn writes/session restore cross authority adapters, semantic chat indexing crosses the authority seam, production fact/skill/lesson/development-history/self-model recall routes through specialized adapters, and production fact/development/skill/lesson/reflection/consolidation/planner/compaction paths now dispatch through authority adapters. The latest turn-path slice also makes semantic recall, episodic persistence, and `/api/v1/chat` coordinator wiring use the injected MemoryAuthority rather than silently consulting the process-global fallback. Council lesson recall and mission-scoped append-only deliberation evidence also route through scoped adapters. The consolidator's contradiction reconciliation, supersession, and bulk status reads, plus default-chat confidence calibration and reflection lesson reads, now dispatch through MemoryAuthority. Advisory pheromone query/deposit/reinforcement/decay, Council context, hibernation preview, and system onboarding episodic counts now use authority-owned adapters; process-wide working/semantic compactor facades, Cortex self-model production wiring, consolidation and semantic-indexer dependencies, development metrics/skills/trails reads, system metrics reads, and mirror snapshot development/skill reads are authority-owned too. Specialist dependency providers now return canonical facts/development/skills/lessons stores while explicit injected fakes remain supported. Planner, ReflectionAgent, and the authority bootstrap's consolidator now reuse registered specialist stores; only explicit standalone/injected-fake paths construct legacy stores. CouncilOrchestrator no longer constructs an implicit PheromoneStore when pheromones are enabled without MemoryAuthority; the architecture quarantine manifest shrank accordingly. A CI architecture guard freezes the remaining documented legacy-construction seams. The focused Council/R11 regression is `66 passed`; the package-wide gate exits `0` with `3,161` collected, `3,153 passed, 8 skipped`, combined coverage `88.84%`, and frontend tests/build green. Packaged runtime proof stays open |

**R11 Council recall checkpoint — 2026-07-16:** `MistakeBackedRetriever` now
requires either `MemoryAuthority` or an explicit injected mistake store; it no
longer constructs an implicit legacy store. The focused Council/R11 gate is
`80 passed`; the latest local backend gate is `3,161` collected, `3,153 passed,
8 skipped`, with `88.85%` combined coverage. Exact remote CI/CodeQL for this
new wave remains to be verified after push.

**R11 Planner authority checkpoint — 2026-07-16:** `Planner` now refuses all
implicit specialist-store construction without `MemoryAuthority` or an
explicit injected store. `ToolAgent` and both application turn-agent factories
carry explicit planner stores, and the offline sovereignty proof injects its
existing skill store. The focused Planner/native/offline/architecture gate is
`40 passed`; the affected ToolAgent/native-plan/proof checks are `6 passed`.
The clean local backend gate is `3,166` collected, `3,158 passed, 8 skipped`,
`88.85%` combined coverage; frontend is `598 passed` across `104` files and
the Vite build is green. Exact remote CI/CodeQL remains to be verified after
push.

**R11 Reflection authority checkpoint — 2026-07-16:** `ReflectionAgent` now
refuses implicit `MistakeMemory(db_path)` construction without
`MemoryAuthority` or an explicit lesson store; `get_reflection_agent` also
fails closed when the authority is unavailable. The focused
Reflection/offline/API/architecture gate is `36 passed`; the clean local
backend gate is `3,168` collected, `3,160 passed, 8 skipped`, `88.86%`
combined coverage, with the existing frontend gate green. Exact remote
CI/CodeQL remains to be verified after push.

**R11 Planner CI checkpoint — 2026-07-16:** Repair commit
`a163ba00af793c236efc052985160468e37b6165` is synchronized with
`origin/master`; exact-tip CI run `29496704967` and CodeQL run `29496705025`
completed successfully across frontend, Ubuntu/macOS/Windows backend,
aggregate, release-authority, and CodeQL jobs.

## Current authority readiness at the audited baseline

The slice evidence above records what was tested or shipped; it does not by
itself prove production authority. The release evaluator exposes the same
two-layer distinction as `source_present` and `runtime_proven`.

| Authority boundary | Status | Current truth |
|---------------------|--------|---------------|
| Human Sovereign identity | **VERIFIED** | Durable operator/device/authentication-event/session authority and privileged route wiring exist; R14 hosted strict proof passed temporary enrollment, authentication, privileged reauthentication, and session rotation |
| Exact capabilities | **VERIFIED** | `CapabilityAuthority` persists token digests plus server-owned exact action payload metadata and binds operator/device/auth-event/session/action/route/method/payload/resource/mission/contract/policy/scope/verification metadata; R14 hosted strict proof passed exact issue/consume/replay/alteration behavior |
| TurnCoordinator | **VERIFIED** | Both production routes delegate pipeline ownership to application handlers; local gates and real production chat/generate lifecycle, two exact approval pauses/resumes, no-write-before-approval, final verification, and canonical Cortex-bus evidence are green in an isolated real process |
| Isolated Executor Service | **VERIFIED** | Private client, production wiring, disposable-worker handling, and Compose/CI topology exist; hosted R14 strict proof passed UID 65534, no network, and no workspace escape |
| PromotionAuthority | **VERIFIED** | Bounded R10 production/demo Council integration sends only staged, evidence-bound diffs through PromotionAuthority; hosted R14 strict proof passed staging, strong verification, promotion, post-check, and rollback recovery |
| EmergencyStopController | **VERIFIED** | Hosted R14 strict proof engaged the durable latch, blocked capability/mission/execution boundaries across restart, and cleared only with fresh privileged authority |
| Other runtime gates | **VERIFIED** | Hosted R14 strict proof passed edge, mutation, mission, TurnCoordinator, Cortex cursor, truthful mirror, memory provenance, and production fail-closed checks |

## Latest CI Repair Checkpoint — 2026-07-16

Commit `e4a918adc39909cc395ef35b66946b324592afd0` is synchronized with
`origin/master`. Exact-tip CI run `29485413218` and CodeQL run `29485413276`
are green across the backend matrix, frontend, aggregate, release-authority,
and CodeQL jobs. The previous checkpoint already proved
the lightweight private executor release boundary with the UID `65534` shared
workspace and one-shot control-plane integration container. Overall R11 and v1
readiness remain **PARTIAL**.

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
injected-fake compatibility paths. The latest turn-path slice also makes
semantic recall, episodic persistence, and `/api/v1/chat` coordinator wiring
use the injected MemoryAuthority rather than silently consulting the process
 global. Council pheromone context now fails closed when advisory pheromones
 are enabled without MemoryAuthority; explicit injected stores remain bounded
 compatibility inputs. The latest authoritative backend gate is `3,161` collected,
`3,153 passed, 8 skipped`, exit `0`, with `88.84%` combined coverage; frontend
tests/build are green. Repair tip `6dd7a8f9f47aa4d50a294a20235d8ad2ea2a9652`
is synchronized with `origin/master`; exact-tip CI run `29488676684` and
CodeQL run `29488676662` are green across the platform matrix, frontend,
aggregate, release-authority, and CodeQL jobs. The prior checkpoint `e4a918a`
was also exact-tip green; the
previous checkpoint passed CodeQL, the dependency audit,
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

**R11 Specialist provider CI checkpoint — 2026-07-16:** Exact pushed repair
tip `5f886084d04a0d708080218b7c17a6725d62747d` passed CI run `29504715690`
and CodeQL run `29504715702`; all required platform, frontend, aggregate,
release-authority, and analysis jobs completed successfully. The local gate
is `3,169` collected, `3,161 passed, 8 skipped`, exit `0`, with `88.86%`
combined coverage; the affected API/dependency regression set is `206 passed`.
R11 remains partial. Continue at the next ordered compatibility seam, starting
with the Council route/adapter boundary, while keeping runtime authority proof
separate from source-level green evidence.

**R12 Mirror replay-recovery local checkpoint — 2026-07-16:** The mirror
stream no longer silently swallows replay failures. `ConsumerReplayGap` and
other replay exceptions are logged and surfaced as a `snapshot_required` SSE
event; gap metadata includes the cursor and earliest retained event. The
red-first replay-gap test failed before repair. Focused mirror/Cortex tests
passed (`13`), the adjacent event/projection/API gate passed (`203`), the
projection/Cortex bus gate passed (`38`), and the clean package gate passed
with `3,173` collected, `3,165 passed, 8 skipped`, exit `0`, and `88.86%`
coverage. R12 remains partial; canonical event unification and frontend mirror
truth remain open.

**R12 Mirror replay-recovery CI checkpoint — 2026-07-16:** Exact pushed repair
tip `e49dbe4004ff3aa32966b1c2231e59170496daf0` passed CI run `29521716118`
across Ubuntu, macOS, Windows, frontend, aggregate, and release-authority
jobs. CodeQL run `29521716110` passed all analysis jobs. The local package gate
is `3,173` collected, `3,165 passed, 8 skipped`, with `88.86%` coverage. R12
remains partial; canonical event unification and frontend mirror truth remain
open.

**R11 Reflection CI checkpoint — 2026-07-16:** Exact pushed repair tip
`12e691b8e0c4054d86233b403a584feacf3b245e` passed CI run `29500130518` and
CodeQL run `29500130475`; all required platform, frontend, aggregate,
release-authority, and analysis jobs completed successfully. The local gate
remains `3,168` collected, `3,160 passed, 8 skipped`, with `88.86%` combined
coverage. R11 remains partial; continue at the next ordered compatibility
seam, starting with `aios/api/deps.py`, and keep packaged runtime authority
proofs separate from source-level green evidence.

**R11 Consolidator CI checkpoint — 2026-07-16:** Exact pushed repair tip
`1a497a022c584cbb9a1b54f697aac02295b38d48` passed CI run `29508215933` and
CodeQL run `29508216169`; all required platform, frontend, aggregate,
release-authority, and analysis jobs completed successfully. The local gate
is `3,170` collected, `3,162 passed, 8 skipped`, exit `0`, with `88.85%`
combined coverage. The architecture manifest now records three remaining R11
construction seams: `aios/api/deps.py`, `aios/api/routes/council.py`, and
`aios/application/memory/adapters.py`. R11 remains partial; continue with a
red-first audit and keep packaged runtime authority proof separate from
source-level green evidence.

**R11 Semantic adapter local checkpoint — 2026-07-16:** The next repair wave
requires `LegacySemanticMemoryAdapter` to wrap an explicit `SemanticMemory`
store; only the MemoryAuthority composition root now creates that physical
semantic store. The red-first refusal test, architecture gate, and affected
authority/API/approval regression set passed (`205 passed`). The clean package
gate completed with `3,171` collected, `3,163 passed, 8 skipped`, and `88.85%`
coverage. A prior full-suite Windows run exposed one stateful rollback `403`
instead of `200`; the exact test passed in isolation, and the final clean run
completed without a failure marker. Remote verification is pending for the
source wave; R11 remains partial.

**R11 Semantic adapter CI checkpoint — 2026-07-16:** Exact pushed repair tip
`11d1d4a852e452509271b0efd62f6e50e4733314` passed CI run `29512847189` and
CodeQL run `29512847479`; all required platform, frontend, aggregate,
release-authority, and analysis jobs completed successfully. The local gate
is `3,171` collected, `3,163 passed, 8 skipped`, with `88.85%` combined
coverage; the affected authority/API/approval regression set is `205 passed`.
The architecture manifest now records two remaining R11 construction seams:
`aios/api/deps.py` and `aios/api/routes/council.py`. R11 remains partial; keep
packaged runtime authority proof separate from source-level green evidence.

**R11 Semantic adapter docs-tip CI checkpoint — 2026-07-16:** The continuity
tip `864352afb2429d6aa5a0c88f0ba951859a83e209` passed CI run `29513971752`
and CodeQL run `29513969945` after the Windows job was rerun. The first
Windows attempt timed out in the sabotage proof; the first retry failed a
different stateful Council 403; the second retry passed. All required jobs are
green and the source wave remains unchanged. R11 remains partial.

**R11 Council authority-boundary local checkpoint — 2026-07-16:** The
orchestrator now refuses an authority-backed `CouncilMemory` unless the
authority's scoped `council` adapter owns that exact mission-local store. The
red-first unbound-authority test failed before repair; explicit
`CouncilMemory`-only compatibility callers remain supported. The focused
Council suite passed (`18`), the broader Council/authority/API regression set
passed (`231`), and the clean package gate passed with `3,172` collected,
`3,164 passed, 8 skipped`, exit `0`, and `88.86%` coverage. The two documented
composition-root seams in `aios/api/deps.py` and `aios/api/routes/council.py`
remain for the next audit; R11 remains partial.

**R11 Council authority-boundary CI checkpoint — 2026-07-16:** Exact pushed
repair tip `e3bb5a8dad68e8780408be83391e759a6cf3b087` passed CI run
`29518614467` across Ubuntu, macOS, Windows, frontend, aggregate, and
release-authority jobs. CodeQL run `29518614365` also passed all analysis jobs.
The local package gate is `3,172` collected, `3,164 passed, 8 skipped`, with
`88.86%` coverage. R11 remains partial; keep packaged runtime authority proof
separate from source-level green evidence.

**R12 Canonical Cortex event-schema local checkpoint — 2026-07-17:** The
red-first append contract failed because `CortexBus.append` still accepted the
legacy `(event_type, signature, payload)` triple. The bus now requires a
`CanonicalEvent`, derives its per-entity signature from canonical identity
fields, and persists the complete canonical envelope. All production producer
call sites and affected test doubles use the single schema. The focused R12
event/mirror gate and compatibility gates passed; the exact package gate passed
with `3,174` collected, `3,166 passed, 8 skipped`, exit `0`, and `88.85%`
combined coverage. R12 remains partial; hosted CI and CodeQL are pending for
the source tip.

**R12 hosted verification finding — 2026-07-17:** Exact source tip
`ad8c89a17bb0207957e65701aa153e43cd675d29` passed CodeQL
`29527777727`, all backend matrix jobs, frontend, aggregate, and platform
checks in CI `29527777325`. The release-authority job failed only at its Ruff
format gate because `tests/test_operations.py` would be reformatted. The
format-only follow-up tip `06581df71f6682874ea803eeb5a29579d8756a8c` passed
CodeQL `29528718788`, all ordinary CI jobs, and the Ruff gate, but its private
Executor isolation proof failed when the Docker build exhausted runner disk
space installing the heavyweight image. Rerun the failed job before changing
source.

**R12 hosted verification complete — 2026-07-17:** The exact current tip
`06581df71f6682874ea803eeb5a29579d8756a8c` is green in CI
`29528718805` after release-authority rerun job `87726348325`, including the
private Executor isolation proof. CodeQL `29528718788` is also green. The
first release-authority attempt failed only from runner disk exhaustion while
building the heavyweight test image; no source change was required.

**R12 cursor/schema consumer local checkpoint — 2026-07-17:** The frontend
mirror now seeds its durable cursor from `last_event_id`, handles named
`snapshot_required` SSE frames by marking the view stale and refreshing the
measured snapshot, and ignores frames without a durable SSE cursor or
canonical `eventType`. Red-first focused tests passed (`13`); the complete
frontend suite passed (`104` files, `600` tests), typecheck passed, lint passed
with `0` errors and `123` existing warnings, the production build passed, and
the focused backend mirror/Cortex compatibility gate passed. Local coverage
under Node `24.16.0` reports `70.75%` scoped lib functions against the `73%`
floor, while the hosted Node `20` baseline on the prior exact tip reports
`75.59%`; the threshold was not changed. Commit and hosted verification are
the next checkpoint.

**R12 cursor/schema coverage repair — 2026-07-17:** The first exact hosted
run for `e195f3785eb48ea7f0170859edeeac62a317c039` passed typecheck, lint, and
all `600` frontend tests but failed the scoped-lib function floor at `70.75%`.
The root cause was the existing broad mirror fixture sending events without
durable SSE ids or canonical `eventType`; the fail-closed client correctly
ignored them, leaving registry reaction functions uncovered. The fixture now
sends canonical frames with durable ids and verifies that the reaction path
executes. The full local coverage gate passes at `76.07%` scoped-lib functions;
CodeQL `29532113056` passed, and the corrected follow-up tip still needs exact
hosted CI verification.

**R12 cursor/schema hosted verification complete — 2026-07-17:** Exact pushed
tip `3004e7d1cae1688caed79b8861019c85b4e6b8c` passed CI `29533017263` across
Ubuntu, macOS, Windows, frontend coverage/build, aggregate, release-authority,
and private Executor isolation. CodeQL `29533017285` passed all actions,
Python, and JavaScript/TypeScript analyses. The frontend coverage repair kept
the 73% scoped-lib function floor unchanged and measured `76.07%` locally.

**R11 Council composition seam local checkpoint — 2026-07-17:** The
red-first architecture guard failed because `aios/api/routes/council.py`
constructed its mission-local `CouncilState`/`CouncilMemory` directly. The
route now receives both deliberation and execution scopes from
`get_council_memory_scope` in the canonical API composition root; the copied
`MemoryAuthority` owns the exact scoped Council adapter, and the quarantine
manifest now lists only `aios/api/deps.py`. The focused R11/Council gate passed
(`96`), the exact package gate passed with `3,175` collected, `3,167 passed,
8 skipped`, exit `0`, and `88.85%` coverage; frontend typecheck, lint,
coverage, and build also passed. Hosted CI and CodeQL are pending for this
source wave. The remaining R11 audit is the authority bootstrap/advisory
pheromone seam in `aios/api/deps.py`.

**R11 Council composition seam hosted verification complete — 2026-07-17:**
Exact source tip `7a5262710b210d7be75d872ad368d58b67d1eb75` passed CI
`29536342306` across frontend, Ubuntu/macOS/Windows backend, aggregate,
release-authority, and private Executor isolation. CodeQL `29536339651` passed
Actions, Python, and JavaScript/TypeScript. The route-level construction bypass
is removed; R11 remains partial only at the remaining canonical `deps.py`
authority-bootstrap/advisory-pheromone seam and the separate packaged runtime
proof frontier.

**R11 Council composition docs checkpoint hosted verification complete —
2026-07-17:** The docs-only tip `5e78af9b2a2b1cfd0de5d70a6762e0c87057342b`
passed CI `29537224831` after one bounded retry of Ubuntu's stateful Council
test; the rerun passed Ubuntu, Windows, macOS, aggregate, frontend,
release-authority, and private Executor isolation. CodeQL `29537224826` passed
Actions, Python, and JavaScript/TypeScript. The first Ubuntu attempt failed
only at `test_approve_triggers_execution_and_worker_acts` with a credential-like
capability-payload 403 after coverage had passed; no source change was made.

**R11 advisory pheromone authority guard local checkpoint — 2026-07-17:** The
red-first regression demonstrated that `_sync_pheromone_adapter()` accepted a
look-alike adapter when its wrapped object matched the configured private
fields. The sync guard now requires the canonical `AdvisoryPheromoneAdapter`
before reusing an existing store, preserving the non-authoritative pheromone
boundary. The focused pheromone/memory-architecture gate passed and the exact
full backend gate exited `0` at `88.85%` coverage. Source commit and hosted
CI/CodeQL verification were pending at this local checkpoint.

**R11 advisory pheromone authority guard hosted verification complete —
2026-07-17:** Exact pushed source tip `a986f314eac088e12a46e04a0ac644e11a36661a`
passed CI `29540174920` and CodeQL `29540174909`. The canonical advisory-wrapper
guard is now green locally and on the immutable hosted tip. The next cursor is
the ordered R11/R13 packaged-runtime proof seam; overall V1 remains partial.

**R11 advisory pheromone guard continuity checkpoint hosted verification
complete — 2026-07-17:** Follow-up docs tip
`29ce9bb9f2e9ab14e3d683852919422a33a46d87` passed CI `29540544540` and CodeQL
`29540544508`. Local `HEAD` and `origin/master` match the exact hosted SHA;
the source repair remains green and the overall V1 declaration remains partial.

**R13 production emergency-stop construction local checkpoint — 2026-07-17:**
The production dependency graph now composes one durable
`EmergencyStopController` with real hooks for active capability revocation,
queued mission and worker cancellation, autonomy-grant revocation, and
tamper-evident evidence preservation. Capability issuance, earned-autonomy
reuse, executor dispatch, mission origination/execution, worker admission, and
promotion all receive the latch and check it before their side-effect boundary;
the mission state machine records emergency kills for queued states. The new
R13 wiring plus adjacent governance/mission regression set passed (`21`), Ruff
passed on the new enforcement files, and the exact package gate passed with
`3,179` collected, `3,171` passed, `8` skipped, exit `0`, and `88.76%` coverage.
The source commit and hosted CI/CodeQL verification are pending. R13 remains
partial because the exact emergency-clear capability and complete restart
matrix are still unproven; overall V1 remains partial.

**R13 production emergency-stop construction hosted verification complete —
2026-07-17:** Exact pushed source tip
`45765ebbe92f3b9a7e4cc7a8c2c9077c090e0d9f` passed CI
`29542860644` across platform tests, frontend, backend aggregate, and
`release-authority`; CodeQL `29542860619` also passed. The production stop
latch construction is therefore green on the immutable hosted tip. R13 is
still partial because the exact emergency-clear capability and complete
packaged restart matrix remain unproven; the next cursor is the R13/R14
packaged-runtime proof seam and overall V1 remains partial.

**R13 exact emergency-clear capability local checkpoint — 2026-07-17:** The
emergency latch now persists opaque clear-capability digests bound to its
generation, operator, new privileged authentication event, and session. The
capability is issued only while engaged, consumed atomically, rejected on
altered session/replay/generation, and accompanied by tamper-evident evidence;
the clear path remains fail-closed if evidence preservation fails. Governed
HTTP state/engage/clear routes are registered under the policy authority, and a
real isolated API probe passed bootstrap, login, strong re-authentication,
engage challenge/consume, post-stop re-authentication, clear challenge/consume,
and final unengaged state. The affected gate passed `197` tests; the exact
package gate passed with `3,181` collected, `3,173` passed, `8` skipped, exit
`0`, and `88.65%` coverage. Source commit and hosted verification are pending;
R14 strict runtime proof remains open.

**Hosted CI portability repair checkpoint — 2026-07-17:** Exact source tip
`206104dbd71fafdc914399df6606366ed6bc3c42` reached hosted CI run
`29545481136`; frontend jobs, the backend test execution, and CodeQL
`29545481141` were green, but all backend matrix jobs failed on the same
release-conformance assertion. FastAPI `0.139` exposes included routers as
lazy wrapper objects, so the test's shallow `app.routes` scan omitted the
governance routes even though the routes were mounted and covered. The test
now recursively flattens included routers. The local exact package gate is
green again (`3,181` collected, `3,173` passed, `8` skipped, `88.65%`); the
compatibility fix is pending its own pushed CI/CodeQL verdict. R14 strict
runtime proof remains open and V1 remains partial.

**Hosted CI portability repair verified — 2026-07-17:** Exact source tip
`addcde81931fba5acfbad4ec4e2e6081d88ffc24` passed CI `29546552374` across
Windows, Ubuntu, macOS, frontend, backend aggregate, and release-authority;
CodeQL `29546552431` passed all analysis jobs. The route-conformance test is
now portable across FastAPI's eager and lazy included-router representations.
R13 exact clear is hosted-green; R14 strict runtime proof remains open and
V1 remains partial.

**R14 packaged runtime proof hosted verification complete — 2026-07-17:**
Source tip `7e715b41e8dccc4ce710e5d76213c35fca12186c` is synchronized with
`origin/master`. CI `29549644470` passed Windows, Ubuntu, macOS, frontend,
aggregate backend, and release-authority; CodeQL `29549644476` passed all
analysis jobs. The release-authority job passed the private Executor Service
isolation proof and the complete strict runtime matrix; its JSON emitted
`ready=true` and `runtime_proof.all_passed=true`. The first R14 attempt at
`8a28efb` exposed that `.dockerignore` excludes the separately packaged
frontend, so the mirror probe failed closed. Follow-up `7e715b4` mounts the
checked-out frontend read-only for the one-shot proof container; the focused
conformance/runtime suite passed `30`, and the repaired hosted run is green.
Local full gate remains `3,185` collected, `3,177` passed, `8` skipped, exit
`0`, `88.52%` coverage. Local strict mode still reports only the expected
executor-unavailable limitation because this Windows workspace has no live
private service. Runtime proof is complete at the hosted release boundary;
the remaining work is continuity finalization and non-builder/operator review.
