# GAGOS Feature-Flag & Reachability Recommendations

**Repo:** `C:\Users\kumar\ai-editor` · **Prepared:** 2026-07-05 · **Scope:** every default-off flag in `aios/config.py`, plus a full backend-route-to-frontend-UI reachability audit, both independently re-verified against the live codebase before being included here.

This document only includes findings that survived adversarial re-verification. Anything flagged as an overclaim, refuted, or unconfirmed in the verification pass has been left out or explicitly corrected below.

---

## 1. Flip these on now

These flags were independently re-verified as either genuinely inert (no production code path consumes them yet) or mechanically safe (local-only, caution-only, or read-only). Flipping them costs nothing and, for the Sovereign Roadmap cluster, gets you real endpoints instead of 404s.

- **`AIOS_COUNCIL_KING_REASONING`** — Set `AIOS_COUNCIL_KING_REASONING=true` (or flip its default to `True` in `aios/config.py`). Note: this alone will not yet change anything visible — `reason_king()` (`aios/council/king_reasoning.py`, called from `council_orchestrator.py:202-208`) also needs a `king_complete` LLM callable constructor-injected, and nothing in production wires that in today (the same not-yet-wired pattern already documented for the sibling `COUNCIL_REASONING` flag). There's no downside to arming it now so it's live the moment that wiring lands.

- **`AIOS_CRAG_LLM_JUDGE`** — Set `AIOS_CRAG_LLM_JUDGE=true`. Confirmed local-only (`_crag_llm_judge` calls `get_ollama_client()`, never a cloud client) and caution-only — it can only lower a hit's confidence score, never rescue a bad one. Pure local latency cost, no privacy exposure.

- **`AIOS_PHEROMONE_ENABLED`** — Set `AIOS_PHEROMONE_ENABLED=true`. Confirmed that `PheromoneStore(...)` is only ever constructed inside `sovereignty.py`'s own route handlers — nothing in the council/worker pipeline deposits pheromones automatically. Flipping this turns `/api/v1/pheromones/*` from 404 into a real (initially empty) endpoint. No behavior change to the organism.

- **`AIOS_LIVE_SURFACE`** — Set `AIOS_LIVE_SURFACE=true`. Same pattern: `LiveSurface(...)` is only constructed in route handlers, nothing auto-populates it. Safe.

- **`AIOS_ROLLBACK_REGISTRY`** — Set `AIOS_ROLLBACK_REGISTRY=true`. This is a separate queryable *catalog* from the always-on rollback engine (`aios/agents/rollback_engine.py`, which needs no flag). Nothing auto-registers a snapshot into this catalog yet, so enabling it just exposes an empty, safe registry.

- **`AIOS_POLICY_ENGINE`** — Set `AIOS_POLICY_ENGINE=true`. Confirmed `PolicyEngine.enact()` is a pure database status write with zero downstream hook — `aios/security/gateway.py`'s `classify()` and the executor never consult enacted policies. Today this is governance record-keeping with no behavioral effect, verified directly against the gateway code.

- **`AIOS_QUEEN_SERVICES`** — Set `AIOS_QUEEN_SERVICES=true`. The `QUEEN_SERVICES` registry starts empty and nothing calls `register_service()` in production (only in tests). Flipping the flag changes the endpoint's response from 404 to `{}` — nothing else.

**One caveat that applies to the whole Sovereign Roadmap cluster** (pheromones, live surface, rollback registry, policy engine, queen services): flipping these flags makes the *backend* endpoints real, but none of them have any frontend hook today (see Section 4) and none of them auto-populate from real council/worker activity. Turning them on is safe, but don't mistake "flag is on" for "feature is live and doing something" — it only removes the 404.

---

## 2. Must stay gated

These have a real, specific reason to remain off — not just "nobody's gotten to it yet."

- **`AIOS_CRAG_EXTERNAL`** — This is "privacy-gated by design — it's the door from 'local-only' to 'network/cloud call.'" The project's own spec is explicit: *"GAGOS is local-first and privacy-first... never a mandatory web call, opt-in, and skipped entirely in local-only mode."* This is the master switch for every boundary-crossing CRAG source; it should only be flipped as a deliberate privacy decision, not a default.

- **`AIOS_CRAG_WEBSEARCH`** — Confirmed as "the most literal 'opt-in because it leaves the machine' flag in the codebase — actual outbound HTTP to a third-party search API with the query content." Real internet egress with your query text attached. Leave off.

- **`AIOS_TRUST_PROXY_HEADERS`** — "Trusting proxy headers without an actual reverse proxy in front lets any caller spoof their apparent IP and bypass the loopback-only restriction." This isn't an incomplete feature, it's a correct security default: "should stay off by default regardless of this audit's goal." Only turn this on if you actually stand up a trusted reverse proxy in front of the API.

- **`AIOS_ENABLE_DOCS`** — Standard "don't expose your API schema/attack surface by default" hardening. "Enabling it doesn't add capability so much as introspection surface." No functional loss from leaving it off.

---

## 3. Needs real engineering before enabling

These are not simple flips — enabling them today would either silently misbehave or introduce a real risk that hasn't been closed yet.

