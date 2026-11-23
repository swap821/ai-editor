# Organ 44: golden cohort on a plan brain, at master `32f961dc` (2026-11-23)

**Result: [4, 5, 5] of 5. 14 of 15 mission runs passed (93%), and all three repeats are valid measurements.** The bar is three consecutive clean 5/5 repeats. This result has two in a row, not three, so organ 44 stays yellow.

## How it was run

- **Code:** master `32f961dc7591da98c255253ac76bb6ebe35db33c`, which includes #731: GAGOS tells its plan brains what their writes did (a `[NOT RUN]` result for a call skipped by an approval pause, and the scope label on `read_directory`, `create_file` and `edit_file` results).
- **Model:** `plan.claude-sonnet-5-5`, through the operator's Claude plan, as on 2026-11-22.
- **Setup, per repeat:** the same harness as 2026-11-22:
  - a fresh backend on its own port, with its own `AIOS_DATA_DIR`, its own enrollment and throwaway keys;
  - Claude Code's own session variables removed;
  - `training_ground` and `lab` reset between repeats;
  - `python tools/golden_mission_runner.py run --model plan.claude-sonnet-5-5`, from a detached worktree at that commit;
  - the sandbox image `aios-verify:c4db53eb1fce` (master's requirements after #732).
- **When:** 2026-11-23, 06:07-06:37Z. Repeat timings: 686 s, 477 s, 574 s.
- **Records:** `2026-11-23-plan-sonnet-cohort.jsonl` holds all 33 records. Every batch summary reads `unreached_steps: []`, `valid: true`.

## By mission

| mission | r1 | r2 | r3 |
|---|---|---|---|
| tdd-workflow | pass | pass | pass |
| iterative-refinement | pass | pass | pass |
| multi-module | pass | pass | pass |
| error-handling | pass | pass | pass |
| data-pipeline | **fail** | pass | pass |

- `tdd-workflow`'s red phase is intact in every repeat: step 1 expects `verified_failure` and got it.
- `multi-module` passed all three repeats. On 2026-11-22 it failed all three, and #731 fixed the two gaps behind that.

## The failure: `data-pipeline`, step 2, repeat 1 (`verified_failure`)

Step 2 asks the model to add error handling to `pipeline.py`: a failing step raises `PipelineError`.

- **What happened.**
  - The model edited `pipeline.py`, and the audit trail records the edit as applied (06:15:49Z). The tests passed (7 of 7).
  - It then edited `test_pipeline.py` to import `PipelineError`. Every run after that failed at collection, because `pipeline.py` has no `PipelineError`.
  - The model ran pytest nine more times, including `pytest -v` and `pytest --collect-only`, and never edited `pipeline.py` again.
- **Why: the plan never saw the failure.**
  - The repeat's privacy audits show `redacted_tool_files` rising from 3 to 10 across those calls, one for each failing run.
  - Re-running the real report through `PrivacyFilter(scope_files_shown=True)` (the plan route's filter) turns it into `[FILE CONTENT REDACTED: file]` whole. A pytest failure report quotes the failing source lines, and the filter treats a code-shaped tool result as a file.
  - A short passing report keeps its text. So the model saw its tests pass, but never saw why they failed.
- **Whose gap.** This is a GAGOS gap, not a measured model failure. #731 labels only the file tools' results (`read_file`, `read_directory`, `create_file`, `edit_file`). The `verify` tool's report is deliberately not labelled, and `tests/test_plan_sees_scope_files.py` asserts that.
- **2026-11-22.** That cohort's one `data-pipeline` failure (repeat 2) shows the same pattern:
  - the same `9 passed, 3 failed` report six times in a row, while that repeat's `redacted_tool_files` rose from 0 to 16;
  - its record called it a model failure. Before #731 that count also included write results, so it is consistent with this gap, not proof of it.

## What this is not

- It does not meet the bar: two clean repeats in a row, not three.
- It is not the September [5,5,5] Gemini cohort, and it is not compared with it as if it were.
- It runs on the harness that no longer voids turns and retries them into passes (#726, #729); every batch summary is valid, with no step unreached.
