# AI-OS — System True Picture (whole-repository deep read, 2026-06-14)

> **This is the canonical whole-system map. Read this first.** It extends
> [`BACKEND_TRUE_PICTURE.md`](BACKEND_TRUE_PICTURE.md) (the 2026-06-13 deep read of the
> Python backend core) with the frontend (the GAG superbrain lab + the product/classic
> UI), the root tooling/drivers, the test suite, config/infra/deploy, and — most
> importantly — **how it all composes end to end**: a request from the UI → SSE →
> backend cognition/memory/security → earned-autonomy/swarm → audit chain → back to UI events.
>
> **Evolving document.** Authored 2026-06-14. The UI canon was relaxed on 2026-06-19
> (palette + textures sacred; everything else may evolve). Test counts and some
> surface inventories are stale; trust the live run and `RESUME.md` for current
> baselines. The architectural composition described here remains accurate.
>
> **Division of authority.** For the backend core (security spine, cognition loop, agent
> layer, memory, learning), `BACKEND_TRUE_PICTURE.md` remains the source of truth and is
> not repeated here in full. For the frontend, tooling, tests, config, and the
> system-as-a-whole, this document is authoritative. Non-obvious findings, debt, dead
> code, doc drift, and footguns live in [`HIDDEN_KNOWLEDGE.md`](HIDDEN_KNOWLEDGE.md); the
> blueprint-vs-reality phase table lives in [`PLAN.md`](PLAN.md).
>
> **Working-tree state at the time of this read.** Branch `feat/jarvis-voice` is checked
> out and contains everything below. Two feature branches are **unmerged to `master`**:
> `feat/frontend-renovation` (the honest+premium 2D HUD, dead chrome removed, root `:5173`
> is now the integration Shell) and `feat/jarvis-voice` (Slice 1 = `POST /api/v1/chat`,
> a Hinglish conversational mind, no tools). The frozen-canon rule on the 3D brain+space
> was **lifted by the operator** (the brain is now modifiable — but cherished:
> enhance, do not replace). Verified test baseline this session: **551 passed / 1 skipped**
> (`pytest tests/`, 169s) — up from the 457 in the backend snapshot.

---

## 1. What this system is, in one paragraph

This is a **supervised, memory-driven, local-first AI operating system** with two faces.
The backend (`aios/`, ~9k LOC Python) is a cognitive loop in which a weak local model
(Ollama, optionally Bedrock/Gemini via a privacy-gated router) can actually act on a
workspace — plan, read, write, run, verify, self-correct, and even patch its own source —
while a **deterministic, fail-closed security kernel and an evidence-based verifier decide
what is allowed to happen**. The frontend is a single Vite/React SPA that mounts one of
three UIs at one URL: a 3D "voyaging brain" Shell (now the official default), a classic
IDE (fallback), and a bare canon home. Both faces stream the *same* supervised turn over
SSE, share one session, and bind to one backend boundary. The thesis carried through every
layer is **"trust the evidence, not the model"**: anywhere a lesser design would let the
LLM's word stand ("safe", "confident", "passed", "approved"), a piece of non-LLM code
(pattern-matching, SQLite, exit codes, a hash chain) re-derives or re-proves the claim.
This is a real ~2-week+ system that **exceeds its own blueprint on the backend core**,
is genuinely production-shaped where it counts, and has honest, named edges (no voice
audio, no knowledge-graph traversal, no observability stack, opt-in OS isolation,
lopsided frontend test coverage).

---

## 2. Top-level component map

