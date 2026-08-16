# Organ 44 — what the golden cohort's failures actually are

**Date:** 2026-08-16
**Result:** 1/5 (20%) — the third consecutive 1/5
**Purpose:** not to move the number, but to make the failure breakdown true.

Run on merged master (`624a1f06`, including the empty-turn fix #220), a fresh
backend and data dir, live `gemini-2.5-pro`, real containerised pytest. Same
command and missions as the two prior runs.

## The breakdown

| mission | outcome | cause |
|---|---|---|
| `tdd-workflow` | `error` | **the model produced no output** |
| `iterative-refinement` | `error` | **the model produced no output** |
| `multi-module` | `verified_failure` | wrote code, its tests failed |
| `error-handling` | **PASS** | — |
| `data-pipeline` | step 1 PASS, step 2 `unverified` | wrote code, no sibling test |

Recorded verbatim for the two `error` steps:

```
The model produced no output this turn -- no tool call, no answer, no code.
Nothing was written and nothing was verified. This is a failed turn, not a
completed one; retry the request.
```

**Two of the four failures are the model returning nothing.** That is now
measured. Before #220 both would have been recorded as `unverified` and been
indistinguishable from the `data-pipeline` case, which is a genuinely different
failure — code written, no test to verify it with.

Three distinct causes, correctly separated:

* **2 × empty turn** — nothing attempted
* **1 × verified_failure** — attempted, code wrong
* **1 × unverified** — attempted, nothing to verify against

## The variance is the other finding

| run | model | mission that passed |
|---|---|---|
| 2026-08-11 | `2.5-flash` | `data-pipeline` |
| 2026-08-16 | `2.5-pro` | `multi-module` |
| 2026-08-16 (this) | `2.5-pro` | `error-handling` |

Three runs, three *different* missions passing, the score pinned at exactly 1/5
each time. No mission is reliably hard and none is reliably easy. Combined with
the `2.5-pro` result matching `2.5-flash` exactly, the evidence says the cohort
is measuring something with high per-turn variance rather than a capability
ceiling on any particular task.

That also means **single-cohort comparisons cannot resolve small differences.**
Any future claim that a change moved the score needs repeats, not one run — a
standard this session has already violated once, when a 2-turn endurance sample
was reported as "GREEN".

## What this does and does not change

**Does:** organ 44's first blocker now names what its failures are, with the
dominant one — the model producing nothing — measured rather than inferred.

**Does not:** move the score, and does not make organ 44 green. It stays yellow.
Counts unchanged at 52 green / 2 yellow.

## The open question

Why the model returns nothing on a substantial share of turns is still unknown.
Four hypotheses were tested and rejected while diagnosing it — stale files, a
mis-framing SSE parser, position within the cohort, and accumulated memory. The
fix in #220 makes the failure *visible and diagnosable*; it does not explain it.
That remains the highest-value open thread on this organ, ahead of wiring cloud
credentials into CI.

## Reproduce

```
docker compose --profile build-only build worker
AIOS_DATA_DIR=<fresh> AIOS_GEMINI_PROJECT=<project> python -m aios     # detached
# enroll once, capture enrollmentCredential -> AIOS_OPERATOR_CREDENTIAL
python tools/golden_mission_runner.py run --model gemini.gemini-2.5-pro
```

Turn-level evidence: `.aios/audit/golden-mission-runs.jsonl`, rows at or after
`2026-08-16T05:53`.
