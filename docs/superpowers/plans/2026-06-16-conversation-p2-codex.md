# P2 — Make the Being Conversational — Codex Build Spec

**Date:** 2026-06-16
**Owner:** operator (kumarswapnil82) · **Planner/Reviewer:** Claude · **Writer:** Codex (sole frontend writer)
**Base (hash-pin):** `8df94c1` on `feat/living-being-p1` (deep-spine landed + approved)
**Coordination task:** `conversation-p2-codex`
**Master plan:** `docs/superpowers/specs/2026-06-16-living-being-frontend-design.md` §4 State 2 (REST + FIRST CONTACT, decision **B brainstem intake**) + State 3 (AWAKENING / CONVERSATION).

---

## 0. Goal

You talk to the being **through its brainstem**, and it answers **as the being** — words flow **up the cord** into the mind, the cortex brightens and **replies in-scene**, the reply pulses **back down** the body. Voice-first; everything stays **3D — no visible 2D chrome** on the canvas. The loved brain/cortex shader stays **byte-identical**.

## 1. What already exists (reuse — do NOT rebuild)

- **`frontend/src/workbench/BrainstemIntake.jsx`** — a pure-3D glowing intake (dual tori + core + 4 conduits) at `INTAKE_LOCAL = (0,-1.08,-0.42)`, already mounted in `SuperbrainApp.jsx:23`. Today it only *reacts* to cognition events (pulses) — it has **no input capture** and **no upward flow**.
- **`frontend/src/superbrain/lib/aiosAdapter.ts`** — data plane:
  - `sendVoiceTurn(transcript, { onChunk?: (replySoFar:string)=>void }): Promise<string>` (lines 389-442) → POST `/api/v1/chat`, streams `text_chunk` SSE, calls `onChunk` with the accumulated reply, returns the full reply. Publishes `'directive'` on send + `'synthesis'` on done. **This is the P2 path** (no tools/approval — conversation). (`sendDirective` is the tool path; reserve for P3.)
- **`frontend/src/superbrain/lib/cognitionBus.ts`** — `publishCognition(evt)` / subscribe; events `directive | synthesis | route | voice-speaking | knowledge-acquired | agent-dispatch | approval-* | burst | telemetry`.
- **`frontend/src/superbrain/lib/lifecycleStateMachine.ts`** — `REST ↔ ATTENTIVE` via `notifyDirective()` (REST→ATTENTIVE, ~8s decay). `uAwaken` already brightens cortex + leans the brain on REST→ATTENTIVE (`SuperbrainScene.tsx:170,763`).
- **`NervousSystem.tsx`** — a **downward** flow band already exists: `NERVE_FLOW_UNIFORM` (phase) + `NERVE_FLOWGAIN_UNIFORM` (0 at rest, rises on `burst`). The nerve material (`makeBrainMaterial bodyMode:'nerve'`) reads them. Reuse this infra; add a direction.

## 2. The gaps to deliver (the build)

Build in this order; each sub-phase is an **operator browser-gate** — hand back after each for review + his look.

