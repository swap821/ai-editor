# PLAN.md — Blueprint-vs-Reality & The Real Forward Roadmap

> **2026-06-27 Council Runtime supersession:** for near-term build order, the
> operator has elevated
> [`docs/superpowers/specs/2026-06-27-sovereign-ai-os-roadmap.md`](../../docs/superpowers/specs/2026-06-27-sovereign-ai-os-roadmap.md)
> as the canonical roadmap. This older plan remains the blueprint-vs-reality
> and system-context map, but execution now follows the sovereign Council
> Runtime sequence: Phase 0 foundation lock, 30-day First Heartbeat, then the
> 24-week path to v1.0.
> **Status 2026-06-27:** Phase 0, Phase 1A, Phase 1B, Phase 2, and
> Dashboard-lite (KingReport API/panel plus approve/reject decision artifacts)
> are implemented on `council-runtime-v01`; trust `RESUME.md` for current gates
> and the next single action.

> **Full refresh authored by Claude Code on 2026-06-14**, restructuring the prior
> 2026-06-13 refresh. Before the 2026-06-27 Council Runtime supersession above,
> this was the **single source of truth for "what is next."**
> Grounded in the 2026-06-14 whole-repository deep read (8 lenses) + the 2026-06-13
> backend deep read (`.aios/state/BACKEND_TRUE_PICTURE.md`, 8-agent), and verified
> live this session against code on the **`feat/jarvis-voice`** branch (the currently
> checked-out working tree, which contains everything below).
>
> **Test baseline:** trust the live run (`pytest -q` / `npm test`) for current
> pass/skip/fail counts — the hardcoded numbers below are from 2026-06-14 and have
> since moved. As of 2026-06-25 the backend counts **654 passed / 1 skipped** and the
> product frontend counts **326 passed**.
>
> Grep-confirmed absences in the product path: **voice/STT/TTS
> libraries, Neo4j, Prometheus/Grafana** (the only matches are docs + cosmetic HUD
> strings, not dependencies in `aios/` or `requirements.txt`).
>
> **Branch state (neither feature branch merged to master):**
> - `feat/jarvis-voice` *(checked out)* — backend Jarvis voice mind, Slice 1:
>   `POST /api/v1/chat` (Hinglish + personalization, reuses router+memory+facts, no
>   tools), shipped with `tests/test_chat.py`. This branch carries the whole picture.
> - `feat/frontend-renovation` — the 2D HUD made honest + premium-polished + spring
>   physics; dead/duplicate chrome removed; the official mount is now the clean root
>   `:5173` = the integration **Shell** (home↔workbench in one URL).
> - `master` — predates both feature waves.

---

## 0. Where we actually are (one paragraph)

This is a real, ~2-week-plus supervised local-first AI-OS — neither an MVP toy nor
flawless. The deterministic backbone (security spine, hash-chained audit, scope-lock,
approval capabilities, verifier, self-apply, multi-store memory, stigmergic skill
trails, cross-provider router) is **solidly built, end-to-end wired in
`aios/api/main.py`, and proven by behavior-level tests** that drive the *real*
gateway/verifier/DB rather than mocking them. On top of the blueprint the system has
shipped **substantial surplus** the blueprint never asked for — earned autonomy,
self-analysis T0–T4, worker swarm, role-pass castes, curriculum/brain-growth, a
multi-LLM hybrid router, a marquee 3D "superbrain" frontend, a renovated honest 2D
HUD, and now a backend **Hinglish conversational mind** (`/api/v1/chat`, Jarvis voice
Slice 1). The genuine blueprint gaps are narrow and known: **voice I/O (STT/TTS) not
yet built, no Neo4j knowledge graph, no observability stack**, plus a set of
"surplus-maturation" edges (model ceiling, deployment hardening, doc currency,
test/coverage gates, frontend test-darkness). The **frozen-canon rule has been
lifted** by the operator — the 3D brain + space are now modifiable, but **cherished:
enhance, never replace** (FIDELITY-IS-SACRED still governs *how*).

