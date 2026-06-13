# AI-OS — System True Picture (whole-repository deep read, 2026-06-13)

> ⚠️ **SUPERSEDED SNAPSHOT (dated 2026-06-13) — body unchanged, kept as a record.** Since this read,
> the **multi-LLM library** (cross-provider router + Gemini/Bedrock + hybrid local-LLM pick + evidence
> calibration) and the **active-brain UI badge** shipped; the suite is now **516 passed / 1 skipped**.
> This doc's 512/457/458 counts and "doc-drift" notes predate that — current state is `RESUME.md` C0.

> **What this document is.** This is the canonical, whole-system architecture map a future builder should read first. It *extends* `BACKEND_TRUE_PICTURE.md` (2026-06-13), which remains the authoritative read of the Python core (security spine, cognition loop, agent layer, memory, learning, RAG/coordination). This document adds the **frontend** (the 3D "superbrain" lab + the product/classic UIs), the **root tooling/drivers**, the **test suite**, the **config/infra/deploy** surface, the **docs-currency** state — and, most importantly, **how it all composes end to end**: a single request from the UI, down through SSE → cognition → memory → security → earned-autonomy/swarm → audit chain, and back up into the UI as a live stream of events.
>
> It is written for a builder who already trusts that the backend is real (it is — 90% line coverage, 512 passing tests across three suites) and now needs the *map of the whole machine* plus an honest **real-vs-aspirational** ledger.

---

## 1. One-paragraph thesis

The ai-editor is a **supervised, memory-driven, local-first AI operating system** built around a single load-bearing invariant — **"trust the evidence, not the model"** — carried without compromise through every layer. A weak local LLM (Ollama, 7–8B) *proposes*; deterministic, tested, SQLite-backed machinery *decides*. The backend is a real cognitive loop sandwiched between two layers it cannot bypass (an advisory alignment/router layer above, a fail-closed security spine + audit chain below). The frontend is two UIs over that one backend: a **3D react-three-fiber "superbrain"** (the default, operator-chosen face) that renders the live supervised mind as an organism voyaging through knowledge space, and a **classic Vite/React IDE-chat shell** (behind `?ui=classic`). The same discipline that governs the backend governs the frontend: **no decorative lies** — when the link is down or there is no data, the experience goes honestly dormant rather than faking activity. This is a genuine ~2-week+ system: neither an MVP toy nor flawless. Its frontier is deliberate (tiny autonomous surface, opt-in OS isolation, a 7B model ceiling), not accidental.

---

## 2. Top-level component map

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ OPERATOR (single supervised developer, his own machine)                        │
└──────────────────────────────────────────────────────────────────────────────┘
        │ types a turn in the command bar / clicks AUTHORIZE / REJECT
        ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ FRONTEND  (one mount switch: frontend/src/main.jsx:10-22)                       │
│                                                                                │
│  DEFAULT ── SUPERBRAIN (3D r3f) ──────────┐     CLASSIC ── ?ui=classic ───────┐│
│  lab canon: GAG demo/gag-orchestrator     │     frontend/src/App.jsx (IDE/chat)││
│  ported byte-faithfully into              │     SSE via frontend/src/lib/sse.js ││
│  frontend/src/superbrain via `npm run port`│    + config.js (token-aware)      ││
│                                            │                                    ││
│   cognitionBus (pub/sub spine)             │                                    ││
│   ├─ SuperbrainScene  (3D organism)        │                                    ││
│   ├─ SuperbrainHUD    (DOM-in-canvas)      │                                    ││
│   ├─ MemoryGalaxy     (real trails=stars)  │                                    ││
│   ├─ soundEngine      (synth voice)        │                                    ││
│   ├─ metricsStore     (single source)      │                                    ││
│   └─ aiosAdapter  ◄── THE ONLY BACKEND BOUNDARY ──────────────────────────────┐│
└──────────────────────────────────────────────────────────────────────────────┘│
        │  POST /api/generate (SSE)   +   20s poll: /trails /metrics /audit /autonomy
        ▼                                                                          │
