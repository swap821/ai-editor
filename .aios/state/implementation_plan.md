# R15 Slice 14: Runtime Proof and Benchmark Expansion

## Goal
Implement the executable runtime proofs for the R15 architecture to guarantee that the sovereign intelligence boundaries, local workforce configuration, and maintenance lifecycles function exactly as designed and fail-closed when constraints are violated.

## Proposed Changes

### [NEW] `aios/application/governance/r15_runtime_proof.py`
This file will contain the `run_r15_runtime_proofs()` function, which acts similarly to the v1 proofs by executing the R15 matrix in a disposable environment. 

We will add executable proofs for:
1. `local_workforce_registry`: Verifies that configuration persists across restarts.
2. `local_workforce_qualification`: Verifies that a local model can execute clerical tasks.
3. `local_workforce_non_authority`: Verifies that local jobs do not carry capability/mutation authority.
4. `hardware_admission`: Verifies that hardware capability is assessed before a model is admitted.
5. `canonical_intelligence_hiring`: Verifies the flow from HiringBroker to a hired model.
6. `privacy_gated_cloud_use`: Verifies that private/secret information is routed strictly locally and cloud calls are bounded.
7. `expert_trajectory_provenance`: Verifies that expert trajectories capture valid context.
8. `skill_applicability`: Verifies that skills are appropriately matched to tasks.
9. `skill_re_escalation`: Verifies that a skill can safely escalate back to a higher-level planner or human.
10. `maintenance_finding_persistence`: Verifies that durability of maintenance findings is maintained across runs.
11. `maintenance_canonical_repair`: Verifies that repair jobs leverage `MissionContract`.
12. `maintenance_rescan_resolution`: Verifies that maintenance jobs must be resolved via successful rescans.

Required failure demonstrations:
- Capability replay refused.
- Out-of-scope edit refused.
- Local model unavailable.
- Cloud unavailable.
- Secret-classified task blocked from cloud.
- Skill applicability mismatch.
- Verification failure prevents promotion.
- Scanner still detects issue after green tests.
- EmergencyStop blocks queued maintenance work.
- Mirror refuses malformed events.

### [NEW] `tests/test_r15_runtime_proof.py`
This test will execute `run_r15_runtime_proofs()` and assert that:
- All required R15 proofs are present.
- All required R15 proofs pass successfully.
- No dummy data or state leaks out of the sandbox.

### Verification Plan
- `pytest tests/test_r15_runtime_proof.py -v` will execute the proofs.
- Verify that the failures correctly throw their intended domain exceptions.
- The entire CI suite will be executed to guarantee no regressions.
