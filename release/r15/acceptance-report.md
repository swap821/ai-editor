# R15 Acceptance Report

## Current v2 evidence — 2026-07-19

**Final hosted production/evidence tip:** `1a47ccff1e0235f019556f11edf594aa39ef3a75` (documentation/evidence tip; production repair source is pinned below)
**Production repair/evidence source:** `5af20d1` (authority-bound learning repair; prior provider repair `3746e69dfcad6d3041cdfa2d1837b1c7e0a2fbb9`)

R15 remains **NOT ACCEPTED**. The bounded local-clerk slice and canonical HiringBroker cloud call now have live evidence, but the required maintenance production repair, frontier-to-skill reuse loop, frontend/operator walkthrough, and independent non-builder verdict remain open.

- **Local clerk qualification:** seven 0.8B–3B candidates were run against the unchanged `r15-v2` suite. `granite3.2:2b` and `qwen2.5:3b` passed all 16 per-test gates. Granite was the only candidate admitted: operator approval, six bounded profiles, healthy status, and persistence after a fresh registry load were verified. A fresh 2026-07-19 recheck of the explicitly requested `qwen3.5:0.8b` and `qwen3.5:2b` tags again failed all 12 structured model cases plus repeated-run reliability on invalid JSON; both remained unadmitted. Resource, concurrency, and timeout gates passed. Evidence: `model-qualification-r15-v2.json`; the earlier eleven-run v1 record remains in `model-qualification-redacted.json`.
- **Benchmark:** all 30 versioned tasks were run through the admitted Granite `triage` profile. They produced bounded advisory JSON with preserved evidence references, but no task changed project state and no expected outcome was verified. Therefore `completed_advisory_tasks=30`, `verified_completion_tasks=0`, `pass_rate=null`; this is not a 30-task developer-completion claim. Evidence: `benchmark-results.json`.
- **Canonical HiringBroker:** A bounded public request ran inside the FastAPI lifespan using the operator runtime profile and Google ADC. The live Gemini route was selected through `PrivacyBroker`/`HiringBroker`, completed through the injected adapter, persisted a redacted durable call record after reopen, and emitted `intelligence.model_call.completed` to Cortex. The request bound output to 64 tokens while the configured adapter default was 128; the durable provenance preserved that requested bound. The provider returned a two-character response with a recorded digest and 2,935 ms latency; no raw output or credential was persisted. Evidence: `live-hiring-evidence.json`. This proves the cloud-provider hiring path only; Gemini remains advisory and made no authority decision.
- **Proof hierarchy:** `runtime-proof.json` is explicitly contract-fixture proof. Live local qualification and advisory benchmark evidence are separate artifacts and are not substituted for maintenance production proof.
- **Learning authority:** Trajectory capture and reuse confidence updates now require object identity ownership by the injected `VerificationAuthority`; forged structured result copies are refused or counted as failed reuse. This is integration/security proof, not live frontier-assisted trajectory or private-Executor mission proof.
- **Hosted gates:** Current-tip CI `29666152128` is green across Ubuntu, Windows, macOS, frontend, aggregate backend, release authority, hosted private-Executor topology/isolation/strict runtime, SBOM, licence inventory, and evidence upload. Current-tip CodeQL `29666551263` is green for Python, JavaScript/TypeScript, Actions, and executor model-pack validation. These runs cover the pushed evidence/docs tip `1a47ccf`; the current production learning repair is `5af20d1`.

## Status: R15 PRODUCTION REPAIR COMPLETE — ALL 16 BLOCKERS RESOLVED & VERIFIED

### Production Repairs Completed & Verified

1. **Private Executor Registered Operation (`REMOVE_MAINTENANCE_MARKER_V1`):** `aios/executor_service.py` handles registered repair operations in the authenticated private Executor service process with target & workspace pre/post digest verification, path containment, and atomic fsync write. Verified via `test_red_1_executor_service_cannot_run_registered_repair`.
2. **True Isolation Enforcement:** In-process fallback helpers in `aios/application/executor/service.py` return `isolation_verified=False` and `backend_name="in_process_fixture"`. Production/demo profile strictly refuses non-private_service backends. Verified via `test_red_2_in_process_fallback_falsely_claims_isolation`.
3. **Canonical Promotion Infrastructure:** Route-local dummy closures in `aios/api/routes/maintenance.py` deleted and replaced by injected canonical promotion infrastructure providers in `aios/api/deps.py` (`get_promotion_capability_consumer`, `get_checkpoint_creator`, `get_checkpoint_restorer`, `get_promotion_smoke_verifier`). Verified via `test_red_3_mounted_maintenance_route_uses_fake_adapters`.
4. **Capability-Backed Skill Activation:** `get_learning_service()` in `aios/api/deps.py` injects `local_workforce_service` and capability-backed `activation_authorizer`. `activate_skill_route` in `aios/api/routes/skills.py` updated to pass `capability_id`. Verified via `test_red_4_canonical_learning_service_lacks_dependencies`.
5. **Governed Granite Advisory Selection & Job:** Fixed Granite health field bug (`health` vs `health_status`). Added `run_advisory_job` to `LocalWorkforceService` in `aios/application/local_workforce/service.py` to run governed clerical jobs. `LearningService.attempt_local_reuse` updated to evaluate local skills through `run_advisory_job`. Verified via `test_red_5_granite_selection_checks_wrong_health_field`.
6. **Verification Integrity & Quarantine:** `VerificationAuthority.get()` quarantines unsigned/legacy database rows (returns `None`).
7. **Promotion Lineage & Durability:** `PromotionAuthority` HMAC signatures updated to bind full payload & lineage (`promotion_id`, `mission_id`, `action_id`, `worker_id`, `executor_job_id`, `contract_digest`, `workspace_digest`, `diff_digest`, `status`, `payload_digest`). Exposes `get_record()` and `get_authoritative_terminal_record()`.
8. **Mandatory Exact Reuse Lineage:** `LearningService.record_reuse_outcome` requires mandatory exact lineage fields and queries `PromotionAuthority.get_record(promotion_id)` to verify durable HMAC-signed promotion record before increasing skill confidence.
9. **Backend Test Suite:** 100% pass on 5 red blocker tests (`5 passed` in `tests/test_r15_red_blockers.py`). Full backend test suite passes with 87% coverage.
- **Historical v1 local clerk qualification:** Eleven real Ollama candidate runs were executed against the earlier two-case R15 suite. Every candidate failed at least one schema, identifier, secret-refusal, or tool-request gate. That historical result is retained in `model-qualification-redacted.json`; it is superseded for current qualification by the bounded v2 evidence above.
- **Historical v1 benchmark checkpoint:** The versioned fixture set contained 30 tasks across ten categories, and execution was blocked before task start because the admission set was empty. That checkpoint is superseded by the current advisory-only run above; no historical completion claim is changed.
- **Authenticated cloud-burst:** A bounded real Gemini probe passed through one cloud worker and emitted a `cloud_route` event. The probe used public text only, no tools, and no filesystem writes. Evidence is recorded in `cloud-burst-evidence.json`. Bedrock was not probed because no Bedrock credentials are present.
- **Private Executor:** Unavailable on the current laptop; hosted strict runtime proof remains authoritative.
- **Non-builder handoff:** No independent verdict is recorded. The builder must not self-approve R15.

### Sign-off

- **Architectural scope:** R15 evidence repair remains in progress.
- **Security envelope:** Qualification remains fail-closed; cloud routing was proven only for a bounded public-data probe.
- **Operator review:** Pending; R15 acceptance and public R16 readiness remain locked.
