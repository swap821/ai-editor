# Organ 44 — 0/5 to 1/5 by letting the agent iterate

**Date:** 2026-08-11 · **Model:** `gemini-2.5-flash` via Vertex ·
**Result: 1/5 missions, 4/8 steps** (was 0/5, 2/8)

The first mission this system has ever completed end to end.

## The defect

`ToolAgent._detect_agent_loop` stopped a turn when the last four tool calls
alternated `A→B→A→B`, and the detection window was cleared **only** at the
start of `run()` — never when the agent made progress.

Edit → test → edit → test *is* `A→B→A→B`. The canonical debugging loop was
indistinguishable from spinning, so the agent was stopped precisely when it
began iterating toward a fix.

Two more defects sat alongside it:

* The no-sibling-test note said *"the change is UNVERIFIED — do not assume it
  works"*. True and useless: the loop knew exactly which file was missing and
  never asked for it. The model wrote the implementation, was told it was
  unverified, had nothing to do, and ended the turn.
* `VerifierResult.summary` kept the last **500** characters of a failing run.
  pytest prints the useful part last, so the model could be told *that* two
  tests failed without being told *which*.

## The changes

1. **Progress-aware loop safety.** `note_progress()` clears the detection
   window when a write lands or a verifier verdict changes. Both patterns still
   trip for genuine no-progress spinning, because nothing clears the window
   then.
2. **The UNVERIFIED note names the file to create** and says the work stays
   unverified until it exists. Same verdict, same fail-closed meaning; only the
   instruction is new.
3. **Failure detail 500 → 4000 characters, failure path only.** A passing run
   has nothing to diagnose.

None of these touches a mission, a verdict, or an allowlist. All three are
defects any user of the agent loop would hit; the golden cohort merely made
them visible.

## The result

```
tdd-workflow          PASS verified_failure · FAIL error
iterative-refinement  PASS verified_success · FAIL error
multi-module          FAIL verified_failure
error-handling        FAIL verified_failure
data-pipeline         PASS verified_success · PASS verified_success  [PASSED]

FINAL: 1/5 (20%)   —   steps: 4/8 passing
```

| | before | after |
|---|---|---|
| missions | 0/5 | **1/5** |
| steps | 2/8 | **4/8** |
| `unverified` (no test written) | 3 | **0** |
| `error` (loop detector) | 1 | 2 |
| `verified_failure` | 2 | 2 |

**The `unverified` class is gone.** All three became real verdicts once the
model was told which file to write — change 2, working exactly as intended.

**`data-pipeline` completed both steps.** No mission had ever done that.

## What still fails, honestly

**Two `error`s (loop detector).** Both show the same shape:

```
[VERIFY FAIL] 0 passed, 5 failed (exit 1)
FFFFF                                    [100%]
```

The pytest body now reaches the model (change 3 working), but the verdict is
byte-identical across attempts, so no progress signal fires. If the agent is
re-running pytest without editing in between, that is genuine spinning and the
detector is correct to stop it. That has not been proven either way here, and
is not claimed.

**Two `verified_failure`s.** Real test failures in generated code. The agent
can now iterate on them; it did not converge.

## Why this stops at 1/5

The remaining gap is the part where honest work and score-chasing start to look
alike. Three real defects were found and fixed, and the number moved because
the system genuinely improved. Continuing to push on a number — retrying,
tuning prompts, adjusting thresholds until missions pass — would produce a
better figure and a worse measurement.

1/5 is recorded as the result. Organ 44 stays yellow: green on "Golden Mission
and Endurance Evaluation" would read as *the missions pass*, and four of five
do not.

## Reproduce

```
docker compose build worker
AIOS_GEMINI_PROJECT=ai-editor-498414 AIOS_API_TOKEN=<token> \
AIOS_DATA_DIR=<clean dir> AIOS_OPERATOR_CREDENTIAL=<credential> \
AIOS_EXECUTOR_HOST_WORKSPACE_ROOT=$(pwd)/data/executor-workspaces \
python tools/golden_mission_runner.py run --model gemini.gemini-2.5-flash
```
