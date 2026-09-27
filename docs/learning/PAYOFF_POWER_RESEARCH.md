# Learning payoff: can AWS make the test able to answer? (research, 2026-09-27)

*The operator asked ("we have aws, use it honestly … research about this") how a
cloud model could help prove the payoff honestly. This is the research record. It
changes nothing yet. What it proposes becomes binding only as a Deviation in
`PAYOFF_PREREGISTRATION.md`, signed off by the operator and committed **before**
the run it governs.*

## 1. Why the current test cannot answer

The Phase 0 baseline (`PAYOFF_PHASE0_RESULT.md`) was N = 30 targets, one sample
per arm, on `ollama.qwen2.5-coder:7b`. Both arms earned about 11–14%, and the
run produced **one** discordant pair. The judged test is an exact two-sided
McNemar test at α = 0.05. It cannot reject until there are at least 6
discordant pairs, all in one direction.

The simulation in §4 puts numbers on it. At N = 30 with one sample per arm,
the chance of detecting a real **+10-point** effect is **3–9%**, and **4%** for
+5 points. A null result from that design says nothing about whether memory
helps. It is what the design produces whatever the truth is.

## 2. What the literature says

- **Realistic effects are small.** ReasoningBank (ICLR 2026) reports **+4.6%**
  over a memory-free agent on SWE-Bench-Verified and +8.3% on WebArena. It also
  reports that other memory designs (trajectory memory, workflow memory) gained
  less. A test built to see only large effects will call a real, useful memory
  "no effect".
- **Pair, resample and plan the size before running.** Miller (2024), *Adding
  Error Bars to Evals*, recommends three things:
  - compare conditions **paired**, on the same questions;
  - **resample** each question K times and analyse question-level means, since
    Var(sᵢ) = σᵢ²/K;
  - choose the size from n = (z_{α/2} + z_β)² (ω² + σ_A²/K_A + σ_B²/K_B) / δ².

  Resampling helps only while within-question noise dominates. It pays off
  **only if repeated samples actually differ** (§5).

## 3. What our own data says (no new runs)

The self-corpus ladder has already run this exact task (a pin test graded by
`grade_pin_test`) on Bedrock (`.aios/audit/reverse-engineering-runs.jsonl`,
2026-09-21). All 20 Bedrock `model_error`s come from one run (08:13), which a
since-fixed harness bug sent to `amazon.nova-lite` whatever model was asked.
Excluding that run:

| Model | Reached attempts | Earned | Provider errors |
|---|---|---|---|
| `ollama.qwen2.5-coder:7b` | 54 | 12 (22%) | 0 |
| `qwen.qwen3-coder-30b-a3b-v1:0` (Bedrock) | 21 | 11 (52%) | 0 |
| `qwen.qwen3-coder-480b-a35b-v1:0` (Bedrock) | 12 | 6 (50%) | 0 |

- **About 50% is the best place for a paired test.** It is far from the floor
  (the 7B) and far from the ceiling. A model that earns 95% without memory
  leaves memory nothing to add.
- **The dominant failure is "the model's own test fails on correct code".** That
  is a mistake a recalled lesson could, in principle, prevent. So the task has
  room for memory to matter.
- **Limit:** only 3–4 targets were attempted more than once per model. The data
  cannot estimate how consistent a model is on a single target, so §4 brackets
  it and §5 measures it.

The target pool is 269 functions in `aios/`, about 200 of them never practised.
That is enough for N = 150–200 NOVEL targets.

## 4. Power simulation

Model: each target has a latent logit θᵢ ~ N(0, τ²). OFF succeeds with
σ(θᵢ). ON adds a constant logit shift, calibrated so the average gain is the
stated number of points. The OFF base rate is about 50%. With K = 1 the test is
exact McNemar; with K > 1 it is Wilcoxon signed-rank on per-target mean
differences. There are 1,500 simulations per cell, and power counts only a
significant result **in the positive direction**.

| Effect | τ (target heterogeneity) | N30 K1 | N150 K1 | N150 K3 | N200 K3 | N200 K5 |
|---|---|---|---|---|---|---|
| +5 pts | 1 / 2 / 3 | .03 / .04 / .04 | .11 / .16 / .21 | .36 / .47 / .61 | .44 / .60 / .71 | .64 / .82 / .91 |
| +10 pts | 1 / 2 / 3 | .09 / .09 / .09 | .43 / .57 / .64 | .90 / .96 / .99 | .97 / .99 / 1.0 | 1.0 |
| +15 pts | 1 / 2 / 3 | .15 / .20 / .23 | .79 / .91 / .96 | 1.0 | 1.0 | 1.0 |

**Reading:** N = 150, K = 3 detects a +10-point effect with 90–99% power. A
ReasoningBank-sized +5 points needs about N = 200, K = 5. These K > 1 figures
assume independent samples. §5 is why that assumption must be measured, not
assumed.

<details><summary>Simulation code (seed 20260927)</summary>

```python
import numpy as np
from scipy import stats
rng = np.random.default_rng(20260927)
sig = lambda x: 1 / (1 + np.exp(-x))

def shift_for(tau, pts, m=200_000):
    th = rng.normal(0, tau, m); lo, hi = 0.0, 3.0
    for _ in range(40):
        b = (lo + hi) / 2
        lo, hi = (b, hi) if sig(th + b).mean() - sig(th).mean() < pts / 100 else (lo, b)
    return (lo + hi) / 2

def power(N, K, tau, pts, sims=1500):
    b, hits = shift_for(tau, pts), 0
    for _ in range(sims):
        th = rng.normal(0, tau, N)
        on, off = rng.binomial(K, sig(th + b)), rng.binomial(K, sig(th))
        if K == 1:
            n10, n01 = int(((on == 1) & (off == 0)).sum()), int(((on == 0) & (off == 1)).sum())
            p = stats.binomtest(n10, n10 + n01, 0.5).pvalue if n10 + n01 else 1.0
            hits += p < 0.05 and n10 > n01
        else:
            d = (on - off) / K; nz = d[d != 0]
            p = stats.wilcoxon(nz).pvalue if len(nz) >= 10 else 1.0
            hits += p < 0.05 and d.mean() > 0
    return hits / sims
```
</details>