┌──────────────────────────────────────────────────────────────────────────────┐ │
│ HTTP SURFACE  (aios/api/main.py — 31 routes, FastAPI, ~1767 lines)             │ │
│  lifespan: deploy-policy (non-loopback ⇒ ≥32-char token), DB init, backend     │ │
│  validate, optional vector shield │ CORS + Bearer middleware │ DI for providers │ │
│  /api/generate ─ event_stream() ─ emits SSE frames ──────────────────────────►─┘ │
│  step│text_chunk│code│earned_autonomy│human_required│error│done                  │
└──────────────────────────────────────────────────────────────────────────────┘
        │  composes the turn (DI)
        ▼
┌───────────────────────────── BACKEND CORE (aios/) ──────────────────────────────┐
│  ABOVE (advisory):  AlignmentInterpreter → model_selector (auto/ollama/bedrock)  │
│                                                                                  │
│  MIDDLE (cognition): ToolAgent reason→act→observe loop  (DEFAULT_MAX_ITERS=5)    │
│    9 tools: read_file read_directory execute_terminal edit_file create_file      │
│             verify plan self_analyze propose_fixes                                │
│    optional: WORKER SWARM (run_swarm: decompose→N gated workers→synthesize)       │
│    optional: ROLE-PASS castes (planner→coder→reviewer, verifier-evidence auth)    │
│                                                                                  │
│  BELOW / AROUND (deterministic, fail-closed — the cage):                         │
│    security spine: gateway (3-zone RED-default) → scope_lock → secret_scanner     │
│                    → injection_shield(opt-in) → audit_logger (SHA-256 chain)      │
│    approvals: single-use, session-bound, digest-only capability tokens            │
│    verifier: exit-code-authoritative; _auto_verify force-runs sibling pytest      │
│    executor: shell=False argv, env-secret strip, host OR hardened Docker sandbox  │
│    self_apply: the only writer of aios/ source (human-gated, snapshot→rollback)   │
│    earned_autonomy (off by default): verified-evidence → GREEN bridge, RED-unearnable│
│                                                                                  │
│  MEMORY (multi-store cognitive model):                                           │
│    L1 working (RAM) · L2 episodic · L3 semantic (FAISS+SQLite) · L3b facts        │
│    · L4 mistakes · procedural skill TRAILS (stigmergy) · curriculum · dev-metrics │
│    hybrid retrieval: R = 0.25·BM25 + 0.45·FAISS + 0.30·decay                      │
└──────────────────────────────────────────────────────────────────────────────┘
        │  every security decision + self-apply intent
        ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ AUDIT LEDGER  aios_audit.db  (SHA-256 hash-chain, genesis=64 zeros, O(n) verify)│
