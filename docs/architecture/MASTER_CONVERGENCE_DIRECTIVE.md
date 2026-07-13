# GAGOS SOVEREIGN INTELLIGENCE AI-OS V1.0

## Master Convergence and Production-Control-Plane Implementation Directive

> Canonical directive for transforming `swap821/ai-editor` into GAGOS v1.0 — a local-first sovereign intelligence agentic AI-OS prototype for one developer, combining a permanent Queen Council, ephemeral worker colony, evidence-aware memory, multi-model intelligence, isolated execution and a truthful living interface under absolute human authority.

This is a convergence and hardening mission. Do not replace GAGOS’s unusual subsystems with a simpler conventional agent architecture. Preserve them, clarify their roles, remove duplicated authority paths and wire them into one efficient causal organism.

---

## PART I — OPERATING RULES

### 1. Do not trust narration over code

The repository contains many plans, architecture documents, test reports and historical state files. Use them as context, but determine reality from:

- Current imports.
- Runtime composition.
- Endpoint registration.
- Configuration reads.
- Database writes.
- Event producers and consumers.
- Frontend mount sites.
- Tests.
- Actual commands and CI results.

A config flag existing does not prove a subsystem is wired. A class existing does not prove it is instantiated. A test existing does not prove production uses the tested class. A frontend component existing does not prove it is mounted. Before touching each subsystem, trace its complete runtime path.

### 2. Never implement the entire roadmap in one branch

Work one ordered slice at a time. For each slice:

1. Inspect the actual current implementation.
2. Document the invariant being established.
3. Add failing tests first where practical.
4. Implement the smallest complete architectural change.
5. Run focused tests.
6. Run the full backend and frontend gates.
7. Update the implementation ledger.
8. Commit the slice independently.
9. Stop and report evidence.

Do not start the next slice while the current slice is incomplete or red.

### 3. Do not perform a cosmetic rewrite

Do not:

- Rename everything without changing architecture.
- Create a second replacement event bus.
- Create a second replacement policy engine.
- Create a third agent runtime.
- Duplicate memory stores.
- Add another global state singleton.
- Add abstractions that have no production caller.
- Add config flags without a runtime branch and tests.
- Move hundreds of files only to appear architectural.
- Replace unique GAGOS terminology at the product layer.

Conventional terminology may be used inside lower-level infrastructure, but the product architecture remains:

- Human Sovereign / King.
- Sovereign Kernel.
- Queen Council.
- Temporary Worker Colony.
- Cortex.
- Memory.
- Proof and Recovery.
- Living Mirror.

### 4. Preserve hard security invariants

Never weaken:

- RED actions remain unapprovable.
- Authority never travels through the Cortex Bus.
- Model output never grants authority.
- Pheromones remain advisory.
- A weak green cannot promote trusted memory.
- Verification remains target-specific.
- Secrets are scrubbed before persistence and model exposure.
- Scope violations fail closed.
- Missing isolation never causes silent host fallback.
- Rollback targets remain exact and snapshot-bound.
- Approval capabilities are single-purpose.
- Frontend state never becomes backend authority.

### 5. Branch and commit discipline

Use one branch per slice:

- `kimi/gagos-s00-baseline`
- `kimi/gagos-s01-edge-boundary`
- `kimi/gagos-s02-operator-identity`
- ...

Commit naming:

- `feat(control-plane): ...`
- `fix(security): ...`
- `refactor(runtime): ...`
- `test(adversarial): ...`
- `docs(architecture): ...`

Never commit:

- Test-output dumps.
- Temporary debugging scripts.
- Secrets.
- Local databases.
- Generated coverage directories.
- Unrelated formatting changes.
- Broad dependency upgrades unrelated to the slice.

Do not merge to master automatically.

---

## PART II — NORTH-STAR PRODUCT CONTRACT

### 6. V1 product boundary

GAGOS v1.0 supports:

- One enrolled human operator.
- One developer workstation.
- Multiple explicitly enrolled project roots.
- One local GAGOS control plane.
- One isolated execution service.
- Local model support.
- Optional cloud models behind explicit privacy policy.
- Permanent Queen Council organs.
- Temporary bounded workers.
- Evidence-aware memory.
- Human-supervised mutations.
- Verified low-risk earned autonomy.
- Truthful frontend self-portrait.
- Crash recovery, audit and rollback.

GAGOS v1.0 does not require:

- Multi-tenancy.
- Enterprise RBAC.
- Organization management.
- Public unauthenticated deployment.
- Distributed consensus.
- Kubernetes.
- Hundreds of simultaneous workers.
- Autonomous policy modification.
- Autonomous credential management.
- Autonomous control-plane self-modification.
- Fully unrestricted computer control.

Do not widen the product boundary.

### 7. One causal life cycle

Every meaningful directive must eventually conform to:

```
Human directive
    ↓
Turn Coordinator
    ↓
Project and memory context
    ↓
Intent and risk classification
    ↓
Adaptive Queen Council deliberation
    ↓
Bounded MissionContract
    ↓
Deterministic policy decision
    ↓
Human capability when required
    ↓
Worker Foundry selects worker strategy
    ↓
Worker executes inside isolated staged workspace
    ↓
Evidence Authority records results
    ↓
Verification Authority challenges results
    ↓
Promotion Authority atomically promotes or rejects
    ↓
Memory Authority consolidates verified learning
    ↓
Cortex emits observations
    ↓
Read models update incrementally
    ↓
Living Mirror displays truthful state
```

There must be no alternative side-effect path that bypasses this life cycle.

### 8. Runtime convergence rule

The repository currently contains:

