# Verification Confidence — Mutation-Probe Design (are the checks the right checks?)

Date: 2026-07-06
Status: Design approved for v1.0 (Tier 0 ships with the learning-loop prover; Tiers 1–2 post-v1.0)
Builds on: `2026-06-28-verification-strength-taxonomy-design.md` (floor = STRONG)

## The open problem

The strength taxonomy answers *"how strong was the check that passed?"* It cannot
answer the question above it: *"does the verification machinery actually detect
breakage?"* Every promotion in the learning loop — lessons, skills, playbooks,
calibration — inherits its trust from `[VERIFY *]` verdicts. If the verify path
itself rotted (a harness bug, a swallowed exit code, a pytest invocation that
collects zero tests, a sandbox path mix-up that runs the wrong file), the system
would keep minting verified experience from checks that check nothing. That is
the one failure mode the current design cannot see from inside.

## The mechanic — mutation probes

A **probe** is a deterministic triple: *(mutant artifact, verify command,
expected verdict)*. The mutant is code that is broken **on purpose** in a known
way; the expected verdict is always FAIL (or a specific strength label). Driving
a probe through the SAME live verify path the learning loop uses yields
**meta-evidence about the verifier itself**:

- Probe behaves as expected → STRONG meta-evidence that the verify path detects
  that breakage class. Recorded, dated, repeatable.
- Probe passes verification (broken code goes green) → a **verification-confidence
  violation**: the single loudest alarm the system can raise, because every other
  green verdict is now suspect.

Probes are deterministic fixtures — no LLM in the probe loop. The LLM may ferry
the command (as in the prover), but the artifact and expectation are pinned.

## Tier 0 — shipped now (inside `tools/learning_loop_prover.py`)

One static probe, phase 3 of every prover run: a planted test file whose only
test asserts `1 == 2`. The prover instructs a verify of exactly that file and
hard-asserts that `[VERIFY FAIL]` (and no `[VERIFY PASS]`) is observed. A
violation fails the entire prover run regardless of every other check, and the
JSONL artifact records it as `probe.broken-code-fails: FAIL`.

This is deliberately minimal: it proves the *pattern* (mutant → live loop →
expected verdict → meta-evidence row) end-to-end with zero new product code.

## Tier 1 — probe library (post-v1.0, first follow-up)

A small library of mutant classes, each targeting a distinct way verification
can lie, each asserting **both** the verdict and the derived strength label:

| Probe class | Mutant | Must yield |
|---|---|---|
| assertion-fail | test asserting a falsehood | FAIL |
| import-error | test importing a missing module | FAIL |
| syntax-error | unparseable test file | FAIL |
| empty-suite | file with no test functions | never STRONG (0 collected ⇒ `passed_count == 0`) |
| weak-green | command exiting 0 with no test semantics | never STRONG (WEAK label) |
| wrong-target | pass on file A must not clear a FAIL key on file B | per-target keys hold |

The last three probe the *anti-laundering* seams specifically (strength floors,
per-target evidence keys) — the places where a subtle regression would be
invisible to normal use.

Runner: a `probes` subcommand on the prover (same SSE plumbing, same artifact).
Aggregate outcome surfaces as a `verification_confidence` block in
`GET /api/v1/development/harness` (probes passed / total / last run), read from
the JSONL like the existing harness summaries — no new storage.

**Promotion freeze on violation (design decision to confirm at implementation):**
`AIOS_PROBE_FAIL_FREEZES_PROMOTION` (proposed default ON) — a recorded violation
sets a flag that makes `meets_promotion_floor` return False until an operator
clears it. Rationale: after the verifier is caught lying once, minting more
verified experience is worse than pausing learning. Fail-closed, operator-owned.

## Tier 2 — mutation of real artifacts (future)

After a turn verifies green in the sandbox, mutate the just-verified artifact
with a semantic mutant (e.g. flip an operator, negate a branch) and re-run the
SAME verify command: it must now fail. This closes the deeper gap Tier 1 cannot:
*"the tests pass but do not cover the behavior."* Expensive (one extra verify
per sampled turn), so sampled, off the hot path, and sandbox-only. Explicitly
out of scope for v1.0.

## What this deliberately does not claim

- Probes prove detection of the **probed classes only** — they bound, never
  eliminate, verifier doubt. The honest claim is a growing, dated list of
  breakage classes the machinery demonstrably catches.
- This complements the strength taxonomy; it never substitutes for it. A STRONG
  verdict still means what the taxonomy says — probes defend the meaning.
- The RED frozen security spine is untouched; probes live entirely in
  `training_ground/` + `tools/` + read-only reporting.

## Verification of this design itself

Tier 0 is verified by every green prover run (the probe is a hard check). Tier 1
lands with unit tests per probe class plus one live run recorded in the harness
endpoint; the freeze flag lands with tests proving promotion is refused while a
violation is unresolved.