- **`AIOS_COUNCIL_CRITIQUE`** — Enabling this is not cosmetic. `council_orchestrator.py`'s `_enrich_worker_ledger()` calls `has_blocking_verdict(verdicts)` over the *full* verdict list including the Critique verdict — a `defer` (which `CritiqueQueen` returns whenever its cautions fire) flips `RunLedger.status` to `"failed"` **even after the worker already completed real work**. Worse, its "coverage" check is brittle: it looks for whether a verification command literally contains the changed file's basename as a substring. Any legitimate full-suite command like `python -m pytest` (no per-file args) won't contain the basename and will trigger a false "insufficient verification" caution — downgrading a genuinely-passing mission to `needs_revision`/`failed`.
  **Work needed:** fix the coverage heuristic in `aios/council/queens/critique.py` to recognize full-suite verification commands before defaulting this on, or it will cry wolf on completely normal CI runs.

- **`AIOS_WORKER_REASONING`** — The adversarial pre-merge fixes (empty-verification `ContractViolation`, `WORKER_MAX_FILE_BYTES` cap) are real and hold. But three things still need closing before this should be a default:
  1. The LLM worker's own pass/fail check in `_run_llm_worker` is a bare `returncode == 0` with no strength requirement — a trivial `verification_commands` entry like `echo ok` is sufficient for the worker to report GREEN. The King's report only adds a *soft warning* for below-floor strength; it still recommends approve/observe.
  2. The container backend (the default, fail-closed path) needs Docker actually installed and running. On a bare Windows dev box with Docker not running, every mission using this flag fails-closed silently — correct behavior, but it means the flag alone accomplishes nothing until Docker Desktop is stood up.
  3. A real compounding risk: `aios/council/reasoning.py:108-109` lets the Planner's injected LLM propose its own `verification_commands`, unioned into the contract. If a Planner LLM is ever wired in (see Section 1's `king_complete` note — the same class of wiring) while `WORKER_REASONING` is on, the same model that authors a code change could also author the check that "verifies" it — a self-grading path with no dedicated guard against it today.
  **Work needed:** enforce a verification-strength floor at the worker's own gate (not just a King-report warning), confirm Docker is provisioned, and require at least one operator- or deterministically-supplied verification command whenever an LLM-authored plan is in play.

- **`AIOS_CRAG_CLOUD`** — The "inert without cloud creds" framing is mechanically true for a fresh install, but not for this deployment: this operator already has Bedrock/Gemini configured, with the router already defaulting reasoning/coding tasks to cloud. On this box, flipping `AIOS_CRAG_CLOUD` is not a no-op second privacy gate — it will actually route memory-gap query content to whichever cloud client is already active.
  **Work needed:** this needs an explicit, scoped privacy decision for this specific deployment (not a blanket flip) — at minimum, confirm what query content would be sent to the cloud model before enabling, since the "no creds configured" safety net that makes this flag inert elsewhere doesn't apply here.

- **`AIOS_INJECTION_VECTOR_SHIELD`** — The mechanism itself checks out: it's fail-safe (embedder error → `False`, regex stays authoritative) and deterministic (fixed curated phrase set + cosine threshold, no LLM judgment), and the original "avoid loading torch" cost argument is confirmed stale — `torch`/`sentence-transformers` are already mandatory base dependencies for memory/CRAG embeddings, so there's no new dependency cost to enabling it.
  **Work needed:** what's unverified is real-world false-positive behavior. This shield can reclassify a request as RED, and under this repo's own RED-zone hard-block policy, a RED classification is refused even after approval, with no override. Before defaulting this on, validate the curated phrase list and cosine threshold against representative real operator command traffic to rule out a false-positive RED block of a legitimate command — the design is sound, but it hasn't been exercised against this operator's actual usage patterns yet.

---

## 4. Backend capabilities the frontend can't reach

Confirmed via a full trace of every backend route against every fetch/axios call site in the live render tree (`main.jsx` → `SuperbrainApp.jsx` → `GagosChrome.jsx` + `CouncilDashboard.jsx` + the 3D scene). Each of these has a real backend capability and zero UI path today. Suggested hooks are scoped the same way as the recent chat-model-selector fix — one small control added to an existing component, not a new subsystem.

- **Swarm / role-pass has no trigger.** `GenerateRequest.swarm` / `.role_pass` (`aios/api/main.py:1049-1053`, gating `run_swarm`/`run_role_pass` at `main.py:3638-3647`) default to `False`, and the sole production caller — `streamTurn()`'s request body in `frontend/src/superbrain/lib/aiosAdapter.ts` (~line 302) — never sets either field. The `intentHint === 'swarm'` check in `GagosChrome.jsx:1135` only picks an icon glyph; it never touches the request. The backend's multi-caste swarm narration is fully wired once triggered — it just can never be triggered from the shipped UI.
  **Hook:** add a small toggle chip next to the command bar in `GagosChrome.jsx` (near the existing `intentHint` logic) that sets `swarm: true` (or `rolePass: true`) on the body passed into `streamTurn()`. One boolean, one checkbox.