```
                                  ┌─────────────────────────────────────────────────────┐
   BROWSER (one Vite SPA)         │  main.jsx  —  ?ui= mount switch (code-split per UI)   │
   http://localhost:5173          │   (no flag)/?ui=shell → SuperbrainShell  [DEFAULT]    │
                                  │   ?ui=classic          → App.jsx (classic IDE)        │
                                  │   ?ui=home/superbrain  → SuperbrainApp (bare canon)   │
                                  └───────────────┬─────────────────────────────────────┘
                                                  │
   ┌──────────────────────────────────────────────┼──────────────────────────────────────────┐
   │ THE SUPERBRAIN SHELL (default)                │   THE CLASSIC IDE (?ui=classic)            │
   │  WorkspaceCanvas (one persistent R3F <Canvas>)│    file tree · Monaco · live preview       │
   │   ├ SuperbrainScene (3D organism, shaders)    │    chat · terminal/git · model picker      │
   │   ├ SuperbrainHUD  (DOM HUD, in-canvas)       │    DiffView approval · self-analysis panel │
   │   ├ ForgePorts (Monaco+preview at nerve pts)  │    own SSE parser (lib/sse.js)             │
   │   ├ OrgansDock (10 read-only organs)          │                                            │
   │   └ ApprovalSafetyNet (triple-redundant)      │                                            │
   │      ↑ all subscribe to ↓                     │      ↑ own approval/route handling ↓        │
   │  cognitionBus (pub/sub) · metricsStore · soundEngine                                       │
   │            └──────────────── aiosAdapter.ts (THE data spine) ──────────────┘              │
   └────────────────────────────────────┬──────────────────────────────────────────────────────┘
                                         │  HTTP / SSE  (POST /api/generate · /api/v1/chat ·
                                         │               20s poll: /development/{trails,metrics,
                                         │               autonomy} + sampled /audit/verify)
                                         ▼
   ┌──────────────────────────────────────────────────────────────────────────────────────────┐
   │ FastAPI  aios/api/main.py  (~2270 LOC, ~33 routes)                                          │
   │  CORS allow-list · token/loopback auth middleware · lifespan startup policy                 │
   │  ┌──────────────────────────────────────────────────────────────────────────────────────┐ │
   │  │ TURN PIPELINE (the cage)                                                               │ │
   │  │  AlignmentInterpreter (advisory) → model Router (privacy-gated) → ToolAgent loop       │ │
   │  │      reason → act → observe (≤5 iters)                                                  │ │
   │  │        every action ▶ Security Gateway (GREEN/YELLOW/RED, fail-closed)                  │ │
   │  │        YELLOW ▶ human_required (resumable approval) │ RED ▶ refused (even if approved)  │ │
   │  │        write ▶ snapshot → audit → apply → _auto_verify (sibling pytest)                 │ │
   │  │        Verifier: exit code is authoritative truth                                      │ │
   │  │        earned-autonomy bridge: verified-streak class auto-applies (OFF by default)      │ │
   │  │        swarm:true ▶ worker castes (coder/reviewer) under the same gate                  │ │
   │  └──────────────────────────────────────────────────────────────────────────────────────┘ │
   │  Memory (data/, gitignored):  L1 working · L2 episodic · L3 semantic(FAISS) · L3b facts ·   │
   │                               L4 mistakes · skills(stigmergy) · curriculum · dev tracker     │
   │  Security spine (frozen core): gateway · scope_lock · secret_scanner · audit_logger ·        │
   │                                injection_shield   →   SHA-256 hash-chained audit ledger       │
   │  Executor: shell=False argv · host runner (default) | DockerRunner (opt-in, hardened)        │
   │  Self-apply / Rollback: snapshot → git apply --check → audit → confined apply → integrity →  │
   │                         verify → auto-rollback (RED frozen core refused; no self-approval)    │
   └──────────────────────────────────────────────────────────────────────────────────────────┘
        ▲                                              ▲
        │ root drivers (operator CLIs, hit the HTTP)   │ legacy tier (ORPHANED from live system)
   curriculum_evidence_driver.py · swarm_demo.py ·     hybrid_search.py · ingest_*.py ·
   earn_demo.py · agent_coord.py (disk control plane)  vector_memory_setup.py · reset_audit_chain.py

   GAG demo/gag-orchestrator/  —  the Next.js superbrain LAB (gitignored nested repo; canon
   SOURCE for the 3D UI; byte-ported into frontend/src/superbrain via tools/port-to-frontend.mjs)
```

---

## 3. Layer by layer

### 3.1 Backend core (`aios/`) — see `BACKEND_TRUE_PICTURE.md`

The backend is the deepest, most proven part of the system and is documented authoritatively
in the backend read. In brief, it composes six subsystems into one organism:

