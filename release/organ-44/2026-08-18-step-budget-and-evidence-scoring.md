# Organ 44 — the golden cohort moved: 1.125 → 2.667 of 5

- **Measured**: 2026-08-18, on `ecdedb86`, model `gemini.gemini-2.5-pro` via Vertex ADC
- **Distribution**: `[2, 3, 3]` across 3 complete runs — mean **2.667 of 5**
- **Prior**: `[2, 0, 2, 0, 1, 2, 2, 0]` across 8 runs — mean **1.125 of 5**
- **Verdict**: organ 44 stays **YELLOW**. The number improved; the blocker is not
  discharged.

## The one-line summary

The new **minimum equals the old maximum**. Every run in the new set matched or
beat the best result ever recorded before, and a 3/5 had never occurred.

Nine previous fixes — three agent-loop defects, empty turns (#220), Gemini
truncation (#222), the loop detector explaining itself (#236), the no-op write
dead end (#238) — moved this number by nothing measurable. Each fixed a real
defect. These two moved it.

## What changed

### 1. The step budget could not reach the exit the system offers

`DEFAULT_MAX_ITERS` was a hardcoded 5. The measured dominant failure was
`edit_file` BLOCKED on `old_string not found` — **7 of 10 unverified steps**.
#240 gave that dead end a way out: the error names `overwrite_file` with the
complete body. Taking it costs at minimum:

```
read_file 1, edit_file 2 (fails), overwrite_file 3, verify 4 (may fail),
fix 5, verify 6
```

The turn ended on the step where the guidance began. The system was telling the
model what to do and then stopping it before it could do it.

Now `AIOS_AGENT_MAX_ITERS`, default 16. Across all four runs since,
`old_string not found` occurred **zero times**.

### 2. Earned evidence was being discarded

`run_prompt` had two classification paths:

| path | rule |
|---|---|
| clean finish | last terminal verdict wins |
| `error` event | `outcome="error"`, evidence thrown away |

Identical verifier output scored differently depending on how the turn ended.
This is the same validator/actor divergence found twice already this month — here
between two branches of one function.

It mattered because (1) gave the agent room to dither *after* finishing. It
re-reads a file it has already read, the loop detector correctly stops the turn,
and `iterative-refinement` step 2 was scored a **FAILURE** while carrying:

```
[VERIFY PASS] 6 passed, 0 failed (exit 0) (strength=STRONG)
```

Both paths now call `outcome_from_evidence`. The bar is unchanged, and was
checked against all three real evidence strings *before* the change was written:

| step | evidence | outcome | vs expected |
|---|---|---|---|
| iterative-refinement s2 | `[VERIFY PASS] … STRONG` | verified_success | **converts to PASS** |
| tdd-workflow s2 | `[VERIFY FAIL] 3 passed, 1 failed` | verified_failure | still FAIL |
| multi-module s2 | `[VERIFY SKIPPED]` | unverified | still FAIL |

Exactly one step converted — the one that had earned a STRONG pass. `errored`
is retained in the result so the loop trip stays visible: an agent that finishes
the work and then fails to stop is a real defect, and hiding it would be the
opposite of the point.

## What this does NOT establish

**Attribution is unresolved.** Both changes are present in all three runs. A
pilot run with the budget change alone scored 2/5 — the top of the old range;
the 3s appear only once the scoring fix is in. So part of the gain is the
harness ceasing to discard evidence it had already earned, not the agent
improving. Those are different claims and are not merged here. One cohort run
with the scoring fix and `AIOS_AGENT_MAX_ITERS=5` would isolate it.

**n=3.** If these were draws from the old distribution, all three landing ≥2
would happen roughly 12% of the time by chance. Suggestive, not proven.

## Where the failures went

| Mission | rep1 | rep2 | rep3 |
|---|---|---|---|
| tdd-workflow | FAIL | FAIL | PASS |
| iterative-refinement | PASS | FAIL | FAIL |
| multi-module | FAIL | PASS | PASS |
| error-handling | PASS | PASS | FAIL |
| data-pipeline | FAIL | PASS | PASS |

**Every mission passes at least once and fails at least once.** None is
structurally impossible; the system is unreliable rather than incapable.

Of the 7 remaining failures:

- **4** — `verified_failure`: the model's code fails the model's own tests
  (`divide` raising `ValueError` where the test requires `ZeroDivisionError`)
- **3** — `unverified`: no sibling test written, so nothing could be verified
- **0** — `old_string not found`

The bottleneck has moved from **harness structure** to **model correctness and
instruction-following**. That is a materially different diagnosis from the one
this organ carried for the last eight runs.

## The next real lever, not taken here

The agent has no completion signal. Extra budget therefore turns into dithering:
it finishes, re-reads a file three times, and the loop detector stops it. In
`tdd-workflow` it hit a genuine failure and re-read the *test* rather than
editing the *code* — the detector was right to fire. Fixing this is loop design,
not a constant, and it is the most likely source of the next real gain.

## Blocker status — why this is still YELLOW

| # | Blocker | Status |
|---|---|---|
| 1 | golden cohort shortfall | **Improved, not discharged.** 2 of 5 missions still fail per run. |
| 2 | CI has no cloud credentials or worker/executor images | **Untouched.** Needs operator GCP action (WIF pool/provider). |
| 3 | endurance 0.611 vs the 0.80 bar | **Not re-measured** since these fixes. The same two changes plausibly apply. |
| 4 | harness runs once per instance | **Worse than recorded.** It cannot run twice against one instance at all — the enrollment credential is one-time. These runs used a fresh `AIOS_DATA_DIR` per repeat. That is a workaround, not a fix; surfacing the credential is identity-adjacent and is the operator's design call. |

Green requires `known_blockers == []`. Proposing green is not mine to do, and on
these numbers it would not be honest anyway.

## Method

Three cohorts, each against a **fresh instance** — its own port (8011-8013), its
own `AIOS_DATA_DIR`, its own enrollment. Nothing shared between runs except the
code under test. Backends launched `DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP`
so that reaping the controlling session could not kill a run mid-measurement.

Four setup defects were found on the way in, all previously undocumented:

1. A **10-hour-stale backend** held port 8000 (started 16:07, fix at 02:22, no
   `--reload`). Measuring against it would have produced a confident, meaningless
   number. Left running; the measurement used its own instance.
2. `AIOS_PROBE_HOST` **hardcodes `localhost:8000`**, so any instance on another
   port fails enrollment with a misleading "Host header is not configured".
3. `GEMINI_ENABLED = bool(GEMINI_PROJECT and GEMINI_MODEL)` and `GEMINI_PROJECT`
   was empty — Gemini was silently **off**, and `/api/generate` returned a bare
   503 with no indication that a provider was unconfigured. A disabled provider
   should say so.
4. Blocker 4, encountered live and worse than its description.