│   redact-before-hash · cross-process BEGIN IMMEDIATE · distinct earned-autonomy │
│   entry · surfaced back to UI via GET /api/v1/audit/verify (TAMPER alarm)        │
└──────────────────────────────────────────────────────────────────────────────┘

  OUT-OF-BAND (operator control plane, NOT in the request path):
   agent_coord.py (Claude+Codex single-writer lease + hash-pinned review)
   curriculum_evidence_driver.py / swarm_demo.py / earn_demo.py (live evidence drivers,
     hard fail-closed allowlist: training_ground/*.py writes + pytest only)

  DEAD / SUPERSEDED (in tree, off the product path):
   legacy_node/ (19 files — complete Node prototype), root RAG scripts
   (hybrid_search.py, ingest_*.py, vector_memory_setup.py) keyed to orchestrator_memory.sqlite
```

**Tracked surface (262 files):** `frontend/` (76), `aios/` (46 — the live Python core), `tests/` (40), `training_ground/` (29 — the agent's writable sandbox), `legacy_node/` (19 — dead prototype), `.aios/` (19 — tracked Claude Code continuity brain).

---

## 3. The end-to-end composition (how one turn actually flows)

This is the spine of the whole system and the part no single-subsystem read captures. A turn is a **bidirectional stream**: a request descends through the cage, and a narrated event stream rises back into the organism.

### 3.1 The request, descending

1. **UI → adapter.** The operator types in the superbrain command bar. `aiosAdapter.streamTurn` (`GAG demo/gag-orchestrator/src/lib/aiosAdapter.ts`, ported into `frontend/src/superbrain/lib/`) POSTs to **`/api/generate`** with the prompt, any `approval_tokens`, `approved_commands/edits/creations`, and optional `swarm:true`. It is the **single backend boundary** — every other frontend module talks only to the cognition bus, never to HTTP.
2. **HTTP policy gate.** `main.py` lifespan already enforced deploy policy (non-loopback host ⇒ ≥32-char `AIOS_API_TOKEN`, `main.py:89-94`); the auth + CORS middleware (`main.py:120-149`) gates the call (loopback-only by default, constant-time token compare when set).
3. **Turn composition.** `/api/generate` (`main.py:1291`) builds the turn via DI: `AlignmentInterpreter` frames it (advisory, redacted, **non-authoritative**) → `model_selector` routes (`auto` ⇒ best installed tool-capable local model; `ollama.x` ⇒ local; any other id ⇒ Bedrock-or-503) → constructs the `ToolAgent` with planner/self-analysis LLMs, executor, approved-runner, reflection hook.
4. **The cognitive loop runs inside the cage.** `ToolAgent.run` executes reason→act→observe. Every consequential action is funneled through `gateway.classify` (GREEN auto / YELLOW human / RED blocked, **RED by default** for anything not provably safe), `scope_lock` canonicalization (training_ground/ only), and `audit_logger` (logged **before** the bytes touch disk). Reads are secret-scrubbed before the model sees them. After an approved write lands, `_auto_verify` **autonomously** runs the file's sibling pytest and feeds the authoritative PASS/FAIL back into the conversation.
5. **Memory in the loop.** Before the turn, `_recall_memory` injects tiered recall (`VERIFIED TRUSTED MEMORY` vs `UNVERIFIED PRIOR CHAT — use as a lead, never evidence`) plus verified skill trails. After, `record_outcome` writes development + skill + curriculum evidence **keyed strictly off the verifier verdict**.

### 3.2 The events, ascending

`event_stream()` (`main.py:1358`) is a generator that emits typed SSE frames as the loop progresses. The exact frame vocabulary (verified in source) and what each does on screen:

| SSE frame | Emitted when | Backend site | Superbrain reaction |
|---|---|---|---|
| `step` | every tool dispatch / verify verdict | `main.py:1610` | agent-dispatch + region thought-wave; `[VERIFY PASS/FAIL]` → knowledge-acquired / red shadow |
| `text_chunk` | model prose | `main.py:1613` | terminal log stream |
| `code` | code block | `main.py:1615` | code surfacing |
| `earned_autonomy` | a write auto-applied with **no** human pause (class earned it) | `main.py:1618-1623` | `AUTONOMY ⚡N` pill, "AUTONOMOUS ACTION" |
| `human_required` | a YELLOW action pauses the turn | `main.py:1624-1701` | breath freezes amber, ApprovalPanel shows real diff/command; AUTHORIZE replays with token, REJECT POSTs `/api/v1/approval/req` |
| `error` | turn error | `main.py:1616` | honest failure surfacing |
| `done` | turn end | `main.py:1702` | answer persisted (L2), turn consolidated (L3), per-target final verdict computed |

The frontend parses these with `parseSseBuffer` (`frontend/src/lib/sse.js`, 22 lines — carries partial frames across network chunks) in the classic UI, and with the richer `aiosAdapter` in the superbrain (which maps each frame onto `cognitionBus` events). **The approval pause is the product thesis rendered across five subsystems**: on `human_required` the organism's breath freezes mid-inhale, cortex/wires/aura tint amber, the starfield clock dilates to 30%, the camera dollies in, and the sound engine plays an unresolved suspended 2nd — a supervised mind visibly deferring.

### 3.3 The ambient channel (polling, not in the turn)

Separately from turns, `aiosAdapter.pollOnce` runs every 20s: reads `/development/trails` + `/metrics`, samples `/audit/verify` every 5 polls and `/development/autonomy` every poll. This drives the whole HUD from **real data** — link dot, measured latency, verified/candidate counts, intervention rate — and feeds `metricsStore` (the single source of truth shared by HUD intake rows and brain RegionPins). Each real pheromone trail becomes a persistent GPU star in `MemoryGalaxy` (brightness = strength, size = walks, red pulse = quarantine); a `valid:false` from `/audit/verify` flips the shield to **TAMPER** with a sustained tritone alarm. **Honest dormancy is enforced here**: no trails ⇒ no stars; link down ⇒ LINK OFFLINE, not faked activity.

---

## 4. Layer-by-layer

### 4.1 Backend core (aios/) — see BACKEND_TRUE_PICTURE.md for the deep read

Unchanged and authoritative. The five-part summary: **security spine** (frozen core, fail-closed every direction, RED-by-default allowlist, SHA-256 hash-chained audit with redact-before-hash); **cognition loop** (orthogonal security/confidence gates, force-verify-after-write, `_extract_text_tool_calls` recovering 4 real prose shapes through one allowlist, **human approval can never authorize RED**); **agent layer** (9 tools, resumable filepath-keyed approval grants, role-pass castes, self-apply with no agent apply-tool); **memory** (L1–L4 + facts, crash-consistent FAISS via `IndexIDMap`, hybrid `0.25·BM25 + 0.45·FAISS + 0.30·decay`); **learning** (stigmergic skill trails with asymmetric pheromone, held-out-gated curriculum, evidence-only promotion). **Surplus beyond the blueprint** lives here too: earned-autonomy (`aios/core/autonomy.py`), self-analysis T0–T4, swarm, role-pass.

### 4.2 Frontend — the superbrain (default) + classic (`?ui=classic`)

**One mount switch** (`frontend/src/main.jsx:10-22`): the comment confirms the operator's 2026-06-12 decision — the superbrain *is* the official frontend; classic is behind `?ui=classic`; each UI's stack is lazy-loaded.

**The superbrain** is a Next.js 16 + react-three-fiber 3D organism whose canonical source is the **lab** (`GAG demo/gag-orchestrator/`); `npm run port` copies the byte-faithful "live set" into `frontend/src/superbrain/`. Its architecture:
- **`cognitionBus.ts`** — a ~67-line module-singleton pub/sub (NOT zustand; `stores/` is empty). Every layer (scene, HUD, sound, metrics, tier, galaxy) hangs off this one event stream. This is what makes it read as one organism.
- **`aiosAdapter.ts`** — the single backend boundary (680 lines, 13 tests). All SSE frame types + the 20s poll/audit/autonomy cadence + the approval token lifecycle + fault-isolated offline honesty.
- **`SuperbrainScene.tsx`** — the 3D organism (1312-line monolith): per-vertex anatomical region color baking so labeled knowledge lights the *same* lobe every time; ONE shared-uniform object (`SCENE_UNIFORMS`) written once per frame so cortex shader, aura shells, fireflies and wires breathe phase-locked; thought-wave GLSL shared between cortex and fireflies anchored to tool-kind.
- **`SuperbrainHUD.tsx`** — the DOM HUD (1169 lines) rendered **inside** the `<Canvas>` via drei `<Html>`+`createPortal` to `#hud-portal-root`; topbar sovereignty row (FIDELITY · SKY · SURFACE · SOUND, each changed only by the operator's own click), terminal log, intake rows, command bar, approval host.
- **`metricsStore.ts`** (single source of truth, `useSyncExternalStore`), **`MemoryGalaxy.tsx` / `CognitiveGrasp.tsx`** (real trails → deterministic persistent stars + recall glints), **`soundEngine.ts`** (fully synthesized WebAudio voice, no assets, sovereign-silent until the operator's SOUND click, with limiter + OS-interruption recovery), **`PostFX.tsx`** (hand-built AgX + log-space contrast + W3C soft-light split-tone grade co-designed with the bloom ladder).

**Resilience:** webglcontextlost grace window then Canvas remount via `glEpoch`; `WebGLErrorBoundary` fallback; HUD state seeded from the adapter singleton so a GPU-loss remount never drops a pending approval hold; true-boot races the backend for 1.6s and replaces lore with real version/trail facts.

**The classic UI** (`frontend/src/App.jsx`, 1817 lines) is the IDE/chat shell: SSE streaming turns parsed via `frontend/src/lib/sse.js`, diff/proposals panels, alignment panels. It is token-aware (`frontend/src/config.js` wires `VITE_AIOS_API_TOKEN` → Bearer header) — **the superbrain adapter is not** (see §6 deploy gap).

### 4.3 Root tooling + drivers (the operator's control plane, OUT of the request path)

Three families:
- **`agent_coord.py`** — a real, production-grade Claude+Codex coordination control plane: SQLite over `.aios/state/coordination.db`, single-writer "worktree" lease with TTL+heartbeat (atomic compare-and-swap under `BEGIN IMMEDIATE`), 50/50 builder routing, and **SHA-256 hash-pinned review handoffs** — `tree_snapshot` hashes HEAD + binary tracked diff + sorted untracked file bytes, so `record_verdict` fail-closes if the tree changed after handoff and forbids a builder approving their own work. Wired into AGENTS.md III-A and `.vscode/tasks.json`. (~95% complete for its CLI role.) Honest limit: it is a *passive* disk lock + ledger — identity is honor-system, enforcement is cooperative.
- **Live HTTP evidence drivers** — `curriculum_evidence_driver.py` (streams `/api/generate` SSE, replays through approvals, classifies by FINAL `[VERIFY PASS/FAIL]`, appends verbatim evidence to `.aios/audit/curriculum-evidence-run.jsonl`) plus `swarm_demo.py` and `earn_demo.py`, which **import** the driver's vetted allowlist helpers verbatim (single-sourced, not copy-pasted). The allowlist is adversarially tight: `^…$`-anchored `training_ground/*.py` writes + `pytest` on a single such file only — no pip, no shell, no traversal — and `reject_and_abort` `sys.exit`s on the first violation, even re-running the allowlist on its own deletion targets.
- **LEGACY/dead** — `hybrid_search.py`, `ingest_knowledge.py`, `ingest_update.py`, `vector_memory_setup.py`, `reset_audit_chain.py`, `pdf_util.py`, `extract_text.py`. **DB split-brain**: these key off `orchestrator_memory.sqlite` while production uses entirely different DBs (`aios_memory.db`, `aios_audit.db`, `aios_approvals.db` — `aios/config.py:99-103`). They are reachable only from `legacy_node/memoryAgent.js`, superseded by `aios/memory/*`, and `extract_text.py` is dead (its source PDF is gone). `reset_audit_chain.py` is effectively a no-op against the live ledger (it clears the *legacy* table; its `sqlite_sequence` delete matches nothing on the live `entry_id` schema).

### 4.4 Test suite — three independent suites, 512 passing + 1 skipped

| Suite | Files | Tests | Verified result | Runner |
|---|---|---|---|---|
| Backend (`tests/`) | 28 + conftest | 458 collected | **457 passed, 1 skipped** (~60–86s) | pytest |
| Product frontend (`frontend/src`) | 9 `.test.{js,jsx}` | 29 | all pass | vitest + RTL |
| Lab orchestrator (`GAG demo/.../src/test`) | 4 | 26 | all pass | vitest |

**Live-measured 90% line coverage of `aios/`** (5087 stmts, 510 missed; lowest module `memory/semantic.py` at 81%, none below). The dominant pattern is **"real gateway, fake runner"**: fakes are only the non-deterministic edges (LLM chat, shell spawn, embedder); the security/scope/audit/verify machinery runs for real, so tests prove **genuine refusal**, not mocked returns. Negative-path density is unusually high (self_apply: 18 tests, ~15 refusal/rollback; security: ~32 incl. fail-closed-on-exception). Distinctive contracts under test: a `VERIFICATION RED` event provably never plays the 1318.5Hz success tick (`soundEngine.test.ts`); the adapter's honest `LINK OFFLINE`/`rejected (unconfirmed)` degradation is itself tested (`aiosAdapter.test.ts`); a self-validating golden harness proves its drift check is not vacuous.

**Honest caveats:** the "457 passed" project-memory figure is **backend-only and omits the 1 skip** (the symlink-escape security test, `skipif win32` — so that guarantee is **never exercised on the developer's own Windows machine**, only on POSIX CI). The true all-suite total is **512 passing**. There is **no single "run everything" gate** — `pytest` runs only `tests/` and says nothing about the 55 JS/TS tests. No coverage threshold is enforced (no `--cov-fail-under`), so the strong 90% is discipline, not a gate. No test ever exercises a real subprocess, real Docker container, or real Ollama/Bedrock model — the suite proves the **wiring and gating** are correct but cannot catch a regression in actual shell-quoting, container flags, or live SSE byte-framing.

### 4.5 Config + infra + deploy

`aios/config.py` is a flat module of `Final` constants populated by typed env accessors (`AIOS_*` overridable, gitignored root `.env`), with safe fallbacks (bad ints/bools fall back, never crash). Filesystem state lives under one gitignored `DATA_DIR`. The HTTP layer's lifespan enforces deploy policy; the executor (`aios/core/executor.py`) offers host **or** a genuinely hardened Docker backend (`--network none --read-only --cap-drop ALL --user 65534`, noexec tmpfs, env-secret stripping). **~85% complete for a single-laptop target; ~55% for true multi-user/internet deploy** — and that gap is deliberate and documented.

### 4.6 Docs currency

Three tiers. The **`.aios/` live continuity layer** (RESUME, CEO_LOG, EVIDENCE_CURRICULUM, BACKEND_TRUE_PICTURE) is ~95% current and genuinely disciplined (CEO_LOG honestly tracks the test-count climb 116→…→458). The **Tier-1 operating docs** (README/AGENTS/START_HERE/KICKOFF) are ~70% current — structurally correct but ~3 days and two feature waves stale: the **375/1 test baseline is hard-coded into four docs** (now 458), the README never mentions the superbrain (the default UI since 06-12), earned-autonomy, or swarm, and two README.md files are untouched scaffolding templates. `websocket_security_update.md` is fully orphaned (describes a transport the active HTTP+SSE stack does not use).

---

## 5. What is REAL vs ASPIRATIONAL (the honest ledger)

### 5.1 Solidly real and proven (do not re-litigate)

- **The security spine + audit chain.** Fail-closed every direction, RED-by-default, SHA-256 hash-chain with cross-process integrity (proven by a 4×20 concurrent-append test landing one valid 80-entry chain), redact-before-hash. The frozen core that earns the name.
- **The cognition loop end-to-end.** Wired in `main.py` (not test-only), force-verify-after-write, exit-code-authoritative verdicts, orthogonal security/confidence gates, **RED un-grantable even after human approval**.
- **The memory + learning layers.** Multi-store cognitive model with DB-enforced invariants (partial unique indexes), crash-consistent FAISS writes, faithful hybrid retrieval, stigmergic skill trails with the exact asymmetric pheromone constants pinned by test. The learning layer is the most mature thing in the repo.
- **Self-application.** The OS patches its own source through a snapshot → `git apply --check` → audit-before-write → single-file-confined apply → independent two-snapshot byte-comparison → gated verify → auto-rollback path, with **no agent apply-tool** (structural no-self-approval).
- **The superbrain frontend as a polished product UI** (~90% for its scope): full cognition bus, adapter (all SSE frames + poll/audit/autonomy), HUD, approval recipe, sound engine, galaxy, sovereignty row, GPU resilience. Bound to **real** backend data with honest dormancy.
- **Earned-autonomy + swarm are wired and shipping** (`main.py:40,433,1581,1618`), tested at both ledger and end-to-end levels, with a distinct earned-autonomy audit-chain entry.
- **The coordination control plane** (hash-pinned review, single-writer lease) and the **live evidence drivers** (which produced a real audited 6/6-mastered curriculum proof over the same HTTP surface the human UI uses).
- **The test discipline itself**: 90% coverage, 512 passing tests, adversarial/negative-path-dominant, "real gateway, fake runner."

### 5.2 Real but deliberately narrow (the designed frontier)

- **The autonomous surface is tiny by design.** In host mode the GREEN auto-execute allowlist is **two patterns** (`echo`, `pwd`). Everything real — pytest, edits, installs, git — is YELLOW and needs a human. Earned-autonomy is the one bridge widening this, and it is **off by default**, double-gated, and **RED-un-earnable**. This is correct for a supervised OS; it means unattended capability is near-zero unless explicitly opened.
- **Strong OS isolation is opt-in, not default.** The hardened `DockerRunner` is real; the default `host` backend is candidly **not** an OS isolation boundary. The strongest boundary depends on Docker being present.
- **The model is the ceiling.** Planning is advisory, calibration is a no-op on a cold DB, castes are "architecture proven / 7B-limited," and curriculum matching is exact-prompt-string (live-proven via a controlled run, narrow for organic chat). The mechanism layer is built to receive a better brain.
- **Recall has two named lexical seams** (skill/lesson/curriculum recall is lexical despite a full semantic FAISS stack sitting right there; BM25 runs only over the FAISS candidate pool) and **the growth stores have no forgetting** (episodic append-only, semantic only superseded — monotonic growth on a long-running install).

### 5.3 Aspirational, stale, or genuinely absent (do not mistake for built)

- **VOICE = 0%.** Blueprint §4.2/§12 specify Whisper STT + Piper TTS; there is no STT/TTS/audio dependency anywhere in `aios/` or `requirements.txt`. The single biggest blueprint-vs-reality gap (correctly deferred). *(The superbrain's `soundEngine` is synthesized UI sonification — not voice I/O.)*
- **Full knowledge graph (Neo4j + multi-hop) = not built.** Product reality is a flat SQLite triple store with contradiction detection (`aios/memory/facts.py`) — intent met, backend honestly downscoped. A 1-hop graph exists only in the dead `legacy_node/knowledgeGraph.js`, which a careless `grep "knowledge graph"` would surface misleadingly.
- **Observability (Prometheus + Grafana + docker-compose) = not built.** Blueprint §10 specifies an 8-service Compose topology; reality has only `Dockerfile.executor` (the sandbox image — **not** an app/server image) and an internal JSON `/api/v1/development/metrics`. The alert-rule tables are documentation-only.
- **No app-level deployment artifact / uvicorn entrypoint.** The server is a hand-typed `python -m uvicorn aios.api.main:app` one-liner; there is **no** `if __name__=="__main__"`, no docker-compose, no Procfile, no TLS/reverse-proxy sample. `AIOS_API_HOST/PORT` are read by the policy check but do not bind the server unless mirrored on the CLI.
- **The PROJECT.md/lab roadmap is stale** (marks "runtime integration" as Planned though `aiosAdapter` fully implements it; lists files that do not exist). The Tier-1 docs froze at the 375-test baseline. The blueprint *itself* deliberately understates ("~45% implemented") and the reality has moved far past even its own §00 reconciliation.
- **No automated tests for any 3D/R3F component, HUD, ApprovalPanel, MemoryGalaxy, or shader logic** — the scene's correctness rests on 37 golden PNGs + 15 puppeteer probes a human must eyeball. A regression in wave anchoring or hold choreography would not fail CI.

### 5.4 Security/hygiene findings a future builder must action

- **🔴 Live Bedrock credential on disk.** `frontend/.env` contains a real, currently-valid AWS Bedrock bearer token (`ABSK…`) **plus** shell launch commands. It is gitignored and verified **never in git history** (no leak via the repo), but it is a live secret in the wrong place (a frontend dir; Bedrock is backend-only) misnamed as a dotenv. **Rotate and relocate to the backend env.**
- **Deploy auth gap in the default UI.** The superbrain `aiosAdapter` sends **no** Authorization header (only the classic `config.js` wires a Bearer token). A token-protected / non-loopback deploy of the default UI would get 401s on every call.
- **CORS with `allow_credentials=True` + wildcard methods/headers** is fine for the loopback defaults, but there is no validation that an operator-added `AIOS_CORS_ORIGINS` entry isn't `*` — credentialed cross-origin access could widen silently.
- **Audit chain has no external anchoring.** A local hash chain without an out-of-band root of trust: an attacker with full write access can recompute a self-consistent forgery. Inherent to the single-laptop threat model; periodic off-box notarization of the head hash is the fix the moment this system matters enough to attack.

### 5.5 Tracked debt to clean (misleads future readers, not broken)

- `legacy_node/` (19 files — complete dead Node prototype of the *entire* system; referenced by nothing live).
- Root RAG scripts (DB split-brain, off the product path) + dead `extract_text.py`.
- Tracked cruft: `success.txt` ("OS Online"), `creator.txt` (0 bytes), `chat-ui.html` (stale "Jarvis" demo), `websocket_security_update.md` (orphaned).
- Two untracked 50-byte `assert True` stubs in `training_ground/` (`test_auto_grant.py`, `test_autonomy_live.py`) — earn/auto-grant demo residue, NOT real tests, and NOT collected by `pytest` (testpaths=tests).
- Monolith files: `aios/api/main.py` (1767), `aios/agents/tool_agent.py` (1528), `SuperbrainScene.tsx` (1312), `App.jsx` (1817), `superbrain.css` (1825); `constants.ts` carries ~120 lines of dead `LAYOUT_CONFIGS` from a prior panel-based design the scene never reads.
- The ~1.3MB lazy `SuperbrainApp` JS chunk (three.js + r3f stack) is dwarfed by **~4.5MB of brain PNG textures** — the real download weight is textures, not JS.

---

## 6. Bottom line for the next builder

You have a **real, coherent, internally-consistent supervised AI-OS** whose defining quality is **intellectual honesty enforced as code** — it refuses to let an LLM's word stand anywhere it matters, it tells the truth about its own weaker modes in docstrings, and that same discipline now extends to the frontend, which goes honestly dormant rather than faking a living mind. The deterministic foundation (security spine, audit chain, approvals, scope-lock, verifier, self-apply, the memory state machines) is genuinely solid and proven at the level of its contracts; the superbrain is a polished, real-data-bound product face for it.

The frontier is not about fixing what's broken — it's three deliberate moves the system is *built to receive*: **earned autonomy** (widen the gated evidence→GREEN bridge), **a better brain** (clear the 7B/RAM ceiling and close the semantic-recall + forgetting gaps that come with running longer), and **default-strong isolation** (make the container boundary the norm). The immediate hygiene actions are smaller and concrete: **rotate the `frontend/.env` Bedrock token**, plumb auth into the superbrain adapter before any non-loopback deploy, add a single "run everything" test gate across the three suites, and refresh the Tier-1 docs (test count, superbrain default, autonomy, swarm) to point at the `.aios/state/*_TRUE_PICTURE.md` pair as the architecture source of truth.

The hard, unglamorous part — the part most people never finish — is the part already built.

---

*Synthesis of 8 whole-repo lens reads (superbrain frontend, classic frontend, root tooling, test suite, docs currency, config/infra/deploy, cross-cutting audit, blueprint-vs-reality) folded over the 6-subsystem `BACKEND_TRUE_PICTURE.md`. Composition path, SSE frame vocabulary, mount switch, and autonomy/swarm wiring re-verified against source (`aios/api/main.py`, `frontend/src/main.jsx`, `frontend/src/lib/sse.js`). 2026-06-13.*
