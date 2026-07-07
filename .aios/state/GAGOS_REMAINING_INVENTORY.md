# GAGOS Remaining-Work Inventory (backing catalog for Ultra Plan v3)

Generated 2026-07-07 by a 10-area Sonnet inventory sweep + completeness critic, verified against live code. **154 line items** + 9 periphery items. Status/effort/risk per item. This is the exhaustive list; GAGOS_ULTRA_PLAN.md sequences it.


## security-privacy-spine

> The core security primitives (fail-closed gateway, scope-lock, secret scanner, Ed25519 audit chain, dual-layer injection shield) are genuinely well-built and heavily tested — that part of the spine is solid. But three things are true at once: (1) a live, reproducible cloud-egress secret leak exists today in aios/core/privacy_filter.py that is NOT the same code path as the hardened aios/security/secret_scanner.py, so the strength of the security module doesn't protect the privacy/egress module; (2) the primitives needed for safe multi-project/autonomous operation (per-task scope isolation, per-workspace autonomy, git-aware snapshots, origin-scoped routing, frozen-core CI enforcement) are confirmed not built — the ultra-plan's Phase-0 read is accurate against the live code; (3) several 'built' security features are inert in practice — boot attestation logs but never blocks, the external audit anchor mechanism exists but nothing ever calls its publisher, the audit signing key has no rotation trigger, and GREEN-zone commands (the majority of autonomous traffic) bypass the container by construction, not by bug. Every item below was verified by reading the current file, not inferred from the plan.

### 1. Fix live cloud-egress secret leak in privacy_filter.py (path-shape exemption swallows real secrets)
- **status:** not-started · **effort:** M
- **what:** aios/core/privacy_filter.py's `_in_filename_context()` exempts any high-entropy token that fullmatches `_PATH_SHAPED` (slash-separated alnum/underscore/hyphen segments) from `_redact_high_entropy()`. Reproduced live: `aws_secret_access_key = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY` is NOT redacted before cloud egress — the token's two `/` characters make it 'path-shaped' so it's waved through untouched. This is the exact opposite-failure-mode sibling of the 2026-07-07 'don't blind cloud models to real filenames' fix (tests/test_privacy_filter.py::TestPathShapedTokensAreNotSecrets) — that fix (operator-approved) is what left this hole open. Root cause: privacy_filter.py has its OWN hand-rolled credential regex list (`_CREDENTIAL_PATTERNS`) that does NOT include a generic AWS-secret-key pattern and does NOT call the hardened `aios/security/secret_scanner.scan_and_redact()` at all — the egress path and the security-classification path are two independently-maintained secret detectors, one much weaker than the other. Fix needs both directions to hold simultaneously (regression tests already exist for the filename side; need the credential side added — e.g. require the path-shape exemption to also demand a preceding path separator or a following extension, not slash-count alone). Add the 2 regression tests plan item 0.7 calls for.
- **unblocks:** Phase 0 close-out; any future work that raises cloud routing eligibility (origin-scoped routing, Project Passport cloud calls) inherits this leak until fixed.
- **risk if skipped:** Any AWS/GCP-style secret (or PEM body, which is also slash-heavy base64) sitting in a file the operator asks a cloud-routed turn to read is transmitted to Anthropic/Bedrock/Gemini in plaintext — directly contradicts the README's stated invariant ('anything that does leave passes the privacy filter with paths and secrets redacted') and is the single highest-severity item in this area.

### 2. Sub-path credential denylist in scope_lock.py
- **status:** not-started · **effort:** M
- **what:** aios/security/scope_lock.py's `command_stays_in_scope`/`is_path_in_scope` only enforce root-membership plus a blanket `~` (home) refusal (verified: `cat ~/.ssh/id_rsa` is blocked ONLY because it starts with `~`, per tests/test_security.py:184). There is no fail-closed glob denylist for `.env`, `.git/`, `.aws`, `.ssh`, `id_rsa*`, `*.pem`, `*.key`, `.docker`, `.claude`, `.codex`, `.gemini`, or other credential-shaped names WITHIN an allowlisted scope root. Needs a denylist check wired into every file-read and file-write handler, in addition to (not instead of) root-membership.
- **unblocks:** Any project-scan / passport-harvester work (P3) and Phase B/F autonomy on real repos.
- **risk if skipped:** The moment a scope root is widened to a real project (Phase F, or even ai-editor itself in Phase B), a `.env` or `.git/config` sitting inside that allowlisted root is fully readable/writable — nothing currently stops it.

### 3. Per-task ScopeContext (replace scope_lock's process-global mutable scope roots)
- **status:** not-started · **effort:** L
- **what:** aios/security/scope_lock.py holds ONE process-global `_scope_roots: list[Path]` guarded by a lock; `set_scope_roots()` mutates it for the whole process. Confirmed: no per-call/per-task scope parameter exists anywhere in gateway.classify(), command_stays_in_scope(), or Executor._scope_cwd() — all read the same global. Needs a `ScopeContext` object threaded through `gateway.classify(command, scope=...)` -> `command_stays_in_scope(...)` -> `executor._scope_cwd(scope=...)` so one task's declared workspace can't leak into a concurrently-running task's checks.
- **unblocks:** Phase B heartbeat loop / any concurrent-lane execution; per-workspace AutonomyLedger (next item) is meaningless without this.
- **risk if skipped:** Any future multi-tasking (concurrent worker lanes, multi-project autonomy) has a race: task A's scope_roots mutation is visible to task B mid-flight, or a lane confined to project X can be scope-checked against project Y's roots if they're set concurrently. Today it's masked because only one interactive session runs against the default training_ground/lab roots.

### 4. Per-workspace dimension in AutonomyLedger.signature()
- **status:** not-started · **effort:** M
- **what:** aios/core/autonomy.py: `AutonomyLedger.signature()` is `sha256(f"{action_type}|{norm}".encode())` — no workspace/project id in the hash (confirmed by reading the full file). A streak earned doing `create *.py` in one project silently grants the same signature's earned status in any other project with the same action-shape. Needs `workspace_id` threaded into `signature()`, the `earned_autonomy` table schema (migration in the sqlite DDL inside `_ensure_table`), and every `is_earned()`/`record_outcome()`/`record_for()` call site.
- **unblocks:** Phase B/F multi-project autonomy; makes the earned-autonomy claim in README accurate rather than aspirational.
- **risk if skipped:** Autonomy earned safely in ai-editor's training_ground would silently apply to a completely different (possibly untrusted) project the moment multi-project autonomy exists — a direct violation of the 'earned per action-class-per-workspace' claim already made in README.md.

### 5. Frozen-core hardening: relocate guardrail constants, widen frozen_subdirs, add CI diff-gate
- **status:** not-started · **effort:** M
- **what:** AGENTS.md SS XI documents the frozen core as exactly `aios/security/{gateway,scope_lock,secret_scanner,audit_logger,injection_shield}.py`, and `aios/agents/self_analysis_agent.py::classify_target()` / `SelfAnalysisAgent.__init__` both still default `frozen_subdirs=("security",)` (confirmed by reading lines 128-217) — the guardrail constants living in `aios/config.py` (`SCOPE_ROOTS`, `EARNED_AUTONOMY_*`, `ROUTER_CLOUD_TASKS`, `MAX_RED_ACTIONS_PER_SESSION`, `AUDIT_GENESIS_HASH`) and the CORS/Bearer block in `aios/api/main.py` are NOT under any frozen-path protection, and there is no self-analysis-driven enforcement covering them. Also confirmed: `.github/workflows/ci.yml` has zero occurrences of 'frozen' as a dedicated gate — no CI job fails a PR that touches a frozen path. Work: extract the guardrail constants into a new `aios/security/limits.py` and the CORS/Bearer logic into `aios/security/http_guard.py` (both then inherit the existing frozen-prefix convention), widen `frozen_subdirs`, and add a CI job that greps the PR diff for frozen paths and fails.
- **unblocks:** Phase B (ai-editor self-improvement loop) is unsafe to enable without this.
- **risk if skipped:** Today this is contained because no autonomous loop exists yet to exploit it. The moment Phase B (self-improvement loop with PR-write access to ai-editor) ships, a self-authored PR can edit `aios/core/executor.py`, `aios/config.py`, or the CORS/token block in `aios/api/main.py` — none of which are RED/frozen today — with only a human PR-merge as the backstop, no automated one.

### 6. Git-repo-aware snapshot path for real git repositories
- **status:** partial · **effort:** L
- **what:** aios/runtime/snapshots.py `SnapshotManager._engine_for()` fail-closes (raises `RollbackError`) whenever the target workspace already contains a `.git` directory not owned by the Council runtime — confirmed by reading the file; this is deliberate and correct (it refuses to silently adopt a foreign repo), but it means there is currently NO snapshot-before-write mechanism at all for a workspace that is itself a real git repo (e.g., ai-editor). `aios/runtime/worktree_backend.py` (WorktreeBackend: create_lane/destroy_lane/list_lanes) already exists and is the right primitive for this, but it is not wired into any pre-write snapshot flow — nothing calls `git stash create` / a throwaway ref before an autonomous write, and there's no snapshot-retention policy (`git gc --auto`, keep last N / 7 days) for whatever mechanism replaces it.
- **unblocks:** Phase B (ai-editor self-improvement loop) and the 'every autonomous write reversible' guardrail-spine invariant.
- **risk if skipped:** For the one workspace the ultra-plan scopes write-autonomy to first (ai-editor itself), there is no rollback guardrail today — an autonomous write into a real git repo currently has no proven, tested recovery path, only the fail-closed refusal (which is safe but means the feature literally cannot run yet).

### 7. GREEN-zone auto-execution bypasses the container sandbox by construction
- **status:** not-started · **effort:** S
- **what:** aios/core/executor.py: `Executor.execute()` on a GREEN classification calls `self._run_in_sandbox(command, Zone.GREEN)` with no `runner=` override, so it always uses `self.runner` (defaults to `_default_runner`, a bare host subprocess). Only `execute_approved()` (the post-YELLOW-approval / earned-autonomy path) ever receives `self.approved_runner` (the `DockerRunner`). Confirmed by reading both methods end-to-end: GREEN commands — auto-executed with no human in the loop — never touch the container regardless of `AIOS_APPROVED_EXECUTION_BACKEND=container`. This needs an explicit policy decision (documented, not silently accepted): either extend container isolation to GREEN, or formally accept the host-execution risk for the narrow `_SAFE_PATTERNS` allowlist (currently just `echo`/`pwd`) per Phase A3.
- **unblocks:** Phase A3 RAM-budget/backend-pinning decision; an honest README/SECURITY.md claim about what the container boundary actually covers.
- **risk if skipped:** Documented as a known gap in the ultra-plan but not yet resolved in code or policy; an operator could reasonably believe `AIOS_APPROVED_EXECUTION_BACKEND=container` isolates ALL execution when it only isolates the approved/YELLOW path.

### 8. Sign and enforce boot attestation (currently log-only, unsigned)
- **status:** partial · **effort:** M
- **what:** aios/boot_attestation.py computes a plain SHA-256 Merkle hash over `aios/security/*.py` and appends `{hash, previous_hash, integrity}` to `.aios/audit/boot-attestation.jsonl` — no Ed25519 signature (unlike the audit ledger, which does sign). aios/api/main.py (lines ~241-246) calls `attest_boot()` at startup and only `logger.info`/`logger.warning`s the result — a `TAMPERED` integrity verdict does not abort startup, does not refuse RED/YELLOW actions, does not raise any alert beyond a log line. An attacker (or a bug) that modifies the frozen security spine files between boots produces a log entry nobody is guaranteed to read, and the process starts normally anyway.
- **unblocks:** Honest 'Definition of 100%' item #3 in the ultra-plan (frozen-core CI gate) — this is boot-time, that is PR-time; both are needed for the full claim.
- **risk if skipped:** The entire point of boot attestation — detecting spine tampering — is defeated if the only consequence is an INFO-level log line; the guardrail-spine claim 'frozen core never autonomously edited (enforced in code + CI)' currently has no enforcement teeth at boot time, only at write time via scope_lock.

### 9. Wire the external audit-anchor publisher (mechanism built, never invoked)
- **status:** partial · **effort:** S
- **what:** aios/audit_anchor.py's `publish_anchor(publisher, db_path)` takes an injectable publisher callback and appends to a local `anchor_history.jsonl` on success — but confirmed by grep: `publish_anchor` is never called anywhere in the codebase (only `get_external_anchor` and `anchor_history`, both read-only, are wired into aios/api/routes/sovereignty.py for the operator to view on demand). No scheduled job, CLI, or route actually publishes the anchor anywhere external. audit_logger.py's own docstring names the exact residual risk this leaves open: 'an attacker who deletes EVERY entry AND the anchor leaves a pristine-looking empty DB; only an externally-published anchor could detect that.'
- **unblocks:** docs/SECURITY.md 'restore data/ / verify the audit chain' operator runbook (Phase E2).
- **risk if skipped:** The tamper-evident ledger's strongest claim (detect a full wipe, not just a partial edit) is unrealized — the mechanism exists in code but provides zero actual protection until something outside the local machine holds a copy of the anchor.

### 10. Audit signing-key and API-token rotation have no operational trigger
- **status:** not-started · **effort:** S
- **what:** aios/security/audit_logger.py::`rotate_audit_key()` exists and is exported, but grep confirms it is never called from anywhere except its own module and `__all__` — no API route, CLI, or scheduled job invokes it. Separately, `AIOS_AUDIT_PRIVATE_KEY` is unset by default, so `_load_or_create_private_key()` generates a fresh ephemeral Ed25519 key on every process start (logged as a WARNING) — meaning the non-repudiation guarantee does not survive a restart unless the operator has manually provisioned and persisted the env var, which nothing currently prompts or automates. Separately again, aios/api/main.py's bearer-token check (`config.API_TOKEN`, `secrets.compare_digest`) is a single static token with no dual-token grace-period support — rotating it requires a synchronized restart with every client updated simultaneously.
- **unblocks:** docs/SECURITY.md rotation runbook (Phase E2); production/always-on hardening.
- **risk if skipped:** In practice low risk today (single-operator laptop, restarts are rare and manual) — but 'secret rotation' named in this area's scope is genuinely unaddressed: no runbook, no tooling, and the default (ephemeral audit key) silently weakens the auditability story across restarts without the operator necessarily noticing.

### 11. Injection-vector shield ships default-off (dormant)
- **status:** not-started · **effort:** S
- **what:** aios/config.py: `INJECTION_VECTOR_SHIELD: Final[bool] = _env_bool("AIOS_INJECTION_VECTOR_SHIELD", False)`. aios/api/main.py only installs `VectorInjectionShield` (aios/security/injection_shield.py) via `set_injection_shield()` when this flag is true. The regex layer (aios/security/gateway.py `_INJECTION_PATTERNS`) is always active and well-tested, but the semantic/embedding-similarity second layer that catches paraphrased injections is off by default — confirmed live in config and main.py.
- **unblocks:** Ultra-plan Phase C2 flag decision; the D1 chaos-test target ('50 injection strings 100% blocked') is currently only exercising the regex layer if this stays off.
- **risk if skipped:** Paraphrased prompt-injection attempts that don't match the curated regex list pass through unchallenged in the default configuration; this is a conscious flag-flip (plus verifying the embedding-model load cost on a 16GB box, since it lazily loads `aios.memory.embeddings.EmbeddingModel`) rather than new code, which is why effort is small — but it needs an explicit default-on decision + RAM/latency check, not just silence.

### 12. Add a real GET /health liveness endpoint
- **status:** not-started · **effort:** S
- **what:** aios/api/main.py's `require_api_token` auth middleware has a docstring/comment stating '`/health` remains public for liveness probes' (line ~478) and explicitly carves it out of the protected-path check — but grep confirms no route handler for `/health` is ever registered anywhere in main.py. The exemption is dead code protecting a 404.
- **unblocks:** Phase A2 always-on host watchdog; any external monitoring.
- **risk if skipped:** Blocks Phase A2 (launcher/watchdog) which needs to poll `/health` every 30s to detect and relaunch a crashed process — there is currently nothing to poll. Also a small but real honesty gap: the code comments assert a public surface that doesn't exist.

### 13. Origin-scoped LLM routing (interactive vs. autonomous cloud eligibility)
- **status:** not-started · **effort:** M
- **what:** aios/core/router_wiring.py's `_router_policy()` builds `cloud_tasks=frozenset(config.ROUTER_CLOUD_TASKS)` fresh each call from the ONE process-global `config.ROUTER_CLOUD_TASKS` (default `("reasoning", "coding")` — cloud-eligible by default, confirmed by reading aios/config.py line 311). There is no `origin: "interactive"|"autonomous"` parameter anywhere in the routing call chain, and no separate `AIOS_ROUTER_CLOUD_TASKS_AUTONOMOUS` variable exists. Separately, `SWARM_CLOUD_BURST_ENABLED` defaults `True` (aios/config.py line 204) and is consulted directly in aios/api/main.py and aios/agents/swarm.py with no origin distinction either.
- **unblocks:** Phase B/C2 — required before any unattended loop is allowed to run at all, per the guardrail spine's own non-negotiable list.
- **risk if skipped:** Once an autonomous loop exists (Phase B), it inherits whatever cloud-eligibility the OPERATOR's interactive session has configured — there is no way today for an unattended background task to be forced local-only independent of the human's own settings, contradicting the guardrail-spine claim 'autonomous LLM calls are local-only.'


## autonomy-council-worker

