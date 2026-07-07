# GAGOS Sovereign Brain — Ultra Plan v3 (final master plan)

**Author:** Claude Code (Fable, co-architect) · **Date:** 2026-07-07
**Supersedes:** v1, v2, and the Codex "Final Production Prompt".
**Backing catalog:** [`GAGOS_REMAINING_INVENTORY.md`](./GAGOS_REMAINING_INVENTORY.md) — the exhaustive
**163 line items** (status/effort/risk each) this plan sequences. Nothing here is hand-waved; every
workstream points at real items verified against live code by: a thesis audit (62 claims), an
autonomy red-team (49 findings), and a 10-area remaining-work inventory (163 items). This document
is the ORDER and the GATES; the catalog is the DETAIL.

---

## The honest headline

GAGOS has a genuinely strong, well-tested **governance core** and a real vision. It is **not** at
100% on any honest reading — the inventory found **163 remaining items** (131 not-started), including
**one live cloud-egress secret leak**, ~13 places the README/thesis claims things the code does not
do, and the fact that the security primitives needed for safe autonomous operation **do not exist
yet**. "100%" is not one finish line; it is three (below). This plan reaches them in order, and each
step leaves the system **more honest**, not just more feature-full.

## Three milestones (what "100%" actually means)

- **M1 — Honest 100% (weeks):** every thesis claim is TRUE, the live secret leak is closed, docs match
  code. The system *is what it says it is.* Nothing autonomous yet. → Phase 0.
- **M2 — Sovereign 100% (months):** always-on, earning *verified* experience autonomously on
  **ai-editor itself via PR**, fully guarded, observable, and torture-tested. → Phases 1-4, 8.
- **M3 — Product 100% (long horizon):** the P3-P6 roadmap (Passport, Web Navigator, Taste Memory,
  public modes), multi-user, packaged, encrypted-at-rest. → Phases 5-7, 9-10.

Do not conflate them. Chasing M3 before M1 is how the current overclaims happened.

---

## Guardrail spine (NON-NEGOTIABLE, all phases)

RED never auto-runs · frozen core never autonomously edited (enforced in code + CI, Phase 1) ·
`SCOPE_ROOTS` never widened to the home root · credentials/system/personal hard-excluded (denylist,
Phase 1) · every autonomous write reversible via git-aware snapshot · ai-editor self-work = branch →
full suite + prover → PR → operator merge · autonomous LLM calls local-only · everything audited ·
kill switch + digest · **commit only on operator ask · Honesty Law: stop & report if harder than spec'd.**

---

# PHASE 0 — Truth & Safety (M1) · days · DO FIRST

The cheapest, highest-integrity work. Closes the one live hole and makes every claim true *before* any
big build. ~15 items, mostly S.

- **0.1 Privacy-filter secret-leak fix** (security · M). `privacy_filter.py._in_filename_context()`
  waves through any `/`-bearing high-entropy token → AWS secret keys and PEM bodies egress in plaintext.
  Root-cause fix: run credential/entropy checks *before* the path exemption; require a real path
  separator+extension, not slash-count; ideally route egress secret-detection through the hardened
  `aios/security/secret_scanner.scan_and_redact()` instead of the weaker private regex list. + 2
  regression tests. **Operator sign-off (security spine).**
- **0.2 Thesis honesty pass** (docs · ~13 S). Fix every CONTRADICTED/STALE claim in README.md + AGENTS.md
  + PLAN.md: router "local-only by default" (false), prover 16/19-vs-19/19 self-contradiction, "secrets
  redacted" (leak), "goes dormant when no data" (false — RegionPins), `autonomy.py` docstring vs real
  default, INJECTION_VECTOR_SHIELD off-by-default, SWARM_CLOUD_BURST default-True, frozen-core covers
  only `aios/security/*`, no frozen-path CI gate exists (DoD item unmet), planner-confidence caveat,
  boot-attestation is detection-only, stale test counts. **Make prose match code.**
- **0.3 Real `/health` + readiness** (ops · S) — nothing exists today; needed by everything downstream.

**Gate M1:** re-run the thesis audit → zero CONTRADICTED/STALE. The system is now honest.

---

# PHASE 1 — Autonomy-Safe Foundation (M2 gate) · weeks · security spine, sign-off each

