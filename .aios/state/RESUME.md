# RESUME MANIFEST

## ACTIVE FRONT (2026-06-15 late): NEXT-GEN 3D ELEVATION + PREMIUM-WORKING FRONTEND
Deep research DONE + committed: `.aios/state/SUPERBRAIN_NEXTGEN_DESIGN.md` ([[nextgen-3d-design-direction]])
+ `.aios/state/PREMIUM_FRONTEND_PLAN.md` (whole-frontend premium-vs-demo audit, waves W0-W6).
Operator: "keep working until the final GOAT version, full trust, use ultracode workflows"
([[workflow-default-working-style]]). Two tracks built in parallel via supervised workflows.

⚠️ **USAGE/SESSION LIMIT HIT ~2026-06-15 (resets 4:50am Asia/Calcutta)** — killed the W2 workflow's
implement+verify agents mid-run; Bash classifier also briefly unavailable. Resume after reset.
See [[workflow-limit-recovery]]: resume workflows via resumeFromRunId (journal cache), don't relaunch fresh.

### CANON TRACK (lab-only, gitignored, NONE ported yet — needs operator browser review + guard break-glass)
The canon "living brain" milestone is BUILT in the lab (1a→2b), a coherent gorgeous whole:
- ✅ Phase 0: canon tag `pre-nextgen-canon-v1` pushed (rollback).
- ✅ 1a voice-speaking brain pulse (cognitionBus type + SuperbrainHUD TTS publish per word-boundary +
  SuperbrainScene wave/burst reaction).
- ✅ 1b volumetric god-rays (workflow): `<GodRays>` + emissive teal sun-proxy parented to the brain,
  driven by uBurst/uHold, high-tier, pre-AgX slot. SuperbrainScene + PostFX. Both verifiers passed; vitest 38.
- ✅ 2a living flesh (workflow): cortex fresnel rim + interior light-bleed (fake SSS) using the region's
  OWN color desaturated 50% (no new hue), driven by uBreath/uBurst. SuperbrainScene. Verifier passed; vitest 38.
- ✅ 2b synaptic dust (workflow): new SynapticDust.tsx — single-draw-call vertex-shader curl-noise
  (2000/1000/400 by tier, off on low), divergence-free, canon teal, additive, reduced-motion-safe.
  Mounted at scene root. 1st verifier PASSED (detailed FIDELITY checklist); **2nd verifier died w/o emitting
  + I couldn't re-run vitest (classifier down) → RE-CONFIRM 2b FIDELITY + re-run lab vitest on resume.**
- **OPERATOR REVIEW (FIDELITY, his browser):** `cd "GAG demo/gag-orchestrator"; npm run dev` → :3000 (+
  backend `.venv\Scripts\python -m aios`). See the whole milestone: brain speaks-pulses + god-rays + living
  flesh + churning dust. Bless or tune (every effect has documented tuning knobs in its workflow output).
- **THEN port:** canon-freeze guard now has break-glass — port with `npm run port` then commit using
  `python tools/check_canon_frozen.py --allow-canon` (operator-authorized; default still blocks accidental edits).
- ⏭ Canon NEXT after his review: Phase 3 (voyage — nebula depth + camera; camera is the riskiest-blind, do
  with his feedback) → Phase 4 (truth-in-light: route-privacy tint, earned-act pulse, swarm mesh, star-birth).

### PRODUCT TRACK (premium-working, product-only — shipped to feat/renovation-p0)
- ✅ W0-1 killed the fabricated "Amazon Bedrock connected" greeting (the one outright lie) → honest greeting.
- ✅ W0-2 deleted dead code (BuildFeed.jsx, Workbench.jsx; build-confirmed unused).
- ✅ W0-3 aria-label on ForgePorts ⟳ refresh button.
- ⏳ W0-5 (define --sb-band-h) DEFERRED: visual call on superseded band-dock layers — needs shell render
  context + his eyes. W0-4 (delete specgloss.png) SKIP: it's a FROZEN canon texture (his asset) — needs his OK.
- 🟡 W2 honest-states (workflow wf_7d03efc4-550) — **SPEC DONE, IMPLEMENT KILLED BY USAGE LIMIT.** The spec
  (useOrganFetch hook design + organ adoption + empty/offline/error states + cold-offline fix) is in the
  workflow result. **RESUME:** `Workflow({scriptPath: ".../honest-states-w2-wf_7d03efc4-550.js",
  resumeFromRunId: "wf_7d03efc4-550"})` — the spec agent is cached; implement+verify re-run live.
