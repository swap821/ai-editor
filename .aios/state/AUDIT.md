# AUDIT.md — Evidence-Based Status of the AI-OS vs. Blueprint v3/v4

> Phase 1 audit (read-only). Authored by Claude Code on **2026-06-03**.
> **Rule applied:** a component is **BUILT** only if its code exists **AND** it has
> tests **AND** I ran those tests and they passed. Comments, docstrings, and
> RESUME.md claims were treated as unverified until confirmed against code + a
> green test. This file supersedes the stale counts in CLAUDE.md ("89") and
> RESUME.md ("94"/"107").

---

## 0. Ground truth — full suite run

```
.venv\Scripts\python -m pytest -q --cov=aios
=> 111 passed, 1 skipped, 1 warning in ~34s
=> TOTAL coverage 83% (1661 stmts, 289 missed)
```

- The **1 skip** is `test_symlink_escape_is_out_of_scope` — skipped on Windows
  because symlink creation needs privilege. Environmental, not a failure.
- The **1 warning** is a Starlette/httpx deprecation in the test client. Cosmetic.
- Per-file coverage (security/memory/agents core): gateway 95%, secret_scanner
  95%, audit_logger 91%, scope_lock 88%, retrieval 87%, reflection 92%, rollback
  88%, executor 89%, planner 88%, confidence 100%, mistake 82%. `llm.py` is 16%
  (pure Ollama HTTP I/O, exercised only live — agents use injected fakes; this is
  expected, not a gap).

### ⚠ Flags found during audit (need your attention before Phase 2/3)
1. **Uncommitted edits to the FROZEN security core.** `aios/security/scope_lock.py`
   and `tests/test_security.py` are modified in the working tree (not committed).
   The change rewrites `command_stays_in_scope` from regex path-fragment scanning
   to `shlex` word-splitting (+4 new scope tests). Tests pass *with* these edits.
   Per CLAUDE.md §VII, security is a frozen core — this change is an improvement
   but it landed without an explicit approve/commit. **Decision needed:** commit
   it, or revert it.
2. **4 untracked CSS files** (`frontend/src/styles/{App,design-system,nexgen-3d,
   nexgen-layout}.css`) — the parked "premium 2026" rewrite. Preserved, unimported.
3. **Stale docs:** CLAUDE.md baseline (89) and RESUME.md (94/107) no longer match
   reality (111). Worth syncing.
4. **Repo hygiene:** `legacy_node/` is the archived Node backend (its `tests/*.js`
   are NOT run by pytest). Loose root scripts (`hybrid_search.py`, `ingest_*.py`,
   `vector_memory_setup.py`, `pdf_util.py`, `reset_audit_chain.py`, `memory.db`,
   `vector_index.faiss`, `chat-ui.html`) are pre-`aios/` artifacts, untested and
   not part of the package. Not blueprint components; candidates for an `archive/`.

---

## 1. Module structure → blueprint component map

```
aios/
  config.py                 single source of truth (paths, weights, thresholds)   [Core API contract §6.3 tunables]
  core/
    llm.py                  Ollama HTTP client (complete/chat/stream/list)         [LLM routing, P0]
    bedrock.py              AWS Bedrock Converse client (opt-in cloud)             [NOT in blueprint — extra]
    planner.py              CoT goal->task-tree + confidence gate                  [Stage 2 Planner]
    confidence_filter.py    0.72 escalation gate                                   [Stage 3 Confidence Filter]
    executor.py             gateway-guarded, scope-locked, audited subprocess      [Stage 7 Executor]
  memory/
    db.py / schema.sql      SQLite bootstrap (WAL, FK), L2/L3/L4 DDL               [§4.1 storage]
    working.py              L1 RAM dict, session-scoped                            [L1 Working]
    episodic.py             L2 chronological turns                                 [L2 Episodic]
    semantic.py             L3 text chunks + FAISS sync                            [L3 Semantic]
    mistake.py              L4 mistake pool + lifecycle                            [L4 Mistake / §6.1]
    embeddings.py           MiniLM encoder + FAISS HNSW IndexIDMap                 [Vector index]
    retrieval.py            R = .25·BM25 + .45·FAISS + .30·e^(-.05Δt)              [§4.2 hybrid+decay]
  security/
    gateway.py              deterministic 3-zone, fail-closed, rate limiter        [Stage 5 / §5.1]
    scope_lock.py           path canonicalization + scope roots                    [§5.2 scope locking]
    secret_scanner.py       regex + Shannon-entropy redaction                      [§5.2 secret scanner]
    audit_logger.py         SHA-256 hash chain, O(n) verify, redact-before-store   [Stage 10 / §6.2]
  agents/
    reflection_agent.py     LLM post-mortem -> L4, pending->verified              [Stage 9 Reflection]
    rollback_engine.py      GitPython snapshot/restore, refuses project root       [Stage 11 Rollback]
    tool_agent.py           bounded reason->act->observe loop, in-chat approval    [orchestration / Stage 6]
  api/main.py               FastAPI: 8 v1 contracts + /generate + /terminal        [§6.3 API contracts]
frontend/                   React/Vite UI (chat, code canvas, live preview, 3D)    [P0 UI: preview/edit/approve]
```

