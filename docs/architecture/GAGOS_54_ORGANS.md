# GAGOS 54 Organs

**Established:** Slice 25 of the GAGOS Completion Plan (Slices 25-40), baseline
commit `f3cb6122fb8d86bf0ae5b603da8f60678d7231ad`.

This is the canonical enumeration of every organ the GAGOS Completion Plan
tracks to green. It is a *baseline*, not a finished audit: the 22 organs
marked green below are grounded in code and tests that exist in this
checkout today (see `production_entrypoints`/`focused_tests` in
`.aios/state/ORGAN_GREEN_LEDGER.json`), not in historical claims from
`.aios/state/PRODUCTION_CONVERGENCE_LEDGER.md` that a later truth-reset
(`cc2ecea`) showed could not always be trusted at face value. The 32 organs
marked yellow are exactly the organs named across Slices 26-40; each starts
from the truthful blocker stated in that slice's own "current position",
not an optimistic completion claim.

Machine-readable source of truth: `.aios/state/ORGAN_GREEN_LEDGER.json`,
validated by `aios.application.governance.organ_ledger.validate_ledger` and
surfaced via `python -m aios.launcher organ-check [--json] [--strict]`.

## Status vocabulary

- **green** — typed contract, one production authority path, durable state,
  tests, and (where required) live evidence stamped with the commit under
  evaluation. Never a synthetic fixture presented as live proof.
- **yellow** — genuinely partial or missing; the ledger records the exact
  blocker instead of an aspirational claim.

## Green organs (22) — established prior to Slice 25

| # | Organ | Authority owner | Entry point | Tests |
|---|-------|------------------|-------------|-------|
| 1 | Security Gateway | `SecurityGatewayAuthority` | `aios/security/gateway.py` | `tests/test_security.py`, `tests/adversarial/test_gateway_bypass.py` |
| 2 | Scope Lock | `ScopeLockAuthority` | `aios/security/scope_lock.py` | `tests/test_security.py`, `tests/adversarial/test_sandbox_escape.py` |
| 3 | Secret Scanner | `SecretScannerAuthority` | `aios/security/secret_scanner.py` | `tests/test_security.py`, `tests/adversarial/test_secret_detection.py` |
| 4 | Tamper-Evident Audit Logger | `AuditLoggerAuthority` | `aios/security/audit_logger.py` | `tests/test_audit.py`, `tests/adversarial/test_audit_integrity.py` |
| 5 | Prompt Injection Shield | `InjectionShieldAuthority` | `aios/security/injection_shield.py` | `tests/test_generate_input_shield.py`, `tests/test_chat_input_shield.py` |
| 6 | Edge Trust Boundary | `EdgeTrustAuthority` | `aios/interfaces/http/edge_security.py` | `tests/test_edge_security.py`, `tests/test_api.py` |
| 7 | Policy Kernel | `PolicyKernelAuthority` | `aios/policy/kernel.py` | `tests/test_policy_kernel.py`, `tests/test_route_registry_conformance.py` |
| 8 | Action Broker | `ActionBrokerAuthority` | `aios/application/action_broker.py` | `tests/test_action_broker.py`, `tests/test_release_conformance.py` |
| 9 | Exact Capability Authority | `CapabilityAuthority` | `aios/application/capabilities/authority.py` | `tests/test_exact_capabilities.py`, `tests/test_e2e_sovereign_flywheel.py` |
| 10 | Mission Authority | `MissionAuthority` | `aios/application/missions/mission_service.py` | `tests/test_mission_contract_v1.py`, `tests/test_council_orchestrator.py` |
| 11 | Turn Coordinator | `TurnCoordinatorAuthority` | `aios/application/turns/turn_coordinator.py` | `tests/test_turn_coordinator.py`, `tests/test_chat.py` |
| 12 | Worker Foundry | `WorkerFoundryAuthority` | `aios/application/workers/foundry.py` | `tests/test_worker_foundry.py`, `tests/test_council_orchestrator.py` |
| 13 | Isolated Executor Service (construction) | `ExecutorServiceAuthority` | `aios/executor_service.py` | `tests/test_executor_service.py`, `tests/test_release_conformance.py` |
| 14 | Staged Workspace Manager (construction) | `StagedWorkspaceAuthority` | `aios/application/workspaces/staged.py` | `tests/test_staged_workspaces.py`, `tests/test_council_orchestrator.py` |
| 15 | Evidence and Verification Authority (construction) | `VerificationAuthority` | `aios/application/evidence/verification.py` | `tests/test_verification_strength.py`, `tests/test_promotion_authority.py` |
| 16 | Promotion Authority (construction) | `PromotionAuthority` | `aios/application/promotion/authority.py` | `tests/test_promotion_authority.py`, `tests/test_council_orchestrator.py` |
| 17 | Cortex Observation Bus | `CortexBusAuthority` | `aios/runtime/cortex_bus.py` | `tests/test_cortex_bus.py`, `tests/test_release_conformance.py` |
| 18 | Memory Authority (construction) | `MemoryAuthority` | `aios/application/memory/authority.py` | `tests/test_memory_authority.py`, `tests/test_chat.py` |
| 19 | Emergency Stop Controller (construction) | `EmergencyStopController` | `aios/application/governance/emergency_stop.py` | `tests/test_governance.py`, `tests/test_release_conformance.py` |
| 20 | Living Mirror Reaction Registry (construction) | `LivingMirrorAuthority` | `frontend/src/superbrain/lib/livingMirrorRegistry.ts` | `frontend/src/superbrain/lib/livingMirrorRegistry.test.ts`, `frontend/src/superbrain/lib/aiosMirror.test.ts` |
| 21 | Queen Council Orchestrator | `QueenCouncilAuthority` | `aios/council/council_orchestrator.py` | `tests/test_council_orchestrator.py`, `tests/test_e2e_sovereign_flywheel.py` |
| 22 | V1 Release Declaration (`gagos v1-check`) | `ReleaseDeclarationAuthority` | `aios/application/governance/v1_declaration.py` | `tests/test_v1_declaration.py`, `tests/test_launcher.py` |