- ⏭ Product NEXT: finish W2 (resume) → W1 (stylesheet/a11y substrate: extract App.jsx 142 inline styles +
  focus-visible + reduced-motion + ARIA — the unlock) → W3 (voice end-to-end finish) → W4 (responsive) →
  W5 (error boundaries, code-split, typecheck/CI, self-host Monaco) → W6 (coverage). Per PREMIUM_FRONTEND_PLAN.md.

LAB CAVEAT: all canon-track edits live in the gitignored lab (GAG demo/gag-orchestrator). Operator should
push the lab to swap821/gag-demo so a fresh clone's `npm run port` stays consistent.

## PRIOR FRONT (2026-06-15): WHOLE-SYSTEM RENOVATION — first-8
Plan: `.aios/state/RENOVATION_PLAN.md` (importance-ranked, reconciled under
FUTURE_FRONTIER). Branch `feat/renovation-p0` (off `feat/jarvis-voice`); PR #12
(feat/jarvis-voice → master) is open for the operator to merge. 17 calendar
events scheduled (IST). Per-item discipline: read → edit → test (`.venv\Scripts\
python -m pytest -q`) → commit → push.

First-8 order + status:
1. ✅ P1-1 push (feature branches to origin).
2. ✅ P0-1 CORS guard (commit 36fa1f7) — `_validate_cors_origins`, narrowed methods/headers.
3. ✅ P0-6 entrypoint (96e7965) — `python -m aios`, host/policy lockstep.
4. ✅ P0-2 + P0-5 legacy quarantine (53eea10) — `legacy/` + README; dead root-DB scripts moved.
5. ✅ P1-10 doc sweep (6d967c9) — live test-count language; `python -m aios`; real frontend README.
6. ✅ P0-7 input-shield /api/v1/chat (9a1dcd2) — transcript max_length=8000 (422) +
   per-session 30/60s flood throttle (429); 5 tests. Suite 561 pass / 1 skip.