| Subsystem | One-line truth | Status |
|---|---|---|
| **Security spine** (frozen core) | Deterministic 3-zone classifier, fail-closed everywhere; shell-operator-aware scope tokenizer; SHA-256 hash-chained audit ledger (redact-before-hash, cross-process `BEGIN IMMEDIATE`) | **Solid / proven**, 53 tests |
| **Cognition loop** | `ToolAgent` reason→act→observe; tool-call recovery for 4 observed prose shapes; orthogonal security/confidence gates; `_auto_verify` runs sibling pytest; RED never grantable by approval | **Solid / proven** |
| **Agent layer** | 9 real tools; resumable filepath-keyed approval (`_pre_apply_grants` fixes the dropped-grant replay bug); reflection-on-failure; role-pass castes from verifier evidence only; Self-Analysis T0–T4; guarded self-apply | **Solid / proven**, 148 tests |
| **Cognitive memory** | L1/L2/L3/L3b/L4 multi-store; crash-consistent FAISS writes (`IndexIDMap`); hybrid `R=α·BM25+β·FAISS+γ·decay` with real Okapi BM25; partial-unique-index invariants pushed into SQLite | **Solid / proven**, ~65 tests |
| **Learning** | Stigmergic skill trails (asymmetric pheromone, constants test-pinned); held-out-gated curriculum; evidence-gated promotion; the most mature subsystem | **Solid / proven**, 31 tests |
| **RAG + coordination** | Production retrieval live-wired into `/api/generate`; disk-based two-agent control plane with hash-pinned review verdicts | **Solid / proven**, 13 coord tests |

**Backend frontier (unchanged from the backend read):** the autonomous GREEN surface is
deliberately tiny (host mode auto-runs only `echo`/`pwd`); strong OS isolation is opt-in
(Docker), not default; the model is the ceiling (planning advisory, calibration a no-op on
a cold DB, castes "architecture proven / 7B-limited"); skill/lesson/curriculum recall is
lexical-only; the growth stores have no forgetting/compaction; the audit chain has no
external anchoring.

### 3.2 The superbrain lab (canon source) — `GAG demo/gag-orchestrator/`

The **byte-faithful source** of the 3D UI. A Next.js 16 + react-three-fiber interface that
renders the AI-OS as a living, voyaging brain in deep knowledge space — the authored
"wow-factor face." It is a **separate, gitignored nested repo** (the operator's own lab;
confirmed: `git ls-files` misses it, `.gitignore:50` ignores the whole dir) and is the
canon source that `tools/port-to-frontend.mjs` copies into `frontend/src/superbrain/`.

What makes it genuinely production-grade for its scope (~90–95% complete, ~9.1k LOC read):

- **One nervous system, three singletons.** `lib/cognitionBus.ts` (synchronous, fault-isolated
  pub/sub), `lib/metricsStore.ts` (`useSyncExternalStore`, NOT zustand), and `lib/aiosAdapter.ts`
  (the *only* backend boundary — streams `POST /api/generate` SSE and polls
  `/api/v1/development/{trails,metrics,autonomy}` + `/api/v1/audit/verify`, translating every
  frame/poll into bus events).
- **Honest-data discipline enforced in code, not docs.** Offline, the metric rows render `--`
  rather than the store's demo drift; the terminal goes silent rather than inventing lines; the
  verified-trail `+N` delta only paints on a real hash-chain growth; a rejection is asserted
  *only* when the server confirmed `decision==='rejected'` — otherwise it reads
  `"rejected (unconfirmed — token will expire)"` (`SuperbrainHUD.tsx:453-469`,
  `lib/aiosAdapter.ts:407-413`).
- **Causal sentience.** A dispatched tool lights the anatomical lobe that owns the work
  (plan→frontal, read→temporal, write→parietal) via a keyword→wave-anchor map shared by the
  scene, region pins, and HUD routing (`SuperbrainScene.tsx:487-510`, `RegionPins.tsx:43-74`).
- **Operator sovereignty + FIDELITY-IS-SACRED.** The topbar sovereignty row
  (FIDELITY/SKY/SURFACE/SOUND) only the operator's click ever writes; the quality-tier
  governor is **declawed by law** — `TierGovernor.onDecline` only publishes an advisory and
  **never auto-degrades** (`TierGovernor.tsx:43-60`), and the goldens/canon discipline
  (canon-v1, sky-A/B, organ-v1) backs it.