---

## PART 1 — Blueprint-vs-Reality (Phases 1–5)

Spec under test: `AI_OS_Blueprint_APlus_v6` (`blueprint_text.md`, 5-phase roadmap §18
lines 1287–1313) + companion `aiosv6_assessment_text.md` (the §6 design source for the
shipped self-analysis surplus). The blueprint **deliberately understates itself**
(`blueprint_text.md:149–152` says "~45% implemented, do not claim fully built") and
its own inline §00 audit-reconciliation banner (`blueprint_text.md:154–177`) already
flips rows to BUILT. **Reality is the inverse of the headline: the backend core
*exceeds* the spec; the only real gaps are voice, full knowledge-graph, and
observability.**

### Phase table

| Phase | Blueprint scope | Status | Evidence / what's real | What's missing |
|---|---|---|---|---|
| **1 — Foundation** | LLM gen, executor, approval flow, file edit | **✅ 100%** | `aios/core/executor.py`, `aios/agents/tool_agent.py`; bounded reason→act→observe loop, structured-argv `shell=False`, scope-locked cwd, YELLOW human gate. Blueprint §00-banner's "no file-edit diff preview" gap is **CLOSED**: `frontend/src/components/DiffView.jsx` (wired `App.jsx:1413`, `DiffView.test.jsx`) | — |
| **2 — Memory + Reflection** | L2/L3/L4 stores, reflection, hybrid retrieval, mistake_pool, hash-chain audit | **✅ 100% (test-backed; exceeds blueprint §00's pessimistic ~35%)** | `aios/memory/retrieval.py:5–10` implements `R=α·BM25+β·FAISS+γ·decay` with exact weights `0.25/0.45/0.30/0.05` from `config.py:124–130`, real Okapi BM25 (`rank_bm25`), exact cosine, UTC decay; per-layer stores (`working/episodic/semantic/facts/mistake.py`); SHA-256 hash-chain (`audit_logger.py`) matches §7.2, *hardened beyond it* (redact-before-hash, cross-process `BEGIN IMMEDIATE`, 4×20 concurrent-append → one valid chain) | — |
| **3 — Intelligence** | Confidence scoring, auto-verify, vector memory, **knowledge graph** | **~85%** | Confidence filter (0.72 threshold, `config.py:194`), `_auto_verify` force-verify-after-write, FAISS `IndexIDMap` semantic memory — all built + tested. Contradiction flow (§5.3) faithfully implemented in `facts.py:39–106` | **Full Neo4j knowledge graph + multi-hop traversal NOT built** (Gap 2). Product ships `facts.py` flat-SQLite `(subject,predicate,object)` triples *with contradiction detection*; intent met, but **no traversal beyond `facts_for(subject)` (`facts.py:145`)**, no recursive CTE, no Neo4j |
| **4 — Security & Voice** | Gateway + scope_lock + secret_scan + audit, rollback, injection shield, **voice (Whisper/Piper)** | **~78%** (security 100%; voice = backend Slice-1 chat only, no audio I/O) | Security spine **100%** (53 tests, fail-closed proven), `rollback_engine.py`, opt-in vector `injection_shield.py`. **NEW: voice Slice 1 SHIPPED** — `POST /api/v1/chat` (`main.py:2138`), a single-shot Hinglish "voice mind" reusing the router + privacy gate + operator-facts + recalled memory, fake-streams `route→text_chunk→done`, persists to L2/L3; `tests/test_chat.py` (6 tests) | **Actual VOICE (STT/TTS audio) = 0%.** Grep-confirmed: no whisper/piper/pyaudio/sounddevice in `aios/` or `requirements.txt`. The shipped endpoint is **CHAT TEXT only**; the branch name "jarvis-voice" overstates (Gap 1) |
| **5 — MVP & Showcase** | Vite frontend + the 8 REST contracts; **observability (Prometheus/Grafana/compose)** | **MVP RUNNING; observability absent** | All 8 blueprint REST endpoints live at exact paths (`plan:899`, `memory/search:560`, `security/classify:855`, `approval/req:932`, `execute:910`, `reflect:873`, `audit/verify:866`, `rollback:972`); running API exposes ~35 routes (≈4× blueprint). **Two frontends + the renovated integration Shell at root `:5173`** (default = 3D superbrain; `?ui=classic` = IDE) | **No Prometheus/Grafana/docker-compose** (grep-confirmed). Only `Dockerfile.executor` (sandbox image) + internal JSON `/api/v1/development/metrics:740`, not a scrape surface. **No app-level deploy artifact / `uvicorn.run` entrypoint** (`AIOS_API_HOST/PORT` are read but never bind). **No CI** (`.github/` absent) |

### Contract fidelity

The blueprint specifies **8 REST endpoints** (`blueprint_text.md:481–521`); the running
API has **~35**. All 8 originals are present at the exact blueprint paths — contract
honored — but the surface is ~4× larger, most growth in `/api/v1/development/*`
(autonomy, skills, trails, curriculum, workspace) the blueprint never contemplated,
plus the new `/api/v1/chat`.

### Surplus beyond the blueprint (built; the blueprint never asked for it)

| Surplus feature | Where | Notes |
|---|---|---|
| **Multi-LLM hybrid router** | `aios/core/router.py`, `gemini.py`, `bedrock.py`, `failover.py`, `catalog.py` | Cross-provider, **privacy-gated** (`AIOS_ROUTER_CLOUD_TASKS` ships as `reasoning,coding`; set `AIOS_ROUTER_CLOUD_TASKS=""` to force `auto` local-only, `config.py:346`), evidence-calibrated, failover-truthful active-brain badge. Both clouds live-verified. Dedicated suites (router/route-wiring/failover/gemini/bedrock/catalog) |
| **Jarvis voice mind (Slice 1)** | `POST /api/v1/chat` (`main.py:2138`) | Hinglish conversational endpoint; reuses router+memory+facts; tools=None (no forge loop); honest about itself in the docstring ("CONVERSATION, not the agentic forge") |
| **Earned autonomy** (evidence→GREEN bridge) | `aios/core/autonomy.py` | OFF by default (`AIOS_EARNED_AUTONOMY=False`, `config.py:177`); double-gated by `MIN_SUCCESSES=5` (`config.py:179`); **RED is structurally un-earnable**. Ledger + integration tests; distinct audit-chain entry |
| **Self-analysis T0–T4** | `self_analysis_agent.py` + `self_apply.py` | Faithful build of `aiosv6_assessment_text.md` §6. T0 index → T1 diagnose (AST) → T2 propose-diff → T3 guarded apply → T4 frozen-core-RED. Golden-regression freeze (`tests/test_golden_analysis.py`) with a load-bearing vacuity guard |
| **Worker swarm** | `aios/agents/swarm.py` | decomposer→workers→synthesizer, stigmergic, no shared mutable state; `swarm:true` flag; `AIOS_SWARM_MAX_WORKERS=4` |
| **Role-pass castes** | `aios/agents/role_pass.py` | planner→coder→reviewer; per-caste tool subsets enforced *mechanically* at the dispatcher; reviewer authority from VERIFIER evidence only |
| **Stigmergic skill trails + curriculum + dev-metrics** | `memory/skills.py,curriculum.py,development.py` | Most mature subsystem; asymmetric pheromone, held-out-gated mastery, verified-only calibration. **Live-proven 6/6 mastered** (curriculum evidence run, 2026-06-11) |
| **Claude+Codex coordination control plane** | `agent_coord.py` | SQLite single-writer lease + SHA-256 hash-pinned review handoffs that fail-close on post-handoff tree drift |
| **3D "superbrain" frontend + renovated honest Shell** | `frontend/src/superbrain/`, `frontend/src/workbench/`, `GAG demo/gag-orchestrator` (lab) | Default UI; real backend binding (SSE turns, trails, audit, autonomy), in-experience approval recipe, synthesized 10-event WebAudio sound engine, embedded Monaco/preview ForgePorts pinned at canon nerve world-points, 10 read-only governance organs. The 2026-06-14 renovation made the 2D HUD honest + premium-polished. ~90% complete for its scope |

### The three genuine gaps (definitive)

1. **VOICE I/O — audio path 0% built (backend chat Slice-1 only).** Blueprint §4.2
   stage-1 (Whisper+Piper <200ms, `blueprint_text.md:287`) + §12 toolchain
   (`:940–941`). Grep-confirmed: no STT/TTS/audio code in `aios/`, no audio dep in
   `requirements.txt`. What exists is the **text** mind (`/api/v1/chat`). The
   remaining work is mic-capture→STT and streamed-text→TTS (see `JARVIS_VOICE_PLAN.md`
   Slices 2–4). *Trap:* the branch name "jarvis-voice" reads like audio shipped — it
   has not.
2. **FULL KNOWLEDGE GRAPH (Neo4j + multi-hop) — not built.** Blueprint §5.1/§18
   Phase-3 (`:320–322,1300`). Reality: contradiction-aware flat SQLite triple store
   only (`facts.py`). *Trap for a future reader:* a 1-hop graph (`knowledge_graph`
   table + `addGraphEdge`) exists only in the **superseded** `legacy_node/
   knowledgeGraph.js` — built-then-dropped at the Python rewrite, off the product
   path, different DB. `networkx` is pinned in `requirements.txt` but **never imported
   in `aios/`** (a transitive dep of radon/scikit-learn, not a graph layer).
3. **OBSERVABILITY (Prometheus + Grafana + docker-compose) — not built.** Blueprint
   §10 (`:767–816`) specs an 8-service compose topology with Prometheus:9090 +
   Grafana:3001 + 6 signals + alert rules. Reality: no compose/prometheus/grafana
   config anywhere (grep-confirmed); only `Dockerfile.executor` (sandbox image) and an
   internal JSON metrics endpoint. The blueprint's alert-rule tables are
   **documentation-only** and could read as "built" to a skimmer.

**Overall: ~80–85% of the blueprint's *intended* scope, plus large surplus the
blueprint never asked for.** Phase 1: 100% · Phase 2: 100% · Phase 3: ~85% · Phase 4:
~78% · Phase 5: MVP running, observability absent.

---

## PART 2 — The Real Forward Roadmap (prioritized)

Sequenced by leverage and risk. Effort is rough solo-dev time. **Operating rules carry
forward unchanged:** one item at a time; restate the item and **wait for explicit OK
before writing code**; tests-first; verify (full suite green) → checkpoint `RESUME.md`
→ next. **Approvals stay ON; never `--dangerously-skip-permissions`.** Frozen core
(`aios/security/*`, audit) needs an explicit go before any touch. **RED stays a hard
block even after approval** (pinned by `test_execute_approved_still_refuses_red`).
**The 3D brain+space are now operator-unfrozen but CHERISHED — enhance, never replace;
FIDELITY-IS-SACRED still governs *how* (no auto-degrade, before/after screenshots,
canon tag + goldens before any visual change).** Honest target everywhere: **~90%,
reported as such, never "100%".**

### Tier 0 — Immediate hygiene (do first; hours, not days)

| # | Item | Rationale | Effort |
|---|---|---|---|
| **H0** | **Merge or explicitly land the two feature branches.** `feat/jarvis-voice` (current, carries everything) and `feat/frontend-renovation` are both unmerged to `master`; `master` predates both feature waves. Decide the integration order, merge, and re-baseline. | Right now `master` materially understates the system; multi-branch + worktree activity risks silent divergence. Cheap, unblocks a clean baseline. | ~1–2 hrs |
| **H1** | **Doc-currency sweep — pin ONE test baseline.** Adopt `KICKOFF_PROMPT.md:24`'s "report live counts" pattern in the living docs (`README.md`, `START_HERE.md`, `AGENTS.md`). Reconcile the frontend auth claim against current code: `aiosAdapter.ts` now initializes the httpOnly session cookie and sends `credentials: "include"`; it does **not** embed `VITE_AIOS_API_TOKEN` in the browser bundle. `frontend/README.md` is already project-specific, not stock Vite. Add superseded banners to dated snapshots (`HIDDEN_KNOWLEDGE.md`, `BACKEND_TRUE_PICTURE.md`, `CEO_LOG.md`, `FRONTEND_RENOVATION_BLUEPRINT.md`, `ARCHITECT_REVIEW_2026-06-14.md`) rather than rewriting their historical numbers. | Docs are the single largest class of drift; stale baselines make healthy runs look anomalous. | ~3–4 hrs |
| **H2** | **Delete tracked cruft + untracked sandbox residue.** Remove/relocate `websocket_security_update.md` (orphaned Node-WS note; zero WS in the FastAPI+SSE stack — `websockets==16.0` is also a dead pin), `chat-ui.html` (659B), `success.txt`, `creator.txt` (0B); the 0-byte `.eslintrc.json` (dead, shadows the real `eslint.config.js`); clean/gitignore the many untracked `training_ground/*` demo files + `test_auto_grant.py`/`test_autonomy_live.py` `assert True` stubs (autonomy-demo residue, excluded by `pytest.ini`). Note `data/` + root `.fuse_hidden*` are FUSE artifacts, not project files. | Pure noise that misleads future readers; documented-but-undone across two cycles. | ~30–45 min |
| **H3** | **Quarantine the legacy/orphaned tier.** `legacy_node/` (19 files, full dead Node prototype) and the root RAG scripts (`hybrid_search.py`, `ingest_*.py`, `vector_memory_setup.py`, `extract_text.py`) are keyed to the **dead** root `orchestrator_memory.sqlite`, not the live `data/` DBs. **`reset_audit_chain.py` is a silent no-op against production integrity** — it clears the legacy table, not `data/aios_audit.db` that `verify_chain` reads. Move out of the tracked path or add a loud README banner. | A reader could mistake these for canonical; an operator could run `reset_audit_chain.py` expecting to clean the live ledger (it won't). | ~1–2 hrs |

> **Already DONE (from the prior PLAN; verify, don't redo):** the **multi-LLM router**
> frontier item; **Bedrock credential relocated to backend env** (gitignored, never in
> git history); partial Tier-1 doc refresh. The credential-on-disk finding is resolved.

### Tier 1 — The genuine gaps (sequenced by value)

| # | Item | Rationale | Effort |
|---|---|---|---|
| **G1** | **Voice I/O frontend (the goosebumps loop) — Jarvis Slice 2.** Mic capture → STT → the shipped `/api/v1/chat` → stream → TTS speak-back → the brain pulses while speaking (a new `voice-speaking` cognition-bus event) + a push-to-talk HUD control. **MVP = browser-native** (`SpeechRecognition` hi-IN/en-IN + `SpeechSynthesis`, zero install); **harden later** with local `faster-whisper` + `piper`. | The backend mind already ships; voice is now the **highest-leverage** gap because it is the operator's active initiative and completes the marquee "Jarvis" loop on top of existing seams. Browser-native path is days, not weeks. | ~1 week (browser MVP); +1.5–2 wks local STT/TTS |
| **G2** | **Knowledge-graph traversal.** Don't necessarily adopt Neo4j — first add **multi-hop reasoning over the existing `facts.py` triples** (SQLite recursive-CTE beyond `facts_for(subject)`), then decide if a real graph DB earns its weight. | The intent (contradiction-aware relations) is already met; the gap is *traversal*. A recursive-CTE layer may close ~80% of the value with no new dependency. | ~1 week (SQLite path); +1 week if Neo4j |
| **G3** | **Observability + the missing app-level deploy artifact.** Prometheus + Grafana + `docker-compose.yml` wrapping the API; expose a `/metrics` scrape surface (the internal `/api/v1/development/metrics` already has the data). Bundle the deploy fix here: add a `uvicorn.run`/`__main__` entrypoint so `AIOS_API_HOST/PORT` actually bind. | Operability multiplier; needs no model improvement and the data already exists. Forces the missing deploy artifact (no compose/Procfile/systemd today; backend launched by a hand-typed uvicorn one-liner). Lower forward-leverage than voice for a single-laptop install, so it sits below G1. | ~1–1.5 weeks |

### Tier 2 — Surplus maturation (raise the ceiling of what's already built)

| # | Item | Rationale | Effort |
|---|---|---|---|
| **S1** | **A better local brain (14B+) + a semantic-recall layer.** Swarm castes, planning calibration, and curriculum exact-prompt matching are all **"architecture proven / 7B-limited."** Skill/lesson/curriculum recall is purely **lexical** despite a full FAISS stack sitting right there; a workflow phrased in different vocabulary than its goal may not be recalled. | The single biggest lever on *intelligence* — mostly a model swap + a semantic-recall layer over existing FAISS, not new architecture. | Model swap: low; semantic-recall layer: ~3–4 days |
| **S2** | **Default-strong isolation.** Make the hardened `DockerRunner` (`--network none --read-only --cap-drop ALL --user 65534`) the **default where Docker is available**, with detection + a lighter host-path sandbox fallback. Today `APPROVED_EXECUTION_BACKEND=host` runs approved code as the backend user — honestly documented, but it's the gap between the stated trust model and the running one. | Closes the trust-model-vs-reality gap; the hardened backend already exists and is tested — a default-selection + detection change. (Bonus: slim the executor image — `Dockerfile.executor` installs the full `requirements.txt` incl. torch/faiss it never runs.) | ~2–3 days |
| **S3** | **Deployment auth + CORS hardening for the default UI.** ✅ *DONE* — `aiosAdapter.ts` initializes the backend httpOnly session cookie, sends API requests with `credentials: "include"`, and falls back to a generated body `sessionId` only when cookie setup fails. The browser bundle intentionally does **not** carry `AIOS_API_TOKEN`; token-protected/non-loopback deployments need a trusted same-origin/reverse-proxy auth boundary. `AIOS_CORS_ORIGINS` is validated at startup and rejects `*` while credentials are enabled (`_validate_cors_origins` in `aios/api/main.py`, regression tests in `tests/test_cors_guard.py`). The proxy-header policy is hardened: `AIOS_TRUST_PROXY_HEADERS`/`--proxy-headers` disable the loopback token exemption and require a strong `AIOS_API_TOKEN` (`aios/__main__.py`, `aios/api/main.py`, `tests/test_token_auth_proxy_header.py`). | A token-protected/non-loopback deploy must not silently expose bearer tokens in the browser or be bypassed by a proxy. | — |
| **S4** | **Memory forgetting / compaction.** Episodic is append-only with no pruning; semantic is only ever superseded, never aged out; working memory has no TTL despite the docstring; `_index_turn` writes unverified chat (now from BOTH `/api/generate` and `/api/v1/chat`) every turn with only recall-tiering as counter-pressure. On long-running installs these grow monotonically and unverified chat can dominate the candidate pool. | The missing half of consolidation: you have promotion, not eviction. The new chat endpoint *increases* the unverified-write rate, so this matters sooner now. | ~3–4 days |
| **S5** | **Test/coverage gates + cross-suite runner.** ✅ *DONE* — Backend pytest enforces an 85% coverage floor in `.github/workflows/ci.yml` (latest measured `89.50%`). A cross-suite CI workflow runs backend tests on Windows and frontend typecheck/tests/build on Ubuntu. The product frontend now has 326 vitest tests across the superbrain lib and workbench. The remaining frontend dark spots (organ ports, classic IDE surface) are tracked as P2-1/P2-2 rather than a missing gate. | Locks in the quality that already exists so it can't silently regress across the multi-branch activity; cheap insurance. | — |
| **S6** | **Frontend polish (the operator's standing mandate) — now on an unfrozen-but-cherished canon.** Deep micro-detailing per `FRONTEND_RENOVATION_BLUEPRINT.md` waves: a paint-trap CSS lint + the canon-freeze guard as the first protective commits; a real fixed-layer PROPOSALS container; approval self-heal reusing the canon `ApprovalPanel`. Also: dead `LAYOUT_CONFIGS`/`SPRING_CONFIGS` in `constants.ts` (~150 dead lines ride into the product via the port), dead `effectiveTier`/`demoteTier` whose doc comment misdescribes runtime, the `AccretionCore` PRNG fork, and stale lab `PROJECT.md` (lists non-existent files, marks shipped runtime-integration "Planned"). **Enhance, never redesign** — canon is unfrozen but cherished. | The marquee surface and the operator's explicit recurring mandate; strictly below core-gap work, and now the 3D layer itself is in-scope for enhancement (with reversibility: branch/tags/before-after/operator's eye). | Ongoing |

### Structural-debt watchlist (address opportunistically, not a sprint)

- **Monolith files** (correct but the riskiest to change blind): `api/main.py`
  (2270 lines, ~35 routes), `tool_agent.py` (1528), `App.jsx` (1875),
  `SuperbrainScene.tsx` (1312), `SuperbrainHUD.tsx` (1827), `superbrain.css` (1825).
  Refactor only when touching them for another reason.
- **Session-id resolver duplicated in 4 files** (`aiosAdapter.ts`, `ConversationPort`,
  `IntentPort`, `App.jsx`) with the same magic `'gag-superbrain-hud'` fallback — a
  silent-fork hazard if any copy drifts; classic + superbrain genuinely continue ONE
  conversation via this seam.
- **Magic cross-file invariants with no test guard:** ForgePorts world-points
  (`-4.8,-1.7 / 4.8,-1.5`) hand-pinned to canon nerve points; the z-index ladder
  (OrgansDock 55 < canon band 60 < ApprovalSafetyNet 62) guaranteeing the AUTHORIZE
  button stays clickable; `NervousSystem` wire-port X=4.82. A frozen-scene move or CSS
  edit could silently detach cables or block approval.
- **`Workbench.jsx`** looks like dead/legacy ("Phase 2 increment 1"), superseded by
  ForgePorts; not on any active mount path.
- **Stale `MODEL_TAGS`/`PROVIDER_META`** in `App.jsx` advertise dozens of models the
  live picker can't serve — aspirational metadata that misleads about real capability.
- **~4.4MB committed binary brain textures** (`public/textures/brain/*.png`) +
  ~1.65MB golden PNG dwarf all JS source; not LFS-managed. No `manualChunks` bundle
  strategy; **no TypeScript typecheck** despite shipping `.tsx` (types are
  esbuild-stripped, never verified).
- **`OrganSurface` never samples `specgloss.png`** though the port ships it; a brittle
  implicit contract between the port tool's GLB-texture strip and the runtime loader.
- **Audit chain has no external anchoring** — inherent to a single-laptop local hash
  chain; periodic off-box notarization of the head hash is the fix *if/when this
  system matters enough to attack*. Not urgent at the current threat model.

---

## Definition of done (per item)

Full suite green on every checkpoint (`pytest tests/` + the product + lab JS/TS suites
≈ 654 tests); each new item ships its own passing tests; `npm test` + `npm run build`
green for any frontend work; visual changes carry before/after screenshots + canon
goldens (FIDELITY IS SACRED — the canon is unfrozen but cherished: enhance, keep
reversibility); `RESUME.md` checkpointed; the relevant Tier-1 doc updated in the same
change. Honest target: **~90% of each item's scope**, reported as such.

---

_This PLAN supersedes the 2026-06-13 refresh (whose "DONE" items — multi-LLM router,
Bedrock-cred relocation, partial doc currency — are verified shipped). It reflects the
2026-06-14 state on `feat/jarvis-voice`: the frontend renovation, the lifted
frozen-canon rule, and the Jarvis voice-mind Slice 1. It is the single source of truth
for "what is next." Per standing operating rules: on each item I will restate it and
**wait for explicit OK before writing code.**_
