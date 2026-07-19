**Goal:** Complete the GAGOS R15 Sovereign Intelligence and Maintenance Flywheel with executable, fail-closed evidence; do not start R16.

**Last completed+verified step:** 
- **Phase 1 (Canonical mounted skill-reuse composition)** — COMPLETE & VERIFIED (15/15 tests green in `tests/test_canonical_skill_reuse_validator.py`).
  - Production `verification_plan_validator` in `aios/api/deps.py` enforces strict fail-closed validation of `SkillVerifierSpec` (validates verifier_id, version, target_pattern, required_observations, minimum_strength, rejecting string plans, None, extra fields, executable command fields).
- **Phase 2 (Repair maintenance mission completion ordering)** — COMPLETE & VERIFIED (2/2 red-first tests green in `tests/test_maintenance_completion_ordering.py`, plus 24/24 in `tests/test_maintenance_resolution_authority.py` and 4/4 in `tests/test_maintenance_convergence.py`).
  - Reordered completion lifecycle in `aios/application/maintenance/service.py`: `repair worker completes` → `structured verification` → `promotion` → `exact post-promotion rescan` → `authoritative rescan proof` → `COMPLETED`.
  - Mission remains in `VERIFYING` state until `reconcile_rescan` proves resolution with `VERIFIED_RESOLVED`, at which point `MissionService.complete` is invoked.

**Next action:** Phase 3 (Canonical maintenance production composition in `aios/api/deps.py` or remaining production blockers).

**Open approvals/blockers:**
- Phases 3-11 of R15 production blockers remain open.
- R15 remains NOT ACCEPTED. Do not self-approve R15 or start R16.

**Active files:**
- `aios/api/deps.py`
- `aios/application/maintenance/service.py`
- `aios/domain/maintenance/lifecycle.py`
- `tests/test_canonical_skill_reuse_validator.py`
- `tests/test_maintenance_completion_ordering.py`
- `tests/test_maintenance_resolution_authority.py`
