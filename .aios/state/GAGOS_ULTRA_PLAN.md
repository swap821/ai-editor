# GAGOS Sovereign Brain — Ultra Plan v4 (final, red-teamed twice)

**Author:** Claude Code (Fable, co-architect) · **Date:** 2026-07-07
**Supersedes:** v1, v2, v3, and the Codex "Final Production Prompt".
**Backing catalog:** [`GAGOS_REMAINING_INVENTORY.md`](./GAGOS_REMAINING_INVENTORY.md) — ~157 distinct
remaining items (the "163" count double-counted ~6; see Dedup note). Grounded by a thesis audit
(62 claims), a v2 autonomy red-team (49 findings), a 10-area inventory, and a **v3 red-team (43
findings, 6 critical)** whose fixes are folded in here. This is the ORDER, GATES, and CORRECTIONS.

---

## v3 -> v4 changelog (what the red-team forced)

1. **Phase-name legend added** — the catalog's cross-refs use v2 letters (A-F); v4 maps them (below).
2. **Catalog de-duplicated** — real count ~157, not 163 (frozen-core, git-snapshots, origin-routing,
   credential-denylist each appeared twice across areas). Use the LARGER effort tag of any pair.
3. **NEW Phase 0.0 — Contain the ALREADY-LIVE autonomy.** v3 falsely said "no autonomy runs until
   Phase 1." `EARNED_AUTONOMY` is default-ON *today* (`config.py:182`) and auto-executes file writes
   after 5 verified successes — with none of Phase 1's guardrails. This is fixed first.
4. **Phase 0.1 now closes TWO live egress holes** — the `privacy_filter.py` secret leak AND the
   `FailoverChatClient` cloud-as-local misclassification + `.complete()` privacy-filter bypass.
5. **Phase 0.3 corrected** — `/health` already exists (`aios/api/routes/system.py`, landed 2026-07-06);
   the task is *upgrade to readiness* (Ollama/DB/disk/router-provider visibility), not "build it".
6. **Frozen-core CI gate redesigned (1.4)** — `classify_target()` hardcodes `package="aios"` and can
   NEVER protect `.github/workflows/` or relocated constants; the gate must operate on full-repo paths.
7. **Origin-routing widened (1.6)** — must also patch `IntelligenceGateway._cloud_allowed()` (the
   Council/worker cloud path), not just `router_wiring._router_policy()`.
8. **NEW: scoped BOT identity for autonomous pushes** — Phase 3 must NOT use the operator's full-scope
   personal GitHub token (verified live in the OS keyring); it needs a fine-grained, ai-editor-only,
   revocable bot credential. The file-glob denylist cannot govern an OS-keyring secret.
9. **NEW: Windows power management** — an always-on laptop sleeps/hibernates/closes its lid; v3 never
   addressed it. Added to Phase 2. The "always-on" claim is honestly bounded to "whenever awake + a
   wake-timer policy," not literally 24/7.
10. **External-project autonomy is now an explicit gated phase (Phase 9-E "ex-Phase F")** — 7+ catalog
    items depend on it; v3 had orphaned it.