> Earned autonomy today is a single, process-global, interactive-chat-only mechanism (aios/core/autonomy.py wired only into aios/agents/tool_agent.py for create_file/edit_file) — it has never been extended to the Council/worker mission path at all. The Council Runtime (aios/council/*, aios/runtime/spawner.py, worker_entry.py) is a real, human-triggered request/approve/execute pipeline with good fail-closed primitives (mission-collision locks, worker capacity semaphore, rollback engine, secret scrubbing) — but the "always-on loop" named in this area's brief (heartbeat, idle/AC detection, workspace registry, kill switch, digest) does not exist anywhere in the repo: zero files. The King's LLM-reasoning layer is verified dead code in production (never constructed with a real `complete` callable), self-modification (self_apply.py) hot-patches the live tree directly rather than using the already-built-but-unwired WorktreeBackend, and several of the Phase-0 security-spine prerequisites named in the Ultra Plan (per-workspace ledger, frozen-core relocation, origin-scoped cloud routing, credential denylist) are confirmed still not started by reading the current code, not just the plan.

### 14. Per-workspace AutonomyLedger dimension
- **status:** not-started · **effort:** M
- **what:** aios/core/autonomy.py: AutonomyLedger.signature() = sha256(f"{action_type}|{norm}") has no workspace/project dimension, and the `earned_autonomy` SQLite table (created in _ensure_table) has no workspace_id column. AutonomyLedger is constructed with zero args in aios/api/deps.py:get_autonomy() -> AutonomyLedger() — one process-global ledger. A streak earned while writing training_ground/*.py in project A silently grants the same shaped write in project B the moment a second workspace is onboarded (Phase F). Needs: workspace_id threaded into signature(), a migration in aios/memory/db.py, and every is_earned()/record_outcome() call site (aios/agents/tool_agent.py:1010,1350) updated to pass the active workspace id.
- **unblocks:** Any multi-project autonomy (Phase F); is the direct precondition the Ultra Plan (0.2) names before autonomy can safely leave ai-editor.
- **risk if skipped:** Autonomy earned on one project's shape silently auto-executes on an unrelated project with a matching directory/extension shape — a cross-project privilege leak with no test currently catching it.

### 15. Earned autonomy is not wired into the Council/worker mission path at all
- **status:** not-started · **effort:** L
- **what:** Confirmed by grep: `autonomy`/`Autonomy` appears nowhere in aios/runtime/{spawner.py,worker_entry.py,concurrency.py,contracts.py} or aios/council/*.py. AutonomyLedger.is_earned()/record_outcome() are called only from aios/agents/tool_agent.py (the interactive chat tool loop), scoped to just `create_file`/`edit_file`. Every Council mission — including the ai-editor self-improvement path this area's brief names — pauses for a human King decision every single time; there is no mechanism by which a Council mission class can graduate to auto-execute even after N verified successes.
- **unblocks:** Phase B4 (ai-editor self-improvement loop) and any "earn autonomy on the always-on loop" story — currently there is nothing to graduate.
- **risk if skipped:** The always-on loop (once built) has no earned-autonomy bridge, so it either (a) can never auto-act without a human present, defeating "overnight autonomous", or (b) someone bolts on a second, inconsistent autonomy mechanism instead of reusing the audited one.

### 16. King LLM-reasoning is dead code in production — decide wire-it-or-cut-it
- **status:** not-started · **effort:** M
- **what:** aios/council/council_orchestrator.py accepts `king_complete: Callable[[str], str] | None = None`; `reason_king()` in aios/council/king_reasoning.py only runs `if config.COUNCIL_KING_REASONING and self.king_complete is not None`. Verified by grep across aios/: the ONLY two production constructions of CouncilOrchestrator (aios/api/routes/council.py:378 and :396, in _run_council_deliberation/_run_council_execution) never pass `king_complete`. So even flipping `AIOS_COUNCIL_KING_REASONING=1` in production changes nothing — the King never reasons; it is only exercised by tests that inject a fake `complete`. This is the exact "disconnected dead code" finding from the thesis audit, confirmed still true by reading the current call sites.
- **unblocks:** An honest README claim about the King (currently overstated) and any real LLM-assisted council deliberation.
- **risk if skipped:** README/thesis continues to describe a live LLM King that does not run; a future contributor may assume flipping the flag is sufficient and ship a false sense of deeper cognition.

### 17. King reasoning human_summary staleness bug
- **status:** not-started · **effort:** S
- **what:** aios/council/king_reasoning.py reason_king(), lines ~94-99: when the LLM returns a parseable RECOMMENDATION but no RATIONALE, and the clamped `final` differs from the deterministic baseline, the code does `return report.model_copy(update={"recommendation": final})` — updating `recommendation` but NOT `human_summary`. The operator-facing summary text still describes the OLD (less cautious) recommendation while `report.recommendation` has been strengthened, producing a report where the headline text and the machine-readable verdict disagree.
- **unblocks:** Trustworthy King reports once king_complete is actually wired (item above) — otherwise this bug ships live the moment that wiring lands.
- **risk if skipped:** An operator reading the King dashboard sees a summary that describes approval while the actual recommendation was silently escalated to revise/rollback/reject — a real UI-trust bug, not cosmetic.

### 18. Git-repo-aware snapshots for workspaces that already have .git
- **status:** not-started · **effort:** M
- **what:** aios/runtime/snapshots.py SnapshotManager._engine_for() still raises RollbackError when the target workspace_root already contains a `.git` directory not owned by the Council runtime ("Council rollback refused: workspace already contains a .git directory not owned by the Council runtime"). ai-editor itself is exactly such a workspace. This is unchanged from the Ultra Plan's finding #4 — verified by reading the current code, not the plan doc.
- **unblocks:** Any Council-orchestrated mission whose workspace_root is ai-editor's own repo (i.e., Phase B4, the self-improvement loop this area is scoped to).
- **risk if skipped:** Council missions targeting ai-editor itself fail closed at snapshot creation before a worker ever runs — the self-improvement loop cannot function on its own repo today.

### 19. WorktreeBackend exists but has zero callers — completely unwired
- **status:** partial · **effort:** L
- **what:** aios/runtime/worktree_backend.py implements a full git-worktree lane manager (create_lane/destroy_lane/list_lanes) with lane-id validation and prune-on-destroy. Grep across aios/ for `WorktreeBackend(` / `worktree_backend` returns zero matches outside the file's own definition — nothing in spawner.py, council_orchestrator.py, or any route constructs or calls it. It is dead infrastructure today.
- **unblocks:** Phase B4/B3: parallel worker lanes and the git-repo-aware snapshot path (item above) both need this wired as the actual execution backend for a self-work mission.
- **risk if skipped:** The one piece of infrastructure that would let Council missions safely branch/isolate inside ai-editor's own repo sits unused while self_apply.py (see next item) does the opposite — writes straight to the live tree.

### 20. self_apply.py hot-patches the live working tree instead of branch -> PR
- **status:** partial · **effort:** L
- **what:** aios/core/self_apply.py (the ONLY existing self-modification path for aios/ source) applies an approved diff via `git apply` directly against the live repo's working tree (grep confirms `git apply`/`git apply --check` calls against cwd; no `checkout -b`, `git commit`, `gh pr`, or worktree/branch calls anywhere in the file). This directly violates the Ultra Plan's non-negotiable guardrail-spine line: "ai-editor self-work = branch -> full suite + prover -> PR -> operator merge (never hot-patch the live process)". Today's mechanism is snapshot -> git-apply -> verify -> auto-rollback-on-failure, which is reversible but still mutates the live checkout the running process is served from.
- **unblocks:** An honest write-mode="pr" self-improvement loop (B4) that never risks corrupting the live serving process mid-request.
- **risk if skipped:** A self-apply that lands between requests to a live (no --reload) backend process can leave the running process serving stale bytecode against new source, or, if verify fails after a partial write, leaves the live tree in a rolled-back-but-observed-inconsistent state during the apply window.

### 21. Origin-scoped routing (interactive vs autonomous cloud eligibility)
- **status:** not-started · **effort:** L
- **what:** Grep of aios/core/router_wiring.py for "origin"/"ROUTER_CLOUD_TASKS_AUTONOMOUS"/"interactive.*autonomous" returns zero matches. There is no concept anywhere of tagging a request as `origin="interactive"` vs `"autonomous"`; ROUTER_CLOUD_TASKS (config.py:311-313) is one process-global default `("reasoning", "coding")` = cloud-eligible. Separately, SWARM_CLOUD_BURST_ENABLED (config.py:204) defaults True (`AIOS_SWARM_CLOUD_BURST`, default True) — confirmed still the case reading current config, matching the known-context finding. Nothing distinguishes a future daemon-initiated call from the operator's own interactive one in the same process.
- **unblocks:** Any safe always-on loop — without this, the moment a heartbeat loop exists it inherits the interactive cloud-eligible defaults with no separate opt-in gate.
- **risk if skipped:** An unattended overnight loop routes reasoning/coding tasks (and swarm cloud bursts) to a third-party cloud provider by default, sending operator code/data off-machine with no human present to notice — the exact "local-only egress is unimplementable as written" finding, still true.

### 22. Sub-path credential denylist in scope_lock
- **status:** not-started · **effort:** M
- **what:** Full read of aios/security/scope_lock.py: is_path_in_scope()/command_stays_in_scope() only check root-membership (is the resolved path inside a declared SCOPE_ROOT), with a `~` home-reference refusal. There is no additional glob-based denylist for `.env`, `.git/`, `.aws`, `.ssh`, `id_rsa*`, `*.pem`, `*.key`, `.docker`, `.claude`, `.codex`, `.gemini`, or other credential-shaped names layered on top of root-membership. A file named `.env` sitting inside an otherwise-allowlisted scope root is readable/writable today.
- **unblocks:** Safe read/index-only expansion into real operator projects (Phase F) and safe indexing during Project Passport harvesting.
- **risk if skipped:** An allowlisted project root that happens to contain a `.env`, SSH key, or AWS credentials file has those files read/exfiltrated by any tool call scoped only by root-membership — no dedicated regression test exists for this today (tests/test_security.py covers root-escape, not sub-path credential shapes).

### 23. Always-on host / heartbeat loop / workspace registry — entirely unbuilt
- **status:** not-started · **effort:** XL
- **what:** Targeted search (`find aios -iname "*heartbeat*" -o -iname "*workspace*"`) returns zero files. There is no aios/runtime/heartbeat_loop.py, no aios/runtime/workspaces.py registry, no idle/AC (psutil) detection, no Ollama-arbitration-under-interactive-preempt mechanism, no task-source priority queue (failing tests -> self-analysis findings -> passport next-step -> curriculum), no lane-lifecycle management calling WorktreeBackend.destroy_lane() in a finally. This is the entire content of Ultra Plan Phase B (B1-B5) and is the literal "always-on loop" this area's brief asks about — it does not exist as even a skeleton.
- **unblocks:** Everything downstream in the Ultra Plan: Phase B4 self-improvement, Phase C instrumentation, Phase D burn-in, Phase F external projects — none of it can start without this.
- **risk if skipped:** "Always-on autonomous brain" remains aspirational prose; the README/thesis's Council Runtime and earned-autonomy primitives stay permanently reachable only via a human clicking through the API/dashboard, never by an unattended loop.

### 24. Kill switch + morning digest
- **status:** not-started · **effort:** M
- **what:** No `data/KILL_SWITCH` sentinel check, no `POST /api/v1/daemon/kill` endpoint, no scripts/kill.ps1, and no digest function reading the audit ledger into a per-session summary exist anywhere in the repo (confirmed via targeted find for *kill_switch*/*digest*, zero hits). `GET /health` DOES exist (aios/api/routes/system.py:83-84) — that is the one piece of Phase A already present.
- **unblocks:** Any operator confidence in running the loop unattended overnight — this is the emergency stop and the morning accountability report named as non-negotiable in the guardrail spine.
- **risk if skipped:** Once a heartbeat loop exists, there is no way for the operator to halt it short of killing the process, and no digest to review what it did while they were away — directly undermines "human sovereign" for an unattended system.

### 25. Frozen-core hardening: relocate guardrail constants, widen frozen_subdirs, add CI gate
- **status:** not-started · **effort:** L
- **what:** aios/agents/self_analysis_agent.py classify_target()/SelfAnalysisAgent.__init__ still default `frozen_subdirs: tuple[str, ...] = ("security",)` (lines 132, 189, 212) — verified unchanged. AUDIT_GENESIS_HASH, SCOPE_ROOTS, EARNED_AUTONOMY_*, ROUTER_CLOUD_TASKS, MAX_RED_ACTIONS_PER_SESSION all still live in aios/config.py; `find aios/security` shows no limits.py or http_guard.py. `.github/workflows/ci.yml` has no job matching frozen/SCOPE_ROOTS/AUDIT_GENESIS_HASH (grep returned zero matches) — no automated CI backstop blocks a PR that touches a frozen path.
- **unblocks:** Any self-authored PR path (B4) being safe to run even semi-unattended — this is the backstop for when a human reviewer misses a frozen-path diff.
- **risk if skipped:** A self-improvement mission (once B4 exists) can propose and, if self_apply's git-apply hot-patch path or a future B4 branch flow is used, land an edit to aios/core/executor.py, aios/config.py (every guardrail constant), or aios/api/main.py's CORS/auth block — none of which are protected by frozen_subdirs today, and CI would not catch it.

### 26. Approval-request-level decision race is not lock-protected (only mission-level is)
- **status:** partial · **effort:** S
- **what:** aios/api/routes/council.py _write_council_decision(): the mission-level decision path (COUNCIL_ORIGINATION + request_id is None) is protected by an atomic `(mission_dir / "decision.lock").mkdir(exist_ok=False)` — this closes the double-execute TOCTOU that was previously flagged. BUT the request_id-scoped branch (used for granular per-step approvals, request_id is not None) only does a check-then-write: `if response_path.exists(): raise 409` followed by a separate `response_path.write_text(...)` — no atomic exclusive create. Two concurrent decisions for the same request_id can both pass the existence check before either writes.
- **unblocks:** A fully race-free approval surface for the finer-grained (non-mission-level) approval flow used during multi-step worker missions.
- **risk if skipped:** Two concurrent approve/reject calls on the same granular request_id can both succeed and both write a response file (one overwriting the other), producing an ambiguous or lost decision record on the audit trail for exactly the case the mission-level fix was built to prevent.

### 27. Cloud-cost budget dials in BudgetGuard are dead controls
- **status:** partial · **effort:** M
- **what:** aios/runtime/budget_guard.py ModelPolicy exposes `mission_cloud_budget`/`daily_cloud_budget` (dollar-denominated) and BudgetGuard.check_cloud_request()/record_cloud_usage() gate on them, but the only production caller — aios/runtime/intelligence_gateway.py IntelligenceGateway.request() — hardcodes `cost=0.0` (line ~125) and `cost_estimate=0.0` (line ~132) on every cloud call. Verified: no code path anywhere computes a real per-token/per-provider cost estimate. Only the token-count-based budgets (`max_tokens_per_request`, `max_tokens_total`) are live; the dollar budgets can never trip.
- **unblocks:** Real cost-based circuit breakers for autonomous cloud usage once origin-scoped routing (item above) allows any autonomous cloud egress at all.
- **risk if skipped:** An operator who sets `daily_cloud_budget` expecting it to cap spend gets silent false safety — the dial is wired into the dataclass and README-adjacent docs may describe it as functional, but it can never fire.

### 28. WORKER_REASONING (LLM-driven Council worker) has no origin/frozen-core/workspace gates yet
- **status:** partial · **effort:** M
- **what:** aios/runtime/worker_entry.py `_run_llm_worker` (used when config.WORKER_REASONING, default False) is otherwise well-built — bounded repair attempts (WORKER_MAX_REPAIRS), forbidden-file probe, verification-gated "completed" status, size cap (WORKER_MAX_FILE_BYTES) — but its `allow_cloud` comes straight from `contract.metadata.get("allow_cloud_reasoning", False)`, a mission-contract field with no independent enforcement tying it to the (still nonexistent) origin-scoped local-only policy for autonomous work, and no check against frozen_subdirs beyond whatever the mission's own allowed_files/forbidden_files already encode. It depends on the three items above (frozen-core, origin-scoped routing, per-workspace autonomy) before it is safe to flip on for anything beyond supervised single missions.
- **unblocks:** Turning WORKER_REASONING on by default for the eventual always-on loop.
- **risk if skipped:** If someone flips AIOS_WORKER_REASONING=1 for the daemon before the three prerequisite gates land, an LLM-driven worker mission could set allow_cloud_reasoning=true on itself (or be given it) with no separate autonomous-origin cloud policy to override it.

### 29. No chaos/torture test suite for the council-worker-autonomy path
- **status:** not-started · **effort:** L
- **what:** `find tests -iname '*torture*' -o -iname '*chaos*'` returns zero files (tests/test_autonomy.py, tests/test_earned_autonomy_integration.py, and tests/adversarial/test_autonomy_safety.py exist and cover the ledger/tool_agent path in isolation, but there is no fixture-driven suite exercising: Ollama killed mid-worker-stream, disk-full during a Council write, concurrent missions vs WORKER_POOL cap exhaustion under real load, or an approval race under concurrency). This is Ultra Plan Phase D1, and it is the area's own burn-in gate.
- **unblocks:** Any credible "48h unattended burn-in" claim (Phase D2) for this area.
- **risk if skipped:** The concurrency/capacity/rollback primitives that exist (WORKER_POOL semaphore, SnapshotManager, decision.lock) are unit-tested in isolation but never proven under simultaneous adversarial load — exactly the gap a red-team would find first.


## router-providers

> The router (aios/core/router.py, router_wiring.py) is architecturally the strongest-built part of the system: a clean 3-layer deterministic-policy + evidence-calibration + optional-LLM-pick design, with real cross-provider failover (aios/core/failover.py), live Ollama discovery, and account-accurate cloud catalog discovery (aios/core/catalog.py) across five providers (Ollama, Bedrock, Gemini, OpenAI-compat, Anthropic direct). It is also well-tested (test_router.py + test_route_wiring.py, ~50 tests). The remaining work is NOT "build the router" — it's closing the honesty gap between what the docs/thesis claim and what config.py actually defaults to, fixing two real (if currently double-redundant) privacy-boundary bugs found by direct code reading, and building the pieces the sovereign-autonomy plan needs but that don't exist yet: origin-scoped (interactive vs autonomous) egress, live provider health, retry/backoff, and 16GB-host resource awareness. Every item below was verified against current code, not assumed from the plan.

### 30. Fix router egress cloud-eligible-by-default vs the 'local-only by default' claim
- **status:** not-started · **effort:** S
- **what:** aios/config.py:311 `_ROUTER_CLOUD_TASKS_DEFAULT = ("reasoning", "coding")` makes cloud egress opt-out, directly contradicting README.md:202 ('a cloud route requires per-task-class operator opt-in ... empty by default = local-only') and router.py's own module docstring describing `LOCAL_FIRST` (empty cloud_tasks) as 'the behaviour-preserving default ... nothing ever leaves the machine'. Already flagged twice in project history (2026-06-29, 2026-07-07) as an unresolved P0 doc/code mismatch. Decide operator intent once and either flip the default to `()` or rewrite README.md:202 + the router.py docstring to state the true cloud-by-default-for-two-tasks design.
- **unblocks:** README re-audit (Plan E1); Definition-of-100% item 5
- **risk if skipped:** The project's core sovereignty pitch stays falsifiable: every reasoning/coding turn already round-trips through AWS/Google by default once credentials exist, while the README promises local-only-by-default. This is the exact 'reversed claim' the thesis audit named.

### 31. Fix 'transparent heuristic' claim vs LLM-pick-on-by-default
- **status:** not-started · **effort:** S
- **what:** aios/config.py:317 `ROUTER_LLM_PICK` defaults `True`, so any `auto` turn with 2+ policy-allowed candidates hands the final choice to a local model's free-text guess (router_wiring._maybe_llm_picker -> router.pick_from) rather than the deterministic ranking alone. README.md:33 states 'Selection is a transparent heuristic, not an LLM guessing about itself.' Either default `ROUTER_LLM_PICK` to `False` to match the doc, or rewrite the README line to describe the actual hybrid (heuristic-plus-optional-LLM-override) design.
- **unblocks:** README re-audit; deterministic routing guarantees relied on by audit tooling
- **risk if skipped:** Same class of documentation dishonesty as the egress default; also makes routing non-deterministic/non-reproducible by default for anyone debugging or auditing a route decision.

### 32. FailoverChatClient misclassifies openai/anthropic as 'local', breaking the H9 single-cloud-provider guarantee
- **status:** not-started · **effort:** S
- **what:** aios/core/failover.py:50-53 — `_CLOUD_PROVIDERS = frozenset({"bedrock","gemini","aws","google","vertex"})` and `_LOCAL_PROVIDERS = frozenset({"ollama","local"})` both omit `"openai"` and `"anthropic"`. `_is_cloud_provider()`/`_is_local_provider()` return False for those names, so they fall into the `else: local_indices.append(i)` branch (comment: 'Unknown — treat as local — never assume cloud', backwards for these two real cloud providers). Consequence, verified by reading `chat()`/`stream_chat()`/`stream_chat_with_tools()`: (1) the class's own documented guarantee ('at most ONE cloud provider per turn ... never to a different cloud provider when local fallback exists') is violated whenever a ranked cascade mixes bedrock/gemini with openai/anthropic, since the H9 skip-guard never fires for the latter two; (2) the single pre-filtered `filtered_messages` copy is never applied on the openai/anthropic leg (`use_messages = filtered_messages if i in cloud_indices else messages` always picks raw `messages` for them) — no live leak today only because each client's own `.chat()` re-filters internally. `grep -n "openai\|anthropic" tests/test_failover.py tests/test_failover_stream_tools.py` returns zero matches — completely untested. Fix: add `"openai"` and `"anthropic"` to `_CLOUD_PROVIDERS`.
- **unblocks:** A trustworthy H9 guarantee ahead of Phase 0.5/0.7 hardening
- **risk if skipped:** A real privacy-invariant bug ships silently, currently masked only by redundant per-client filtering; the moment that per-client filter is ever refactored away (a plausible 'failover already filters this' cleanup), sensitive data reaches two cloud providers in one turn instead of the documented one.

