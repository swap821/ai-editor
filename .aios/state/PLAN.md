# PLAN.md — Blueprint-vs-Reality & The Real Forward Roadmap

> **Full refresh authored by Claude Code on 2026-06-13**, restructuring the prior
> 2026-06-03 Phase-2 slice plan (all of whose slices have since shipped). This is now
> the **single source of truth for "what is next."** Grounded in the 2026-06-13
> whole-repository deep read (8 lenses) and `.aios/state/BACKEND_TRUE_PICTURE.md`,
> and verified live this session: **`pytest tests/` → 457 passed, 1 skipped (458
> collected)** in ~47s; whole-suite total **512 passing** (457 backend + 29 product
> frontend + 26 lab); **90% line coverage of `aios/`**; grep-confirmed absences of
> voice, Neo4j, and Prometheus/Grafana in the product path.

---

## 0. Where we actually are (one paragraph)

This is a real, ~2-week-plus supervised local-first AI-OS — neither an MVP toy nor
flawless. The deterministic backbone (security spine, hash-chained audit, scope-lock,
approval capabilities, verifier, self-apply, multi-store memory, stigmergic skill
trails) is **solidly built, end-to-end wired in `aios/api/main.py`, and proven by
behavior-level tests** that drive the *real* gateway/verifier/DB rather than mocking
them. On top of the blueprint, the system has shipped **substantial surplus** the
blueprint never asked for — earned autonomy, self-analysis T0–T4, worker swarm,
role-pass castes, curriculum/brain-growth, and a marquee 3D "superbrain" frontend
(the default UI since 2026-06-12). The genuine gaps are narrow and known: **no voice,
no Neo4j knowledge graph, no observability stack**, plus a set of "surplus-maturation"
edges (model ceiling, deployment hardening, doc currency, a leaked-on-disk credential,
test/coverage gates). The prior PLAN.md's Slices 1–7 are **all done** — this refresh
replaces that plan.

---

## PART 1 — Blueprint-vs-Reality (Phases 1–5)

