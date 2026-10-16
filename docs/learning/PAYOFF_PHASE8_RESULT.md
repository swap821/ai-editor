# Learning payoff: Phase 8 judged result

*2026-10-12. Registered under D4, D5 and D8–D11 (`PAYOFF_PREREGISTRATION.md`).
Trails: `payoff_phase8_cloud_trail.json`, `payoff_phase8_7b_trail.json`. Verdict
file: `payoff_judged_result.json`, written by `tools/judge_payoff_family.py`
from those trails, and pinned to them by `tests/test_judge_payoff_family.py`.*

## Verdict: H1 not met. No harm, and hardening kept utility.

The registered family is {H1-cloud, H1c-cloud, H1-7B}, Holm-corrected at
family-wise α = 0.05. A member is met only if its direction is positive **and**
its Holm-adjusted p is below 0.05.

| Member | Question | Pairs | Targets where ON earned more / fewer | Earned samples, ON vs comparison | Raw p | Holm p | Met |
|---|---|---|---|---|---|---|---|
| H1-cloud | NOVEL: ON vs OFF | 83 | 17 / 11 | 64 vs 56 of 249 | 0.434 | 1.000 | no |
| H1c-cloud | NOVEL: ON vs PLACEBO | 83 | 12 / 10 | 64 vs 64 of 249 | 1.000 | 1.000 | no |
| H1-7B | NOVEL: ON vs OFF | 18 | 0 / 1 | 1 vs 2 of 18 | 1.000 | 1.000 | no |

- **H2, harm (per cohort, uncorrected):** not violated in either cohort.
  - Cloud: 17 / 11, p = 0.434.
  - 7B: 0 / 1, p = 1.0.
- **H3, hardening preserves utility (per cohort):** not violated in either cohort.
  It compares the ON arm with that cohort's own baseline, on targets whose ON arm
  reached the model in both runs.
  - Cloud: 85 targets; this run was better on 12 and the baseline on 10, p = 1.0.
  - 7B: 19 targets; 0 against 2, p = 0.5.

## The runs

| | Cloud | 7B |
|---|---|---|
| Run | `20261012T043600-0863795b` | `20261012T074959-65c6f335` |
| Model | Bedrock `qwen.qwen3-coder-30b-a3b-v1:0`, 420 s timeout | `ollama.qwen2.5-coder:7b`, 420 s timeout |
| Design | 150 frozen targets (`payoff_targets_cloud_baseline.txt`), `--novel-only`, calibration excluded, K = 3, OFF / ON / PLACEBO | 30 frozen targets (`payoff_targets_phase0.txt`), K = 1, OFF / ON: Phase 0's design, unchanged as D4 says |
| Measured code | corpus `c5989c5f` | corpus `092fb0f9` |
| Harness | `c5989c5f` | `c5989c5f` |
| Registration hash (LF-normalised) | `9e532d9c5de8…` | `9e532d9c5de8…`, equal to the committed registration's |
| Memory | a copy of the operator's live store, made 2026-10-12 | same copy |
| Admitted to the run's principal | 11 lessons of 34 (ids 111–121), 0 skills | same |
| Positive control | passed | passed |
| Comparable | 85 / 150; 83 NOVEL, 2 SEEN | 19 / 30; 18 NOVEL, 1 SEEN |
| Not comparable | 65, all "recall returned nothing", so both arms would see identical prompts | 9 for empty recall; 2 because an arm never reached the model |
| Transport retries | 0 | 0 |
| Prompt length (median chars, NOVEL) | OFF 1,855; ON 2,357; PLACEBO 2,191 | |

- **The principal:** both runs read the store as `operator:e2f262a7…`, the
  operator's real principal. D8 had named `operator:swap`, which owns nothing,
  so the census would have reported zero admitted lessons.
- **Two measured commits:** the code differs between the two runs only by #470
  (`tools/import_practice_lessons.py`, `tools/readmit_learning.py` and a test),
  with zero files under `aios/`. The registration measures `origin/master` at
  the time of each run, which is what each run did.

## Confidence and shape (cloud, NOVEL, context beside the registered test)

The intervals come from 20,000 bootstrap resamples over the 83 targets, seed
20261012.

| Comparison | Difference (points) | 95% CI |
|---|---|---|
| ON vs OFF | +3.2 | [−3.6, +10.0] |
| ON vs PLACEBO | 0.0 | [−6.8, +6.8] |
| PLACEBO vs OFF | +3.2 | [−3.2, +9.6] |

- **Mostly all-or-nothing targets.** OFF earned 0 of 3 on 58 targets and 3 of 3
  on 13; only 12 were mixed.
- **Recall was thin.** A median of 1 lesson was recalled per ON prompt, and at
  most 5.

## What this says

- **No measurable benefit from this memory, on either model.**
  - The cloud model's ON arm earned 3.2 points more than OFF. PLACEBO, unrelated
    stored lessons of matched size, earned exactly as much as ON.
  - The small lean towards ON is therefore not the lessons' *content*. It is
    consistent with a prompt-length effect, or with noise.
  - Effects above about +10 points are unlikely. A benefit of a few points is
    neither shown nor ruled out.
- **Memory is the bottleneck, not the model.**
  - Only 11 lessons were admitted. 65 of 150 cloud targets and 9 of 30 7B
    targets recalled nothing at all.
  - Where something was recalled, it was usually one lesson.
- **The 7B member was at the floor.** `qwen2.5-coder:7b` earned 1 to 2 of 18
  NOVEL samples in either arm. With one sample per arm, H1-7B could only have
  detected a very large effect.
- **Nothing here suggests memory hurts.** H2 is not violated in either cohort.

## Disclosures

- **An interim look.** At 143 of 150 cloud targets, the operator asked for
  progress, and a raw per-arm tally was computed and reported. The stopping
  rule (every frozen target) was fixed before the run and was not changed. The
  run was neither stopped nor extended.
- **H3's computation.** No tool for H3 existed before this run.
  `tools/judge_payoff_family.py` compares the ON arm's earned samples per
  target with the cohort's baseline trail, using the harness's own
  `mcnemar_exact` (K = 1) and `sign_flip_exact` (K > 1). It skips targets whose
  ON arm did not reach the model in both runs, because the Phase 8 cloud run
  makes no model call on an empty-recall target.

## Next (not part of this verdict)

This verdict stands as registered. The next experiment is D12, registered
before it runs:
- **A strong teacher:** the strongest Bedrock model writes the lessons (#479).
- **The student unchanged:** the same student model, practising on targets
  disjoint from every frozen list.
- **Review:** lessons are fact-checked, and the operator signs re-admission.
- **Then a new judged run.**
