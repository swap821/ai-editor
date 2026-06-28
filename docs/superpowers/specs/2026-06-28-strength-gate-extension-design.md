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

## Rollout
No flag. Behavior changes only for below-STRONG greens, which now stop calibrating
these three sites — the intended fix. Default-STRONG params preserve back-compat
until live callers pass real strength (the chat/generate caller does).
