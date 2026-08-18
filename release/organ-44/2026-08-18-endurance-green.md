# Organ 44 — endurance GREEN: 0.611 → 0.703 → 1.000

- **Measured**: 2026-08-18, `gemini.gemini-3.7-flash` via Vertex (`global`)
- **Verdict**: **GREEN** on all three conditions
- **Blocker 3: DISCHARGED**

```
[endurance] GREEN
  turns          : 24
  success rate   : 1.0     (threshold 0.80)
  latency        : p50 60.8s  p95 138.4s  baseline_p95 89.5s
  latency stable : True    (p95 <= 2x baseline)
  backend memory : 556.7MB -> 559.5MB (growth 2.8MB, peak 561.6MB)
  duration       : 31.5 minutes
```

## Verified, not just reported

A perfect score deserves the scrutiny a zero gets. Checked against the log:

| | |
|---|---|
| turn outcomes | 24 OK, 0 anything else |
| verification verdicts | **24 `[VERIFY PASS]`** |
| strength | **24 `strength=STRONG`** |
| allowlist refusals | 0 |
| provider errors | 0 |
| tracebacks | 0 |

Every verdict is a real pytest run parsed to STRONG by the strength taxonomy
that exists so `echo "5 passed"` cannot forge a pass. No turn was scored on
absent evidence.

## The three measurements

| | 2026-08-16 | 2026-08-18 (first) | 2026-08-18 (this) |
|---|---|---|---|
| success rate | 0.611 | 0.703 | **1.000** |
| turns | 18 | 37 | 24 |
| verdict | RED | RED | **GREEN** |
| latency stable | — | True | True |
| memory growth | not measured | 7.3MB | **2.8MB** |
| agent model | gemini-2.5-flash | gemini-2.5-flash | gemini-3.7-flash |

Fewer turns than the 0.703 run because 3.7-flash spends longer per turn
(p50 60.8s against 32.3s) and completes rather than failing fast.

## What changed, and what deliberately did not

Changed: the agent model (2.5-flash to 3.7-flash, itself the result of measuring
four models); the allowlist admitting output-only pytest flags, twice, by
operator decision; the sandbox conftest that stopped a test importing the module
beside it; the step budget raised from a hardcoded 5.

**Not changed: the prompts, the 0.80 threshold, the verifier, or what counts as
a pass.** This matters. The documented failures at 0.611 and 0.703 concentrated
on `count_vowels` and `deep_get`, both prompts where the edge case is genuinely
underdetermined. Rewriting those two prompts was the obvious way to lift the
number, and it would have raised the score without the system improving. It was
named as forbidden in the earlier record and it was not done.

The number moved because the system got better, not because the bar moved.

## Configuration note

Run with `AIOS_LLM_MODEL=qwen2.5:3b` for the local clerk, not the shipped
`llama3.1:8b`, which is 5.6GB resident and pulled per turn by the default-on
aliveness organs even when every agent turn is cloud-routed. On a 16GB host that
reached 96% memory within a minute and killed two earlier attempts. That default
was changed on this branch for the same reason.