---

## 2. Component status table

| Component (blueprint) | Status | Evidence (files) | Tests pass? | Gap to close |
|---|---|---|---|---|
| **Security Gateway** — 3-zone, deterministic, fail-closed, rate limit | **BUILT** | `security/gateway.py` | ✅ 27 in `test_security.py` incl. fail-closed-on-exception, rate limit, determinism | None for core. (Vector-blocklist injection layer is separate row below.) |
| **Scope Locking** — path canonicalization, traversal/symlink defense | **BUILT** | `security/scope_lock.py` | ✅ (abs/relative/embedded-traversal; symlink skipped on Win) | Commit the uncommitted rewrite; add a privileged-CI symlink run. |
| **Secret Scanner** — regex + entropy, redact w/ fingerprint | **BUILT** | `security/secret_scanner.py` | ✅ AWS/entropy/plain-english cases | None. |
| **Audit Logger** — SHA-256 chain, tamper-evident, redact-before-store | **BUILT** | `security/audit_logger.py` | ✅ 6 in `test_audit.py` incl. tamper-breaks-chain, genesis, redaction | None. (Startup-verify hook is an enhancement.) |
| **L1 Working Memory** — RAM dict, session TTL | **BUILT** | `memory/working.py` | ✅ isolation test | None. |
| **L2 Episodic Memory** — SQLite chronological | **BUILT** | `memory/episodic.py`, `schema.sql` | ✅ chronological-order test | None. |
| **L3 Semantic Memory** — durable chunks + FAISS | **PARTIAL** | `memory/semantic.py` | ✅ add+search test | Stores **text chunks**, not entity-relation triples (§4.1); no preference/entity schema. |
| **L4 Mistake Pool** — structured post-mortems + lifecycle | **BUILT** | `memory/mistake.py`, `schema.sql` | ✅ clamp + pending/verified/superseded + recurrence | None. Schema matches §6.1. |
| **Vector Index (FAISS HNSW)** — 384-dim, IDMap | **BUILT** | `memory/embeddings.py` | ✅ via semantic/retrieval tests | None. |
| **Hybrid Retrieval + Decay** — BM25+FAISS+e^(−λΔt) | **BUILT** | `memory/retrieval.py` | ✅ ranking + recency-decay + empty-index | None. Formula + weights match §4.2. |
| **Contradiction Detection** (§4.3) — conflict check before L3 write | **MISSING** | — | — | No entity parse, no conflict query, no reconciliation route. |
| **Planner** — CoT decomposition + confidence | **BUILT** | `core/planner.py` | ✅ 7 incl. malformed-JSON, clamp, partition | None. |
| **Confidence Filter** — 0.72 gate | **BUILT** | `core/confidence_filter.py` | ✅ boundary (0.719→escalate, 0.72→pass) | None. 100% cov. |
| **Executor** — sandboxed, scope-locked, audited | **BUILT** | `core/executor.py` | ✅ 7 incl. RED-blocked, YELLOW-not-run, env-strip, every-outcome-audited | Sandbox = cwd+env-strip+timeout; **no OS chroot/cgroup** (§3.2 "subprocess+chroot"). Acceptable local-first, note it. |
| **Approval Engine** — human-in-loop, resumable YELLOW | **BUILT** | `tool_agent.py`, `api/main.py` (`/approval/req`, `/generate`) | ✅ pauses-on-YELLOW, runs-approved, refuses-RED | RED is **hard-blocked**, not typed-token-confirmed as §5.1 specifies (safer deviation — confirm intended). |
| **Reflection Agent** — post-mortem -> L4 | **BUILT** | `agents/reflection_agent.py` | ✅ 8 incl. malformed-reject, clamp, recurrence, confirm | None. |
| **Rollback Engine** — git snapshot/restore | **BUILT** | `agents/rollback_engine.py` | ✅ 5 incl. restore-state, refuse-project-root, clean-untracked | None. |
| **Verifier Layer** (Stage 8) — pytest/jest assertions + delta | **PARTIAL** | `tool_agent._format_exec_result` (exit-code only) | ✅ (indirect) | No dedicated verifier component/endpoint; no test-assertion run or delta computation on agent executions. |
| **API Contracts (8 endpoints §6.3)** | **BUILT** | `api/main.py` | ✅ classify/memory/audit/reflect/generate/terminal directly; plan/execute/approval/rollback via unit tests | Add **direct HTTP tests** for `/plan`, `/execute`, `/approval/req`, `/rollback` (logic is tested; routes are thin but unasserted). Path is `/approval/req` vs blueprint `/approval/request`. |
| **Prompt-Injection Shield** — regex **+ vector blocklist** | **PARTIAL** | `gateway.py` (`_INJECTION_PATTERNS`) | ✅ regex cases | Regex layer only; **no embedding/vector blocklist** (§5.2). |
| **LLM Code Generation** — multi-model routing | **BUILT** | `core/llm.py`, `core/bedrock.py`, `/generate` | ✅ streams text+code+done | None for backend. |
| **Terminal Interaction** — gated sandbox | **BUILT** | `api/main.py` `/api/terminal` | ✅ green-runs, red-blocked | None. |
| **File Modification — diff preview, git-aware** (P0) | **PARTIAL/MISSING** | only via `execute_terminal` (shell write, YELLOW) | partial | **No write_file tool, no interactive diff preview** — the signature demo moment (0:30) is not built as specified. |
| **Live Preview Environment** (P0) | **PARTIAL** | `frontend/src/components/LivePreview.jsx` | ❌ no automated tests | Frontend has **zero** test suite; cannot be called BUILT. |
| **Frontend UI** (chat, approval bar, model picker, 3D) | **PARTIAL** | `frontend/src/**` | ❌ no tests; recently broke + was stabilized | Add a minimal frontend test/build-smoke; verify the live e2e path. |
| **AWS Bedrock cloud provider** (extra, not in blueprint) | **BUILT** | `core/bedrock.py` | ✅ 10 in `test_bedrock.py` | None. Opt-in; off unless region set. |
| **Voice Interface** (Whisper/Piper, P2) | **MISSING** | — | — | Out of MVP scope (P2). |
| **Project Knowledge Graph** (Neo4j, P3) | **MISSING** | — | — | Out of MVP scope (P3). |
| **Deployment/Observability** (Docker, Prometheus, OTel) | **MISSING** | — | — | Out of MVP scope. |
| **Test tiers** — integration/e2e/security-automation/chaos/perf | **PARTIAL** | `tests/` (unit + light integration) | ✅ what exists | Strong unit + some integration; no e2e/Playwright, no chaos/perf, no automated adversarial suite. |