- Direct conversational chat.
- ToolAgent.
- Role passes.
- Swarms.
- Council missions.
- Council workers.
- Direct execute routes.
- Terminal routes.
- Self-apply.
- Rollback.
- Memory promotion.

Do not delete their useful behavior. Reassign them:

- **Turn Coordinator** owns the lifecycle of one human directive.
- **Queen Council** owns deliberation and bounded mission creation.
- **Worker Foundry** owns selection and creation of temporary execution strategies.

Worker strategies (existing systems become strategies):

- `ToolAgent` → `ToolLoopWorkerStrategy`
- `run_role_pass()` → `RolePassWorkerStrategy`
- `run_swarm()` → `SwarmWorkerStrategy`
- `worker_entry` → `DeterministicWorkerStrategy` / `CodeWorkerStrategy`

`ToolAgent`, `run_role_pass()` and `run_swarm()` should ultimately be used behind these strategies rather than remain competing top-level runtimes.

- **Action Broker** owns every proposed side effect.
- **Policy Kernel** returns deterministic allow, approval-required or deny decisions.
- **Capability Authority** binds human approval to one exact action.
- **Execution Broker** sends approved actions into the isolated execution plane.
- **Evidence and Verification Authorities** determine what happened and whether it is trustworthy.

---

## PART III — CANONICAL DOMAIN LANGUAGE

Create these domain contracts before large-scale rewiring. Use Pydantic or immutable typed models. Prohibit unknown fields unless migration compatibility specifically requires them.

### 9. Principal

```python
class Principal:
    principal_id
    principal_type: operator | system | model | queen | worker | scheduler | recovery
    display_name
    session_id
    authentication_level
    authenticated_at
    parent_principal_id
    metadata
```

Rules:

- Only operator may issue human approvals.
- A Queen remains a proposal-producing principal.
- A worker principal is derived from its mission.
- A model is never represented as an operator.
- Caller-provided display text never becomes identity.

### 10. TurnContext

```python
class TurnContext:
    turn_id
    session_id
    operator_id
    project_id
    directive
    mode: conversation | advisory | mission | governance
    data_classification
    correlation_id
    created_at
    status
```

Both `/api/v1/chat` and `/api/generate` must eventually call one Turn Coordinator. They may retain compatibility routes temporarily, but they must not maintain independent memory, routing or authority pipelines.

### 11. MissionContract v1

Create `MissionContractV1` rather than mutating v0.1 unsafely.

```python
class MissionContractV1:
    version
    mission_id
    turn_id
    parent_mission_id
    project_id
    requested_by
    created_by
    goal
    worker_strategy
    caste
    priority
    risk_level
    policy_version
    scope: ...
    budgets: ...
    network: ...
    models: ...
    verification: ...
    approval: ...
    recovery: ...
    integrity: ...
```

The contract digest must change whenever an authority-relevant field changes.

### 12. ActionEnvelope

```python
class ActionEnvelope:
    action_id
    turn_id
    mission_id
    principal_id
    action_type
    target
    payload_reference
    payload_digest
    requested_scope
    expected_side_effects
    network_intent
    secret_intent
    data_classification
    requested_at
    policy_version
    mission_contract_digest
```

Every mutation must create one. Examples include file read/write, command execution, network request, model call involving sensitive data, memory promotion, policy proposal, worker spawn, rollback, project enrollment, package installation, self-analysis patch promotion.

### 13. PolicyDecision

```python
class PolicyDecision:
    decision: ALLOW | REQUIRE_APPROVAL | DENY
    risk: GREEN | YELLOW | RED
    reason_codes
    human_explanation
    constraints
    required_capability_spec
    policy_version
    evaluated_at
```

This is deterministic. No LLM may return or modify an authoritative `PolicyDecision`.

### 14. CapabilityGrant

```python
class CapabilityGrant:
    capability_id
    operator_id
    authentication_event_id
    action_id
    action_digest
    mission_id
    contract_digest
    scope_digest
    resource_digest
    policy_version
    issued_at
    expires_at
    nonce
    maximum_uses = 1
    status
    revoked_at
    consumed_at
    signature_or_mac
```

A capability must fail when reused, expired, revoked, action/target/scope/policy/contract changed, operator session invalid, or required privileged authentication is stale.

### 15. EvidenceRecord

```python
class EvidenceRecord:
    evidence_id
    mission_id
    action_id
    worker_id
    evidence_type
    source
    content_reference
    content_digest
    redaction_status
    produced_at
    environment_digest
    tool_version
    trust_level
    verification_strength
    supersedes
    metadata
```

Evidence should reference large content rather than duplicate it everywhere.

### 16. CanonicalEvent v1

```python
class CanonicalEventV1:
    schema_version
    event_id
    event_type
    entity_type
    entity_id
    mission_id
    turn_id
    worker_id
    correlation_id
    causation_id
    sequence
    occurred_at
    source
    trust_level
    payload
    payload_digest
```

Events remain observations only. Add explicit categories:

- `operational`
- `narrative`
- `ambient`
- `interaction`

Only backend operational events may mutate authoritative frontend read models.

### 17. Mission state machine

Use one enforceable state machine:

```
draft
→ deliberating
→ blocked | awaiting_approval
→ approved | rejected
→ queued
→ running
→ verifying
→ promotion_pending
→ completed | failed | rolled_back | cancelled
```

Invalid transitions fail closed. Store transitions transactionally.

---

## PART IV — PERFORMANCE AND COMPLEXITY BUDGETS

The system must become incremental.

### 18. Required complexity characteristics

**Cortex**

