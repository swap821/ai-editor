# Organ 44 — the golden cohort on gemini-2.5-pro

**Date:** 2026-08-16
**Result:** 1/5 (20%) — **identical to `gemini-2.5-flash`**
**Machine:** laptop, live Gemini via Vertex ADC, real containerised pytest
(`aios-worker:local`), Docker 29.5.2. Same command, same missions, same harness;
only `--model` changed.

## Why this run existed

Organ 44's first blocker records `MEASURED 1/5`. The open question was whether
that number reflected the *system* or the *model*. I had stated — more than
once — that 3 of the 4 remaining failures looked model-bound and that a stronger
model was the honest lever.

This run tested that claim directly. **It does not hold.**

## The result

```
tdd-workflow          FAIL   error — Agent loop detected
iterative-refinement  FAIL   unverified (step 2)
multi-module          PASS
error-handling        FAIL   unverified
data-pipeline         FAIL   unverified

FINAL: 1/5 mission runs passed (20%)
```

Side by side with the recorded `2.5-flash` run:

| mission | 2.5-flash | 2.5-pro |
|---|---|---|
| tdd-workflow | FAIL `verified_failure` | FAIL `error` (loop) |
| iterative-refinement | FAIL `error` (loop) | FAIL `unverified` |
| multi-module | FAIL `verified_failure` | **PASS** |
| error-handling | FAIL `verified_failure` | FAIL `unverified` |
| data-pipeline | **PASS** | FAIL `unverified` |
| **total** | **1/5** | **1/5** |

The score is unchanged and **the passing mission swapped**. `2.5-flash` passed
`data-pipeline` and failed `multi-module`; `2.5-pro` did the exact reverse. No
mission passes reliably across both models.

## What actually changed: the failure MODE inverted

| | 2.5-flash | 2.5-pro |
|---|---|---|
| dominant failure | `verified_failure` — wrote tests, tests failed | `unverified` — verification never ran |
| loop errors | 1 | 1 |

That inversion is the finding. A stronger model did not write better code that
passed more tests; it failed *earlier*, before verification happened at all.

## The signal that points at the system

`error-handling` and `data-pipeline` produced **no `[VERIFY ...]` evidence rows
whatsoever** — not a `FAIL`, not even a `SKIPPED` note — and ended in **53.8s
and 48.3s** respectively:

```
error-handling   steps_completed 1/1   elapsed 53.8s   outcome unverified
data-pipeline    steps_completed 1/2   elapsed 48.3s   outcome unverified
```

Every step that reached verification in this run took **100-250s**. These two
turns ended in roughly a fifth of that with nothing attempted. That is not a
model writing incorrect code; something ended the turn before the loop's
auto-verify ever fired.

By contrast, where the turn survived, the loop worked exactly as designed.
`multi-module` and `iterative-refinement` step 1 both show the actionable
no-sibling-test note from #215 doing its job:

```
[VERIFY SKIPPED] no sibling test for training_ground/validator.py
                 (looked for test_validator.py) ... Create test_validator.py
                 next to it with tests covering this change ...
[VERIFY PASS] 8 passed, 0 failed (exit 0) (strength=STRONG)
```

The model read the note and went on to write the test. That fix is confirmed
working — when the turn lives long enough to use it.

## What this settles, and what it opens

**Settled:** blocker 1 is not a model-selection question. Spending on a stronger
model does not move 1/5. The claim that the remaining failures were mostly
model-bound was wrong, and this supersedes it.

**Opened:** the highest-value remaining thread on organ 44 is not cloud
credentials for CI — it is why two turns ended in ~50 seconds having attempted
no verification. Wiring CI to run a cohort that still scores 1/5 would buy
nothing until that is understood.

## Reproduce

```
docker compose --profile build-only build worker
AIOS_DATA_DIR=<fresh> AIOS_GEMINI_PROJECT=<project> python -m aios     # detached
# enroll once, capture enrollmentCredential -> AIOS_OPERATOR_CREDENTIAL
python tools/golden_mission_runner.py run --model gemini.gemini-2.5-pro
```

Turn-level evidence: `.aios/audit/golden-mission-runs.jsonl`, rows at or after
`2026-08-16T04:00`.