## 5. The catch: temperature 0.1

The harness samples at the product's `AIOS_LLM_TEMPERATURE` (0.1), which is
close to deterministic. If repeats of one prompt are nearly identical, K > 1
buys almost nothing, and most of the remaining "noise" is **prompt
sensitivity**: any change to the prompt, relevant or not, flips some outcomes
in both directions. Two consequences:

1. **Measure it before choosing K.** A calibration run on targets **disjoint**
   from the judged set measures three things: the OFF base rate, how often
   repeats at 0.1 disagree, and how often ON and OFF disagree. N and K are then
   set from those numbers with Miller's formula. Calibration outcomes are
   published, and never touch a judged target.
2. **Add a placebo arm.** The registration already concedes that "a content
   effect is not separated from a prompt-length effect". A PLACEBO arm gets the
   same number of recalled items at about the same length, drawn by a fixed seed
   from lessons **irrelevant** to the target. ON versus PLACEBO then isolates
   whether the *content* of memory helps, separately from "a longer, different
   prompt". It costs 50% more arms.

## 6. What AWS changes, and what it does not

**It changes:**
- **The chance of an answer.** A roughly 50% model at N = 150–200 can detect a
  +10-point effect; the 7B at N = 30 cannot.
- **Cost.** Bedrock lists Qwen3-Coder-30B-A3B at $0.15 per million input tokens
  and $0.60 per million output. ON prompts are about 1k tokens. Even 1,800 arms
  cost a few dollars.
- **Time.** Grading dominates, at about 35–55 s per arm on this machine, so a
  full run takes 9–14 hours. It runs detached, overnight, with no concurrent
  heavy load.

**It does not change:**
- **A cloud model's payoff is not the 7B's.** It is reported as its own number,
  never as the product's default model's.
- **The lessons were learned from the 7B's failures.** Transfer to another model
  is part of what is being measured, not assumed.
- **The Phase 0 → Phase 8 pairing (H3) exists only for the 7B.** A cloud
  cohort gets H3 only if its own baseline runs **before** Phases 3–7 change
  recall. That is the strongest reason to run it soon rather than at Phase 8.
- **The skill channel in pilot mode** contains only skills the operator has
  activated (D3). Every run records `library_active_at_start`.

## 7. Proposed Deviation D4 (NOT binding until committed to the pre-registration before the run)

| | |
|---|---|
| Cohort | Bedrock `qwen.qwen3-coder-30b-a3b-v1:0`, temperature 0.1, 420 s timeout |
| Judged status | **Operator decision, 2026-09-27: "Both judged, corrected".** The judged family is H1 on the cloud cohort, H1c (content, ON vs PLACEBO) on the cloud cohort, and the 7B's Phase 8 H1. All three are Holm-corrected at family-wise α = 0.05, so none gets a free extra chance at significance. It was fixed before either run, so neither can be picked afterwards. The alternatives recorded against it: cloud primary with the 7B secondary, or keeping the 7B as the only judged number. |
| Targets | NOVEL only, from `collect_targets`' fixed ranking, disjoint from the calibration targets and frozen before any arm runs |
| N, K | Set from calibration with Miller's formula for 80% power at +10 points. Expected range N 150–200, K 1–5. |
| Arms | OFF, ON and PLACEBO, with arm order rotated by target index |
| Tests | H1: ON vs OFF. H1c (content): ON vs PLACEBO. H2 unchanged. K = 1: exact McNemar. K > 1: exact sign-flip permutation on per-target mean differences. H1 and H1c use Holm correction. |
| Baseline timing | Run now, before Phase 3, and again after Phase 7 on the same frozen targets. That gives this cohort its own H3. |
| Credentials | `AWS_BEARER_TOKEN_BEDROCK` and `AIOS_BEDROCK_REGION` go only in the operator's own terminal, which launches the run. They are never on disk, and never seen by the agent. |
| Stopping rule | Unchanged: one analysis at the fixed N, no interim looks. |

**Harness work before any of it runs** (each with a test that fails without it):
- `--samples K`;
- a PLACEBO arm with seeded irrelevant recall;
- `--exclude-targets` for calibration disjointness;
- a transport-only retry for Bedrock throttling that never sees an outcome, with
  retries recorded;
- the new tests and the Holm correction in the summary.

## Sources

- [ReasoningBank: Scaling Agent Self-Evolving with Reasoning Memory (arXiv 2509.25140)](https://arxiv.org/pdf/2509.25140)
- [ReasoningBank (Google Research blog)](https://research.google/blog/reasoningbank-enabling-agents-to-learn-from-experience/)
- [Miller, Adding Error Bars to Evals (arXiv 2411.00640)](https://arxiv.org/abs/2411.00640)
- [Qwen3 Coder 30B A3B pricing on Amazon Bedrock (Future AGI)](https://futureagi.com/llm-cost-calculator/bedrock/qwen-qwen3-coder-30b-a3b-v1-0/)
- [Amazon Bedrock pricing (AWS)](https://aws.amazon.com/bedrock/pricing/)
