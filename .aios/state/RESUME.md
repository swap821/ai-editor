# RESUME MANIFEST

## Current goal
The AI-OS is a real, supervised, memory-driven cognitive system (see
`.aios/state/BACKEND_TRUE_PICTURE.md` — the 8-agent deep read; NOT an MVP).
Active front: extend its CAPABILITY (earned autonomy + worker swarm) and keep
the superbrain frontend worthy of it. Two CEOs/Chief Architects: Claude + Codex
(50/50, §III-A). Codex is OFFLINE, back ~2026-06-16 → documented pattern is
operator-authorized landing + POST-HOC Codex inbox review.

## Last completed and verified (2026-06-13, Claude session)
1. RECOVERED the limit-killed Fable micro-detail audit (132 findings) and
   shipped POLISH II–XI of the superbrain (sound, interaction a11y+visual,
   motion/tokens, signal+galaxy shaders, chrome alignment, glass rim+approval
   recipe, galaxy color-space, cortex casing, console rim+approval anchoring).
   All committed + ported byte-faithful; goldens are documentary
   (polish-ladder-complete.png). Held: approval-panel entrance, objective-bar
   scaleX, section-label weight (judgment calls).
2. BACKEND_TRUE_PICTURE.md — deep, honest architecture read (security spine,
   cognition core, multi-store memory, stigmergic learning, RAG production path
   + CAG-style recall-before-turn injection, self-apply).
3. EARNED AUTONOMY (the evidence->GREEN bridge): `aios/core/autonomy.py`
   AutonomyLedger; wired into ToolAgent's YELLOW seam + `main.py` make_agent;
   `GET/POST /api/v1/development/autonomy`. Opt-in (`AIOS_EARNED_AUTONOMY`),
   off by default, RED un-earnable, instant-revoke-on-failure, frozen spine
   untouched. 13 tests.
4. WORKER SWARM (ant-colony): `aios/agents/swarm.py` run_swarm (decompose -> N
   ephemeral gated workers -> synthesize; stigmergic via conversation+sandbox+
   trails; bounded by SWARM_MAX_WORKERS). Wired as the `swarm` request flag.
   5 tests.
