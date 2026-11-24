# Organ 44: golden cohort on a plan brain, at master `c3bb03d5` (2026-11-23)

**Result: [5, 5, 4] of 5. 14 of 15 mission runs passed, and all three repeats are valid measurements.** The bar is three consecutive clean 5/5 repeats, so it is not met. Organ 44 stays yellow.

## Why this run

- The [5, 5, 5] cohort at `df68b748` (`2026-11-23-plan-sonnet-cohort-df68b748.md`) met the bar. #739's squash merge then orphaned that commit.
- The operator attested it, and `verify_organ_contracts.py` refused the flip. A green organ needs a live-evidence row stamped at its `last_verified_sha`, and that row would have been stamped at a commit off master; tree-hash equality with master (#740) does not stand in for it. The attestation was never committed.
- So this cohort ran at master's own tip, where a row can be stamped.

## How it was run

- **Code:** master `c3bb03d57c531979785191ddcc73f5bf2f3a8e87` (#741), with #739's two fixes.
- **Model:** `plan.claude-sonnet-5-5`, through the operator's Claude plan.
- **Harness:** the same as every 2026-11-23 cohort:
  - three repeats, each a fresh backend instance with its own port, its own `AIOS_DATA_DIR`, its own enrollment and throwaway keys;
  - `training_ground` and `lab` reset between repeats;
  - a detached worktree at that commit;
  - the sandbox image `aios-verify:c4db53eb1fce`.
- **When:** 16:46-17:12Z. Repeat timings: 519 s, 596 s, 434 s.
- **Records:** `2026-11-23-plan-sonnet-cohort-c3bb03d5.jsonl`, all 33 records. Every batch summary reads `valid: true`, `unreached_steps: []`. `redacted_tool_files` is 0 across all 88 plan calls.

## By mission

| mission | r1 | r2 | r3 |
|---|---|---|---|
| tdd-workflow | pass | pass | pass |
| iterative-refinement | pass | pass | **fail** |
| multi-module | pass | pass | pass |
| error-handling | pass | pass | pass |
| data-pipeline | pass | pass | pass |

## The failure: `iterative-refinement`, step 1, repeat 3 (`unverified`)

- **What happened.**
  - Step 1 asks for `sorted_insert.py` and then `test_sorted_insert.py`. The first turn paused for approval on `sorted_insert.py`.
  - The resumed turn landed it; its forced verify reported no sibling test.
  - The model's one reply on that turn began "Creating the test file next; after it is written and approved, I wi…" (the stored reply is cut off there). No call executed: no approval pause, no file, nothing in the audit trail. The turn ended `unverified`.
- **A GAGOS mechanism that fits, not proven.**
  - `aios/core/plan_cli.py:_turn` drops a plan reply's tool call whose `arguments_json` does not parse as a JSON object. It tells neither the model nor the loop, and the turn ends on the reply's text.
  - A `create_file` whose file body carries raw, unescaped newlines is dropped this way. An escaped one is kept; both were checked on the shipped function.
  - The plan CLI runs with `--no-session-persistence` and the harness keeps no reply text, so this run cannot show whether the reply carried such a call. It is a candidate cause, not a measured one.

## What this is

A valid measurement at a master commit: [5, 5, 4], against a bar of three clean 5/5 repeats in a row. The [5, 5, 5] at `df68b748` stands as recorded, at a commit no longer on master.
