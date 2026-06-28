# Verification-Strength Taxonomy (GAGOS roadmap Phase 1 — keystone, vertical slice)

Date: 2026-06-28
Status: Approved (operator; floor = STRONG)
Branch target: `council-runtime-v01` → fast-forward `master` on green

## Goal

Make "verified" mean **one strength** everywhere the learning loop trusts it, so a
weak green (an arbitrary command that merely exits 0) can no longer imprint on the
future. Today `Verifier.verify` judges `passed = exit_code == 0` and discards the
`passed_count`/`failed_count` it already parses, so a behavior-asserting test suite
and a bare `exit 0` are indistinguishable to every downstream promotion.

This is the roadmap keystone (§2.1): the learning loop already imprints on this
signal, and weak greens compound into hollow competence.

## Scope (this slice)

Vertical slice through **one** promotion site to prove the mechanic and establish
the reusable gate:
- Derive strength at the source (`Verifier` + council `TestingQueen`).
- Gate the **skills** promotion site so a below-floor success cannot become a
  `verified` skill.
- Define the shared gate helper the other sites adopt next.

**Out of scope (follow-ups):** the other promotion sites (`development`,
`mistake`→planner-confidence, `swarm_patterns`, `consolidation`) adopt the same
helper later; the anatomical imprint (strong = bright, weak = faint) is a separate
UI slice. The RED frozen security spine is untouched.

## The taxonomy — `aios/core/verification_strength.py`

`VerificationStrength` enum, ordered STRONG > MEDIUM > WEAK > NONE, derived
deterministically (no new execution) from a `VerifierResult`:
- **STRONG** — behavior-asserting suite passed: `passed` and `passed_count > 0`
  and `failed_count == 0`.
- **MEDIUM** — recognized checker passed: `passed`, no parsed test counts, and the
  command's program is on a small checker allowlist (`mypy`, `pyright`, `tsc`,
  `ruff`, `flake8`, `eslint`, `pylint`, `mypy`). Best-effort **labeling only**.
- **WEAK** — `passed` but exit-code-only (no counts, not a recognized checker).
- **NONE** — not passed (fail/blocked/timeout/un-runnable).

Helpers: `derive_strength(*, passed, passed_count, failed_count, command) ->
VerificationStrength`; `meets_promotion_floor(strength) -> bool` against
`config.VERIFICATION_PROMOTION_FLOOR` (default **STRONG**). Because the floor is
STRONG, MEDIUM/WEAK/NONE are all ineligible — so an imperfect checker allowlist can
only mislabel WEAK↔MEDIUM (both ineligible) and can never cause a false promotion.

## Source wiring

- `VerifierResult` gains `strength: VerificationStrength`; `Verifier.verify` sets it
  via `derive_strength(...)` (it has `command`, `passed`, counts).
- Council `TestingQueen` derives strength for each verification result and records
  the aggregate (min across commands) in `QueenVerdict.metadata["verification_strength"]`.

## Skills gate — `aios/memory/skills.py`

`record_attempt(goal, steps, *, success, strength=VerificationStrength.STRONG)`:
- Default `STRONG` keeps every existing caller/test byte-identical; only an
  explicitly below-floor success is gated.
- A success increments the promotion-eligible `success_count` **only if**
  `meets_promotion_floor(strength)`; otherwise it increments a new
  `weak_success_count` (recorded, ineligible — never reaches `verified`).
- `failure_count` and the `success >= min_successes and rate >= min_success_rate`
  promotion rule are unchanged; `success_count` is now eligible-only, so a skill
  fed only below-floor greens stays `candidate` forever.
- Stamp the row with the latest success's `verification_strength`.
- Schema: two additive columns on `procedural_skills`
  (`verification_strength TEXT`, `weak_success_count INTEGER NOT NULL DEFAULT 0`),
  added idempotently in the `init_memory_db` migration path (ALTER-if-missing).
- Wire the live learning caller to pass `result.strength` through, so real WEAK
  greens are gated (not merely defaulted).
- `weak_success_count` surfaced in `trail_map()` for observability.

## Config

`VERIFICATION_PROMOTION_FLOOR` (env `AIOS_VERIFICATION_PROMOTION_FLOOR`, default
`"STRONG"`), parsed to the enum (unknown value → STRONG, fail-closed).

## Error handling

- Unparseable/unknown floor or strength string → STRONG (fail-closed: the strictest
  bar, never accidentally lax).
- Missing columns on an older DB → added on init; reads default `weak_success_count`
  to 0 and `verification_strength` to NULL.

## Testing (Verifier-owned, the done-when)

- **Keystone:** 3 WEAK greens → skill stays `candidate`, eligible `success_count == 0`,
  `weak_success_count == 3`; 3 STRONG greens → `verified`.
- `derive_strength`: STRONG (pytest "3 passed"), MEDIUM (`mypy .`), WEAK (bare
  `exit 0`), NONE (failure / non-OK status).
- `meets_promotion_floor` honors `VERIFICATION_PROMOTION_FLOOR` (STRONG default →
  only STRONG eligible; flipping to MEDIUM admits MEDIUM).
- `Verifier.verify` populates `strength`; `TestingQueen` verdict carries it.
- Existing skills suite stays green (default STRONG).
- Full backend suite + 85% floor; frozen spine untouched.

## Rollout

No flag needed — the gate is always on, but defaulting `record_attempt`'s strength
to STRONG means behavior is unchanged until the live caller passes real strength.
The only behavioral change: a workflow proven solely by below-STRONG verification
no longer becomes a `verified` skill — which is the intended fix.

## Adversarial review outcome (2026-06-28, Verifier-owned per roadmap §6)

The review's mandate was to make a hollow green imprint. It succeeded once —
fixed before merge:
- **[HIGH] forged STRONG** — `_is_test_runner` accepted a runner token in ANY
  position, so `echo running pytest now: 5 passed` classified STRONG (and that
  echo is GREEN/auto-exec while real pytest is YELLOW — the hollow path was
  *easier*). Fixed: runner/checker must be in **program position** (basename) or a
  structural pair (`-m pytest`, `go test`, `npm test`). Regression-tested.
- **[LOW] floor clamp** — a misconfigured `NONE` floor would admit failed
  verifications. Fixed: `promotion_floor()` clamps anything below WEAK up to
  STRONG (misconfig can only make the gate stricter).

Held under attack (no fix): stdout/strength-token injection (header-first +
first-match), rate-math inflation, weak→success leakage, `record_reuse`
laundering, db consolidation, TestingQueen aggregate (metadata-only, min-across).

### Residual / follow-ups (not blockers)
- A trivially-passing real test is legitimately STRONG — the gate certifies "a
  recognized runner asserted passes," not test quality.
- `record_attempt`'s `strength` defaults to STRONG (back-compat); future call
  sites must pass it explicitly.
- `swarm_patterns` + `curriculum` (+ `development`, `mistake`→confidence) promotion
  sites are not yet gated — the next slice adopts `meets_promotion_floor` there.
- Verified: full backend `pytest --cov` exit 0, 1221 passed / 1 skipped, 87.35%.