- **GPU context-loss resilience**, a fully-synthesized WebAudio voice bound to the same bus
  (sovereign/silent until the operator's click), and a byte-faithful port pipeline with a
  manifest-drift tripwire.

**Lab gaps/debt:** the heavy 3D/shader code (the bulk of the tree) is verified only by manual
screenshots/goldens, not automated assertions; `SuperbrainScene.tsx` (1,312 lines) and
`SuperbrainHUD.tsx` (1,827 lines) are single-file god-components; `lib/constants.ts` is largely
dead (`LAYOUT_CONFIGS`, `SPRING_CONFIGS`, etc. exported but zero consumers); `QualityTierProvider`'s
`effectiveTier`/`demoteTier` are dead in production (FIDELITY-IS-SACRED overrode the dimming path
the doc comment still describes); `PROJECT.md` is stale (lists a renamed file and marks shipped
runtime-integration as "Planned").

### 3.3 Product frontend — `frontend/src/`

A single Vite 8 + React 19 SPA. **Mount selection is a `?ui=` switch in `main.jsx`** (verified):
no flag / `?ui=shell` → `SuperbrainShell` (the **official default**); `?ui=classic` → the classic
`App.jsx`; `?ui=home`/`superbrain` → bare canon `SuperbrainApp`. Each branch's heavy stack is
code-split so only the mounted UI loads.

**The superbrain dir is byte-identical to the lab** — verified clean (ignoring CRLF). Because the
lab uses Next-style `@/...` imports, `vite.config.js` aliases `@`→`./src/superbrain` and a
`define` shim bridges `VITE_API_BASE`/`TOKEN` → the lab's `process.env.NEXT_PUBLIC_*`, so the
ported files stay overwrite-safe under `npm run port` while unifying the backend origin.

**The product-authored additive layer** (`frontend/src/workbench/*`) self-portals to
`document.body` so it never enters the R3F reconciler or perturbs the brain:

- **`ForgePorts.jsx`** mounts a real Monaco editor + sandboxed live-preview *as in-scene
  `<Html>` panels* at the canon nerve world-points (−4.8 / +4.8), each flaring on the matching
  real bus event, and syncs editor tabs to the agent's **real on-disk** `training_ground`
  workspace via `/development/workspace` — path-independent of whether the write landed by
  approval or by earned-autonomy auto-write (the only correct way to show what the mind
  *actually wrote*, since the auto-write path never pauses).
- **`OrgansDock.jsx`** hosts **ten read-only observability organs** (Conversation, Autonomy
  Ledger, Curriculum, Skills, Proposals, Memory L3 probe, Plan, Intent, Zone Probe, Models),
  each encoding a 3-to-5-state honesty model (loading/live/empty/stale-keep-last/offline) and
  deliberately keeping destructive controls *out* of the HUD layer (observe-first governance).
- **`ApprovalSafetyNet.jsx`** is a genuinely subtle reliability fix: triple-redundant
  (poll + bus + visibility) recovery of a missed approval signal, behind a 1.5s grace gate, so
  a paused run is never un-actionable — and it renders *only* when the canon panel demonstrably
  failed (zero double-UI in the healthy path).

**The classic IDE (`App.jsx`, ~1875 lines)** is a full self-contained file-explorer + Monaco +
live-preview + chat + terminal/git + alignment/self-analysis IDE with its own SSE parser
(`lib/sse.js`) and its own approval/route/earned-autonomy handling, plus approval-on-diff via
`DiffView.jsx` (which closes the blueprint's old "no file-edit diff preview" gap).

**Product frontend status: ~90% as a working, wired product.** Evidence: 11 test files / **65
tests pass** (vitest, ~9.3s); a fresh `dist/` build exists (2026-06-14); every organ binds to a
real backend endpoint with honest offline states. **Gaps:** test coverage is lopsided — only the
classic libs + `OrgansDock` + `ApprovalSafetyNet` are tested; the 10 organ ports, `ForgePorts`,
`SuperbrainShell`, and the entire ported superbrain lib/scene/HUD have **zero product-side tests**.
The classic Monaco editor is a manual scratch workspace **decoupled from the agent** (generated
`code` frames are explicitly NOT written to files; no `/development/workspace` sync in classic).
`Workbench.jsx` is superseded/dead (replaced by `ForgePorts`). `MODEL_TAGS`/`PROVIDER_META`
advertise dozens of models the live picker can't actually serve (aspirational metadata).

### 3.4 Root tooling + drivers (repo-root Python)

Two non-overlapping tiers share the repo root:

**(1) Current "driver" tier (~95%, live-wired).** Operator-authorized, hard-allowlisted CLIs that
orchestrate the live backend over HTTP and produce auditable evidence:
- **`agent_coord.py`** — a self-contained `sqlite3` coordination control plane
  (`.aios/state/coordination.db`): single writer-lease mutex (`BEGIN IMMEDIATE` + WAL), 50/50
  builder routing, and **SHA-256 tree-snapshot hash-pinning** so a review verdict is refused if
  the tree changed after handoff and a builder cannot approve their own handoff. The only driver
  not dependent on the live server.
- **`curriculum_evidence_driver.py`** — the operator-delegated approver + SSE driver. Defines the
  **canonical hard allowlist** (`ALLOWED_FILE_RE`/`ALLOWED_CMD_RE`: only `.py` directly under
  `training_ground/` and only single-file anchored `pytest`), fail-closed on the first
  out-of-allowlist action, with append-only JSONL audit. It is built to *catch the product lying
  to itself* (warns on "verified success with no curriculum increment").
- **`swarm_demo.py`** / **`earn_demo.py`** — reuse that driver's audited helpers verbatim (one
  source of truth for the guardrail) to drive the swarm and prove the zero-approval auto-grant.

**(2) Legacy "Phase 3 Intelligence Layer" tier (orphaned).** `hybrid_search.py`, `ingest_*.py`,
`vector_memory_setup.py`, `reset_audit_chain.py`, `pdf_util.py`, `extract_text.py` build/query a
standalone FAISS+SQLite RAG store and a tamper-audit table in **`orchestrator_memory.sqlite`** —
which **the live system no longer uses** (the live stores are under `data/`). Functionally complete
but effectively dead relative to the running product. **Footgun:** `reset_audit_chain.py` operates
on the legacy DB while the live verifier reads `data/aios_audit.db`, so it "succeeds" loudly while
having **zero effect on the chain the product verifies** — a silent no-op that looks like a fix.
`vector_memory_setup.py` `DROP`s its table with no confirmation.

### 3.5 Test suite

Three independent suites, **~654 green total, verified this session**:

| Suite | Result (verified) | Character |
|---|---|---|
| Backend pytest (`tests/`, 43 files) | **551 passed / 1 skipped** (169s) | Behavioral, fault-injecting, fakes-at-the-edges |
| Product vitest (`frontend/`, 11 files) | **65 passed** (~9.3s) | Classic libs + 2 workbench files |
| Lab vitest (`GAG demo/`, 5 files) | **38 passed** | Adapter/bus/sound/tier honesty contracts |

**The backend suite is the project's primary evidence-of-correctness gate and is genuinely strong**
(~85–90% of the cognition/security/memory/router surface), and **not mostly happy-path**: it
exercises fail-closed-to-RED on internal exception, ~12 scope-escape vectors, the audit
hash-chain with 4-thread/80-entry concurrency, a load-bearing golden vacuity guard (deliberately
drops a finding to prove the freeze catches drift), earned-autonomy streak-grant/instant-revoke,
and privacy invariants **asserted against raw SQLite bytes**. The linchpin is `conftest.py` setting
`AIOS_DATA_DIR` to a temp dir *before* `aios.config` is imported, so the whole run never touches
real `data/`.

**The "1 skipped" is environment-dependent, not broken** — it's the vector-shield
semantically-novel-injection test gating on embedding-model availability; on a provisioned host it
runs and passes. (Note: the prior `457`/`516` baselines quoted across docs are stale; the true
current count is **551**.)

**The weak leg is the product frontend** — ~34 non-test src files, ~10 test files; the 1875-LOC
`App.jsx`, `main.jsx`, and the large superbrain/workbench 3D surface are essentially untested by
unit tests (covered only indirectly by the lab tests + manual FIDELITY screenshots). **No
repo-wide coverage threshold is enforced anywhere** (no `.coveragerc`, no `--cov`, no vitest
coverage gate). Live/E2E proof lives in untracked `training_ground/` scripts outside the default
`pytest.ini` gate.

### 3.6 Config, infra, deploy

**Config (~95%, production-grade for the stated single-laptop target).** `aios/config.py` is a
genuine single source of truth: 60+ `AIOS_*` flags via typed accessors with local-first defaults,
`.env` auto-loaded on import, `DATA_DIR` created at import time, every subsystem reading its
tunables here and wired into FastAPI via `Depends(...)` so tests swap fakes. The privacy gate is
deterministic and unspoofable by a model: `AIOS_ROUTER_CLOUD_TASKS` is empty by default
(`auto` never routes to cloud), parsed once into a frozenset with unknown task names silently
dropped, and the hybrid LLM picker can re-order but never escape the allowed set. Secret hygiene is
layered and real (keys never persisted; the executor strips `*KEY*`/`*TOKEN*`/`*SECRET*`/`*BEARER*`/
etc. from every child env). The token-gated API hard-requires a ≥32-char token before it will boot
on a non-loopback host.

**Deploy/infra readiness is materially lower (~50–60%).** The security primitives for a hardened
deploy *exist* (token policy, CORS allow-list, hardened `DockerRunner` for the executor sandbox,
no-secret-persistence) but there is **no deployment artifact**: no `uvicorn.run` entrypoint
(the server is a hand-typed `python -m uvicorn aios.api.main:app`), no docker-compose/Procfile/
systemd unit, no TLS/reverse-proxy guidance, and **no CI** (`.github/` absent). A real footgun:
**`AIOS_API_HOST`/`AIOS_API_PORT` are dead for binding** — read only by the startup policy check
and CORS, never passed to uvicorn, so setting `AIOS_API_HOST=0.0.0.0` expecting a public bind
silently leaves you on loopback. `requirements.txt` is a flat freeze with no dev/optional split
(heavy ML deps mandatory even when embedding is disabled), and `Dockerfile.executor` installs the
*full* requirements into a sandbox that only needs Python+pytest (multi-GB image bloat).

---

## 4. How it all composes — the end-to-end request

This is the most important section: the subsystems are not a pile of features; they form one
control flow in which **cognition is sandwiched between deterministic layers it cannot bypass.**

### 4.1 An agentic turn (the forge: `POST /api/generate`)

1. **UI → SSE.** The operator types a directive in the Shell's `CommandLine` (or the classic
   chat box). `aiosAdapter.streamTurn` POSTs to `/api/generate` with `modelId:'auto'` and the
   shared `aios_session_id` (the same localStorage key the classic UI uses — both faces continue
   **one** backend conversation). Note the 3D experience has no model picker, so it can only ever
   run the backend's auto-route; model selection is a classic-only feature.