- Event append: amortized O(1).
- Fetch unread events: O(k) for k unread events.
- Event lookup: indexed.
- Never scan the full history for a normal snapshot.
- Never maintain an unbounded client queue.

**Read models**

- Apply one event: O(1) or proportional only to affected active entities.
- Fetch system portrait: approximately O(1) plus current active missions/workers.
- Rebuild only as a recovery operation.

**Capability authority**

- Capability lookup: indexed O(1).
- Nonce/replay lookup: indexed O(1).
- Action-digest comparison: bounded by canonical serialization size.

**Mission scheduling**

- Mission lookup: indexed.
- Worker status lookup: indexed.
- Queue insertion/removal: O(log w) or better.
- V1 maximum active worker count remains small and configurable.

**Memory router**

- Exact identity or session lookup → SQL index.
- Recent episode lookup → timestamp/project index.
- Semantic similarity → FAISS.
- Verified skill lookup → task/project/signature indexes.
- Fact relationships → indexed fact edges.

Do not query every memory subsystem for every turn.

**Council**

Do not invoke every Queen for every directive. Use adaptive participation:

- Simple conversation → no Council mission.
- Low-risk project question → Memory Queen + Router Queen.
- Ordinary code mission → Planner + Memory + Security + Testing plan.
- High-risk mission → Planner + Memory + Security + Testing + Critique.
- Architectural mission → full Council.

---

## PART V — ORDERED IMPLEMENTATION SLICES

### SLICE 0 — Establish executable truth

**Objective:** Create one authoritative implementation baseline before modifying architecture.

**Inspect:** `aios/api/main.py`, `aios/api/deps.py`, `aios/api/routes/*`, `aios/agents/*`, `aios/council/*`, `aios/core/*`, `aios/memory/*`, `aios/runtime/*`, `aios/security/*`, `aios/policy/*`, `frontend/src/workbench/*`, `frontend/src/superbrain/*`, `docker-compose.yml`, `Dockerfile`, `.github/workflows/*`, `.aios/state/*`.

**Create:**

- `docs/architecture/NORTH_STAR_V1.md`
- `docs/architecture/CURRENT_RUNTIME_MAP.md`
- `docs/architecture/SUBSYSTEM_REGISTRY.md`
- `docs/architecture/AUTHORITY_MAP.md`
- `docs/architecture/DATA_OWNERSHIP.md`
- `docs/adr/`
- `.aios/state/PRODUCTION_CONVERGENCE_LEDGER.md`

Generate an actual subsystem registry. For every subsystem record: name, role, production entry point, constructor, feature flag, default, producers, consumers, database/files, authority level, tests, status (live / partially wired / dormant / dead / duplicate), target organ.

**Establish baseline:** Run the gate commands and record exact outcomes.

**Acceptance gate:**

- Working tree clean before implementation.
- Current failures documented.
- No production code changed.
- All major side-effect paths mapped.
- All current databases and file stores mapped.
- Every feature flag’s actual reader identified.
- Parallel runtimes explicitly diagrammed.

**Forbidden shortcut:** Do not copy the existing architecture document and call the slice complete.

---

### SLICE 1 — Repair the browser and request trust boundary

**Objective:** Eliminate the current origin-hostname vulnerability and make mutation authentication exact.

**Refactor:** Extract edge security from `aios/api/main.py` into `aios/interfaces/http/edge_security.py`. Implement separate functions for parsing, origin, host, proxy, and IP validation.

**Rules:**

- Invalid IP input returns invalid, never private.
- Only exact localhost receives hostname-local treatment.
- `localhost.attacker.example` is rejected.
- `127.0.0.1.attacker.example` is rejected.
- Origin comparison includes exact scheme, hostname and port.
- `Origin: null` is rejected for mutations.
- `Sec-Fetch-Site` is supporting evidence, not standalone authentication.
- Add Host-header validation.
- Trust forwarded headers only from explicitly configured trusted proxies.
- Mutation routes require authenticated session or valid machine token.

**Tests:** Add adversarial tests for arbitrary domain Origin, localhost suffix attacks, IP-looking domain attacks, IPv6, encoded hostnames, trailing dots, mixed case, empty/null Origin, spoofed proxy headers, invalid Host header, simple and JSON POSTs, DELETE/PATCH, Council approve/reject, self-analysis reject, rollback. Every test must assert that the intended side effect did not happen.

**Acceptance gate:** Arbitrary websites cannot mutate GAGOS; exact allowed local origins still work; CLI bearer authentication works; no mutation relies only on a client IP being private; full suites green.

---

### SLICE 2 — Create the real Human Sovereign principal

**Objective:** Make operator authority attributable.

**Implement single-developer enrollment:** Create `aios/domain/identity/`, `aios/application/identity/`, `aios/infrastructure/identity/`. Support exactly one initial operator, bootstrap enrollment only when no operator exists, Argon2id password or generated local enrollment credential, recovery code, server-side session, session rotation, logout/revocation, privileged re-authentication, durable operator ID. Store no plaintext password.

**Session correction:** Do not return session cookie material in JSON. Remove body-session fallback from production-sensitive routes. Stop echoing `sessionId`. Treat the cookie as opaque bearer material. Store only a secure hash server-side. Add CSRF token bound to the authenticated session. Rotate the session on privilege escalation. Record authentication events.

**Principal dependency:** Create `get_authenticated_principal()` and `require_privileged_operator()`. Migrate execute, approval, rollback, Council approve/reject, project enrollment, self-analysis decisions, autonomy settings, policy settings.

