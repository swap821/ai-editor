# Organ 44 — four models, fifteen cohorts: switch to gemini-3.7-flash

- **Measured**: 2026-08-18, golden cohort, 3 repeats per model, fresh instance each
- **Conclusion**: **switch to `gemini-3.7-flash`** (3.000, zero variance)

| Model | runs | scores | mean | spread |
|---|---|---|---|---|
| **gemini-3.7-flash** | 3 | **3, 3, 3** | **3.000** | **zero** |
| gemini-2.5-pro | 3 | 2, 3, 3 | 2.667 | 1 |
| gemini-3.7-flash *(before the flag widenings)* | 3 | 2, 3, 1 | 2.000 | 2 |
| deepseek-r1-0528-maas (Vertex) | 3 | 2, 3, 0 | 1.667 | 3 |
| gemini-3.1-pro-preview | 3 | 1, 1, 1 | 1.000 | zero |

`gemini-3.7-flash` is both the highest mean and the only model to repeat the
same score three times at the top. It is also a FLASH model, so it is cheaper
and faster than the pro it displaces.

## The same model went 2.000 -> 3.000 without changing

Nothing about gemini-3.7-flash changed between those two rows. What changed was
`ALLOWED_CMD_RE`: it stopped refusing `--collect-only`, `--no-header`, `--tb=`
and `-s`. A full mission per run was being lost to how the model formatted its
pytest output.

That is the clearest single demonstration of this session's theme. The benchmark
was measuring the model's pytest habits and reporting the result as capability,
and it did so consistently enough to look like a real 2.000.

## What was refuted along the way

Two claims made earlier the same day, both mine, both wrong:

  * "the agent's missing capability is for sale" -- gemini-3.1-pro-preview,
    newer and nominally stronger, measured 1.000 against 2.5-pro's 2.667;
  * "the bottleneck moved to model correctness" -- it had partly moved to the
    approval gate, which no model change could have fixed.

And a third, stated as a prediction before this final run: that admitting `-s`
would convert "at most one mission", landing near 2.333. It landed at 3.000.

## What it cost to get a number that meant anything

**Eight** distinct infrastructure causes had to be cleared first. Every one
produced a low cohort score that looked exactly like model quality:

| # | Cause | Symptom | Origin |
|---|---|---|---|
| 1 | `GEMINI_LOCATION=us-central1` | 404 — "model doesn't exist" | pre-existing |
| 2 | `thought_signature` not replayed | 400 after first tool call | pre-existing |
| 3 | Raw bytes in the conversation | `TypeError` mid-turn | introduced here |
| 4 | History ending on a model turn | 400 | pre-existing |
| 5 | Allowlist refusing `pytest -v` | 4 of 5 `rejected` | pre-existing |
| 6 | Inherited 1024-token budget | empty turns, all `unverified` | introduced here |
| 7 | Privacy filter corrupting arguments | 400 "Expected a valid JSON object" | pre-existing |
| 8 | Measurement branch missing fix 5 | `rejected` again | introduced here |

Three were introduced while doing this work; five were pre-existing and latent.
Of the pre-existing five, four were invisible because nothing had ever exercised
that path: no Gemini 3.x model had been called, and no OpenAI-compatible
provider had been configured.

**A score is not a diagnosis.** The first four attempts each returned a
confident-looking `0/5` from four unrelated causes. Reporting any of them as
"model X is worse" would have been well-formatted and wrong.

## The correlation that gave the game away

Before the privacy-filter fix, three DeepSeek repeats scored [1, 1, 3]:

    repeat 1: 2 provider errors -> 1/5
    repeat 2: 3 provider errors -> 1/5
    repeat 3: 1 provider error  -> 3/5

Fewer defects, higher score. That is what a contaminated measurement looks like,
and it is why those numbers were discarded rather than recorded.

## Remaining known contaminant, not fixed

`pytest --noconftest training_ground/x.py` is still refused by `ALLOWED_CMD_RE`.
DeepSeek reaches for it; gemini-3.7-flash reached for `-v`; gemini-2.5-pro uses
bare `pytest`. **The allowlist measures a model's pytest habits, not its
capability**, and each model has different habits. One DeepSeek mission was lost
to it here.

Widening it further was not done: the operator authorised `-v` specifically, and
widening an approval gate to raise a score is the move organ 44's plan forbids.
Whether the gate should accept any read-only pytest invocation on a sandbox file
is a decision worth making deliberately — the current boundary is an accident of
which flags happened to be needed first, not a policy.

## Method

Three repeats per model, each against a fresh instance: own port, own
`AIOS_DATA_DIR`, own enrollment, local clerk unloaded between runs. Backends
launched detached so reaping the controlling session could not kill a run.
`AIOS_LLM_MODEL=qwen2.5:3b` throughout (the 5.6GB default cannot coexist with a
cohort on a 16GB host).
