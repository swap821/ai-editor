# HIDDEN KNOWLEDGE — the "you'd never know unless you read it" bible

> ⚠️ **SUPERSEDED SNAPSHOT (dated 2026-06-13) — body unchanged, kept as a record.** Several flagged items
> are now RESOLVED: the "375/1 baseline hard-coded in four Tier-1 docs" doc-drift is fixed (README/AGENTS/
> START_HERE → **516 passed / 1 skipped**), and the multi-LLM library + active-brain badge shipped. Treat the
> test-count and doc-drift findings below as historical; current state is `RESUME.md` C0.

**Date:** 2026-06-13
**Scope:** whole-repo (`C:\Users\kumar\ai-editor`), synthesized from 8 deep-reader lenses + the prior 8-agent backend read (`.aios/state/BACKEND_TRUE_PICTURE.md`).
**Purpose:** Aggregate every *non-obvious* finding — undocumented behavior, surprising couplings/footguns, dead/orphaned code, doc drift, tech debt, security-surface notes, perf hotspots, and surplus features no doc mentions — into one deduplicated, prioritized reference. Each item carries the finding, the evidence (`file:line` where the lens cited it), and the risk/why-it-matters.

This is a companion to `BACKEND_TRUE_PICTURE.md` (the architecture read). That doc tells you what the system *is*; this one tells you what will *bite you* — the things that are true but invisible from the structure.

> **Honesty note:** This is a real 2-week+ system. Most findings below are *deliberate, well-reasoned* decisions whose rationale is invisible unless you read the code (and several are documented in-code). A handful are genuine hazards. They are flagged ⚠ (act soon), ⚑ (know before you touch the area), or ◇ (informational / by-design surprise).

---

## P0 — Act soon (real hazards)