**Acceptance gate:** Anonymous local processes cannot claim to be the operator; browser JavaScript receives no reusable session value; body `sessionId` cannot authenticate; approval identity comes from backend authentication; session rotation and revocation tests pass; existing non-mutating local flows remain usable.

---

### SLICE 3 — Replace approval tokens with exact capabilities

**Objective:** Turn “approval” into an exact, single-use control-plane capability.

**Implement:** Create `aios/domain/capabilities/`, `aios/application/capabilities/`, `aios/infrastructure/capabilities/sqlite_store.py`. Evolve `ApprovalStore` through a compatibility adapter. Bind every capability to operator, action, payload digest, resource, scope, mission, contract digest, policy version, privileged authentication event, expiry, single-use nonce.

**Migrate first:** Command execution, rollback, file create/edit, Council mission approval, Council worker mid-mission approval, self-analysis proposal apply.

**Council correction:** Remove fixed `decided_by = "king_dashboard"`. Record the authenticated `operator_id`.

**Self-apply correction:** Remove caller-controlled `approvedBy`. Self-analysis may continue producing proposals, but applying a proposal must consume a privileged capability bound to the exact patch digest.

**Acceptance gate:** Tests must prove replay fails, edited command fails, edited file content fails, changed mission contract fails, changed policy version fails, different session fails, revoked capability fails, expired capability fails, correct exact action succeeds once.

---

### SLICE 4 — Introduce explicit runtime profiles

**Objective:** Replace accidental feature combinations with validated product modes.

**Create:** `aios/bootstrap/settings.py`, `aios/bootstrap/profiles.py`, `aios/bootstrap/startup_validation.py`.

**Profiles:** `development`, `demo`, `production`, `test`.

**Production defaults:** Loopback or same-origin gateway; documentation routes disabled; exact origin configuration; real operator authentication; container executor required; host worker execution forbidden; synthetic metrics forbidden; self-apply disabled; cloud burst disabled unless provider policy explicitly allows it; earned autonomy disabled until later slices; debug endpoints disabled; no default credentials.

**Demo defaults:** No real project mutation; no terminal execution; synthetic state visibly labelled; safe demonstration data.

**Compatibility:** Temporarily map current environment variables into typed settings, but prevent business logic from reading module globals indefinitely.

**Startup posture report:** Report profile, operator enrollment, edge security, executor availability, database health, audit integrity, project roots, model providers, cloud privacy state, disabled capabilities, fatal errors, warnings. Production startup fails on fatal errors.

**Acceptance gate:** Production cannot silently start with host execution; demo cannot mutate real projects; invalid flag combinations fail at startup; settings are instantiated once and injected.

---

### SLICE 5 — Create ActionEnvelope and the deterministic Policy Kernel

**Objective:** Establish one authority path for all side effects.

**Create:** `aios/domain/actions/`, `aios/domain/policy/`, `aios/application/action_broker.py`, `aios/infrastructure/policy/`.

**Migrate policy logic from:** `aios/security/gateway.py`, Security Queen wrappers, direct route checks, tool handlers, WorkerRuntime, Self-apply, Rollback, File endpoints, Model privacy decisions. Do not delete the existing gateway immediately; adapt it behind the new Policy Kernel until migration is complete.

**Add an enforceable route registry:** Every mutating endpoint declares `action_type`, `required_principal`, `body_limit`, `rate policy`, `audit event`, `capability requirement`. CI fails when a mutating route has no declaration.

**Acceptance gate:** Every mutation creates an `ActionEnvelope`; every mutation receives a `PolicyDecision`; unknown actions deny; route metadata is enforced, not descriptive; model output cannot directly call an executor.

---

### SLICE 6 — Unify `/chat` and `/generate` beneath TurnCoordinator

**Objective:** Eliminate two independent cognitive pipelines without removing their useful fast paths.

**Create:** `aios/application/turns/turn_coordinator.py`, `aios/application/turns/turn_context.py`, `aios/application/turns/turn_result.py`.

**Coordinator flow:** authenticate → construct `TurnContext` → classify directive → restore conversation context → retrieve relevant memory → cerebellum check → determine mode → select direct conversation or mission → stream typed events → record outcome.

**Modes:** `conversation` (no tools/project side effects), `advisory` (read allowed context, no mutation), `mission` (creates Council mission), `governance` (approvals, rollback, settings).

**Compatibility routes:** Keep `/api/v1/chat` and `/api/generate` temporarily; both delegate to the coordinator. Do not retain duplicate recall, routing, session or outcome code.

**Acceptance gate:** One turn ID exists across chat, mission, events and memory; both routes produce compatible typed events; conversation fast path remains fast; tool-requiring intent cannot bypass mission policy; existing frontend remains operational through compatibility adapters.

---

### SLICE 7 — Introduce MissionContract v1 and transactional mission state

**Objective:** Turn Council artifacts into durable product state.

**Implement:** Versioned mission contract, mission state machine, mission repository, transition validation, contract digest, project/operator/policy/capability association, budget fields.

**Current artifact migration:** Mission state is split among JSON contracts, JSON ledgers, JSON King reports, approval files, `CouncilState` SQLite, Cortex events. Make SQLite the authoritative mission source. Keep JSON ledgers and reports as exported artifacts, not competing truth.

**Staged migration:** Add database source; dual-write temporarily; compare database and files in tests; switch reads to database; retain export functionality; remove authority from files.

**Acceptance gate:** A mission survives restart; invalid state transitions fail; concurrent double approval does not double-run; file tampering cannot modify authoritative mission state; mission history is queryable by project and turn; current mission artifacts can be migrated.

---

### SLICE 8 — Converge the Queen Council

