# R15 Acceptance Report

## Status: NOT ACCEPTED — evidence checkpoint

### Requirements validation

- **Runtime proof:** Twelve executable disposable probes pass locally; evidence is recorded in `runtime-proof.json`.
- **Backend package gate:** 3,235 passed, 8 skipped, 88% coverage locally; hosted CI is the authoritative cross-platform gate.
- **Hosted CI:** Run `29640537402` is green on source tip `0aadef86b8fb8161e3d746bf694e574bfbae37ea`, including backend Ubuntu/macOS/Windows, frontend tests/build, aggregate backend, release-authority, hosted private-Executor topology/isolation/strict runtime, SBOM, licenses, and evidence upload.
- **CodeQL:** Run `29640544285` is green on the same source tip for Python, JavaScript/TypeScript, Actions, and executor model-pack validation.
- **Local clerk qualification:** Eleven real Ollama candidate runs were executed against the unchanged R15 suite. Every candidate failed at least one schema, identifier, secret-refusal, or tool-request gate; `qualified_models` is empty and no local model is admitted. Evidence is recorded in `model-qualification-redacted.json`.
- **Benchmark:** The versioned fixture set contains 30 tasks across ten categories. Execution is blocked before task start because the admission set is empty; `benchmark-results.json` records no completion or pass-rate claim.
- **Authenticated cloud-burst:** A bounded real Gemini probe passed through one cloud worker and emitted a `cloud_route` event. The probe used public text only, no tools, and no filesystem writes. Evidence is recorded in `cloud-burst-evidence.json`. Bedrock was not probed because no Bedrock credentials are present.
- **Private Executor:** Unavailable on the current laptop; hosted strict runtime proof remains authoritative.
- **Non-builder handoff:** No independent verdict is recorded. The builder must not self-approve R15.

### Sign-off

- **Architectural scope:** R15 evidence repair remains in progress.
- **Security envelope:** Qualification remains fail-closed; cloud routing was proven only for a bounded public-data probe.
- **Operator review:** Pending; R15 acceptance and public R16 readiness remain locked.
