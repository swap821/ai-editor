# Organ 44: golden cohort on a plan brain, at master `423b93d0` (2026-11-22)

**Result: [4, 3, 4] of 5. 11 of 15 mission runs passed (73%), and all three repeats are valid measurements.** The bar set before the 2026-08-19 runs is three consecutive clean 5/5 repeats. This result does not meet it, so organ 44 stays yellow.

## How it was run

- **Code:** master `423b93d08c1b3ab422bf78342c9996f5e6252146`, which includes #726 and #729: a turn counts as reached when the model under test answered it.
- **Model:** `plan.claude-sonnet-5-5`, through the operator's Claude plan.
- **Why not the September bar's model:** that bar was set with `gemini.gemini-3.7-flash` on Vertex. Vertex now refuses with `403 BILLING_DISABLED` on project `ai-editor-498414`, and enabling billing is the operator's act. He chose a plan brain, so this is a new measurement on a different model, not a repeat of the September one.
- **Files in scope:** since #727, files the tools read from GAGOS's scope reach his plans, with keys, credentials, paths and random-looking strings still masked.
- **Setup, per repeat:**
  - a fresh backend on its own port, with its own `AIOS_DATA_DIR`, its own enrollment and throwaway keys;
  - Claude Code's own session variables removed;
  - `training_ground` and `lab` reset between repeats;
  - `python tools/golden_mission_runner.py run --model plan.claude-sonnet-5-5`;
  - the sandbox image `aios-verify:9528ebce8681`.
- **When:** 2026-11-22, 20:03-20:33Z. Repeat timings: 542 s, 607 s, 589 s.
- **Records:** `2026-11-22-plan-sonnet-cohort.jsonl` holds all 33 records: every mission start and finish, each step's outcome and evidence, the approvals granted, and one batch summary per repeat. Every batch summary reads `unreached_steps: []`, `valid: true`.

## By mission

| mission | r1 | r2 | r3 |
|---|---|---|---|
| tdd-workflow | pass | pass | pass |
| iterative-refinement | pass | pass | pass |
| multi-module | **fail** | **fail** | **fail** |
| error-handling | pass | pass | pass |
| data-pipeline | pass | **fail** | pass |

`tdd-workflow`'s red phase is intact in every repeat: step 1 expects `verified_failure` and got it.

## The failures

### `multi-module`, step 2, all three repeats (`unverified`)

Step 2 asks the model to create `user_registry.py` (importing `validate_email` from step 1's `validator.py`) and `test_user_registry.py`, then verify. At least two of the three failures come from GAGOS, not only from the model, going by the model's own answers:

- **Repeat 2.** The model said the read tools "are not available in this session, so I couldn't inspect training_ground/validator.py". It declined to guess and changed nothing.
- **Repeat 3.** The model called `create_file` for both files, but "the results came back redacted, so I can't tell whether either write was approved or completed". It also said the read tools were not available to check. Only `user_registry.py` was approved and created. The verifier reported no sibling test.
- **Repeat 1.** The model created `user_registry.py` and ran `pytest training_ground/test_user_registry.py`, but never created the test file.

Two GAGOS gaps behind this, both open:

1. **Read tools reported unavailable.** In some turns the plan brain says `read_file` and `read_directory` are not available, or believes so. The cause is not yet found.
2. **Write results hidden.** `create_file` and `edit_file` results still reach the plan as `[FILE CONTENT REDACTED]`. #727 showed his plans only the results of `read_file` inside the scope.

### `data-pipeline`, step 2, repeat 2 (`verified_failure`)

The model's own edit left 3 of its tests failing (`test_failing_step_returns_pipeline_error`, `test_pipeline_error_reports_step_index_and_exception`, `test_steps_after_failure_do_not_run`). That is a model failure, measured.

## What this is not

- It is not the September [5,5,5] Gemini cohort, and it is not compared with it as if it were.
- It does not meet the bar.
- It is the first valid cohort since the harness stopped voiding turns and retrying them into passes (#726, #729). The two runs before it on 2026-11-22 were stopped: one was going INVALID, and one was retrying a genuine failure.
