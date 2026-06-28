# Phase 2b — containerize the worker's verification execution

Date: 2026-06-28
Status: Approved (operator; "containerize run_command" scope)
Branch target: `council-runtime-v01` → fast-forward `master` on green
Roadmap: Phase 2 follow-up (the opt-in Council worker ran verification host-side).

## Goal

Pull the worker's arbitrary-command execution inside the Phase 2 container
boundary. `WorkerRuntime.run_command` runs the MissionContract's
`verification_commands` via bare `subprocess.run` on the host — the exact
host-execution gap the Phase 2 escape-review flagged. Route it through the
locked-down container instead (container-by-default, host a loud opt-out,
fail-closed-degrades), so a worker's verification cannot touch the host outside
the boundary by default.

## Scope (operator decision: run_command only)

Containerize ONLY `run_command` (the only place a worker executes an arbitrary
command). Deliberately unchanged:
- `write_file` — already scope-locked to `allowed_files` under `workspace_root`.
- `request_change` / `request_plan` — LLM API calls, not code execution. They stay
  on the host worker process so the reasoning worker keeps local-LLM (Ollama)
  access; a `--network none` container would cut it off. (Whole-worker isolation +
  a network policy is a deferred follow-up — not this slice.)

## Design

### 1. Backend-selected command runner (`aios/runtime/worker_api.py`)
`WorkerRuntime.__init__` gains `command_runner: Runner | None = None` (the
`aios.core.executor.Runner` protocol: `(command_str, *, cwd, env, timeout_s) ->
(stdout, stderr, returncode)`). `run_command` keeps all existing validation
(empty / non-string / `_command_allowed` allowlist / redaction / evidence), but
replaces the bare `subprocess.run` with:

- `runner = self._command_runner or _runner_for_backend(config.APPROVED_EXECUTION_BACKEND)`
  - `"container"` → `DockerRunner()` (the Phase 2 hardened runner: `--network none`,
    `--read-only`, `--cap-drop ALL`, `no-new-privileges`, non-root, pids/mem/cpu caps,
    `noexec` tmpfs), with `workspace_root` bind-mounted at `/workspace`.
  - `"host"` → `aios.core.executor._default_runner` (the explicit dev-only opt-out;
    bounded output, structured argv).
  - anything else → `None` → fail-closed refusal.
- Run with `cwd=str(self.workspace_root)`, a sanitized env (`executor._sanitise_env()`),
  `timeout_s=contract.timeout_seconds`.
- **Fail-closed:** a runner exception (e.g. docker CLI missing) → `returncode != 0`
  with a clear `[verification backend unavailable] …` stderr — NEVER a silent host
  fallback. A down daemon already yields a non-zero docker exit (fail-closed
  naturally). `subprocess.TimeoutExpired` propagates as today (unchanged semantics).

The command is passed as `" ".join(command)` (already an allowlisted argv;
verification commands are simple). The result payload shape
(`{command, returncode, stdout, stderr}`) and redaction/cap are unchanged.

### 2. Propagate the backend setting into the worker (`aios/runtime/backends.py`)
The worker subprocess env allowlist (`_restricted_environment`) currently drops
`AIOS_APPROVED_EXECUTION_BACKEND`, so a worker would always read the
container-by-default — even when the operator set `host`. Add the non-secret
execution-backend vars to the allowlist so the worker honors the host's config:
`AIOS_APPROVED_EXECUTION_BACKEND`, `AIOS_CONTAINER_RUNTIME`, `AIOS_CONTAINER_IMAGE`,
`AIOS_CONTAINER_MEMORY_MB`, `AIOS_CONTAINER_CPUS`, `AIOS_CONTAINER_PIDS_LIMIT`.
(These are configuration, not secrets; the secret scrub still strips everything else.)

## Error handling / fail-closed
- Container configured but unavailable → verification returncode != 0 → the worker's
  self-correction loop sees a failed check; the mission cannot report a hollow pass.
  Never a host run.
- Unknown backend value → refuse (non-zero), never run.
- Host opt-out → runs on the host via `_default_runner` (documented dev-only).

## Testing
- **Container routing:** with `APPROVED_EXECUTION_BACKEND=container`, `run_command`
  dispatches through an injected runner with `cwd == workspace_root`; assert (via a
  real `DockerRunner` + a fake `_bounded_run`) the docker argv carries the hardening
  flags and mounts the workspace; the host path is never taken.
- **Fail-closed:** an injected runner that raises → `run_command` returns
  `returncode != 0` and records the failure in evidence; no host fallback.
- **Host opt-out:** `APPROVED_EXECUTION_BACKEND=host` → runs via the host runner.
- **Env propagation:** `_restricted_environment()` includes
  `AIOS_APPROVED_EXECUTION_BACKEND` (and the container vars) when set.
- Existing worker tests (`test_runtime_real_worker`) that run real verification
  in-process pin `APPROVED_EXECUTION_BACKEND=host` (they test the think→act→verify
  loop, orthogonal to the isolation backend; no Docker in CI).
- Full backend suite + 85% floor; frozen security spine untouched.

## Rollout
No flag/migration. Container-by-default already governs the Executor; this extends
it to the worker's verification. README updated: the worker's verification now runs
inside the boundary by default (Phase 2b), host is the dev-only opt-out. Whole-worker
isolation + LLM network policy remains a future slice.