**Objective:** Make the Council the single deliberative brain for missions.

**Preserve existing Queens:** Planner, Security, Memory, Testing, Critique. Add clear adapters for Routing, Reflection, Project Understanding. Do not make every Queen an LLM.

**Adaptive Council:** Create deterministic Council participation policy based on mission type, risk, scope, data classification, model requirements, verification requirements, prior failures.

**Queen output:** Every Queen returns `QueenVerdict`, `QueenEvidence`, constraints, confidence basis, recommended worker strategy, unresolved questions. Confidence must include its basis.

**QueenService correction:** The existing service registry must become either a real initialized registry with bounded service queues and production callers, or a removed duplicate after its useful behavior is absorbed. Do not leave live API endpoints operating against an always-empty registry.

**Acceptance gate:** The Council generates one `MissionContract v1`; Queen constraints are machine-enforced downstream; no Queen can widen operator scope; full Council invoked only when justified; Council cost and latency measured; Queen service endpoints reflect actual registered services.

---

### SLICE 9 — Unify ToolAgent, role-pass, swarm and Council workers

**Objective:** Create one Worker Foundry without deleting existing intelligence strategies.

**Create:** `aios/application/workers/foundry.py`, `aios/application/workers/scheduler.py`, `aios/domain/workers/`, `aios/infrastructure/workers/strategies/`.

**Strategies:** Wrap existing implementations:

- `ToolAgent` → `ToolLoopWorkerStrategy`
- `run_role_pass()` → `RolePassWorkerStrategy`
- `run_swarm()` → `SwarmWorkerStrategy`
- `worker_entry` → `DeterministicWorkerStrategy` / `CodeWorkerStrategy`

**Worker lifecycle:** requested → admitted → born → running → awaiting_capability → completed | failed | killed → dissolved.

**Scheduler:** Priority queue, global concurrency cap, per-mission cap, per-provider model cap, cancellation, deadline, budget enforcement, fairness across missions, no unbounded spawning.

**Worker identity:** Every worker receives worker principal, exact mission contract, exact action capabilities, no inherited operator identity, no global access to config secrets.

**Acceptance gate:** All worker styles use one scheduler; `run_swarm()` is no longer an alternate authority path; worker lifecycle events are canonical; a worker cannot spawn another worker outside contract authority; failure always produces evidence and dissolution.

---

### SLICE 10 — Introduce Privacy Broker and governed model routing

**Objective:** Make local-plus-cloud intelligence an explicit sovereign policy.

**Create:** `aios/domain/privacy/`, `aios/application/models/privacy_broker.py`, `aios/application/models/model_router.py`, `aios/infrastructure/models/providers/`.

**Data classes:** `PUBLIC`, `PROJECT_INTERNAL`, `SENSITIVE`, `SECRET`, `NEVER_EXTERNAL`.

Every model call records requesting principal, mission, purpose, data classification, redactions, allowed provider set, selected provider/model, local/cloud decision, fallback, estimated and actual token use, cost, latency, output digest.

**Preserve existing routing:** Ollama, Bedrock, Gemini, OpenAI-compatible, Anthropic, CRAG external sources, IntelligenceGateway. No provider may be called directly from a Queen or worker after migration.

**Acceptance gate:** `NEVER_EXTERNAL` data cannot reach cloud; cloud burst is policy-controlled; fallback cannot silently widen privacy; provider health does not become authority; the frontend can show exactly which intelligence participated.

---

### SLICE 11 — Build the isolated Executor Service

**Objective:** Move the complete worker body—not only verification commands—behind an OS isolation boundary.

**Architecture:** GAGOS control plane → private authenticated protocol → Executor service → disposable container cage. The main control plane must not receive the Docker socket. Only the executor service may manage worker containers.

**Protocol:** Use structured messages: `job_id`, `mission_contract_digest`, `capability`, `image`, `argv` or worker entrypoint, workspace snapshot, mount policy, environment allowlist, network policy, resource limits, timeout, output limit, verification expectation. Do not send raw shell strings.

**Cage requirements:** Disposable container, non-root user, read-only root filesystem, writable staged workspace only, no network by default, capability drop, `no-new-privileges`, PID limit, CPU/memory limits, temporary directory quota, full process-tree destruction, bounded output, no host home, no SSH agent, no cloud metadata, no inherited `.env`, no Docker socket, no arbitrary devices.

**Windows development:** Support Docker Desktop as the initial v1 isolation substrate. Host backend remains development-only and must never activate under production profile.

**Acceptance gate:** The Council worker itself runs inside the cage; LLM-generated code never executes in the control-plane process; container unavailable means refusal; fork bombs, output floods and timeouts are contained; worker cannot access host credentials; worker destruction is independently verified.

---

### SLICE 12 — Wire staged workspaces and the dormant worktree concept

**Objective:** Prevent workers from modifying the actual project before verification.

**Inspect existing:** `aios/runtime/worktree_backend.py`, `aios/runtime/snapshots.py`, `aios/agents/rollback_engine.py`, `aios/runtime/rollback_registry.py`. Reuse validated behavior where appropriate. Do not enable the existing worktree module merely because it exists.

**Flow:** real project → immutable baseline identification → mission worktree/staged workspace → worker changes → diff collection → verification in fresh cage → promotion decision → atomic application → post-promotion check.

**Required properties:** One mission, one workspace; collision-safe IDs; workspace path never supplied directly by model; symlink and junction escape protection; clean deletion after mission; failed work remains inspectable for a bounded retention period; real project remains untouched before promotion.