| # | Finding | Evidence | Why it matters |
|---|---------|----------|----------------|
| 1 ⚠ | **A LIVE AWS Bedrock bearer token sits in plaintext on disk** — in a frontend directory that has nothing to do with Bedrock (Bedrock is backend-only). The file is also a misnamed personal scratch file: it contains shell launch commands, not a real dotenv. | `frontend/.env:2,6` (`ABSKQmVkcm9ja0FQSUtleS...`) — verified present and currently-valid this session. | Gitignored and verified **NOT** in git history (`git ls-files` shows untracked; `-S` history search for the token prefix returns nothing) — so it never leaked via the repo. But it is a real, valid credential on disk. **Rotate it, move it to the backend env, and rename the scratch file.** |
| 2 ⚠ | **The official default UI cannot authenticate to a protected backend.** The superbrain `aiosAdapter` sends **no Authorization header** — only `Content-Type` — on every call, and `AIOS_BASE` has no token plumbing. | `aiosAdapter.ts:21-22,194,342`; only the *classic* `frontend/src/config.js:4-5` wires `VITE_AIOS_API_TOKEN`→Bearer. | The moment an operator sets `AIOS_API_TOKEN` (required for any non-loopback deploy), the default superbrain UI gets **401 on every request**. The two frontend API clients have diverged on both auth and base URL — see #19. |
| 3 ⚠ | **CORS is `allow_credentials=True` with wildcard methods/headers**, and there is no validation that `AIOS_CORS_ORIGINS` entries aren't `*`. | `aios/api/main.py:120-126` (verified: `allow_credentials=True`, `allow_methods=["*"]`, `allow_headers=["*"]`). | Fine for the loopback defaults (wildcards reflect against the explicit origin list). But if an operator adds a broad origin via `AIOS_CORS_ORIGINS`, credentialed cross-origin access **widens silently** with no guard. |
| 4 ⚑ | **`AIOS_API_HOST`/`AIOS_API_PORT` do NOT bind the server.** There is no `uvicorn.run` / `if __name__=="__main__"` anywhere in `aios/`. | `config.py:303-304` (read only by the policy check); README.md:58 / START_HERE.md:60 launch via a hand-typed `uvicorn` one-liner. | The config values are read by the non-loopback token-policy check but **never actually bind the socket** unless the operator manually mirrors them on the CLI. An operator who sets `AIOS_API_HOST=0.0.0.0` in `.env` expecting a public bind gets a still-loopback server *and* (via #3/#4 interaction) may trip the token requirement without the host change taking effect. |

---

## Undocumented behavior (true, but no doc says so)

These are real shipped behaviors that a reader would not predict from the docs.

### Major shipped subsystems that NO public doc mentions
- ⚑ **README/AGENTS are silent on the entire current product surface.** `README.md` has **zero** mentions of swarm, role-pass/castes, stigmergy, earned-autonomy, trails, or the superbrain frontend (verified by grep — README headers stop at "Brain Growth Loop" / "Local Model Gallery"); `AGENTS.md` has zero mentions of swarm/caste/stigmergy. (*Cross-cutting lens; Docs lens.*)
- ⚑ **The superbrain is the DEFAULT frontend since 2026-06-12, and README never mentions it.** `frontend/src/main.jsx:6-22` mounts `SuperbrainApp` by default; `App.jsx` is only reachable via `?ui=classic`. README's architecture diagram and Core Modules table still present `frontend/src/App.jsx` as "Main IDE/chat shell" (`README.md:52`). The actual default UI is entirely undocumented.
- ⚑ **Earned-autonomy and the worker swarm are undocumented in both README and AGENTS**, including their env flags `AIOS_EARNED_AUTONOMY` / `AIOS_SWARM_MAX_WORKERS` (`config.py:177,187`). They are wired and live (`main.py:40,42,433,1581,1618`) and are what `RESUME.md` treats as the *active front*. (*Docs lens.*)
- ◇ **Surplus the blueprint never asked for is real and shipped:** earned-autonomy evidence→GREEN bridge (`aios/core/autonomy.py`), self-analysis T0–T4 (`self_analysis_agent.py` + `self_apply.py`), stigmergy skill-trails + curriculum + dev-metrics (`memory/skills.py,curriculum.py,development.py`), worker swarm (`agents/swarm.py`), Claude+Codex coordination, RAG+CAG, alignment interpreter (`core/alignment.py`). Much of this "surplus" is itself a faithful build of a *second* spec — `aiosv6_assessment_text.md` §6 (lines 251–411) is the literal design source for the self-analysis T0–T4 module. (*Blueprint lens.*)

### Surprising security/gateway behavior
- ◇ **The auto-execute GREEN allowlist is only two patterns: `echo` and `pwd`.** Verified at `gateway.py:138-141` (`_SAFE_PATTERNS`) and the RED default at `gateway.py:348`. Every other read command (`ls`, `cat`, `grep`) is **not** auto-green and falls to the RED default unless it matches a YELLOW caution pattern. This is surprisingly strict and easy to misread as permissive. It also means the unattended autonomous surface is **near-zero by design** — the central tension `BACKEND_TRUE_PICTURE.md` flags for the next phase.
- ◇ **Human approval can NEVER authorize a RED action.** `execute_approved` re-classifies and refuses RED even after a one-click human approval (`executor.py:435-443`) — stricter than the blueprint's typed-token override, and matching the user's standing RED-zone hard-block policy.
- ◇ **The vector injection shield fails *safe* (toward fewer blocks), the opposite of the gateway.** An embedder error returns `False` so the regex layer is never weakened into blocking everything (`injection_shield.py:87-88`). The fail-direction asymmetry (gateway fail-*closed* → RED; shield fail-*safe* → allow-through-to-regex) is deliberate and tested, but counterintuitive.
- ◇ **The RateLimiter silently migrates legacy plaintext session ids to SHA-256 on init**, merging collisions (`gateway.py:185-210`). A row inserted under the old plaintext scheme is rewritten on first use — invisible unless you read the migration.
- ◇ **The executor strips `AWS_BEARER_TOKEN_BEDROCK` *by name*** (`executor.py:51`) in addition to the `KEY/TOKEN/SECRET/PASSWORD/...` substring blocklist. This is a Bedrock-specific hardcoding that won't generalize if the cloud provider/credential var name changes.

### Surprising provider/config behavior
- ⚑ **Setting only `AIOS_BEDROCK_REGION` silently enables the cloud provider.** `BEDROCK_ENABLED` is derived at import from `region AND model` both being truthy (`config.py:297`), and `BEDROCK_MODEL` has a non-empty default (`amazon.nova-lite-v1:0`). An operator who sets a region for any other reason flips cloud on. (*Config lens.*)
- ◇ **Bad env values silently fall back to defaults rather than crashing** (`config.py:40-61`) — a malformed `AIOS_*` int/float/bool is swallowed. Robust, but a typo'd flag fails *open to the default* with no signal.

### Surprising frontend / superbrain behavior
- ◇ **The DOM HUD is rendered INSIDE the R3F `<Canvas>`** and escapes back to the DOM via drei `<Html>` + `createPortal` to `#hud-portal-root` (`SuperbrainHUD.tsx:818-1038`, mounted via `WorkspaceCanvas.tsx:232`). Consequence: a Canvas remount (`glEpoch` bump on WebGL context loss) **remounts the entire HUD** — mitigated only because the HUD seeds approval/telemetry/link state from the adapter singleton that outlives the component (`SuperbrainHUD.tsx:577-591`).
- ◇ **Idle attract-mode is test-aware production code.** On unmount it parks `lastInputMs=Infinity` specifically so idle "cannot go idle until remount" and never fires during the puppeteer e2e window (`SuperbrainScene.tsx:1107-1134`). A behavior baked in to keep screenshots deterministic.
- ◇ **`earned_autonomy` is an SSE case but deliberately NOT a `CognitionEventType`.** It is republished as `knowledge-acquired`/"AUTONOMOUS ACTION" (`aiosAdapter.ts:256`); the scene/sound key off the *label string*, not a dedicated bus type. The bus type union is intentionally narrow.
- ◇ **`MemoryGalaxy` silently caps at `MAX_STARS=128`** and slices trails beyond that (`MemoryGalaxy.tsx:23,136`). A brain that learns >128 skills stops adding stars with **no indication**.
- ◇ **Sparkline "hills" and `IDLE_LORE` fall back to canned/fictional data** when offline or before 2 samples exist (`SuperbrainHUD.tsx:87-108,188-199`, `metricsStore.ts:101`). Honest by design (gated on `linkUp`), but the *default first paint* is partly imagination.
- ◇ **`AccretionCore`'s feeding pulse IS bound to real `knowledge-acquired` events** (`AccretionCore.tsx:161-169`) — not decorative, contrary to what a skim assumes.
- ◇ **Dev-only escape hatches `window.__gagCognition` / `window.__gagGalaxyCount`** let probes drive the nervous system and read galaxy count, but are stripped in production (`WorkspaceCanvas.tsx:167-174`, `MemoryGalaxy.tsx:159-161`).

### Surprising test-harness behavior
- ◇ **`pytest` deliberately does NOT collect `training_ground/`.** `pytest.ini` sets `testpaths=tests` specifically so a deliberately-broken `training_ground` sandbox during a BREATHE demo doesn't fail the suite (`pytest.ini:1-6`) — a non-obvious coupling between test config and the agent's sandbox-breaking demos. The two untracked `training_ground/test_auto_*.py` files are therefore **not** part of the suite.
- ◇ **`golden/fixture/tests/test_*.py` look like real tests but are analyzer INPUT DATA.** `golden/conftest.py` uses `collect_ignore_glob=['fixture/*']` so pytest never collects them (`tests/golden/conftest.py:10`); running them would couple the suite to fixture content.
- ◇ **The API tests rely on an emergent property, not a stub.** They dropped the old `hybrid_search` stub entirely; an empty isolated FAISS index makes retrieval short-circuit to `[]` *without ever constructing the embedding model*. This is asserted as a contract in `test_data_isolation.py:41-52` — so a future change that eagerly loads the embedder would break API tests **in a confusing way**.
- ◇ **Two embedding/dep-gated test groups silently skip on a thin environment** (`test_memory.py:37-43`, `test_security.py` vector-shield + radon/coverage `importorskip` at `:104-108`). On this machine they ran; on a leaner one they vanish from the count **without failing**, so "all green" is environment-sensitive and not self-announcing.

---

## Dead / orphaned code & cruft

The biggest single source of "this looks live but isn't." None of it is on the product path.

| Item | Evidence | What it actually is |
|------|----------|---------------------|
| ⚑ **`legacy_node/` (19 files)** | `legacy_node/server.js:1-14` + siblings (`securityGateway.js`, `scopeLock.js`, `secretScanner.js`, `auditLogger.js`, `knowledgeGraph.js`, `memoryAgent.js`, `database.js`) | The **complete original Node.js prototype of the entire system** — every `aios/` security module has a `.js` ancestor here. Referenced by **nothing** in aios/tests/frontend. Kept as historical reference; should be removed or moved out of the tracked tree so it stops implying a live JS backend. |
| ⚑ **Orphaned root RAG/prototype scripts** | `hybrid_search.py`, `ingest_knowledge.py`, `ingest_update.py`, `vector_memory_setup.py`, `pdf_util.py`, `extract_text.py` | Superseded legacy generation: cruder BM25+FAISS fusion keyed to the dead `orchestrator_memory.sqlite` / root `vector_index.faiss`, invoked only by `legacy_node/memoryAgent.js:14`. Superseded by `aios/memory/retrieval.py`. (See DB SPLIT-BRAIN below — this is the most misleading cruft for a new reader.) |
| ◇ **`extract_text.py` is fully dead** | `extract_text.py:1` (imports deprecated `PyPDF2`) | Its source PDF `AI_OS_Blueprint_v3_0_Production_Edition.pdf` no longer exists on disk (confirmed by ls), so it **cannot be re-run**. `pdf_util.py:6` uses maintained `pypdf` for the same job — two PDF libs, one with a missing input. |
| ◇ **`chat-ui.html` (660 bytes)** | tracked root file | Stale hardcoded "Jarvis" demo HTML, zero connection to the real React frontend. Orphaned. |
| ◇ **`success.txt` ("OS Online") + `creator.txt` (0 bytes)** | tracked root sentinel files | No code references. Pure cruft in git. |
| ⚑ **`websocket_security_update.md`** | grep finds **zero** WebSocket/`ws://`/`wss://` usage in `aios/` or `frontend/src/` | Completely orphaned Node.js WebSocket security note. The active transport is HTTP+SSE. Almost certainly a stray research note / RAG-ingestion leftover from the retired `legacy_node/` era. A future reader could mistake it for guidance on the live transport. Delete or archive. |
| ◇ **A 1-hop `knowledge_graph` exists only in dead code** | `legacy_node/knowledgeGraph.js` | A reader grepping "knowledge graph" gets a hit and could wrongly conclude the graph is built. The real product-path "graph" is `facts.py`'s flat SQLite triple store — no traversal, no Neo4j. (See Blueprint gaps.) |
| ◇ **Two untracked 50-byte `assert True` stubs** | `training_ground/test_auto_grant.py`, `training_ground/test_autonomy_live.py` (**verified this session**: each is `import pytest` + `def test_*(): assert True`) | Sandbox residue from live earn/auto-grant demos — *evidence that a live run happened*, not real coverage. Clean up or gitignore. |
| ◇ **~30 multi-MB baseline/verify/crop PNGs at the GAG orchestrator root** | root `*.png` listing (not under `goldens/`) | Bloat the tree. |
| ◇ **Dead config block in `constants.ts`** | `constants.ts:45-137,219-233` | ~120 lines of `LAYOUT_CONFIGS` / `LayoutContext` / `PanelConfig` / `AIState` / `SPRING_CONFIGS` / `DRAG` / `PARALLAX` from a prior panel-based design the current scene never reads. Pure dead config — and the "spatial workflows" vision it scaffolds is unbuilt. |
| ◇ **Dead/contradicted helpers in `QualityTierProvider`** | `QualityTierProvider.tsx:51-54,99-145` | `demoteTier`/`effectiveTier` and the doc comment ("dims its own cortex by one tier while generating") are now DEAD: the FIDELITY-IS-SACRED rewrite hardwired `tier=perfTier=baseTier` with no auto-dim. `generating` is pure status text. |
| ◇ **Stale runtime artifacts on disk (correctly gitignored)** | `memory.db` 40KB, `orchestrator_memory.sqlite` 151KB, `vector_index.faiss` 65KB, `.coverage`, `__pycache__` everywhere | Stale prototype runtime state, **not** tracked. Local-disk cleanliness nit only. |

---

## Doc drift (docs vs reality)

The Tier-1 operating docs froze ~2026-06-10, before three feature waves. The `.aios/` live layer is current; the public docs are the stale layer.

- ⚑ **The "375 passed / 1 skipped" baseline is hard-coded into FOUR Tier-1 docs** (`AGENTS.md:124`, `README.md:79`, `START_HERE.md:54`, `KICKOFF_PROMPT.md:24`) but the suite now collects **458** (375 was the 06-10 baseline; curriculum→408, trails→423, stigmergy→438, earned-autonomy+swarm→456–458). `RESUME.md` is itself internally inconsistent: "456 passed" (lines 39,92) vs "457 tests" (line 68). **The honest cross-suite total is 512 passing + 1 skipped** (457 backend + 29 product + 26 lab) — see "Test-count truth" below.
- ⚑ **`AUDIT.md` (06-07) badly understates the system.** S3 still calls Planner/Verifier/Confidence-filter "islands not in the live loop" and S5 calls the Self-Analysis module "genuinely missing" — but `BACKEND_TRUE_PICTURE.md` (06-13) shows the Verifier IS wired (`_auto_verify`/force-verify-after-write) and Self-Analysis T0–T4 + self-apply shipped. A reader trusting AUDIT.md as current would *badly* under-state the system. Needs a superseded banner.
- ⚑ **`PLAN.md` (06-03) is ~2 weeks + dozens of features stale.** It lists Slices 1–7 as the forward plan; every one plus the marquee Self-Analysis module shipped weeks ago. It ends "Phase 2 complete. STOPPING for your approval." `NEXT_ANALYSIS.md` explicitly schedules a PLAN.md refresh — the team knows.
- ⚑ **The documented Claude+Codex 50/50 two-writer protocol has been running in bypassed mode.** `AGENTS.md` S0/SXI and START_HERE describe a live two-writer lease; `RESUME.md` notes recent sessions ran with `active_writer:null` (no lease held, operator-authorized) and Codex offline until ~06-16. The documented coordination invariant is documented-but-bypassed.
- ⚑ **Two README.md files are 0% real.** `frontend/README.md` is the unmodified Vite React template ("This template provides a minimal setup…"); `GAG demo/gag-orchestrator/README.md` is unmodified `create-next-app` boilerplate (references `app/page.tsx`). Both *actively misdirect* about two of the most important UI surfaces. The real lab docs live in `PROJECT.md` / `VISION.md`.
- ◇ **The lab's agent rulebook is a trap.** `GAG demo/gag-orchestrator/CLAUDE.md` is just `@AGENTS.md`, and that lab `AGENTS.md` is a 5-line nextjs-agent-rules stub — so the lab's *real* instructions are in `PROJECT.md`/`VISION.md`, **not** the CLAUDE.md/AGENTS.md an agent auto-discovers.
- ◇ **`PROJECT.md` (superbrain) is stale/aspirational.** It lists files that do not exist (`KnowledgeWake.tsx`, `test/e2e.js`) as "Active Architecture" and marks "Runtime integration" as *Planned* though `aiosAdapter` fully implements it (`PROJECT.md:20-34`).
- ◇ **`aiosv6_assessment_text.md` scorecard is contradicted by reality** ("Self-analysis readiness 5/10", "~45% implemented") with no "historical" banner — reads as a current verdict though the module shipped.
- ◇ **`.env.example` lags the real flags** — missing `AIOS_EARNED_AUTONOMY`, `AIOS_SWARM_MAX_WORKERS`, `AIOS_INDEX_CHAT`, `AIOS_REFLECT_ON_FAILURE`, `AIOS_INTERPRET_ALIGNMENT`, `AIOS_CORS_ORIGINS` (`.env.example:1-58`).
- ◇ **Minor in-code doc drift:** `PostFX.tsx:15` header says exposure 1.6 while `constants.POST_FX.toneMappingExposure` is 1.45 (`constants.ts:190`); VISION.md/SuperbrainScene comments still reference `SKY_MODE 'layered'` nuances the simplified two-mode toggle flattened; the blueprint's §10 Prometheus/Grafana alert-rule tables read as "built" but are documentation-only.

> **Test-count truth (single source for the above):** Backend = **457 passed + 1 skipped** (458 collected; the "457" in memory hides the skip). The 1 skip is `test_symlink_escape_is_out_of_scope`, `skipif sys.platform=='win32'` because symlink creation needs privilege (`tests/test_security.py:133-140`) — meaning **the symlink-escape security guarantee is NEVER exercised on the developer's own Windows machine**; it only runs on POSIX CI. Product frontend = 29. Lab = 26. **All-suite = 512 passing + 1 skipped.** Live-measured backend coverage = **90% of `aios/`** (5087 stmts, 510 missed; lowest module `semantic.py` at 81%).

---

## Fragility / footguns (sharp edges in live code)

- ⚑ **DB SPLIT-BRAIN.** The root legacy scripts hard-code `orchestrator_memory.sqlite` while the production `aios/` stack uses entirely different DBs — `aios_memory.db`, `aios_audit.db`, `aios_approvals.db` (`aios/config.py:99-103`). They are **NOT the same store**. The root memory tools operate on a parallel, stale database, and any reader assuming continuity between them is wrong.
- ⚑ **`reset_audit_chain.py` is a no-op against production audit integrity.** It clears `tamper_audit_trail` in `orchestrator_memory.sqlite` (`reset_audit_chain.py:15,27`), but the LIVE audit ledger written by `aios/security/audit_logger.py` lives in `aios_audit.db`. Even within `orchestrator_memory.sqlite` the live table uses `entry_id` (no AUTOINCREMENT id), so its `DELETE FROM sqlite_sequence WHERE name='tamper_audit_trail'` (`reset_audit_chain.py:28`) **silently matches nothing**. An operator running it to "reset the audit chain" achieves nothing on the real ledger.
- ⚑ **A `--builder` override skews future auto-routing.** `agent_coord.py` route() balances on `preferred_builder` counts (`agent_coord.py:165-171`), but a manual `--builder` override (`:197-201`) is *still stored as* `preferred_builder` — so a one-off manual assignment quietly biases the 50/50 balancer.
- ⚑ **`reject_and_abort` can leave a dangling un-rejected approval token.** It swallows the rejection POST's `RequestException` (`curriculum_evidence_driver.py:107-108`) and still `sys.exit`s — so a failed reject network call does not stop the fail-closed abort, but the server may be left with a live un-rejected approval token.
- ⚑ **Shared replay/timeout caps are a latent truncation risk for swarm builds.** `MAX_REPLAYS=10` / `TURN_TIMEOUT_S=900` are module constants in `curriculum_evidence_driver.py:46-47` and `swarm_demo.py` imports them. A multi-worker swarm build can need more replays than a single-file curriculum turn, so the shared cap can silently truncate a swarm run.
- ◇ **`vector_memory_setup.py` DROPs `semantic_memory` unconditionally** (`:11`) with no archive — re-running it destroys all legacy memories (unlike `reset_audit_chain.py`, which archives first).
- ◇ **Root scripts assume CWD is the repo root** (relative DB/index paths). Running them from a subdir silently creates a *fresh empty DB* instead of erroring (`hybrid_search.py:18-19` and ingest scripts). The production code uses absolute `config.DATA_DIR` paths and is immune.
- ◇ **Bare/broad `except` masking real failures:** `hybrid_search.py:51-54,68-69` (datetime parse → silent `now()` fallback) and `curriculum_evidence_driver.py:107-108` (network). Repo-wide there are **147 broad-except sites in `aios/` non-test code**, but 65 are explicit `# noqa: BLE001` fail-closed-by-design (`gateway.py:349`, `scope_lock.py:107`, `injection_shield.py:87`). The ~80 unannotated ones warrant a sweep to confirm intent.
- ◇ **`write_report`'s scope `LIKE` pattern is unescaped** (noted in-code as a v1 caveat): a scope path containing SQL `_` or `%` is treated as a wildcard. Current scopes (`aios`, test `pkg`) contain neither, so it's safe today but is a latent sharp edge. *(Agent-layer; BACKEND_TRUE_PICTURE.)*
- ◇ **Finding-fingerprint collisions in Self-Analysis v1:** two identically-named functions in one module, or two identical TODO lines in one file, collapse to a single fingerprint (acknowledged v1 limitation). *(Agent-layer.)*
- ◇ **`localhost` vs `127.0.0.1` are different CORS origins.** The classic frontend defaults to `http://localhost:8000` (`config.js:3`) while the superbrain adapter defaults to `http://127.0.0.1:8000` (`aiosAdapter.ts:22`). The CORS allow-list includes both spellings for 5173/4173 (`config.py:312-320`) so it works — but any new origin must be added in **both** spellings or it breaks.
- ◇ **`Dockerfile.executor` cannot write bytecode** by design — `ENTRYPOINT []` + `--read-only` root + noexec tmpfs + `PYTHONDONTWRITEBYTECODE`. Belt-and-suspenders that is easy to mistake for redundancy (`executor.py` image, `Dockerfile.executor:18`).
- ◇ **`config.py.__all__` is a hand-maintained 59-entry list** (`config.py:323-381`) that must track the constants above it in lockstep — easy to drift (e.g. a new flag added but omitted from `__all__`).

---

## Surprising couplings (subsystem A secretly depends on B)

- ⚑ **`agent_coord.py` is a *cooperative* lock, not enforcement.** It explicitly CANNOT wake an agent or replace human approval (stated `agent_coord.py:3-6`) — it is a passive disk lock + ledger. An agent that ignores the lease is **not blocked at the filesystem level**. All enforcement is cooperative.
- ◇ **`tree_snapshot` reads every untracked file's full bytes into the hash** (`agent_coord.py:151-157`) — O(repo) per handoff/verdict/status call. On a large dirty tree this is slow, but it is exactly what makes the hash-pinned review handoff spoof-resistant (a verdict is cryptographically bound to the exact tree inspected; any post-handoff edit fail-closes it — `:537-539`).
- ◇ **`swarm_demo.py` / `earn_demo.py` have ZERO independent approval logic** — they import `check_allowlist`/`reject_and_abort`/`parse_sse` from `curriculum_evidence_driver` (`swarm_demo.py:19-26`, `earn_demo.py:10`). The "same hard allowlist" claim in their docstrings is literally true *by construction*, not convention. The allowlist is single-sourced.
- ◇ **The whole superbrain reads as "one organism" because every subsystem hangs off a single ~67-line module-singleton pub/sub** (`cognitionBus.ts`) — NOT zustand (`stores/` is empty; zustand survives only in `attic/`). Scene, HUD, sound, metrics, tier, galaxy all subscribe to the same stream. This is the architectural spine; it's invisible until you trace a single `CognitionEvent`.
- ◇ **ONE shared-uniform object (`SCENE_UNIFORMS`) written once per frame** drives the cortex shader, two aura shells, fireflies, and wires phase-locked (`SuperbrainScene.tsx:143-184,1136-1252`). The "moves as one body" effect depends on the unenforced invariant "the scene mounts exactly once" (`:181-184`) — module-level mutable singletons that are justified-but-fragile.
- ◇ **The approval "hold" is a 5-subsystem state machine.** A `human_required` pause freezes breath mid-inhale, tints cortex/wires/aura amber, dilates the starfield clock to 30%, dollies the camera, and plays a suspended 2nd chord — across `SuperbrainScene.tsx:1024-1031,1143-1194`, `CosmicBackground.tsx:113-137`, `NervousSystem.tsx:74-75`, `soundEngine.ts:117-122`. A single product thesis rendered across five files.
- ◇ **`pytest.ini testpaths=tests` is coupled to the agent's sandbox-breaking demos** (see Undocumented behavior). Touching the test config can re-expose the suite to BREATHE-demo breakage.
- ◇ **A naming collision invites confusion:** root `hybrid_search.py` is the DEAD prototype, while `aios.api.main` also defines a live `hybrid_search` symbol that tests monkeypatch (`test_api.py:457`). Same name, totally different code.

---

## Security surface (beyond the audited frozen-core spine)

The frozen core (`gateway/scope_lock/secret_scanner/audit_logger/injection_shield`) is exhaustively tested and genuinely strong. These are the surfaces *around* it.

- ⚑ **Host execution mode is NOT an OS/container isolation boundary** — and it's the default. The hardened `DockerRunner` (`--network none --read-only --cap-drop ALL --user 65534 --tmpfs noexec`, `executor.py:197-228`) is real, but the default `APPROVED_EXECUTION_BACKEND='host'` runs approved arbitrary code as the backend OS user. The docstring is candid (`executor.py:14-17`): host mode cannot guarantee process-tree containment or network isolation. The strongest boundary is **opt-in**, and on Windows depends on Docker being present. So the default backend choice determines whether the exfil guardrail is regex-only or true `--network none`.
- ◇ **The audit chain has no external anchoring.** An attacker with full write access who recomputes the entire chain forward from a tampered entry produces a self-consistent forgery (`audit_logger.py`; flagged in `BACKEND_TRUE_PICTURE.md:43,58`). Inherent to a single-laptop hash chain without an out-of-band root of trust — fine for the threat model, but the moment this system matters enough to attack, periodic off-box notarization of the head hash is the fix.
- ◇ **The vector injection shield's curated set is only 10 strings and is off by default** (`injection_shield.py`; `gateway.py:306-308`). A missed injection phrasing doesn't auto-execute (allowlist catches it → RED), it just may not be *labeled* "injection."
- ◇ **`command_stays_in_scope` only scope-checks tokens that look like paths.** A bare program name is intentionally skipped (`scope_lock.py`); the dangerous-execution cases are caught by the shell-escape/composition/destructive layers instead. Scope enforcement for non-path-shaped commands relies on those *other* layers — defense-in-depth, but not obvious.
- ◇ **The self-apply path is structurally un-self-approvable.** There is deliberately **no agent `apply` tool** (the agent only has `propose_fixes`); applying is reachable **only** from a human HTTP endpoint, with `approved_by != proposed_by` as a labeled second layer (`self_apply.py:13-18`). RED frozen-core is refused; the zone is re-derived from `target_path`, never trusted from the stored value.
- ◇ **Self-apply's verify Executor is locked to one command.** It rejects any command other than `DEFAULT_VERIFY_COMMAND` (`main.py:210-245`), so the human-gated self-edit path can't be repurposed to run arbitrary code at project root.
- ◇ **The UI terminal endpoint runs through the EXACT same gateway+sandbox+audit path as agent actions** (`main.py:1731-1767`), issuing approval tokens for YELLOW — there is no privileged "operator shortcut" that bypasses the spine.

---

## Performance hotspots (real, mostly acceptable)

- ◇ **Cold-start model load on the request thread.** The first call to any embedding/recall path triggers a ~90MB MiniLM load + FAISS index read on the request thread via the lazy singleton (`aios/memory/embeddings.py:42-56`). Cold-start latency on the first `/api/generate` or memory search. Mitigated for empty indexes by the short-circuit (see test-harness note) but real once data exists.
- ◇ **The cortex shader's `microDetail()` is "the single heaviest cost on screen."** Two 27-cell animated Voronoi loops per fragment (`SuperbrainScene.tsx:683-733`), frozen on low tier but still expensive at high — on a machine sharing GPU bandwidth with a local LLM.
- ◇ **The real frontend download weight is textures, not JS.** The lazy `SuperbrainApp-*.js` chunk is 1,297,730 bytes (three.js + @react-three/{fiber,drei,postprocessing} + motion), but the brain 3D assets are ~4.5MB of PNG (`public/textures/brain/normal.png` 2.35MB + `diffuse.png` 1.89MB + `specgloss.png` 269KB) + `brain.glb` 155KB. Optimizing JS bundle size while ignoring textures would miss the bulk of the weight.
- ◇ **`NervousSystem` builds 115 Frenet-framed spiral TubeGeometries merged into one draw call** with a hardcoded `tabX` to avoid 60fps geometry rebuilds (`NervousSystem.tsx:96-149,171-334`) — a deliberate perf trade that's invisible until you wonder why the wires don't recompute.
- ◇ **`customProgramCacheKey` keyed by tier (`superbrain_v6_${tier}`)** is a documented hard-won fix (`SuperbrainScene.tsx:798-803`): a *constant* key made three.js reuse the first-compiled program for the whole session regardless of FIDELITY. A subtle shader-cache footgun, already solved — don't "simplify" it back to a constant.

---

## Structural debt (the monoliths and asymmetries)

- ⚑ **`aios/api/main.py` is a 1767-line monolith** (31–33 routes, 15 Pydantic models, the entire DI graph, a ~470-line `event_stream` generator). It is **both the largest file and the largest untested-coverage hole**: 743 stmts, 111 missed (85%), with untested error/guard branches at `:896-940, :1254-1286, :1655-1660` and the autonomy/trails endpoints untested at the HTTP level. `test_api.py` is correspondingly 66KB / 67 tests. A refactor here touches enormous, tightly-coupled tests.
- ⚑ **`aios/agents/tool_agent.py` is 1528 lines** — the second monolith (the agentic loop, tool dispatch, caste tool-subset enforcement, grant pre-apply all in one module); `test_tool_agent.py` is 63KB / 63 tests.
- ◇ **`SuperbrainScene.tsx` is a 1312-line monolith** — region-baking math, 3 GLSL programs, BrainModel, CameraDrift, the idle controller, the wave scheduler, and the scene root. Highest complexity *and* highest sophistication in the frontend.
- ◇ **`frontend/src/App.jsx` (1817 lines)** and `superbrain/superbrain.css` (1825 lines) are large single-file UI surfaces that resist incremental review.
- ◇ **Test-to-source size asymmetry concentrates refactor risk:** `test_api.py` (66KB), `test_tool_agent.py` (63KB), `test_self_analysis.py` (30KB), `test_brain_growth.py` (30KB) carry the bulk of the suite.
- ◇ **No coverage threshold is enforced anywhere** — no `.coveragerc`, no `--cov-fail-under`, no `pytest-cov` in `pytest.ini`. The strong 90% is achieved by **discipline, not gate**, and can silently regress.
- ◇ **No single "run everything" gate.** Backend pytest, the 29 product vitest tests, and the 26 lab tests have no shared runner. A developer running only the documented backend command gets a green that says **nothing** about the 55 JS/TS tests.
- ◇ **Frontend/lab coverage is entirely unmeasured** (`vitest run`, no `--coverage`). The 3D scene, HUD, ApprovalPanel, MemoryGalaxy, and every shader have **zero unit tests** — correctness rests entirely on 37 golden PNGs + 15 puppeteer probes a human must eyeball. A regression in wave anchoring, region baking, or hold choreography would **not fail CI**.
- ◇ **Two near-identical ingesters** (`ingest_knowledge.py:13-58` vs `ingest_update.py:12-42`, differ only in `MD_PATH` + log wording) should be one parametrized script. Two PDF libs for one job (`PyPDF2` vs `pypdf`).
- ◇ **The executor image installs the full ML `requirements.txt`** (torch 2.12 / faiss / transformers, ~2GB) it never uses (`Dockerfile.executor:13-14`) — no API/ML dependency split, bloating sandbox build time and size.
- ◇ **Growth stores have no forgetting/compaction.** Episodic is append-only; semantic is only superseded, never aged out; `_index_turn` writes unverified chat on every answered turn with only recall-tiering as counter-pressure. On a long-running install these grow monotonically and unverified chat can dominate the candidate pool. You have promotion; you don't yet have eviction. *(BACKEND_TRUE_PICTURE.)*
- ◇ **`.gitignore` parks several CSS files + a design PDF as "source-reference artifacts"** (`.gitignore:41-49`) — dead/parked assets tracked-out rather than removed.
- ◇ **`next@16.2.7` / `react@19.2.4` are bleeding-edge.** AGENTS.md/CLAUDE.md warn "This is NOT the Next.js you know" (Next 16 canary) — APIs may diverge from training data; a real maintenance risk on the lab.

---

## Blueprint-vs-reality gaps (genuine, not debt)

These are intended-scope items the docs imply are built; they are honestly deferred, not broken.

- ◇ **VOICE = 0% built** — the single biggest blueprint gap. Blueprint §4.2 stage-1 (Whisper+Piper) + §12 specify STT/TTS, but there is **no** whisper/piper/pyaudio code anywhere in `aios/` and **no** audio dep in `requirements.txt` (grep-confirmed). Only doc/HUD string mentions exist. Correctly deferred to post-internship.
- ◇ **Full knowledge graph (Neo4j + multi-hop) NOT built.** Reality is `aios/memory/facts.py` — a flat SQLite contradiction-aware triple store (`semantic_facts`, `schema.sql:119-128`), no traversal beyond `facts_for(subject)`, no Neo4j. The product-path "graph" is a triple *table*. (The only graph-shaped code is the dead `legacy_node/knowledgeGraph.js`.)
- ◇ **Observability (Prometheus + Grafana + docker-compose) NOT built.** Blueprint §10 specifies an 8-service Compose topology with Prometheus:9090 / Grafana:3001 and 6 signals. Reality: **no** `docker-compose.yml`, **no** prometheus/grafana config — only `Dockerfile.executor` (the sandbox image) and an internal JSON `/api/v1/development/metrics:688` (not a scrape surface). The blueprint's §10 alert-rule tables are documentation-only.
- ◇ **No app-level deployment artifact.** `Dockerfile.executor` is ONLY the sandboxed code-runner image, not an API-server/frontend image. No docker-compose, no Procfile, no systemd unit, no process manager, no CI config, no TLS/reverse-proxy sample (documented as an external operator responsibility, `README.md:159-161`). Deployment completeness is ~85% for the single-laptop target, ~55% for true multi-user/internet.
- ◇ **The blueprint deliberately understates itself.** It says "~45% implemented, do not claim fully built" (`blueprint_text.md:149-152`) but an inline §00 "Audit Reconciliation" block (`:154-177`) already flips 6 rows from PARTIAL/DESIGNED to BUILT+tested. The blueprint is **not a neutral spec** — it argues against its own pessimism, and reality has moved well past even that. The running API has ~32 endpoints vs the blueprint's 8 (all 8 originals present at exact paths; the 4× growth is in `/api/v1/development/*`).
- ◇ **No production document/PDF ingestion pipeline.** Product knowledge enters only via single-string `SemanticMemory.add`; the real RAG ingest path is the *dead* legacy scripts. *(BACKEND_TRUE_PICTURE.)*

---

## Where to start (if you fix anything from this doc)

1. **Rotate the live Bedrock token** (`frontend/.env:2`), move it to the backend env, rename the scratch file. *(P0-1)*
2. **Decide the deploy auth story for the default UI** — wire a token into `aiosAdapter.ts` or accept loopback-only forever. *(P0-2)*
3. **Validate `AIOS_CORS_ORIGINS` rejects `*`** when credentials are enabled. *(P0-3)*
4. **Pin the test count in one place** and add superseded banners to `AUDIT.md` / `PLAN.md` / `aiosv6_assessment_text.md`; update README to mention the superbrain default, swarm, and earned-autonomy. *(Doc drift)*
5. **Delete or `legacy/`-archive** `legacy_node/`, `websocket_security_update.md`, `chat-ui.html`, `success.txt`, `creator.txt`, and the orphaned root RAG scripts — or add a one-line "SUPERSEDED — see aios/memory" header so a future reader isn't misled. *(Dead code)*
6. **Clean the two `assert True` stubs** out of `training_ground/`. *(Cruft)*

Everything else is either by-design (and now documented here) or known structural debt that is safe to leave until it's in your way.
