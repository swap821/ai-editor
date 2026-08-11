# Organ 44 — the first real measurement: 0/5

**Date:** 2026-08-11 · **Model:** `gemini-2.5-flash` via Vertex AI ·
**Sandbox:** `aios-worker:local` (pytest 9.1.1) · **Result: 0/5 missions**

This is the honest number. It is recorded, not engineered, and nothing in the
missions or the verifier was loosened to improve it.

## Why earlier 0/5s did not count

Three cohorts ran today and all three scored 0/5. Only the third measured
anything. Each earlier run died on an environmental wall that presented from
the outside as "the model failed":

| Wall | Symptom |
|---|---|
| `AIOS_GEMINI_PROJECT` unset | Gemini disabled; provider already built for this laptop's ADC |
| Runner sent no auth | 403 on every turn, since the day the API was secured |
| Model id lacked the `gemini.` prefix | Fell through to Bedrock; reported "AWS Bedrock is not configured" |
| Reason discarded by `run_mission` | A 0/5 with no recoverable cause |
| Docker not running | Verifier could not execute; every step `[VERIFY FAIL] 0 passed, 0 failed` |
| `aios-executor:local` not built | `No such image` |
| No pytest in the sandbox | Model correctly tried `pip install pytest`; allowlist refused it |

Seven layers. Every one invisible until the diagnostics from step 1 named it.

## The measurement

```
tdd-workflow          step 1  PASS  verified_failure   (correct TDD red)
                      step 2  FAIL  error — agent loop detected
iterative-refinement  step 1  PASS  verified_success
                      step 2  FAIL  unverified
multi-module          step 1  FAIL  unverified
error-handling        step 1  FAIL  [VERIFY FAIL] 7 passed, 2 failed
data-pipeline         step 1  FAIL  [VERIFY FAIL] 4 passed, 1 failed

FINAL: 0/5 mission runs passed (0%)
```

Eight steps attempted:

| Verdict | Count | What it means |
|---|---|---|
| genuine pass | 2 | a correct TDD red, and a clean `verified_success` |
| real test failure | 2 | 7-of-9 and 4-of-5 assertions passing — near misses |
| `unverified` | 3 | no sibling test file written; the model skipped the test half |
| `error` | 1 | loop detector stopped repeated identical actions |

`7 passed, 2 failed` is the line that separates this run from the others. The
model wrote real code and real tests and the sandbox executed them. The earlier
`0 passed, 0 failed` was a container with no test runner.

`verified_success` had never appeared in this repo before today.

## What 0/5 does and does not say

**It says:** on `gemini-2.5-flash`, through this agent loop, with these five
missions and this verifier, no mission completed end to end. Two of eight steps
passed. Two more were near misses. Three failed by omitting the test file.

**It does not say** the system is incapable, that the missions are fair, or
that the verifier's strictness is calibrated. Those are separate questions this
run does not answer, and no claim about them is made here.

Notably, `unverified` — three of eight steps — is a single repeated behaviour:
the model writes the implementation and not the tests. Whether that is a prompt
problem, a model problem, or a mission-design problem is not established.

## Organ 44 stays yellow

The harness is now trustworthy: it runs live against a real cloud provider,
executes tests in a real disposable sandbox, distinguishes five verdicts, and
reports why for every failure.

The score it reports is 0/5. Green on "Golden Mission and Endurance Evaluation"
would read to any reasonable person as *the missions pass*. They do not. The
operator's instruction was explicit — an honest 0/5, not a narrowed claim that
turns a working evaluator into a green organ while the number stays bad.

So the number goes in the record and the colour does not change.

## Also still true

* This is a laptop run. CI has neither cloud credentials nor these images.
* Endurance (`tools/endurance_tester.py`) has not been run and still carries
  the auth defect that was fixed for the golden runner.
* AWS Bedrock remains entirely absent from this machine, and — as this work
  established — was never the blocker.

## Reproduce

```
docker compose build worker
AIOS_GEMINI_PROJECT=ai-editor-498414 \
AIOS_API_TOKEN=<token> \
AIOS_DATA_DIR=<clean dir> \
AIOS_OPERATOR_CREDENTIAL=<enrollment credential> \
AIOS_EXECUTOR_HOST_WORKSPACE_ROOT=$(pwd)/data/executor-workspaces \
python tools/golden_mission_runner.py run --model gemini.gemini-2.5-flash
```