Spec under test: `AI_OS_Blueprint_APlus_v6` (`blueprint_text.md`, 5-phase roadmap
§18 lines 1287–1313) + companion `aiosv6_assessment_text.md` (the §6 design source
for the shipped self-analysis surplus). Note the blueprint **deliberately understates
itself** (`blueprint_text.md:149–152` says "~45% implemented, do not claim fully
built") and its own inline §00 audit-reconciliation (`blueprint_text.md:154–177`)
already flips 6 rows to BUILT. Reality has moved further past it.

### Phase table

| Phase | Blueprint scope | Status | Evidence / what's real | What's missing |
|---|---|---|---|---|
| **1 — Foundation** | LLM gen, executor, approval flow, file edit | **✅ 100%** | `aios/core/executor.py`, `aios/agents/tool_agent.py`; bounded reason→act→observe loop, structured-argv `shell=False`, scope-locked cwd, YELLOW human gate | — |
| **2 — Memory + Reflection** | L2/L3/L4 stores, reflection, hybrid retrieval, mistake_pool, hash-chain audit | **✅ 100% (test-backed; exceeds blueprint §00's pessimistic ~35%)** | `schema.sql:15–112`; `mistake_pool` byte-faithful to §7.1 (`schema.sql:99–112`); `retrieval.py:5–10` implements `R=α·BM25+β·FAISS+γ·decay` with exact 0.25/0.45/0.30 weights via real Okapi BM25 + FAISS cosine + UTC decay; SHA-256 hash-chain (`audit_logger.py`) matches §7.2 formula, *hardened beyond it* (redact-before-hash, cross-process `BEGIN IMMEDIATE`) | — |
| **3 — Intelligence** | Confidence scoring, auto-verify, vector memory, **knowledge graph** | **~85%** | Confidence filter (0.72 threshold), `_auto_verify` force-verify-after-write, FAISS `IndexIDMap` semantic memory all built and tested | **Full Neo4j knowledge graph + multi-hop traversal NOT built** (genuine gap, see Gap 2). Product ships `facts.py` flat-SQLite `(subject,predicate,object)` triples *with contradiction detection* (`schema.sql:119–128`) — intent met, backend downscoped honestly; no traversal beyond `facts_for(subject)` |
| **4 — Security & Voice** | Gateway + scope_lock + secret_scan + audit, rollback, injection shield, **voice (Whisper/Piper)** | **~75%** | Security spine **100%** (53 tests, fail-closed proven), `rollback_engine.py`, opt-in vector `injection_shield.py` all built | **VOICE = 0% — the single biggest gap.** No whisper/piper/pyaudio/transcribe code anywhere in `aios/`, no audio dep in `requirements.txt` (grep-confirmed). Only doc/HUD string mentions exist (see Gap 1) |
| **5 — MVP & Showcase** | Vite frontend + the 8 REST contracts; **observability (Prometheus/Grafana/compose)** | **MVP RUNNING; observability absent** | All 8 blueprint REST endpoints live at exact paths (`plan:803`, `memory/search:508`, `security/classify:759`, `approval/req:836`, `execute:814`, `reflect:777`, `audit/verify:770`, `rollback:876`); two frontends running (classic Vite + 3D superbrain) | **No Prometheus/Grafana/docker-compose** (grep-confirmed: only in docs). Only `Dockerfile.executor` (sandbox image) + internal JSON `/api/v1/development/metrics:688`, not a scrape surface. Blueprint §6 interactive diff-preview UI partially a gap on the UI side |

### Contract fidelity

The blueprint specifies **8 REST endpoints** (`blueprint_text.md:481–521`); the running
API has **~32**. All 8 originals are present at the exact blueprint paths — contract
honored — but the surface is 4× larger, most growth in `/api/v1/development/*`
(autonomy, skills, trails, curriculum) the blueprint never contemplated.

### Surplus beyond the blueprint (built, the blueprint never asked for it)

| Surplus feature | Where | Notes |
|---|---|---|
| **Earned autonomy** (evidence→GREEN bridge) | `aios/core/autonomy.py` | OFF by default (`AIOS_EARNED_AUTONOMY=False`, `config.py:177`); double-gated by `MIN_SUCCESSES=5` (`config.py:179`); **RED is structurally un-earnable** — even the surplus stays inside the blueprint's human-authority invariant. Tested at ledger + end-to-end levels (`test_autonomy.py`, `test_earned_autonomy_integration.py`) with a distinct audit-chain entry |
| **Self-analysis T0–T4** | `self_analysis_agent.py` + `self_apply.py` | A faithful build of `aiosv6_assessment_text.md` §6 (lines 257–411). T0 index → T1 diagnose (stdlib AST) → T2 propose-diff → T3 guarded apply → T4 frozen-core-RED. Golden-regression harness (`tests/test_golden_analysis.py`) |
| **Worker swarm** | `aios/agents/swarm.py` | decomposer→workers→synthesizer, stigmergic, no shared mutable state; `swarm:true` flag (`main.py:433,1581`); `AIOS_SWARM_MAX_WORKERS=4` |
| **Role-pass castes** | `aios/agents/role_pass.py` | planner→coder→reviewer; per-caste tool subsets enforced *mechanically* at the dispatcher, not by prompt; reviewer authority from VERIFIER evidence only |
| **Stigmergic skill trails + curriculum + dev-metrics** | `memory/skills.py,curriculum.py,development.py` | The most mature subsystem; asymmetric pheromone, held-out-gated mastery, verified-only calibration. **Live-proven 6/6 mastered** (curriculum evidence run, 2026-06-11) |
| **Claude+Codex coordination control plane** | `agent_coord.py` | SQLite single-writer lease + SHA-256 hash-pinned review handoffs that fail-close on post-handoff tree drift; 13 tests vs a real git fixture |
| **Alignment interpreter (advisory)** | `aios/core/alignment.py` | Validated, redacted, explicitly NON-authoritative understanding frame |
| **3D "superbrain" frontend** | `frontend/src/superbrain/` + `GAG demo/gag-orchestrator` (lab) | The default UI since 2026-06-12; real backend binding (SSE turns, trails, audit, autonomy), in-experience approval recipe, synthesized sound engine; ~90% complete for its scope |

### The three genuine gaps (definitive)

1. **VOICE INTERFACE — 0% built.** Blueprint §4.2 stage-1 (Whisper+Piper <200ms,
   `blueprint_text.md:287`) + §12 toolchain (`:940–941`). Grep-confirmed: no
   STT/TTS/audio code in `aios/`, no audio dep in `requirements.txt`. Correctly
   deferred (post-internship).
2. **FULL KNOWLEDGE GRAPH (Neo4j + multi-hop) — not built.** Blueprint §5.1/§18
   Phase-3 (`:320–322,1300`). Reality: flat SQLite triple store with contradiction
   detection only (`facts.py`, `schema.sql:119–128`). *Trap for a future reader:* a
   1-hop graph exists only in the **superseded** `legacy_node/knowledgeGraph.js` —
   off the product path, different DB. The real product-path "graph" is `facts.py`'s
   flat triples.
3. **OBSERVABILITY (Prometheus + Grafana + docker-compose) — not built.** Blueprint
   §10 (`:767–816`) specs an 8-service compose topology with Prometheus:9090 +
   Grafana:3001 + 6 signals + alert rules. Reality: no compose/prometheus/grafana
   config anywhere (grep-confirmed); only `Dockerfile.executor` (the sandbox image)
   and an internal JSON metrics endpoint. The blueprint's alert-rule tables are
   **documentation-only** and could read as "built" to a skimmer.

**Overall: ~80–85% of the blueprint's *intended* scope, plus large surplus the
blueprint never asked for.** Phase 1: 100% · Phase 2: 100% · Phase 3: ~85% · Phase 4:
~75% · Phase 5: MVP running, observability absent.

---

## PART 2 — The Real Forward Roadmap (prioritized)

Sequenced by leverage and risk. Effort is rough solo-dev time. **Operating rules carry
forward unchanged:** one item at a time; restate the item and **wait for explicit OK
before writing code**; tests-first; verify (full suite green) → checkpoint `RESUME.md`
→ next. **Approvals stay ON; never `--dangerously-skip-permissions`.** Frozen core
(`aios/security/*`, audit) needs an explicit go before any touch. **RED stays a hard
block even after approval** (decided 2026-06-03, still pinned by
`test_execute_approved_still_refuses_red`). Honest target everywhere: **~90%, reported
as such, never "100%".**

### Tier 0 — Immediate hygiene (do first; hours, not days)

| # | Item | Rationale | Effort |
|---|---|---|---|
| **H1** | **Rotate + relocate the live Bedrock credential at `frontend/.env`.** It holds a real, currently-valid `ABSK…` bearer token (plus shell launch snippets) in plaintext on disk — gitignored and verified NOT in git history, so it never leaked via the repo, but it is a real credential in the wrong place (frontend dir; Bedrock is backend-only). | A live secret on disk is the single highest-severity finding in the whole read; cheap to fix. | ~30 min |
| **H2** | **Delete tracked cruft + untracked sandbox residue.** Remove/relocate: `websocket_security_update.md` (orphaned Node WS note; zero WS in the live SSE stack), `chat-ui.html`, `success.txt`, `creator.txt` (0 bytes); clean or gitignore the two untracked `training_ground/test_auto_grant.py` / `test_autonomy_live.py` `assert True` stubs (autonomy-demo residue, not real tests, excluded by `pytest.ini testpaths=tests`). | Pure noise that misleads future readers; trivial. | ~30 min |
| **H3** | **Doc-currency sweep (Tier-1).** The stale **375/1** test baseline is hard-coded in four docs (`AGENTS.md:124`, `README.md:79`, `START_HERE.md:54`, `KICKOFF_PROMPT.md:24`) — actual is **457 passed/1 skipped (458)**; `RESUME.md` is itself inconsistent (456 vs 457). README never mentions the **superbrain default UI**, **earned autonomy**, or **swarm**; `AGENTS.md` SXI env-flag list omits `AIOS_EARNED_AUTONOMY` / `AIOS_SWARM_MAX_WORKERS`. Add superseded banners to `AUDIT.md` (06-07, calls shipped features "islands") and this old PLAN's predecessor. Pin the test number in **one** place. | Docs are ~3 days + two feature-waves stale; every commit widens the drift. | ~3–4 hrs |

### Tier 1 — The three genuine gaps (sequenced by value)

| # | Item | Rationale | Effort |
|---|---|---|---|
| **G3** | **Observability stack** (Prometheus + Grafana + `docker-compose.yml` wrapping the API). Blueprint §10's 6 signals + alert rules; the internal `/api/v1/development/metrics` endpoint already exists to scrape from. | Highest-value of the three: it's a deployment/operability multiplier, the system already emits the data, and it needs no model improvement. Also forces the missing **app-level deploy artifact** (no compose/Procfile/systemd today; backend launched by a hand-typed uvicorn one-liner). | ~1–1.5 weeks |
| **G2** | **Knowledge-graph traversal.** Don't necessarily adopt Neo4j — first add **multi-hop reasoning over the existing `facts.py` triples** (graph queries beyond `facts_for(subject)`), then decide if a real graph DB earns its weight. | The intent (contradiction-aware relations) is already met; the gap is *traversal*. A SQLite recursive-CTE multi-hop layer may close 80% of the value without a new dependency. | ~1 week (SQLite path); +1 week if Neo4j |
| **G1** | **Voice interface** (Whisper STT + Piper TTS). Blueprint §4.2/§12. | Genuinely deferred and lowest forward-leverage right now: it's a UX modality, not a correctness or capability gain, and it's RAM/latency-sensitive on a 16GB laptop already sharing bandwidth with a local LLM. Do it last of the three. | ~1.5–2 weeks |

### Tier 2 — Surplus maturation (raise the ceiling of what's already built)

| # | Item | Rationale | Effort |
|---|---|---|---|
| **S1** | **A better local brain (14B+).** Swarm castes, planning calibration, and curriculum exact-prompt matching are all **"architecture proven / 7B-limited."** The mechanism layer is built to receive a better model; intelligence won't materially improve until the model does (or a semantic-match layer is added to curriculum/skill recall, which is purely *lexical* today despite a full FAISS stack sitting right there). | The single biggest lever on *intelligence*; mostly an ops/model swap + a semantic-recall layer, not new architecture. | Model swap: low; semantic-recall layer: ~3–4 days |
| **S2** | **Default-strong isolation.** Make the hardened `DockerRunner` (`--network none --read-only --cap-drop ALL --user 65534`) the **default where Docker is available**, or add a lighter host-path sandbox. Today `APPROVED_EXECUTION_BACKEND=host` runs approved code as the backend user — honestly documented as "not an OS isolation boundary," but it's the gap between the stated trust model and the running one. | Closes the trust-model-vs-reality gap; the hardened backend already exists and is tested — this is a default-selection + detection change. | ~2–3 days |
| **S3** | **Deployment hardening for the default (superbrain) UI.** `aiosAdapter.ts` sends **no `Authorization` header** (`aiosAdapter.ts:194,342`) — only the classic Vite client wires `VITE_AIOS_API_TOKEN`, so a token-protected/non-loopback deploy of the default UI gets 401s on every call. Add a `uvicorn.run`/`__main__` entrypoint so `AIOS_API_HOST/PORT` (read but never used to bind) actually take effect. Validate `AIOS_CORS_ORIGINS` rejects `*` (credentialed CORS widens silently otherwise). Split the heavy ML stack out of the executor image (it installs torch/faiss it never uses). | The default UI literally cannot authenticate to a protected backend — a real deploy blocker once H1's security posture tightens. | ~3–4 days |
| **S4** | **Memory forgetting / compaction.** Episodic is append-only with no pruning; semantic only ever superseded, never aged out; working memory has no TTL despite the docstring; `_index_turn` writes unverified chat every turn. On long-running installs these grow monotonically and unverified chat can dominate the candidate pool. You have promotion; you don't have eviction. | The missing half of the consolidation story; a real long-run debt the blueprint's TTL columns imply. | ~3–4 days |
| **S5** | **Test/coverage gates + cross-suite runner.** No `--cov-fail-under` anywhere — the strong 90% is discipline, not gated. No single "run everything" command (backend pytest says nothing about the 55 JS/TS tests). The 3 untested HTTP routes (`GET/POST /development/autonomy`, `GET /development/trails`) need TestClient coverage; `api/main.py` is the largest hole (85%, 111 missed). Add a coverage threshold and a one-shot all-suite gate. | Locks in the quality that already exists so it can't silently regress; cheap insurance. | ~2–3 days |
| **S6** | **Frontend polish (the operator's standing mandate).** The superbrain is ~90% complete but has **zero unit tests for any 3D/R3F component, HUD, ApprovalPanel, or shader** — correctness rests on golden screenshots + puppeteer probes a human eyeballs. Stale `PROJECT.md` (lists non-existent files, marks shipped runtime-integration as "Planned"); dead `LAYOUT_CONFIGS` scaffolding in `constants.ts`. Deep micro-detailing polish per the standing mandate — **never redesign** (FIDELITY IS SACRED: no auto-degrade, before/after screenshots, canon tag + goldens before any visual change). | The marquee surface; polish is the operator's explicit recurring mandate, but it's strictly below core-gap work. | Ongoing |

### Structural-debt watchlist (address opportunistically, not a sprint)

- **Monolith files:** `api/main.py` (1767 lines, 31 routes), `tool_agent.py` (1528),
  `SuperbrainScene.tsx` (1312), `App.jsx` (1817), `superbrain.css` (1825) — refactor
  only when touching them for another reason; each concentrates the most code *and*
  the most untested code.
- **Legacy `legacy_node/` (19 files)** — the complete dead Node prototype of the whole
  system; referenced by nothing live. Move out of the tracked tree to stop implying a
  live JS backend.
- **Orphaned root RAG scripts** (`hybrid_search.py`, `ingest_*.py`,
  `vector_memory_setup.py`, `pdf_util.py`, `extract_text.py`) — superseded by
  `aios/memory/*`, keyed to the dead `orchestrator_memory.sqlite` (DB split-brain). A
  reader could mistake them for canonical. `extract_text.py` is fully dead (source PDF
  gone) and uses deprecated PyPDF2.
- **`reset_audit_chain.py` is a no-op against production integrity** — clears the legacy
  DB's table, not the live `aios_audit.db`; its `sqlite_sequence` delete matches nothing.
- **Audit chain has no external anchoring** — inherent to a single-laptop local hash
  chain; periodic off-box notarization of the head hash is the fix *if/when this system
  matters enough to attack*. Not urgent at the current threat model.

---

## Definition of done (per item)

Full suite green on every checkpoint (`pytest tests/` + the 55 JS/TS tests); each new
item ships its own passing tests; `npm test` + `npm run build` green for any frontend
work; visual changes carry before/after screenshots + canon goldens (FIDELITY IS
SACRED); `RESUME.md` checkpointed; the relevant Tier-1 doc updated in the same change.
Honest target: **~90% of each item's scope**, reported as such.

---

_This PLAN supersedes the 2026-06-03 Phase-2 slice plan (Slices 1–7 all shipped). It is
the single source of truth for "what is next." Per standing operating rules: on each
item I will restate it and **wait for explicit OK before writing code.**_