5. LIVE-PROVEN both (backend on :8000, AIOS_EARNED_AUTONOMY=true, min=3):
   - Swarm built a REAL verified file: `training_ground/wordcount.py` +
     test (3 passed). 7B finished subtask 1, not subtask 2 (model-limited,
     architecture proven). Driver: `swarm_demo.py` (operator-authorized,
     curriculum-driver hard allowlist).
   - Earned autonomy GRADUATED live (`earn_demo.py`): streak 1->3 = earned,
     then turns 3/4/5 auto-granted writes with ZERO approvals, each VERIFY
     PASS. Ledger: create_file:training_ground/*.py = earned, succ=6.
   Full suite: 456 passed, 1 skipped. Pushed to swap821/ai-editor master.
6. COORDINATION CATCH-UP done: routed earned-autonomy-and-swarm-v1 (builder
   claude/reviewer codex), claimed lease -> hash-pinned handoff (msg 17) +
   review-request (msg 18) to Codex; marked his msg #8 read; gitignored .aios/tmp.
7. PRESERVED all of Fable 5.0's Jun 9-12 work: parent (backend+docs, 66 commits)
   + lab superbrain both pushed; his pre-lab .agents/ build-notebooks folded into
   the lab repo (build-history/) + pushed (off-machine, ab57a99); visual_test/
   harness in a new local-only GAG demo/ repo (b3bb917) — operator to push to
   swap821/gag-demo himself (agent blocked by exfil guardrail; one-liner given).
8. SUPERBRAIN SHOWS ITS CAPABILITIES (lab faaf087 / product 1967fea): API forwards
   the earned_autonomy SSE event (e9e9e09); aiosAdapter publishes AUTONOMOUS ACTION
   (the brain acts on its own earned trust) + CAPABILITY EARNED (a class graduates)
   + getAutonomy() getter. LIVE-PROVEN: ledger persists across restart (earned:1),
   an earned create_file streams `event: earned_autonomy`. 26 lab + 456 backend tests.

## DONE earlier (2026-06-13, on master + pushed)
- **Whole-ai-editor 8-lens analysis** (commit 75406b1): `SYSTEM_TRUE_PICTURE.md`,
  `HIDDEN_KNOWLEDGE.md`, refreshed `PLAN.md`, `BACKEND_TRUE_PICTURE.md` (doc set).
  P0: live Bedrock token in `frontend/.env` (gitignored, never committed; rotate+relocate, PLAN H1).
- **FUTURE_FRONTIER.md** (725 lines, commit 0d95b01): north-star above PLAN; spine =
  Evidence-Locked Self-Improvement Flywheel; honest headline = frontier-grade ENGINEERING,
  not yet a frontier AI SYSTEM (gates = intelligence/7B + isolation, not architecture).

## ACTIVE FRONT (2026-06-13): SUPERBRAIN ⇄ CLASSIC INTEGRATION  [MERGED + pushed to master 2d0d8d8 (branch feat/superbrain-integration retained)]
Operator-directed: fold the classic IDE into the superbrain as ONE app. Canon tag
`pre-integration-canon-v1` = rollback. Design **A** (superbrain is the LEAD: home form +
manufacturing form). Docs: `.aios/state/SHELL_REDESIGN.md` + `NERVOUS_SYSTEM_REDESIGN.md`;
memories [[superbrain-core-theme]] (his soul-line) + [[superbrain-integration-plan]].

**THE UNLOCK (operator-clarified):** the brain's NERVOUS SYSTEM is its CONTROL BUS — the
wires PLUG INTO ui PORTS (left console x=-4.8, right x=+4.8, spinal=command bar), carry
data packets, surge on uBurst, quiet on uHold (`NervousSystem.tsx`). Every tool, present or
future, is a PORT. The first band-dock FAILED because it HID the panels the nerves plug into
(severed them) AND a shorter band re-projected the hardcoded nerve tips (they dangle).

**DONE + verified** (build clean, 29 product tests green; ONE canvas; canon scene+nerves
byte-unchanged; home/`?ui=superbrain` + `?ui=classic` untouched):
- **Phase 0**: canon tag + `frontend/FIDELITY_BASELINE.md`.
- **Phase 1**: unified backend boundary — `vite.config.js` define bridges `VITE_*`→
  `NEXT_PUBLIC_*` (one base URL); classic learns `earned_autonomy`; superbrain adapter gets
  Bearer auth + shared `aios_session_id` (lab edit + byte-sync; closes the P0 default-UI auth gap).
- **Phase 2 = THE EMBEDDED FORGE** (operator verdict: "impressed wow"): editor + preview
  mounted as in-scene drei `<Html>` AT the canon nerve ports (-4.8 / +4.8), non-`transform`
  + inner `translate(-50%,-100%)` = byte-exact canon anchor, so the REAL nerves plug into real
  Monaco + LivePreview; ports FLARE on real cognitionBus events; command line at the spinal
  rendezvous. The brain stays FULL/canon-framed (no band). ONE lab touch = a geometry-neutral
  `children` slot on `WorkspaceCanvas` (lab commit 90e0394, synced; no re-golden). Product
  files: `frontend/src/workbench/{ForgePorts.jsx, forge.css, CommandLine.jsx, shell.css,
  manufacturing.css}`, `superbrain/SuperbrainShell.jsx`, `main.jsx` (`?ui=shell`). Commit 29824d8.

**HOW TO EXTEND (add a future tool-port):** the nerves are the universal control plane.
Re-tenant a canon port (product-side: new `<Html>` at -4.8/+4.8/spinal) OR add a real 4th
nerve (lab `NervousSystem.tsx` `leftTargetX/rightTargetX` + a 4th `addWireBundle` + move the
matching `SuperbrainHUD` `<Html>` together + `npm run port` + FULL FIDELITY gate). Light any
port by `publishCognition` on the bus. See `NERVOUS_SYSTEM_REDESIGN.md` §3/§6.

## WHAT'S NEXT — the plan (decided 2026-06-13, from the full session)
Integration LANDED on master (4226b4c). Three fronts, in priority order. Standing rule:
restate the chosen item and WAIT for explicit OK before writing code; ~90% honest target.

### A. FINISH THE EMBEDDED FORGE (the live, loved front — complete it before pivoting)
A1. **Truthful content channel** ✅ DONE + FIXED (master 84f1976): the forge editor syncs to the
    REAL `training_ground` workspace via `GET /api/v1/development/workspace` (read-only, confined to
    training_ground, newest-first, capped) on mount + after each turn (debounced on bus events) —
    **PATH-INDEPENDENT**, so earned-autonomy auto-writes AND approval writes AND edits all surface.
    The demo's bug (operator-caught): with AUTONOMY ⚡1, a create AUTO-APPLIES via the earned path
    (emits `earned_autonomy`, not `human_required`) so the approval-only A1 never fired — `hello.py`
    wrote to disk but never showed. The approval-path preview (proposed content during a pause) stays.
    ✅ VERIFIED (operator: "editor shows the files now", master b8e5661). THE REAL BLOCKER was a STALE
    uvicorn on :8000 serving OLD code (the new endpoint 404'd → forge fell back to samples) — ALWAYS
    start the backend with `--reload` so edits hot-load. Sync hardened with bounded re-read bursts
    (350/1500/3500ms, beats the earned write-race) + a manual ⟳ + active-tab preservation. (Diagnosed
    the demo by frame-extracting it via ffmpeg — no audio.)
A2. ✅ DONE (master 78bcf87): editor port bumped to 500x412 (preview 410x330) for real multi-file
    code. Final anchor/size + GPU feel = operator's browser eyeball (camera-projection-dependent).
A3. ✅ DONE (master 78bcf87): a YELLOW write that PAUSES shows the proposed file in the editor + an
    amber "PENDING · <file> — not applied" banner (cleared on resolve); ported `.approval-panel`
    carries Approve/Reject + diff; on approve the workspace re-sync shows the applied file. RED hard-blocked.
    (Note: with earned-autonomy ON, writes auto-apply — no pause — so the banner shows when autonomy is OFF.)

THE EMBEDDED FORGE IS COMPLETE (A1+A2+A3 done + verified). Branch merged to master.

### B. CHEAP HIGH-SEVERITY HYGIENE (alongside A)
B1. **Rotate + relocate the live Bedrock token** (`frontend/.env`) — P0 security, ~30min (PLAN H1).
B2. (opt) clean the 2 untracked `training_ground/test_auto_*.py` assert-True stubs + tracked cruft
    (`success.txt`/`creator.txt`/`chat-ui.html`/`websocket_security_update.md`) (PLAN H2).
B3. (opt) Tier-1 doc-currency: stale 375/1 test baseline in README/AGENTS/START_HERE/KICKOFF → 458 (PLAN H3).

### C. THE FRONTIER — forge done, now here (per FUTURE_FRONTIER queue discipline)
C0. **MULTI-LLM LIBRARY** — operator's chosen direction; PLAN in `.aios/state/MULTI_LLM_PLAN.md`.
    The brain picks the best model per task across local (Ollama) + Bedrock + Google Gemini (gcloud ADC).
    Decided: routing = **HYBRID** (local LLM picks among policy-allowed candidates, can't override the
    deterministic privacy/cost gate; deterministic fallback; evidence-calibrated; cage verifies regardless).
    Gemini access = gcloud / Vertex AI (ADC), no key on disk.
    ✅ **DONE — the hybrid router core landed** (pure + tested, NOT yet wired into main.py):
      `aios/core/router.py` — `Provider` (data, no client), `Policy` (operator-owned gate),
      `policy_allows`/`candidates`/`route` + `route_model_id`. `route()` is a pure fn of
      (task, providers, policy, metrics) + one injected `picker` (the local LLM). Default `LOCAL_FIRST`
      policy = cloud OFF (empty `cloud_tasks`) → BEHAVIOUR-PRESERVING (local-only) until the operator
      sets the privacy boundary. `tests/test_router.py` (18 tests) pins: privacy gate, "LLM can never
      escape the policy", deterministic fallback, cost ceiling, evidence calibration. Full suite 476 pass / 1 skip.
    NEXT phases: P0 secure Bedrock cred to backend env (= PLAN H1) → P1 add `GeminiClient` (Vertex/ADC,
    function-calling → agent message shape) → **P2 WIRE router into `_select_chat_client` (main.py:1074)**
    behind the default LOCAL_FIRST policy (behaviour-preserving) + a config-driven privacy boundary →
    P3 evidence-calibration from dev-metrics + UI active-brain badge. The cage verifies regardless of
    provider (soul intact); every call audited; local-first DEFAULT, cloud = per-task policy-gated escalation.
    OPEN OPERATOR DECISION (gates P2 wiring going live to cloud): which task classes may leave the machine
    (`Policy.cloud_tasks`). Until set, the router stays local-only even once wired.
C1. **Brain ceiling** (PLAN S1: local quant + 14B) — addressed largely by C0 (frontier access now); + semantic-recall.
C2. **Default-strong isolation** (PLAN S2: hardened Docker default where available).
C3. The three genuine gaps: voice (G1), knowledge-graph traversal (G2), observability (G3); + the
    near-term proof artifacts (Refusal Reel + Cage Conformance Spec, both [near]).

RECOMMENDATION: do **A (finish the forge) + B1 (token)** first — the forge is live and loved, and the
token is cheap+severe; pivot to C when ready for the bigger capability work. Full roadmap:
`.aios/state/PLAN.md` (blueprint-vs-reality) + `FUTURE_FRONTIER.md` (north-star above PLAN).
Run: `cd frontend && npm run dev` → `http://localhost:5173/?ui=shell` (Enter workbench).

(Background — already complete this session:)
Earned-autonomy feature is now COMPLETE end-to-end + the brain SHOWS it:
- AUTONOMY ⚡N topbar readout (lab dc8116c, additive, live-verified);
- earned grants AUDIT-TAGGED as distinct 'earned-autonomy' hash-chain entries
  with evidence (lab 0e6b253, 457 tests);
- swarm/role-pass caste NARRATION in the terminal (lab 7a89ce1).
Live backend ON :8000 (AIOS_EARNED_AUTONOMY=true, ledger persists earned:1).
DEFERRED (deliberately, low ROI): full 3D swarm-worker viz + a transient SWARM
topbar indicator — swarm turns are rare + 7B-limited; revisit with a 14B+ model.
OPERATOR DECISIONS: (a) whether earned autonomy ships ON by default (config
default is OFF); (b) push GAG demo/ backup to swap821/gag-demo (one-liner given).
Codex reviews earned-autonomy-and-swarm-v1 (handoff msg 17/18) when back ~06-16.

## Open approvals/blockers
- Lease discipline: did all the above with `active_writer: null` (no worktree
  lease held) — §III-A wants the builder to hold it. Operator-authorized, but
  note the gap; reacquire/handoff going forward.
- Codex inbox msg #8 (2026-06-10, correct-resume-stale-runway): unread; his
  process note = "released without hash-pinned handoff, no formal verdict".
- Earned autonomy is ON in the running backend (min=3). Default config is OFF.
- Demo artifacts on disk: swarm_demo.py, earn_demo.py, training_ground/
  wordcount.py + test_proof{1..5}.py (trivial earn-demo files).

## Runtime
Brief: `.venv\Scripts\python agent_coord.py brief --agent claude`
Backend: `.venv\Scripts\python -m uvicorn aios.api.main:app --port 8000`
  (live now with AIOS_EARNED_AUTONOMY=true, CORS incl :3000)
Frontend (lab): `cd "GAG demo/gag-orchestrator"; npm run dev` (:3000)
Tests: `.venv\Scripts\python -m pytest -q`  (baseline 456 passed, 1 skipped)
Autonomy ledger: `GET /api/v1/development/autonomy`
Swarm: POST /api/generate with `"swarm": true`
True picture: `.aios/state/BACKEND_TRUE_PICTURE.md`
