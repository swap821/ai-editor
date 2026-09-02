# Wave 3 — seven more green, and five refusals worth more than the promotions

**Date:** 2026-09-01
**Evaluated commit:** `3f7e1edebf6a8c784d7fdd54c86d6943ab23bfc1`
**Result: 23 green / 31 yellow → 30 green / 24 yellow.**

Organs restored: **8, 11, 15, 17, 21, 22, 26.**

Twelve organs were searched. Five were **not** promoted, and those results are
the more useful half of this wave.

## What was promoted

| Organ | C3 | C4 | C5 |
| --- | --- | --- | --- |
| 8 Action Broker | `test_constitution_digest_survives_the_real_store_round_trip` | `test_same_token_rejects_every_changed_binding_field` | `test_production_broker_issues_and_consumes_exact_capability` |
| 11 Turn Coordinator | N/A → `TurnCoordinatorAuthority` | N/A → `TurnCoordinatorAuthority` | `test_two_pause_chain_replays_convo_tail_and_teaches_one_skill` |
| 15 Evidence & Verification | `test_verification_durable_persistence_and_reload` | `test_is_authoritative_rejects_forged_results` | `test_stdout_spoof_cannot_forge_strong` |
| 17 Cortex Observation Bus | `test_crash_between_append_and_dispatch_replays_on_restart` | `test_tampered_payload_is_detected_on_read` | `test_retention_boundary_requires_snapshot_rebuild` |
| 21 Queen Council Orchestrator | `test_state_persists_across_instances` | N/A → `MissionTransitionJournal` | `test_council_orchestrator_blocks_protected_allowed_file_before_worker` |
| 22 V1 Release Declaration | N/A → `ReleaseDeclarationAuthority` | N/A → `ReleaseDeclarationAuthority` | `test_release_declaration_reports_blocked_executor_and_authority_layers` |
| 26 Emergency Stop (hard-wiring) | N/A → `EmergencyStopController` | N/A → `AuditLoggerAuthority` | `test_capability_authority_consume_refuses_when_stop_engaged` |

All 20 well-formed pytest nodes were executed and confirmed passing before being
written into the ledger; all seven N/A symbols were resolved through the real
`na_cite_validator`. No test was written for this wave.

The N/A instruction was tightened after wave 2, where two proposals justified a
discharge by the cited symbol merely existing. This wave's discharges each name
the organ that actually owns the property — organ 42's `MissionTransitionJournal`
for the council path (the call site's own comment reads `(organ 42)`), organ 19's
`EmergencyStopController` for the durable latch (per the hard-wiring authority's
own docstring), organ 4's `AuditLoggerAuthority` for the boundary modules.

## Two organs whose ledger prose is wrong in code

**Organ 6 (Edge Trust Boundary) — C4 could not be honestly cited.** Its verdict
claims the organ "relies on audit + token-rotation stores". Read end to end,
`aios/interfaces/http/edge_security.py` never calls `aios/security/audit_logger.py`
— its only logging is a stdlib `logger.warning(...)` — and the token-rotation
table it reads (`api_token_store.py`) stores a plain
`current_token_digest`/`previous_token_digest` UPSERT row with no hash chain and
no verify method. **The claim is not true of the code**, so no tamper-evidence
test was cited for a data path that has none. Organ 6 stays yellow. Closing it
needs either an audit-chain write on edge-trust rejection, or a verify/HMAC
method on the rotation row, plus a test that tampers a row and asserts detection.

**Organ 12 (Worker Foundry) — no durable owner exists.** `WorkerFoundry` and
`WorkerScheduler` hold only in-memory dicts and heaps with zero file or DB I/O,
and production wiring (`aios/api/deps.py::get_worker_foundry`) constructs the
foundry with no `bus=` and no `lifecycle_observer=`, so **nothing durably records
worker admission or lifecycle in production at all.** `CortexBusAuthority`'s
content-digest chain is real and tamper-evident but is not wired into that
factory, so citing it as this organ's C4 owner would misdescribe the live wiring.
Organ 12 needs a production-wiring decision, not a citation.

Organs 13 and 14 likewise returned no proof for one condition each and stay
yellow.

## Organ 20 — dropped by hand, and why it matters

The search proposed for C5:

```
frontend/src/superbrain/lib/livingMirrorRegistry.test.ts::rejects malformed known events before read-model mutation or reaction
```

A vitest test whose **name contains spaces**. The gate's referent pattern is
`((?:tests|frontend)/….(py|tsx?|jsx?))::([\w\[\]\-]+)` — it would have matched
`…livingMirrorRegistry.test.ts::rejects` and stopped, producing a citation that
*looks* resolvable and points at nothing. It also cannot be verified on a machine
without the vitest JUnit report.

This is exactly the failure the bar exists to catch, and it surfaced only because
every node is executed before it is written. Organ 20 stays yellow.

## Verification

```
$ python -m aios.launcher organ-check --strict
GAGOS organ ledger: 30/54 green (CONFORMANT)
  no ledger violations

$ python scripts/verify_organ_contracts.py
organs: 54 total, 30 green, 24 yellow
no contract violations -- ledger and manifest are self-consistent

$ python scripts/verify_organ_twelve_conditions.py --enforce-condition-proofs --allow-unexecuted-frontend
running 82 referenced test file(s) for C6/C7/C9 ...
test outcomes: 82 file(s), 2014 passed, 0 failed
live evidence rows resting on operator attestation: 0
C3/C4/C5 greens without a mechanical proof: 0
green mechanical failures: 0
exit=0
```

One node in the searched set skips on this platform
(`test_unenrolled_and_symlinked_projects_are_rejected` — symlinks unavailable on
Windows). It belongs to organ 14, which is staying yellow regardless, so no
promotion rests on it.

## Remaining: 24 yellow

Named blockers, none of which are citation work:

- **44** — cloud Gemini cohort plus operator attestation. Not agent-reachable.
- **52** — one Docker-capable run; CI has already proven the node, but
  `executor-junit` is not uploaded so that evidence cannot be replayed locally.
- **6** — needs real tamper-evidence on the edge-trust data path (see above).
- **12** — needs a production-wiring decision about who durably owns worker
  lifecycle (see above).
- **54** — `aios/operations/recovery.py::verify_backup` raises on a hash mismatch
  and no test exercises that path. Still the one confirmed piece of genuinely new
  authoring.

The other 19 are ordinary citation work of the kind waves 1-3 have been doing.
