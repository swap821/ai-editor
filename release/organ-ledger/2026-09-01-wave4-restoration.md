# Wave 4 — twelve more green, and the point where citation work runs out

**Date:** 2026-09-01
**Result: 30 green / 24 yellow → 41 green / 13 yellow.**

Organs restored: **27, 28, 29, 30, 31, 32, 36, 38, 39, 43, 54.**
Organ 40 was promoted and then held back; see below.

This wave finishes the reachable citation work. What remains is not
citation-shaped, and the categories below matter more than the count.

## Organ 54 — the only genuinely new test in this campaign

Waves 1-3 wrote no tests at all; every green rested on a proof that already
existed and had simply never been cited. Organ 54 was the one confirmed
exception, identified back in wave 1's analysis:
`aios/operations/recovery.py::verify_backup` re-hashes every archive member and
raises `RecoveryError("backup hash mismatch: …")`, and **nothing exercised that
path**.

Two tests now do, in `tests/test_operations.py`:

* `test_a_tampered_archive_member_is_detected_by_its_content_hash` — rebuilds the
  archive with altered bytes while keeping the **original manifest**, so the
  manifest still lists the old digest. Tampering the way an attacker must. A test
  that edited the manifest too would only prove two attacker-controlled values
  agree with each other.
* `test_a_member_added_after_the_manifest_is_refused` — the other half: a file
  smuggled in that the manifest never declared, which a per-file hash loop alone
  would wave through.

**Mutation-checked in both directions.** With `verify_backup`'s digest
comparison and member-set check disabled, both fail; restored, both pass; and
`recovery.py` is byte-identical afterward. A test written to close a gap is
worthless if it cannot detect the gap reopening.

Organ 54's C3 and C5 already existed, so only C4 needed authoring — exactly what
wave 1's analysis predicted.

## Eleven promoted on existing proofs

27, 28, 29, 30, 31, 32, 36, 38, 39, 43 (plus 54 above). All 33 located pytest
nodes were executed and passed with **no skips**; all nine N/A symbols resolved
through the real `na_cite_validator`.

The resumed search agents were markedly more careful than the first attempt —
they ran candidate tests themselves before proposing, and twice refused rather
than guessed (see organ 14 and organ 20 below).

## Organ 40 — promoted, then held back

It passed C3/C4/C5, then failed **C7**:

```
organ 40 failed mechanical re-read: [('C7', 'no integration_tests proved anything
here (unverified: tests/test_executor_integration.py (all 4 skipped))')]
```

Its ONLY integration suite gates on `AIOS_EXECUTOR_INTEGRATION` and skips all
four tests without Docker, so the gate correctly reports nothing was proven.
`ci.yml` documents this exact fact and solves it by running that file inside the
container and mounting out `executor-junit.xml` for the gate to merge.

Held back rather than promoted, because organ 52 was held for the identical
reason in wave 1 — promoting 40 while holding 52 would be incoherent. Its
C3/C4/C5 work is kept.

**One Docker-capable run now unblocks organs 40 and 52 together**, which makes it
the highest-leverage remaining action.

## The structural finding: frontend organs cannot satisfy C5 at all

Organs **20, 48, 49 and 51** are all blocked on C5 for the same reason, and it is
not a missing proof.

Their tests are vitest `it('...')` with human-readable names, and **every name
contains spaces** — e.g. `rejects malformed known events before read-model
mutation or reaction`. The gate's referent pattern is:

```
((?:tests|frontend)/….(py|tsx?|jsx?))::([\w\[\]\-]+)
```

The part after `::` admits only word characters, hyphens and brackets. Citing any
vitest test therefore matches the first word and stops, producing a referent that
looks resolvable and points at nothing. C5 has no N/A escape, so these four
organs are **unciteable by construction**.

This is a gap in the contract, not in the organs. It needs an operator decision:
widen the pattern (e.g. allow a quoted name), or accept that frontend-facing
organs cap at yellow. Their C3/C4 N/A discharges were located and resolve
(`LivingMirrorAuthority`, `TruthfulMirrorAuthority`,
`ApprovalDecisionSurfaceAuthority`, `SovereignHeartbeatSurfaceAuthority`), so C5
is the sole obstacle.

## Three organs whose ledger prose is not true of the code

Reported rather than papered over. None is citation work.

* **Organ 13** — `execute_registered_operation_in_service` does compute
  before/after digests and reject mismatches, but **no test anywhere calls it**;
  grep across `tests/` returns nothing. The tamper tests that exist exercise a
  separate parallel implementation in `aios/application/executor/service.py` or a
  hand-mocked fake. Not an N/A case either: the file contains real, untested
  integrity logic.
* **Organ 14** — `for_mission()`'s own docstring claims it returns the durable
  lease "including after restart" via an on-disk fallback, but every test reuses
  the **same manager instance**, so the in-memory cache always answers and the
  disk-recovery path never runs. The class plainly owns durable state, so N/A
  would be false.
* **Organ 6** (from wave 3) — its C4 claims reliance on "audit + token-rotation
  stores", but `edge_security.py` never calls the audit logger and the rotation
  table has no chain and no verify method.

## Verification

```
$ python -m aios.launcher organ-check --strict
GAGOS organ ledger: 41/54 green (CONFORMANT)
  no ledger violations

$ python scripts/verify_organ_contracts.py
no contract violations -- ledger and manifest are self-consistent
```

## What remains: 13 yellow, in four honest categories

| Category | Organs | What it needs |
| --- | --- | --- |
| One Docker-capable run | 40, 52 | Run the executor integration suite with a real daemon, or commit a CI-generated phase-5 artifact |
| Gate cannot express the proof | 20, 48, 49, 51 | Operator decision on the referent pattern vs. vitest names |
| Code/wiring gaps, not citations | 6, 12, 13, 14 | Real integrity or persistence work, named above |
| Operator-only | 44 | Cloud Gemini cohort plus personal attestation |
| One condition unproven | 34, 53 | Ordinary work; no proof located this pass |

Organs 1, 4 and 5 remain green on the operator's signature rather than on current
evidence — re-attesting them is still an operator-only act.
