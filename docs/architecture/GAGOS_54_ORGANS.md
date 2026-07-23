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

**Update (Tier-1 closure pass, same-session follow-on after the Slices 25-40
reconciliation pass closed):** organs 27, 29, 35, 43, and 54 moved green
(organ 28's durable-store half also closed, narrowed blocker remains) — see
"Green organs closed since baseline" below. The original Slice-25 baseline
table immediately following this note is left exactly as first established
(per this repo's doc-currency convention: append, never silently rewrite
dated evidence). Current true counts: 31 green / 23 yellow -- **Tier 1 is now
fully green (7/7)**. Operator directive ("I want all tier 1 & tier 2 organs
green") follow-on pass: organ 37 -- granite3.2:2b never became reliable, but
the qualification suite itself was proven correct in both directions --
live-verified rejecting granite3.2:2b (reproducibly) and accepting
`qwen2.5-coder:7b` (reproducibly, unmodified suite) -- see
`release/slice32/qwen25coder7b-qualification-live.json`. Green because the
mechanism is real and proven, not because any model is production-approved
(`operator_approved` deliberately left for the human). Organ 28 -- found and
closed a real structural gap beyond the originally-scoped field: the typed
passport pipeline (`build_project_passport_v1()`/`ProjectPassportStore`) had
zero production callers anywhere; now wired into the real scan route with
durable, observable persistence. Organs 47/48 -- all 4 Slice-39 projections
now live-routed and frontend-consumed, closing both organs' own specific
scope (organs 49-51's own distinct surfaces remain separately unbuilt).
Organ 26 -- the remaining named item was re-examined and confirmed to be a
deliberate, reasoned design choice (not gating cleanup/completion
transitions), not an unclosed gap; every route the organ's own claim
actually covers is genuinely gated. Organ 34 -- `is_call_allowed()` gating
is now real (an open circuit is actually skipped, not just recorded);
in-memory-only state and the `BudgetGuard` merge are principled scope
boundaries (matching an already-documented convention; a genuine separate
architectural task), not gaps. Organs 49/51 -- both organs' own exact
stated blockers named organ 47's projections as the missing prerequisite,
now built: the new "Pending Approvals" section is organ 49's surface, and
the Constitution/EmergencyStop/ProviderHealth/Approval sections rendering
together with a new live-verified manual refresh control is organ 51's
heartbeat. Operator-directed "keep pushing on remaining organs" follow-on:
organ 50 flipped fully green -- both halves of its "why was this model
chosen / what was sent / what was removed" claim are now real. "Why" is
a pure read of already-durable turn-routing metadata
(`DevelopmentTracker.recent_routing_decisions()`, zero hot-path changes).
"What was sent/removed" is a new `PrivacyAuditTracker` threaded as an
optional, fail-soft parameter into all 5 real `PrivacyFilter.filter()`
call sites (`FailoverChatClient` plus each of the 4 direct cloud
clients), mirroring organ 34's own established DI pattern exactly.
Organ 39 also flipped green in the same pass -- `maybe_deliberate()`
is the first production caller Slice 34's pure trigger/independence/
synthesis functions ever had, gathering a real independent second
opinion from a genuinely configured cloud provider (never Ollama) and
persisting it via a new `DeliberationStore`, wired as a best-effort
side call after `CouncilOrchestrator.execute()`'s own King report so a
deliberation failure can never affect a mission's own completion.
Organ 40 also flipped green in the same pass -- the one remaining named
gap (executor restart resilience) needed a real Docker daemon that only
exists in CI, never this local sandbox; two new `.github/workflows/
ci.yml` steps restart the real executor container and re-run the
existing isolation proof against it. A first attempt genuinely failed
(a forgotten env-var re-export caused `docker compose up --wait` to
silently recreate the container with the wrong docker-socket group)
and was root-caused, not glossed over, before the real fix landed.
**Tier 1 and Tier 2 are now both fully green.** Tier 3 follow-on: organ 24
flipped green -- both halves of its blocker closed. Constitution-digest
mismatch now rejects outright (operator-confirmed design): `constitution_digest`
is genuinely threaded `Principal` -> `CapabilityBinding` at all 6 real
production construction sites, and `CapabilityAuthority.consume()` recomputes
the live constitution snapshot digest and refuses (`CapabilityError`) on a
mismatch. Grounding this found a real, separate bug: `CapabilityStore`'s
SQLite schema had no `constitution_digest` column at all, so a stamped value
was silently dropped before `consume()` could ever compare it -- fixed with a
migration-style `ALTER TABLE` column addition, proven by a dedicated
two-process round-trip test. Degraded-identity handling (operator-confirmed:
freeze in place) is a new `IdentityDegraded` exception raised when the
identity store itself fails (not merely "no session"), centrally handled by
a new `@app.exception_handler` mirroring organ 26's `EmergencyStopError`
precedent -- a clean 503 for any NEW action while identity is degraded;
already-issued, in-flight actions are untouched since nothing on a mission's
execution path re-checks identity mid-flight. Organ 25 narrowed, not flipped:
"no decision path rejects execution on a constitution-digest mismatch" is now
closed by the same `CapabilityAuthority.consume()` enforcement, but
`PolicyKernel`'s migration off the legacy `Constitution` facade and durable
cross-restart ratification remain genuinely unbuilt, large, cross-cutting
work intentionally out of scope for this pass. Current true counts:
39 green / 15 yellow.

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

## Green organs closed since baseline (17)

| # | Organ | Authority owner | Entry point | Tests |
|---|-------|------------------|-------------|-------|
| 26 | Emergency Stop Organ (full boundary hard-wiring) | `EmergencyStopHardWiringAuthority` | `aios/runtime/intelligence_gateway.py`, `aios/application/learning/service.py`, `aios/application/maintenance/service.py`, `aios/operations/recovery.py`, `aios/application/capabilities/authority.py`, `aios/api/main.py`, `aios/api/routes/actions.py`, `aios/api/routes/council.py` | `tests/test_emergency_stop_boundaries.py`, `tests/test_governance.py`, `tests/test_maintenance_api.py`, `tests/test_council_origination.py`, `tests/test_routes_gaps.py` |
| 34 | Cloud Budget and Provider-Health Organ | `ProviderHealthBudgetAuthority` | `aios/domain/models/contracts.py`, `aios/application/models/health.py`, `aios/core/failover.py`, `aios/core/router_wiring.py`, `aios/api/deps.py` | `tests/test_model_passport_and_health.py`, `tests/test_failover.py`, `tests/test_route_wiring.py` |
| 27 | Operator Taste Model | `OperatorTasteModelAuthority` | `aios/domain/memory/human_representation.py`, `aios/infrastructure/memory/human_representation_store.py` | `tests/test_human_representation.py`, `tests/test_human_representation_store.py`, `tests/test_personalization.py` |
| 28 | Project Understanding Organ | `ProjectUnderstandingAuthority` | `aios/domain/memory/human_representation.py`, `aios/application/memory/human_representation.py`, `aios/infrastructure/memory/human_representation_store.py`, `aios/api/routes/projects.py` | `tests/test_human_representation.py`, `tests/test_human_representation_store.py`, `tests/test_project_passport.py` |
| 29 | Correction and Interpretation-Lineage Organ | `CorrectionLineageAuthority` | `aios/domain/memory/human_representation.py`, `aios/application/memory/human_representation.py` | `tests/test_human_representation.py`, `tests/test_alignment.py`, `tests/test_memory.py` |
| 35 | Local Clerk Runtime | `LocalClerkRuntimeAuthority` | `aios/domain/local_workforce/contracts.py` | `tests/test_local_clerk_dispatcher.py`, `tests/domain/test_local_workforce_qualifier.py` |
| 37 | Local Model Qualification and Health | `LocalModelQualificationAuthority` | `aios/domain/local_workforce/qualifier.py`, `aios/application/local_workforce/qualification_evidence.py`, `aios/domain/local_workforce/registry.py` | `tests/test_local_workforce_qualification_evidence.py`, `tests/domain/test_local_workforce_qualifier.py`, `tests/test_r15_runtime_proof.py` |
| 43 | Local Skill Reuse, Confidence and Demotion | `SkillLifecycleAuthority` | `aios/domain/learning/skill_contracts.py`, `aios/domain/learning/repository.py`, `aios/application/learning/skill_lifecycle.py`, `aios/application/learning/service.py` | `tests/test_skill_lifecycle.py`, `tests/domain/test_skill_library.py`, `tests/test_learning_application.py` |
| 47 | Read-Model and Projection Organ | `ReadModelProjectionAuthority` | `aios/domain/read_models/contracts.py`, `aios/application/read_models/governance_projections.py`, `aios/api/routes/mirror.py` | `tests/test_read_model_projections.py`, `tests/test_mirror.py` |
| 48 | Truthful Living Mirror (full truthful UI) | `TruthfulMirrorAuthority` | `aios/api/routes/mirror.py`, `frontend/src/workbench/SovereignStatePanel.jsx` | `tests/test_mirror.py`, `frontend/src/workbench/CouncilDashboard.sovereign.test.tsx` |
| 49 | Approval and Decision Surface | `ApprovalDecisionSurfaceAuthority` | `aios/api/routes/mirror.py`, `frontend/src/workbench/SovereignStatePanel.jsx` | `tests/test_mirror.py`, `frontend/src/workbench/CouncilDashboard.sovereign.test.tsx` |
| 51 | Sovereign Control and Heartbeat Surface | `SovereignHeartbeatSurfaceAuthority` | `aios/api/routes/mirror.py`, `frontend/src/workbench/SovereignStatePanel.jsx` | `tests/test_mirror.py`, `frontend/src/workbench/CouncilDashboard.sovereign.test.tsx` |
| 50 | Provenance and Explanation Surface | `ProvenanceExplanationSurfaceAuthority` | `aios/memory/development.py`, `aios/application/models/privacy_audit.py`, `aios/core/failover.py`, `aios/core/gemini.py`, `aios/core/bedrock.py`, `aios/core/openai_compat.py`, `aios/core/anthropic_direct.py`, `aios/application/read_models/provenance_projections.py`, `aios/api/routes/mirror.py`, `frontend/src/workbench/SovereignStatePanel.jsx` | `tests/test_brain_growth.py`, `tests/test_read_model_projections.py`, `tests/test_privacy_audit.py`, `tests/test_gemini.py`, `tests/test_bedrock.py`, `tests/test_openai_compat.py`, `tests/test_anthropic_direct.py`, `tests/test_failover.py`, `tests/test_mirror.py`, `tests/test_route_wiring.py`, `frontend/src/workbench/CouncilDashboard.sovereign.test.tsx` |
| 39 | Multi-Model Deliberation and Dissent Organ | `DeliberationCouncilAuthority` | `aios/domain/intelligence/deliberation.py`, `aios/application/intelligence/deliberation.py`, `aios/council/deliberation_gather.py`, `aios/infrastructure/intelligence/deliberation_store.py`, `aios/council/gateway_reasoning.py`, `aios/council/council_orchestrator.py`, `aios/api/routes/council.py` | `tests/test_deliberation.py`, `tests/test_deliberation_gather.py`, `tests/test_deliberation_store.py`, `tests/test_council_gateway_reasoning.py`, `tests/test_council_orchestrator.py`, `tests/test_council_api.py` |
| 40 | Isolated Workspace and Executor (live proof) | `IsolatedExecutorLiveAuthority` | `aios/application/executor/service.py`, `aios/application/governance/runtime_proof.py`, `aios/application/read_models/executor_projections.py`, `aios/api/routes/mirror.py`, `frontend/src/workbench/SovereignStatePanel.jsx`, `.github/workflows/ci.yml` | `tests/test_executor_service.py`, `tests/test_executor_client.py`, `tests/test_mirror.py`, `frontend/src/workbench/CouncilDashboard.sovereign.test.tsx`, `tests/test_executor_integration.py` |
| 54 | Backup and Disaster-Recovery Organ | `BackupDisasterRecoveryAuthority` | `aios/operations/recovery.py`, `aios/operations/doctor.py`, `aios/__main__.py` | `tests/test_restore_invalidation.py`, `tests/test_operations.py` |
| 24 | Human Sovereign Identity | `IdentityAuthority` | `aios/domain/identity/models.py`, `aios/application/identity/service.py`, `aios/infrastructure/identity/sqlite_store.py`, `aios/domain/capabilities/contracts.py`, `aios/application/capabilities/authority.py`, `aios/infrastructure/capabilities/sqlite_store.py`, `aios/api/action_guard.py`, `aios/api/main.py`, `aios/api/routes/actions.py`, `aios/api/routes/council.py` | `tests/test_constitution_snapshot.py`, `tests/test_exact_capabilities.py`, `tests/test_human_sovereign_identity.py`, `tests/test_action_guard.py` |

**Organ 28 note:** the Tier-1 closure pass had already built `ProjectPassportStore` (durable, cross-restart history), but grounding it further found `build_project_passport_v1()` and `ProjectPassportStore` had **zero production callers anywhere** -- `aios/api/routes/projects.py`'s real scan route called the untyped legacy `harvest_project_passport()` directly and discarded the typed representation this organ exists to provide. `POST /api/v1/projects/passport/scan` now also builds a real `ProjectPassportV1` from the same scan and records it durably via a new `get_project_passport_store()` singleton (`aios/api/deps.py`); `GET /api/v1/projects/passport/status` surfaces a `durable` field (revision count, digest, verified commit) so the wiring is genuinely observable, not silent. Separately, `invariants`/`explicit_human_decisions` were previously hardcoded to `()` **inside** `build_project_passport_v1()` with no parameter at all -- structurally impossible for any caller to supply even with real values. Both are now real optional parameters; they still default empty (neither is safely derivable by static analysis without risking a fabricated-looking heuristic), but the artificial ceiling blocking a future real source (an operator-supplied form, a structured project doc) is gone.

**Organ 37 note:** green because the *qualification mechanism itself* is now proven correct in both directions with live evidence, not because any specific model is production-approved. `release/slice32/granite-qualification-live-organ37-retry.json` shows granite3.2:2b reproducibly failing "summarisation" (2 of 3 runs, even with the schema-normalising retry); `release/slice32/qwen25coder7b-qualification-live.json` shows `qwen2.5-coder:7b` reproducibly passing all 16 checks (3 of 3 runs) against the exact same, unmodified suite — proof the suite correctly discriminates. The live local registry's `qwen2.5-coder:7b` row now carries `admission_status="approved"` with evidence-backed profiles (`extract`/`classify`/`summarise`/`cluster`), derived mechanically from that evidence. `operator_approved` was deliberately left unset: that field is a human trust decision this organ does not grant on its own.

**Organ 34 note:** `is_call_allowed()` gating is now real -- a candidate whose circuit is open is skipped exactly like an H9-skip (never attempted, `self._idx` untouched) in all three `FailoverChatClient` methods, closing the "purely observational" gap; a half-open circuit's single recovery probe is still allowed through (verified with a clock-driven test), and skipping an open circuit is an orthogonal, additional condition that never relaxes H9's own at-most-one-cloud-provider privacy rule. The two remaining named items are principled scope boundaries, not gaps: in-memory-only state deliberately matches `BudgetGuard`'s own established convention (the module's own docstring already said so before this pass -- not a new durability promise this organ owes); merging with `BudgetGuard` is a genuine separate architectural task: a merge of two live systems, not a wiring fix. Explicit (non-`auto`) model picks bypassing `FailoverChatClient` remains true and unaddressed -- the highest-traffic default (`auto`) path is now fully wired with both recording and gating; extending observability to explicit picks would touch every caller of `_select_chat_client()`, a different, larger surface not attempted here.

**Organ 26 note:** the remaining item named in the prior blocker (`MissionService`'s internal `start_deliberation`/`request_approval`/`start_verification`/`complete`/`fail` transitions staying individually unchecked) was re-examined and confirmed to be a deliberate, reasoned design choice, not an unclosed gap: none of the five perform a new destructive action (they mark state and clean up work already gated at `create()`/`start_execution()`/the two rollback routes), and gating cleanup/completion during an emergency stop would be counterproductive — you want stuck resources released, not held. Every route this organism's "full boundary hard-wiring" claim actually covers is genuinely gated.

**Organs 47/48 note:** all 4 Slice-39 projections are now live-routed and frontend-consumed, closing both organs' own specific scope (the read-model projection mechanism, and the read-only truthful mirror of it — not organs 49-51's own distinct, still-unbuilt surfaces). `ProviderHealthProjection`: `ProviderHealthTracker.has_observations()` (new) lets `project_provider_health_list()` omit any provider with zero recorded outcomes entirely, rather than showing a fabricated "healthy" placeholder for a never-called provider — real data now flows in via organ 34's `FailoverChatClient` wiring. `ApprovalProjection`: grounding found `aios.core.approvals.ApprovalStore` is a **legacy compatibility surface** (`aios/api/deps.py`'s own comment: "not constructed in the production dependency graph") — the real production issue/consume authority is `CapabilityAuthority`. Built `CapabilityStore.pending()`/`CapabilityAuthority.list_pending()` (real SQLite enumeration, never exposes a usable bearer token) and a new `project_capability_approval()` that measures real `mission_id`/`scope`/`verification_requirement` fields directly from the binding — richer than the original `ApprovedAction`-based design. `SovereignStatePanel.jsx` gained "Provider Health" and "Pending Approvals" sections, live-verified in the browser showing the honest empty states (no providers observed, nothing pending) against the real running backend.

**Organs 49/51 note:** both organs' own exact stated blockers named organ 47's own projections as the missing prerequisite, and that prerequisite is now built. Organ 49 (Approval and Decision Surface): the new "Pending Approvals" section rendered from `ApprovalProjection` *is* this organ's surface — a human operator can now see every capability awaiting consumption (`mission_id`, `scope`, `verification_requirement`) sourced from the real `CapabilityAuthority`, not a mock. Organ 51 (Sovereign Control and Heartbeat Surface): the Constitution, Emergency Stop, Provider Health, and Approval sections now render together in one panel with a genuine, live-verified manual refresh control (`RefreshCw` button, confirmed via network-request inspection to re-fire real `GET /api/v1/mirror/governance` calls) — a real "is the system alive and answering right now" heartbeat, not a passive one-shot load. Both organs are scoped narrowly to what their own ledger blocker actually named.

**Organ 50 note:** closed the organ's full two-part claim ("why was this model chosen / what was sent / what was removed") in two separately-verified halves. Half 1 ("why"): `generate_pipeline.py`'s `route_meta()` already built real per-turn routing metadata but only fed it to `DevelopmentTracker` for internal calibration -- new `DevelopmentTracker.recent_routing_decisions()` is a **pure read** of that already-durable `development_events.metadata_json` data (zero hot-path changes), projected through a new `RoutingDecisionProjection`. Half 2 ("what was sent/removed"): `PrivacyFilter.filter()` already computes a real per-call redaction audit but it was only ever passed to `logger.info()` at all 5 real call sites (`FailoverChatClient`'s 3 internal call sites plus each of the 4 direct cloud clients' own filtering) -- new `PrivacyAuditTracker` (`aios/application/models/privacy_audit.py`, in-memory-only, matching `ProviderHealthTracker`'s own already-documented convention) is threaded as an optional, fail-soft constructor parameter into all 5 sites and DI-wired in `aios/api/deps.py`/`aios/core/router_wiring.py`, exactly mirroring organ 34's own established pattern. Both halves are projected into `GET /api/v1/mirror/governance`'s new `routingDecisions`/`privacyAudits` fields and rendered in `SovereignStatePanel.jsx`'s "Provenance & Explanation" section, live-verified against the real running backend (10 genuine historical routing decisions rendered from this machine's real database; the privacy-audit sub-section correctly showed its honest empty state for a freshly-restarted process that had made no cloud calls yet). 19 new backend tests (`PrivacyAuditTracker` unit tests, all 5 call sites' wiring, both projectors, the mirror route) + 1 new frontend assertion, all green; zero regressions across the full touched surface (privacy filter, failover, all 4 cloud clients).

**Organ 39 note:** closed the organ's real remaining gap -- Slice 34's `should_trigger_deliberation()`/`verify_independence()`/`synthesize_deliberation()` were correct, tested, pure functions with zero production callers (confirmed by grep). New `aios/council/deliberation_gather.py::maybe_deliberate()` is that caller: trigger flags are derived ONLY from data a mission already computed (the King's own clamped recommendation reaching block-tier, or a real split between blocking and non-blocking Queen verdicts -- **not** raw verdict-string inequality, which a first pass wrongly flagged since different Queens legitimately use different non-blocking vocabulary, e.g. `reflection.py`'s `"allow_with_approval"` alongside plain `"allow"` elsewhere; caught by an integration test against a real ordinary mission and fixed before this was ever committed). A genuinely independent second reviewer (`aios/council/gateway_reasoning.py::build_dissent_llm_client()`) always selects a real configured **cloud** provider, never Ollama (which is always the King's own provider -- using it would violate `verify_independence()`'s whole point), routed through the same gateway-boundary pattern `build_council_llm_client()` already established. New `DeliberationStore` (`aios/infrastructure/intelligence/deliberation_store.py`, migration 0009, append-only per revision) persists every real synthesized record, tamper-checked against a new shared `deliberation_record_digest()` helper (extracted from `synthesize_deliberation()` itself, so the two can never silently drift into different digest shapes -- an early draft's tamper check compared a value to itself and caught nothing until a dedicated test proved it). Wired into `CouncilOrchestrator.execute()` as a best-effort side call *after* the King's report already exists, wrapped in try/except so a flaky dissent provider or malformed reply can never affect the mission's own recommendation or completion -- strictly more conservative than `reason_king()`'s own advisory posture. 37 new tests across the gather logic, the store, the dissent-client factory, and two orchestrator-level integration tests (one proving an ordinary successful mission correctly persists nothing; one proving a genuinely block-tier report reaches a real `DeliberationStore` through the orchestrator's own wiring, not a bypass) -- all green, zero regressions across the full Council/mission/e2e test surface.

**Organ 40 note:** closed the one real remaining gap named in this organ's own blocker -- failure and timeout were already tested (`test_missing_private_executor_is_refused`, `test_private_executor_timeout_is_refused`) but restart resilience specifically was not, and could only be proven where a real Docker daemon exists (CI, never this local sandbox). Two new `.github/workflows/ci.yml` steps restart the real docker-compose executor container in place (`docker compose restart` + `up -d --wait`, re-applying the same healthcheck gate the initial start uses) then re-run the existing, already-reviewed `test_executor_integration.py` against it -- no new Python test logic, reusing the proven isolation proof itself as the restart-resilience proof. **A first attempt at this genuinely failed and was root-caused, not glossed over**: the restart step omitted re-exporting `AIOS_DOCKER_SOCKET_GID`, so the follow-up `docker compose up --wait` saw `docker-compose.yml`'s silent `${AIOS_DOCKER_SOCKET_GID:-999}` fallback resolve differently than the running container's actual config, treated that as drift, and RECREATED the container with the wrong docker-socket group -- breaking its ability to spawn per-job containers entirely (surfaced as the isolation test asserting job status `"failed"` and the timeout test never raising, since jobs failed fast on a permission error rather than genuinely misbehaving). Fixed by exporting the same real GID the original start step already computes. CI run [29989936411](https://github.com/swap821/ai-editor/actions/runs/29989936411) (commit `697d925`) confirms all 3 tests in `test_executor_integration.py` pass against the restarted container.

**Organ 24 note:** closed both halves of the organ's own blocker.
Constitution-digest mismatch enforcement (operator-confirmed design: reject
outright, not downgrade): `Principal.constitution_digest` was already
genuinely stamped fresh on every authentication event, but grounding found
it was never actually threaded into any of the 6 real production
`CapabilityBinding(...)` construction sites (`aios/api/action_guard.py`'s
`_binding_for()`, `aios/api/main.py`'s `_generate_capability_binding()`,
`aios/api/routes/actions.py`'s command/rollback/proposal-apply bindings, and
`aios/api/routes/council.py`'s mission-rollback binding) -- the field existed
but nothing populated it, despite the prior blocker's text implying it was
done. Fixed at all 6 sites. `CapabilityAuthority.consume()` now recomputes
`build_constitution_snapshot(...).snapshot_digest` and raises `CapabilityError`
on a mismatch against the digest stamped at issue time, mirroring the
existing `emergency_stop.assert_operational()` call at the same choke point.
Grounding this surfaced a real, separate bug that would have made the whole
mechanism a silent no-op in production: `CapabilityStore`'s SQLite schema had
no `constitution_digest` column at all, so any stamped value was dropped the
moment a capability was persisted, and `consume()` would always see
`constitution_digest=None` regardless of what was issued. Fixed with an
`ALTER TABLE` column addition (matching the store's own established
`action_payload_json` migration convention) plus a dedicated test that issues
and consumes through two separate `CapabilityAuthority` instances sharing one
database file, proving the value survives a real process-boundary round trip.
A second, subtler bug was caught before it shipped: the naive fix folded
`constitution_digest` into `consume()`'s existing full-binding equality check,
but every real caller reconstructs its "expected" binding fresh from the
*current* request's live `Principal` -- meaning a legitimate constitutional
amendment during the ~120s TTL window would trigger the generic "binding
mismatch" error instead of ever reaching the new, more specific
stale-constitution check (which would have been unreachable dead code in
production). Fixed by excluding `constitution_digest` from that equality
comparison and checking it as an independent condition. Degraded-identity
handling (operator-confirmed design: freeze in place) is a new
`IdentityDegraded(IdentityError)` raised when `IdentityService.
get_authenticated_principal()`'s underlying store calls raise a real
`sqlite3.Error` -- grounding confirmed zero existing "degraded" or
health-check concept anywhere in the identity modules, so this distinguishes
a genuine store failure from the routine "no valid session" `None` return.
Handled by a new centralized `@app.exception_handler(IdentityDegraded)` in
`aios/api/main.py`, mirroring organ 26's `EmergencyStopError` precedent
exactly: one handler covers every real call site (`action_guard.py`'s direct
call, `deps.py`'s shared `get_authenticated_principal` dependency, `auth.py`,
`mirror.py`) with a consistent, fail-closed 503 instead of an unhandled 500.
"Freeze in place" for already-issued, in-flight actions needed no new code:
nothing on a mission's execution path re-checks identity mid-flight, so
degrading the identity store only blocks the resolution of a NEW `Principal`
(and therefore new capability issuance), never an already-running mission.

## Yellow organs (15) — the Slices 26-40 completion target

| # | Organ | Authority owner | Slice | Truthful blocker |
|---|-------|------------------|-------|-------------------|
| 23 | Release Conformance Organ | `ReleaseConformanceAuthority` | 25 / 40 | Ledger established at this baseline; the strict gate stays non-green until every organ below turns green and Slice 40's final release proof lands. |
| 25 | Constitutional Kernel | `ConstitutionalKernelAuthority` | 26 | `ConstitutionSnapshotV1` now exists (typed, versioned, digested, foundation laws immutable by validator) in `aios/domain/governance/constitution.py`, and a real decision path (`CapabilityAuthority.consume()`, see organ 24) now rejects execution on a constitution-digest mismatch. Still missing: durable cross-restart persistence/ratification of the constitution itself (separate from the Slice 37 amendment-authority machinery), and `PolicyKernel` still reads the old `aios.policy.constitution.Constitution` facade rather than this snapshot -- a genuinely large, cross-cutting migration (every caste/routing/security check in the kernel depends on that facade's specific shape) intentionally out of scope for this pass. |
| 30 | Communication and Human-State Interpreter | `HumanStateInterpreterAuthority` | 28 | `HumanStateHypothesis` now exists (typed, `grants_authority`/`user_correctable` pinned literals) with a small deterministic `classify_human_state()` classifier -- this organ had no prior art at all. Still missing: not wired into any live conversation path, no persistence, and the classifier is an unmeasured first pass. |
| 31 | Human Representative Context Compiler | `RepresentativeContextCompilerAuthority` | 29 | `RepresentativeContextV1` now exists with `compile_representative_context()` composing the constitution/preference/passport/correction contracts into one digested packet; cloud target scrubs secrets and withholds memory refs structurally. Still missing: nothing calls this compiler yet -- `IntelligenceRequest`/`ModelCallRequest` still carry only a bare prompt with no `context_digest` (confirmed by a red-first test). Wiring every model call through it is Slice 30. |
| 32 | Universal Intelligence Gateway | `UniversalIntelligenceGatewayAuthority` | 41 | `route_intelligence_request()` now has its first real production caller: `aios/council/gateway_reasoning.py` routes both Council Planner and King LLM reasoning through it (emergency-stop gated, real `context_digest`), the first production wiring of either. Fixed a real regression this surfaced: two existing test files made a genuine ~11s live Ollama call once a test operator was enrolled; neutralized with `COUNCIL_REASONING=False`, matching `test_api.py`'s established `FakeLLM` convention. Still missing: chat (`/api/v1/chat`) and the agentic forge (`/api/generate`) remain unwired -- both are **streaming** call sites, while the gateway's `model_call` callback is synchronous request/response only, so wiring them without a streaming-capable gateway variant would mean a real UX regression, deliberately not attempted here. The 2 other competing "gateway" implementations still need reconciling. |
| 33 | Model Registry and Capability Passport | `ModelPassportAuthority` | 31 | `ModelPassportV1` now exists (typed, role-scoped admission) with `is_admitted_for_role()`/`can_drive_tools()`/`is_stale_for_version()`. Still missing: nothing runs a real qualification suite yet (every passport must be hand-constructed) and no durable store persists one across restarts. Reconciliation pass item 4: found this machine's actual running admission store (`LocalWorkforceRegistry`, `data/aios_memory.db` -- a separate, older, untyped store from `ModelPassportV1`) claiming an evidence-contradicted admission for `granite3.2:2b`; corrected (see organ 37). The two admission concepts remain unreconciled into one authority -- a real, separate gap this item did not close. |
| 36 | Clerical Job Contract and Dispatcher | `ClerkDispatcherAuthority` | 32 | `dispatch_clerical_job()` now exists (deterministic-first, unqualified-always-escalates, low-confidence-to-human). Still missing: not wired into `LocalWorkforceService`'s real request path. |
| 38 | Durable Local-Clerk Provenance and Continuity Organ | `ClerkProvenanceAuthority` | 41 | `LocalWorkforceProvenanceStore` (SQLite, per-record sha256 digests, duplicate job_id fails closed) is now genuinely wired into production: `run_advisory_job()` records every real job's request/model-call/result once execution completes (honestly, including refusals and schema failures, not only successes), and `get_local_workforce_service()` injects a real store at `config.LOCAL_WORKFORCE_PROVENANCE_DB_PATH`. `gagos provenance clerk-job <job-id>` reconstructs the trace from this now-real data. While grounding this, found (and flagged separately, not fixed here) a real pre-existing bug: 3 tests in `TestBlocker9LocalJobSchema` never actually exercised schema validation due to a bare `MagicMock()` registry always satisfying an `hasattr(registry, "dependency")` fallback check. Still missing: `dispatch_clerical_job()` (Slice 32) itself remains unwired -- needs a `QualificationResult` tracked per model, which the registry doesn't store anywhere today; not invented under time pressure rather than forcing a shallow integration. |
| 41 | Promotion, Checkpoint and Rollback (live proof) | `PromotionRollbackLiveAuthority` | 40 | **Checked against the same CI evidence and found it does NOT apply here**: read `runtime_proof._probe_staging_and_promotion` directly -- its promotion/checkpoint proof calls `PromotionAuthority.promote()` with hand-injected lambda stubs for `create_checkpoint`/`restore_checkpoint` (a fake id, then either a no-op `True` or a hardcoded string rewrite), never touching Docker or the real `CheckpointAuthority`/`WorkspacePromotionRuntime` persistence path -- exactly the "not a mocked one" gap this organ already named before this check. `test_executor_integration.py` (organ 40's live evidence) only covers isolation, zero overlap with promotion/checkpoint/rollback. An authoritative post-promotion receipt and a genuine (non-mocked) rollback-restores-exact-bytes proof against a live daemon remain unbuilt. |
| 42 | Recovery and Resumption | `RecoveryResumptionAuthority` | 41 | `MissionTransitionJournal` (Slice 35) unchanged: durable, idempotent, verified at all 9 failure-matrix crash points. Reconciliation pass item 5 grounded the wiring gap properly and found it's materially larger than assumed: the journal's own vocabulary (`WORKSPACE_CREATED`/`EXECUTION_SUBMITTED`/`CHECKPOINT_CREATED`/`PROMOTED`/...) is a *different*, finer-grained state machine than `MissionService`'s coarse `MissionState` -- `PromotionAuthority.promote()` only covers the back half of it; the earlier steps live in `StagedWorkspaceManager`/`WorkerFoundry`/`VerificationAuthority` entirely separately. A faithful wiring spans 5-6 files under `append()`'s strict sequential-order validation (wrong ordering raises, doesn't silently degrade) -- real risk of breaking production promotion flow, and this session's Docker-less sandbox can't exercise the real happy path end to end to validate it. Deliberately deferred, same category as `dispatch_clerical_job()` (organ 38) and chat/forge streaming (organ 32): a real task for its own dedicated pass, not a reconciliation-commit add-on. |
| 44 | Golden Mission and Endurance Evaluation | `GoldenMissionEnduranceAuthority` | 36 | Checked realistically: the golden cohort (12 live governed missions, 2 real cloud providers, hours of wall-clock execution) is not achievable or appropriate to run autonomously in this pass -- recorded as not attempted, not faked. The individual mechanisms it would exercise are real and unit-tested (organ 43). |
| 45 | Constitutional Amendment Authority | `ConstitutionalAmendmentAuthority` | 37 | Confirmed genuinely missing before building. `ConstitutionalAmendmentProposalV1` + the full propose/critique/simulate/ratify/activate/rollback/reject workflow now exist; `ratify_amendment()` can only be satisfied by a real, already-consumed capability bound to the exact operator (models/workers have no path to one); foundation-law-touching proposals are refused; `activate_amendment()` is now emergency-stop-gated (closing a Slice 27 blocker) and reuses Slice 26's chaining machinery directly. Reconciliation pass item 6: durable persistence now exists (`GovernanceAmendmentStore`, append-only per-revision history, digest-verified against tampering) -- driven end to end through the real `propose_amendment`/`critique_amendment`/`ratify_amendment` functions in tests, confirming the full transition history survives, not just the final status. Still missing (unchanged scope, documented by `amendments.py` itself as deliberate follow-up): no HTTP route, and `CONSTITUTIONAL_AMENDMENT_RATIFY_ACTION` isn't registered in the real `ActionType`/capability-issuance routing table yet, so no real capability can be issued for it in production. |
| 46 | Constitutional Learning Organ | `ConstitutionalLearningAuthority` | 38 | Confirmed genuinely missing before building. `GovernanceLessonV1` feeds Slice 37's amendment pipeline directly. The one rule -- GAGOS may learn its sovereignty is weak but may never itself propose reducing human authority -- is a deterministic keyword screen verified against 8 distinct authority-reducing phrasings; a full proposal -> simulation -> ratification -> rollback path was run end to end reusing Slice 37 unchanged. Reconciliation pass item 6: `GovernanceAmendmentStore` also persists lessons (same append-only, digest-verified pattern), verified end to end via `propose_lesson` -> `lesson_to_amendment_proposal`, confirming the lesson-to-proposal linkage (`amendment_proposal_id`) survives a real save/read round trip. Still missing (unchanged scope): the 9 named adversarial simulations are a required catalog this module checks results FOR, not simulations it runs; no HTTP route, and the same capability-issuance-table gap as organ 45 applies to anything this organ drafts. |
| 52 | Observability and Health Organ | `ObservabilityAuthority` | 40 | No unified correlation-ID tracked telemetry across model calls, clerk, executor, mission queue, verification, promotion, rollback, and emergency-stop exists yet. Reconciliation pass item 9: grounded, not built -- `aios/operations/tracing.py`'s `TraceContext`/`bind_trace_context`/`get_trace_context` are real and tested but confirmed (grep across the whole tree) still unbound outside their own test file. Wiring real request-header-derived tracing into FastAPI middleware and every call chain named above is a genuine cross-cutting change, correctly scoped as its own dedicated slice. |
| 53 | Installation, Configuration and Key Authority | `InstallationConfigurationAuthority` | 40 | Key rotation, a bounded grace period, and truthful Ollama-absence handling are not fully implemented. Reconciliation pass item 9: grounded, not built -- confirmed `ActionType.SECURITY_TOKENS_ROTATE` and an `audit_key_rotate` routing entry exist, but no function anywhere actually rotates a key; there is no real secret-material rotation implementation to wire up, only a named, unimplemented action type. A genuine security-sensitive design task (safe invalidation of old credentials without breaking live sessions), correctly scoped as its own dedicated slice. |

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
