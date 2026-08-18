# Organ 44 — endurance re-measured: 0.611 → 0.703, still RED

- **Measured**: 2026-08-18 on `cede520b`, `gemini.gemini-2.5-flash` via Vertex ADC
- **Verdict**: **RED** — success rate `0.703` against the `0.80` bar
- **Blocker 3 stays open**, now on the merits rather than on a crashed run

```
[endurance] RED
  turns          : 37
  success rate   : 0.703  (threshold 0.80)
  latency        : p50=32.3s p95=111.7s baseline_p95=57.7s
  latency stable : True
  backend memory : 556.5MB -> 563.8MB (peak 567.1MB, growth 7.3MB)
  duration       : 30.7 minutes
```

| | recorded 2026-08-16 | this run |
|---|---|---|
| success rate | 0.611 | **0.703** |
| turns | 18 | **37** |
| latency stable | — | **True** |
| memory growth | not measured (see #226) | **7.3MB** |
| duration | 1794.5s | 1842s |

## Two of the three green conditions are met

Endurance is green only when success-rate **and** latency-stability both hold.
Latency is stable — p95 111.7s against a 57.7s baseline, inside the 2× rule —
and memory over 30 minutes grew **7.3MB**, essentially flat. The system endures.
What misses is the model's output quality.

37 turns against the previous 18 is double the sample in the same window, and
turns got *faster* despite `AIOS_AGENT_MAX_ITERS` rising 5 → 16. The agent now
finishes rather than grinding into the cap.

## The failures are not diffuse

26 `[VERIFY PASS]` / 11 `[VERIFY FAIL]`, and the failures concentrate on two of
the eight prompts:

| task | failures | shape |
|---|---|---|
| `count_vowels` | 5 | uppercase / mixed-case / symbols |
| `deep_get` | 4 | empty path, None-valued path |
| other | 2 | — |

Same shape the golden cohort shows and the 2026-08-16 record described: the
model writes a test asserting one behaviour and an implementation with another.
`test_retry_zero_attempts_raises_error` is the clearest instance — the test
demands a raise on zero attempts, the code returns instead.

This is a specification-ambiguity failure more than a competence failure. Both
clusters are prompts where the correct edge-case behaviour is genuinely
underdetermined by the prompt text: is `deep_get(d, "")` a miss or the whole
document? Are uppercase vowels vowels? The model picks one reading for the test
and another for the code.

**That is worth knowing before anyone "fixes" it by raising the bar or editing
the prompts.** Editing the prompts to remove the ambiguity would raise the score
without the system improving, which is exactly the move this organ exists to
refuse.

## Configuration caveat — read before comparing

This run used `AIOS_LLM_MODEL=qwen2.5:3b`, **not** the shipped default
`llama3.1:8b`. The agent model was `gemini-2.5-flash` in both runs; what changed
is the local model the default-on aliveness organs (CRAG, reflection,
narrative/facts extraction) invoke per turn.

The default could not be used, and that is itself a finding:

**`llama3.1:8b` is 5.6GB resident and is pulled per turn even when every agent
turn is cloud-routed.** On this 16GB host, memory reached 96.1% within a minute
and two prior attempts died. Verified during those runs: routing was correct
throughout — Vertex calls to `2.5-flash`, no local inference in the agent path —
while `llama-server` loaded alongside the backend regardless.

So the honest reading is that the shipped default configuration cannot sustain a
30-minute endurance run on 16GB. `qwen2.5:3b` (2.2GB resident) leaves ~4.6GB
headroom and the run completed cleanly with flat memory.

## A harness defect this exposed

When the host runs out of memory, the endurance harness reports
`ConnectionResetError(10054)` — **indistinguishable from a deliberately killed
backend**. The 2026-08-16 record already documents a `ConnectionReset` at turn 6
correctly attributed to *"my process handling, not a system fault"*. Both
diagnoses were right for their own run, and neither could have distinguished the
other's cause from the symptom.

An endurance harness whose job includes memory stability should name resource
exhaustion when it sees it rather than surfacing a transport error.

## Status

Blocker 3 is **not discharged**: 0.703 < 0.80. It is now a measured shortfall
from a complete 30.7-minute run rather than an unmeasured unknown, and the two
system-level halves of the verdict (latency, memory) are green.