11. **~20 orphaned catalog items placed** (King wire/cut #16, King summary bug #17, approval race #26,
    budget dials #27, drift-check #125, host metrics/alerts #105/#70/#66, docs #121/#122, curriculum
    #53, fact-extraction #54, pheromone #55, embedding-version #56, e2e collection #85, taste staleness
    #148, a11y #159, provider data-use disclosure #160, CouncilDashboard #76, and more — see phases).
12. **M2 horizon re-sized honestly** — Phase 3 bundles multiple L/XL items on the true critical path;
    "a few months" was optimistic.

## Phase-name legend (v2 catalog letters -> v4 phases)

`A -> 2 (Always-On Host)` · `B -> 3 (Sovereign Loop)` · `C -> 4 (Observability)` ·
`D -> 8 (Testing/Torture)` · `E -> 0.2 + 10 (Honesty/Docs)` · `F -> 9-E (External-Project Autonomy)`.
"Definition-of-100%" cross-refs point at the numbered DoD at the end of this doc.

---

## Three milestones (unchanged framing)

- **M1 — Honest 100% (weeks):** every thesis claim true, BOTH live egress holes closed, the live
  autonomy path contained, docs match code, a machine-checked drift guard. → Phase 0.
- **M2 — Sovereign 100% (several months, honestly):** always-on, earning verified experience
  autonomously on **ai-editor via a scoped bot PR**, guarded + observable + torture-tested. → 1-4, 8.
- **M3 — Product 100% (long horizon):** external-project autonomy (9-E) + P4-P6 + multi-user +
  encrypted-at-rest. → 5-7, 9, 10.

## Guardrail spine (NON-NEGOTIABLE)

RED never auto-runs · frozen core never autonomously edited (code + CI on FULL-REPO paths, 1.4) ·
`SCOPE_ROOTS` never widened to home root · credentials/system/personal hard-excluded (denylist 1.2 +
scoped bot token, not the operator's keyring) · every autonomous write reversible via git-aware
snapshot · ai-editor self-work = branch → full suite + prover → PR (scoped bot) → operator merge ·
autonomous LLM calls local-only (router AND IntelligenceGateway) · everything audited · kill switch +
digest · commit only on operator ask · Honesty Law.

---

# PHASE 0 — Truth & Safety (M1) · days-to-1wk · DO FIRST

- **0.0 Contain the already-live autonomy** (security · M · **do this before anything**). `EARNED_AUTONOMY`
  is ON today and auto-applies writes after 5 successes without the credential denylist / workspace-id /
  ScopeContext. Immediately either (a) wire the 1.2 denylist + a workspace-id check directly into
  `AutonomyLedger.is_earned()` now, or (b) narrow the live path to `training_ground/` until Phase 1 lands.
  **Operator sign-off.**
- **0.1 Close BOTH live cloud-egress holes** (security · M · sign-off). (i) `privacy_filter.py`
  `_in_filename_context` waves through `/`-bearing secrets (AWS keys, PEM bodies) → run credential/entropy
  checks *before* the path exemption; ideally route egress detection through the hardened
  `secret_scanner.scan_and_redact()`. (ii) `FailoverChatClient` misclassifies openai/anthropic as "local"
  and `.complete()` bypasses `PrivacyFilter` on `AnthropicDirectClient`/`OpenAICompatClient` → fix both;
  add regression tests for all three.
- **0.2 Thesis honesty pass + a MACHINE-CHECKED drift guard** (docs · M). Fix every CONTRADICTED/STALE
  claim (router local-only-by-default, prover 16-vs-19, "secrets redacted", "goes dormant"/RegionPins,
  `autonomy.py` docstring, injection-shield off #11, swarm-cloud default-True, frozen-core coverage,
  planner-confidence caveat, boot-attestation detection-only, test counts) across README/AGENTS/PLAN.
  **Build `tools/thesis_audit.py` (#125 — the single highest-leverage item):** asserts config defaults ==
  documented claims, run in CI. Reconcile remaining PARTIAL claims (#126). Add a per-provider
  data-use disclosure (#160).
- **0.3 Upgrade `/health` to readiness** (ops · S->M). It EXISTS (`system.py`, 2026-07-06); add a distinct
  `/ready` probe: Ollama reachability, DB writability, disk-free, and router/provider visibility (#37, #68).

**Gate M1 (machine-checked):** `tools/thesis_audit.py` green in CI (zero CONTRADICTED/STALE) + both
egress-hole regression tests pass + 0.0 contained. The system is now honest AND cannot silently rot.

---

# PHASE 1 — Autonomy-Safe Foundation (M2 gate) · weeks · security spine, sign-off each

Each its own reviewed PR with `pytest tests/test_security.py tests/test_audit.py` green.

- **1.1 Per-task `ScopeContext`** (L) — replace `scope_lock`'s process-global mutable `_scope_roots`.
- **1.2 Sub-path credential denylist** (M) — fail-closed globs into every read/write handler.
- **1.3 Per-workspace `AutonomyLedger`** (M) — `workspace_id` in `signature()` + migration.
- **1.4 Frozen-core hardening + FULL-REPO CI gate** (L->XL) — relocate guardrail constants →
  `aios/security/limits.py`, CORS/Bearer → `aios/security/http_guard.py`. **Redesign `classify_target()`
  to operate on full-repo-relative paths (not the hardcoded `aios/` prefix)** so it can protect
  `.github/workflows/`, `limits.py`, and `http_guard.py`. Add a CI job failing any PR touching a frozen
  path. (Closes DoD #3.)
- **1.5 Git-repo-aware snapshots** (L) — wire `WorktreeBackend` (built, zero callers) / in-repo throwaway
  refs; `SnapshotManager` raises on existing `.git`.
- **1.6 Origin-scoped routing across BOTH cloud paths** (L) — `origin: interactive|autonomous` into
  `router_wiring._router_policy()` **AND** `IntelligenceGateway._cloud_allowed()`; autonomous-origin
  traffic must be forced local-only even though the interactive shipped config keeps
  `AIOS_ROUTER_CLOUD_TASKS=reasoning,coding`; `SWARM_CLOUD_BURST` off for the daemon.
- **1.7 Concurrency + cost + latent-security** (M) — atomic exclusive-create for the request_id approval
  decision (#26, race today); wire real per-token cost estimation so `BudgetGuard` dials can actually fire
  (#27, dead controls today); sign+enforce boot attestation; wire the audit-anchor publisher; key rotation.
- **1.8 King: wire-or-cut decision** (M) — the King LLM-reasoning is dead code in production (#16). Decide
  and land it BEFORE Phase 3/6 build on the King; if wired, fix the `human_summary`-vs-`recommendation`
  desync (#17) in the same PR.

---

# PHASE 2 — Always-On Host (no new autonomy) · after Phase 1

Launcher + Scheduled Task with reboot survival (3am Windows-Update) · **Windows power management: handle
sleep/hibernate/lid-close; wake-timer policy or an honest "runs when awake" bound** · watchdog (crash +
memory-ceiling) · RAM budget table + backend policy (Ollama+Docker+API vs 16GB) · log rotation · kill
switch · `data/` backup/restore · snapshot/rollback-git retention + gc · low-disk detection · graceful
degradation (retry/circuit-breaker/fallback-to-local).

---

# PHASE 3 — Sovereign Work-Loop (M2 core) · ai-editor first · after 1-2

**Precondition — scoped BOT identity:** provision a fine-grained, **ai-editor-repo-only, revocable**
GitHub token for autonomous PR pushes. **Never the operator's OS-keyring personal token.** The loop
authenticates as the bot; the operator merges.

Workspace registry (seed ai-editor, write_mode=pr) · heartbeat loop: idle/AC-gated via `psutil` (add dep)
+ Ollama arbitration (interactive preempts) + **power-aware pause** + task-source priority + worktree-lane
lifecycle · **async self-work** (branch → full suite + prover → bot PR → operator merge; NOT a synchronous
human wait) · earned-autonomy wired into the council/worker mission path · worker-reasoning behind
origin/frozen/workspace gates · morning digest v2 with one-click revert.

**Gate M2:** loop opens ≥1 operator-merged ai-editor PR authored via the bot; earns ≥1
action-class-per-workspace; burn-in monitor (Phase 8) proves ZERO out-of-scope / credential / frozen-core
events; the bot token is proven scope-limited.

---

# PHASE 4 — Observability & Cognition · parallel with 3

Unify the 3 event schemas → cognition bus · `GET /api/v1/cognition/stream` (filters/heartbeat/resume) ·
instrument all subsystems incl. Council/King · request_id↔turn_id · end-to-end run tracing · Prometheus
metrics incl. **host RAM/CPU/disk (#105 — the metric a laptop operator most needs)** + autonomy-grant +
plan-stage advisory (#66) · **real Alertmanager receiver + rules for host pressure, dispatcher liveness,
egress spikes (#70)** · structured logging + durable sink · schedule `CortexBus.sweep()`.

# PHASE 8 — Testing, CI/CD & Hardening · alongside 3-4 · gates M2

Chaos/torture suite · **48h burn-in harness with a security monitor — and a NAMED execution environment**
(the red-team found neither obvious option works; decide: a dedicated always-on runner vs a scoped host
process, and budget it) · frozen-path CI gate (1.4) · real container-executor build/run in CI · fix the
e2e demo-script filename so pytest collects it (#85) · mypy gate · bandit gate · nightly CI (prover +
golden-mission + endurance) · per-module coverage floors · flaky-test hygiene.

---

# PHASE 5 — Memory & Knowledge Depth (M3) · after M2

Project Passport seed is now built as a local-only proposal/evidence scanner; remaining Phase 5 work is
symbol-level RepoMap, scheduled memory maintenance, compaction across all 9+ tables · backup/restore ·
semantic (not lexical) recall · FAISS-index uploaded docs · CRAG calibration on real data · fact-graph
editing · contradiction UX · **curriculum multi-domain + revive the 2 dead escalation templates (#53)** ·
**broaden operator-fact auto-extraction beyond 3 first-person regexes (#54 — feeds P5 taste)** ·
pheromone quality/reinforcement beyond the v7 `PheromoneStore.for_contract` council wiring ·
**embedding-model version tagging + reindex path (#56).**

# PHASE 6 — Frontend Organism (M3) · after 4

Honesty first: kill offline data fabrication (verify real component names by grep) · MemoryGalaxy
mastery-flash + WCAG color-only · wire cognition state machine to real events · King approval UI
(diff/command/rollback — surfaces the #17 summary, so land 1.8 first) · **connect CouncilDashboard.jsx to
the living organism (#76)** · metabolism panel · event replay · routing trust ledger · **systematic
accessibility audit of the 3D UI (#159).**

# PHASE 7 — Router Robustness (M3) · after 1.6

Provider health checks (`available` hardcoded True) · retry/backoff · RAM/VRAM-aware model selection ·
raise cloud token caps · catalog-cache lock · **router ranked-candidate coverage-preview surface (#41)** ·
**refresh the Bedrock curated fallback list (#43).** (Egress/heuristic honesty already in Phase 0.)

---

# PHASE 9 — Roadmap Frontier + External-Project Autonomy (M3, long horizon)

- **9-E External-Project Autonomy (ex-"Phase F") — its own gate.** Extending write-autonomy beyond
  ai-editor requires: a **Node-capable verifier image** (Dockerfile.executor is python-only), a
  fact-checked candidate list (skip empty/stub/scratch dirs), per-project passport + a human-approved
  first task before earn is enabled, and per-project bot scoping. 7+ catalog items unblock here.
- **P4 Sovereign Web Navigator** (XL) · **P5 Human Taste Memory** (incl. taste-fact staleness/reconfirm
  #148) · **P6 Public Product** (modes, onboarding, packaging, multi-tenant decision).

# PHASE 10 — Periphery & Longevity (M3)

At-rest encryption (memory/audit SQLite) · daemon self-upgrade/rollback · consolidated threat-model doc ·
operator data export + "forget everything" · fix Grafana default admin/admin · make/withdraw the untested
cross-platform claim · dependency license-compat audit · incident-response runbook ·
**`docs/API.md` from live OpenAPI (#121)** · **`docs/ARCHITECTURE.md` matching reality (#122).**

---

## Dedup note (the real tally)

The catalog lists ~163 numbered items but double-counts ~6 across areas (frozen-core hardening #5/#25;
git-snapshots; origin-routing #21/#34; credential-denylist; /health #12/#94; King items). **Real distinct
work ≈ 157.** When two entries conflict on effort, take the larger. A future catalog regen should merge them.

## Definition of 100% (ENFORCED)

1. Host survives reboot+crash 7 days unattended (incl. sleep/wake policy).
2. Loop opens ≥1 operator-merged ai-editor PR via the **scoped bot** (not the personal token); earns ≥1
   action-class-per-workspace; burn-in monitor proves ZERO out-of-scope/credential/frozen-core events.
3. **Frozen-path CI gate blocks any PR touching a frozen path — including `.github/` and the relocated
   guardrail files** (proven by a red test).
4. Both live egress holes closed (regression tests) + `tools/thesis_audit.py` green in CI.
5. README re-audit passes — every claim SUPPORTED.
6. Kill switch + digest + one-click revert work; per-module coverage floors + mypy + bandit green.

## Honest sizing

~157 distinct items. **M1 = ~1-2 weeks** (Phase 0 grew: 0.0 containment + a 2nd egress hole + the drift
tool). **M2 = several months** (Phase 3 bundles the heartbeat XL + bot identity + power-awareness + async
self-work + council-autonomy wiring on the true critical path; Phase 1's spine refactors have wide blast
radius). **M3 = long horizon** (9-E + P4/P6 are multi-XL). A program, not a session.

**Start here:** 0.0 (contain live autonomy) + 0.1 (both egress holes) need your sign-off; 0.3 (`/health`
upgrade) + starting `tools/thesis_audit.py` (0.2) need nothing. Say go and I take Phase 0.
