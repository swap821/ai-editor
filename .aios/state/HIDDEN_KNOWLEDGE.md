> **SUPERSEDED SNAPSHOT (dated 2026-06-14) — body unchanged, kept as a record.**
> The P0 hazards flagged here (CORS, audit-reset no-op, legacy quarantine, input-shield,
> proxy-header auth, token-auth bearer wiring) have since been resolved. Test baselines
> have moved (trust the live run; see `RESUME.md` for the current state). The canon/UI
> freeze was relaxed on 2026-06-19 (palette + textures remain sacred; everything else
> may evolve). Read this for historical context, then verify against current code and
> `RESUME.md`.

# HIDDEN KNOWLEDGE — the "you'd never know unless you read it" bible

**Date:** 2026-06-14
**Scope:** whole-repo (`C:\Users\kumar\ai-editor`), synthesized from 8 deep-reader lenses (frontend lab, product frontend, root tooling, test suite, docs-currency, config/infra, cross-cutting audit, blueprint-vs-reality) + the prior 8-agent backend read (`.aios/state/BACKEND_TRUE_PICTURE.md`), with load-bearing claims re-verified against source this session.
**Working-tree state:** branch `feat/jarvis-voice` (contains the backend deep-read state + the frontend renovation + the voice Slice-1). Neither `feat/jarvis-voice` nor `feat/frontend-renovation` is merged to `master`. Live suite this session: **551 passed / 1 skipped** (was 457 at the last backend read).

This is the companion to `BACKEND_TRUE_PICTURE.md` (architecture) and `SYSTEM_TRUE_PICTURE.md` (whole-system map). Those tell you what the system *is*; this one tells you what will *bite you* — the things that are true but invisible from the structure.

> **Honesty note.** This is a real 2-week+ system. Most findings below are *deliberate, well-reasoned* decisions whose rationale is invisible unless you read the code (and many are documented in-code). A handful are genuine hazards. They are flagged **⚠** (act soon), **⚑** (know before you touch the area), or **◇** (informational / by-design surprise).

> **Supersedes the 2026-06-13 edition.** Two of the old P0 hazards are now RESOLVED and are noted as such below: (a) the superbrain adapter now sends `Authorization: Bearer` when a token is set (`aiosAdapter.ts:30-31`), and (b) the doc-drift baseline was partially re-pinned (though it has since drifted *again* — see Doc Drift). Treat any reference to "375/457/516" baselines as historical; the current count is **551 / 1**.

---

## P0 — Act soon (real hazards)

| # | Finding | Evidence | Why it matters |
|---|---------|----------|----------------|
| 1 ⚠ | **CORS is `allow_credentials=True` with wildcard methods + headers**, and nothing rejects a `*` (or overly broad) entry in `AIOS_CORS_ORIGINS`. | `aios/api/main.py:128-134` (verified: `allow_credentials=True`, `allow_methods=["*"]`, `allow_headers=["*"]`); origins from `config.API_CORS_ORIGINS` (`config.py:382-390`). | Safe for the loopback defaults (wildcards reflect against the explicit origin list). But the moment an operator adds a broad origin via `AIOS_CORS_ORIGINS`, credentialed cross-origin access widens **silently** with no guard. Add a guard that refuses `*` when `allow_credentials=True`. |
| 2 ⚑ | **`AIOS_API_HOST` / `AIOS_API_PORT` do NOT bind the server.** There is no `uvicorn.run` / `if __name__=="__main__"` anywhere in `aios/`. | `config.py:374` (read only by the lifespan policy check `main.py:97-101` + CORS); launch is a hand-typed `python -m uvicorn aios.api.main:app --port 8000` (AGENTS.md:122, README.md:65, START_HERE.md:60). | An operator who sets `AIOS_API_HOST=0.0.0.0` in `.env` expecting a public bind gets a **still-loopback** server, while the non-loopback token policy may simultaneously refuse to boot. Host/port config is a trap unless mirrored on the CLI. Also flagged in `ARCHITECT_REVIEW_2026-06-14.md:230`. |
| 3 ⚑ | **`reset_audit_chain.py` is a silent no-op on the live ledger.** It archives-then-clears `tamper_audit_trail` in the **legacy** root `orchestrator_memory.sqlite`, but the live audit chain is in `data/aios_audit.db`. | `reset_audit_chain.py:15` (`DB = 'orchestrator_memory.sqlite'`, verified); live path `config.AUDIT_DB_PATH` → `data/aios_audit.db` (`aios/security/audit_logger.py:22,200-228`). The root DB *does* contain a `tamper_audit_trail` table, so the script **"succeeds" loudly while changing nothing** the product verifies. | An operator running it to "reset the chain" gets a success message and an unchanged live ledger — a fix-shaped no-op. Repoint it at `config.AUDIT_DB_PATH` or quarantine it. |
| 4 ⚑ | **`vector_memory_setup.py` is destructive on re-run with no confirmation.** It begins `DROP TABLE IF EXISTS semantic_memory` and rewrites `vector_index.faiss` from scratch. | `vector_memory_setup.py:11,26` (verified). Unlike `reset_audit_chain.py` (which requires `--yes`), this has no guard. | Re-running it silently destroys all ingested memories in the legacy store. (It targets the *orphaned* legacy store, so live memory is unaffected — but the script itself is a footgun if ever repointed.) |