2. **Frame the turn (advisory).** The backend runs `AlignmentInterpreter` (a validated, redacted,
   explicitly **non-authoritative** understanding frame) and the **privacy-gated Router**
   (`_select_chat_client` → `_router_policy()` re-read fresh each call) to pick the provider/model.
   The chosen `(provider, model)` is announced **lazily** over the `route` SSE frame — only after
   the first real output, and re-announced on a mid-turn failover — so the badge never advertises a
   ranked-but-uninvocable primary. The adapter narrates this onto the bus as the **active-brain**
   badge.
3. **The cage: `ToolAgent` reason→act→observe (≤5 iters).** The local model proposes tool calls
   (robustly recovered from 4 prose shapes), but **every consequential action funnels through the
   security gateway** — most-dangerous-wins zone classification, fail-closed to RED on empty/
   unknown/exception. The adapter narrates each frame as cognition: `tool_call` → agent-dispatch
   + lobe lighting, `[VERIFY PASS/FAIL]` → knowledge-acquired verdict, `route` → active-brain.
4. **YELLOW → resumable approval.** A YELLOW action (anything real — pytest, edits, installs, git)
   pauses the *whole turn* with a `human_required` frame. The adapter raises the approval surface
   (the diff is the decision surface); `ApprovalSafetyNet` guarantees the AUTHORIZE button is
   always reachable above the organs (z-index ladder 55 < 60 < 62). AUTHORIZE replays the turn with
   the server-issued **single-use, session-bound token**; the server records the *exact* pending
   action and grants are **keyed by filepath and pre-applied before the model speaks**
   (`_pre_apply_grants` — the fix for the dropped-grant replay bug). REJECT only claims "rejected"
   when the server confirmed it.
