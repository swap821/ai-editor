# Wave 2 — eleven more organs returned to an honest green

**Date:** 2026-09-01
**Evaluated commit:** `1aaa6fa6b2badf5dbfd98bce9bfe59a621364aa0`
**Result: 12 green / 42 yellow → 23 green / 31 yellow.**

Organs restored: **7, 10, 16, 18, 23, 24, 25, 35, 37, 45, 46.**
Organ 52 remains held — see below.

Continues `2026-09-01-wave1-restoration.md` under the same rule: the C3/C4/C5
proof gate is armed at budget 0, so every promotion must cite a node that runs
and passes in the gate's own invocation.

## Two populations

**Organs 23 and 46 needed no proof work at all.** They were demoted by the
recount for *stale live evidence* under the old broad `requires_live_evidence`
reading, not for missing referents — their C3/C4/C5 already resolved. Under the
narrowed definition their flag is false, because every referent AND every
live-evidence citation on both is an in-gate pytest node re-executed on each
push. Verified before promoting: 15 referents plus 10 evidence-cited nodes, all
passing.

**The other nine needed citations located.** As in wave 1, the tests already
existed and the ledger had never named them.

| Organ | C3 | C4 | C5 |
| --- | --- | --- | --- |
| 7 Policy Kernel | `test_durable_rate_limiter_coordinates_workers_and_reset` | N/A → `AuditLoggerAuthority` | `test_request_authority_unknown_route_is_fail_closed` |
| 10 Mission Authority | `test_mission_survives_restart` | N/A → `RecoveryResumptionAuthority` | `test_testing_queen_failure_changes_king_report_to_rollback` |
| 16 Promotion Authority | `test_receipt_survives_the_real_durable_store_round_trip` | *(already resolved)* | `test_forged_lease_cannot_reach_promotion_callback` |
| 18 Memory Authority | `test_council_memory_records_deliberation_as_advisory_evidence` | `test_changed_proposal_and_missing_lineage_fail_closed` | `test_recall_trust_preserves_unverified_and_advisory_status` |
| 23 Release Conformance | `test_verify_organ_contracts_passes_on_the_shipped_ledger_and_manifest` | `test_organ_proof_manifest_hash_pins_the_ledger` | `test_phase4_honesty_rejects_silent_organs_without_named_reason` |
| 24 Human Sovereign Identity | `test_durable_store_validates_cookie_hash_after_restart` | `test_yellow_route_challenges_before_mutation_and_binds_exact_payload` | `test_degraded_identity_store_returns_503_not_a_bare_500` |
| 25 Constitutional Kernel | `test_an_activated_amendment_reaches_every_authority_and_survives_restart` | `test_cas_rejects_an_activation_whose_predecessor_moved` | `test_governance_projection_is_honestly_unavailable_when_unauthenticated` |
| 35 Local Clerk Runtime | `test_registry_preserves_configuration_across_restarts` | *(already resolved)* | `test_an_unqualified_model_escalates_rather_than_being_trusted` |
| 37 Local Model Qualification | `test_registry_preserves_configuration_across_restarts` | *(already resolved)* | `test_schema_retry_is_bounded_and_still_reports_honest_failure` |
| 45 Amendment Authority | `test_rollback_restores_the_exact_predecessor_and_survives_restart` | `test_tampered_proposal_row_is_detected_at_read_time` | `test_ratify_amendment_refuses_every_capability_defect` |
| 46 Constitutional Learning | `test_the_drafted_proposal_is_independently_fetchable_and_still_unratified` | `test_changes_swapped_after_ratification_are_refused` | `test_a_passing_screen_ships_its_own_limits_so_nobody_reads_it_as_safe` |

**No test was written for this wave either.** All 22 located nodes were executed
and confirmed passing *before* being written into the ledger, and all four
proposed N/A symbols were resolved through the real `na_cite_validator`.

## Proposals that were rejected rather than applied

The citation search was run by parallel agents, and three of its proposals were
**not** taken:

Organs **16, 35 and 37 already had a resolving C4**. The search proposed
replacing those working verdicts anyway — two of them with the reasoning
*"N/A-BY-DESIGN against the confirmed class"*, which is circular: it justifies
the discharge by the fact that the cited symbol exists, not by the organ lacking
a journal. Rewriting a verdict that already works adds risk for no gain, so only
the genuinely missing conditions were filled. The apply step computes each
organ's real gap with the gate's own predicate and touches nothing else.

The two N/A discharges that WERE accepted are grounded in ownership, not
convenience: organ 7's kernel keeps mutable counters and its auto-grants are
chained by organ 4's audit logger; organ 10's mission transitions are journaled
by organ 42's `RecoveryResumptionAuthority`, which wave 1 already proved
tamper-evident.

## Organ 52 — still held, for the second time

CI has now *proven* its Docker-dependent C10 node: the merged wave-1 run executed
`tests/test_executor_integration.py` in-container (4 passed) and emitted the
`executor-junit.xml` the gate merges. That satisfies the promotion condition
written into its blocker.

It is still not promoted, because `executor-junit` is **not uploaded as a CI
artifact** — it is produced and consumed inside the same job — so that evidence
cannot be pulled down and replayed here. Promoting it would mean committing a
ledger this machine's own gate rejects (`green mechanical failures: 1`) and a
phase 5 artifact reading `survives mechanical adversarial re-read: no`. CI
proving something is not the same as having verified it. One run on a
Docker-capable machine closes it.

## Verification

```
$ python -m aios.launcher organ-check --strict
GAGOS organ ledger: 23/54 green (CONFORMANT)
  no ledger violations

$ python scripts/verify_organ_contracts.py
organs: 54 total, 23 green, 31 yellow
no contract violations -- ledger and manifest are self-consistent

$ python scripts/verify_organ_twelve_conditions.py --enforce-condition-proofs --allow-unexecuted-frontend
running 68 referenced test file(s) for C6/C7/C9 ...
test outcomes: 68 file(s), 1737 passed, 0 failed
live evidence rows resting on operator attestation: 0
C3/C4/C5 greens without a mechanical proof: 0
green mechanical failures: 0
exit=0
```

## Remaining: 31 yellow

Organ 52 (needs one Docker-capable run) and organ 44 (cloud Gemini cohort plus
operator attestation, not agent-reachable) are the two named exceptions. The
other 29 follow the same recipe; C4 remains the biggest gap, and organ 54's
archive-tamper test is still the one confirmed piece of genuinely new authoring:
`aios/operations/recovery.py::verify_backup` raises on a hash mismatch and no
test exercises that path.
