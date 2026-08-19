# Organ 23 — the last yellow earns green

2026-08-19. Ledger goes **54 green / 0 yellow**.

## The blocker was satisfied a day before the organ was ready

Organ 23's single blocker read:

> Phase 6 gate — organ 23 stays yellow until every below-organ is honestly green

Organ 44 went green earlier the same day (#254), which satisfied that condition
exactly. **It did not make the organ green.** Flipping it then would have failed
three separate gates:

| gate | state before this change |
|---|---|
| C10 | **zero** `live_evidence` rows — a green must hold `proof_level=live` evidence |
| C11/C12 | `last_verified_sha` was `None` |
| ratchet | C3/C4/C5 named no referent, so `greens_without_condition_proofs` would go 46 → **47**, over budget |

A blocker's condition being met is not the same as the organ having done the
work. The work is below.

## C3, C4, C5 earned referents — the ratchet did not move

The budget file is explicit: the number *"may only go DOWN … never raise it to
make a failing gate pass"*, and C5 *"must be positively proven with a named test;
C5's definition carries no N/A-BY-DESIGN clause, and inventing one would be the
exact failure mode this gate exists to catch."*

None was invented. Every citation is a test in organ 23's own suite, which the
gate already runs because the file is in `focused_tests`:

* **C3** — *durable state survives process restart.* Organ 23's durable state is
  the ledger and manifest on disk, and its authority is a **script**: every
  invocation is a fresh process that re-reads both and re-derives its verdict,
  holding nothing between runs.
  → `test_verify_organ_contracts_passes_on_the_shipped_ledger_and_manifest`
  (the real script, the real on-disk artifacts, no fixtures)
* **C4** — *tamper-evidence / integrity chain.* Not incidental here; it is the
  organ's whole job.
  → `test_organ_proof_manifest_hash_pins_the_ledger`, with
  `test_validate_manifest_rejects_wrong_ledger_hash` and
  `test_validate_manifest_rejects_a_stale_tracked_file_hash` — the chain is
  proven by what it **refuses**, not by what it accepts.
* **C5** — *fail-safe reporting: unavailable rather than a plausible zero.*
  → `test_phase4_honesty_rejects_silent_organs_without_named_reason` and
  `test_green_with_known_blockers_fails` — the second is the rule that kept
  organ 23 itself yellow until today.

`greens_without_condition_proofs` stayed at **46** and
`.aios/state/condition_proof_budget.json` was not touched.

## C10 — evidence anyone can re-derive, with no attestation

Unlike organ 44, organ 23 needs **no** `OPERATOR-ATTESTED` row:

* **CI run
  [32246180129](https://github.com/swap821/ai-editor/actions/runs/32246180129)** —
  `conclusion=success`, `head_sha=abf7346d`, **`release-authority` success**. That
  job runs `verify_organ_contracts.py` and `verify_organ_twelve_conditions.py`
  against the shipped ledger and manifest, so it re-derives every green claim in
  this file *including this one*. The organ whose job is checking release
  conformance is proven by conformance being checked, at a commit, by a machine
  nobody here controls.
* **Test node** — the C3 citation, which the gate runs and must pass.

`last_verified_sha` is `abf7346d`, the same commit, so the stamp and the cited
run describe one thing rather than merely both being well-formed.

## Three tests changed, and why none of it is laundering

Reaching 54/54 broke three tests that had been sourcing their fixtures from the
real ledger's colour distribution. In each case the property under test was never
about a yellow existing — the fixture had simply run out.

**`test_launcher_organ_check_strict_fails_until_all_organs_green`** asserted
`organ_check(strict=True) == 1` and `all_green is False`. Its name carried its own
expiry. Flipping the constants to `0`/`True` would have produced a test just as
stale the next time an organ is honestly demoted — and a demotion is exactly when
it needs to still mean something. It is now
`test_launcher_organ_check_strict_agrees_with_the_ledger`, asserting strict passes
**iff** the ledger has no yellow. Strictly stronger, and true in both directions.

**`test_check_fails_when_the_ledger_moves_ahead_of_the_prose`** did
`next(r for r in moved if r["status"] != "green")` and raised `StopIteration`. It
now flips an organ *to* yellow when none exists; the property is that the renderer
**reads `status`**, which never depended on which colour was scarce.

**`test_yellow_rows_carry_their_real_residual`** asserted *"expected at least one
yellow organ with a blocker"*. It now builds a **synthetic** yellow row so the
renderer is exercised whatever the shipped ledger looks like, and still checks
every real yellow when one exists. Verified non-vacuous: the synthetic residual
appears in the rendered prose, a `### Yellow (1)` section renders, and changing
the residual changes the output.

The common lesson: **a guard that can only fire while the repo is imperfect stops
guarding the moment it succeeds.**

## Blast radius, checked before the flip

`all_green` has exactly one consumer — `aios/launcher.py:360`, reached only via
the explicit `organ_check` CLI subcommand. Nothing auto-enables at 54/54. The
`42 green / 12 yellow` strings in `scripts/finalize_*_checkpoint.py` are dated
one-off checkpoint writers, not gates, and are left alone as the historical
records they are.

## Verification

* `_condition_proof_failures` (naming **and** execution) → none
* `_evidence_reference_failures` → none; **0** rows resting on attestation
* `verify_organ_contracts.py` → 54 organs, **54 green / 0 yellow**, no violations
* ledger sweep → **221 passed / 0 failed**
* build order `build_organ_ledger_doc.py` → `build_release_manifest.py`; all
  hash-pinned files LF (0 CRLF)
* ratchet **46**, budget file untouched

The twelve-condition verifier in `release-authority` is the judge of this claim,
not its author.