---

## 3. Prioritized gap list (P0 → P3)

**P0 — blocks an honest, demoable MVP**
1. **File-edit with diff preview** (write tool + UI diff). The blueprint's headline
   demo (0:30 YELLOW source-edit with diff) currently shows a *command*, not a
   *diff*. Highest-value missing capability.
2. **Frontend has no tests + unverified e2e.** Add a build-smoke + the live
   happy-path walk (chat → YELLOW → approve → run → reflect). It broke once already.
3. **Direct HTTP tests for `/plan`, `/execute`, `/approval/req`, `/rollback`.**
   Logic is tested; the contract layer is not asserted end-to-end.

**P1 — core fidelity to the blueprint**
4. **Verifier stage** as a real component: run pytest/jest assertions on an agent
   execution, compute pass/fail delta, feed the Reflection loop on failure.
5. **Prompt-injection vector blocklist** to complement the regex layer (§5.2).
6. **L3 semantic = entity/preference facts** (not just chat-turn text), enabling…
7. **Contradiction detection** before L3 commit (§4.3).
8. **Decide RED policy:** keep hard-block (current, safer) vs. blueprint's typed-token
   confirm — and write the choice down.

**P2 — deferred capability**
9. Offline voice (Whisper + Piper).
10. Audit-verify-on-startup hook + chain-integrity alert.

**P3 — scope only after core is green**
11. Project knowledge graph (Neo4j).
12. Docker Compose + Prometheus/Grafana/OpenTelemetry.
13. Chaos + performance + automated adversarial (MITRE ATLAS) test tiers.

---

## 4. Honest completion estimate

**Backend P0–P1 core: ≈ 80% built and verified.** **Whole demoable MVP: ≈ 62%.**

- *Justification (backend):* the security/memory/audit/reflection/rollback/planner/
  executor/agentic-loop backbone is implemented to spec **and** covered by 111
  passing tests that assert the real invariants (tamper-evidence, fail-closed,
  scope escape, confidence boundary, lesson lifecycle, rollback restore). This is
  genuinely well past the blueprint's own "40–50%" framing for these modules.
- *Justification (whole MVP):* the user-facing demo path drags the real number
  down — the signature diff-preview edit isn't built, the frontend has no tests and
  was recently broken/stabilized, there's no Verifier stage, and the prompt-injection
  vector layer is absent. These gate "demoable," not just "coded."

This is **not** 100% and must not be reported as such. It is a strong, test-backed
backend with a thin/unverified front edge and three or four real P0–P1 gaps.

---

_Phase 1 complete. STOPPING here for operator review per the agreed protocol.
Phase 2 (week-by-week PLAN.md) begins only on your approval of this audit._