**Acceptance gate:** Failed workers do not dirty the project; concurrent missions cannot overwrite one another; diff is reproducible; baseline changes invalidate stale promotion; worktree cleanup is safe on Windows and Unix.

---

### SLICE 13 — Establish Evidence and Verification Authorities

**Objective:** Make proof a product-level authority shared by every runtime.

**Create:** `aios/domain/evidence/`, `aios/domain/verification/`, `aios/application/evidence/`, `aios/application/verification/`.

**Verification plan:** Before execution, define intended behavior, relevant targets, required tests, static checks, security checks, expected/forbidden side effects, minimum strength, freshness requirements.

**Evidence requirements:** Evidence must bind to mission, action, workspace digest, code diff digest, executor environment, tool version, verification command, output digest, timestamp.

**Preserve anti-laundering:** The weakest required evidence remains the promotion limit. A passing sibling file cannot hide a failing target. A command exiting zero is not automatically strong evidence.

**Self-consistency module:** The existing dormant self-consistency implementation may be wired as an optional verification strategy, never as approval authority. Only wire it when it consumes canonical evidence, has production callers, its feature flag has tests, and it can only strengthen caution. Otherwise archive it.

**Acceptance gate:** All worker strategies return canonical evidence; Testing Queen consumes Evidence Authority results; verification is behavior-aware; stale evidence cannot verify changed content; memory promotion uses only authoritative verification results.

---

### SLICE 14 — Create atomic Promotion and Recovery

**Objective:** Make verified change promotion a controlled transaction.

**Promotion process:**

1. Confirm mission state.
2. Confirm capability where required.
3. Confirm project baseline digest.
4. Confirm contract digest.
5. Confirm required verification strength.
6. Create recovery checkpoint.
7. Apply staged diff.
8. Run post-promotion smoke test.
9. Mark completed.
10. Emit observations.
11. Consolidate memory.

**On failure:** Restore checkpoint, verify restoration, mark failed or rolled back, record evidence, reduce relevant autonomy.

**Self-analysis:** Self-analysis may detect, explain, propose patch, build staged workspace, run tests, present evidence. It may not directly modify the control plane in v1. Self-analysis promotion uses the same path as any other mission and requires privileged operator approval.

**Acceptance gate:** No verified change is promoted without a checkpoint; partial promotion is recoverable; rollback restoration is tested; audit and mission state remain consistent after restart; self-analysis has no private shortcut.

---

### SLICE 15 — Upgrade Cortex to durable consumer semantics

**Objective:** Turn Cortex into a reliable nervous system.

**Preserve:** Durable append, observation-only rule, canonical events, retention, at-least-once delivery.

**Add:** `cortex_consumers` table with `consumer_name`, `last_event_id`, `updated_at`, `status`, `failure_count`. Each consumer advances independently.

**Delivery:** Batch by cursor; retry only failed consumer; dead-letter or quarantine after bounded repeated failure; per-entity ordering; idempotency keys; replay pagination; retention boundary detection; snapshot-required response when history is unavailable.

**SSE:** Bounded queue, slow-client detection, maximum queue age, disconnect/reconnect, paginated replay, sanitized payload limits, heartbeat, explicit event name and schema version.

**Acceptance gate:** One failed observer does not block others; reconnect beyond 1,000 events works; slow client cannot cause unbounded memory; authority event families remain structurally blocked; events can be replayed deterministically.

---

### SLICE 16 — Build incremental system read models

**Objective:** Eliminate historical rescanning and hardcoded truth.

**Create projection tables:** `system_portrait`, `active_turns`, `active_missions`, `active_workers`, `queen_health`, `model_health`, `executor_health`, `memory_summary`, `verification_summary`, `governance_summary`, `project_summary`. Projection consumers update these incrementally from canonical events and authoritative database state.

**Remove:** Full 100,000-event snapshot scan, hardcoded node count, hardcoded engaged model count, hardcoded memory size, random operational drift, unqualified confidence indicators.

**Metric envelope:** Every displayed value uses `value`, `status` (`measured` / `derived` / `unavailable` / `stale` / `simulated`), `measured_at`, `source`, `freshness`.

**Acceptance gate:** Snapshot cost does not grow with complete event history; fresh boot is truthful; reconnect is truthful; stale state is visible; no invented operational value exists in production mode.

---

### SLICE 17 — Create one Memory Authority

**Objective:** Preserve specialized memories while giving them one promotion, provenance and retrieval policy.

**Keep specialized adapters:** Working, Episodic, Semantic, Facts, Skills, Mistakes, Curriculum, Council memory, Pheromones, Narrative self, Operator model. Do not force all data into one physical table.

**Create canonical interfaces:** `recall(query, context)`, `propose(record)`, `verify(proposal, evidence)`, `promote(proposal, operator_or_policy)`, `supersede(record)`, `compact(policy)`, `rebuild_derived_indexes()`.

**Memory record provenance:** Every durable promoted record includes source principal, source turn/mission, evidence IDs, verification strength, operator approval when applicable, project, policy version, confidence basis, contradictions, supersession lineage, review/expiry time.

**Pheromones:** Remain advisory, decaying, project-scoped, non-authoritative, derived from verified outcomes. They may influence routing priority, never permissions.

**Versioned database migrations:** Replace the growing ad hoc migration function with `aios/infrastructure/storage/migrations/0001_...`, `0002_...`, record migration digests and versions.

**Acceptance gate:** Derived FAISS indexes are rebuildable; repetition alone cannot create truth; untrusted document content cannot self-promote; every verified skill has evidence lineage; fresh install and upgrade paths pass.

---

