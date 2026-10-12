# Best cloud + local intelligence, measured (H8)

*2026-10-11, at the operator's request: "I honestly want the best cloud+local
intelligence." Best is measured here, not named.*

## What was wrong

1. **Models the account can't call were ranked.**
   - Bedrock discovery lists every Claude, GPT-5.x/6 and Grok. This account
     gets "not available for this account" for all of them.
   - The router ranked two denied Claude models among its top four.
   - Each refusal counted as a Bedrock **outage**: one transient failure of
     the top model plus two denied candidates opened the circuit breaker, and
     *every* Bedrock model went dark for the cooldown.
2. **The newest model could not be used at all.**
   - Every call to Kimi K3 failed: "doesn't support the temperature field".
3. **"Best" was never checked.**
   - The router ranks by a heuristic over model names.
   - Its measured-calibration hook had no data on this machine.

## What changed

- **`aios/core/model_availability.py`: a refusal of one model is about that model.**
  - Refusals covered: not available for this account, invalid id, no access,
    retired.
  - The model is skipped for 24 h and is not offered by the router.
  - It never counts against the provider's breaker.
  - Provider-wide failures still trip the breaker: a bad key, an
    organization denying API keys, throttling, timeouts, credits.
- **`BedrockClient`:** a model that rejects `temperature` is retried without
  it, and remembered.
- **`tools/intelligence_benchmark.py`: 50 fixed tasks with mechanical checkers.**
  - 30 basic and 20 hard; coding and reasoning.
  - No model-written code is executed.
  - Errored calls are never scored.
  - Committed before each run.
- **`aios/core/benchmark_rates.json` is the router's calibration prior.**
  - It holds the results per (provider, model, task).
  - Live verified evidence overrides it.

## Results — the operator's account, `ap-south-1`, 50 tasks

Evidence: `release/intelligence/`.

| Model | Coding /25 | Reasoning /25 | All /50 | Median time (basic / hard) |
|---|---|---|---|---|
| Mistral Large 3 (675B) | 25 | 25 | **50** | 1.2 s / 1.9 s |
| Qwen3-Coder-480B | 25 | 25 | **50** | 1.8 s / 2.6 s |
| Kimi K2.5 | 25 | 25 | **50** | 2.0 s / 2.9 s |
| Kimi K3 | 25 | 25 | **50** | 2.6 s / 3.0 s |
| Devstral 2 (123B) | 24 | 25 | 49 | 3.7 s / 5.6 s |
| Qwen3-235B | 24 | 25 | 49 | 2.2 s / 3.0 s |
| gpt-oss-120b | 24 | 24 | 48 | **0.7 s / 1.6 s** |
| DeepSeek V3.2 | 24 | 24 | 48 | 5.3 s / 2.9 s |
| GLM-5 | 23 | 25 | 48 | 2.1 s / 3.2 s |
| MiniMax M2.5 | 22 | 25 | 47 | 3.5 s / 6.7 s |
| Kimi K2-thinking | 15 | 24 | 39 | 4.5 s / 10.1 s |
| **local** qwen2.5-coder:7b | 17 | 20 | 37 | 16.6 s / 20.2 s |
| **local** qwen2.5:3b *(current default)* | 8 | 10 | **18** | 4.2 s / 7.0 s |

**Reading it honestly**

- **The top tier is saturated.** Four models got all 50 right; these tasks
  separate strong from weak, not the very best.
- **The router's top pick per task held up.**
  - Coding: Qwen3-Coder-480B, 25/25.
  - Reasoning: Kimi K2-thinking, 24/25, but slow and weak at coding.
  - General: Mistral Large 3, 50/50 and the fastest.
  - The prior changes the order *below* the top: a model weak at a task is
    demoted for it.
- **The biggest lever is local.**
  - The default local model scored 18/50.
  - `qwen2.5-coder:7b`, already installed, scored 37/50, about 4× slower on
    this CPU.
  - Choosing the default local model is the operator's decision
    (`AIOS_LLM_MODEL`).
- **NVIDIA endpoint (four key sets).**
  - Kimi K3 there timed out.
  - GLM-5.3 works, but took 54 s to say "ok".
  - DeepSeek V4 flash is retired (410).
  - Grok's x.ai team is out of credits.
  - Bedrock is the reliable cloud.

## For the best on this machine (operator)

1. Allow cloud for reasoning and coding (with H7, the constitution is the
   ceiling). This is a guardrail, so set it in your **own environment**, not
   in `.env`, which guardrails ignore by design
   (`tests/test_guardrails_ignore_dotenv.py`). An earlier version of this page
   said `.env`, which was wrong (corrected 2026-10-12). In PowerShell:
   `[Environment]::SetEnvironmentVariable("AIOS_ROUTER_CLOUD_TASKS", "reasoning,coding", "User")`,
   then open a new terminal.
2. Consider `AIOS_LLM_MODEL=qwen2.5-coder:7b` for local and offline work:
   twice the measured quality, at four times the latency.
3. Keep one working Bedrock key in the key file. Line 26's organization
   denies API keys.
4. Set `AIOS_BEDROCK_MODEL` (in `.env`; it is not a guardrail). The shipped
   default, `amazon.nova-lite-v1:0`, cannot be called on demand in
   `ap-south-1`: Bedrock answers "on-demand throughput isn't supported" and
   wants an inference-profile ID. The router gives that default a cold-start
   bonus and swarm burst calls it directly, so every first cloud call failed.
   `AIOS_BEDROCK_MODEL=mistral.mistral-large-3-675b-instruct` (50/50, fastest
   of the top tier) answered with the stored production key on 2026-10-12;
   `qwen.qwen3-coder-480b-a35b-v1:0` answered too.