5. **RED → refused, always.** A RED action is refused even if listed as approved
   (`execute_approved` re-classifies). Human approval can never authorize RED — stricter than a
   typed-token override.
6. **Write → snapshot → audit → apply → verify.** An approved write is snapshotted, **audited
   before it is written** (no ledger entry → no write), applied via atomic write confined to a
   single file, then **`_auto_verify` autonomously runs the file's sibling pytest** through the
   gated Verifier. The Verifier treats **exit code as authoritative truth**; the authoritative
   PASS/FAIL is fed back into the conversation so the model's next turn is anchored to evidence,
   not its own prose. A genuine failure fires reflection → a structured lesson into the mistake
   pool.
7. **Memory + learning loop.** Before the turn, relevant memory is recalled and tiered into
   "VERIFIED TRUSTED MEMORY" vs "UNVERIFIED PRIOR CHAT (use only as a lead)". After, the verdict
   drives `record_outcome` (development + skill-trail + curriculum evidence, keyed strictly off the
   verifier verdict), then `record_reuse` credits/stains recalled trails. The pheromone math is
   asymmetric and the DIRECT/REUSE evidence boundary means co-occurrence can never launder a
   candidate into "verified".
8. **Earned autonomy (OFF by default).** If `AIOS_EARNED_AUTONOMY` is enabled and a write *class*
   has crossed the verified-streak threshold (default 5 consecutive verified successes), that class
   auto-applies **without pausing for approval** — a distinct, audit-tagged hash-chain entry
   carrying the evidence. A single verified failure instantly revokes it. RED is structurally
   un-earnable. The adapter surfaces this as a topbar AUTONOMY count + a CAPABILITY EARNED event;
   because the auto-write never pauses, `ForgePorts` reads the on-disk workspace to show what was
   actually written. (Two independent paths can briefly disagree: the live `earned_autonomy` SSE
   frame fires immediately, while the every-poll `/development/autonomy` probe drives the
   persistent count — the count can lag the action by up to one poll.)