### SLICE 18 — Make learning and earned autonomy one governed loop

**Objective:** Preserve GAGOS’s learning techniques while preventing uncontrolled trust accumulation.

**Learning loop:** attempt → evidence → verification → outcome → lesson/skill proposal → promotion decision → reuse → reuse evidence → reinforcement or decay.

**Autonomy is per action class:** Never assign one global autonomy score. Example keys: `project + action_type + tool + path class + verification plan`.

**Trust increases only with:** strong verification, repeated success, stable policy, stable project, no scope violations, no hidden network/secret access, successful rollback availability.

**Trust decreases with:** failure, weak evidence, tool change, model change, policy change, project change, time decay, audit anomaly, operator revocation.

**Cerebellum:** Use as a fast proposal path for verified patterns. It may propose a known safe workflow but still passes through policy and capability enforcement.

**Curriculum:** Can evaluate development but cannot grant authority.

**Acceptance gate:** No model can edit its trust score; autonomy cannot transfer between projects; failure causes decay; policy changes invalidate earned capabilities; every autonomous action remains reversible and visible. Keep earned autonomy disabled in the production profile until this gate passes.

---

### SLICE 19 — Reshape the frontend into four product spaces

**Objective:** Turn the unique interface into a coherent product without losing the living organism.

**Home — Living Mind:** Organism, conversation, current directive, current mission, one important approval, overall trust and degradation state.

**Workbench:** Project tree, code editor, diff, terminal, test output, materialized work surfaces.

**Governance:** Actual Council mission, Queen verdicts, constraints, exact capability request, policy reason codes, scope, network intent, secret intent, verification plan, rollback checkpoint, autonomy policy, emergency stop.

**History:** Mission timeline, worker births and dissolution, evidence, verification, memory provenance, rollbacks, model participation, cost, audit integrity.

**Correct Council panel:** Replace the current swarm-only Council panel with actual Council state. Swarm state may remain as a subsection. Panel behavior: most panels closed by default; preserve layout preferences; one clear primary task; keyboard navigation; reduced motion; non-WebGL access to all governance actions.

**Acceptance gate:** The Council shown is the real backend Council; approval displays exact consequences; core control works without the canvas; mobile begins as read-only for privileged governance; product remains visually unique.

---

### SLICE 20 — Make the Living Mirror constitutionally truthful

**Objective:** Connect the organism’s body to measured state without turning it into a plain dashboard.

**Event distinction:**

- **Operational** — only from backend canonical events (mission running, worker started, verification failed, approval required, model selected, memory promoted).
- **Narrative** — derived explanation of operational truth.
- **Ambient** — pure visual life (breathing, background movement, idle particles).
- **Interaction** — local frontend state (hover, camera, panel open, keyboard input).

Ambient and interaction events may animate the organism but must never claim operational activity.

**Replace giant switch:** Create a typed reaction registry: event type, required schema, operational reducer, visual reaction, accessibility announcement, fallback behavior. Unknown events are logged and ignored safely.

**Organism mapping:**

- Healthy control plane → breathing.
- Active Council → cortical convergence.
- Worker birth → bounded emergence.
- Worker dissolution → reabsorption.
- Approval wait → contraction/held posture.
- Verification success → evidence pulse.
- Verification failure → guarded degradation.
- Offline backend → dormant state.
- Stale data → visually distinct from offline.
- Audit failure → critical governance warning.

**Acceptance gate:** Frontend cannot invent worker or model activity; every operational animation traces to a canonical event; ambient life remains beautiful while idle; accessibility has text equivalents; event schema tests cover reaction mappings.

---

### SLICE 21 — Operations, observability and recovery

**Objective:** Make the local product understandable when something fails.

**Secure Compose topology:** Add gateway/frontend, control-plane, executor. Keep observability internal or loopback by default. Remove default Grafana password, public Prometheus exposure, public Alertmanager exposure by default.

**Trace IDs:** Propagate `request_id`, `turn_id`, `mission_id`, `action_id`, `worker_id`, `correlation_id`, `causation_id`.

**Metrics:** Pending approvals, active missions, active workers, policy denials, capability replay attempts, executor availability, event lag, verification strength, rollback count, memory promotion count, model token use and cost, cloud routing count, audit health. Do not place prompts, paths containing secrets or user content in metric labels.

**Recovery commands:** `gagos doctor`, `gagos backup create`, `gagos backup verify`, `gagos backup restore`, `gagos audit verify`, `gagos cortex rebuild-projections`, `gagos memory rebuild-index`, `gagos executor probe`.

**Acceptance gate:** Crash during mission recovers to a known state; corrupt derived index rebuilds; backup restoration is tested; audit failure is visible; support bundle is redacted; observability has no default credential.

---

### SLICE 22 — Make CI a production release authority

**Objective:** Ensure green tests mean the shipped production profile is trustworthy.

**Preserve current gates:** Python 3.12, Ubuntu/Windows/macOS backend tests, 85% backend coverage, frontend typecheck, frontend tests and coverage, frontend production build, dependency audit, CodeQL.

**Add:** Ruff lint and formatting, type checking for domain/application layers, import-boundary tests, secret scan, license scan, container scan, SBOM, Docker executor integration test, database migration test, backup/restore test, Playwright production flow, architecture conformance tests, dead-code and unused-feature-flag report.

**Frontend warning budget:** Reduce monotonically `124 → 100 → 75 → 50 → 25 → 0`. Never raise it.

**Adversarial suite:** Cross-site mutation, DNS rebinding, session fixation and replay, capability replay, path traversal, symlink/junction escape, malicious model output, prompt injection, secret exfiltration, network bypass, output flood, process bomb, worker timeout, database lock, event poison, slow SSE client, audit tampering, stale verification, stale promotion, partial rollback.

