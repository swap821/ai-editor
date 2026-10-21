# D12 judged result: cloud members

*Dated evidence, written 2026-10-21. Do not rewrite: add a superseded banner if
the local members change the family picture. Design:
`PAYOFF_PREREGISTRATION.md` D12. Practice, fact-check and re-admission:
`D12_PRACTICE_AND_FACTCHECK_RESULT.md`. Trail: `payoff_d12_cloud_trail.json`.*

## Status

| Member | Question | Status |
|---|---|---|
| H1-cloud-D12 | NOVEL targets: ON vs OFF | **run, not met** |
| H1c-cloud-D12 | NOVEL targets: ON vs PLACEBO | **run, not met** |
| H1-local-D12 | NOVEL targets: ON vs OFF, local student | not run (the operator decides; about 2–3 days) |
| H1c-local-D12 | NOVEL targets: ON vs PLACEBO, local student | not run |

The family is Holm at family-wise α = 0.05 over all four. A member is met only
if its direction is positive and its Holm-adjusted p is below 0.05 (D4). Holm
never lowers a p-value. Both cloud members have raw p of 0.72 or above, so
**neither can be met, whatever the local members show.** The family verdict waits
for the local run; `tools/judge_payoff_family.py` gains the D12 family when it
exists.

## The run

| | |
|---|---|
| Run id | `20261021T033650-0043a38f` |
| Ran | 2026-10-21, 09:06 to 17:08 IST (about 8 h) |
| Model | `qwen.qwen3-coder-30b-a3b-v1:0`, unchanged from Phase 8 |
| Route | AWS account 424123861008, us-east-1, the operator's IAM key (the 2026-10-18 amendment) |
| Harness and corpus | `501c2536` (master) |
| Pre-registration sha256 | `e847fe16742d1ded83652913114c718cacb431d3673fc688ce3b7c79cc0572a8` |
| Targets | the 150 frozen cloud-baseline targets, with the 20 calibration targets excluded, K = 3 per arm |
| Store | a copy of the operator's live store made after his re-admission: 117 lessons admitted (Phase 8: 11), 0 active skills |
| Comparable | **150 of 150**: no model errors and no hollow runs |

## Results

| | Pairs | ON earned | Other arm earned | Targets ON did better | Targets ON did worse | Raw p | Direction |
|---|---|---|---|---|---|---|---|
| **H1-cloud-D12**: ON vs OFF, NOVEL | 141 | 114 / 423 | OFF 114 / 423 | 18 | 16 | **1.000** | zero |
| **H1c-cloud-D12**: ON vs PLACEBO, NOVEL | 141 | 114 / 423 | PLACEBO 109 / 423 | 21 | 16 | **0.721** | positive |
| H2 harm (cloud, all pairs) | 150 | 126 / 450 | OFF 125 / 450 | 20 | 18 | 1.000 | **no harm** |
| SEEN (context only) | 9 | 12 / 27 | OFF 11 / 27 | 2 | 2 | 1.000 | — |

All p-values are the harness's own exact sign-flip tests over targets.

**Against Phase 8's cloud run** (same model and same targets), the D12 store did
not move the result:

| | Phase 8 | D12 |
|---|---|---|
| Lessons admitted | 11 | 117 |
| Targets with no lesson recalled | 65 of 150 | **0 of 150** (every target recalled 5) |
| ON vs OFF, by target | 17 vs 11 (p = 0.43) | 18 vs 16 (p = 1.00) |
| ON vs PLACEBO, by target | 12 vs 10 (p = 1.00) | 21 vs 16 (p = 0.72) |

## What this says, honestly

- **More lessons, and truer ones, did not help the cloud student.** Every one of the 150 targets now recalled lessons, where Phase 8 left 65 empty. The store was 10× larger and fact-checked: 5% false, against D11's 21–40%. ON and OFF still earned exactly the same: 114 of 423 each.
- **Content leans positive, but within noise.** Real lessons beat a placebo of the same size on 21 targets and lost on 16 (p = 0.72). It is the right direction for "what the lesson says matters", but far from evidence.
- **No harm.** Lessons did not make the student worse.
- **This matches the prediction stated before any number.** The pre-registration said, before the run: "Cloud: the effect may still be small. The student is a capable model, and most cloud targets were all-or-nothing in Phase 8." 107 of 141 novel targets tied between ON and OFF.
- **What is still open.** The pre-registration names the local student as the member "most likely to show a benefit, if there is one", because it has more headroom. That member has not been run.

## Observations

- **`can_drive_tools`: earned 7 of 9 in Phase 8, 0 of 9 here, with unchanged code.**
  - In every arm the model wrote a test that builds `ModelPassportV1(tool_protocol_status="verified")` with a single field. The class requires about 7 more, so validation fails before the test runs. Phase 8's OFF arm made the same error in 2 of 3 samples.
  - In Phase 8, both ON and PLACEBO earned 3 of 3: some prepended text steered the model to a valid construction. Here, a different store's recall did not.
  - Not an instrument fault. It is one more sign that the text prepended to the task changes behaviour whether or not it is relevant: the same position effect PLACEBO exists to separate from content.
- **Which lessons were recalled per target is not in the trail.** Only the count is recorded (5 on every target). So this result cannot show whether recall varied by task, or returned similar lessons everywhere (the Phase 8 calibration finding, D9). Recording the recalled ids is a harness change worth making before the local run.
- **Attempts took 13–23 s**, slower than Phase 8's ~10 s, through the new account and region. Run time was about 8 h, not the 3 h first estimated.
