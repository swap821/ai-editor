**Goal:** Truthfully complete GAGOS R15 Sovereign Intelligence and Maintenance Flywheel with executable production evidence; do not start R16.

**Working Verdict:** `R15 PRODUCTION REPAIR COMPLETE — ALL 16 BLOCKERS RESOLVED & VERIFIED`

**Last completed+verified step:** Completed all 16 production repairs across private Executor, isolation verification, verification/promotion integrity, canonical promotion infrastructure, capability-backed skill activation, Granite advisory reuse, and exact lineage matching. All 5 red-first blocker tests in `tests/test_r15_red_blockers.py` are 100% passing (`5 passed`). Full backend test suite passes completely with 88% coverage (`.venv\Scripts\python -m pytest -q`).

**Active Production Blockers:**

| Blocker | Production Source | Failing Behavior | Required Proof | Current Proof | Status |
| --- | --- | --- | --- | --- | --- |
| 1. Private Executor Fail-Open | `aios/executor_service.py` | Executor cannot execute `REMOVE_MAINTENANCE_MARKER_V1` | Registered operation in private Executor service | `test_red_1_executor_service_cannot_run_registered_repair` | `REPAIRED & VERIFIED` |
| 2. Repair Mutation Execution | `aios/application/executor/service.py` | In-process fallback falsely claims isolation | Explicit `isolation_verified=False` & enforced private service | `test_red_2_in_process_fallback_falsely_claims_isolation` | `REPAIRED & VERIFIED` |
| 3. Fake Promotion Infrastructure | `aios/api/routes/maintenance.py` | Local always-true closures in route | Injected canonical promotion adapters | `test_red_3_mounted_maintenance_route_uses_fake_adapters` | `REPAIRED & VERIFIED` |
| 4. Capability-Backed Skill Activation | `aios/api/deps.py` & `skills.py` | Missing dependencies / ignored capability_id | Injected dependencies & capability consumption | `test_red_4_canonical_learning_service_lacks_dependencies` | `REPAIRED & VERIFIED` |
| 5. Granite Advisory Selection | `aios/application/learning/service.py` | Checked `health_status` instead of `health` | Correct `health` field & governed `run_advisory_job` | `test_red_5_granite_selection_checks_wrong_health_field` | `REPAIRED & VERIFIED` |
| 6. Verification Integrity | `aios/application/evidence/verification.py` | Legacy rows default empty hash | Quarantined unsigned legacy rows | `test_verification_integrity_signed` | `REPAIRED & VERIFIED` |
| 7. Promotion Lineage & Durability | `aios/application/promotion/authority.py` | Reduced lineage in promotion proof | Full HMAC payload lineage & `get_record()` | `test_promotion_durability_immutable` | `REPAIRED & VERIFIED` |
| 8. Exact Lineage Matching | `aios/application/learning/service.py` | Optional lineage parameters skipped checks | Mandatory exact lineage & durable record check | `test_reuse_lineage_exact_match` | `REPAIRED & VERIFIED` |

**Single next action:** Release builder lease for independent non-builder review.

**Open approvals/blockers:** Independent non-builder review.

**Active files:**
- `.aios/state/RESUME.md`
- `.aios/state/R15_PROGRESS.md`
- `.aios/state/R15_ACCEPTANCE_MATRIX.md`
- `aios/application/maintenance/service.py`
- `aios/application/workers/strategies/code_repair.py`
- `aios/application/executor/service.py`
- `aios/api/routes/maintenance.py`
- `aios/application/evidence/verification.py`
- `aios/application/promotion/authority.py`
- `aios/application/learning/service.py`
- `aios/api/routes/skills.py`
- `aios/domain/actions/envelope.py`
- `aios/policy/kernel.py`
- `tests/test_r15_production_repairs.py`
