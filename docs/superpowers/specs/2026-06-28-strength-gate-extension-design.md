# Extend the verification-strength gate to the remaining promotion sites

Date: 2026-06-28
Status: Approved (operator; 3 sites, exclude mistake)
Branch target: `council-runtime-v01` → fast-forward `master` on green

## Goal

Phase 1 keystone, completion pass: make ALL test-backed learning calibrate on
verification strength, not just skills. A weak green must not promote a swarm
pattern, calibrate the router/planner, or advance curriculum mastery.

## Scope

Three sites that share the "calibrate on a test-backed turn outcome" model and
adopt the existing `meets_promotion_floor` (floor STRONG):
1. `aios/agents/swarm_patterns.py` — `record_attempt` (caller `main.py:3023`).
2. `aios/memory/development.py` — verified outcomes that calibrate router/planner.
3. `aios/memory/curriculum.py` — `record_matching` mastery progress.

**Excluded: `mistake`→planner-confidence.** A mistake lesson is confirmed when the
exact failed COMMAND succeeds on retry (`tool_loop_helpers.confirm`, an
exit-code-only command re-run) — inherently WEAK by the taxonomy. Gating it on the
STRONG floor would essentially never confirm a lesson and would break mistake
learning. Its evidence model is different; if ever gated, it needs command-aware
strength at the confirm point and a WEAK/MEDIUM floor — a separate slice.

## Design

### Shared
`strength` is computed once at the top of the chat/generate recording closure via
`strength_from_text(evidence)` (already used for skills) and reused for all sites.