## Yellow organs (32) — the Slices 26-40 completion target

| # | Organ | Authority owner | Slice | Truthful blocker |
|---|-------|------------------|-------|-------------------|
| 23 | Release Conformance Organ | `ReleaseConformanceAuthority` | 25 / 40 | Ledger established at this baseline; the strict gate stays non-green until every organ below turns green and Slice 40's final release proof lands. |
| 24 | Human Sovereign Identity | `IdentityAuthority` | 26 | Slice 26 landed `session_generation` (a stale session now fails closed at `IdentityService.get_authenticated_principal`) and `constitution_digest` stamping on `Principal`, threaded into `MissionContract`/`CapabilityBinding`/`ActionEnvelope`. Still missing: end-to-end HTTP-layer enforcement of a constitution-digest mismatch, and a distinct read-only code path during degraded identity. |
| 25 | Constitutional Kernel | `ConstitutionalKernelAuthority` | 26 | `ConstitutionSnapshotV1` now exists (typed, versioned, digested, foundation laws immutable by validator) in `aios/domain/governance/constitution.py`. Still missing: durable cross-restart persistence/ratification (Slice 37 territory), `PolicyKernel` still reads the old `aios.policy.constitution.Constitution` facade rather than this snapshot, and no decision path rejects execution on a constitution-digest mismatch yet. |
| 26 | Emergency Stop Organ (full boundary hard-wiring) | `EmergencyStopHardWiringAuthority` | 27 | Slice 27 closed 5 confirmed-missing boundaries: intelligence gateway (local + cloud), skill activation/reuse, maintenance scan/repair (service layer), backup restore, and capability consume. Still open: constitutional amendment activation (organ doesn't exist until Slice 37), route-layer check duplication with inconsistent error handling, and mission-transition re-checks beyond create/start. |
| 27 | Operator Taste Model | `OperatorTasteModelAuthority` | 28 | `OperatorPreferenceV1` now exists (typed source_type/confidence/status/supersedes/contradicted_by) wrapping the existing `SemanticFacts` contradiction lifecycle. Still missing: a persistence adapter that stores/reads these records, and project-scoped leak-prevention enforcement. |
| 28 | Project Understanding Organ | `ProjectUnderstandingAuthority` | 28 | `ProjectPassportV1` now exists (typed, digested, commit-bound) wrapping the existing `harvest_project_passport()` scanner, with `is_project_passport_stale()` for commit-drift detection. Still missing: `invariants`/`explicit_human_decisions` have no source in the scanner yet, and no durable cross-restart store exists. |
| 29 | Correction and Interpretation-Lineage Organ | `CorrectionLineageAuthority` | 28 | `CorrectionRecordV1` now exists (typed, digested, `grants_authority` pinned `False`) wrapping the existing before/after frame lineage in `ConversationStateStore.record_correction()`. Still missing: the store itself doesn't construct/return the typed record yet, and there's no query surface for Slice 39's read model. |
| 30 | Communication and Human-State Interpreter | `HumanStateInterpreterAuthority` | 28 | `HumanStateHypothesis` now exists (typed, `grants_authority`/`user_correctable` pinned literals) with a small deterministic `classify_human_state()` classifier -- this organ had no prior art at all. Still missing: not wired into any live conversation path, no persistence, and the classifier is an unmeasured first pass. |
| 31 | Human Representative Context Compiler | `RepresentativeContextCompilerAuthority` | 29 | `RepresentativeContextV1` now exists with `compile_representative_context()` composing the constitution/preference/passport/correction contracts into one digested packet; cloud target scrubs secrets and withholds memory refs structurally. Still missing: nothing calls this compiler yet -- `IntelligenceRequest`/`ModelCallRequest` still carry only a bare prompt with no `context_digest` (confirmed by a red-first test). Wiring every model call through it is Slice 30. |
| 32 | Universal Intelligence Gateway | `UniversalIntelligenceGatewayAuthority` | 30 | `route_intelligence_request()` now exists (emergency-stop -> context compilation -> caller-supplied model call -> output redaction) and the architecture guard now also forbids direct `OllamaClient` construction outside named local-adapter files. Still missing (investigated, requires net-new wiring, not a safe single commit): conversation/agentic-forge/maintenance/skill-compilation don't route through it yet, Council Queens' LLM slots are wired but never supplied a client (dead code), and 3 pre-existing competing "gateway" implementations still need reconciling against this one. |
| 33 | Model Registry and Capability Passport | `ModelPassportAuthority` | 31 | `ModelPassportV1` now exists (typed, role-scoped admission) with `is_admitted_for_role()`/`can_drive_tools()`/`is_stale_for_version()`. Still missing: nothing runs a real qualification suite yet (every passport must be hand-constructed) and no durable store persists one across restarts. |
| 34 | Cloud Budget and Provider-Health Organ | `ProviderHealthBudgetAuthority` | 31 | `ProviderHealthTracker` now exists: a real deterministic closed/open/half-open circuit breaker over caller-reported outcomes, in-memory per-process (matching `BudgetGuard`'s own convention). Still missing: no real provider call is wired through it yet, so it tracks nothing in production, and it isn't unified with the existing `BudgetGuard`. |
| 35 | Local Clerk Runtime | `LocalClerkRuntimeAuthority` | 32 | `LocalJobProfile` already had 9 real profiles; Slice 32 added the 4 with no prior equivalent (`VALIDATE_STRUCTURE`/`SUMMARISE_DISAGREEMENT`/`EXPLAIN_ROUTE`/`CHECK_CONTEXT_COMPLETENESS`) rather than duplicate near-synonyms. Still missing: no qualification cases or handlers for the 4 new profiles yet. |
| 36 | Clerical Job Contract and Dispatcher | `ClerkDispatcherAuthority` | 32 | `dispatch_clerical_job()` now exists (deterministic-first, unqualified-always-escalates, low-confidence-to-human). Still missing: not wired into `LocalWorkforceService`'s real request path. |
| 37 | Local Model Qualification and Health | `LocalModelQualificationAuthority` | 32 | **Live evidence recorded**: the pre-existing `QualificationSuite` was actually run 3x against the real `granite3.2:2b` model via Ollama (see `release/slice32/granite-qualification-live.json` -- exact tag, digest, hardware profile). Honest finding: all 3 runs reliably pass 15/16 checks but consistently fail "summarisation" because the model substitutes its own field name instead of the instructed one (reproduced across 5 additional samples, 1/5 correct). The organ stays yellow because the model genuinely does not yet qualify -- that is what a truthful gate is for, not a synthetic pass. |
| 38 | Durable Local-Clerk Provenance and Continuity Organ | `ClerkProvenanceAuthority` | 33 | `LocalWorkforceProvenanceStore` now exists (SQLite, per-record sha256 digests verified on read, duplicate job_id fails closed) and `gagos provenance clerk-job <job-id>` reconstructs the trace honestly from partial state -- verified directly for restart-reconstruction and tamper-detection. Still missing: `LocalWorkforceService.run_advisory_job()` doesn't call this store yet, so no real job is persisted in production. |
| 39 | Multi-Model Deliberation and Dissent Organ | `DeliberationCouncilAuthority` | 34 | Built from scratch (confirmed zero prior art). `DeliberationRecord` now exists with `unresolved_minority_concerns` derived from every position's security concerns (synthesis cannot silently drop one) and `blocks_promotion()` gating on it; fewer than 2 real positions refuses rather than faking a single-model deliberation. Still missing: Council Queens' LLM slots are wired but never supplied a client in production, so there is no live path to trigger this from yet. |
| 40 | Isolated Workspace and Executor (live proof) | `IsolatedExecutorLiveAuthority` | 35 | **Checked, not assumed**: `docker ps` fails to connect to the daemon in this environment (Docker Desktop installed but not running) -- matches this repo's own prior admission that Docker unavailability blocks the executor runtime probe. Construction exists (organ #13/#14) and is emergency-stop-gated; live proof genuinely cannot be produced here right now. |
| 41 | Promotion, Checkpoint and Rollback (live proof) | `PromotionRollbackLiveAuthority` | 35 | Same Docker-unavailable finding as organ 40. Construction exists (organ #15/#16, real `CheckpointAuthority`/`WorkspacePromotionRuntime`); an authoritative post-promotion receipt and genuine rollback-restores-exact-bytes proof both require a live daemon this environment doesn't have right now. |
| 42 | Recovery and Resumption | `RecoveryResumptionAuthority` | 35 | `MissionTransitionJournal` now exists: durable, idempotent, and verified directly (not just asserted) at all 9 of the brief's failure-matrix crash points -- a simulated restart always reports the exact same `current_state` and can resume forward. A real table-name collision with the pre-existing coarse `MissionState` transition-audit table was caught by the full regression suite and fixed before commit. Still missing: nothing in the real promotion/mission-service path calls this journal yet. |
| 43 | Local Skill Reuse, Confidence and Demotion | `SkillLifecycleAuthority` | 36 | Found real prior infrastructure (`SkillRepository.transition_state()`, `ConfidenceUpdater` -- whose own docstring flagged this exact gap) and built the missing piece: `evaluate_demotion()`/`apply_reuse_outcome()`/`human_revoke()`, plus 3 genuinely-distinct new states (`probation`/`suspended`/`revoked`) reachable through the existing validated graph. Still missing: nothing in the real `LearningService` reuse path calls it yet. |
| 44 | Golden Mission and Endurance Evaluation | `GoldenMissionEnduranceAuthority` | 36 | Checked realistically: the golden cohort (12 live governed missions, 2 real cloud providers, hours of wall-clock execution) is not achievable or appropriate to run autonomously in this pass -- recorded as not attempted, not faked. The individual mechanisms it would exercise are real and unit-tested (organ 43). |
| 45 | Constitutional Amendment Authority | `ConstitutionalAmendmentAuthority` | 37 | Confirmed genuinely missing before building. `ConstitutionalAmendmentProposalV1` + the full propose/critique/simulate/ratify/activate/rollback/reject workflow now exist; `ratify_amendment()` can only be satisfied by a real, already-consumed capability bound to the exact operator (models/workers have no path to one); foundation-law-touching proposals are refused; `activate_amendment()` is now emergency-stop-gated (closing a Slice 27 blocker) and reuses Slice 26's chaining machinery directly. Still missing: no HTTP route, no durable persistence, and the ratify action type isn't registered in the real capability-issuance routing table yet. |
| 46 | Constitutional Learning Organ | `ConstitutionalLearningAuthority` | 38 | Confirmed genuinely missing before building. `GovernanceLessonV1` feeds Slice 37's amendment pipeline directly. The one rule -- GAGOS may learn its sovereignty is weak but may never itself propose reducing human authority -- is a deterministic keyword screen verified against 8 distinct authority-reducing phrasings; a full proposal -> simulation -> ratification -> rollback path was run end to end reusing Slice 37 unchanged. Still missing: the 9 named adversarial simulations are a required catalog this module checks results FOR, not simulations it runs; no HTTP route or persistence. |
| 47 | Read-Model and Projection Organ | `ReadModelProjectionAuthority` | 39 | `ConstitutionProjection`/`EmergencyStopProjection`/`ProviderHealthProjection`/`ApprovalProjection` now exist, built on the pre-existing `MetricEnvelope`/`MetricStatus` provenance primitive (not a new one) rather than inventing the wheel `mirror.py` already has. Four real projector functions in `aios/application/read_models/governance_projections.py` assemble them from real Slice 26/27/31 objects and the real production `ApprovedAction`/`ApprovalStore` -- verified directly: a missing constitution, an unknown provider budget, and unsupplied approval fields all render `UNAVAILABLE`, never a fabricated default. Still missing: no live API route calls these projectors yet. |
| 48 | Truthful Living Mirror (full truthful UI) | `TruthfulMirrorAuthority` | 39 | Reaction-registry construction exists (organ #20) and organ 47 now supplies real typed, status-aware projections to build this from. Still missing: no frontend component consumes them -- this autonomous session has no human operator to perform the required live browser walkthrough, so frontend wiring was honestly not attempted rather than claimed. |
| 49 | Approval and Decision Surface | `ApprovalDecisionSurfaceAuthority` | 39 | `ApprovalProjection` (organ 47) is the pinned exact-decision contract -- structurally verified to carry no `approved`/`decision`/`grants_authority` field of its own, so rendering it can never itself grant authority. Still missing: no frontend surface renders it yet (same live-browser-walkthrough gap as organ 48). |
| 50 | Provenance and Explanation Surface | `ProvenanceExplanationSurfaceAuthority` | 39 | No UI answers "why was this model chosen / what was sent / what was removed" yet; unchanged this slice -- out of the backend-projection scope this pass covered. |
| 51 | Sovereign Control and Heartbeat Surface | `SovereignHeartbeatSurfaceAuthority` | 39 | `ConstitutionProjection`/`EmergencyStopProjection`/`ProviderHealthProjection` (organ 47) are exactly the typed values this heartbeat surface would compose. Still missing: no single view assembles them together, and no frontend consumes them yet. |
| 52 | Observability and Health Organ | `ObservabilityAuthority` | 40 | No unified correlation-ID tracked telemetry across model calls, clerk, executor, mission queue, verification, promotion, rollback, and emergency-stop exists yet. |
| 53 | Installation, Configuration and Key Authority | `InstallationConfigurationAuthority` | 40 | Key rotation, a bounded grace period, and truthful Ollama-absence handling are not fully implemented. |
| 54 | Backup and Disaster-Recovery Organ | `BackupDisasterRecoveryAuthority` | 40 | Backup/restore does not yet guarantee stale capabilities, pending approvals, and old sessions never restore as active. |

## How this ledger is enforced

```
python -m aios.launcher organ-check --json
python -m aios.launcher organ-check --strict
```

`--strict` exits non-zero until all 54 organs are green. `validate_ledger`
additionally refuses: duplicate `organ_id`, duplicate `authority_owner`,
missing or unknown organs, a `green` organ without focused or integration
tests, a `green` organ that requires live evidence but has none, live
evidence labelled `fixture` where `live` is required, and live evidence
stamped with any commit other than the one under evaluation.