> **RESOLVED since 2026-06-13:** The "live Bedrock bearer token in plaintext in `frontend/.env`" P0 and the "default UI can't authenticate" P0. The token-scratch file remains **untracked** (`git ls-files frontend/.env` → empty; never in history), and the adapter now reads `AIOS_TOKEN` and sends `Authorization: Bearer ${token}` when set (`aiosAdapter.ts:28-32`). Still rotate/relocate the key if it is a real credential; treat as housekeeping, not P0.

---

## Undocumented behavior (true, but no doc says so)

### Major shipped subsystems / surfaces that no Tier-1 doc surfaces
- ⚑ **The superbrain 3D shell is the DEFAULT frontend at the clean root URL; the classic IDE (`App.jsx`) is now a fallback behind `?ui=classic`.** A reader expecting `App.jsx` to be "the app" is wrong. `main.jsx:20-35` selects: no flag / `?ui=shell` → `SuperbrainShell` (lazy); `?ui=classic` → `App` (eager); `?ui=home|superbrain` → bare canon brain.
- ⚑ **README/AGENTS are silent on most of the current product surface:** swarm, role-pass/castes, stigmergy, earned-autonomy, trails, the superbrain frontend, the synthesized sound engine, and the cognition bus are wired and live but undocumented in the Tier-1 docs. Their env flags exist (`AIOS_EARNED_AUTONOMY` `config.py:177`, `AIOS_SWARM_MAX_WORKERS` `config.py:187`).
- ◇ **The synthesized WebAudio sound engine and the cognition event bus are genuine, non-trivial capabilities no doc mentions as features:** 10 distinct event→sound mappings (recall ticks, VERIFY-RED shadow, mastery arpeggio, approval sus-chord, tamper tritone), bound to a real pub/sub spine off backend telemetry, sovereign-silent until the operator's first click (`frontend/src/superbrain/lib/soundEngine.ts:1-30`, `cognitionBus.ts:13-50`).
- ◇ **Surplus the blueprint never asked for is real and shipped:** earned-autonomy evidence→GREEN bridge (`aios/core/autonomy.py`), self-analysis T0–T4 (`self_analysis_agent.py` + `self_apply.py`), stigmergy skill-trails + curriculum + dev-metrics (`memory/skills.py`, `curriculum.py`, `development.py`), worker swarm (`agents/swarm.py`), Claude+Codex coordination, the multi-LLM hybrid router (`router.py` + `gemini.py` + `bedrock.py`). Much of this "surplus" is itself a faithful build of a *second* spec — `aiosv6_assessment_text.md` §6 (lines 251–411) is the literal design source for the self-analysis T0–T4 module.

### Surprising frontend rendering / state behavior
- ◇ **The entire DOM HUD is rendered INSIDE the WebGL `<Canvas>`** via drei `<Html>` + `createPortal` to `#hud-portal-root`, and the left/right consoles are pinned to 3D-projected wire endpoints (`WorkspaceCanvas.tsx:232`, `SuperbrainHUD.tsx:1107,1631`). The nervous-system wires physically plug into the DOM panels — but this means the whole HUD lives under R3F's reconciler, so a Canvas remount on GPU context loss remounts the HUD too. That is exactly why the HUD seeds its approval/telemetry state from adapter module-globals (`SuperbrainHUD.tsx:537-540`).
- ◇ **Honest-dormancy is enforced asymmetrically by link state.** `metricsStore` keeps a gentle demo *drift* while offline (`linkUp ? 0 : random drift`, `metricsStore.ts:101`), but the HUD deliberately HIDES that drift behind `'--'` so the fabricated motion never reaches the screen (`SuperbrainHUD.tsx:450-469`). The store lies a little; the view refuses to show it. A reviewer reading only `metricsStore` would think the HUD shows drift offline — it does not.
- ◇ **`QualityTierProvider`'s doc comment actively misdescribes runtime behavior.** Its exported `effectiveTier`/`demoteTier`/`perfTier` describe dimming the UI by one tier while generating, but the provider value sets `tier: baseTier, perfTier: baseTier` (FIDELITY-IS-SACRED overrode it). So `effectiveTier`/`demoteTier` are **dead in production** and live only in `qualityTier.test.tsx`; `generating` is now pure status text (`QualityTierProvider.tsx:47-54` vs `:133-145`).
- ◇ **`TierGovernor` is deliberately declawed.** It is a `PerformanceMonitor` with bounds/flip-flops, but its `onDecline` only publishes a terminal advisory and **never changes the tier** — auto-degrade was removed by law, so the governor is a measurement-only whisperer (`TierGovernor.tsx:43-60`).
- ◇ **Idle attract-mode:** after 30s with no input, the brain keeps "thinking" — extra orbital yaw, ±2° pitch, seeded 6–9s thought cascades — and logs unprompted inference (`SuperbrainScene.tsx:1204-1244`). It is not idle; it is voyaging.

