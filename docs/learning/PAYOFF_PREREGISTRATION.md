# Learning payoff — pre-registration

*Registered 2026-09-25, before any official run of `tools/learning_payoff.py`.
Every run records the sha256 of this file (`preregistration_sha256` in
`.aios/audit/learning-payoff.jsonl`). A result produced under a different hash
was produced under a different hypothesis, and says so.*

## Why this exists

The payoff benchmark is the number the learning loop is judged by. A judged
number whose hypothesis, sample, model or success line can be chosen after the
results are visible is not a measurement — it is a narrative. Everything below
is fixed now. Changing any of it is allowed only through the **Deviations**
section, dated, with a reason, **before** the run it affects.

## The question

Does what this system remembers make its model measurably better at real work
it has **not** practised before?

## Design

- **Task:** pin the behaviour of a real function in this repository with a
  pytest test, graded by `grade_pin_test` (passes clean, fails when the
  function is mutated, source untouched, suite still green). Unchanged.
- **Arms:** OFF = the production task prompt; ON = the same prompt with
  recalled lessons and verified skills prepended through the production recall
  path. Arm order alternates by target index.
- **Pairing:** each target is its own control (ON vs OFF, same model, same
  corpus commit).
- **Before/after:** the **Phase 0 baseline** run (before any hardening) and the
  **Phase 8 judged** run use the **same frozen target list** and the same model.
  The Phase 0 run's chosen targets are exported to
  `docs/learning/payoff_targets_phase0.txt` and committed; Phase 8 runs with
  `--target-labels docs/learning/payoff_targets_phase0.txt`.

## Fixed parameters

| Parameter | Value |
|---|---|
| Model (primary, judged) | `ollama.qwen2.5-coder:7b` — the product's default local model |
| Model (secondary, descriptive only) | the strongest available cloud model, if credentials are present; never the judged number |
| Targets | **30**, chosen by `select_targets` (alternating never-practised / practised) at the Phase 0 run, then frozen |
| Measured code | `--ref origin/master` at the time of the run (fetched first); corpus sha recorded |
| Model timeout | 420 s |
| Grader | `tools/self_corpus_grading.py::grade_pin_test`, positive control (`run_self_check`) required first |

## Hypotheses and tests

All tests are **exact two-sided McNemar** on discordant pairs, α = 0.05.

- **H1 — transfer (THE JUDGED NUMBER).** On NOVEL pairs (no recalled item
  recorded on that target), ON earns more often than OFF.
  *Met* iff ON-only > OFF-only **and** p < 0.05.
- **H2 — no harm.** On ALL comparable pairs, ON does not earn significantly
  *less* often than OFF. *Violated* iff OFF-only > ON-only and p < 0.05.
- **H3 — hardening preserves utility.** Across Phase 0 → Phase 8, on the same
  frozen targets, the ON arm's earned outcome does not drop significantly
  (McNemar over the ON arm's paired outcomes between the two runs).
  *Violated* iff Phase-0-only > Phase-8-only and p < 0.05.

SEEN-pair results are reported as context and carry no test.

## Exclusions (decided now)

- A pair is **not comparable** — excluded from every test, and counted — when
  recall returned nothing (identical prompts) or either arm never reached the
  model. Not-comparable pairs are never scored as losses.
- A run refused by containment, the positive control, the hollow-suite guard or
  the memory-store guard produces **no number**. It is re-run in full; the
  refusal is kept in the trail. There is no partial result.

## Stopping rule

One analysis per run, at the fixed N. No interim looks, no extending N because
a result is close, no re-running because a result is disliked. A re-run is
permitted **only** after a refusal listed above, and the reason is recorded.

## What each outcome means

| Outcome | Reported as |
|---|---|
| H1 met, H2 not violated | Memory helps on new work. |
| H1 not met, direction positive | A direction, not a finding — reported as such. |
| H1 not met, no discordant pairs | No measurable difference. A result, not a failure to measure. |
| H2 violated | **Memory hurts.** The most important possible result; it is not explained away. |
| NOVEL has no comparable pairs | No judged number this run — recall had nothing relevant to transfer. |

## What this does not claim

Recall channels exercised: lessons and verified skills only — not semantic
memory, facts or the self-model. Recall is prepended, so a content effect is not
separated from a prompt-length effect. A 7B local model's behaviour is not a
frontier model's. These limits travel with every number.

## Deviations

*None yet. Each entry: date, what changed, why, and which run it applies to —
recorded before that run.*