9. **Swarm (`swarm:true`).** The worker swarm builds a multi-file toolkit under the *same* gate;
   role-pass castes derive reviewer authority **from verifier evidence only** (`[VERIFY PASS/FAIL]`),
   never from model prose. The adapter narrates castes and counts auto-grants vs human approvals.
10. **Audit chain → back to the UI.** Every security-relevant decision lands in the SHA-256
    hash-chained ledger (redact-before-hash, cross-process integrity). The adapter samples
    `/api/v1/audit/verify` every 5 polls and raises **AUDIT CHAIN BROKEN** on tamper. The 20s poll
    of `/development/{trails,metrics,autonomy}` fires bus events only on genuine reinforcement /
    candidate→verified mastery / failure-weakening, which become MemoryGalaxy stars, region-pin
    metrics, and the autonomy ledger — closing the loop from real backend evidence back to the
    living 3D organism.

### 4.2 A conversational turn (the voice mind: `POST /api/v1/chat`, Slice 1)

New on `feat/jarvis-voice` (verified at `main.py:2138`). This is **conversation, not the agentic
forge**: `tools=None`, **no `ToolAgent` loop, no file writes**. It reuses the same cross-provider
router (privacy gate fully intact — `auto` stays local-only by default), injects real operator
facts + recalled memory under a Hinglish persona prompt, calls the chat client **once**, and
**fake-streams the reply word-by-word over the same SSE wire shape** (`route` → `text_chunk` →
`done`) so the existing UI reader works identically for local and cloud. User + assistant turns are
persisted to L2/L3 exactly like `/api/generate`. **There is no STT/TTS audio anywhere** — the
branch name "jarvis-voice" describes the conversational mind, not voice I/O; STT/TTS is the
deferred frontend modality.

---

## 5. What is real vs aspirational (the honest summary)

### Real and proven (production-shaped, end-to-end wired, tested where it matters)

- The **deterministic security foundation**: gateway, scope-lock, secret scanner, hash-chained
  audit ledger, approval capabilities, verifier, self-apply, rollback — solid, fail-closed,
  53+ tests, and it **earns** the "frozen core" label.
- The **supervised cognition loop** and **multi-store memory** with real hybrid retrieval and the
  exact blueprint formula — exceeds the blueprint's own self-assessment.
- The **stigmergic learning layer** — the most mature subsystem; principled pheromone math with
  test-pinned constants and a clean DIRECT-vs-REUSE evidence boundary.
- The **earned-autonomy bridge, worker swarm, multi-LLM hybrid router (Bedrock+Gemini+Ollama with
  a privacy gate), self-analysis T0–T4, and curriculum-driven learning** — all real surplus the
  blueprint never asked for, all backend-verified.