**Acceptance gate:** Production profile is exercised in CI; P0 and P1 security findings are zero; architecture boundaries are enforceable; release artifact includes SBOM; latest release tests clean installation and recovery.

---

### SLICE 23 — Package the single-developer product

**Objective:** Make GAGOS launchable as a product rather than a repository ritual.

**Provide one launcher:** `gagos start`, `gagos stop`, `gagos status`, `gagos open`.

**First-run flow:**

1. Enroll Human Sovereign.
2. Save recovery code.
3. Enroll one project root.
4. Verify executor.
5. Detect local model.
6. Configure optional cloud providers.
7. Select privacy policy.
8. Run safe diagnostic mission.
9. Demonstrate approval.
10. Demonstrate rollback.

**Same-origin production:** Serve frontend and API through one local origin. Cross-origin Vite development remains development-only.

**Updates:** Signed; back up first; check database compatibility; apply versioned migrations; retain rollback package; never overwrite user projects.

**Acceptance gate:** Clean-machine installation works; no source editing required; one launcher starts all required services; uninstall preserves projects by default; upgrade and rollback are tested.

---

### SLICE 24 — Reintroduce controlled autonomy and declare v1.0

**Objective:** Enable the north-star intelligence only after the sovereign spine is trustworthy.

**Levels:**

- **L0 Advisory** — no side effects.
- **L1 Observation** — read approved project context.
- **L2 Supervised action** — every mutation requires exact capability.
- **L3 Earned low-risk action** — only narrow, previously verified action classes. No network, secrets, package installation or control-plane modification.
- **L4 Bounded delegated mission** — operator approves goal, scope, tools, time, workers, network, token/cost budget, verification, stop conditions. Workers may operate inside that contract only.

**Emergency control:** One operator action must revoke all unused capabilities, stop queued missions, kill active workers, disable autonomy, preserve evidence, keep read-only diagnosis available.

**V1 release declaration:** Do not call GAGOS v1.0 production-ready until:

- Real operator identity is enforced.
- Exact capabilities are enforced.
- Entire workers are isolated.
- Project changes are staged.
- Verification gates promotion.
- Rollback is tested.
- Cortex has independent consumer cursors.
- Mirror has no fabricated operational state.
- Council UI shows real deliberation.
- Memory promotion has provenance.
- Production configuration fails closed.
- CI validates installation, mission, approval, execution, verification, promotion and rollback.

---

## PART VI — ARCHITECTURAL CONFORMANCE TESTS

Create tests that continuously enforce:

- No model imports `CapabilityAuthority` write methods.
- No Queen directly imports executor implementation.
- No frontend value grants authority.
- No worker receives operator credentials.
- No event type from an authority family enters Cortex.
- No mutating route lacks an `ActionEnvelope`.
- No capability lacks an action digest.
- No promotion occurs below required verification strength.
- No production worker backend is host subprocess.
- No production operational metric uses synthetic values.
- No memory promotion lacks evidence lineage.
- No config flag exists without a production reader or declared dormant status.
- No second top-level mission orchestrator exists.

Fail CI when these invariants break.

---

## PART VII — SLICE REPORT FORMAT

After every slice, report:

- Slice
- Branch
- Starting SHA
- Ending SHA
- Invariant established
- Current implementation inspected
- Files added
- Files modified
- Files removed
- Database migrations
- Tests added
- Focused test command and result
- Full backend command and result
- Frontend typecheck result
- Frontend lint result
- Frontend test result
- Frontend build result
- Security/adversarial result
- Container result
- Performance before
- Performance after
- Known residual risks
- Deferred work
- Why this slice is independently safe

Do not claim completion without command evidence.

---

## PART VIII — FORBIDDEN SHORTCUTS

Never:

- Hardcode operational telemetry.
- Accept caller-provided human identity.
- Authenticate from body `sessionId`.
- Let approval override RED policy.
- Silently fall back to host execution.
- Run the worker brain on the host in production.
- Treat exit code zero as automatically strong proof.
- Promote model repetition into truth.
- Allow Cortex to carry authority.
- Use frontend state as proof of approval.
- Leave Queen service endpoints backed by an empty registry.
- Keep two independent mission authorities.
- Add a third bus.
- Add an unbounded queue.
- Scan full event history per snapshot.
- Open every panel by default.
- Claim voice is implemented when it only logs.
- Enable self-apply before the common promotion authority exists.
- Enable global autonomy.
- Delete unique subsystems merely because they are disabled.
- Preserve dead code merely because its name sounds visionary.

A dormant subsystem must be either:

1. Properly wired behind canonical contracts and tested.
2. Explicitly archived with its design retained.
3. Removed after reachability proof and migration of useful ideas.

---

## PART IX — FIRST EXECUTION ORDER

Begin with:

- **SLICE 0 — Establish executable truth**
- **SLICE 1 — Repair browser and request trust boundary**

Do not begin Slice 2 in the same implementation session.

At the end of Slice 1:

- Run all required gates.
- Produce the slice report.
- Show the exact diff summary.
- State remaining P0 risks.
- Stop.

The product must become safe from the outside inward, then converge from the authority spine outward.

The final goal is not merely that GAGOS has many intelligent subsystems.

The final goal is that:

> Every organ speaks one canonical language, every worker is born under one mission contract, every action passes through one constitution, every claim returns with evidence, every memory retains provenance, every visual reaction reflects reality, and the Human Sovereign remains the only final authority.
