# Learning payoff: calibration result (not judged)

*Run `20260927T134910-94623ddc`, 2026-09-27. Registered under Deviation D4
(`PAYOFF_PREREGISTRATION.md`, sha256 `cb4f882b…` at run time). Trail:
`payoff_calibration_trail.json`. Targets: `payoff_targets_calibration.txt`.
**Calibration numbers never enter a judged test.** They exist to size the
baseline, and they uncovered one design problem, recorded as D5.*

| | |
|---|---|
| Model | Bedrock `qwen.qwen3-coder-30b-a3b-v1:0`, temperature 0.1, 420 s timeout |
| Credentials | from the operator's env file, loaded into the run process only (two names; values never printed or written) |
| Measured code | corpus `f085eb1b` (master at the time) |
| Harness | `d4c264a9` (#397's head; fetch with `git fetch origin refs/pull/397/head`) |
| Design | 20 never-practised targets, 3 samples per arm, OFF / ON / PLACEBO, `AIOS_SKILL_STORE_MODE=pilot` |
| Skill library | 0 active skills at start, so the skill channel was empty |
| Positive control | passed |
| Comparable | 20 / 20; 0 provider errors, 0 throttling retries |

## What it measured

| | Value | Used for |
|---|---|---|
| Repeat disagreement: (target, arm) cells whose 3 samples differed | 5 / 40 = **12.5%** | K (below 5% would have meant K = 1) |
| OFF earned (samples) | 16 / 60 = 27% | base rate |
| ON earned (samples) | 19 / 60 = 32% | context only |
| Median seconds per arm | 12 | time projection |
| OFF per-target earned counts (of 3) | 14 targets 0, 1 target 1, 5 targets 3 | heterogeneity |
| PLACEBO matched | **0 / 20** | see D5 |

ON against OFF, **context only**: ON earned more on 4 targets and fewer on 3.
The exact sign-flip test gives p = 0.72. With one sample per arm this would
read as noise, and that is what it is.

## The sizing rule, applied mechanically (D4)

- **K = 3.** Repeat disagreement of 12.5% is above the 5% threshold.
- **N = 150** never-practised targets, excluding these 20.
- **Projected duration:** 150 × 3 arms × 3 samples × 12 s ≈ **4.6 hours**.
- **Minimum detectable effect:** the registered simulation is used, with its
  heterogeneity fitted to the OFF counts above by maximum likelihood on a grid.
  The fit is OFF logit mean −2.75 with τ = 4.0.
  - At 80% power and α = 0.05: **+6 points**.
  - At α = 0.05/3 (Holm's worst case for a family of three): **+7 points**.
  - **Caveat:** τ = 4.0 is the top of the fitting grid. The OFF outcomes are
    almost all-or-nothing per target (19 of 20 targets were 0/3 or 3/3), so the
    true heterogeneity may be higher still. Treat the MDE as approximate. It is
    reported beside the result and never used to change N.

## What it found about the memory itself

**Recall is not task-specific.** The store holds 7 verified lessons, 12 pending
and 87 superseded. On a read-only check of the run's own snapshot, all 20 tasks
recalled **the same five lessons** (ids 93, 95, 96, 98, 99). With no skill
activated, the skill channel was empty.

So "memory ON" currently means **the same five lessons prepended to every
task**. A payoff measured on this store is the value of that fixed block, not
of per-task transfer.

It is also why D4's placebo (memory recalled *for other tasks*) could never be
drawn. Only 2 verified lessons were left that ON had not already shown. That
failure is the reason for D5.

This is a product finding, not only a measurement one. It belongs with
Phase 4 (recall) and with the learning loop's own growth (7 verified lessons).
It is not fixed here.
