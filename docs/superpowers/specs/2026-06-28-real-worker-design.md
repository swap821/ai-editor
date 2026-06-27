# The Real Worker — think, act, react (bounded self-correcting loop)

Date: 2026-06-28
Status: Approved (operator), ready for implementation
Branch target: `council-runtime-v01` → fast-forward `master` on green (session convention)

## Goal

Replace the deterministic worker's hardcoded heartbeat (`worker_entry.py` appends
`// Council Runtime deterministic worker heartbeat`) with a real LLM-driven worker
that **accomplishes the mission**: generate the edit, apply it, verify it, and
self-correct on failure — all inside the worker's existing scrubbed sandbox.

## Non-goals (YAGNI)

- Multi-file missions / cross-file orchestration (single target file this slice).
- Diff/patch application (full new-file content only).
- Per-edit human approval (the MissionContract is already King-approved; RED is
  refused upstream).
- Changing the worker's isolation model or the frozen security spine.
- A product endpoint to originate missions (separate slice).

## Architecture

`run_worker` (worker_entry.py) dispatches on a flag:
- `config.WORKER_REASONING` **off (default)** → today's deterministic path,
  byte-for-byte unchanged (CI stays deterministic; no Ollama needed).
- **on** → `_run_llm_worker(runtime, contract, started_at)`.

The worker still runs in the `ControlledSubprocessBackend` sandbox (scrubbed env,
`AIOS_WORKER_SANDBOX=1`, scoped FS). This slice changes *what the worker does
inside the box*, not the box.

## The loop (bounded, terminating)

```
read target (scoped read_file)
attempt = 0
while attempt <= max_repairs:
    purpose = "plan" if attempt == 0 else "repair"
    new_content = runtime.request_change(prompt, purpose=purpose)   # via gateway
    write_file(target, new_content)                                 # scoped
    results = [run_command(split(c)) for c in verification_commands] # allowlisted
    if all returncodes == 0 (or no verification commands): -> completed/GREEN
    else: capture failure into the next prompt; attempt += 1
-> if never passed: needs_revision (RED→ honest partial), keep last attempt+evidence
```

- Prompt (attempt 0): goal + current file content + "return the COMPLETE new file
  content, nothing else."
- Prompt (repair): goal + current (post-edit) content + the failing command(s)
  stdout/stderr + "fix it; return the COMPLETE new file content."
- `max_repairs` = `config.WORKER_MAX_REPAIRS` (default 2 → ≤3 total attempts).
- Each LLM call is token/timeout-bounded by the gateway; every tool call goes
  through `_begin_tool` which enforces `contract.max_steps`. Termination guaranteed.
- The forbidden-probe self-check (proves scope enforcement) runs as today.

## Components

### `worker_api.py` — `request_change`
`request_change(self, prompt: str, *, allow_cloud: bool = False, purpose: str = "plan") -> str`
- Thin wrapper over `intelligence_gateway.request(IntelligenceRequest(purpose=...))`,
  mirroring `request_plan`'s evidence recording. `purpose` ∈ {"plan","repair"}
  (both already in the IntelligenceRequest Literal — no schema change).
- Returns the response text (already secret-redacted by the gateway).

### `worker_entry.py` — `_run_llm_worker`
- Owns the loop above; returns `(status, summary, risk_after, evidence)`.
- `run_worker` calls it when `config.WORKER_REASONING` and the worker has a usable
  gateway; otherwise the existing deterministic path.
- Records per-attempt evidence: attempt index, verification results, model route.

### `config.py`
- `WORKER_REASONING: bool` (env `AIOS_WORKER_REASONING`, default **False**).
- `WORKER_MAX_REPAIRS: int` (env `AIOS_WORKER_MAX_REPAIRS`, default 2).

## Safety (reuses existing controls; no new privilege)

- Edits → scoped `write_file` (workspace + `allowed_files`); LLM content cannot
  escape the contract's already-approved file set.
- Commands → `run_command` allowlisted to `verification_commands`.
- Gateway scrubs secrets from prompts, redacts responses, forces local on
  RED/secret, budget-guards. Worker never sees providers/keys.
- **Honest failure:** reasoning requested but gateway unavailable
  (`IntelligenceGatewayError`) → status `failed` ("reasoning unavailable"), NOT a
  silent heartbeat that falsely reports success.

## Error handling

- Gateway error on attempt 0 → `failed` (reasoning unavailable).
- Gateway error mid-loop → stop, report `needs_revision` with attempts so far.
- ContractViolation (e.g., LLM proposes an out-of-scope path) → blocked + recorded
  (worker_api raises; loop reports `contract_violation`), never escapes scope.
- Verification command failure → drives the repair loop; exhaustion →
  `needs_revision`.

## Testing (deterministic, no network)

Unit-test `_run_llm_worker` in-process with a **fake gateway** injected into
`WorkerRuntime` (it already accepts `intelligence_gateway=`):
1. **Success first try** — fake returns valid content; verification passes →
   `completed`, file changed.
2. **Self-correction** — attempt-0 content lacks a required marker; a real
   `verification_command` (`python -c` checking the file) fails; repair content
   includes the marker → passes. Asserts ≥2 attempts and final `completed`.
3. **Exhaustion** — fake always returns failing content → `needs_revision`, attempts
   == max+1, last content persisted.
4. **Scope safety** — even with reasoning on, a write to a forbidden path is blocked
   (ContractViolation recorded); the LLM cannot widen scope.
5. **Gateway-unavailable** — fake raises `IntelligenceGatewayError` → `failed`,
   not a false success.
6. **Flag-off determinism** — `WORKER_REASONING` false → existing heartbeat path,
   existing subprocess test unchanged.

Full backend suite + 85% floor green; frozen security spine untouched.

## Rollout

Ships **off by default** (`AIOS_WORKER_REASONING=false`). Production enables it
(with a local Ollama or policy-permitted cloud) to get a worker that thinks and
acts; until then, behavior is exactly today's deterministic worker.

## Adversarial review outcome (2026-06-28)

4-angle adversarial review. Containment held: no filesystem-scope escape, no
command injection, no secret/provider leakage (worker gateway `cloud_clients={}`),
guaranteed termination. Two findings were fixed before merge:
- **[HIGH] empty `verification_commands` → false `completed`/GREEN.** The LLM worker
  now raises `ContractViolation` when no verification command exists — an
  unverifiable edit can never be reported completed. (`worker_entry._run_llm_worker`)
- **[MEDIUM] no size cap on written content (DoS).** Added `WORKER_MAX_FILE_BYTES`
  (default 1 MB); oversized proposals are refused before write.

### Tracked follow-ups (not blockers; scope-bounded)
- **Verifier-executed write targets (exec channel).** If the target is a
  pytest-imported file (`conftest.py`, `test_*.py`), the worker writes LLM content
  that the verification step then executes — bounded to the workspace inside the
  already-scrubbed worker subprocess, but real. Fix later: run verification via the
  isolated execution backend and/or flag/approval-gate contracts whose write
  surface intersects the verifier's import surface; tighten the worker_api
  directory-prefix write match to explicit entries/globs.
- **Step-budget exhaustion mislabels as `contract_violation`/RED** instead of
  `failed` (cosmetic honesty; `worker_api._begin_tool`).
- **Deterministic-twin** has the same vacuous-pass on empty verification, but it
  writes a fixed heartbeat (not hostile content) — low risk, pre-existing.