- **Self-Analysis proposals have no UI at all.** Three live endpoints exist — `GET /api/v1/self-analysis/proposals`, `POST .../apply`, `POST .../reject` (`aios/api/main.py:2206-2253`) — and a full case-insensitive grep of `frontend/src` for `self-analysis`/`self_analysis`/`selfAnalysis` returns zero matches anywhere.
  **Hook:** add a collapsible "Self-Analysis" list inside `CouncilDashboard.jsx`, reusing its existing mission-review list/approve/reject pattern, backed by three new small `aiosAdapter.ts` functions: `fetchSelfAnalysisProposals()`, `applySelfAnalysisProposal(id)`, `rejectSelfAnalysisProposal(id)`.

- **The entire `sovereignty.py` governance/stigmergy layer is invisible.** All 24 routes in `aios/api/routes/sovereignty.py` — pheromone deposit/reinforce/decay, runtime-surface emit/sweep, rollback registry, audit-anchor verify/history, and the full policy propose→vote→enact→suspend workflow — have zero references anywhere in `frontend/src`, confirmed by an OR-grep across every path fragment plus an independent cross-check against every real `fetch(...)` call site in the frontend.
  **Hook:** don't build all 24 controls at once — start with the handful of read-only GETs (pheromone surface, runtime surface, runtime rollbacks, audit anchor, policy current/chain) as a single new read-only "Sovereign State" tab in `CouncilDashboard.jsx`. This is also what makes the Section 1 flags actually visible instead of just returning JSON to curl.

- **Curriculum proposals have no review UI.** `GET/POST /api/v1/development/curriculum`, `GET .../proposals`, `POST .../proposals/accept` have no frontend caller anywhere, even though `curriculum.record_matching(...)` (`aios/api/main.py:3626-3633`) runs unconditionally inside `/api/generate` and its resulting `skill.mastered` SSE frame *is* genuinely consumed and narrated via `cognitionBus`.
  **Hook:** add a pending-proposals badge to `TrustHalo.jsx` (which already polls `/api/v1/development/metrics`) with a one-row accept action, reusing the same mote-approve pattern `MemoryHalo` already has for pending facts.

- **`SuperbrainHUD.tsx` is dead code carrying working, unreachable controls.** Grepped every reference outside its own file — the only hits are type-only `CognitiveMode` imports in `NeuralAura.tsx`, `SuperbrainScene.tsx`, and `WorkspaceCanvas.tsx`. It is never mounted, but it still contains working calls to `sendDirective`, `previewIntent`, `fetchOnboardingState`, `fetchOperatorModel`, and `getAutonomy`.
  **Action:** either delete the file outright, or if the `getAutonomy`/autonomy-revoke control is wanted, port just that one control into `GagosChrome.jsx` or `TrustHalo.jsx` rather than resurrecting the full ~2000-line component.

---

## 5. Connection issues — signals the being's nervous system never hears

This is a structural gap, not an incidental miss: the frontend's single documented nervous-system entry point is `publishCognition`/`subscribeCognition` in `frontend/src/superbrain/lib/cognitionBus.ts`. An entire class of real backend signal — the swarm/ant-colony lifecycle — never reaches it.

**Backend side** (`aios/agents/swarm.py:222` caste_start, `:234` cloud_route, `:377` swarm_plan, `:456/484/495` caste_end emit sites), forwarded to the SSE stream via `aios/api/main.py:3775, 3779, 3791`. The backend faithfully narrates the full decompose → dispatch-castes → cloud-route → synthesize swarm turn over SSE.

**Frontend side** (`frontend/src/superbrain/lib/aiosAdapter.ts:435-450`): the SSE switch statement does have a `case` for all four (`swarm_plan`, `caste_start`, `caste_end`, `cloud_route`) — but each one hands off to `startSwarmPlan()` / `startSwarmCaste()` / `endSwarmCaste()` / `markSwarmCloudSubtask()` in a separate store, `swarmHUDStore.ts`, which has **zero import of `cognitionBus`** anywhere in the file. Confirmed further: `cognitionBus.ts`'s own `CognitionEventType` union (lines 13-56) has no swarm- or caste-shaped member at all — the nervous system's vocabulary has no slot for this signal, so this isn't a dropped case, it's an absent type.

The one place a bridge could plausibly exist — `SuperbrainReactiveEffects.jsx`, which imports *both* `subscribeSwarmHUD` and `subscribeCognition` — was checked in full and confirmed to use the two subscriptions for entirely disjoint effects (cloud-route lightning / caste-orbit motes vs. a verify-pass aurora flare keyed on `event.type === 'verify'`). No bridge exists.

**Net effect:** a swarm turn can run its complete multi-caste, cloud-routed lifecycle, and the organism's core cognition bus — the thing every 3D body/scene component listens to — never fires once for it. Only the narrow `SwarmHUD` widget knows it happened at all.

**What closing this would take:** add a swarm/caste member to `CognitionEventType` in `cognitionBus.ts`, and have the four `aiosAdapter.ts` cases (lines 435-450) call `publishCognition` in addition to their existing `swarmHUDStore` calls — the narration data is already flowing correctly, it just needs a second, minimal fan-out into the bus the rest of the being actually listens to.