### 1. swarm_patterns (mirror the skills gate)
`record_attempt(goal, subtasks, *, success, strength=VerificationStrength.STRONG)`:
- `eligible = success and meets_promotion_floor(strength)`; a below-floor success
  increments a new `weak_success_count` column, never the promotion `success_count`
  (so it can't reach `verified`).
- Stamp `verification_strength` (latest success).
- Schema: two additive columns on `swarm_patterns`
  (`weak_success_count INTEGER NOT NULL DEFAULT 0`, `verification_strength TEXT`)
  via the `db._migrate` ALTER-if-missing pattern (a `swarm_additions` dict).
- Caller `main.py:3023` passes `strength=strength`.

### 2. development (reuse the existing exclusion)
At the recording site, downgrade the development outcome:
`dev_outcome = "unverified" if (outcome == "verified_success" and not
meets_promotion_floor(strength)) else outcome`, and pass `dev_outcome` to
`development_tracker.record(...)`. `unverified` events are already excluded from
`relevant_success_rate` and `model_task_success_rates`, so a weak green no longer
calibrates the router/planner. `passed` (used by skills/swarm/curriculum) is
UNCHANGED — only the development record is downgraded. No schema/query change.

### 3. curriculum (no hollow mastery)
`record_matching(prompt, *, passed, evidence)` derives `strength_from_text(evidence)`;
a below-floor pass still increments `attempts` but contributes **0** to `successes`
(`successes += 1 if (passed and meets_promotion_floor(strength)) else 0`). So a weak
green is recorded as an attempt but never advances mastery / unlocks the next level.
Evidence-format validation is unchanged.

## Error handling / fail-closed
- Unparseable strength token → `NONE` (already), below floor → ineligible.
- Default `strength=STRONG` on `swarm_patterns.record_attempt` keeps existing
  callers/tests byte-identical; only the live caller passing real strength gates.
- Missing columns on older DB → added on init.

## Testing
- swarm_patterns: 3 WEAK successes → stays `candidate`, `success_count == 0`,
  `weak_success_count == 3`; 3 STRONG → `verified`; default STRONG preserved.
- development: a `verified_success` with WEAK strength is recorded `unverified`
  (asserted via `model_task_success_rates`/`relevant_success_rate` excluding it);
  STRONG calibrates.
- curriculum: a weak `[VERIFY PASS]` increments attempts but not successes (no
  mastery); a STRONG pass advances mastery.
- Existing swarm/development/curriculum suites stay green.
- Full backend suite + 85% floor; frozen spine untouched. Then Verifier-owned
  adversarial review (try to make a hollow green calibrate any of the 3).

## Adversarial review outcome (Verifier-owned) — fixes folded into this slice

The Phase-1 adversarial review returned `invariant_holds = false` with three
findings. All were fixed before landing (the operator's standing "fix any HIGH,
then land" pattern); they share the evidence → strength → calibration path this
slice gates, so they land together rather than as a follow-up.

1. **[HIGH] Hollow-STRONG from a zero-test run (a regression introduced mid-slice).**
   A mid-slice experiment dropped the `passed_count > 0` requirement from
   `derive_strength` STRONG, on the theory that a runner's exit code is
   authoritative. That mints STRONG for a recognized runner that asserted
   NOTHING — `jest --passWithNoTests`, `vitest --passWithNoTests`, `pytest` over
   an empty path, a no-op `npm test` wrapper — all exit 0 with 0 passes.
   **Reverted.** STRONG again requires `_is_test_runner(command) and passed_count
   > 0 and failed_count == 0`. The command-aware program-position check is the
   *spoof* defense (`echo "5 passed"` stays WEAK); `passed_count > 0` is the
   *hollow-run* defense (a real runner that asserted nothing stays WEAK). The
   brittleness that motivated the experiment (a fake/real verify producing exit 0
   with no parseable "N passed") is a test-fixture artifact, fixed by giving the
   affected test a runner that emits realistic counted output — NOT by weakening
   the taxonomy. Regression test: `test_test_runner_that_asserted_nothing_is_not_strong`.

2. **[HIGH] Forgeable evidence — provenance gate.** The chat/generate evidence
   collector appended ANY tool-result whose output started with `[VERIFY PASS/FAIL]`,
   so a model running a GREEN `echo "[VERIFY PASS] 5 passed (strength=STRONG)"`
   forged authoritative evidence and a STRONG strength, laundering a hollow turn
   into calibration. **Fixed:** the collector now requires trusted provenance —
   `ev.get("tool") == "verify"` (the model's `verify` and the forced
   `autoverify-*`, the only emitters of real verifier evidence) — in addition to
   the string prefix. (Predates this slice, but it defeats the gate's whole
   premise, so it is fixed here.) Regression test:
   `test_forged_verify_evidence_from_non_verify_tool_does_not_calibrate`.

3. **[MEDIUM] turn_strength laundering.** `turn_strength` was the strength of the
   LAST `[VERIFY PASS]` across all evidence, so a model could append a STRONG
   advisory verify after a weak forced auto-verify to raise the turn. **Fixed:**
   strength is now tracked per target (`auto_strengths`/`verify_strengths`) and
   the turn strength is the **weakest authoritative passing target** (auto-verify
   if any ran, else the model's own verify) — one strong target cannot mask a weak
   one, and an advisory verify cannot raise the authoritative auto-verify. The
   authoritative strength is also passed into `curriculum.record_matching(...,
   strength=...)` so mastery can't be laundered via the evidence text either.

## Second adversarial re-review (Verifier-owned, 24 agents) — 2 HIGH fixed, 1 MEDIUM surfaced

A full re-review of the landed fixes (commit `426defe`) returned
`invariant_holds = false` — the fixes still leaked. Two HIGH live-path forgeries
fixed here; one MEDIUM grandfathering decision surfaced to the operator (two other
findings correctly refuted: npm/cargo wrapper runners are gateway-RED hence not
live-reachable; the configurable WEAK/MEDIUM floor requires the operator to
deliberately disable their own keystone).

1. **[HIGH] `_is_test_runner` PAIR-scan was not program-anchored.** The bare-token
   check was anchored to the program position, but `_has_pair` scanned EVERY token
   offset, so a GREEN `echo -m pytest 1 passed` / `echo go test :: 3 passed` /
   `echo npm test 7 passed` minted `strength=STRONG` (the model controls echo's
   stdout → `passed_count=1`), passed the provenance gate (it IS a real `verify`
   call), and calibrated all four sites. **Fixed:** replaced `_has_pair` with
   `_program_starts_with` — pairs match ONLY at the program position (pair[0] vs
   the program basename, rest vs the following tokens); `python -m pytest` handled
   explicitly (interpreter at program position + `-m` + recognized module). Verified
   live: every `echo …` forge now reads WEAK; every real runner (incl. absolute
   `…/npm.exe run test`) stays STRONG. Regression:
   `test_runner_pair_in_argument_position_cannot_forge_strong`.

2. **[HIGH] Per-target key collision masked FAIL/weak targets.** `_verify_target_key`
   stripped the directory, so `a/test_w.py` and `b/test_w.py` collided; a later
   sibling PASS overwrote an earlier FAIL/weak target in the authoritative maps
   (last-write-wins), laundering the turn's verdict AND strength upward. **Fixed:**
   the key keeps the directory (normalized, leading `./` stripped). Same file/same
   spelling still shares a key (the self-correct FAIL→PASS loop is preserved — note
   the review's "FAIL-sticky + MIN-strength" suggestion would have BROKEN that loop;
   collision-resistant keying is the correct root fix). Regression:
   `test_verify_target_key_does_not_collide_across_directories`.

3. **[MEDIUM — surfaced, not auto-fixed] Legacy pre-gate `verified` rows.** Rows
   promoted before the strength gate carry `verification_strength IS NULL` and are
   still recalled (recall has no strength predicate). The reviewer's suggested
   fix (demote them) directly conflicts with an explicit, tested migration
   invariant — *"migration preserves earned verified state; trail rows are
   irreplaceable provenance; nothing is destroyed"* (`test_migration_*`) — and
   would demote the operator's genuinely-earned pre-gate skills (most were real
   STRONG pytest passes that simply predate the stamp). It is bounded (no NEW row
   can be created this way; the gate is live for all new records) and is a one-time
   grandfathering POLICY decision, so it is surfaced to the operator rather than
   applied unilaterally. Options: (A) demote legacy verified+NULL → candidate
   (fail-closed, recoverable, but contradicts the preserve-provenance invariant);
   (B) recall-time filter (non-destructive, same practical effect — earned skills
   stop being recalled until re-verified); (C) accept (lowest priority — bounded,
   pre-existing data only).

## Rollout
No flag. Behavior changes only for below-STRONG greens, which now stop calibrating
these three sites — the intended fix. Default-STRONG params preserve back-compat
until live callers pass real strength (the chat/generate caller does).
