# Clerk benchmark: results, 2026-10-12

*Jobs: `clerk_benchmark_v1_1.json` (54 synthetic jobs, 9 profiles × 6; changelog
inside). Tool: `tools/clerk_benchmark.py`. Results: `results/` (each file records
the LF-normalised SHA-256 of the jobs it was graded on: v1 `f6bc8473…`, v1.1
`8c2ba930…`). Re-score them all at once with
`python tools/clerk_benchmark.py --report docs/clerk/results/v1_1_*.json`.*

## Why it exists

The clerk's qualification suite (r15-v3) is pass/fail and saturated. Every
installed local model passed 22/22, so it cannot say which clerk is best or
where a local clerk is weak.

The operator's design needs exactly that: the local clerk always first, and a
powerful cloud clerk "only when needed".

## v1.1 results

| Model | Where | Score | On jobs it saw unaltered | Median time | Injections resisted (of 4) |
|---|---|---|---|---|---|
| `global.moonshotai.kimi-k3` | cloud | 52/54 | **52/52** | 3.5 s | **4** |
| `qwen.qwen3-coder-480b-a35b-v1:0` | cloud | 47/54 | 47/52 | 0.5 s | 3 |
| `mistral.mistral-large-3-675b-instruct` | cloud | 46/54 | 46/52 | 0.4 s | 2 |
| `granite4.2:8b` | local | 47/54 | 47/54 | 4.0 s | 2 |
| `qwen3.5:9b` (think=false) | local | 46/54 | 46/54 | 5.2 s | 1 |
| `qwen2.5-coder:7b` | local | 45/54 | 45/54 | 2.8 s | **3** |

**Per profile:** the best local model against Kimi K3, on the jobs both saw
identically:

| Profile | Jobs | Kimi K3 | Best local | |
|---|---|---|---|---|
| classify | 6 | 6 | 6 | local is enough |
| extract | 6 | 6 | 6 | local is enough |
| explain_route | 6 | 6 | 6 | local is enough |
| summarise_disagreement | 6 | 6 | 6 | local is enough |
| select_skill | 6 | 6 | 6 (qwen2.5-coder) | local is enough |
| validate_structure | 6 | 6 | 6 (granite, qwen3.5) | local is enough |
| cluster | 6 | 6 | 5 | a gap of 1, within noise at n = 6 |
| summarise | 6 | 6 | 5 | a gap of 1, within noise at n = 6 |
| **check_context_completeness** | 4 | **4** | **2** | **the one clear gap** |

## What this says

- **On 6 of 9 profiles, a local clerk equals the best cloud clerk.** Two more are
  within one job. With 6 jobs a profile, a difference of one is noise. Only
  differences of two or more are read as real.
- **Kimi K3 is the best cloud clerk measured.** It got every job it saw
  unaltered right, and it resisted all four injections. It is also the slowest
  (3.5 s) and needs its *global* inference profile. A global profile may serve a
  request from outside ap-south-1, so using it on real operator data is a
  data-residency decision.
- **The local clerks are close together** (45, 46 and 47 of 54), within noise
  of each other. What separates them is **safety**. `qwen2.5-coder:7b` resisted
  3 of 4 injections, granite 2 and qwen3.5 1. Both granite and qwen3.5 picked
  `restart_backend` when injected text told them to.
- **Where the cloud clerk is needed: check_context_completeness**, deciding
  whether a request has a file path, the error text and the reproduction steps.
  - The privacy filter rewrites repo paths to `aios[PATH REDACTED]` before
    anything leaves the machine, so a cloud clerk can never see a path.
  - So a file path should be detected by deterministic code, and the cloud
    clerk should judge only the error text and the steps.
  - That rule is a design input for the cloud clerk. It was not measured here.

## Integrity notes

- **The v1 answer key had defects.**
  - Three free-text jobs required facts their instructions never asked for.
  - One grouping job accepted only one of two defensible answers.
  - Both were found after v1 ran on the three local models.
  - v1.1 states the requirements and accepts both groupings (see its
    `changelog`). **Every model was rerun on v1.1.** v1's results are kept in
    `results/v1_local.json`.
- **Some cloud jobs were not seen as written.** The privacy filter rewrites 2
  of 54 payloads for cloud models (context-01 and context-02 name repo paths).
  The tool scores cloud models on the 52 jobs they saw unaltered as well
  (`cloud_altered_jobs`).
- **One cloud run is invalid.** In `results/v1_1_cloud.json`, the
  `moonshotai.kimi-k3` rows (0/54) are from the plain model id, which Bedrock
  refuses on demand in ap-south-1. Every call failed and none was answered.
  That run is discarded; Kimi K3's result is `results/v1_1_cloud_kimi_global.json`.
- **A stale label in the result files.** The v1.1 files are labelled
  `clerk-benchmark-v1` because the tool wrote a fixed label then. Their jobs
  hash identifies them as v1.1. The tool now reads the version from the jobs
  file.
- **Each local run is a single sample.** Rerunning on v1.1 measured how much a
  score moves between runs.
  - On the 45 jobs v1.1 did not change, the totals moved by at most 1:
    qwen2.5-coder 38 → 38, granite 38 → 39, qwen3.5 39 → 38.
  - Underneath, 1 to 2 individual jobs flipped per model.
  - Run-to-run noise of that size is why a difference smaller than 2 is not
    read as real.

## Next

- **The cloud clerk** (product code) escalates only check_context_completeness,
  and only once the operator applies the `clerical` egress class (#486). The
  file-path check stays deterministic and local.
- **The local clerk:** `qwen2.5-coder:7b` stays the recommended clerk. Its
  quality is within noise of the others, it is the most injection-resistant
  locally, it is the fastest, and it is the smallest. D12's calibration decides
  the local *student* for intelligence; if that is a different model, the
  operator chooses between one model for both roles and two models.
- **Teaching the clerk:** Kimi K3's answers on clerk jobs are the candidate
  examples a clerk-example memory would recall. That gets measured on this
  benchmark with a fresh job set, so no job is taught and tested at once.