### Surprising backend behavior
- ◇ **`/api/v1/chat` (the "Jarvis voice mind", branch `feat/jarvis-voice`) is TEXT-only.** It is a single-shot Hinglish conversational reply (`tools=None`, NO `ToolAgent` loop, NO file writes), word-fake-streamed over SSE, reusing the cross-provider router + privacy gate + memory recall + operator facts (`main.py:2138-2230`, docstring at `:2147` is honest: "CONVERSATION, not the agentic forge"). **There is no STT/TTS audio anywhere** — the branch name overstates. A reader expecting voice I/O from the branch name would be misled.
- ◇ **The auto-execute GREEN allowlist is tiny.** Unknown commands default to RED (`gateway.py:348`); only a short safe-pattern set is auto-green. Every other read command (`ls`, `cat`, `grep`) falls to RED unless it matches a YELLOW caution pattern. The unattended autonomous surface is **near-zero by design** — easy to misread as permissive.
- ◇ **Human approval can NEVER authorize a RED action.** `execute_approved` re-classifies and refuses RED even after a one-click approval — stricter than the blueprint's typed-token override, matching the operator's standing RED-zone hard-block policy.
- ◇ **The vector injection shield fails *safe* (toward fewer blocks), the opposite of the gateway.** An embedder error returns `False` so the regex layer is never weakened into blocking everything (`injection_shield.py:73-88`). Fail-direction asymmetry (gateway fail-closed→RED; shield fail-safe→allow-through-to-regex) is deliberate and tested, but counterintuitive.
- ◇ **The RateLimiter silently migrates legacy plaintext session ids to SHA-256 on init**, merging collisions (`gateway.py:185-210`). A row inserted under the old scheme is rewritten on first use — invisible unless you read the migration.
- ◇ **`BEDROCK_ENABLED` / `GEMINI_ENABLED` are computed at IMPORT time** (`config.py:297,322`), so flipping `AIOS_BEDROCK_REGION` requires a backend restart — unlike `ROUTER_CLOUD_TASKS`, which `_router_policy()` re-reads fresh per call (`main.py:1128-1138`). Setting only `AIOS_BEDROCK_REGION` silently enables the cloud provider (region AND a non-empty default model both truthy).
- ◇ **Bad env values silently fall back to defaults rather than crashing** (`config.py:34-86`). A malformed `AIOS_*` int/float/bool is swallowed — robust, but a typo'd flag fails *open to the default* with no signal.

---

## Dead / orphaned code (carried in the tree, referenced by nothing live)

| Item | Evidence | Status |
|------|----------|--------|
| **`legacy_node/`** — a full parallel OLD implementation (19 files incl. `securityGateway.js`, `knowledgeGraph.js`, `reflectionEngine.js`, its own `package-lock.json` + Node tests) | `README.md:12-13` ("retained for history"); zero imports anywhere | Fully dead, retained-for-history. It mirrors `aios/` closely enough that a reader could mistake it for canonical — and it contains the knowledge-graph feature the Python side **lacks** (see "Built-then-dropped" below). |
| **Root `hybrid_search.py`** — standalone RAG CLI over the dead root DB/index | live impl is `aios.memory.retrieval.hybrid_search` (`main.py:83`); root script references `orchestrator_memory.sqlite` (`hybrid_search.py:18`, verified) | Dead duplicate, orphaned from live memory. |
| **Legacy RAG/ingest tier** — `vector_memory_setup.py`, `ingest_knowledge.py`, `ingest_update.py` | All bind root `orchestrator_memory.sqlite` + `vector_index.faiss`; live system uses `data/aios_memory.db` + `data/vector_index.faiss` (`config.py:99-110`); referenced only from `legacy_node/*.js`, never from `aios/` | Functionally complete but orphaned from the running system. `ingest_update.py` is also hardwired to a single file `websocket_security_update.md` (`:10`) with no argv. |
| **`extract_text.py`** — older hardcoded PDF→md extractor (PyPDF2) | duplicates `pdf_util.py` (pypdf, argv-driven); hardcoded paths (`extract_text.py:12-16`) | Dead duplicate; `pdf_util.py` is the current/better one. |
| **`frontend/src/workbench/Workbench.jsx`** — standalone editor+preview ("Phase 2 increment 1") with hardcoded `DEFAULT_FILES` | not imported by any active mount path (`SuperbrainShell` uses `ForgePorts` instead) | Superseded/legacy. |
| **Three stray root files** | `creator.txt` (0 B), `success.txt` (11 B: "OS Online"), `chat-ui.html` (659 B "Jarvis" demo) — all confirmed present, zero references | Orphaned cruft; H2 cleanup target across two doc cycles, never done. |
| **`websocket_security_update.md`** — Node WebSocket hardening doc | live stack is FastAPI + SSE with **zero** websockets (grep-confirmed); `websockets==16.0` is pinned in `requirements.txt` with no backend consumer | Doubly-orphaned: doc + dependency both vestiges of the dead Node era. |
| **Root `.eslintrc.json`** — 0-byte empty file | confirmed 0 bytes; frontend uses `eslint.config.js` flat config | Dead config shadowing the real one. |
| **`constants.ts` legacy block (lab + ported)** — `LAYOUT_CONFIGS`, `LayoutContext`, `SPRING_CONFIGS`, `PARALLAX`, `DRAG`, `AIState`, `LIGHTS`, `TIMING`, `CAMERA.position` | exported but grep-confirmed zero live consumers; only `POST_FX` + `CAMERA.{fov,near,far}` are wired (`constants.ts:45-233`) | ~150 lines of dead constants that ride into the product via `npm run port`. |
| **`stores/` and `hooks/` subdirs** (mentioned in some scope docs) | do not exist in the live `src`; only under `attic/` (non-ported) | The only store is `metricsStore` (`useSyncExternalStore`); **no zustand** is a dependency. A scope doc referencing them is wrong about the live tree. |
| **Two untracked `training_ground/test_auto_*.py`** | `test_auto_grant.py`, `test_autonomy_live.py` — trivial `assert True` stubs | Real residue of earn/swarm autonomy runs, not authored tests; they sit inside the very allowlist path the drivers write to. |

