# R15 Acceptance Report

## Status: NOT ACCEPTED — executable evidence repair checkpoint

### Requirements Validation
- **Local R15 runtime matrix:** 12 executable disposable probes pass locally; evidence is recorded in `runtime-proof.json`.
- **Backend package gate:** 3,235 passed, 8 skipped, 88% coverage locally; this is not hosted CI or CodeQL evidence.
- **Provider boundary:** The direct swarm cloud-client construction violation is repaired and its architecture test passes.
- **Durable maintenance findings:** Restart persistence, verifier-only resolution, and reappearance reopening pass in a disposable SQLite store.
- **Benchmark:** Blocked before execution because all installed 2–3B local clerk candidates failed qualification/admission; `benchmark-results.json` records the 30-task fixture set and makes no completion claim.
- **Real model qualification:** Executed against installed `qwen2.5-coder:3b`, `llama3.2:3b`, and `qwen2.5-coder:1.5b-base`; all candidates were rejected by one or more schema/refusal gates. No model is admitted; evidence is recorded in `model-qualification-redacted.json`.
- **Private Executor:** Unavailable on the current laptop; hosted/package proof remains required.
- **Hosted CI:** Green on source tip `e1d8de0` in run `29636436923`, including all backend OS matrices, frontend tests/build, aggregate backend, release-authority, hosted private-Executor topology/isolation/strict runtime, SBOM, license inventory, and evidence upload.
- **CodeQL:** Green on source tip `e1d8de0` in run `29636442316` for Python, JavaScript/TypeScript, and Actions; the executor model-pack validation also passed.
- **Non-builder handoff:** Not yet available; the coordination lease is currently unowned and no independent verdict is recorded.

### Sign-off
- **Architectural Scope**: R15 evidence repair in progress
- **Security Envelope**: Local affected gates green; real model qualification correctly rejected; independent review pending
- **Frontend Sync**: Existing Antigravity artifacts retained; clean-room UX proof pending
- **Operator Review**: Pending; R15 acceptance and public R16 readiness remain locked.