- The **two frontends**: the 3D superbrain Shell (default) and the classic IDE, both binding to a
  real backend over SSE with genuine honest-offline contracts; the integration Shell at root
  `:5173` works home↔workbench at one URL.
- The **operator tooling** that drove a real, audited 6/6-mastered curriculum learning proof and
  the earned-autonomy zero-approval proof against the same HTTP surface the human UI uses.
- A **551-pass backend suite** that tests contracts (fail-direction, no-secret-persistence, tamper
  precision, RED-not-grantable), not incidentals.

### Aspirational / deferred-by-plan / honest edges (named, not hidden)

- **Voice (audio) = 0%.** No whisper/piper/STT/TTS code or dependency anywhere. Only the text-only
  `/api/v1/chat` Slice 1 exists. (Blueprint scheduled voice for Phase 4 — deferred by plan.)
- **Knowledge-graph traversal = not built.** `facts.py` is a contradiction-aware flat triple store
  with no multi-hop/Neo4j. (Notably, the graph *was* once built in the deprecated `legacy_node/`
  generation and not ported — built-then-dropped, not never-attempted.)
- **Observability stack = not built.** No Prometheus/Grafana/docker-compose/`/metrics`; only an
  internal JSON `/development/metrics` endpoint that nothing scrapes.
- **Deploy story = doc-only.** No uvicorn entrypoint, no compose/Procfile/systemd/TLS, no CI; the
  `AIOS_API_HOST/PORT` flags don't actually bind.
- **Strong OS isolation = opt-in.** The hardened `DockerRunner` is real but the default host mode
  runs approved code as the backend user (the docstrings are candid about this).
- **The model is the ceiling.** Planning is advisory, calibration is a no-op on a cold DB, castes
  are "architecture proven / 7B-limited," and curriculum matching is exact-prompt-string — organic
  progression is narrow until a 14B+ local model or a semantic-match layer lands.
- **Frontend test coverage is lopsided**, and **no repo-wide coverage gate** exists.
- **Doc drift is the dominant non-code debt.** The pytest baseline is hand-copied (and stale) in
  ~7 docs; `AGENTS.md` still says "~75-80%" while newer docs say ~80-85%; the lab `PROJECT.md`
  marks shipped work as "Planned"; `frontend/README.md` is the stock Vite template; the running
  install's cloud posture (`ROUTER_CLOUD_TASKS=('reasoning','coding')`, Bedrock+Gemini enabled via
  the gitignored `.env`) diverges from the documented "local-only default" — only `RESUME.md`
  captures it.
- **Repo hygiene.** `legacy_node/` (a full dead parallel implementation), a dead root
  `hybrid_search.py` duplicate, orphaned `creator.txt`/`success.txt`/`chat-ui.html`,
  `websocket_security_update.md` documenting a WebSocket surface that doesn't exist, ~4.4 MB of
  committed brain textures, no TypeScript typecheck in the toolchain, and a 0-byte `.eslintrc.json`.

---

## 6. Bottom line for the next builder

You have a **real, coherent, internally-consistent supervised AI-OS** whose defining quality is
**intellectual honesty enforced as code**. The hard, unglamorous foundation — the security spine,
audit chain, approval capabilities, scope-lock, verifier, self-apply, the memory state machines,
the stigmergic learning — is genuinely solid and proven, and the backend **exceeds its own
blueprint**. The two frontends are real and live-bound, with the 3D superbrain Shell now the
official face and the classic IDE as a working fallback; both honor the "show only real data"
contract down to rendering `--` rather than a fabricated number offline.

The frontier is not about fixing what's broken — it's about three deliberate moves and a clean-up:
**(1)** widen the earned-autonomy bridge and make the container the default isolation where Docker
is present; **(2)** get a better brain (the 14B+ model / semantic-recall / forgetting gaps that
come with running longer); **(3)** turn the deferred edges into product — voice audio I/O on top of
the shipped `/api/v1/chat`, knowledge-graph traversal (a SQLite recursive-CTE closes most of it
without Neo4j), and a real deploy artifact + CI. And throughout: **collapse the doc drift to one
canonical, single-sourced test baseline** and quarantine the legacy/dead tier so a future reader
can never mistake `reset_audit_chain.py` for a fix or `legacy_node/` for canon.

Merge the two feature branches when ready; everything described here lives on `feat/jarvis-voice`
and is green at **551 passed / 1 skipped**.