**Built-then-dropped (the non-obvious one):** the blueprint's knowledge-graph (edges + traversal) **once existed** in the abandoned Node generation — `legacy_node/knowledgeGraph.js` defines a real `knowledge_graph` SQLite table (`source_node, relation, target_node, UNIQUE`) with `addGraphEdge` — and was **not ported** to Python. The Python product downscoped it to the flat `aios/memory/facts.py` triple store. A reader scanning only `aios/` would conclude the graph was never attempted; the truth is built-then-deprecated.

---

## Doc drift (docs vs reality)

- ⚠ **The pytest baseline is stale/contradictory in EVERY doc that pins it.** True count = **551 passed / 1 skipped / 552 collected** (verified this session). Hardcoded wrong values found: `AGENTS.md:124` = 516, `README.md:95` = 516, `START_HERE.md:54` = 516, `CEO_LOG.md:234,248` = 516, `RESUME.md` = 545 (C0) / 525 (failover) / 544 (Runtime) — *three different numbers in one file* — `PLAN.md` banner = 516 but body = 457/512, `FRONTEND_RENOVATION_BLUEPRINT.md` = 516 at `:166/:200/:214` but 546 at `:261`. **No doc states the true 551.** `START_HERE.md:54` "expect: 516 passed" will make a new contributor think a healthy run is anomalous. The fix pattern already exists: `KICKOFF_PROMPT.md:24` wisely says "report the exact pass/skip/fail counts" instead of hardcoding — adopt that everywhere and pin the number in ONE place.
- ⚑ **The running machine's cloud posture DIVERGES from the documented "safe default", and only `RESUME.md` captures it.** README.md:76 / AGENTS.md:138 say cloud is "off by default / empty = local-only" — true of the *code* default (`config.py:346` = `()`), but the live process has `ROUTER_CLOUD_TASKS=('reasoning','coding')`, `BEDROCK_ENABLED=True`, `GEMINI_ENABLED=True` (from the gitignored `.env`). A reader trusting only README would believe this install is local-only; **it is not.** The most consequential doc-vs-runtime gap.
- ◇ **`EARNED_AUTONOMY_MIN_SUCCESSES` default is 5** (`config.py:179`, matching AGENTS.md:144), **but `RESUME.md` item 5 repeatedly says "min=3"** — that is a live-run override the operator set, not the shipped default. A reader could mistake 3 for the default.
- ◇ **`AGENTS.md:155` still says "the code is ~75-80% of MVP"** while newer `PLAN.md:96` / `ARCHITECT_REVIEW` say ~80-85% — the canonical rulebook lags the newer estimate.
- ◇ **`AGENTS.md` §XI router paragraph (`:132-142`) predates `failover.py` + `catalog.py` + the calibration aggregator** — the rulebook lags the shipped multi-LLM surface by one feature wave. README/AGENTS document none of the failover/breadth/calibration layers.
- ◇ **Lab `PROJECT.md` understates its own completed work.** It marks Phase 3 "Runtime integration" as *Planned* (`PROJECT.md:33`) and lists `KnowledgeWake.tsx`/`test/e2e.js` as Active Architecture, but the file is actually `KnowledgeHorizon.tsx` and the `aiosAdapter` shipped runtime integration. The marquee-UI roadmap doc is stale vs its own code.
- ◇ **`frontend/README.md` is the stock Vite template** (`:1-16`) — zero project-specific content; documents none of the `?ui` mounts, classic IDE, superbrain, or backend wiring.
- ◇ **The blueprint's own "~35%/~45%" completion numbers are STILL quoted by readers** (`blueprint_text.md:149-152`) despite being self-superseded by an inline 2026-06-03 reconciliation banner (`:154-177`) and by every later doc. `AGENTS.md:155` literally has to fight its own oldest number ("the blueprint says ~35%; the code is ~75-80%. Trust the code"). The §00 banner is itself stale: it claims "L3 stores text chunks not entity facts" and "no file-edit diff preview" as still-missing, but both are now resolved (`facts.py` is a real triple store; `DiffView.jsx` exists, wired at `App.jsx:1413`).
- ◇ **`websocket_security_update.md` makes a reader think the system uses WebSockets.** It documents Node WS hardening for a stack that has zero websockets (FastAPI + SSE). H2 cleanup target; survives.
- ◇ **Same-filename, different-intent footgun:** the lab `AGENTS.md` (`GAG demo/gag-orchestrator/AGENTS.md`) is a terse "This is NOT the Next.js you know — read `node_modules/next/dist/docs/` before writing code", NOT the project rulebook a reader would expect. The real shared rulebook is the ROOT `AGENTS.md`. (Analogous to the `hybrid_search` and `orchestrator_memory.sqlite` naming collisions below.)
- ◇ **H2 cleanup is documented-but-not-done across two cycles** (`PLAN.md:118`, `RESUME.md:130`): `websocket_security_update.md`, `chat-ui.html`, `success.txt`, `creator.txt` all still present; the doc describes a cleanup that never happened.

