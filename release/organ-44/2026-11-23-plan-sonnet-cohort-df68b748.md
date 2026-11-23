# Organ 44: golden cohort on a plan brain, at `df68b748` (2026-11-23)

**Result: [5, 5, 5] of 5. 15 of 15 mission runs passed, and all three repeats are valid measurements.** That is three consecutive clean 5/5 repeats, the bar set before the 2026-08-19 runs. Organ 44's condition C9 is met.

## How it was run

- **Code:** `df68b748ba7587306542f7d43ca12864eb2be59f`: master `22be4860` plus the two fixes in this branch (`fix/plan-sees-its-test-reports`):
  - his plans see the test reports of `pytest` runs inside GAGOS's scope (`6f9de45a`);
  - a new edit after a landed grant is the model's own, not the grant again (`df68b748`).
- **Model:** `plan.claude-sonnet-5-5`, through the operator's Claude plan, as on 2026-11-22 and earlier on 2026-11-23.
- **Setup, per repeat:** the same harness as those cohorts:
  - a fresh backend on its own port, with its own `AIOS_DATA_DIR`, its own enrollment and throwaway keys;
  - Claude Code's own session variables removed;
  - `training_ground` and `lab` reset between repeats;
  - `python tools/golden_mission_runner.py run --model plan.claude-sonnet-5-5`, from a detached worktree at that commit;
  - the sandbox image `aios-verify:c4db53eb1fce`.
- **When:** 2026-11-23, 10:35-10:59Z. Repeat timings: 485 s, 443 s, 484 s.
- **Records:** `2026-11-23-plan-sonnet-cohort-df68b748.jsonl` holds all 33 records. Every batch summary reads `unreached_steps: []`, `valid: true`.

## By mission

| mission | r1 | r2 | r3 |
|---|---|---|---|
| tdd-workflow | pass | pass | pass |
| iterative-refinement | pass | pass | pass |
| multi-module | pass | pass | pass |
| error-handling | pass | pass | pass |
| data-pipeline | pass | pass | pass |

- Every step's outcome is the one it expected. `tdd-workflow`'s red phase is intact in every repeat: step 1 expects `verified_failure` and got it.
- No step recorded an error. No repeat met the plan's session limit.
- The privacy audits of all 94 plan calls show `redacted_tool_files` at 0.

## How it got here: three cohorts on 2026-11-23

1. **Master `32f961dc`: [4, 5, 5]** (`2026-11-23-plan-sonnet-cohort.md`). The `data-pipeline` failure came from the plan route's privacy filter. It replaced each failing pytest report, which quotes source lines, with `[FILE CONTENT REDACTED]`, so the model never saw the `ImportError` it had to fix. Fixed in `6f9de45a`.
2. **`2879873b`, the first fix alone: [4, 5, 4], repeat 3 invalid** (`2026-11-23-plan-sonnet-cohort-2879873b.jsonl`, 07:28-07:57Z).
   - Repeat 3 is not a measurement. Its last step was never served: the operator's Claude plan hit its session limit at 07:57Z (`Claude Code exited 1: You've hit your session limit`), and the runner marked the batch `valid: false`.
   - In repeat 1 the reports reached the model (0 redactions), and it saw the error and the fix: add `PipelineError` to `pipeline.py`. By its own final answer, it tried four writes (`edit_file` with two anchors, `edit_file` after `run`, and `overwrite_file`), and each came back "already contains the requested replacement; nothing to change". The audit trail agrees: no edit was recorded after its test edit at 07:36:17Z. It ended the turn and asked the operator to add the class by hand.
   - The cause: on a resumed turn, the operator's approved edit to `pipeline.py` landed first, then stayed in `approved_edits`, and `tool_handlers.edit_file` swapped every later edit to that file for it. Fixed in `df68b748`: a grant stands in for the model's args once. A new edit pauses for approval like any other.
3. **`df68b748`, both fixes: [5, 5, 5]**, this record.

## What this is and is not

- It meets the bar on `plan.claude-sonnet-5-5`, the model the operator chose. It is not the September [5,5,5] Gemini cohort, and it is not compared with it as if it were.
- It ran at a branch commit. It counts on master only if that commit reaches master's history, so the branch is merged with a merge commit, not a squash or a rebase.
