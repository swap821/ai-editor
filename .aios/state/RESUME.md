**Goal:** Complete the GAGOS R15 Sovereign Intelligence and Maintenance Flywheel with executable, fail-closed evidence; do not start R16.

**Last completed+verified step:** 
- **Phase 1 (Canonical mounted skill-reuse composition)** — COMPLETE & VERIFIED (15/15 tests green in `tests/test_canonical_skill_reuse_validator.py`).
  - Production `verification_plan_validator` in `aios/api/deps.py` enforces strict fail-closed validation of `SkillVerifierSpec`.
- **Phase 2 (Repair maintenance mission completion ordering)** — COMPLETE & VERIFIED (2/2 red-first tests green in `tests/test_maintenance_completion_ordering.py`, plus 24/24 in `tests/test_maintenance_resolution_authority.py` and 4/4 in `tests/test_maintenance_convergence.py`).
  - Reordered completion lifecycle in `aios/application/maintenance/service.py`: `repair worker completes` → `structured verification` → `promotion` → `exact post-promotion rescan` → `authoritative rescan proof` → `COMPLETED`.
- **Phase 3 (Canonical maintenance production composition)** — COMPLETE & VERIFIED (7/7 tests green in `tests/test_maintenance_api.py`).
  - Added `MAINTENANCE_SCAN`, `MAINTENANCE_REPAIR_CREATE`, `MAINTENANCE_REPAIR_RUN` to `ActionType` (`aios/domain/actions/envelope.py`).
  - Added `get_maintenance_convergence_service` provider to `aios/api/deps.py`.
  - Registered route authorities in `PolicyKernel._ROUTE_AUTHORITY` and `_METHOD_ROUTE_AUTHORITY` (`aios/policy/kernel.py`).
  - Implemented production maintenance endpoints in `aios/api/routes/maintenance.py` (`POST /api/v1/maintenance/scans`, `POST /api/v1/maintenance/repairs/missions`, `POST /api/v1/maintenance/repairs/run`, `GET /api/v1/maintenance/repairs/{mission_id}/status`).
  - Mounted HTTP test suite verifies unauthenticated refusal, capability challenge/retry/replay, payload mismatch, emergency stop, invalid scanner, escaped path, shell metacharacters, and governed end-to-end flow.

**Next action:** Phase 4 (Real WorkerFoundry and private Executor maintenance proof).

**Open approvals/blockers:**
- Phases 4-11 of R15 production blockers remain open.
- R15 remains NOT ACCEPTED. Do not self-approve R15 or start R16.

**Active files:**
- `aios/domain/actions/envelope.py`
- `aios/policy/kernel.py`
- `aios/api/deps.py`
- `aios/api/routes/maintenance.py`
- `aios/application/evidence/verifier_registry.py`
- `tests/test_maintenance_api.py`
