# Wave 1 — seven organs returned to an honest green

**Date:** 2026-09-01
**Evaluated commit:** `8d9964eaba2e69462253c83eda757ae8ad43a3bc`
**Result: 5 green / 49 yellow → 12 green / 42 yellow.**

Follow-on to `2026-09-01-live-evidence-recount.md`, which demoted 49 organs for
having no resolvable C3/C4/C5 referent and set
`greens_without_condition_proofs` to 0 — arming the gate so that any organ
promoted from here must name a proof that runs and passes in the gate's own
invocation.

Organs restored: **9, 19, 33, 41, 42, 47, 50.**
Organ 52 was prepared, then deliberately held back — see below.

## Why these, and why it was cheap

The recount's finding was that the ledger's problem was *citation*, not absence:
the tests were largely already written against this contract — several docstrings
literally say "Condition 3" or name the organ — and the ledger simply never cited
them by node id. Organ 42 had all three proofs in its own suites. Organs 42 and
52 had theirs in `tests/test_organ_authority_owners.py`, a file their own rows
did not list.

**No test was written for this wave.** Every referent below already existed and
was executed and confirmed passing *before* being written into the ledger — 18
nodes in total. Under an armed gate that ordering is not ceremony: a citation
that does not execute fails the build.

## What each organ now cites

| Organ | C3 | C4 | C5 |
| ---: | --- | --- | --- |
| 9 Exact Capability | `test_constitution_digest_survives_the_real_store_round_trip` | `test_constitution_digest_mismatch_is_rejected_outright` | `test_a_constitution_bound_capability_needs_a_wired_authority` |
| 19 Emergency Stop | `test_emergency_clear_capability_is_bound_single_use_and_restart_durable` | N/A-BY-DESIGN → organ 4's chain | `test_failed_stop_hook_keeps_latch_engaged_and_reports_failure` |
| 33 Model Passport | `test_a_passport_survives_a_restart_because_the_row_does` | (already resolved) | `test_unknown_cost_remains_unknown_not_zero` |
| 41 Promotion/Rollback | `test_receipt_survives_the_real_durable_store_round_trip` | (already resolved) | `test_apply_or_smoke_failure_restores_exact_checkpoint` |
| 42 Recovery/Resumption | `test_the_chain_survives_a_restart` | `test_an_edited_transition_is_detected` | `test_the_recovery_report_never_raises_on_a_tampered_journal` |
| 47 Read-Model | N/A-BY-DESIGN (owns no store) | N/A-BY-DESIGN (integrity is upstream) | `test_provider_health_projection_unknown_budget_is_unavailable_not_zero` |
| 50 Provenance Surface | (already resolved) | `test_durable_tracker_detects_tampered_row` | `test_durable_load_failure_surfaces_unavailable_not_empty_history` |

## Organ 52 — prepared, then held back

Its C3/C4/C5 referents are in place and resolve, and they are kept in the ledger.
It is **not** promoted, because its pre-existing **C10** evidence row cites
`tests/test_executor_integration.py::test_trace_context_reaches_the_isolated_container`,
which needs a real Docker daemon. Docker was not running on the machine that
prepared this wave, so the verifier recorded:

```
organ 52 failed mechanical re-read: [('C10', 'cited test
tests/test_executor_integration.py::test_trace_context_reaches_the_isolated_container
did not run and pass')]
```

and organ 52's own phase 5 artifact consequently read
`survives mechanical adversarial re-read: no`.

That row is **untouched by this wave** (zero occurrences in the diff) and was
passing when organ 52 was green before the recount, which demoted it for
C3/C4/C5 alone. CI is expected to clear it: the `release-authority` job runs that
file inside the container, mounts out `executor-junit.xml`, and the verifier step
in the **same job** merges it via `--extra-junit`. ci.yml's own comment describes
exactly this — *"Emitting JUnit from INSIDE the container and mounting it out is
what lets the gate see the run that actually happened, rather than lowering the
bar for an organ that genuinely passes."*

It is still held back, because "CI will probably clear it" is not a verification,
and promoting an organ whose own proof artifact records `no` would ship precisely
the internal inconsistency this campaign exists to remove. Its blocker names the
condition for promotion: that node observed passing in the gate's own run. Twelve
verified greens is the better number than thirteen with an asterisk.

## Judgment calls, stated rather than buried

**Organ 9's C5 was wrong, and is corrected rather than restated.** Its previous
verdict cited `IdentityDegraded`, which is raised only in organ 24's suite and
never covered organ 9 at all. The new verdict says so in the ledger text.

**Three N/A-BY-DESIGN discharges among the promoted organs, each with a symbol
that resolves.** Organ 19's stop state is a single mutable latch row, not an
append-only chain, and the tamper-evident ledger recording stop events is organ
4's. Organ 47 is a pure projection that owns no store at all, so it has neither
durable state of its own nor a journal. Asserting a chain for either would invent
a property the organ does not have — the failure mode this bar exists to catch.
Each cite was resolved through the real `na_cite_validator`, not by inspection.

**No C5 was discharged as N/A.** The contract grants no such clause for C5 and
none was invented; all seven cite a passing test.

**`requires_live_evidence` is false on all seven**, under the narrowed definition
recorded in the recount memo: true only when a proof needs something the gate's
own pytest run cannot provide. These are proven by nodes that re-execute on every
push — stronger than a probe stamped at an older commit, and the flag's literal
semantics (evidence at the *evaluated* commit) are unsatisfiable while CI never
writes the ledger.

## Verification

```
$ python -m aios.launcher organ-check --strict
GAGOS organ ledger: 12/54 green (CONFORMANT)
  no ledger violations

$ python scripts/verify_organ_contracts.py
organs: 54 total, 12 green, 42 yellow
no contract violations -- ledger and manifest are self-consistent

$ python scripts/verify_organ_twelve_conditions.py --enforce-condition-proofs --allow-unexecuted-frontend
running 36 referenced test file(s) for C6/C7/C9 ...
test outcomes: 36 file(s), 896 passed, 0 failed
live evidence rows resting on operator attestation: 0
C3/C4/C5 greens without a mechanical proof: 0
green mechanical failures: 0
exit=0
```

`--allow-unexecuted-frontend` is the flag CI itself passes; without it organ 50's
frontend suites report unexecuted because they need vitest, which is an artifact
of the local invocation rather than a property of the organ.

## Reproduce

```bash
python -m aios.launcher organ-check --strict
python scripts/verify_organ_contracts.py
python scripts/verify_organ_twelve_conditions.py --enforce-condition-proofs --allow-unexecuted-frontend
```