### 33. `.complete()` bypasses PrivacyFilter on AnthropicDirectClient and OpenAICompatClient
- **status:** not-started · **effort:** S
- **what:** aios/core/anthropic_direct.py:203-223 and aios/core/openai_compat.py:174-197 build their HTTP payload directly from `prompt`/`system` with no call to `self._privacy_filter.filter(...)`, contradicting both classes' own docstrings ('every message list is passed through PrivacyFilter before transmission') and every `.chat()`/`.stream_chat()` method on all four cloud clients, which do filter. Not reachable today — aios/api/main.py (~line 1918) deliberately wires `planner_llm`/`self_analysis_llm` to the local `get_llm_client()`, never a cloud client — but every `.complete()` caller (reflection_agent.py, self_analysis_agent.py, alignment.py, planner.py, council/reasoning.py, runtime/intelligence_gateway.py) is a live public API surface one wiring change away from leaking raw prompts (which can carry file contents, secrets, tool output) to Anthropic/an OpenAI-compatible endpoint unredacted.
- **unblocks:** Safe future cloud-routing of `.complete()`-based subsystems (Plan C2's WORKER_REASONING)
- **risk if skipped:** A latent privacy leak activates silently the day any `.complete()`-based subsystem (planner, reflection, alignment, self-analysis) gets routed to cloud for reasoning — exactly the class of gap the thesis audit's privacy-filter finding already burned this project on once.

### 34. Origin-scoped routing (interactive vs autonomous) not implemented — Plan task 0.5
- **status:** not-started · **effort:** M
- **what:** No `origin` parameter exists anywhere in `router.Policy`, `router_wiring._router_policy()`, or `_select_chat_client()`; `grep -rn "origin|autonomous" aios/core/router*.py` returns nothing, and no `AIOS_ROUTER_CLOUD_TASKS_AUTONOMOUS` env var exists in config.py. Today one process-global `ROUTER_CLOUD_TASKS` governs every call regardless of whether it came from the operator's interactive chat or a future autonomous work-loop call, so once Phase B's heartbeat loop exists it silently inherits the operator's interactive cloud eligibility instead of a separate, default-empty autonomous boundary.
- **unblocks:** Phase B heartbeat loop / ai-editor self-improvement loop (Plan B3/B4); Definition-of-100% item 2
- **risk if skipped:** Blocks Phase B (the sovereign work-loop) from ever being safely autonomous — an unattended task could route reasoning/coding to cloud under the operator's interactive policy, the exact failure the plan's guardrail spine forbids ('autonomous LLM calls are local-only').

### 35. SWARM_CLOUD_BURST_ENABLED defaults True with no autonomous-context override
- **status:** not-started · **effort:** S
- **what:** aios/config.py:204 `SWARM_CLOUD_BURST_ENABLED = _env_bool("AIOS_SWARM_CLOUD_BURST", True)`, consumed in aios/agents/swarm.py:301 and aios/api/main.py:1952. There is no mechanism to force it off specifically for a future daemon/autonomous caller — this depends on the origin-scoping plumbing (previous item) existing first. Named explicitly in the plan (Phase C2): 'SWARM_CLOUD_BURST -> flip local for the daemon (it is True today).'
- **unblocks:** Phase C2 flag decisions; depends on origin-scoped routing item above
- **risk if skipped:** A swarm task kicked off by the future autonomous loop can burst to cloud even if reasoning/coding cloud egress is otherwise locked down for autonomous origin.

### 36. No live health/availability check for cloud providers — `available` is hardcoded True
- **status:** not-started · **effort:** M
- **what:** router_wiring._build_providers() (aios/core/router_wiring.py:97-131) sets `available=True` unconditionally for every Bedrock/Gemini/OpenAI/Anthropic provider row once its client object is non-None — never probes reachability. Contrast with the Ollama row, which does a real `ollama.list_models()` call and sets `available=bool(local_models)`. A cloud provider with expired credentials, a revoked key, an AWS region outage, or a lapsed `gcloud` ADC token is still ranked and offered as the top `auto` candidate; the failure is only discovered mid-turn via FailoverChatClient, burning latency and a failover slot.
- **unblocks:** A trustworthy coverage-preview endpoint and an honest /health
- **risk if skipped:** Degrades the `auto` experience under any real cloud outage/credential problem and skews router.candidates()' ranking/UI badges toward providers that can't actually serve the turn — this area's remit explicitly names 'provider coverage/health'.

### 37. `/health` has no router/provider visibility
- **status:** not-started · **effort:** S
- **what:** aios/api/routes/system.py:83-86 — `GET /health` returns only `{"status": "ok", "version": ...}`. It reports nothing about which providers are configured/reachable, the live `ROUTER_CLOUD_TASKS` value, or whether the local Ollama backend is actually serving models. Plan A2's watchdog design ('poll /health every 30s, relaunch on failure') and any operator/UI wanting to know 'is cloud actually usable right now' have nothing to read.
- **unblocks:** Plan A2 (watchdog), Plan A5 (digest)
- **risk if skipped:** The always-on host (Plan A2) can't detect a provider-level failure via its own liveness probe; the operator has no single place to see the router's live coverage.

### 38. No retry/backoff for transient provider errors
- **status:** not-started · **effort:** M
- **what:** grep across aios/core/{bedrock,gemini,openai_compat,anthropic_direct,failover,router,router_wiring}.py for retry/backoff returns nothing. Every cloud client raises LLMError immediately on any converse/HTTP failure — a transient throttle (Bedrock ThrottlingException, HTTP 429 from Gemini/OpenAI-compatible endpoints, a momentary network blip) is treated identically to a permanent outage: it burns a FailoverChatClient slot and can silently downgrade the turn to a weaker local model instead of a short backoff-then-retry on the same (best) candidate.
- **unblocks:** More reliable cloud routing under real-world throttling
- **risk if skipped:** Under any real cloud rate-limit (likely on the free/low-cost tiers this project targets), turns degrade to worse models more often than necessary — 'failover robustness', explicitly part of this area's scope, stays partial.

### 39. Cloud model-catalog discovery cache has no lock — concurrent-request race
- **status:** not-started · **effort:** S
- **what:** aios/core/catalog.py's module-level `_CACHE` dict (lines 34, 63-82) is read/written via an unlocked check-then-act sequence, unlike aios/api/deps.py's `_bedrock_lock`/`_gemini_lock` singleton pattern for the clients themselves. Under concurrent chat requests hitting the cache right after its 300s TTL expires, multiple threads independently call `client.list_models()` (a real network call) instead of one thread refreshing while the rest reuse the result.
- **unblocks:** Pairs with the retry/backoff item
- **risk if skipped:** Redundant discovery calls under concurrent load, wasting latency and rate-limit budget on the exact endpoints the retry/backoff item above says are already fragile under throttling.

### 40. No RAM/VRAM-aware model selection for the 16GB host
- **status:** not-started · **effort:** L
- **what:** Neither model_selector.select_model()/_score() nor router.candidates()/_best_model_for() has any awareness of host memory or which model Ollama currently has resident — grep for '16GB|VRAM|memory_ceiling|psutil' across aios/ returns nothing. Ranking is purely capability-tier + parameter-size. On this project's stated single 16GB laptop target, a failover cascade or an `auto` pick can propose loading a second large local model right after a first with no check that both fit resident simultaneously.
- **unblocks:** Plan A3 (RAM budget table); safe local-only autonomous operation (Phase B) on 16GB
- **risk if skipped:** On the exact hardware this system is built for, an unlucky failover or auto pick can degrade the whole host (swap thrashing) instead of degrading gracefully to a smaller model — undermines the 'local-first, resource-honest' pitch and Plan A3's not-yet-built RAM budget table.

### 41. No coverage-preview surface for the router's own ranked candidates
- **status:** not-started · **effort:** S
- **what:** router.candidates() already computes a rich, ranked, reasoned candidate list per task, but nothing under aios/api/routes/ exposes it as a read endpoint — there is no way to ask 'what would auto pick right now, across which providers, and why' without triggering a real (possibly cloud) chat turn.
- **unblocks:** A real coverage panel in the UI; pairs with the /health item
- **risk if skipped:** Operators/UI can't preview or audit routing coverage without sending a real message; harder to verify the README's 'Cloud routes detected and visualized in the UI' claim (line 33).

### 42. Default cloud output-token caps (1024) are low for the two task classes routed to cloud by default
- **status:** not-started · **effort:** S
- **what:** aios/config.py:262,268,276,282 — BEDROCK_MAX_TOKENS, GEMINI_MAX_TOKENS, OPENAI_MAX_TOKENS, and ANTHROPIC_MAX_TOKENS all default to 1024, with no task-aware scaling (no larger cap for reasoning/coding vs a trivial fast cloud call). These are exactly the providers ROUTER_CLOUD_TASKS defaults route reasoning and coding turns to — a coding tool-loop turn needing to emit a multi-hundred-line diff or a sequence of tool calls can silently truncate at 1024 output tokens.
- **unblocks:** Reliable cloud completions for coding/reasoning tasks
- **risk if skipped:** Silent truncation of cloud-generated diffs/tool-call sequences for exactly the task classes cloud is meant to help with — a correctness bug disguised as a config default.

### 43. Bedrock curated model fallback list may be stale
- **status:** not-started · **effort:** S
- **what:** aios/core/bedrock.py:41-48 CURATED_MODELS (used when live ListFoundationModels discovery is unavailable/denied — a common AWS posture per the module's own docstring) lists claude-3-5-sonnet-20241022-v2:0 / claude-3-5-haiku-20241022-v1:0 as the newest Anthropic entries, with no test or process tying its freshness to what AWS currently offers by default.
- **unblocks:** N/A — dependency hygiene
- **risk if skipped:** An account without control-plane discovery access silently offers only increasingly outdated models through auto, with no signal that the curated list needs a refresh.


## memory-knowledge

> The memory stack (aios/memory/*, ~5,200 lines across 23 modules) is architecturally serious and unusually well-guarded: quarantined fact proposals, contradiction detection, verification-strength-gated promotion, audited compaction, CRAG (all 3 slices shipped), and a hybrid BM25+FAISS+decay retriever all exist and are tested. The remaining work is concentrated in three honest gaps: (1) the P3 roadmap item (Project Passport) genuinely does not exist in code; (2) several real subsystems were built as pure library functions or read-only endpoints and never wired to the thing that would make them matter — a frontend reconcile action, a scheduler that calls compaction/decay, a calibration harness, a pheromone-to-prompt injection point; (3) retrieval/retention quality is uneven across memory types — chat memory gets hybrid semantic search and bounded storage, while skills/lessons/facts get lexical-only, unbounded, full-table-scan recall. None of this is fake-flagged roadmap; every item below is grounded in a specific file and, where relevant, a specific missing caller.

### 44. Project Passport harvester (P3) — does not exist
- **status:** not-started · **effort:** XL
- **what:** No aios/memory/project_passport.py, no CLI, no POST /api/v1/projects/scan. README marks P3 '❌ designed' and calls it 'the crux — everything downstream (taste learning, web navigation, earned autonomy) depends on accurate project understanding.' The ultra-plan (B2) already specs the exact shape: scan a project into {purpose, stack, commands, safe_files, risky_files, next_step}, store under .aios/projects/<id>/passport.{json,md}, construct its LLM client with cloud_tasks=frozenset() (local-only enforced in code, not just by default flag), apply the credential denylist, and test over >=5 real project fixtures.
- **unblocks:** Phase B (ai-editor self-improvement loop needs project understanding to pick sane next-steps), Phase F (external-project onboarding), P5 Taste Memory, P4 Web Navigator grounding
- **risk if skipped:** Every downstream autonomy/self-improvement plan in the ultra-plan stalls on a task-source that doesn't exist; without it the heartbeat loop (B3) has no principled way to choose what to work on beyond failing tests.

### 45. No scheduled/automatic memory maintenance — compaction, pheromone decay, and curriculum mining are all manual-trigger-only
- **status:** partial · **effort:** M
- **what:** aios/memory/compaction.py's MemoryCompactor (the 'sleep sweep') is only invoked from POST /api/v1/memory/compact (aios/api/main.py); PheromoneStore.decay_all() is only invoked from POST /api/v1/pheromones/decay (aios/api/routes/sovereignty.py); CurriculumMiner.list_proposals() is only invoked from GET /api/v1/development/curriculum/proposals. Grepped the whole aios/ tree for APScheduler/BackgroundScheduler/croniter/schedule.every — none exist anywhere in the codebase. Nothing runs these on a timer or on idle; an operator who never calls the endpoints gets a memory store that only ever grows.
- **unblocks:** Ultra-plan Phase A/B heartbeat loop; makes 'sleep-consolidation' in compaction.py's audit actor name actually true instead of aspirational
- **risk if skipped:** Unbounded local disk growth (SQLite + FAISS + rollback_git), stale pheromone signals never evaporating, and a curriculum that never grows itself — all silently, since there's no error, just accumulation nobody sees until disk pressure or latency shows up.

### 46. Compaction/retention covers only 3 of 9+ memory tables; the rest are fetched in full and scored linearly in Python on every recall
- **status:** partial · **effort:** L
- **what:** MemoryCompactor sweeps only working_memory, episodic_memory, and semantic_memory (aios/memory/compaction.py). mistake_pool, procedural_skills, semantic_facts, development_events, and knowledge_chunks have no forgetting/capping policy at all. Worse: MistakeMemory.relevant_verified (mistake.py) and SkillMemory.relevant_verified (skills.py) both run `SELECT * FROM ... WHERE status='verified'` with NO LIMIT, then score every row in Python with relevance() on every single recall call; SemanticFacts.search (facts.py) has the same no-LIMIT full-scan shape. Recall latency for lessons/skills/facts degrades linearly with lifetime history, forever, with no cap.
- **unblocks:** Long-run stability of the always-on daemon (ultra-plan Phase A/B/D burn-in) — 48h+ unattended operation needs bounded recall latency
- **risk if skipped:** After months of autonomous operation, every turn's lesson/skill/fact recall becomes a full-table Python scan over thousands of rows; the system gets measurably slower the longer it has been useful, and nothing currently detects or bounds this.

### 47. No memory database backup/restore/disaster-recovery tooling
- **status:** not-started · **effort:** M
- **what:** aios/memory/db.py has no export, backup, snapshot, or restore function — grepped for shutil.copy/VACUUM INTO/sqlite3 backup API/restore across aios/memory/*.py: zero matches. memory.db (SQLite, WAL mode) and the FAISS index are two files that must stay in sync (compaction.py's own comment notes 'FAISS cleanup happens outside the SQLite transaction'), and there is no tool to snapshot both together or restore from a prior snapshot after corruption or an operator mistake.
- **unblocks:** Operator trust in running compaction/consolidation for real; ultra-plan Phase D burn-in (memory + rollback_git disk-growth tracking implies backups exist, but they don't)
- **risk if skipped:** A bad compaction run, a corrupted WAL checkpoint, or an accidental DELETE has no recovery path except whatever ad hoc file copy the operator remembered to make — for a system whose entire pitch is 'memory must be earned' and irreversibly earned memory that gets lost is a real loss.

### 48. Contradiction-resolution UX is a dead end in the frontend
- **status:** partial · **effort:** S
- **what:** Backend POST /api/v1/memory/facts/reconcile (aios/api/routes/memory.py:344, backed by MemoryConsolidator.reconcile_fact in consolidation.py) is fully implemented and tested. frontend/src/workbench/SovereignStatePanel.jsx's fact-approval flow catches the 409 contradiction response and only throws a toast error ('it stays pending for reconcile') — grepped the whole frontend/src tree for 'facts/reconcile': zero callers. There is no UI action that lets the operator actually pick a resolution and call reconcile.
- **unblocks:** Closes the loop on the README's flagship 'contradiction is not silently committed — it is surfaced so the caller can route it to reconciliation' claim; makes the quarantine pipeline usable end-to-end from the UI, not just via curl
- **risk if skipped:** Every contradicted fact proposal sits in fact_proposals forever with status='pending' and no operator path to resolve it except a manual API call — the one guarantee (contradictions get surfaced AND resolved) is only half-true in the shipped product.

### 49. No operator-facing fact-graph browsing/editing surface
- **status:** not-started · **effort:** M
- **what:** SemanticFacts (aios/memory/facts.py, 535 lines) exposes search(), facts_for(), neighbors(), traverse(), and traverse_weighted() — a real multi-hop confidence-weighted knowledge graph — and GET /api/v1/memory/facts/graph exposes traverse() over HTTP. The only frontend consumer is frontend/src/superbrain/lib/aiosAdapter.ts:1317, feeding the 3D visualization. There is no page where the operator can search facts by subject/predicate, inspect a fact's neighborhood, or delete/edit an individual active fact outside the reconcile-on-contradiction path.
- **unblocks:** P5 Human Taste Memory (operator-editable preference memory is explicitly on the roadmap and needs exactly this surface); makes the 'operator can inspect memory, edit facts' README claim (line 218) concretely true beyond the narrow approve/reject queue
- **risk if skipped:** The knowledge graph is real but operator-invisible except through the 3D lattice's implicit rendering — no way to audit, correct, or prune what the system 'knows' about the operator/project without direct DB access.

### 50. Skill/lesson/development-outcome recall is purely lexical — no semantic fallback
- **status:** partial · **effort:** L
- **what:** aios/memory/relevance.py's relevance() is pure token-set-overlap (cosine-style Jaccard on tokens); it is the ONLY ranking signal for SkillMemory.relevant_verified (skills.py), MistakeMemory.relevant_verified (mistake.py), DevelopmentTracker.relevant_success_rate (development.py), and CurriculumManager._fuzzy_rows (curriculum.py). This is architecturally inconsistent with semantic_memory's hybrid_search (retrieval.py), which blends real BM25 + FAISS cosine + recency. A prior internal audit already flagged this exact gap ('Lexical relevance scorer has poor semantic coverage', 2026-06-29). A verified skill titled 'build a login form' will not be recalled for a goal phrased 'create an authentication UI' even though they're the same task.
- **unblocks:** Higher skill/lesson reuse rate (fewer redundant re-learning cycles), better curriculum fuzzy-matching precision
- **risk if skipped:** Verified skills and hard-won lessons systematically under-fire on paraphrased future tasks, so the system re-learns things it already proved it knows — directly undercuts the 'memory must be earned' and cerebellum-replay value proposition on anything but near-exact phrasing.

### 51. Uploaded-document (knowledge-chunk) search is a raw SQL LIKE scan, not FAISS-indexed
- **status:** not-started · **effort:** M
- **what:** aios/memory/doc_ingest.py's DocumentIngestor.search_chunks() does `WHERE LOWER(text_content) LIKE '%keyword%'` OR-chained across up to 5 keywords — the module's own docstring says 'A future version could use FAISS vector search on chunk embeddings.' This chunk store feeds _crag_document_source in aios/api/main.py, so operator-uploaded-document grounding (the one CRAG external source that's always privacy-safe, no cloud call) is weaker than every other retrieval path in the system.
- **unblocks:** Better CRAG document-grounding accuracy; brings knowledge_chunks in line with semantic_memory's embedding-backed recall
- **risk if skipped:** Uploaded reference docs (the safest, most privacy-clean knowledge source) are recalled worse than chat memory ever is — keyword mismatch silently drops relevant chunks with no signal to the operator that recall quality here is categorically weaker.

### 52. CRAG threshold calibration exists but has never been run against real data
- **status:** not-started · **effort:** M
- **what:** aios/memory/crag.py's calibrate_thresholds() is a fully implemented, tested, grid-search calibrator for AIOS_CRAG_UPPER/AIOS_CRAG_LOWER. Grepped the whole repo for calls to it outside tests/test_crag.py — zero. The design doc (docs/superpowers/specs/2026-06-29-crag-for-gagos-design.md) explicitly says the shipped 0.6/0.2 defaults are 'GAGOS starting points to be tuned against the operator's corpus — not a direct port of the paper's numbers,' but there is no harness that logs (score, is_relevant) labels from real retrievals or a CLI/scheduled job that periodically re-calibrates and reports drift.
- **unblocks:** Evidence-backed CRAG thresholds instead of permanent spec-default guesses; a template for the same pattern other calibrated constants in the system could use
- **risk if skipped:** CRAG's tripartite routing (CORRECT/AMBIGUOUS/INCORRECT) runs forever on untuned thresholds with no mechanism to discover they're wrong for this operator's actual corpus, silently capping the accuracy the whole CRAG investment was for.

### 53. Curriculum self-mining is single-domain and partly dead code
- **status:** partial · **effort:** M
- **what:** aios/memory/curriculum_miner.py's CurriculumMiner._generate_variants() hardcodes `templates = _ESCALATION_TEMPLATES.get("create_and_test", [])` — the module defines `refactor_and_test` and `extend_and_test` template families (lines 50-56) that are never selected by any code path, so 2 of 3 defined escalation strategies are unreachable. `_extract_module_name` requires the literal `training_ground/(\w+)\.py` shape, so mining only works on the synthetic Python training-ground corpus — verified successes from self-analysis fixes, frontend work, docs, or any real (non-training-ground) task can never seed a new curriculum task.
- **unblocks:** Curriculum breadth beyond the synthetic Python training ground — mining real verified work into practice tasks
- **risk if skipped:** 'Self-curriculum' is real for one narrow synthetic task shape and inert everywhere else; the system's actual growing competence (self-analysis fixes, frontend changes, doc work) never turns into deliberate practice.

### 54. Operator-fact auto-extraction coverage is narrow (3 regex templates, first-person English only)
- **status:** partial · **effort:** M
- **what:** aios/memory/fact_extraction.py's extract_candidates() matches exactly three high-precision patterns: 'I prefer/use/like/want/need X', 'we/this project uses/runs on/depends on X', and 'my X is Y'. This is a deliberate precision-over-recall design (the module docstring says false negatives are fine) reading only the operator's own text (never file/model output — correctly isolated for the memory-poisoning risk). But the practical effect is that most real preference statements ('let's go with Postgres instead', 'call me Swap', 'always run pytest before committing') never generate a proposal at all, so the quarantine pipeline that Project Passport / taste memory depend on stays mostly empty in practice.
- **unblocks:** P5 Human Taste Memory depends on a non-trivial flow of proposed facts to approve; currently the funnel's top is nearly closed
- **risk if skipped:** The whole proposal->approval->active pipeline (correctly built, contradiction-safe, well-tested) stays underfed indefinitely because almost nothing operators actually say matches the 3 supported sentence shapes.

### 55. Generic PheromoneStore's one behavioral hook (for_contract) is never called — orphaned system
- **status:** partial · **effort:** S
- **what:** aios/memory/pheromones.py's PheromoneStore.for_contract(allowed_files) is the only method designed to inject pheromone context into an agent's working contract/prompt. Grepped the full repo for callers of for_contract — zero. The store is fully wired for CRUD (deposit/reinforce/query/decay via aios/api/routes/sovereignty.py, gated behind AIOS_PHEROMONE_ENABLED=False by default) but has no path back into agent behavior. This is a distinct system from the (properly wired) reuse-pheromone math already live inside SkillMemory.record_reuse/relevant_verified in skills.py — so there are two 'pheromone' concepts in the codebase, only one of which does anything.
- **unblocks:** Either wire for_contract() into the tool-agent's per-turn context assembly (main.py) so file-lock/failure-warning/attention-signal pheromones actually influence behavior, or remove the dead surface and its API routes to stop it reading as a shipped feature
- **risk if skipped:** A fully-built, tested, API-exposed stigmergy system silently does nothing to the agent's behavior; an operator who deposits a FAILURE_WARNING pheromone on a resource via the API would reasonably expect it to change future agent behavior near that resource, and it currently cannot.

### 56. No embedding-model version tagging or reindex path
- **status:** not-started · **effort:** M
- **what:** aios/config.py's AIOS_EMBEDDING_MODEL/AIOS_EMBEDDING_DIM are freely overridable, and aios/memory/embeddings.py's VectorIndex/EmbeddingModel have no stored model identifier anywhere in the FAISS index or semantic_memory schema. Changing the embedding model (e.g., upgrading all-MiniLM-L6-v2) after the index already has vectors either dimension-mismatches (hard crash) or silently produces a FAISS index whose old vectors were encoded by a different model than new queries, making retrieval scores meaningless with no detection.
- **unblocks:** Safe future embedding-model upgrades (better local models will exist within this project's lifetime)
- **risk if skipped:** The first time anyone changes AIOS_EMBEDDING_MODEL, the semantic memory silently degrades (mixed-model vector space) or hard-crashes on dimension mismatch, with no migration tool to re-embed the existing corpus into the new space.


## observability-cognition

> Today's "observability" is really two disconnected things wearing one name: (1) a per-turn SSE cognition stream (`aios/core/events.py` + `_sse()`/`_sse_writer()` in `aios/api/main.py`) that only exists for the duration of an in-flight `/api/generate` or `/api/v1/chat` request, and (2) a real Prometheus/Grafana/Alertmanager stack (`observability/*.yml`, `aios/core/metrics.py`) that is genuinely wired but only exposes ~13 coarse gauges. Between them: no standalone `/api/v1/cognition/stream` endpoint (confirmed absent, matches GAGOS_ULTRA_PLAN.md C1), no fan-out bus that could feed one, and three parallel, non-unified event schemas (typed SSE `Event`, the free-text `CortexBus` outbox, and `CouncilState`'s own private SQLite tables) that don't share an id space or a sink. Whole subsystems (`aios/runtime/worker_entry.py`, `worker_api.py`, `spawner.py`, and `aios/council/council_state.py`) emit zero structured logs and zero cognition events — confirmed by grep, not inference. Telemetry data that already exists (`aios/core/telemetry.py`'s dispatch-path/token/latency rows) never reaches Prometheus. There is no request_id↔turn_id correlation, no tracing concept, no log rotation, no readiness probe, and the one alerting receiver configured is a documented dummy sink. None of this is a redesign — it's finishing wiring that's mostly already scaffolded.

### 57. Build GET /api/v1/cognition/stream
- **status:** not-started · **effort:** L
- **what:** A standalone SSE endpoint (referenced in GAGOS_ULTRA_PLAN.md Phase C1 but not implemented anywhere in aios/api/routes/* or main.py — confirmed by route grep). Needs `?run_id=` / `?sources=` query filters, a 15s heartbeat frame, and `Last-Event-ID` resume semantics. Today the frontend's `subscribeCognition`/`publishCognition` bus (frontend/src/superbrain/lib/cognitionBus.ts) only receives events that some caller manually pipes in from the per-turn `/api/generate` SSE parse — there is no backend source a second observer (another tab, an ops dashboard) could subscribe to independently of an in-flight chat turn. This is the single biggest reason the 3D superbrain 'goes dormant when there is no data' (README's own honest disclosure) rather than showing background/autonomous activity.
- **unblocks:** Autonomous heartbeat-loop visibility (Phase B3/B4), any second-observer tooling (ops dashboard, mobile notifier)
- **risk if skipped:** The 'living being' visualization can only ever reflect synchronous chat turns; any future autonomous/heartbeat loop (GAGOS_ULTRA_PLAN Phase B3) has no way to surface its activity to the operator in real time — undermining the whole 'always-on sovereign brain' pitch.

### 58. In-process cognition event fan-out bus
- **status:** not-started · **effort:** M
- **what:** A prerequisite for the item above: today `_sse()`/`_sse_writer()` (aios/api/main.py lines 760-789) yield event strings directly into the single StreamingResponse generator of the request that produced them. There is no broadcast mechanism — no pub/sub, no second SQLite outbox tier — that a concurrently-connected `/api/v1/cognition/stream` client could tap. `CortexBus` (aios/runtime/cortex_bus.py) is architecturally the wrong tool for this: it's a durable cold-path outbox for off-hot-path observers (self-model rebuild) and structurally refuses six 'authority' event prefixes by design — it was never meant to be a live multi-subscriber broadcast layer, and repurposing it needs a deliberate decision, not a reuse-by-accident.
- **unblocks:** GET /api/v1/cognition/stream
- **risk if skipped:** Without this, the cognition-stream endpoint above can only be built as a second copy of the per-turn SSE loop (duplicated logic, drifting behavior) rather than a real shared bus.

### 59. Unify the three parallel event/observability schemas
- **status:** not-started · **effort:** L
- **what:** Three independent event shapes exist with no shared id space or sink: (1) `aios/core/events.py`'s typed `Event`/`EventType`/`EventPhase` — covers only the per-turn SSE stream, and is driven by a hand-maintained `_SSE_TO_COGNITION` string→enum dict (line 35) where an unmapped SSE event name silently falls back to `EventType.SYNTHESIS` rather than erroring, so a new event added at a call site without a matching dict entry is silently misclassified, not caught; (2) `aios/runtime/cortex_bus.py`'s `cortex_events` table — free-text `event_type`/`signature` strings with only a 6-prefix authority-blocklist as structure, and in practice only two event_type strings are ever appended anywhere in the codebase (`turn.completed`, `facts.proposed` — confirmed by grep, aios/api/main.py:293,2059,2690); (3) `aios/council/council_state.py`'s private `queen_verdicts`/`council_events` SQLite tables — yet another shape (`event_type`, `queen_name`, `payload_json`, `risk`, `snapshot_id`) that never touches the SSE layer or CortexBus at all.
- **unblocks:** Cross-subsystem tracing, a real cognition-stream schema, Council visibility in the frontend
- **risk if skipped:** 'Uniform instrumentation across all subsystems' (this area's own charter) stays aspirational — three teams of code produce three shapes of 'what happened,' none queryable together, so any cross-subsystem question ('did the King's veto on mission X correlate with the turn that triggered cerebellum replay Y?') requires manually joining three SQLite files by timestamp.

### 60. Wire Council/King deliberation into the cognition bus
- **status:** not-started · **effort:** M
- **what:** `CouncilState.record_verdict`/`record_event` (aios/council/council_state.py) persist every Queen verdict and council lifecycle event to SQLite, but nothing forwards them to `_cortex_bus.append()` or the SSE stream — confirmed no `cortex_bus`/`event_for_sse`/`_sse` import anywhere in aios/council/*.py. The frontend's own cognitionBus already supports arbitrary event types, but Council activity never reaches it (matches a prior session's own finding that CouncilDashboard doesn't publish cognition events despite the bus supporting it).
- **unblocks:** Honest real-time King-veto visualization; depends on the unified schema item above
- **risk if skipped:** The King veto — README's own words, 'the most sovereignty-relevant organ in the system' — is invisible to the live cognition visualization; an operator watching the superbrain has no real-time signal that a council deliberation or veto is even happening.

### 61. Correlate HTTP request_id with SSE turn_id
- **status:** not-started · **effort:** S
- **what:** `bind_request_context` middleware (aios/api/main.py:365-399) stamps every HTTP request with `x-request-id` via structlog contextvars. Independently, `_sse_writer()` (line 781) mints its own `turn_id` (== the caller-supplied `session_id`, not the request_id) with its own local `seq` counter. The two identifiers are never cross-logged or included in each other's payload — a `request_id` visible in an access-log line cannot be used to find the matching cognition/SSE events for that same HTTP call, and vice versa.
- **unblocks:** End-to-end run tracing
- **risk if skipped:** Debugging a specific failed turn from logs requires guessing which session_id/turn_id corresponds to which request_id by timestamp proximity — exactly the friction 'tracing a full run end-to-end' is supposed to remove.

### 62. Structured logging in worker/spawning/council subsystems
- **status:** not-started · **effort:** M
- **what:** Confirmed by grep: zero `logging`/`logger` usage in aios/runtime/worker_entry.py, worker_api.py, spawner.py, king_report.py, live_surface.py, rollback_registry.py, run_ledger.py, budget_guard.py, concurrency.py, intelligence_gateway.py, secret_policy.py, snapshots.py, turn_state.py, worktree_backend.py, and aios/council/council_state.py. Only cortex_bus.py, cortex_bus_dispatcher.py, self_model_handler.py, council_orchestrator.py, and reasoning.py have a logger at all. When a spawned worker crashes, times out, or a council deliberation errors, there is no structured log line and no cognition event — the only trace is whatever the synchronous caller happens to capture in the returned `WorkerResult`/`QueenVerdict` object, which is invisible to any external observer (ops log, alerting, the audit trail).
- **unblocks:** GAGOS_ULTRA_PLAN Phase D2 burn-in measurement harness; reliable postmortems for autonomous runs
- **risk if skipped:** A worker/mission failure during unattended/autonomous operation (the whole point of GAGOS_ULTRA_PLAN's Phase B heartbeat loop) leaves no trace an operator or monitor could find without reproducing the failure — directly undermines the plan's D2 burn-in monitor requirement to 'track success rate, autonomy grants, event-drop rate.'

### 63. End-to-end run tracing (plan -> tool-loop -> verify -> reflection -> memory)
- **status:** not-started · **effort:** L
- **what:** No tracing library is present anywhere (`grep -rli opentelemetry|OTLP|jaeger|zipkin aios` returns nothing; requirements.txt/pyproject.toml declare only structlog + prometheus-client). There is no span/trace concept linking one turn's plan-stage decision, tool-loop calls, verification result, reflection write, and memory promotion into one traceable unit. The closest proxy — the per-turn SSE `seq` counter — dies with the HTTP response and is never persisted anywhere queryable afterward (CortexBus doesn't carry seq or turn_id linkage). Reconstructing 'what happened in run X' today means manually joining `run_telemetry` rows, audit-ledger entries, and log lines that happen to share a session_id, by hand.
- **unblocks:** Real postmortem tooling; the unified event schema's practical payoff
- **risk if skipped:** Directly named in this area's charter ('tracing a full run end-to-end') and currently impossible without manual cross-referencing across 3+ SQLite stores; makes debugging any multi-step failure (e.g. plan produced a bad step, tool executed it, verification should have caught it but didn't) far slower than it needs to be.

### 64. Expose route-mix / dispatch-path / token-cost as Prometheus metrics
- **status:** not-started · **effort:** M
- **what:** `aios/core/telemetry.py` already computes exactly what's needed — `sovereign_hit_rate`, `verified_success_rate_by_path`, `cost_per_verified_success`, `hit_rate_by_session` — from the `run_telemetry` table, but the only consumer is the `python -m aios.core.telemetry` CLI report (`print_report`). None of it is registered as a Gauge/Counter in `aios/core/metrics.py`'s `MetricsCollector`, so `/metrics` (and therefore Prometheus/Grafana, which are already deployed via docker-compose.yml) cannot chart local-vs-cloud route mix, per-path verified-success rate, or token cost over time — the exact 'route mix, tokens' signal this area's charter names.
- **unblocks:** Grafana dashboards/alerts on route mix and cost; egress-spike alerting relevant to the privacy thesis
- **risk if skipped:** The already-built Prometheus/Grafana/Alertmanager stack (observability/prometheus.yml, alert_rules.yml, grafana/dashboards/aios-dashboard.json) can't answer 'what fraction of traffic is going to the cloud right now' or 'is cost-per-verified-success trending up' without someone manually running the CLI report — a real gap given the README's sovereignty claims hinge on local-first routing being observable.

### 65. Event-drop metric for CortexBus retention drops
- **status:** not-started · **effort:** S
- **what:** `CortexBus.append()` (aios/runtime/cortex_bus.py lines 159-177) fail-softly drops the oldest pending/dispatched rows when `retention_max` is exceeded, and only calls `logger.warning(...)` — no counter is incremented anywhere. GAGOS_ULTRA_PLAN.md's Phase D2 (48h burn-in) explicitly asks for the burn-in monitor to track 'event-drop rate,' which today would require grepping logs for the warning string rather than reading a metric.
- **unblocks:** GAGOS_ULTRA_PLAN Phase D2 burn-in measurement harness
- **risk if skipped:** Silent data loss in the cognition/observation pipeline under load has no dashboard signal; the burn-in monitor named in the plan can't be built as 'not prose' (the plan's own words) without this.

### 66. Per-class autonomy-grant metrics + plan-stage advisory outcome metric
- **status:** not-started · **effort:** S
- **what:** `MetricsCollector` (aios/core/metrics.py) exposes only a flat `aios_earned_autonomy_grants_total` gauge — there is no per-action-class breakdown, even though the README's earned-autonomy story is specifically 'a narrow action class may skip approval after 5 consecutive verified successes for that exact class.' Similarly, there is no metric for the now-default-on `AIOS_PLAN_STAGE` advisory pass/skip/fail-open outcomes emitted per turn.
- **unblocks:** Autonomy-ladder dashboards; plan-stage health monitoring
- **risk if skipped:** Can't graph 'which action classes have earned autonomy and when' or verify the plan-stage's fail-open behavior isn't silently degrading in production — both directly relevant to the honesty claims the README makes about earned autonomy being 'proof-of-work, not a setting.'

### 67. Log rotation / durable file sink
- **status:** not-started · **effort:** S
- **what:** `aios/logging_config.py` configures structlog to a single `logging.StreamHandler(sys.stderr)` — no `RotatingFileHandler`/`TimedRotatingFileHandler`, no file sink at all. Confirmed no logging-driver/max-size config in docker-compose.yml or Dockerfile either. Named explicitly in GAGOS_ULTRA_PLAN.md's list of why v1 wasn't cold-buildable ('no log-rotation').
- **unblocks:** Reliable post-crash forensics for the always-on autonomous host
- **risk if skipped:** On an always-on host (the explicit goal of Phase B's heartbeat loop) there is no persistent log to inspect after a crash or the 3am forced-reboot scenario the plan itself calls out, unless a process supervisor happens to capture and rotate stderr externally.

### 68. Readiness probe distinct from liveness
- **status:** not-started · **effort:** S
- **what:** `GET /health` (aios/api/routes/system.py:83-86) returns a hardcoded `{"status": "ok", "version": ...}` with zero dependency checks — it never verifies Ollama reachability, DB writability, or disk space. There is no separate `/ready` endpoint that would let an orchestrator (or the future always-on supervisor) distinguish 'process is up' from 'process can actually serve a turn.'
- **unblocks:** Safe automated restarts for the always-on host
- **risk if skipped:** A restart/supervisor loop watching only `/health` would keep routing traffic to a process whose Ollama connection or DB is actually down, since liveness alone can't detect that.

### 69. Schedule CortexBus.sweep() retention
- **status:** partial · **effort:** S
- **what:** `CortexBus.sweep()` (aios/runtime/cortex_bus.py:263) implements day-based retention of dispatched events, but is called from nowhere in production code — only from tests/test_cortex_bus.py. The count-based cap inside `append()` keeps the table bounded, but the intended 7-day (`CORTEX_BUS_RETENTION_DAYS`) time-based sweep never runs, so dispatched rows can sit indefinitely as long as the table stays under `retention_max`.
- **unblocks:** N/A — self-contained cleanup
- **risk if skipped:** Minor: cortex_bus.db grows larger and holds older data than the configured retention_days implies — a small honesty gap between the config knob's documented behavior and what actually happens.

### 70. Wire a real Alertmanager receiver; broaden alert rules
- **status:** partial · **effort:** S
- **what:** observability/alertmanager.yml's own comment says it all: 'By default this routes alerts to a dummy sink' (`http://127.0.0.1:1/dummy`) — no real notification channel (Slack/ntfy/email/webhook) is configured, so a firing alert is only visible by someone actively watching http://localhost:9093. Additionally, alert_rules.yml has only 3 rules (audit-chain-broken, high-intervention-rate, high-HTTP-error-rate) — none for cortex-bus-dispatcher-died (`CortexBusDispatcher.is_running` is never scraped), event-drop rate, or cloud-egress spikes (a privacy-relevant signal given the README's egress-opt-in claims).
- **unblocks:** Real unattended-operation safety net
- **risk if skipped:** An unattended, always-on host (Phase B's explicit goal) that hits a critical condition overnight notifies no one — the operator finds out only by checking a dashboard, which contradicts the point of alerting.


## frontend-organism

> The 3D superbrain frontend (frontend/src/superbrain + frontend/src/workbench) is far more mature than the thesis audit's cited component names suggested — most of the audit's "fabricated data when offline" complaint was already fixed in SuperbrainHUD.tsx's SourceRow (proper linkUp/hasRealValue gating, "--" dormant state) and MemoryGalaxy.tsx (renders null with zero trails). But the fix was NOT applied uniformly: two other components read the exact same metricsStore and still paint the store's Math.random() offline demo-drift as if it were live telemetry — WorkTabLiveDashboard (labeled "LIVE · BODY" on-screen, in MaterializedTab.tsx) and RegionPins.tsx's brain-region callouts. Beyond that, the cognition state machine is real and event-driven (cognitionBus.ts + lifecycleStateMachine.ts + SuperbrainHUD's derivePhaseFrom, all unit-tested), but three backend-emitted "sovereignty" events (reflex-recall/graph-recall/template-plan — literally the thesis's "no LLM consulted" moments) have zero visual consumer, the King council's real approval/veto surface (CouncilDashboard.jsx) never touches the cognitionBus even though the 3D organism has a decorative crown-anatomy placeholder reserved for it, and the primary in-3D ApprovalPanel has no rollback/undo affordance despite a backend /api/v1/rollback endpoint existing. Memory-ladder telemetry (candidate/superseded counts) is computed by the adapter but never rendered anywhere. There is no event-replay/session-history surface at all. A confirmed shipped regression (BUG-A, first flagged 2026-06-19) still prevents skill-mastery events from flashing their star in MemoryGalaxy. One color-only accessibility gap remains in the memory visualization.

### 71. Fix offline data fabrication in WorkTabLiveDashboard ("LIVE · BODY" panel)
- **status:** not-started · **effort:** S
- **what:** frontend/src/superbrain/components/canvas/MaterializedTab.tsx, function WorkTabLiveDashboard (~lines 946-1026). It calls useMetric('research'/'memory'/'tools'/'signals') directly and renders the bars + sparkline unconditionally under a label reading literally 'LIVE · BODY'. metricsStore.ts drifts these values with Math.random() whenever the adapter link is down (linkUp=false), so this panel paints fabricated percentages/bar heights as real telemetry while offline — the exact 'WorkTabLiveDashboard' pattern the thesis audit flagged, still unfixed, even though the sibling SourceRow component in SuperbrainHUD.tsx was already fixed with a hasRealValue = linkUp && samples>=1 gate that falls back to a dormant '--' state. Fix: import getLinkState()/subscribe to linkUp the same way SourceRow does, and render a dormant floor state (zeroed bars + no sparkline, or panel hidden) when offline.
- **unblocks:** Closes the single most reputationally damaging item from the thesis audit (fabricated-data-when-offline) with the correct component name now identified; needed before any README claim of 'goes dormant when there is no data' can be honestly asserted project-wide.
- **risk if skipped:** The product's central honesty claim ('honest: goes dormant when there is no data') is falsifiable by simply disconnecting the backend and watching this exact panel — a demo-breaking, thesis-breaking bug hiding in plain sight under a 'LIVE' label.

### 72. Fix offline data fabrication in RegionPins brain-region callouts
- **status:** not-started · **effort:** S
- **what:** frontend/src/superbrain/components/canvas/RegionPins.tsx, component PinChip (~lines 81-132). <strong>{value}%</strong> renders useMetric(pin.key) with no linkUp check at all — the four cortex-surface pins (RESEARCH/MEMORY/TOOLS/SIGNALS) always show a number, real or fabricated. The click-to-expand history graph is honest ('no real samples yet' when history.length<2), but the always-visible headline percentage is not gated the way SuperbrainHUD's SourceRow is. Apply the same hasRealValue = getLinkState() && useMetricHistory(key).length>=1 gate used in SourceRow, falling back to a dormant glyph instead of a number.
- **unblocks:** Second confirmed instance of the same offline-fabrication bug — should be fixed in the same PR as WorkTabLiveDashboard since it's the same root cause (metricsStore's dormancy fix was applied to one consumer, not all four consumers of useMetric).
- **risk if skipped:** Same failure mode as item 1, on the pins painted directly onto the brain's visible cortex — arguably the most visible surface in the whole UI.

### 73. Build a memory metabolism panel (candidate / verified / quarantined / superseded)
- **status:** not-started · **effort:** M
- **what:** aiosAdapter.ts already computes telemetry.candidate and telemetry.superseded (lines ~1249-1251) alongside telemetry.verified/quarantined, but grep across frontend/src/superbrain confirms zero consumers read telemetry.candidate or telemetry.superseded anywhere — only .quarantined is visualized (CognitiveGrasp.tsx cage color, MemoryGalaxy.tsx red stain). There is no panel showing the memory ladder (Observation -> Proposal(candidate) -> Human approval -> Verified use -> Reusable experience, with superseded/contradicted facts called out) that the README's 'How knowledge earns trust' section describes as core to the product. Build a small HUD panel or extend SuperbrainHUD with a memory-ladder strip driven by these already-computed real numbers.
- **unblocks:** Makes the 'quarantined memory pipeline... facts are proposed, then human-approved, then active' claim (README line 34) visible and auditable at a glance, not just true in the backend.
- **risk if skipped:** The memory-approval workflow — one of the product's core trust mechanisms — is invisible to the operator in the living-organism view; they'd have to go elsewhere (API/logs) to see how many facts are awaiting their approval.

### 74. Fix MemoryGalaxy mastery-flash regression (BUG-A, unfixed since 2026-06-19)
- **status:** not-started · **effort:** S
- **what:** frontend/src/superbrain/components/canvas/MemoryGalaxy.tsx line ~172: const match = /trail #(\d+)/.exec(event.detail ?? ''). aiosAdapter.ts's skill.mastered handler (line ~499-513) publishes detail: 'curriculum level mastered under the STRONG verification floor' (no 'trail #N'), and its TRAIL-mastery handler (line ~1159-1164) puts 'TRAIL #{id}' in event.label (not event.detail) while event.detail is trailLabel(...).toLowerCase() (also no 'trail #N'). Because MemoryGalaxy's regex only checks event.detail, neither mastery pathway ever flashes its star — only the generic 'trail #N reinforced' event (line 1143) does. Fix: also match against event.label, or standardize the emit sites to include 'trail #N' in detail.
- **unblocks:** Restores the intended payoff moment ('over weeks the operator literally watches his AI's skill-space grow' — MemoryGalaxy.tsx's own doc comment) for the single most celebratory event type in the system.
- **risk if skipped:** A shipped, previously-flagged regression stays silently broken; the visual reward for the product's proudest claim (skill mastery) never fires.

### 75. Visualize the sovereignty S1/S2/S3 events (reflex-recall, graph-recall, template-plan)
- **status:** not-started · **effort:** M
- **what:** cognitionBus.ts's CognitionEventType includes 'reflex-recall' (cerebellum playbook replay, no LLM), 'graph-recall' (knowledge-graph inference chain, no LLM), and 'template-plan' (native planner from verified templates, no LLM) — described in the type's own doc comments as exactly the moments that prove the thesis ('the model is never trusted... trust the system'). aiosAdapter.ts emits all three (lines 536, 549, 604, 634). A full-repo grep confirms zero consumers: no canvas component, no SuperbrainHUD case, no phaseWeather mapping reacts to any of the three (contrast with 'hesitation', 'verify', 'voice-speaking', which are all consumed). SuperbrainHUD's terminal switch statement (the 'living terminal log') has no case for any of them either, so they don't even appear as a text line.
- **unblocks:** This is the single clearest place the frontend could visually PROVE the core belief ('the model is never trusted, the system is trusted') by showing the operator, in real time, exactly when the system acted WITHOUT consulting an LLM — currently that signal exists end-to-end in the backend and dies silently at the frontend door.
- **risk if skipped:** The most thesis-central telemetry the backend produces has no observable effect on the product at all — an operator can never see the sovereignty story the README tells.

### 76. Connect the King council surface (CouncilDashboard.jsx) to the living organism
- **status:** not-started · **effort:** L
- **what:** frontend/src/workbench/CouncilDashboard.jsx (King deliberation/proposer/veto/rollback for autonomous missions) is mounted as a top-level DOM overlay sibling of SwarmHUD/OperatorProfileCard/TrustHalo in GagosChrome.jsx (line ~1003), completely separate from the 3D canvas tree. A repo-wide grep confirms it never imports cognitionBus or calls publishCognition — none of its deliberation/proposal/veto/rollback actions reach the terminal log, the brain cloud, or NodeLattice's ROUTER hub. Notably, SuperbrainScene.tsx already has a decorative 'DORMANT WONDER' four-seat crown anatomy explicitly reserved for 'council reasoning/origination' (comment at line ~1445-1449) that stays permanently caged/dark because nothing ever wakes it — the visual placeholder exists but is never driven by real King activity.
- **unblocks:** README calls the King 'the most sovereignty-relevant organ in the system' — wiring CouncilDashboard into cognitionBus would let the crown anatomy actually wake for real veto/approval events, making the organism's most safety-critical function visible instead of living only in a disconnected DOM panel.
- **risk if skipped:** The organism's 'one living being' narrative breaks at exactly its most important safety moment: a King veto is invisible to the 3D view an operator is actually watching. (Alternatively, if the product decision is to keep it a deliberately separate console, the crown-seat anatomy placeholder should be removed rather than left permanently dark — either way this is undecided, unshipped work.)

### 77. Add rollback/undo affordance to the primary in-3D ApprovalPanel
- **status:** not-started · **effort:** M
- **what:** frontend/src/superbrain/components/ui/ApprovalPanel.tsx has AUTHORIZE/REJECT only — no post-decision revert path. The backend already exposes POST /api/v1/rollback (main.py line ~12, 'restore the sandbox to a prior snapshot') plus /api/v1/runtime/rollbacks/register|prune, but ApprovalPanel never surfaces them. The only rollback UI in the whole frontend is CouncilDashboard.jsx's submitRollback (lines 320-353), which is scoped to King council missions via a different endpoint (/api/v1/council/missions/{id}/rollback) — the everyday per-turn write/command/browse approvals that most operator interactions go through have no 'undo this' path in the UI at all.
- **unblocks:** Phase B5 (morning digest v2's 'one-click revert') and general operator trust — an operator who authorizes a write and later regrets it currently has no in-product way to undo it outside the council-mission flow.
- **risk if skipped:** Every day-to-day approved action (the common case, not the rare council mission) is a one-way door in the UI even though the backend already supports snapshot-based reversal.

### 78. Build event replay / session history surface
- **status:** not-started · **effort:** L
- **what:** No component anywhere under frontend/src/superbrain implements session replay, a persisted event timeline, or a scrollback beyond SuperbrainHUD's live terminal buffer, which is hard-capped at TERM_BUFFER_MAX = 4 lines and resets on remount (SEED_TERM_LINES). There is no way for an operator to scrub back through what the organism did this session, let alone a past (e.g. overnight autonomous) session — cognitionBus is fire-and-forget pub/sub with no persistence layer.
- **unblocks:** Directly required by GAGOS_ULTRA_PLAN.md Phase B5 ('Morning digest v2 — per-workspace actions... one-click revert') and Phase D2 burn-in ('a monitor that fails on the first out-of-scope write... tracks success rate') — both need a queryable history the frontend can render; today that history doesn't exist client-side at all.
- **risk if skipped:** An always-on autonomous loop (the GAGOS_ULTRA_PLAN north star) that ran overnight would have literally no frontend surface for the operator to review what happened — they'd be reading raw audit-ledger files instead of the product.

### 79. Fix color-only quarantine indicator in MemoryGalaxy (WCAG 1.4.1)
- **status:** not-started · **effort:** S
- **what:** frontend/src/superbrain/components/canvas/MemoryGalaxy.tsx's GALAXY_FRAGMENT shader (lines 66-90) distinguishes a quarantined skill-trail from a healthy one purely by color — 'stain' mixes cyan (vec3(0.3424,0.7484,1.0)) toward red (vec3(1.0,0.0732,0.0470)) with no shape, size, or pattern difference. A colorblind operator (deuteranopia/protanopia, ~8% of men) cannot distinguish a quarantined trail from a strong healthy one in the galaxy view.
- **unblocks:** Closes a concrete, easily-fixed WCAG 1.4.1 (Use of Color) failure in an otherwise well-built, honestly-dormant component.
- **risk if skipped:** Minor but real accessibility gap; low cost to fix (e.g. a pulsing ring or distinct point shape for quarantined stars, already scaffolded via the existing vFlash/vQuarantine varyings).

### 80. Add a persistent local-vs-cloud routing trust ledger
- **status:** not-started · **effort:** M
- **what:** The 'route' cognitionBus event (which brain/provider served each turn, whether it stayed local) is consumed transiently by IdentityReadout.tsx, NodeLattice.tsx (lights the ROUTER hub), SuperbrainHUD.tsx (one terminal line), and turnMetabolism.ts — all one-shot reactions to the CURRENT turn. Nothing accumulates a running 'N local calls / N cloud calls this session' tally the operator can audit at a glance. README's honesty section explicitly flags this as the crux of the sovereignty claim ('the moment GAGOS routes to a cloud model, it sends operator data to a third party... Sovereignty lives with the operator, not the machine') yet the UI only flashes a lightning bolt per-turn with no persistent record.
- **unblocks:** A visible, at-a-glance sovereignty audit trail that matches the README's own framing of 'landlord of governance, tenant of compute' — currently the only way to know how many cloud calls happened this session is to count transient flashes or read the audit ledger file directly.
- **risk if skipped:** The product's single most-hedged honesty claim (infrastructure sovereignty is NOT claimed, only governance is) has no persistent UI evidence trail — an operator who steps away for a minute has no way to know how many cloud calls happened while they weren't watching.


## testing-ci-quality

> The suite is broad (141 backend test files, ~2,550+ test functions, ~85-92% branch coverage gated at 85% in CI) and CI correctly runs backend (pytest+coverage+pip-audit) and frontend (typecheck+vitest+coverage+build) on every push/PR, with dependabot covering dependency updates. What's missing is everything beyond "does the code pass the tests already written": there is no chaos/torture suite, no burn-in harness, no static-analysis gate (mypy/bandit), no nightly/scheduled job of any kind, the frozen-core CI backstop named in the ultra-plan (0.3) doesn't exist, the container-executor tests are mocked rather than real (no CI job ever runs `docker build`), the two e2e demo scripts never actually run in CI (wrong filename pattern for pytest collection), and several operational prover/harness tools (learning_loop_prover.py, endurance_tester.py, golden_mission_runner.py, daily_use_probe.py, preflight.py) exist and work but are 100% manual-invocation, wired into nothing automated.

### 81. Chaos/torture test suite (tests/torture/) does not exist
- **status:** not-started · **effort:** L
- **what:** Create tests/torture/ (currently empty; plan calls for it in D1) with named-fixture tests: kill Ollama mid-stream (actually interrupt the live process during an in-flight SSE generation, not just raise a mocked LLMError as tests/test_tool_agent.py currently does around lines 420/1564); disk-full simulation (no ENOSPC/disk-full test exists anywhere in tests/); concurrent missions vs worker-pool cap under real contention (tests/test_runtime_concurrency.py only unit-tests the pool's accept/reject logic, not a live multi-mission race); a systematic injection barrage — one test with a fixed corpus of ~50 known-bad strings asserting 100% block rate (today injection coverage is scattered as individual cases across 13 files: test_security.py, test_chat_input_shield.py, test_generate_input_shield.py, adversarial/test_gateway_bypass.py, adversarial/test_sandbox_escape.py, etc. — good breadth, no single pass/fail barrage gate); an approval-race test proving exactly one of two concurrent approval submissions for the same token wins (no test file references concurrent-approval resolution anywhere).
- **unblocks:** GAGOS_ULTRA_PLAN Phase D1; confidence that fail-closed guarantees hold under real contention/failure, not just mocked happy-path unit tests
- **risk if skipped:** The security spine (scope_lock, approval gate, worker cap) is proven only against mocked single-threaded inputs; a real concurrent-approval double-spend, a mid-stream Ollama crash leaving a dangling worker, or a disk-full write silently corrupting audit state would first be discovered in production, not CI

### 82. 48h burn-in harness with a security monitor does not exist
- **status:** not-started · **effort:** L
- **what:** tools/endurance_tester.py is a real, working long-run harness (360 lines) but it only measures generation quality/latency/error-recovery over training_ground/ prompts — it has no concept of scope violations, credential reads, or frozen-core edits. Plan D2 calls for a monitor that tails the audit ledger + scope violations and fails on the FIRST out-of-scope write / credential read / frozen-core edit, plus tracks autonomy grants, event-drop rate, memory growth, and rollback_git/ disk growth. Needs a snapshot retention policy too (git gc --auto, keep last N / 7 days) — nothing in aios/runtime/snapshots.py or worktree_backend.py currently prunes old snapshot refs.
- **unblocks:** GAGOS_ULTRA_PLAN Phase D2 and the Definition-of-100% item #1 (7-day unattended survival)
- **risk if skipped:** No automated proof the always-on loop stays fail-closed over a long unattended run; disk fills silently from unpruned snapshot refs; a credential-read or frozen-core violation during a long run is only caught by luck of a human noticing the audit log

### 83. Frozen-core CI protected-path gate (plan 0.3) does not exist
- **status:** not-started · **effort:** S
- **what:** Grep of .github/workflows/*.yml confirms no job checks whether a PR's diff touches a frozen path. Add a CI job to ci.yml that fails any PR whose diff touches aios/security/**, the audit genesis hash, or (once relocated per 0.3) aios/security/limits.py and aios/security/http_guard.py — an automated backstop independent of self_analysis_agent.py's classify_target()/frozen_subdirs runtime check, which today only covers aios/security/ and is enforced in-process, not at the CI-merge boundary.
- **unblocks:** GAGOS_ULTRA_PLAN 0.3 and Definition-of-100% item #3 (proven by a red test)
- **risk if skipped:** A self-authored autonomous PR (or a human PR) that edits security-critical constants merges cleanly as long as tests pass — the only enforcement is a python-level check inside self_analysis_agent's own proposal path, not a merge-time backstop

### 84. Container-executor tests are mocked; no real Docker build/run ever exercised in CI
- **status:** not-started · **effort:** M
- **what:** tests/test_runtime_worker_container.py monkeypatches aios.core.executor._bounded_run and asserts the constructed docker argv (['docker','run','--rm',...]) — it never actually invokes Docker. Neither Dockerfile nor Dockerfile.executor is ever `docker build`ed by any CI job (grep of .github/workflows/*.yml for 'docker build'/'Dockerfile' returns nothing except a comment); tests/test_deployment_hardening.py only text-parses the Dockerfile/docker-compose.yml. The backend CI job also only runs on windows-latest, so the Linux-based production/executor images are never actually executed anywhere in CI.
- **unblocks:** Real confidence that AIOS_APPROVED_EXECUTION_BACKEND=container actually isolates a worker, and that a Dockerfile edit doesn't silently break the image; the container-executor integration coverage called out explicitly in the task brief
- **risk if skipped:** A broken COPY path, missing system package, or entrypoint regression in either Dockerfile ships to master undetected until someone runs docker compose up for real; the container isolation boundary that GREEN/YELLOW verification depends on is asserted only against a mock

### 85. e2e demo scripts never run automatically — wrong filename pattern for pytest collection
- **status:** not-started · **effort:** S
- **what:** tests/e2e/e2e_yellow_verify.py and tests/e2e/e2e_cloud_burst.py are real, working end-to-end scripts (real LLM edit -> YELLOW approval -> verify PASS; council/cloud-burst flow) but neither matches pytest's default test_*.py / *_test.py collection pattern, so `pytest tests/` silently skips both — confirmed by pytest.ini's testpaths=tests with no override, and neither file appears in any collected-test count. They are run-by-hand only: no CI wiring, no marker to opt in.
- **unblocks:** The task brief's explicit ask for end-to-end /api/generate + council mission automated coverage
- **risk if skipped:** Two real end-to-end scenarios that exercise the full YELLOW-approval and cloud-burst paths exist but silently stop running the moment someone forgets to invoke them by hand; a regression in either flow ships undetected since CI reports green without ever touching them

### 86. No static type-checking gate (mypy) anywhere in the repo
- **status:** not-started · **effort:** M
- **what:** Confirmed via grep across pyproject.toml, requirements*.txt, and .github/workflows/*.yml: mypy is not installed, not configured (no [tool.mypy] section), and not run. Add mypy (strict or at minimum non-strict with a ratchet) as a CI job, starting with the security-critical modules (aios/security/*, aios/core/executor.py, aios/core/approvals.py) given their frozen-core status.
- **unblocks:** Catching type-level bugs (None-handling, Optional misuse, signature drift across the executor/security boundary) before they reach runtime; a natural companion to the frozen-core hardening in 0.3
- **risk if skipped:** Type errors in the security spine (gateway.py, scope_lock.py, executor.py) are caught only by whatever a test happens to exercise; a 2,550-test suite still has blind spots a type checker would catch for free

### 87. No security static-analysis gate (bandit) anywhere in the repo
- **status:** not-started · **effort:** S
- **what:** Confirmed via grep: bandit is not installed, not configured, not run in any workflow. pip-audit (dependency CVEs) and CodeQL (semantic security queries) both run today, but neither catches bandit's class of findings (hardcoded secrets/keys, subprocess with shell=True, weak crypto, insecure temp file use) at the pattern level bandit specializes in.
- **unblocks:** A cheap, fast, complementary security gate for a codebase whose whole thesis is a fail-closed security spine
- **risk if skipped:** A pattern-level security regression (e.g. a new subprocess call with shell=True, a hardcoded credential in a new file) ships without any automated flag — CodeQL is heavier/slower and pip-audit only covers third-party CVEs, not first-party code patterns

### 88. No scheduled/nightly CI workflow exists — every automation tool is manual-only
- **status:** not-started · **effort:** M
- **what:** ci.yml has no `schedule:` trigger (only push/pull_request); codeql.yml has a weekly cron but is unrelated to test/prover automation. None of tools/learning_loop_prover.py, tools/endurance_tester.py, tools/golden_mission_runner.py, tools/daily_use_probe.py, or tools/preflight.py is invoked from any workflow (grep confirms zero 'tools/' references in .github/workflows/*.yml). The README's '19/19 learning-loop prover, stable across repeated runs' claim is evidenced only by manual local runs (.aios/audit/learning-loop-runs.jsonl), never a CI artifact.
- **unblocks:** Task brief's explicit ask (the learning-loop prover in nightly CI); turns 'stable across repeated runs' from an operator-asserted claim into a continuously-reverified one
- **risk if skipped:** A regression in the learning loop, the golden mission, or endurance characteristics is only caught the next time a human happens to run the tool by hand — for a system whose core pitch is autonomous self-improvement, its own proof-of-learning is not itself continuously verified

### 89. Backend coverage gate is one aggregate number with no per-module floor
- **status:** not-started · **effort:** M
- **what:** pytest.ini/ci.yml enforce a single --cov-fail-under=85 across all of aios/ — there is no per-directory or per-critical-module floor analogous to what the frontend already has (vite.config.js's src/superbrain/lib and src/workbench thresholds). A well-tested large module (e.g. aios/api/main.py or aios/memory/*) can mathematically hide a near-untested security-relevant file under the aggregate, and nothing in CI would flag it specifically.
- **unblocks:** Precise coverage accountability for aios/security/*, aios/core/executor.py, aios/core/approvals.py — the frozen-core surface — independent of how well-tested the rest of the tree is
- **risk if skipped:** The 85% aggregate gate can pass while a specific high-risk module (e.g. a newly-added security check) ships with near-zero direct test coverage, undetected until the aggregate eventually drifts or an incident occurs

### 90. Frontend coverage floor covers 2 of many src/ subdirectories; rest is measured but unenforced
- **status:** partial · **effort:** M
- **what:** frontend/vite.config.js's coverage.thresholds only claims src/superbrain/lib/** (74/61/73/73) and src/workbench/** (69/57/69/66) — explicitly documented in-code as a deliberate scope decision ('canvas bodies are per-frame WebGL choreography ... measured, never floor-claimed until a conformance harness exists'), not a bug. But it means most of src/ (routes, hooks, non-canvas components) has zero CI-enforced regression floor even though it's measured and reported every run.
- **unblocks:** Catching a coverage regression in any frontend code outside superbrain/lib and workbench before merge, not just after-the-fact via the reported (unenforced) number
- **risk if skipped:** A coverage regression in routing, hooks, or any non-canvas component is visible in CI output as a number but does not fail the build — silent coverage erosion outside the two claimed directories

### 91. No flaky-test hygiene mechanism (retry, quarantine marker, or tracking log)
- **status:** not-started · **effort:** S
- **what:** No pytest-rerunfailures or equivalent retry plugin in requirements.txt/pyproject.toml; no @pytest.mark.flaky or quarantine marker registered in pytest.ini's strict marker list; no log of historically-flaky tests. Given the suite touches SQLite concurrency (test_db_concurrency.py), a real cortex bus, and timing-sensitive worker-pool/approval logic, some flakiness is structurally likely as the suite grows, and there's currently no mechanism to detect, isolate, or track it.
- **unblocks:** Ability to distinguish a real regression from suite flakiness without a human manually re-running CI and guessing
- **risk if skipped:** As the suite scales past 2,550 tests, intermittent failures (timing, filesystem, SQLite lock contention) either get silently ignored via manual re-runs (eroding trust in red==broken) or start blocking merges with no diagnostic trail

### 92. README test-count/prover badge is internally contradictory (stale headline)
- **status:** not-started · **effort:** S
- **what:** README.md line 9's headline badge reads 'runtime prover 16/19' while line 164 (P2 section) correctly states 'runtime prover 19/19' with supporting detail (stable across repeated runs, both arcs shipped 2026-07-07). The top-line badge was never updated when the prover went green. This is exactly the 'stale README badge/test-count' item named in the known thesis-audit context, and it's still live in the current file.
- **unblocks:** README honesty pass (plan Phase E1); a reader who stops at the badge gets a materially wrong number that the body of the same document contradicts
- **risk if skipped:** Continues to misrepresent the system's own verified state in the single most-read line of the repo, undermining the 'honest 100%' framing the whole plan is built on

### 93. learning-loop prover, golden-mission runner, endurance tester, daily-use probe, and preflight are all CLI-only with no automated invocation
- **status:** partial · **effort:** M
- **what:** tools/learning_loop_prover.py, tools/golden_mission_runner.py, tools/endurance_tester.py, tools/daily_use_probe.py, tools/preflight.py collectively total >1,000 lines of working operational-verification tooling, none of it wired into CI, a pre-merge hook, or a scheduled job (confirmed: zero references to any tools/*.py in .github/workflows/*.yml). Each represents real, already-built verification capability that currently only produces evidence when a human remembers to run it.
- **unblocks:** Converts five already-working verification tools from operator-run evidence into continuously-produced, always-current evidence — directly supports the nightly-CI item above and the burn-in item
- **risk if skipped:** The gap between what the tools can prove and what CI actually re-proves on every change stays wide; claims like '19/19 stable across repeated runs' remain true only as of the last time a human happened to run it


## deployment-ops-resilience

> Docker packaging is in decent shape (non-root user, mem/cpu limits, restart policies, healthcheck, full observability stack with Prometheus/Grafana/Alertmanager, dependency-audited CI with 85% coverage gate, weekly dependabot). But everything about keeping the system *running unattended on a single 16GB laptop* is either missing or a stub: /health exists but only as a bare liveness ping with no dependency checks; there is no launcher, watchdog, RAM policy, log rotation, kill switch, or backup/restore; snapshot/worktree retention exists in one subsystem but is neither scheduled nor complete; the observability stack has zero visibility into the one resource dimension (RAM/CPU/disk) that matters most on this hardware; and there is no operational runbook (OPERATIONS.md doesn't exist) or one-command bring-up script. This matches the Ultra Plan's own Phase A assessment but corrects one stale claim: /health is not "nonexistent," it was extracted to aios/api/routes/system.py on 2026-07-06 and is a real but minimal stub.

### 94. Upgrade /health from bare liveness stub to a real readiness probe
- **status:** partial · **effort:** S
- **what:** aios/api/routes/system.py:83-86 currently returns only {"status":"ok","version":...} with zero dependency checks. It does not verify Ollama reachability, DB file writability (aios_memory.db/aios_approvals.db/aios_audit.db/aios_sessions.db), disk free space under AIOS_DATA_DIR, or FAISS index load state. docker-compose.yml's healthcheck (line 32-37) already curls this endpoint every 10s to decide container restarts, so a richer readiness payload (e.g. {status, ollama_ok, disk_free_gb, db_ok}) immediately improves restart/alerting behavior for free. Note: the Ultra Plan (.aios/state/GAGOS_ULTRA_PLAN.md A1) says '/health... nothing like it exists today' — that's now stale (route landed 2026-07-06); the real gap is depth, not existence.
- **risk if skipped:** Container/watchdog 'restarts' will keep reporting healthy while Ollama is unreachable or disk is full, so the process stays up serving broken turns instead of surfacing/recovering — false-positive health signal.

### 95. Always-on launcher + Scheduled Task for reboot survival
- **status:** not-started · **effort:** M
- **what:** No scripts/launcher.ps1 and no schtasks registration exist anywhere in the repo (only aios-resume.ps1/.sh, which is for resuming a Claude Code session, not launching the API). Today the backend is started manually per START_HERE.md ('.venv\Scripts\python -m uvicorn aios.api.main:app --port 8000'). A laptop reboot, sleep/wake cycle, or Windows Update restart silently kills the process with nothing to bring it back.
- **unblocks:** Ultra Plan Phase A/B always-on host and sovereign work-loop
- **risk if skipped:** Any unattended-operation goal (Phase B of the Ultra Plan, or simply 'leave it running overnight') is impossible — the system is only ever up while someone remembers to start it in a terminal.

### 96. Watchdog: crash-detection auto-relaunch + memory-ceiling restart
- **status:** not-started · **effort:** M
- **what:** No polling/supervisor process exists. psutil is not a dependency anywhere in requirements.txt or requirements-optional.txt, and grep confirms zero psutil usage in aios/. There is no mechanism that polls /health, detects a hung/crashed process, or restarts the API when its RSS crosses a budget.
- **risk if skipped:** A memory leak or an unhandled exception in a background task silently takes the whole system down for hours with no recovery and no alert, on a machine with only 16GB to share with Ollama and (optionally) Docker.

### 97. RAM budget table + backend-selection policy enforcement for 16GB
- **status:** not-started · **effort:** S
- **what:** No documented budget (Ollama resident model + Docker Desktop VM + API RSS + OS) and no code enforces pinning AIOS_APPROVED_EXECUTION_BACKEND=host unless Docker is confirmed running and budgeted, as the Ultra Plan's A3 calls for. docker-compose.yml does cap the API *container* itself (mem_limit: 4g, cpus: 2.0) but that only governs the containerized path; nothing arbitrates the shared host RAM between Ollama's loaded model and Docker Desktop's VM when both run simultaneously.
- **risk if skipped:** Ollama + Docker Desktop + the API can jointly exceed 16GB with no guardrail, causing OS-level thrashing/OOM-killer behavior that is much harder to diagnose than an explicit budget check would be.

### 98. Kill switch (operator panic button independent of manual process kill)
- **status:** not-started · **effort:** S
- **what:** No data/KILL_SWITCH sentinel check, no POST /api/v1/daemon/kill endpoint, and no scripts/kill.ps1 exist. Confirmed via grep across aios/ and config.py — no KILL_SWITCH string anywhere in the codebase.
- **risk if skipped:** There is no fast, auditable, remotely-triggerable way to stop a runaway swarm/worker or a misbehaving daemon short of finding and killing the OS process by hand — the opposite of the fail-closed posture the rest of the security spine works hard to guarantee.

### 99. Log rotation — both bare-metal and Docker paths grow unbounded
- **status:** not-started · **effort:** S
- **what:** aios/logging_config.py wires only a bare logging.StreamHandler(sys.stderr) with no RotatingFileHandler/TimedRotatingFileHandler; there is no file-based log sink at all today (stderr just streams to wherever the launching terminal/redirect sends it). Separately, none of the 4 services in docker-compose.yml (aios, prometheus, grafana, alertmanager) set a `logging:` block with max-size/max-file, so the default json-file Docker log driver also grows without bound.
- **risk if skipped:** On a 16GB laptop with finite disk, an always-on process (once A2/A3 above exist) will eventually fill the disk with its own logs, which then also breaks writes to the SQLite DBs living on the same volume.

### 100. Automated backup/restore of data/
- **status:** not-started · **effort:** M
- **what:** data/backups/ and data/backup-pre-trail-mechanics/ contain only stale, one-off manual copies from June 9 and June 11 respectively (confirmed by file timestamps). No script performs a scheduled or pre-risky-operation backup of the live state: aios_memory.db, aios_approvals.db, aios_audit.db, aios_sessions.db, cortex_bus.db, policy.db, pheromones.db, live_surface.db, rollback_registry.db, vector_index.faiss. No restore script exists, and no restore has ever been drilled/verified.
- **risk if skipped:** A corrupted SQLite file, a bad disk sector, or an accidental delete permanently destroys the audit trail, approval history, autonomy ledger, and episodic memory with zero recovery path — this is the system's entire accumulated 'experience,' which AGENTS.md itself calls irreplaceable.

### 101. Scheduled snapshot/rollback-git retention + gc (not just the code that could do it)
- **status:** partial · **effort:** M
- **what:** aios/runtime/rollback_registry.py's RollbackRegistry.prune(retention_days=30) is real and works, but it is reachable ONLY via a manual, rate-limited endpoint (POST /api/v1/runtime/rollbacks/prune in aios/api/routes/sovereignty.py, rate-limited to 5 in main.py's RATE_LIMITS table) — nothing calls it on a timer, so it only runs if an operator remembers to hit it. Separately and more seriously, aios/runtime/snapshots.py's SnapshotManager (used by the Council runtime) writes its own rollback_git/<hash>/ git object databases and snapshots/*.json metadata under AIOS_COUNCIL_RUNTIME_DIR with zero retention or gc logic anywhere — a fully separate unbounded-growth path the registry's prune() never touches. aios/runtime/worktree_backend.py has destroy_lane() for explicit cleanup but nothing force-destroys orphaned lanes left behind by a crashed process (the Ultra Plan's own B3 explicitly calls for 'startup force-destroys stale lanes' — not built).
- **risk if skipped:** Every Council mission and every snapshot-guarded write accumulates git objects and worktree directories forever; on a laptop this silently eats disk over weeks until something (logging, DB writes, the OS itself) fails with no warning.

### 102. Graceful degradation on LLM-provider failure: no retry, no circuit breaker, no fallback-to-local
- **status:** partial · **effort:** M
- **what:** aios/core/llm.py catches URLError/TimeoutError/OSError at 3 call sites and converts them cleanly to LLMError, but there is no retry-with-backoff for a transient Ollama hiccup, and aios/core/router.py's route()/pick_from() only ever *selects* a candidate at request-build time — there is no runtime fallback that retries on local Ollama when the chosen cloud provider (Bedrock/Gemini) fails mid-call (network drop, rate limit, expired token). A single transient failure fails the whole turn.
- **risk if skipped:** Any transient network blip against Bedrock/Gemini, or a momentary Ollama model-load stall, surfaces as a hard user-facing failure instead of a one-retry recovery or a silent drop to the local model that the router's own local-first thesis would otherwise prefer.

### 103. No disk-space / low-disk detection anywhere
- **status:** not-started · **effort:** S
- **what:** Confirmed via repo-wide grep: zero occurrences of shutil.disk_usage, ENOSPC, or any disk-space check in aios/ or tools/. If data/ (SQLite WAL files, the FAISS index, council_workspace worktrees, rollback_git objects) fills the disk, writes fail as raw unhandled OSErrors with no graceful message, no telemetry event, and no /health signal.
- **risk if skipped:** The failure mode for 'disk full' today is whatever exception SQLite/git happens to throw, surfaced to the operator with no context — hard to diagnose quickly on a system meant to run unattended.

### 104. OPERATIONS.md does not exist; SECURITY.md is a disclosure template, not a runbook
- **status:** not-started · **effort:** S
- **what:** SECURITY.md (root) exists but is a standard GitHub vulnerability-disclosure policy (supported versions, how to report, security architecture summary) — it documents *what the security spine does*, not *how an operator runs the system day to day*. There is no written procedure anywhere for: stopping the process, restoring data/ from backup, rotating AIOS_API_TOKEN / AWS_BEARER_TOKEN_BEDROCK / the Grafana admin password, revoking a single approval grant or an earned-autonomy class, or reading/verifying the audit chain outside of hitting GET /api/v1/audit/verify directly.
- **risk if skipped:** Every one of these is exactly the kind of task done rarely and under pressure (after an incident, or when rotating a leaked token) — without a runbook, the operator has to reverse-engineer the right procedure from source at the worst possible time.

### 105. Observability stack has zero host-resource metrics or alerts (RAM/CPU/disk)
- **status:** not-started · **effort:** S
- **what:** aios/core/metrics.py builds a private CollectorRegistry() with only app-level counters/gauges (tasks, approvals, autonomy, audit-chain validity, HTTP request counts/durations/errors) — no ProcessCollector/PlatformCollector is registered (confirmed via grep), so there is no process RSS, CPU%, or open-FD metric exposed at all. observability/alert_rules.yml correspondingly has only 3 alerts (AiOSAuditChainBroken, AiOSHighInterventionRate, AiOSHighErrorRate) — none for memory, CPU, or disk. The full Prometheus+Grafana+Alertmanager stack already runs (docker-compose.yml) but is structurally blind to the exact resource dimension (16GB ceiling) that matters most for this deployment.
- **risk if skipped:** The one metric a single-laptop operator most needs paged on — 'the process is about to get OOM-killed' — cannot fire, even though the entire alerting pipeline to deliver that page already exists and is wired up for everything else.

### 106. No one-command clean-clone bootstrap / 15-minute bring-up
- **status:** not-started · **effort:** S
- **what:** No Makefile, setup.ps1, or setup.sh exists at repo root. README.md's 'Getting started' section (line 234) just points to START_HERE.md, which itself is a multi-step manual walkthrough across two files (create venv, pip install -r requirements.txt, cd frontend && npm install, copy .env.example to .env, pull an Ollama model, start backend, start frontend) with no single command and no measured/verified bring-up time claim anywhere in the docs.
- **risk if skipped:** Every fresh clone (a new machine, a disaster-recovery rebuild, or a new collaborator) redoes the same manual sequence by hand with no automated verification that it actually completes cleanly — the 15-minute bring-up target is aspirational, not tested.

### 107. CI has no CD/packaging/release step
- **status:** not-started · **effort:** M
- **what:** ci.yml (backend pytest+coverage+pip-audit, frontend typecheck+test+build+npm audit) is solid but stops at 'green tests' — there is no job that builds/tags/publishes a versioned Docker image, or produces any other reproducible release artifact. For a single-operator local-first tool this may be acceptable scope, but it means 'the container that runs in production' is never actually built and smoke-tested by CI beyond `docker compose up --build` being implied, not exercised.
- **risk if skipped:** A Dockerfile change (e.g. a base-image bump) can pass all CI checks yet still fail to build or boot in practice, since nothing in CI actually builds the production image.


## honesty-docs-thesis

> Verified against live code (not re-litigating the known thesis-audit list from memory). Headline: the flagship "local-only egress" claim is still factually false in BOTH README.md and AGENTS.md — the latter is the doc every coding agent is told is authoritative, so this is actively misinforming agents, not just readers. Also found and reproduced a live privacy-filter leak (an AWS-secret-shaped token with "/" passes `_redact_high_entropy` unredacted, count=0 — verified by direct execution), a frontend component (RegionPins.tsx) that still displays fabricated non-zero metrics offline despite README's "goes dormant" claim (a sibling component, SuperbrainHUD.tsx, was already fixed — confirming the ultra plan's suspicion that not everything named needed re-verifying), an in-code docstring (autonomy.py) that still asserts the opposite of config.py's actual default, and an internal README self-contradiction (16/19 vs 19/19 prover score in the same file). None of docs/API.md, docs/ARCHITECTURE.md, docs/OPERATIONS.md, docs/SECURITY.md exist, and there is no repeatable mechanism (CI or script) that would have caught any of the above automatically — every one of these findings required a manual grep-and-read session tonight.

### 108. Fix the false "local-only by default" router-egress claim in README.md AND AGENTS.md
- **status:** not-started · **effort:** S
- **what:** README.md:202 states "a cloud route requires per-task-class operator opt-in (AIOS_ROUTER_CLOUD_TASKS, empty by default = local-only)". AGENTS.md:149 repeats the identical claim verbatim ("empty by default = local-only"). Both are currently false: aios/config.py:311 sets `_ROUTER_CLOUD_TASKS_DEFAULT = ("reasoning", "coding")` — cloud-eligible by default for two whole task classes. AGENTS.md is the doc CLAUDE.md tells every agent is authoritative, so this isn't just a reader-facing inaccuracy, it's actively misinforming every coding agent working in this repo about the system's actual privacy posture. Fix: either change the prose to state the true default, or (preferred, tracked separately under Phase 0.5 in GAGOS_ULTRA_PLAN.md) flip the code default to empty and then the docs become true without editing.
- **unblocks:** any credible security/privacy claim in README, AGENTS.md, or a future SECURITY.md; removes the single most reader-visible thesis contradiction
- **risk if skipped:** an operator or reviewer reads either doc, believes egress is local-only by default, and is surprised when a 'reasoning' or 'coding' task silently routes to Bedrock/Gemini — the exact failure mode a sovereignty thesis exists to prevent

### 109. Fix README.md's internal self-contradiction on the learning-loop prover score
- **status:** not-started · **effort:** S
- **what:** README.md:9 (the top-of-file status badge) says "runtime prover 16/19" and is datestamped "as of 2026-07-06"; README.md:164 in the same file says "runtime prover 19/19" and .aios/state/AUDIT.md §8 confirms the flip to a stable 19/19 happened 2026-07-07. The badge line was not updated when the body prose was. Fix: update line 9 to 19/19 and the datestamp to 2026-07-07 (or later), and audit the rest of the badge line's other figures (test counts, coverage %) against the current AUDIT.md ground-truth section at the same time so this doesn't recur piecemeal.
- **unblocks:** README passing a fresh thesis-vs-code re-audit
- **risk if skipped:** a reader who only reads the badge (the most-read line in the file) gets a strictly worse number than reality, undermining trust in every other claim in the same document once the inconsistency is noticed

### 110. Soften/fix README's privacy-filter "secrets redacted" claim — reproduced live leak
- **status:** not-started · **effort:** M
- **what:** README.md:202 claims cloud-bound content "passes the privacy filter with paths and secrets redacted." Reproduced directly: `aios/core/privacy_filter.py._redact_high_entropy("aws_secret_access_key = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY")` returns the string UNCHANGED, count=0 — because the 2026-07-07 filename-exemption fix (`_in_filename_context`, privacy_filter.py:119-137, comment at 122-131) exempts ANY high-entropy token matching the path-shape regex `_PATH_SHAPED` from redaction, and this AWS-secret-shaped token happens to be path-shaped (letters/digits/hyphens joined by `/`). tests/test_privacy_filter.py has zero AKIA/wJalrXUtn-style regression tests, confirming this is untested, not just undocumented. Also PEM matching (privacy_filter.py:48-51) still only matches the `-----BEGIN-----` header line, not inline base64 body lines, per GAGOS_ULTRA_PLAN.md §0.7. Fix: either land the two regression tests + the ordering fix the ultra plan specifies (check `_looks_like_secret` before the path exemption), or — if honesty-docs is scoped to prose only — soften README's unconditional "secrets redacted" claim to name this known gap until the code fix lands, and add a KNOWN GAPS entry to AUDIT.md so the gap is disclosed rather than silently present.
- **unblocks:** a truthful SECURITY.md/OPERATIONS.md; closes GAGOS_ULTRA_PLAN.md Definition-of-100% item #4
- **risk if skipped:** operator data (a real AWS secret key, or any other path-shaped high-entropy secret) leaves the machine to a cloud provider while README asserts it can't — this is the single highest-severity item in this whole inventory because it is currently live, reproducible, and silently regressed by a fix that was framed as an improvement

### 111. Fix README's "frontend goes dormant when there is no data" claim — false for RegionPins.tsx
- **status:** not-started · **effort:** M
- **what:** README.md:39 claims the 3D frontend "goes dormant when there is no data." Verified: frontend/src/superbrain/lib/metricsStore.ts hardcodes non-zero `METRIC_BASES` (research:93, memory:89, tools:78, signals:83) that idle-drift via `Math.random()` regardless of backend connectivity. frontend/src/superbrain/components/ui/SuperbrainHUD.tsx (source-block, ~line 436-460) was already hardened with a `hasRealValue`/`is-dormant` gate that renders '--' offline instead of the store's fabricated drift — but frontend/src/superbrain/components/canvas/RegionPins.tsx (the 3D brain-region callouts, imports `useMetric`/`useMetricHistory` at line 27, reads at lines 82-84) has NO such gate — it renders the store's fabricated percentages unconditionally, online or offline. RegionPins.test.tsx has zero offline/dormancy test coverage. This resolves GAGOS_ULTRA_PLAN.md Phase C3's open question ("RegionPins" does exist by that name and does still fabricate) with a definitive current-code answer. Fix: port the same hasRealValue/dormant gate from SuperbrainHUD.tsx into RegionPins.tsx, add a regression test, then the README claim becomes true.
- **unblocks:** GAGOS_ULTRA_PLAN.md Phase C3 (frontend honesty fixes); the README's "Honest" framing for the frontend organ
- **risk if skipped:** an operator watching the 3D brain with the backend down sees confident-looking 78-93% numbers on the region pins that have never been true, and README explicitly promises this can't happen

### 112. Fix aios/core/autonomy.py's module docstring — still says the opposite of the real default
- **status:** not-started · **effort:** S
- **what:** aios/core/autonomy.py:9 (module docstring) states "It is OFF by default (`AIOS_EARNED_AUTONOMY`); supervision stays the norm." But aios/config.py:182 sets `EARNED_AUTONOMY_ENABLED = _env_bool("AIOS_EARNED_AUTONOMY", True)` — default ON, and README.md / AGENTS.md both correctly describe it as default-ON. This is an in-code doc-rot instance of the exact contradiction GAGOS_ULTRA_PLAN.md Phase C2 names ("resolve the autonomy.py docstring-vs-True default contradiction") — confirmed still unfixed as of this session despite being flagged in memory on 2026-07-07 (obs#8863/#8983). Fix: one-line docstring edit to say ON by default, grants nothing until earned.
- **unblocks:** closes GAGOS_ULTRA_PLAN.md Phase C2's named docstring item; removes a doc-vs-doc split-brain (README says ON, source code comment says OFF) that a future agent reading only the module will get wrong
- **risk if skipped:** any agent or contributor who reads the autonomy.py docstring instead of config.py will believe earned autonomy is opt-in and be surprised when YELLOW actions start auto-executing after 5 verified successes

### 113. Disclose the Planner's "evidence-derived confidence" claim only holds for known task shapes
- **status:** not-started · **effort:** S
- **what:** README.md's Queen Council table (line 78) and AUDIT.md both describe the planner as producing "evidence-derived confidence," contrasted against "LLM-self-reported." Verified in aios/core/planner.py: the LLM is asked to produce a self-reported confidence per step (PLAN_SYSTEM_PROMPT, lines 32-35: "estimate your confidence... that you can complete it correctly"), which is then adjusted "using only verified external evidence" (planner.py:202) when matching skills/mistakes/development-history exist. For a genuinely novel goal with no prior verified evidence to adjust against, the confidence IS the raw LLM self-report — there is no external signal to blend in. This is a real, inherent limitation (not a bug to fix), but it is not disclosed anywhere: the README/AUDIT phrasing reads as an unconditional guarantee. Fix: add one clause to the Planner row / AUDIT.md §2 noting the evidence-adjustment applies when prior verified evidence exists; novel goals fall back to self-report like any other planner.
- **unblocks:** an honest confidence-gate story for the two-hard-problems design docs referenced in AUDIT.md §4.4
- **risk if skipped:** the thesis's core differentiator ("the model is never trusted... confidence is evidence-derived, not self-reported") silently doesn't hold on exactly the class of tasks — novel ones — where a false-confidence failure matters most

### 114. Disclose INJECTION_VECTOR_SHIELD is OFF by default (dormant)
- **status:** not-started · **effort:** S
- **what:** README.md:30 states "Prompt-injection shield via vector blocklist" as a built/verified capability with no caveat. aios/config.py:226 sets `INJECTION_VECTOR_SHIELD = _env_bool("AIOS_INJECTION_VECTOR_SHIELD", False)` — dormant unless an operator explicitly opts in. GAGOS_ULTRA_PLAN.md Phase C2 names this exact flag as needing an explicit sovereignty decision ("→ on") that has not yet been made. Fix: either flip the default (a security-area decision, tracked in C2) or, until that lands, add a parenthetical to the README bullet disclosing the current default-off state the same way the router-egress and earned-autonomy bullets already do for their flags.
- **unblocks:** GAGOS_ULTRA_PLAN.md Phase C2's flag-decision checklist
- **risk if skipped:** a reader assumes injection defense is live out of the box; it is not, and nothing in the current docs says so

### 115. Disclose SWARM_CLOUD_BURST default-True and its interaction with the future autonomous daemon
- **status:** not-started · **effort:** S
- **what:** aios/config.py:204 sets `SWARM_CLOUD_BURST_ENABLED = _env_bool("AIOS_SWARM_CLOUD_BURST", True)`. Neither README.md nor AGENTS.md mentions this flag at all. GAGOS_ULTRA_PLAN.md §0.5/C2 flags it as needing to be forced local for the (not-yet-built) daemon specifically, since today nothing distinguishes an autonomous swarm burst from an interactive one at the origin level. Fix: add the flag to AGENTS.md's router/egress paragraph alongside AIOS_ROUTER_CLOUD_TASKS (same place item #1 above is being fixed) so the full egress picture is in one place and not scattered/omitted.
- **unblocks:** a complete, single-place egress disclosure in AGENTS.md
- **risk if skipped:** swarm cloud-burst is a second, undocumented egress path alongside the router — an operator who correctly locks down AIOS_ROUTER_CLOUD_TASKS can still leak via swarm bursts and no doc tells them this exists

### 116. Clarify that boot attestation is detection-only and non-blocking, and is a different mechanism from the Ed25519 audit-chain signing
- **status:** not-started · **effort:** S
- **what:** README.md:31 says "Tamper-evident audit ledger... with boot attestation." Verified: aios/boot_attestation.py computes a plain SHA-256 Merkle hash over aios/security/*.py (no Ed25519 signature anywhere in this module — that's a separate, real mechanism in aios/security/audit_logger.py). aios/api/main.py:239-246 calls `attest_boot()` inside a try/except explicitly commented "never block startup"; a TAMPERED verdict (`integrity="TAMPERED"`) is only logged at info/warning level and the app boots regardless — there is no enforcement path. Fix: split the README sentence into two accurate claims (the audit ledger IS Ed25519-signed and hash-chained; boot attestation is a separate SHA-256 spine-hash check that currently only logs, does not block), and note the non-enforcement as a named gap rather than implying attestation gates startup.
- **unblocks:** an accurate SECURITY.md section on tamper detection vs. tamper prevention
- **risk if skipped:** a reader believes a tampered security spine would prevent the system from starting; today it boots anyway with a log line, which is a materially different security guarantee than what the sentence implies

### 117. Disclose the frozen-core coverage gap in README/AGENTS.md — only aios/security/* is actually frozen
- **status:** not-started · **effort:** S
- **what:** aios/agents/self_analysis_agent.py:132/189 defaults `frozen_subdirs=("security",)`. Neither README.md nor AGENTS.md discloses that the self-analysis module's self-edit protection covers only aios/security/* and NOT aios/core/executor.py, aios/config.py (the guardrail constants themselves), or aios/api/main.py (CORS/auth) — the exact gap GAGOS_ULTRA_PLAN.md §0.3 documents as needing a fix (relocate guardrail constants into aios/security/limits.py so they inherit the existing frozen-prefix check). Until 0.3 lands, README's "self-analysis proposes diffs for human review instead of widening scope" framing (AUDIT.md §6.3) should name which 3 of 4 named surfaces are NOT yet covered.
- **unblocks:** an accurate frozen-core claim ahead of GAGOS_ULTRA_PLAN.md Phase 0.3 landing
- **risk if skipped:** a reader assumes the self-analysis module's proposed diffs can never touch guardrail-adjacent code; today a self-authored proposal against aios/core/executor.py or aios/config.py would NOT be caught by the frozen-subdir check

### 118. No frozen-path CI gate exists — Definition-of-100% item #3 is unmet, and nothing discloses this
- **status:** not-started · **effort:** S
- **what:** GAGOS_ULTRA_PLAN.md Phase 0.3 and "Definition of 100%" item #3 both require a CI job in .github/workflows/ci.yml that fails any PR whose diff touches a frozen path. Grepped .github/workflows/ci.yml for "frozen"/"SCOPE_ROOTS"/anything resembling this gate: zero matches. This is real work (belongs jointly to CI/security), but the honesty-docs piece is: nothing in README/AUDIT currently states this gate doesn't exist yet, even though the ultra plan itself (written 2026-07-07, in this repo) already names it as a hard precondition for any future autonomy work. Fix (docs piece): add an explicit AUDIT.md "Open gap" line so a reader of the autonomy roadmap knows this precondition is unmet, not silently assumed done.
- **unblocks:** an honest AUDIT.md gaps section ahead of any Phase B autonomy work starting
- **risk if skipped:** a future session (or operator) reads GAGOS_ULTRA_PLAN.md's guardrail spine as already-enforced and greenlights Phase B work before the CI backstop actually exists

### 119. Fix stale frontend test count in .aios/state/PLAN.md (326 vs. actual 468)
- **status:** not-started · **effort:** S
- **what:** PLAN.md:26 and PLAN.md:178 both still say "326 passed"/"326 vitest tests" for the frontend suite. README.md:9 and AUDIT.md:0 both currently report 468. PLAN.md's own item H1 (line 154) literally proposes "pin ONE test baseline... reconcile..." as a recommended fix, but that fix was never applied back to PLAN.md's own numbers in the same document — the doc that recommends fixing stale counts is itself carrying a stale count. Fix: update both occurrences to the current live count (or better, replace the hardcoded number with "see AUDIT.md §0" per the doc-currency convention already used elsewhere).
- **unblocks:** PLAN.md becoming a source of truth instead of a second, disagreeing test-count claim
- **risk if skipped:** two Tier-1 docs (README.md and PLAN.md, both linked from the "Getting started" section) disagree on the frontend test count by 142 tests, and a reader has no way to know which is current without checking git blame

### 120. Add a superseded banner to SYSTEM_AUDIT_2026-06-21.md (and audit any other undated-banner root docs)
- **status:** not-started · **effort:** S
- **what:** SYSTEM_AUDIT_2026-06-21.md is dated 2026-06-21 (17 days stale as of 2026-07-08), predates the Council Runtime, Planner-stage flip, learning-loop prover, and most of the router/privacy work covered above, and carries zero "superseded" marker despite the user's own stated doc-currency convention ("refresh Tier-1 docs after a feature; never rewrite dated evidence, add a superseded banner instead"). It is not currently linked from README/START_HERE/AGENTS.md (so risk is contained to someone browsing the repo root), but it's exactly the kind of orphaned-but-discoverable doc that misleads a future audit pass into treating June findings as current. Fix: add a one-line superseded banner pointing to AUDIT.md as the current source of truth; do the same audit sweep across HONEST_STATE.md (2026-07-03, 5 days stale, makes claims about `prove_sovereignty.py` that should be spot-re-verified) and the other root .md files found (GAGOS_FINAL_ROADMAP_council.md, GAGOS_SEASON_ONE_KICKOFF.md, KICKOFF_PROMPT.md, FOUNDATION_LOCK.md, PRODUCT.md, PROVE_IT.md).
- **unblocks:** a clean root directory where every doc's currency status is self-evident
- **risk if skipped:** low-severity but compounding — every dated snapshot doc left unbannered is one more false trail for a future thesis-vs-code audit session to have to manually re-discover is stale, exactly as this session had to for AUDIT.md/PLAN.md

### 121. Write docs/API.md generated from the live OpenAPI schema
- **status:** not-started · **effort:** M
- **what:** No docs/API.md exists anywhere in the repo (docs/ contains only a superpowers/ subdirectory of dated plans/specs). FastAPI already exposes a live OpenAPI schema at runtime (aios/api/main.py's app); this has not been captured into a versioned reference doc. Fix: script that dumps app.openapi() to docs/API.md (or .json + a thin markdown wrapper) and wire it as a doc-currency check (regenerate + diff in CI, or at minimum a documented manual regen command) so it doesn't immediately go stale the way the hand-written docs above did.
- **unblocks:** any external contributor or future agent trying to call the API without reading main.py + 9 routers by hand
- **risk if skipped:** the only way to know the current API surface is to read aios/api/main.py and aios/api/routes/*.py directly — fine for the operator today, a real onboarding barrier the moment anyone else touches this repo

### 122. Write docs/ARCHITECTURE.md matching current reality
- **status:** not-started · **effort:** M
- **what:** No docs/ARCHITECTURE.md exists. README.md:239 points readers to '.aios/state/PLAN.md' and '.aios/state/AUDIT.md' for architecture depth, but neither is an architecture reference — PLAN.md is a blueprint-vs-reality worklist and AUDIT.md is an evidence ledger. The closest thing, .aios/state/GAGOS_ARCHITECTURE.md, is a dated state snapshot in the same directory as ~50 other dated planning docs (renovation blueprints, poster-gap audits, RTX dossiers) with no clear signal to a reader which one is the current architecture description. Fix: a docs/ARCHITECTURE.md that describes the Sovereign Colony layout (Queen Council organs, King veto, worker agents) cross-referenced to actual module paths (aios/security/gateway.py, aios/core/router.py, aios/memory/*, aios/council/*), kept separate from the dated .aios/state/ planning trail.
- **unblocks:** GAGOS_ULTRA_PLAN.md Phase E2; a stable architecture reference that survives individual feature sessions without going stale the way the dated .aios/state/*.md docs do
- **risk if skipped:** architecture knowledge stays scattered across ~50 dated planning docs with no canonical current-state document, which is exactly the condition that let the router-egress and prover-count contradictions above go unnoticed for a session or more

### 123. Write docs/OPERATIONS.md + docs/SECURITY.md for always-on autonomous mode
- **status:** not-started · **effort:** L
- **what:** GAGOS_ULTRA_PLAN.md Phase E2 calls for these two docs (kill switch, revert, revoke a class, rotate tokens, read the audit chain, restore data/). Neither exists in docs/ today (only a top-level SECURITY.md exists, and it predates the always-on/autonomy work — it documents the interactive-mode security model, not daemon operations). Real sequencing constraint: Phase A (kill switch A5, launcher A2, watchdog) is itself not built yet per the ultra plan, so an OPERATIONS.md written now would either be aspirational or would have nothing true to document for the kill/revert/rotate flows specific to the daemon. Fix: track this as blocked-on-Phase-A rather than independently startable; the SECURITY.md refresh (documenting the CURRENT interactive-mode gateway/audit/approval model against today's code) can proceed independently and sooner.
- **unblocks:** GAGOS_ULTRA_PLAN.md Definition-of-100% item #6 (kill switch + digest + one-click revert documented and working)
- **risk if skipped:** when the always-on daemon eventually ships, there is no operator runbook for the failure modes that matter most (kill, revert, revoke, rotate) — exactly the gap that turns a good security design into an unusable one under pressure

### 124. Document earned-autonomy's de facto STRONG-verification ceiling (.py-with-sibling-test only)
- **status:** not-started · **effort:** S
- **what:** README.md's Earned Autonomy paragraph (line 88) describes the mechanism generically ("a narrow action class may skip its approval pause after 5 consecutive verifier-backed successes") without disclosing that in practice, only Python file writes with a sibling pytest file can reach STRONG verification strength today. Confirmed in aios/agents/tool_agent.py:68-72: "the loop AUTONOMOUSLY runs the written file's sibling pytest... A Python file with no sibling test is reported [weaker]" (line ~1308: "[VERIFY SKIPPED] no sibling test for {filepath}"). Since earned-autonomy promotion is gated on verification strength (aios/core/verification_strength.py), any non-Python write or Python write without a matching test file structurally cannot earn autonomy today, no matter how many times it succeeds. Fix: add a one-line scope disclosure to the README paragraph so "a narrow action class" doesn't read as broader than it currently is.
- **unblocks:** an accurate expectation-setting for anyone reading the earned-autonomy story before Phase F (external projects, non-Python) is attempted
- **risk if skipped:** someone reads the earned-autonomy claim as applying to arbitrary action classes and is surprised that, e.g., a shell-command class or a non-Python file-write class never earns, no matter the streak — because it structurally can't reach STRONG evidence

### 125. Build a repeatable thesis-vs-code drift check (script or CI job)
- **status:** not-started · **effort:** L
- **what:** GAGOS_ULTRA_PLAN.md area brief and the honesty-docs task both call for "a repeatable thesis-vs-code audit in CI." None of the 13 findings above (README/AGENTS.md router-default mismatch, README internal 16/19-vs-19/19 contradiction, autonomy.py docstring drift, PLAN.md stale test count, RegionPins fabricated-data claim, boot-attestation enforcement claim) would have been caught automatically — every one required a manual grep-and-code-read session tonight. Fix: a small script (e.g. tools/thesis_audit.py) that greps known load-bearing config defaults (ROUTER_CLOUD_TASKS, EARNED_AUTONOMY_ENABLED, INJECTION_VECTOR_SHIELD, PLAN_STAGE_ENABLED, SWARM_CLOUD_BURST_ENABLED) out of aios/config.py and asserts the numbers/booleans referenced in README.md/AGENTS.md via regex match them, plus a numeric-consistency check within README.md itself (same metric mentioned twice must agree) — wired as a CI job or at minimum a documented pre-commit-doc-touch check.
- **unblocks:** every future doc-currency pass; turns a 2-hour manual audit into a CI failure the moment a default changes without the doc being updated
- **risk if skipped:** each of the concrete drifts found in this session will recur the next time a flag default changes or a milestone number moves, and will again require a full manual re-audit to catch — this is the single highest-leverage item in the list because it prevents the rest of this inventory from needing to be regenerated by hand every few weeks

### 126. Reconcile remaining thesis-audit PARTIAL claims not individually re-verified this pass
- **status:** partial · **effort:** M
- **what:** The task brief names "7 CONTRADICTED + 10 PARTIAL claims" from a prior thesis audit; this session concretely re-verified and confirmed still-open: router-egress default (CONTRADICTED), privacy-filter secret leak (CONTRADICTED, and arguably worsened by the 2026-07-07 fix), frontend fabricated data (CONTRADICTED for RegionPins specifically), earned-autonomy .py-sibling-test scope (PARTIAL), planner confidence self-report fallback (PARTIAL), boot attestation unsigned/unenforced (PARTIAL-confirmed: unsigned is true of THIS mechanism, unenforced is fully true), stale README badge/CI/test-count (CONTRADICTED, worse than described — the file contradicts itself). Not independently re-verified this session against current code: the King-LLM-veto-disconnected claim (aios/council/king_reasoning.py and aios/runtime/king_report.py now exist and are wired into aios/api/routes/council.py — this needs an explicit live-loop trace, not just an import grep, before it can be marked closed or still-open) and the sandbox-only-wraps-YELLOW-not-GREEN claim (a quick grep of aios/core/executor.py shows GREEN commands DO route through `_run_in_sandbox` at line 514, suggesting this may already be fixed, but needs the same live-trace confirmation, not just a grep). Fix: a dedicated short session tracing both through the live /api/generate path with a real request, then updating README's King framing and Security section with the confirmed current state either way.
- **unblocks:** closing out the full 7+10 claim set from the original thesis audit rather than leaving 2 of 17 as unconfirmed
- **risk if skipped:** the two unverified claims stay in an ambiguous state — not confirmed fixed, not confirmed still-broken — which is itself a form of the dishonesty this whole area exists to eliminate


## roadmap-frontier (P3 Project Passport, P4 Sovereign Web Navigator, P5 Human Taste Memory, P6 Public Product)

> All four roadmap tiers are honestly "designed, not built" (confirmed by .aios/state/AUDIT.md line 53 and zero matching config flags/modules in the codebase). What exists today is much narrower than the roadmap names suggest, and conflating the narrow pieces with the roadmap items would be dishonest: (1) aios/core/websearch.py is a bare, single-provider search-snippet fetcher built for CRAG's internal RAG fallback (Slice 3b) — it has no citations, no full-page fetch, no cross-verification, no quarantine tier, and is not the P4 Navigator. (2) aios/memory/operator_model.py + the read-only OperatorProfileCard.jsx display existing generic operator.* semantic facts but are NOT wired into the actual generation loop (tool_agent.py / main.py never call render_operator_model when building prompts) — so today's "taste memory" is decorative, not behavior-changing. (3) aios/agents/self_analysis_agent.py scans only the ai-editor repo itself for self-improvement findings — it is not a generic Project Passport harvester for arbitrary external projects. (4) onboarding_state in system.py tracks 5 first-run milestones for the single existing mode; there is no Student/Developer/Professional/Creator mode concept, no installer, and the memory schema has no user_id/tenant dimension (single-operator by design). P3 is the correct sequencing priority since P4's grounding, P5's per-project scoping, and earned-autonomy-beyond-ai-editor (per GAGOS_ULTRA_PLAN.md Phase F) all depend on it. Every item below cites the concrete file(s) involved and is real remaining work, not already-shipped functionality relabeled.

### 127. Project Passport harvester core module
- **status:** not-started · **effort:** XL
- **what:** Build aios/memory/project_passport.py: scan a project root into {purpose, stack, folder_map, install/run/build/test commands, env vars, safe_files, risky_files, known_issues, goals, suggested_improvements}. This is the crux item — everything downstream (P4 grounding for 'which project is this research for', P5 per-project taste scoping, and GAGOS_ULTRA_PLAN.md's Phase F external-project autonomy) depends on accurate project understanding existing at all. No code for this exists; aios/agents/self_analysis_agent.py is a different, narrower thing (self-scans only ai-editor's own aios/ tree for refactor findings, gated by classify_target's frozen_subdirs, not a general external-project harvester).
- **unblocks:** POST /api/v1/projects/scan endpoint, passport-driven task sourcing in any future heartbeat loop, P4's per-project research grounding, P5's per-project taste scoping, and GAGOS_ULTRA_PLAN.md Phase F (external-project write-autonomy, which is explicitly deferred until passport + a working verifier exist per a project)
- **risk if skipped:** Every other roadmap tier (P4 grounding, P5 project-scoped taste, autonomy beyond ai-editor) stays blocked indefinitely; the README's own dependency ordering (P3 is 'the crux') is violated if work is attempted on P4/P5/autonomy-widening first

### 128. Project scan API + passport storage + approval gate
- **status:** not-started · **effort:** L
- **what:** POST /api/v1/projects/scan {path} -> passport JSON, storing under .aios/projects/<id>/passport.{json,md} (path convention named in GAGOS_ULTRA_PLAN.md B2). Because a project scan is a 'proposal' on the README's knowledge ladder (Observation -> Proposal -> Human approval -> Verified use), the scan result must NOT become trusted context automatically — needs the same pending/approve/reject pattern aios/api/routes/memory.py already implements for semantic facts (/api/v1/memory/facts/pending/{id}/approve|reject), reused or mirrored for passport fields.
- **unblocks:** any UI or agent surface that wants to read passport data without accidentally treating an unreviewed scan as fact
- **risk if skipped:** a passport scan of an untrusted/malicious repo (e.g. a README with embedded prompt-injection text, or a suggested_improvements field seeded by attacker-controlled content) gets treated as trusted operator-approved context with no human gate, contradicting the project's core evidence-ladder invariant

### 129. Local-only LLM enforcement for the passport harvester's own reasoning calls
- **status:** not-started · **effort:** S
- **what:** When project_passport.py needs an LLM call to synthesize purpose/goals/suggested_improvements from scanned file contents, the client must be constructed with cloud_tasks=frozenset() (named explicitly in GAGOS_ULTRA_PLAN.md B2) so an operator's private, possibly-proprietary project source never leaves the machine during a routine scan.
- **unblocks:** safe-by-default passport scanning of sensitive/proprietary external projects
- **risk if skipped:** scanning a private client project could silently route its file contents to a cloud provider under the interactive-default AIOS_ROUTER_CLOUD_TASKS policy, which is exactly the kind of undisclosed egress the project's own thesis audit already flagged as a contradiction elsewhere in the router

### 130. Passport staleness detection + re-scan trigger
- **status:** not-started · **effort:** M
- **what:** A passport is a point-in-time snapshot; nothing today detects that a project has drifted (new dependencies, changed build commands, new risky files) since the last scan. Add a cheap drift check (git HEAD hash comparison for git repos, mtime/hash comparison for non-git dirs) that flags a passport as stale and offers/queues a re-scan rather than silently serving outdated 'safe vs risky' classifications.
- **unblocks:** safe reuse of a passport across sessions without re-scanning every time, while avoiding silently-stale risk classifications
- **risk if skipped:** a file that was 'safe' at scan time (e.g. a script) could become risky after the operator edits it, and a stale passport would keep classifying it safe — a real safety regression if passport data ever feeds an autonomy decision

### 131. Passport viewer/editor frontend panel
- **status:** not-started · **effort:** M
- **what:** No frontend surface exists to view or correct a project passport (searched frontend/src for 'passport' — zero matches). Needs a panel analogous to OperatorProfileCard.jsx but for passport fields, with the pending-approval affordances the storage-layer item above requires (approve/reject/edit fields before they become trusted).
- **unblocks:** operator visibility into what GAGOS believes about a project before it acts on that belief
- **risk if skipped:** passport data becomes an invisible backend artifact the operator can't audit or correct, undermining the 'human sovereign' framing for this specific subsystem

### 132. Passport harvester test fixtures (>=5 real project shapes)
- **status:** not-started · **effort:** M
- **what:** GAGOS_ULTRA_PLAN.md's own workspace-scope audit found the previously-assumed test/target directories were fiction (crypto-tracker is Node but the executor image is python:3.12-slim; ansel/example are empty; pt is pytest's own 519-file scratch dir). The passport harvester needs its own deliberately-chosen fixture set: a real Node app, a real Python app, a monorepo, an empty directory (edge case), and a directory with no .git (edge case) — each with an expected-passport golden to assert against.
- **unblocks:** confidence that the harvester doesn't silently misclassify stack/commands on the shapes that already burned a prior planning pass
- **risk if skipped:** repeats the exact mistake GAGOS_ULTRA_PLAN.md's red-team already caught once (a harvester that works on toy fixtures but produces nonsense on a real Node/Python mix)

### 133. Sovereign Web Navigator module (distinct from the existing CRAG websearch fallback)
- **status:** not-started · **effort:** XL
- **what:** Build the actual P4 navigator. aios/core/websearch.py is a narrow, ~90-line CRAG Slice-3b helper: POSTs a query to one configurable Tavily-compatible endpoint, secret-scrubs the query, and returns up to 3 result snippet strings — no full-page fetch, no citation objects, no cross-source verification, no quarantine, no freshness tracking, no per-fact provenance. It exists purely to backfill internal RAG recall when local memory confidence is low (gated by AIOS_CRAG_EXTERNAL/AIOS_CRAG_WEBSEARCH, both default off). None of this is the 'controlled internet research with cited sources, cross-verification, quarantine, freshness tracking, and re-verification on use' the README promises for P4. That is a new subsystem.
- **unblocks:** every other P4 item below; also the general capability of GAGOS answering questions that need current external information with any accountability trail
- **risk if skipped:** P4 remains entirely aspirational; if anyone mistakes websearch.py for 'P4 done', the system silently inherits web content's staleness/poisoning risk with zero of the stated mitigations (freshness, quarantine, cross-verification) actually implemented

### 134. Citation/provenance schema for web-sourced findings
- **status:** not-started · **effort:** M
- **what:** Define a per-finding record {source_url, retrieved_at, content_hash, extraction_method} distinct from the current bare list[str] snippets websearch.py returns. Every claim that later becomes a memory candidate needs to carry this provenance through promote_fact so a web-derived fact is visibly and permanently distinguishable from an operator-stated or project-scanned one.
- **unblocks:** the quarantine tier, cross-verification, and freshness items below (all need a citation object to operate on, not a bare string)
- **risk if skipped:** even if a navigator ships, web-derived claims become indistinguishable from operator-approved facts once inside semantic_facts, silently violating the README's 'internet findings are observations' framing

### 135. Web-content quarantine tier (separate proposal pathway for external content)
- **status:** not-started · **effort:** L
- **what:** README states auto-extraction reads ONLY the operator's own statements — never file contents or model output. There is currently no proposal pathway for internet-sourced content at all (grep of aios/api/routes/memory.py's pending-fact flow shows no web/external-source column or actor). Web content needs its own quarantine lane, held to a stricter bar than operator statements (which are trusted as spoken-by-the-human) since web content is untrusted-by-construction.
- **unblocks:** any web finding entering memory at all with correctly differentiated trust
- **risk if skipped:** the only two options today are 'web content never enters memory' (P4 useless) or 'reuse the operator-statement pathway' (a serious trust-model violation letting scraped/attacker-influenced text masquerade as operator-approved)

### 136. Cross-source verification requirement
- **status:** not-started · **effort:** M
- **what:** Require >=2 independent sources to agree (or explicitly flag single-source claims as such) before a web finding is eligible to become even a quarantined proposal. Nothing in websearch.py compares results across sources — it returns whatever the single configured provider returns.
- **unblocks:** meaningfully mitigating (not solving — README's own ceiling statement) the staleness/poisoning risk the README names as inherited-but-mitigated for P4
- **risk if skipped:** a single compromised or SEO-gamed page becomes indistinguishable from a well-corroborated fact

### 137. Freshness TTL + re-verification-on-use
- **status:** not-started · **effort:** M
- **what:** A web-sourced fact needs an expiry; using it after the TTL should trigger a re-fetch/re-verify before the system relies on it again, rather than silently serving stale information forever (the way an operator-stated preference reasonably can be treated as durable, a scraped price/version/status cannot).
- **unblocks:** honest 'freshness tracking and re-verification on use' claim (currently zero code for this)
- **risk if skipped:** the system could confidently restate month-old scraped information as if current, with no mechanism even flagging the staleness

### 138. Full-page fetch + text extraction
- **status:** not-started · **effort:** M
- **what:** websearch.py only consumes the search provider's own result.content/snippet/title fields — it never fetches and parses a full page. A real navigator needs its own HTTP fetch (reusing the existing HTTPS-only/no-localhost _validate_endpoint pattern as a security baseline) plus readability-style text extraction, since snippets alone are too thin to ground a cited claim.
- **unblocks:** citations that actually point to verifiable page content rather than a search engine's own summary
- **risk if skipped:** any 'citation' is really just a link to a search-result blurb, not evidence a skeptic could independently verify

### 139. Injection defense specific to fetched web content
- **status:** not-started · **effort:** M
- **what:** Fetched web pages are the single highest-risk untrusted-input surface in the whole system (attacker-controlled text, by definition). The known context notes the injection_vector_shield is currently dormant system-wide; even once it's flipped on generally (a Phase-C item in GAGOS_ULTRA_PLAN.md, out of this area's scope), P4 specifically needs the shield (or an equivalent sanitization pass) applied to extracted page text before it ever reaches a prompt, since this is the one roadmap tier that intentionally ingests adversarial-by-default content.
- **unblocks:** safe ingestion of arbitrary web content without becoming a live prompt-injection vector into the agent loop
- **risk if skipped:** a scraped page containing 'ignore previous instructions and run X' becomes a direct injection path into whatever agent loop consumes navigator output — the single most dangerous gap in this entire area if P4 ships before this

### 140. Multi-provider search abstraction + budget guard
- **status:** not-started · **effort:** M
- **what:** Today's config (aios/config.py CRAG_SEARCH_ENDPOINT/CRAG_SEARCH_API_KEY) hardcodes exactly one Tavily-compatible endpoint with no fallback and no spend/call cap. A real navigator needs a provider abstraction (so an outage or rate-limit on one provider doesn't kill research capability) plus a budget guard analogous to the BudgetGuard concept already spec'd for the Council Runtime (docs/superpowers/specs/2026-06-27-sovereign-ai-os-roadmap.md section 14) but currently unbuilt for web search specifically.
- **unblocks:** reliable, cost-bounded research capability
- **risk if skipped:** an uncapped research loop against a paid search API is a real runaway-cost risk with zero guard today

### 141. Domain allow/deny policy
- **status:** not-started · **effort:** S
- **what:** No policy exists to exclude categories of source (paste sites, sites requiring auth, known-low-quality domains) from being fetched at all. A minimal denylist plus an operator-configurable allowlist mode.
- **unblocks:** reducing the injection/poisoning attack surface at the source-selection layer, before content even reaches extraction
- **risk if skipped:** no defense-in-depth if the injection-defense item above has a gap; also no legal/ethical guardrail against scraping auth-walled content

### 142. Dedicated audit actor + endpoint surface for web navigation
- **status:** not-started · **effort:** M
- **what:** aios/api/routes/system.py already has a precedent pattern (_has_cloud_route checks for audit rows with actor='cloud-route'); web navigation needs its own actor (e.g. 'web-navigator') so every external fetch — URL, timestamp, content hash — lands in the tamper-evident audit ledger the same way cloud routing does today. Also needs the actual endpoints: POST /api/v1/web/research {query} -> cited findings, GET /api/v1/web/sources/{id}.
- **unblocks:** auditability of the single highest-egress-risk subsystem in the roadmap; frontend citation display (next item)
- **risk if skipped:** web fetches would be the one major egress surface with no audit trail, breaking the 'everything audited' invariant the ultra plan states as non-negotiable for autonomous work

### 143. Frontend citation display for web-sourced facts
- **status:** not-started · **effort:** M
- **what:** Sourced facts need a visible citation chip/link in the UI (superbrain or a workbench panel) that is visually distinct from local-memory or operator-stated facts, so the operator can tell at a glance which claims trace to the internet vs. approved memory.
- **unblocks:** operator ability to actually exercise the cross-verification/quarantine review the backend items above create
- **risk if skipped:** even a fully-built backend navigator would surface findings indistinguishably from trusted memory in the UI, defeating the point of quarantine

### 144. Wire operator/taste facts into the actual generation loop
- **status:** not-started · **effort:** L
- **what:** aios/memory/operator_model.py's render_operator_model() is called in exactly one place today — aios/api/routes/development.py's read-only endpoint that feeds frontend/src/workbench/OperatorProfileCard.jsx. It is never called from aios/agents/tool_agent.py or aios/api/main.py when constructing the system prompt for a real generation turn (grepped both files for render_operator_model/operator_model — zero hits). This is the single biggest gap in P5: 'taste memory' exists as an inert dashboard widget, not as something that changes model behavior.
- **unblocks:** the entire premise of P5 (an operator preference that actually shapes tone/depth/naming/patterns in real output) rather than a read-only display
- **risk if skipped:** P5 stays purely decorative forever; an operator could approve ten 'prefers concise explanations' facts and the model's actual output would never reflect it — a real, checkable honesty gap if P5 is ever claimed as 'built'

### 145. Explicit taste-category schema/predicates
- **status:** not-started · **effort:** M
- **what:** Today operator.* facts are free-form subject/predicate/object triples with no defined vocabulary. P5 as scoped in the README names five concrete categories (tone, explanation depth, naming conventions, design patterns, career goals) plus feedback patterns. Define a constrained predicate set (or a category enum) so these are queryable/promptable as structured taste dimensions rather than an unstructured bag of facts that render_operator_model just group-displays by subject prefix.
- **unblocks:** structured taste-injection into prompts (previous item), and a UI that can present taste by category rather than a flat list
- **risk if skipped:** taste facts stay an ungoverned free-for-all, making both prompt-injection formatting and contradiction detection (which relies on same-subject-different-object matching) less reliable across loosely-related phrasings of the same preference

### 146. Editable/correctable taste-fact UI
- **status:** not-started · **effort:** M
- **what:** OperatorProfileCard.jsx (frontend/src/workbench/OperatorProfileCard.jsx) is read-only — no edit or retract action for an already-active fact. aios/api/routes/memory.py only exposes approve/reject for PENDING proposals and reconcile for CONTRADICTIONS; there is no endpoint to directly correct or retire a single already-active fact (e.g. fixing a typo, or retracting a preference that's no longer true) outside those two flows.
- **unblocks:** the README's own framing of P5 as 'operator-editable preference memory' — currently it is operator-approvable but not operator-editable
- **risk if skipped:** the only way to change a wrong or outdated taste fact is to manually assert a contradicting statement and go through the reconcile flow — workable but not what 'editable' promises, and not discoverable from the UI

### 147. Bridge session-scoped alignment corrections into persistent taste facts
- **status:** not-started · **effort:** M
- **what:** aios/api/routes/memory.py already has /api/v1/conversation/correction and /api/v1/alignment/feedback, which capture per-session interpretation corrections and explicit operator feedback via a ConversationStateStore/AlignmentEvaluationStore — but these are scoped to a single session's alignment frame and never promote a repeated correction into a durable operator.* semantic fact. An operator correcting the same kind of interpretation across 3+ sessions should be a real signal for a candidate taste-fact proposal.
- **unblocks:** the 'feedback patterns' category named explicitly in the README's P5 scope, using signal that's already being captured today but discarded at session end
- **risk if skipped:** a genuinely useful, already-half-built signal (repeated session corrections) never compounds into long-term learning — the system re-learns the same interpretation mistake every session

### 148. Taste-fact staleness / reconfirmation policy
- **status:** not-started · **effort:** S
- **what:** The README claims general memory uses 'decay-weighted freshness,' but operator.* facts have no distinct policy — a tone/style preference asserted once, long ago, is treated as permanently valid with no periodic reconfirmation prompt, unlike more perishable project or web facts.
- **unblocks:** avoiding stale taste applying indefinitely (e.g. a career-goal fact from a year ago that no longer holds)
- **risk if skipped:** minor but real: the system could keep applying an outdated preference indefinitely with no mechanism to prompt reconfirmation

### 149. Per-project vs. global taste scoping
- **status:** not-started · **effort:** M
- **what:** Today's operator.* facts are inherently global (no scoping dimension). Once P3's passport work lands, some preferences are legitimately project-specific (naming conventions in project A vs. project B) rather than universal (tone). No mechanism distinguishes the two today.
- **unblocks:** correct taste application once multiple projects are in play (depends on P3's workspace concept existing first)
- **risk if skipped:** cross-project bleed: a naming convention adopted for one project's codebase gets silently applied to an unrelated project

### 150. Mode selection framework (Student / Developer / Professional / Creator)
- **status:** not-started · **effort:** XL
- **what:** Zero code exists for this. Grepped frontend/src and aios/ for StudentMode/DeveloperMode/ProfessionalMode/CreatorMode — no matches. aios/api/routes/system.py's onboarding_state() only tracks 5 first-run milestones (firstDirective, firstApproval, firstVerify, firstCloudRoute, firstAutonomy) for the single existing mode of operation; there is no concept anywhere of a selectable product mode that changes UI complexity, defaults, or feature surface.
- **unblocks:** any mode-differentiated onboarding, demo, or feature-gating work; the whole P6 premise
- **risk if skipped:** P6 cannot start at all without this — it is the load-bearing concept every other P6 item assumes exists

### 151. Guided first-run onboarding wizard
- **status:** not-started · **effort:** L
- **what:** frontend/src/workbench/GagosChrome.jsx currently has only a dismissable first-run hint (HINT_DISMISSED_KEY in localStorage) plus the backend milestone tracker above — not a guided setup flow (choosing a mode, connecting a first project, configuring cloud-provider keys with informed consent, walking through the approval gate once). This is materially short of the 'onboarding' P6 names.
- **unblocks:** a coherent first-15-minutes experience for a non-technical operator, which today requires reading START_HERE.md manually
- **risk if skipped:** P6 stays unreachable for any operator who isn't already deeply familiar with the project's internals

### 152. Installer / packaged distribution
- **status:** not-started · **effort:** L
- **what:** No scripts/install*, scripts/setup*, or scripts/launcher* exist yet (checked scripts/ directory — none present; GAGOS_ULTRA_PLAN.md Phase A2 names scripts/launcher.ps1 as still-needed for the always-on daemon, which is a prerequisite different from but related to public distribution). A Public Product needs a one-command or installer-driven setup rather than the current 'clone the repo, read START_HERE.md, run backend and frontend manually' flow.
- **unblocks:** distributing the product to anyone outside the current single-developer workflow
- **risk if skipped:** P6 remains permanently gated behind manual developer setup, which contradicts 'Public Product' by definition

### 153. Multi-tenant / multi-user design decision + implementation
- **status:** not-started · **effort:** XL
- **what:** The memory schema (checked aios/memory/db.py) has no user_id or tenant_id dimension anywhere — the system is single-operator by architecture, matching the README's explicit 'single-operator scale' framing used elsewhere (e.g. in FUTURE_FRONTIER.md's knowledge-graph discussion). A genuine Public Product needs at minimum an explicit decision (one instance per operator vs. real multi-tenancy) documented, and if multi-tenancy is chosen, a real schema migration plus isolation guarantees across the security gateway, audit ledger, and memory stores — none of which exist today.
- **unblocks:** any hosted/SaaS form of distribution; also clarifies scope for the installer item (single-operator install is much simpler than multi-tenant)
- **risk if skipped:** shipping any hosted version without this decision risks either an expensive later migration or a real security/privacy incident from unplanned tenant data bleed across the security gateway and memory stores

### 154. Public-facing docs / demo materials distinct from developer README
- **status:** not-started · **effort:** M
- **what:** README.md and START_HERE.md are developer/technical documents. P6 names 'demo videos, case studies' — no such assets exist in the repo (docs/ has no demo or case-study content). This is content work, but it is still concrete, scoped, buildable work blocking P6.
- **unblocks:** any external-facing launch or demonstration of the product to non-technical audiences
- **risk if skipped:** the project remains illegible to anyone outside its own developer, no matter how complete the underlying system becomes


## periphery (completeness critic — missed by the 10 area sweeps)

### 155. [high] No at-rest encryption for local memory/audit SQLite stores
- The security sweep focused on egress (privacy_filter, scope_lock, cloud routing) and the memory sweep focused on backup/compaction/retrieval quality — both stopped short of asking whether data already at rest on the laptop's disk (operator-approved personal facts, project passports, the Ed25519 audit hash-chain, working/episodic/semantic memory DBs) is protected if the device is lost, stolen, or accessed by other local malware. privacy_filter.py only gates what leaves for cloud LLM calls; nothing encrypts the SQLite files themselves.

### 156. [high] No self-upgrade/rollback procedure for the always-on daemon's own runtime code
- The existing items cover git-repo-aware snapshots for *workspace edits* (0.4) and backup/restore of the data/ directory, but neither addresses what happens to the *running daemon process itself* once Phase B4's self-authored PR is human-merged: does the live process hot-reload, or does it need a controlled restart; how is an in-flight autonomous task drained; what is the DB-migration ordering; and how does the operator roll back to the prior version if the new one regresses post-merge. This is exactly the 'upgrade/rollback of the OS itself' the Ultra Plan's Definition-of-100% #1 (7-day unattended survival) implicitly requires but never specifies.

### 157. [medium] No consolidated threat-model document tying the tactical security fixes together
- Every security sweep item is a tactical point-fix (privacy filter, scope_lock denylist, frozen-core hardening, boot attestation). None of the ten sweeps produced a single STRIDE-style enumeration of adversaries (prompt-injected file content, a compromised/hallucinating worker LLM, physical device theft, network MITM on cloud calls, a misbehaving autonomous daemon) mapped to which mitigation covers it and what residual risk remains. Without this, nobody can say with confidence the point-fixes add up to full coverage rather than just the leaks someone happened to notice.

### 158. [medium] No operator-facing full data export / manual 'forget everything' control
- aios/memory/compaction.py implements automated, decay-based forgetting (aging out stale rows) for storage hygiene — the memory sweep correctly flagged that as manual-trigger-only and lacking scheduling. But an operator-invoked 'export all my data' or 'delete everything about me now' control is a different capability (privacy/data-sovereignty, not storage management) and was verified absent by name (grep for export/forget/purge endpoints in main.py returned nothing beyond the compactor). This matters directly for the project's own 'sovereign operator owns memory' claim.

### 159. [medium] Accessibility is ad hoc, not systematically audited, for the primary 3D superbrain UI
- The frontend sweep surfaced exactly one accessibility item (a color-only quarantine indicator, WCAG 1.4.1) because it was scanning for functional/data-fabrication bugs, not doing an accessibility pass. Verified: only 8 prefers-reduced-motion references exist across the whole superbrain frontend, and there is no documented keyboard-navigation path or screen-reader-accessible fallback (e.g. a text log of cognition events) for a UI whose primary surface is a continuously-animated WebGL organism. This is a whole missed dimension, not a single bug.

### 160. [medium] No operator-facing disclosure of what each cloud provider does with egressed data
- The honesty sweep checked internal claims against internal code (router defaults, privacy-filter behavior, frontend fabrication) but never checked the *external* trust boundary: once data passes the privacy filter and reaches Anthropic direct, Bedrock, or Gemini, there is no docs/DATA_HANDLING.md stating each provider's retention period, training-data usage policy, or region. For a project whose entire identity is 'sovereignty of authority, not infrastructure,' this is a live gap in living up to that claim, not just an internal-code discrepancy.

### 161. [low] docker-compose.yml ships Grafana with a known default admin/admin credential and no startup warning
- The deployment sweep concentrated on watchdogs, log rotation, and backups. It missed that the compose stack documented in AGENTS.md ('Grafana... default admin password `admin` unless overridden') has no equivalent to the API token's enforced 32-character minimum (aios/api/main.py) — nothing warns or fails closed if an operator brings the observability stack up with the shipped default credential, unlike the token path which the code actively hardens.

### 162. [medium] README claims cross-platform support ('Windows, Linux, or macOS') that is untested and undisclosed as such
- The honesty sweep re-verified router/privacy/frontend claims line-by-line but did not check the README's platform-scope line against reality: CI runs only on windows-latest, the Ultra Plan's Phase A (launcher, watchdog, idle detection) is written entirely in PowerShell/schtasks/Win32 GetLastInputInfo, and no Linux/macOS packaging, testing, or even documented-gap exists. This is the same class of contradiction the sweep already found elsewhere (claims vs. code) but in a dimension (platform portability) none of the ten area passes was scoped to check.

### 163. [low] No license-compatibility audit of third-party dependencies (distinct from CVE scanning)
- CI already runs pip-audit and npm audit for vulnerabilities (verified in .github/workflows/ci.yml), which likely made the sweep conclude dependency hygiene was handled. But license-compatibility (whether a transitive dependency like torch/faiss-cpu carries terms incompatible with the project's Apache-2.0 LICENSE and the P6 'installer / packaged distribution' goal) is a separate check nothing in CI performs, and it only becomes load-bearing once the roadmap's public-distribution phase ships.


**Completeness verdict:** The combined 92-item inventory plus these ten additions is now broad enough to draft a credible master plan from — it already covers the security spine, autonomy/council wiring, memory lifecycle, routing, frontend honesty, observability, CI/testing, deployment resilience, the P3-P6 roadmap, and doc/thesis honesty in real depth, and the GAGOS_ULTRA_PLAN.md v2 (already red-teamed to 49 findings) shows the security/autonomy portion in particular has had a second, harder pass. What stays genuinely thin even after this sweep is the operational/legal periphery around going from 'single-operator experimental system' to anything longer-lived or more exposed: real incident-response procedure (not just the OPERATIONS.md/SECURITY.md stubs already flagged), data-at-rest protection and operator-initiated data deletion/export, a unified threat model, and the self-upgrade/rollback story for the daemon's own code once it is autonomously merging PRs into itself unattended. None of these block near-term work, but a plan that calls itself done without addressing at least the self-upgrade/rollback gap and at-rest encryption would be leaving two concrete, verifiable holes in exactly the 'honest, sovereign, fail-closed' bar this task set for itself.