7. ✅ The frontend pair (lab-first + ported; canon 3D untouched; frontend vitest 72 pass):
   - P1-3 session-id single-source (commit a777993): one getSessionId() (read-or-create-persist,
     SSR-safe) in superbrain/lib/sessionId.ts; aiosAdapter + ConversationPort + IntentPort + classic
     App.jsx all import it. Kills the read-only-organ-vs-owner fork. +4 tests.
   - P0-3 approval single-source-of-truth (commit 88b0a73): the adapter's pendingApproval is now an
     OBSERVABLE (subscribePendingApproval delivers current truth on subscribe + on every change via a
     single setPendingApprovalState writer); the HUD binds the actionable panel to it, not to the
     transient 'approval-required' bus event. A genuine pause is ALWAYS actionable. +3 tests.
     NOTE: redesigned mid-flight to live ENTIRELY in non-frozen files — the plan named
     WorkspaceCanvas.tsx:184-187 but components/canvas/** is canon-FROZEN (check_canon_frozen.py), so
     the reliable-signal path went through the adapter observable instead of a canvas prop. Don't edit
     canvas/ files; route approval/lifecycle work through lib/ + ui/.
8. 🟡 IN PROGRESS — P1-2 + P1-4 (the operator said "start the voice build now"):
   - ✅ P1-2 Voice Slice 2 MVP (commit 12f17db): the classic mic is now a real "talk to Jarvis"
     loop. New tested helper lib/voiceChat.streamChatReply() streams the CONVERSATIONAL /api/v1/chat;
     App.jsx mic = push-to-talk STT -> reply streams into a bubble -> SpeechSynthesis speaks it back;
     EN-IN/HI-IN toggle; full honest error paths (unsupported/mic-denied/no-speech); aria-live status.
     Cardinal rule by construction: voice hits /api/v1/chat (no tools, no approval) so a spoken word
     can never redeem a token. +4 tests; build green; frontend vitest 76. Screenshot shown to operator.
     DEFERRED (honest): (a) the same loop inside the superbrain HUD command bar (lab ui/ + port);
     (b) the 'voice-speaking' bus event -> 3D brain PULSE while talking — that reaction lives in the
     FROZEN components/canvas scene, so it needs the canon process (lab + goldens + before/after
     screenshots in HIS browser), NOT a logic commit.
   - ⏭ P1-4 structured logging — NOT STARTED. Note: structlog is NOT installed + aios/ uses ZERO
     logging today. Lean dependency-free (stdlib JSON formatter + correlation-id contextvar + a
     FastAPI middleware + replace the bare except/print on the turn path + CRITICAL on audit-verify
     fail) rather than adding structlog. Evidence sites: main.py bare-excepts (114/637/1152/1235/
     1279/1436/1467, pre-renovation line nums), tamper-verify has no emit.
   NEXT DECISION for the operator: try the voice live, then pick — (a) P1-4 logging, (b) port voice
   into the superbrain HUD (glowing brain), or (c) the 3D voice-pulse canon session.

LAB CAVEAT (P1-3 + P0-3): the canonical source edits live in the gitignored lab
(GAG demo/gag-orchestrator: src/lib/sessionId.ts [new], aiosAdapter.ts, components/ui/SuperbrainHUD.tsx,
tools/port-to-frontend.mjs manifest). Only the PORTED product files are committed here. Operator should
push the lab to swap821/gag-demo so a fresh lab clone's `npm run port` stays consistent (else the port
drift-tripwire/regeneration could revert these).

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
B1. ✅ **DONE — relocated the Bedrock token to the backend** (2026-06-14). The `ABSK` token + `AWS_REGION`
    were STRIPPED from `frontend/.env` (incl. pasted `$env:` lines — Vite never bundled them: no VITE_ prefix,
    never committed) and now live ONLY in the project-root `.env` (gitignored). Added `AIOS_BEDROCK_REGION=us-east-1`
    there so the backend actually ENABLES Bedrock — verified live: `config.BEDROCK_ENABLED=True`, a real backend
    `BedrockClient` converse → "pong". Router privacy gate keeps it out of `auto` until opted in. Hermetic-test fix:
    2 tests that assumed Bedrock-off now force `get_bedrock_client=None`. ⚠️ STILL OPERATOR-TODO: **rotate** the
    `ABSK` key in the AWS console (generate new → update root `.env` → revoke old); exposure was ~nil (never in
    git, never client-bundled) so this is hygiene, not incident response.
B2. (opt) clean the 2 untracked `training_ground/test_auto_*.py` assert-True stubs + tracked cruft
    (`success.txt`/`creator.txt`/`chat-ui.html`/`websocket_security_update.md`) (PLAN H2).
B3. ✅ DONE (2026-06-14) Tier-1 doc-currency: README/AGENTS/START_HERE test baseline → **516, 1 skipped**;
    README + AGENTS now document the multi-LLM router / Gemini / Bedrock / evidence-calibration / active-brain
    badge + the new `AIOS_ROUTER_*` / `AIOS_GEMINI_*` flags. (KICKOFF reports the live count, no hardcode.)
    NOT updated (intentionally — dated evidence, not stale): CEO_LOG / EVIDENCE_CURRICULUM / AUDIT / the
    06-13 deep-analysis snapshots (SYSTEM_TRUE_PICTURE, BACKEND_TRUE_PICTURE, HIDDEN_KNOWLEDGE, PLAN).

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
    ✅ **DONE — P1, the Gemini provider** (explicit-pick, behaviour-preserving off by default):
      `aios/core/gemini.py` `GeminiClient` — same `chat(messages,*,tools,model)` contract as Ollama/Bedrock,
      backed by **Vertex AI via gcloud ADC** (`genai.Client(vertexai=True, project, location)`, SDK lazy-
      imported). `_to_gemini` bridges the agent's Ollama-shaped msgs ↔ Gemini `contents`/function-call parts
      (paired by NAME); `_parse_output` maps back; `list_models` discovers + falls back to `CURATED_MODELS`.
      Config: `AIOS_GEMINI_PROJECT` (the opt-in) / `_LOCATION` (us-central1) / `_MODEL` (gemini-2.5-flash) /
      `_MAX_TOKENS`; `GEMINI_ENABLED = bool(project)`. main.py: `get_gemini_client()` dep (None unless enabled),
      `/api/v1/models/gemini` endpoint, and a `gemini.<model>` branch in `_select_chat_client` (strips prefix,
      503 if unconfigured — never a silent provider change). `tests/test_gemini.py` (17 tests). Full suite 493 pass.
      OPERATOR one-time setup before first live turn: `pip install google-genai` + `gcloud auth application-default
      login` + set `AIOS_GEMINI_PROJECT` (see requirements.txt note). NOT auto-routed yet (explicit-pick first, like Bedrock began).
    ✅ **DONE — P2, router WIRED into `auto`** (behaviour-preserving; cloud OFF by default):
      `_select_chat_client`'s `auto` branch now runs `router.route(task, providers, policy, require_tools=True)`.
      Helpers in main.py: `_build_providers` (live Ollama+Bedrock+Gemini → `Provider` rows), `_router_policy`
      (reads config each call), `_client_for` (provider name → client). Config: `AIOS_ROUTER_CLOUD_TASKS`
      (the PRIVACY BOUNDARY, empty=cloud off), `AIOS_ROUTER_PREFER_LOCAL` (True), `AIOS_ROUTER_MAX_COST` (high).
      **Behaviour change (intentional, privacy-first):** `auto` with no local model no longer silently falls back
      to Bedrock — it drops to the local default; cloud egress now requires an explicit `ROUTER_CLOUD_TASKS` opt-in.
      Also fixed via live test: `GeminiClient` disables 2.5 "thinking" by default (`AIOS_GEMINI_THINKING_BUDGET=0`)
      so a turn always returns text within budget. `tests/test_route_wiring.py` (6) pins privacy-gate-on-fallback.
      ✅ **Both cloud creds LIVE-VERIFIED (2026-06-13):** Vertex/ADC `gemini-2.5-flash` returned text (REST ping,
      finish=STOP; note `gemini-2.0-flash` NOT enabled on project `ai-editor-498414`); Bedrock bearer token in
      `frontend/.env` → `amazon.nova-lite-v1:0` returned "pong" (region us-east-1). Full suite 501 pass / 1 skip.
    ✅ **DONE — the full HYBRID layer (local LLM picks)** + **e2e live-proven through the cage**:
      e2e (2026-06-14): a `reasoning` `auto` turn through real `/api/generate` was served by `gemini-2.5-flash`
      (HTTP 200, step·step·done, 3446-char answer; local `.chat` wired to RAISE so the answer could ONLY be Gemini).
      Picker: `router.PICKER_SYSTEM`/`picker_prompt`/`parse_pick` (pure) + `main._maybe_llm_picker` — a fast LOCAL
      model chooses among policy-allowed candidates, invoked ONLY when ≥2 candidates exist (zero latency on the
      default single-candidate path) and a local model is available; its reply is validated by `route()` so it can
      prefer but NEVER escape the gate; deterministic fallback on any non-answer. Config `AIOS_ROUTER_LLM_PICK`
      (default True). `tests/test_router.py` (+4 pure) + `tests/test_route_wiring.py` (+4 hybrid). Full suite 509 pass / 1 skip.
    ✅ **DONE — P3 evidence-calibration + route event (backend)**: the router now LEARNS which model performs.
      `DevelopmentTracker.model_task_success_rates()` aggregates the already-recorded verified outcomes by
      (provider, model, task) → the router's `metrics` map; the dev metadata now also tags `provider`
      (`_provider_name`). `_route_metrics` reads it ONLY on an auto+cloud-opted-in+calibration-on turn (zero cost
      on the default path); `_select_chat_client` passes `metrics`+`calibration_weight` to `router.candidates`.
      Config `AIOS_ROUTER_CALIBRATION_WEIGHT` (default 0.4; cold-start keys fall back to heuristic). The turn now
      emits an `event: route` SSE frame {provider, model, privacy, task, auto} = the "active brain" signal for the UI.
      Tests: test_brain_growth (+2 aggregator), test_route_wiring (+2 calibration/provider), test_api (+1 route event).
    P0 ✅ done (B1). **P3 backend ✅ done.** ✅ **FRONTEND active-brain BADGE DONE (2026-06-14, operator-signed-off):**
      Phase 1 (classic, product-safe, App.jsx) consumes the `route` frame in the header badge. Phase 2A (superbrain
      canon) adds a `BRAIN ● <model> · <privacy>` segment to the sovereignty row — authored in the LAB
      (cognitionBus 'route' type, aiosAdapter publish, SuperbrainHUD segment + subscription, globals.css brain-dot
      green=local/amber=cloud), byte-synced via `npm run port`. ADDITIVE/conditional like AUTONOMY → canon IDLE row
      byte-unchanged (FIDELITY-safe). Before/after goldens in `.aios/state/badge-goldens/` (idle=no badge; cloud=amber
      gemini; local=green qwen). Proposal: `.aios/state/ACTIVE_BRAIN_BADGE_PROPOSAL.md`. Cage verifies regardless of provider.
    ✅ **Active-brain attribution TIGHTENED (2026-06-14):** the `route` SSE frame was emitted at the START of the
      turn, before any `chat()` — so under failover it announced the ranked PRIMARY (e.g. `gemini-2.5-pro`, which
      isn't invocable on the project and rides over to flash/bedrock), momentarily showing a brain that never served.
      Fix (main.py): announce the route LAZILY from inside the stream — on the first `text`/`tool_call`/`code` event
      (and again on a mid-loop failover, idempotent), with `done`/`human_required` as a backstop — so a
      `FailoverChatClient` only reports a model AFTER its `chat()` returns. The badge now names the model that
      ACTUALLY served, never the dead primary. Tests: test_api (+1: bedrock cascade head fails → route names the
      served fallback, never the primary). Full suite 545 pass / 1 skip.
    ✅ **FAILOVER layer DONE (2026-06-14, commit fd47482, live-proven):** `aios/core/failover.py`
      `FailoverChatClient` wraps the router's RANKED candidates and rides the next on an `LLMError`
      (forward-only + sticky; truthful `active_provider/model` attribution so calibration credits the model that
      served). `auto` builds the cascade [picked, …rest by rank]; single candidate → raw client. `_active_route`/
      `_route_meta` record the served model. 8 tests. Operator opted **coding** into cloud
      (`AIOS_ROUTER_CLOUD_TASKS=reasoning,coding` in backend .env) so coding escalates to a frontier model with
      [gemini→bedrock→local] failover. Live: Gemini-down → turn rode Bedrock, recorded as bedrock. **Suite 525 pass / 1 skip.**
    ✅ **BREADTH DONE (2026-06-14):** `aios/core/catalog.py` — `_build_providers` now emits a candidate PER model
      in each cloud provider's CATALOG (discovered once via `client.list_models()`, cached; account-accurate so a
      frontier model is offered only where invocable), capability by a coarse id heuristic (`cloud_capability`,
      +DEFAULT_BONUS for the configured default), calibration refines. So `auto` + the failover cascade + the
      hybrid picker span MANY models (Claude/Nova/Llama/Gemini Pro+Flash…), not one per provider. `tests/test_catalog.py` (8) + wiring tests.
    ✅ **Verify-gap RESOLVED (not a code bug):** traced — approved creates DO run `_auto_verify` via
      `_pre_apply_grants`; the `unverified` outcomes were the LOCAL model writing a module with NO sibling test
      (`[VERIFY SKIPPED]`) or a bad import (the conftest fixed collection). The verify path is correct-by-design;
      routing coding to a capable cloud model (now opted in) makes the agent write complete, verifiable code.
    ✅ **verified_success NOW LANDS — the two-fix `verified_failure` cure (2026-06-14, commits 925e0a1 + this turn,
      live-proven 16→17):** coding turns booked `verified_failure` and never `verified_success`. Root cause: the
      model's OWN `verify` tool call (advisory) often ran a mis-pathed `pytest training_ground/test_x.py` from the
      sandbox cwd → `training_ground/training_ground/...` → 0 tests, exit 4 → a spurious `[VERIFY FAIL]`; the
      done-logic's "any FAIL ⇒ verified_failure" then failed a turn whose written code actually PASSED the forced
      post-write check. **Fix 1 (main.py, 925e0a1):** capture the FORCED auto-verify verdicts (`autoverify-*`)
      separately in `auto_verdicts` and make them AUTHORITATIVE — the model's own verify is advisory, used only as
      fallback when nothing was auto-verified. **Fix 2 (tool_agent.py, this turn):** `_normalise_sandbox_paths`
      strips the redundant sandbox-root prefix from the model's verify command (verify runs FROM the sandbox cwd),
      + the `verify` tool description now tells the model to pass sandbox-relative paths — so its own check actually
      runs instead of emitting a confusing FAIL in the stream. Conservative/idempotent (no-op on `pytest -q` and on
      the already-correct forced path). Tests: test_tool_agent (+2: 8-case normaliser param + e2e mispathed-runs-PASS).
    OPERATOR LEVERS: `AIOS_ROUTER_CLOUD_TASKS` (which tasks may go cloud; now `reasoning,coding`),
    `AIOS_ROUTER_CALIBRATION_WEIGHT` (0.4), `AIOS_ROUTER_LLM_PICK`. Tool: `tools/watch_calibration.py` (live evidence view).
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
Tests: `.venv\Scripts\python -m pytest -q`  (baseline 544 passed, 1 skipped)
Autonomy ledger: `GET /api/v1/development/autonomy`
Swarm: POST /api/generate with `"swarm": true`
True picture: `.aios/state/BACKEND_TRUE_PICTURE.md`