---

## Fragility / footguns (cross-file invariants with no test guarding them)

- ⚑ **Magic world-coordinates pin the editor to the frozen brain.** `ForgePorts` mounts Monaco + preview at hardcoded world-points (`-4.8,-1.7` / `4.8,-1.5`) manually matched to canon nerve endpoints in the frozen `NervousSystem.tsx` / `SuperbrainHUD.tsx` (`ForgePorts.jsx:20-23`, citing exact source lines in a comment). **If the frozen scene ever moves those nerves, the editor/preview silently detach from their cables with no test to catch it.** The now-modifiable 3D brain (canon rule lifted 2026-06-14) makes this materially riskier than it was when the scene was frozen.
- ⚑ **`NervousSystem` hardcodes the wire port X at `4.82`** and bakes the 115-tube braid once (recomputing per-frame "would tank the framerate", `NervousSystem.tsx:171-174,284-325`). The DOM panel anchors at ±4.8 must stay in sync with this magic number **by hand**.
- ⚑ **Magic z-index ladder is the ONLY thing guaranteeing the AUTHORIZE button is clickable.** `OrgansDock` z=55 < canon band z=60 < `ApprovalSafetyNet` z=62, both portaling to `document.body` (NOT the canon `#hud-portal-root`) (`OrgansDock.jsx:23-31`, `ApprovalSafetyNet.jsx:27-30`). A CSS edit or a frozen-scene change could break clickability or hide a live approval with no test guarding it.
- ⚑ **Camera/FOV is a baked-in assumption across the scene.** `CosmicBackground`/`NervousSystem`/`PostFX` rely on hardcoded framing ("at Z=7.5, 45° FOV, 16:9 the width is ~12.4", `CognitiveGrasp.tsx:92-99`). A camera/FOV change silently misaligns wires and off-screen glints — again no test.
- ⚑ **Session-id resolver is duplicated in 4 places with a magic fallback string.** `aiosAdapter.ts:37-52`, `ConversationPort.jsx:43-50`, `IntentPort.jsx:46-53`, `App.jsx:549-555` each independently re-derive `localStorage['aios_session_id']` with the SAME `'gag-superbrain-hud'` SSR fallback. Classic and superbrain genuinely continue ONE conversation — but any drift in one copy would **silently fork the session** (see Surprising couplings).
- ⚑ **The freeze guard protects the 3D canvas + assets, but NOT the lib.** `aiosAdapter.ts`/`cognitionBus.ts` ARE edited in the lab and re-ported; a lab-side `npm run port` (absent from the product) would clobber the product copies. The whole workbench imports FROM the frozen tree (`ApprovalSafetyNet` even re-copies the diff-classer rather than importing it), so the byte-identical-to-lab files (`src/superbrain/*`) are overwritten on port — a known port-clobber gotcha.
- ◇ **The `id`/`vector_id` coupling in the legacy RAG store is silently wrong on any deletion.** `ingest_*.py` derive the FAISS id from `index.ntotal` and store it in `semantic_memory.vector_id`, while `hybrid_search.py` looks rows up by `semantic_memory.id` (`:46`). They coincide only if rows are inserted strictly in FAISS order with no deletions; any divergence returns the wrong text for a hit. (Legacy store only — but a footgun if revived.)
- ◇ **`agent_coord.py status()` mutates the DB on a plain read.** `_active_writer` auto-deletes an expired lease and logs `lease_expired` (`:238-244`); `status()` passes `commit_expiry=True` (`:602`) — merely *viewing* status can reap a stale lease. A non-obvious read-with-side-effect.
- ◇ **One shared hard allowlist for three drivers.** `swarm_demo.py` and `earn_demo.py` import `curriculum_evidence_driver`'s `check_allowlist`/`reject_and_abort` verbatim (`swarm_demo.py:19-26`, `earn_demo.py:10`). Loosening the driver's regexes loosens all three guardrails at once — a single point of trust for "operator-delegated approval".
- ◇ **`agent_coord.py` still routes ~half of work to `codex`**, which per project memory is currently absent (`AGENTS=('codex','claude')`, `:22`). Default automatic routing assigns work to a non-running agent unless `--builder`/`--override-routing` is used.
- ◇ **No error-path UI for a malformed/partial SSE stream** beyond silent frame-drop. A backend that 200s but streams garbage yields an empty answer with no operator-visible signal beyond the generic done/idle relax (`aiosAdapter`).
- ◇ **`reject_and_abort` swallows the rejection POST's network error** (bare `except: pass`, `curriculum_evidence_driver.py:107-108`) but still logs the rejection and exits — fail-closed (safe direction), but a server-side approval token can linger un-rejected if the server never received the POST.

