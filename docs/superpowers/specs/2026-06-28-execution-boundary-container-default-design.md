# Phase 2 — Execution Boundary: container-by-default

Date: 2026-06-28
Status: Approved (operator; "degrade, don't brick" strictness)
Branch target: `council-runtime-v01` → fast-forward `master` on green
Roadmap: GAGOS_FINAL_ROADMAP_council.md §3 Phase 2 ("precondition for sovereign")

## Goal

Make the **container** the default execution backend for arbitrary approved code,
so an approved command cannot touch the host outside the isolation boundary by
default. Host execution becomes a **loud, explicit opt-out** ("development only").
Self-apply (the only path that writes real `aios/` source) runs **only** through
the container boundary.

## Why

`executor.py` says it plainly: host mode runs approved commands as the backend OS
user — *"not an OS/container isolation boundary."* The system self-modifies AND
learns, so a host-mode execution mistake can imprint, not just run. `DockerRunner`
already exists and is hardened (`--network none --read-only --cap-drop ALL
--security-opt no-new-privileges --user 65534 --pids-limit --memory --cpus
--tmpfs /tmp:noexec`). This phase flips the default and tightens the opt-out — it
is not new isolation code.

## Strictness decision (operator): degrade, don't brick

Default = container. On a host without a running Docker daemon / built image, the
app **still boots**; only the arbitrary-approved-exec path and self-apply
fail-closed (with a clear "container unavailable — set
`AIOS_APPROVED_EXECUTION_BACKEND=host` to override" message). Host stays an
explicit, loud opt-out. Same security default as the roadmap, friendlier local dev
(GREEN sandbox commands + chat keep working).

## Scope (YAGNI)

Containerize ONLY the two paths that run arbitrary approved code:
1. `Executor.execute_approved` (the approved-arbitrary-exec path, via `approved_runner`).
2. Self-apply verification (`get_self_apply_engine`).

**GREEN auto-exec stays host.** It runs only gateway-classified-safe commands in a
scope-locked cwd; the roadmap's acceptance is specifically about *approved
arbitrary commands*. Containerizing GREEN is a separate, larger change and is out
of scope. This is a conscious boundary, documented, not an oversight.

## Design

### 1. Flip the default (`aios/config.py`)
`APPROVED_EXECUTION_BACKEND` default `"host"` → `"container"`. No new env var:
setting `AIOS_APPROVED_EXECUTION_BACKEND=host` IS the explicit opt-out. `"container"`
and `"host"` are the supported values; anything else is a misconfiguration.

### 2. Degrade-don't-brick startup (`aios/api/main.py` lifespan + `aios/core/executor.py`)
`validate_approved_execution_backend()` no longer *raises* when the container
backend is selected but Docker/image is unavailable — it logs a loud warning and
returns, so the app boots and the exec path fails-closed at call time. Behavior by
backend:
- `container` + Docker available → validated, ready.
- `container` + Docker/image missing → **loud warning, app boots**; approved-exec
  and self-apply fail-closed at call time.
- `host` → **loud warning** ("development-only opt-out; not an isolation
  boundary"); approved-exec runs on host (the conscious opt-out).
- unknown value → **still raises** (real misconfiguration must fail).

The warning is emitted through the existing logger at startup (after the banner).

### 3. Fail-closed approved exec (`aios/core/executor.py`)
Already correct by construction and pinned by a new test: with the container
default, `approved_runner_from_config()` returns a `DockerRunner`, so
`execute_approved` uses it; if the container cannot run, the runner raises and
`_run_in_sandbox` returns an `ERROR` result. The `or self.runner` host fallback
fires ONLY in explicit host mode (`approved_runner is None`). No silent host
fallback when container is configured.

### 4. Self-apply container-only (`aios/api/main.py` `get_self_apply_engine`)
Today the verifier runner falls back to a bare host `pytest` when no isolated
runner exists. New rule: in host mode (or when the isolated runner is otherwise
unavailable), the self-apply verifier **refuses** — its runner returns/raises a
clear "self-apply requires the container execution boundary" failure, so a
proposal can never reach real `aios/` source through bare host execution. When the
container is configured but down, the `DockerRunner` raises → verification fails →
proposal not applied (fail-closed, recoverable once Docker is up).

Implementation: replace the host `_bounded_run` fallback in `project_root_runner`
with a refusal when `isolated_runner is None`. Keep the existing container path
(run the fixed project test command at `PROJECT_ROOT` through the isolated runner).

### 5. Image + docs
`Dockerfile.executor` already builds the executor image (python:3.12-slim + repo
requirements, non-root `65534`). Document the one-time build:
`docker build -f Dockerfile.executor -t aios-executor:local .`
Label the container as the **supported** execution path and host as
**development-only** — in the relevant docs (AGENTS/README execution section) and
in the host-mode startup warning itself.

## Error handling / fail-closed
- Container configured but unavailable → approved-exec ERROR, self-apply refuses;
  app still serves the rest. Never a silent host run.
- Host opt-out → loud warning every boot; approved-exec runs on host (documented
  dev-only); self-apply still refuses (no host self-apply).
- Unknown backend value → startup raises.

## Testing (Verifier owns the escape-attempt suite)
- **Default-is-container:** `approved_runner_from_config()` returns a `DockerRunner`
  with the env default (no override).
- **Escape boundary:** an approved arbitrary command under the container default is
  dispatched through the `DockerRunner` with the hardening flags
  (`--network none`, `--read-only`, `--cap-drop ALL`, `no-new-privileges`,
  non-root user) and is NEVER routed to the host runner. Asserted via an injected
  `process_runner` capturing the docker argv — no real Docker needed.
- **No silent fallback:** with container configured but the runner raising
  (Docker down), `execute_approved` returns `ERROR`/blocked, not a host run.
- **Self-apply refuses host:** host backend ⇒ the self-apply verifier runner
  refuses (no host pytest spawned); container backend ⇒ it runs through the
  isolated runner.
- **Degrade-not-brick:** container backend + unavailable Docker ⇒
  `validate_approved_execution_backend()` does NOT raise (it warns).
- Existing executor/self-apply/API suites stay green; 85% coverage floor;
  frozen security spine (`aios/security/*`) untouched.

## Rollout
Default behavior changes: a fresh install now defaults to container. On a box
without Docker the operator sees a loud warning and either starts Docker (+ builds
the image) or sets `AIOS_APPROVED_EXECUTION_BACKEND=host`. Existing host-mode
users who want the old behavior set the env var once. No data migration.

## Adversarial review (Verifier-owned, 36 agents) — CLEAN

The escape-attempt review returned `invariant_holds = true`, verdict CLEAN, zero
confirmed in-scope findings. Verified on disk: (1) approved-arbitrary exec routes
through the hardened `DockerRunner` (flags are hardcoded literals; approved argv
lands after the image so it is in-container; H4 mount guard holds) or fails closed
to `ERROR` — the `or self.runner` host fallback fires ONLY in explicit host mode;
(2) degrade-don't-brick boots and only logs the warning; (3) self-apply raises in
host mode (rolls back, never verifies on the host). No in-scope skeptic finding
cleared the ≥2-real-AND-live-reachable bar.

Follow-ups (non-blocking, NOT in this slice):
- **Phase 2b — containerize the Council worker.** The opt-in worker subprocess
  (`aios/runtime/`, `ControlledSubprocessBackend` → `subprocess.run`, default off)
  runs contract verification commands host-side and does not consult
  `APPROVED_EXECUTION_BACKEND`. Real but separate, pre-existing, and explicitly
  de-scoped from Phase 2. Documented in the README so the "container by default"
  claim is not over-read.
- **Optional env hardening.** Strip `DOCKER_HOST`/`DOCKER_TLS_VERIFY`/
  `DOCKER_CERT_PATH`/`DOCKER_CONTEXT` in `_sanitise_env` so ambient env cannot
  redirect the docker client to a rogue daemon. Both finders marked the exploit
  NOT live-reachable (needs control of the backend OS env, outside the
  approved-command threat model); deferred because it can break legitimate
  remote-daemon setups. Operator decision.
