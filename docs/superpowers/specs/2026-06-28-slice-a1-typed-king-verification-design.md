# Slice A1 — type the evidence the King approves on

Date: 2026-06-28
Status: Approved (operator; direction confirmed — "do Slice A1")
Branch target: `council-runtime-v01` → fast-forward `master` on green
Roadmap: completes Phase 1's *governance* half (the learning half shipped). See the
GAGOS handoff §4 and `council-runtime-v01-review`.

## Goal

The verification-strength gate protects what the system **learns** (skills,
autonomy, swarm, curriculum). It does not yet reach what the **human approves on**.
`RunLedger.verification` and `KingReport.verification_result` carry an *untyped*
list of commands — the King (and the operator) approve a mission seeing *which*
commands ran, not *how strong* the evidence was. A1 threads the verification
**strength** into the ledger and the report, and **flags a positive recommendation
that rests on below-floor evidence**, closing the loop between the gated learning
layer and the (currently ungated) governance layer.

This is the organism becoming honest with the operator about its own evidence —
the same honesty the learning loop already has with itself.

## Scope (A1 = backend only; A2 paired-ticketed)

- **A1 (this slice):** derive strength into `RunLedger`, surface it in `KingReport`,
  flag below-floor approvals. Pure backend; testable acceptance.
- **A2 (separate, paired ticket per The One Law):** render verification strength in
  the dashboard as a derived **anatomical** signal (a faint imprint for weak, bright
  for strong), not a table cell. A2 does not ship as part of A1, but A1 is not
  "done" in the roadmap sense until A2 is ticketed.

Out of scope: changing the frozen contract *schema*. `RunLedger.verification` and
`KingReport.verification_result` are already `dict[str, Any]` (open), so strength is
threaded as dict keys — no schema change, FOUNDATION_LOCK untouched.

## Design

### 1. Derive strength at ledger build (`aios/runtime/run_ledger.py`)
Each verification entry in `result.evidence["verification"]` is a `run_command`
result dict: `{"command": [argv...], "returncode": int, "stdout": str, "stderr": str}`.
A new helper derives the mission's verification strength as the **weakest link**
(matching Phase 1's min-over-authoritative-passing-targets):

```
strength(mission) = min( derive_strength(
    passed = (r.returncode == 0),
    passed_count/failed_count = parse_test_counts(r.stdout + r.stderr),
    command = " ".join(r.command),
) for r in verification_results )   # default NONE if the list is empty
```

- A failed verification command → `derive_strength(passed=False) = NONE` → drags the
  min to NONE (fail-closed: a mission with any failed check is not strongly verified).
- Empty / missing verification → `NONE` (unverified, fail-closed).
- Malformed entries are treated as `NONE` (defensive).

`build_run_ledger` sets `verification = {"commands": <results>, "strength": strength.name}`
(keeps the existing `commands` key; adds `strength`). Reuses
`aios.core.verification_strength.derive_strength` / `parse_test_counts` — strength
derivation stays command-aware in one place (do not re-implement output parsing).

### 2. Flag below-floor approvals (`aios/runtime/king_report.py`)
`build_king_report` enriches `verification_result` (copied from `ledger.verification`):

```
strength = strength_from_name(verification_result.get("strength"), default=NONE)  # FAIL-CLOSED default
meets_floor = meets_promotion_floor(strength)
verification_result["meets_floor"] = meets_floor
if recommendation in {"approve", "observe"} and not meets_floor:
    verification_result["below_floor_warning"] = (
        f"verification strength {strength.name} is below the {promotion_floor().name} "
        "floor — this recommendation rests on weak evidence; review before approving"
    )
    human_summary = f"⚠ Weak verification ({strength.name} < {promotion_floor().name} floor). " + human_summary
```

**Fail-closed is load-bearing here:** `strength_from_name` defaults to STRONG; A1
MUST pass `default=NONE` so a missing/unparseable strength is flagged, never waved
through. Both `approve` (human-gated) and `observe` (auto, no approval needed) are
flagged when below floor — a weak auto-proceed is as dishonest as a weak approve.

### 3. Why min, not "any passed"
A King report should reflect the weakest evidence the recommendation rests on — one
strong check cannot launder a weak sibling, exactly as Phase 1's turn strength is the
weakest authoritative passing target. Consistent mental model across the codebase.

## Error handling / fail-closed
- No / empty / malformed verification → `NONE` → any positive recommendation flagged.
- Missing `strength` key on an older persisted ledger → `strength_from_name(None,
  NONE)` → `NONE` → flagged. Never fail-open to STRONG.
- Frozen security spine and contract schemas untouched (open dicts only).

## Testing (adversarial acceptance — the Verifier's bar)
- `build_run_ledger` from STRONG verification (`pytest …`, exit 0, "N passed") →
  `verification["strength"] == "STRONG"`.
- From WEAK verification (`echo done`, exit 0, no counts) → `"WEAK"`.
- From a failed verification (exit 1) → `"NONE"`.
- Empty verification list → `"NONE"`.
- **Acceptance:** a `KingReport` recommending `approve` on WEAK evidence has
  `verification_result["meets_floor"] is False`, a `below_floor_warning`, and a
  `human_summary` caution; recommending `approve` on STRONG is NOT flagged.
- `observe` on below-floor is also flagged.
- Existing runtime/council suites stay green; 85% coverage floor; frozen spine
  untouched.

## Rollout
No flag, no migration. Behavior change is additive: ledgers/reports gain a typed
strength + a caution on weak positive recommendations. A2 (organism render) follows
as its own slice.

## Adversarial review — CLEAN

A focused adversarial skeptic (6 attack angles, code-read + live probes) returned
**INVARIANT HOLDS — CLEAN**. Verified: fail-open is closed (missing/empty/malformed/
garbage strength → NONE → flagged; the `strength_from_name` STRONG default is
neutralized by the explicit `NONE`); command-aware spoof defense survives this path
(`echo 5 passed` → WEAK); `min()` weakest-link holds (one strong cannot mask a weak/
failed sibling); `build_king_report` is the only positive-recommendation path
(`build_deliberation_report` is correctly out of scope — pre-execution, no evidence
yet); frozen contracts not violated (open `dict[str, Any]` keys only). Defense-in-
depth noted: the `TestingQueen` independently denies on any failed check, forcing the
King's `denied` branch — a second fail-closed computation of the same evidence. Two
non-defeating follow-ups (do not block A1): (1) the dashboard + council API payload
don't yet render `meets_floor`/`below_floor_warning` — **this is A2**; (2) a
hand-forged `RunLedger` object could assert `strength="STRONG"`, but that is outside
A1's trust model (the name can only be minted by the spoof-proof
`_verification_strength` in the sole production constructor; forging the ledger forges
everything).