### P2.1 — Input capture → send (voice-first)
- **Voice (primary):** add a press-to-talk on the brainstem intake using the Web Speech API (`window.SpeechRecognition || window.webkitSpeechRecognition` — works in the operator's Edge). A click/hold on the `BrainstemIntake` 3D mesh (use R3F `onPointerDown`/`onPointerUp`, or spacebar-to-talk) starts recognition; on result, call `sendVoiceTurn(transcript, { onChunk })`. While listening, the intake glows brighter (publish/raise a `'voice-speaking'`-style intensity).
- **Typed (fallback, still 3D):** capture text via a **visually-hidden** DOM input (off-screen / `opacity:0` / 1px — NOT visible chrome; honors the all-3D law since nothing flat is shown) that holds focus for caret/IME; render the in-progress text as an **in-scene drei `<Text>`** (3D SDF mesh, NOT `<Html>`) condensing at the intake. Enter → `sendVoiceTurn`. Per the master plan: voice-first; the typed text appears in-scene only while typing.
- On send: call `notifyDirective()` (REST→ATTENTIVE) so the being leans/brightens, and publish `'directive'` (sendVoiceTurn already does this).

### P2.2 — Words travel UP the spine (the question rising)
- Add an **upward** flow to the nerve material — the cleanest is a `uFlowDir` (+1 down / -1 up) or a separate `uIntakeFlow` uniform + a short-lived upward gaussian band that runs **intake→brainstem→cortex** during the send/listening window (arc 1→0). Gate it to the "user is speaking/sending" state (a new `NERVE_INTAKEGAIN_UNIFORM`, attack on send, decay after). Distinct cooler hue (cyan, the intake color) so "question up" reads different from "reply down".
- **Constraint:** all shader edits stay in the **nerve path** (`isNerve`/`bodyMode==='nerve'`) — cortex byte-identical. Reuse the existing flow-band GLSL; add the direction/secondary band behind nerve gating.

### P2.3 — The mind replies (cortex emanation + reply down + in-scene text)
- Wire `sendVoiceTurn`'s `onChunk` to:
  1. **Cortex brightens / emanates** as the reply streams — raise a `uReply`/awaken-style envelope (reuse `uAwaken` or add a nerve+cortex-safe `uReplyGlow`; if it touches cortex emission, gate it so REST is unchanged when `uReplyGlow==0`). The mind "lights up to speak."
  2. **Reply pulse travels DOWN** — drive the existing downward flow (`NERVE_FLOWGAIN_UNIFORM`) up while the reply streams (warm hue), so the answer visibly flows down the body.
  3. **In-scene reply TEXT** via drei `<Text>` (troika SDF — 3D mesh, pure-3D-compliant), emanating near the cortex, fading in as `onChunk` accumulates, then gently dissolving after a dwell. Keep it legible, in the being's palette, camera-facing (billboard). **Do NOT use drei `<Html>`** (that's DOM/2D — violates the law).
- On `'synthesis'` (done): settle back toward REST (let the ATTENTIVE decay run).

### P2.4 — Status off the body (stretch; do last)
- Use the `'route'` event (active brain/model) → a subtle cortex hue/marker **in-scene** (drei `<Text>` micro-label near the stem, or a hue shift), and latency → glow cadence. No 2D HUD. Keep minimal; gate behind operator approval.

## 3. Hard rules / constraints

- **Cortex/brain byte-identical** — every shader change is nerve-gated (`bodyMode==='nerve'`/`isNerve`) or a new uniform that defaults to the current REST value (so REST is unchanged). Verify the brain looks identical at rest vs `8df94c1`.
- **Pure-3D law** — no visible 2D DOM chrome. Reply/echo text = drei `<Text>` (3D). The only DOM allowed is a **visually-hidden** focus-capture input for typing (off-screen, invisible) — nothing the user sees is flat.
- **Reuse, don't fork** — `sendVoiceTurn` for the turn, `cognitionBus` for events, `lifecycleStateMachine` for posture, the existing flow uniforms for motion. Don't add a second data path.
- **Growth/4-draw-call/objectPos contracts** from the deep-spine work stay intact.
- **Backend:** `/api/v1/chat` is the existing endpoint — no backend changes for P2 (the SSE text path is the source). If it's down, degrade gracefully (the being still animates; show an in-scene "link offline" cue, not a crash).
- **Gates green** before each handoff: `cd frontend && npm run typecheck` + `npm test` (currently 128/128; add tests for any new pure logic, e.g. an intake/flow state helper — TDD it). Changed-file lint clean.
- **Final aesthetic = operator's browser** at `http://127.0.0.1:5177/`. Don't declare done — hand to Claude per sub-phase.

## 4. Verification (per sub-phase, in the operator's browser)
1. Speak/type → being goes ATTENTIVE (leans, cortex brightens), question visibly rises up the cord.
2. Reply: cortex emanates, reply text appears in-scene (3D, legible, on-palette), reply pulse flows down.
3. Brain at REST identical to `8df94c1` (no cortex drift).
4. 60fps high-tier feel; no 2D chrome anywhere; reduced-motion still degrades motion not look.

## 5. Handoff protocol
- Task `conversation-p2-codex`, base `8df94c1`. Claim the writer lease, build **P2.1 → P2.2 → P2.3 → P2.4** (operator-gated between sub-phases), run gates, hand to Claude (`agent_coord.py handoff`/`message`). Don't invent on ambiguity — `// CLAUDE?:` + flag it. Note: the `verdict` CLI rejects if the worktree snapshot drifts (e.g. the monitor log) — a coordination `message` is an acceptable approval-of-record fallback.