---

## Security surface (notes beyond the audited spine)

- ◇ **The auth middleware allowlists host `testclient`** alongside `127.0.0.1/::1/localhost` for unauthenticated access (`main.py:152`, verified). Only reachable under Starlette `TestClient`, but it is an explicit non-production host sitting in the loopback allowlist.
- ◇ **The container backend bind-mounts the scope cwd `rw`** while the rest of the FS is `--read-only` (`executor.py:196`). An approved command CAN write to `training_ground` from inside the container — by design (it is the agent's writable sandbox) — but a reader should not assume the container is fully read-only.
- ◇ **`AWS_BEARER_TOKEN_BEDROCK` is stripped twice** — once by name in the absolute-strip list and once via the `*BEARER*` substring hint (`executor.py:49,51`). Belt-and-suspenders, intentional, not dead code; it won't generalize if the credential var name changes.
- ◇ **`_sanitise_env` prepends this project's `.venv` to a child's PATH** and `_default_runner` resolves bare program names via `shutil.which` against that sanitised PATH (`executor.py:286-330`) — closing a Windows `CreateProcess` footgun where a bare `python` could hit the base interpreter or a binary planted inside the writable sandbox.
- ◇ **Scope-lock refuses `~` home refs outright** (pathlib never expands them) and splits on shell operators *before* shlex so a glued escape like `x>/etc/passwd` is isolated and scope-checked as its own token (`scope_lock.py:29,125-177`). Word-level path checking deliberately keeps `.venv\Scripts\python.exe` intact to avoid a documented false-block.
- ◇ **The secret scanner redacts to a non-reversible `<REDACTED:NAME:8charhash>` BEFORE the audit chain hashes the payload** (`secret_scanner.py:75-104`, `audit_logger.py:1-23`) — the non-obvious ordering that lets no-secret-persistence and chain-validity coexist.
- ◇ **No TypeScript compiler in the toolchain.** The superbrain ships `.ts/.tsx` with full annotations, but `typescript` is not in `package.json` and `vite.config.js` has no typecheck step — types are esbuild-stripped and **never verified**, so type errors ship silently. With the canon rule now lifted (3D code is modifiable), this is a sharper risk than before.

---

## Performance / weight hotspots

- ◇ **~4.4MB of committed binary brain textures dwarf all JS source.** `public/textures/brain/normal.png` (2.35MB) + `diffuse.png` (1.89MB) + `specgloss.png` (264K), verified on disk. `brain.glb` is only 152K. `frontend/.gitignore` does not exclude `public/textures`, so they are committed binaries inflating clone/history; not LFS-managed.
- ◇ **`specgloss.png` is shipped and ported but NEVER sampled.** `OrganSurface` reads only diffuse + normal (`OrganSurface.tsx:26-29`), yet the port tool ships specgloss (`port-to-frontend.mjs:63`) and strips ALL GLB textures at port time while `OrganSurface` depends on external PNGs — a brittle implicit contract between the port tool and the runtime loader.
- ◇ **The `.aios/` continuity brain is ~3.9MB TRACKED**, including a single 1.65MB golden screenshot (`.aios/state/badge-goldens/live-cloud.png`) and many 100K+ JSON/JSONL state dumps — the largest source-tree contributor after textures. Intentional continuity state, not code, but it weighs the repo.
- ◇ **`Dockerfile.executor` installs the FULL `requirements.txt`** (torch + faiss + transformers, multi-GB) into a sandbox that only needs Python + pytest (`Dockerfile.executor:13-14`). The executor never imports those libs at runtime — pure image bloat; a slim executor-only requirements file would cut it by GBs.
- ◇ **`requirements.txt` is a flat freeze with duplicate-major HTTP stacks** (`httpcore`/`httpcore2`, `httpx`/`httpx2`, `:18-22`) and no extras_require split — heavy ML deps are mandatory even for a run that disables embedding. `google-genai` is intentionally NOT locked (manual `pip install` before the first Gemini turn).
- ◇ **`ForgePorts` re-fetches the workspace on EVERY synthesis/knowledge/dispatch bus event** via 3 staggered timers (`:122-144`). Bounded per event, but on a chatty long turn this is many `/development/workspace` round-trips.
- ◇ **No bundle-splitting beyond route-level `lazy()`.** `vite.config.js` has no `manualChunks`/`build.rollupOptions`, so vendor (three, monaco, motion) is not deliberately chunked.
- ◇ **Backend test suite is slow (~186s)** — heavy embedder/genai imports at collection, no fast/slow markers, so the inner loop is a ~3-minute wall.

---

## Surprising couplings (cross-cutting invisible-from-one-side links)

- ◇ **The shared `aios_session_id` localStorage key couples the two faces of the AI-OS.** Classic and superbrain continue the SAME backend conversation (`aiosAdapter.ts:37-52` + 3 copies), invisible from either UI alone. Load-bearing seam *and* a silent-fork hazard (see Fragility).
- ◇ **`SuperbrainApp` (`?ui=home`) and `SuperbrainShell` mount the same single `<WorkspaceCanvas/>`** — the ONLY structural difference is the `children` prop: home passes none (byte-identical to the frozen lab), shell passes `<ForgePorts/>` which mount INSIDE the R3F canvas (`SuperbrainShell.jsx:46`).
- ◇ **`aiosAdapter.streamTurn` always POSTs `modelId:'auto'`** regardless of any UI model choice — the superbrain command line has NO model picker (`aiosAdapter.ts:234`, `CommandLine.jsx`). The 3D experience can only ever run the backend's auto-route; **model selection is a classic-only feature.**
- ◇ **`earned_autonomy` is consumed on two independent paths that can disagree briefly.** The live SSE `earned_autonomy` frame fires an immediate AUTONOMOUS ACTION event (`aiosAdapter.ts:293-305`), while the separate every-poll `/development/autonomy` probe drives the persistent topbar count + CAPABILITY EARNED transition (`:652-668`). The count can lag the action by up to a poll interval.
- ◇ **`vite.config.js` bridges `VITE_*` → `NEXT_PUBLIC_*` via `define`** specifically to keep the ported superbrain files byte-identical to the lab (`:30-39`), AND to unify the backend origin and kill the `127.0.0.1`-vs-`localhost` credentialed-CORS split. Two purposes in one shim.
- ◇ **Two Node frameworks + React majors coexist.** `frontend/` is Vite 8 + React 19.2.6; the GAG lab is Next 16.2.7 + React 19.2.4. The port pipeline must keep superbrain files framework-agnostic — the define-shim exists precisely to bridge Next-style env into Vite. The GAG lab is a **separate nested repo**, gitignored from the main project (`.gitignore:50`), and is the canon SOURCE byte-synced via `npm run port`.
- ◇ **`customProgramCacheKey` is tier-tagged (`superbrain_v6_${tier}`)** after a real bug where a constant key made THREE reuse a degraded program for the whole session (`SuperbrainScene.tsx:803`) — a hard-won documented fix; revert it and you reintroduce the bug.
- ◇ **Causal sentience is a shared keyword→wave-anchor map across three files.** A dispatched tool lights the anatomical lobe that owns it (plan→frontal, read→temporal, write→parietal) via the SAME map in `SuperbrainScene.tsx:487-510`, `RegionPins.tsx:43-74`, `SuperbrainHUD.tsx:122-176`. The same shard always lights the same zone *because* three files agree on one table — change one and they desync.

---

## Naming-collision traps (same name, different thing)

- ◇ **`hybrid_search`** exists twice: live `aios.memory.retrieval.hybrid_search` (the real one, `main.py:83`) vs the dead root `hybrid_search.py` over the orphaned legacy store.
- ◇ **`orchestrator_memory.sqlite`** (root, legacy, used by the dead RAG/audit scripts) is NOT the live DB — live memory/audit live under `data/` (`config.py:99-110`). This is what makes `reset_audit_chain.py` a silent no-op (P0 #3).
- ◇ **`AGENTS.md`** means two different things: the ROOT one is the project rulebook; the lab one is a terse Next.js warning.
- ◇ **`networkx==3.6.1` is pinned but never imported in `aios/` or `tools/`** — a false signal that a graph layer exists. It is almost certainly a transitive dep of radon/scikit-learn; there is no graph feature.
- ◇ **`confidence_filter.py` looks untested by filename** but is fully covered by `test_confidence.py` — a filename-based coverage audit produces a false gap here.

---

## Tech debt (correct today, will slow you tomorrow)

- ⚑ **`App.jsx` is a 1,875-line single-file mega-component** (model dictionary, ModelSelector, NewFileDialog, the App state machine, SSE streaming, approval, terminal/git, ~1000 lines of inline-style JSX) and is **untested at the component level** — the largest maintainability liability in the frontend.
- ⚑ **`SuperbrainScene.tsx` (1,312 lines) and `SuperbrainHUD.tsx` (1,827 lines) are single-file god-components** mixing shaders, schedulers, math bakes, and ~25 pieces of HUD state — correct but the riskiest files to change blind, especially now that canon is modifiable.
- ⚑ **No repo-wide coverage gate.** No `.coveragerc`, no `--cov` in `pytest.ini`, no vitest coverage threshold. "How much is covered" is a per-feature narrative, never an enforced number.
- ⚑ **Frontend test coverage is lopsided.** Only the 9 classic components/libs + 2 workbench files (`OrgansDock`, `ApprovalSafetyNet`) have tests. The 10 organ ports, `ForgePorts`, `CommandLine`, `SuperbrainShell`, `SuperbrainApp`, and the entire ported superbrain lib/scene/HUD have ZERO product-side unit tests. The heavy 3D code (the bulk of the tree) is verified only by manual screenshots/goldens.
- ◇ **No CI workflow.** `.github/workflows/` is empty; the test baseline is enforced only by an operator running pytest locally — risky given the active multi-branch / worktree work.
- ◇ **No application-level deploy artifact.** No `uvicorn.run` entrypoint, no docker-compose/Procfile/systemd unit, no TLS/reverse-proxy guidance. `Dockerfile.executor` sandboxes child commands, not the FastAPI app. The whole blueprint §10 observability topology (Prometheus + Grafana + compose) is aspirational-only; metrics exist internally (`/api/v1/development/metrics`) but nothing scrapes them.
- ◇ **`AccretionCore.tsx` defines its own local `createSeededRandom`** (`:114-123`) instead of importing `lib/seededRandom.ts` like every other component — a PRNG copy that can drift from canonical.
- ◇ **Each organ port owns near-identical fetch+phase+stale/offline boilerplate** (~10 copies); `_fmt.js` dedups only `truncate`/`fmtDate`, leaving the fetch-state machine duplicated.
- ◇ **The `metricsStore` "idle imagination" drift (offline only)** is deliberate but non-obvious: a reviewer glancing at the HUD offline would see moving numbers that are NOT real data — mitigated only by the link badge (and the HUD's `'--'` masking, see Undocumented behavior).
- ◇ **Magic constants unexplained/unconfigurable in the legacy + driver tier:** fusion weights `0.25/0.45/0.30` + decay `0.05` (`hybrid_search.py:61-62`), `MAX_REPLAYS=10`/`TURN_TIMEOUT_S=900` (`curriculum_evidence_driver.py:46-47`), HNSW `(384,32)` (`vector_memory_setup.py:25`), `agent_coord.py` message cap 8000 (`:461-462`).
- ◇ **`BASE` hardcoded to `http://127.0.0.1:8000` across all HTTP drivers** with no env override (`curriculum_evidence_driver.py:32`) — drivers are unusable against any non-default host/port.
- ◇ **Duplicate/misleading section numbering in `gateway.py`:** two `# 5.` comments (`:106`, `:124`) and the SHELL_COMPOSITION block is unnumbered — cosmetic, but it obscures the classification order in the one file where order is the contract.
- ◇ **Dozens of ad-hoc verify/baseline/sky/tier PNGs in the orchestrator root** inflate the repo; only `goldens/` is the disciplined set.
- ◇ **`.fuse_hidden0000*` files at repo root and under `data/`** — artifacts of files deleted while open over a FUSE mount, not part of the project.
- ◇ **`frontend/package.json` pins a `dompurify` override (`^3.1.0`)** with no in-tree comment on why — a security-advisory pin whose rationale lives only in git history.

---

## How to use this document

- **Before touching the 3D scene** (now modifiable since the canon rule was lifted): read the Fragility section first — the wire ports, world-coordinates, z-index ladder, camera/FOV assumptions, and the keyword→lobe map are cross-file invariants with **no automated test**. "Enhance, not replace" is enforced socially, not by code.
- **Before a deploy:** P0 #1 (CORS), P0 #2 (host/port don't bind), and the missing entrypoint/CI/observability are the gating items. The security primitives exist; the deploy artifact does not.
- **Before trusting a doc number:** the test baseline is wrong everywhere (true = **551 / 1**) and the live cloud posture is opt-in despite the "local-only by default" claim. Trust the code, then `RESUME.md`, then the dated snapshots — in that order.
- **Before running a root script:** `reset_audit_chain.py` and `vector_memory_setup.py` operate on the orphaned legacy store, not the live one (P0 #3, #4). The legacy RAG/audit tier no longer feeds the running system.