The primitives for safe autonomous/multi-project operation **do not exist yet**. Each ships as its own
reviewed PR with `pytest tests/test_security.py tests/test_audit.py` green. **No autonomy code runs until
this phase closes.** (Catalog: security-privacy-spine + the autonomy-security items.)

- **1.1 Per-task `ScopeContext`** (L) — replace `scope_lock`'s process-global mutable `_scope_roots`;
  thread scope through `gateway.classify → command_stays_in_scope → executor._scope_cwd`.
- **1.2 Sub-path credential denylist** (M) — fail-closed globs (`.env .git/ .aws .ssh id_rsa* *.pem
  *.key .docker .claude .codex .gemini`) wired into every read/write handler, additive to root-membership.
- **1.3 Per-workspace `AutonomyLedger`** (M) — `workspace_id` in `signature()` + table migration; every
  call site passes the active workspace.
- **1.4 Frozen-core hardening** (L) — relocate guardrail constants → `aios/security/limits.py`, CORS/Bearer
  → `aios/security/http_guard.py`; widen `frozen_subdirs`; **add a CI job failing any PR touching a frozen
  path** (closes DoD #3).
- **1.5 Git-repo-aware snapshots** (L) — `SnapshotManager` raises on existing `.git`; wire `WorktreeBackend`
  (built, zero callers today) / in-repo throwaway-ref snapshots so real repos are reversible.
- **1.6 Origin-scoped routing** (L) — `origin: interactive|autonomous` threaded into `_router_policy`;
  autonomous cloud eligibility on a separate `AIOS_ROUTER_CLOUD_TASKS_AUTONOMOUS` (default empty);
  `SWARM_CLOUD_BURST` off for the daemon.
- **1.7 Latent-security close-outs** (M/S) — sign+enforce boot attestation (log-only today); wire the
  external audit-anchor publisher (built, never called); key/token rotation trigger; decide GREEN-in-container.

---

# PHASE 2 — Always-On Host (no autonomy yet) · after Phase 1

Make it run forever, safely, on a 16GB laptop. (Catalog: deployment-ops-resilience, 14 items.)

Launcher + Scheduled Task with **reboot survival** (the 3am Windows-Update case) · watchdog (crash +
memory-ceiling restart) · RAM budget table + backend policy (Ollama+Docker+API vs 16GB) · log rotation ·
kill switch · automated `data/` backup/restore · snapshot/rollback-git retention + gc · low-disk detection ·
graceful degradation on provider failure (retry/circuit-breaker/fallback-to-local).

---

# PHASE 3 — The Sovereign Work-Loop (M2 core) · ai-editor first · after Phases 1-2

The centerpiece. Workspace #1 is **ai-editor itself, via PR** — the only fact-checked viable target.
(Catalog: autonomy-council-worker; the XL "always-on host / heartbeat / registry" splits here.)

Workspace registry (`aios/runtime/workspaces.py`, seed ai-editor write_mode=pr) · heartbeat loop
(`heartbeat_loop.py`): idle/AC-gated via `psutil` (add dep) + Ollama arbitration (interactive preempts) +
task-source priority + worktree-lane lifecycle (`destroy_lane` in `finally`, stale-lane sweep, cap) ·
self-improvement = branch → full suite + prover → PR → operator merge · earned-autonomy **wired into the
council/worker mission path** (unwired today) · worker-reasoning behind origin/frozen/workspace gates ·
morning digest v2 with one-click revert.

**Gate M2:** loop opens ≥1 operator-merged ai-editor PR it authored; earns ≥1 action-class-per-workspace;
burn-in monitor proves **zero** out-of-scope / credential / frozen-core events.

---

# PHASE 4 — Observability & Cognition · parallel with Phase 3

You cannot trust an overnight brain you cannot watch. (Catalog: observability-cognition, 14 items.)

Unify the three parallel event schemas → one cognition bus · `GET /api/v1/cognition/stream` (filters,
heartbeat, resume) · instrument all subsystems incl. Council/King · request_id↔turn_id correlation ·
end-to-end run tracing · Prometheus metrics (route-mix, tokens, autonomy grants, event-drop) · structured
logging + durable sink · schedule `CortexBus.sweep()`.

---

# PHASE 8 — Testing, CI/CD & Hardening · gates M2 sign-off

(Numbered 8 to keep roadmap phases contiguous; runs alongside 3-4.) Catalog: testing-ci-quality, 13 items.

Chaos/torture suite (`tests/torture/`) · **48h burn-in harness with a security monitor** · frozen-path CI
gate (also 1.4) · real container-executor build/run in CI · mypy gate · bandit gate · nightly CI (prover +
golden-mission + endurance) · per-module coverage floors · flaky-test hygiene.

---

# PHASE 5 — Memory & Knowledge Depth (M3) · after M2

Catalog: memory-knowledge (13) + roadmap P3 (6). **Project Passport harvester (P3, XL)** —
`aios/memory/project_passport.py` + `POST /api/v1/projects/scan` + storage + staleness re-scan + viewer,
local-only enforced · scheduled memory maintenance (compaction/decay/mining) · compaction across all 9+
tables (3 today) · memory backup/restore · semantic (not lexical) skill/lesson recall · FAISS-index
uploaded docs · CRAG threshold calibration on real data · fact-graph editing surface · contradiction UX.

---

# PHASE 6 — Frontend Organism (M3) · after Phase 4

Catalog: frontend-organism (10). **Honesty first:** kill offline data fabrication (WorkTabLiveDashboard,
RegionPins) — verify real component names by grep · MemoryGalaxy mastery-flash regression + WCAG
color-only fix · wire cognition state machine to real events · King approval UI (diff/command/rollback) ·
memory metabolism panel · event replay · routing trust ledger.

---

# PHASE 7 — Router Robustness (M3) · after Phase 1.6

Catalog: router-providers (14). Egress + heuristic honesty (also Phase 0) · fix FailoverChatClient
local/cloud misclassification · PrivacyFilter on `.complete()` (bypassed today on Anthropic/OpenAI clients) ·
live provider health checks (`available` hardcoded True) · retry/backoff · RAM/VRAM-aware model selection ·
raise cloud token caps · catalog-cache lock.

---

# PHASE 9 — Roadmap Frontier (M3, long horizon) · after M2

Catalog: roadmap-frontier (28). The genuinely-new capabilities, honestly XL:

- **P4 Sovereign Web Navigator** (XL) — a real module distinct from the CRAG websearch fallback: citation/
  provenance schema · web-content quarantine tier · cross-source verification · freshness TTL +
  re-verify-on-use · page fetch+extract · web-specific injection defense · multi-provider search + budget ·
  domain allow/deny · dedicated audit actor · frontend citation display.
- **P5 Human Taste Memory** — wire taste facts into the generation loop · category schema · editable
  taste-fact UI · bridge session alignment-corrections → persistent facts · per-project vs global scope.
- **P6 Public Product** — mode framework (Student/Dev/Pro/Creator) · onboarding wizard · installer/packaging ·
  public docs/demos · **multi-tenant decision**.

---

# PHASE 10 — Periphery & Longevity (M3) · the critic's blind spots

At-rest encryption for memory/audit SQLite · **daemon self-upgrade/rollback** (the OS updating its own
runtime safely) · consolidated threat-model doc · operator data export + "forget everything" · fix
Grafana default admin/admin · make/withdraw the untested cross-platform claim · dependency
license-compat audit · incident-response runbook (`docs/OPERATIONS.md` + real `SECURITY.md`).

---

## Sequencing rationale

1. **Phase 0 buys integrity cheaply** — do it first; it is days and makes the thesis true.
2. **Phase 1 is the real hidden work** — the vision assumed guardrails that do not exist; nothing
   autonomous is safe until these land. Sign-off each.
3. **2 → 3 → (4, 8)** builds and proves the sovereign loop on ai-editor with eyes on it and torture behind it.
4. **5-7, 9-10** are the M3 long horizon — real months, real XL items — sequenced after the brain can
   safely improve itself.

## Honest sizing

163 items: **58 S · 65 M · 25 L · 6 XL** (+ periphery). **M1 = weeks. M2 = a few months. M3 = a long
horizon** (P4/P6 are multi-XL). This is a program, not a session. The right next move is Phase 0 —
small, high-integrity, and it makes everything downstream honest.

**Start here:** 0.1 (privacy fix, your sign-off) + 0.3 (`/health`) I can begin immediately; 0.2 (honesty
pass) is a fast follow. Say go and I take Phase 0.
