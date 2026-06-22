# PREMIUM WORKING FRONTEND — synthesis plan (every surface + every state)

> **Dated 2026-06-15.** Principal-frontend synthesis of an 8-dimension READ-ONLY audit
> (FORGE · conversation/voice/approval · workbench-shell/organs · classic-IDE · state/data-truth
> · accessibility · responsive · performance/production-grade). Goal per the operator: a
> **PREMIUM, PRODUCTION-GRADE, WORKING** frontend for EVERYTHING that is NOT the canon 3D brain.
> The 3D canon (`components/canvas/**`) is the cherished HERO and is being elevated separately in
> `SUPERBRAIN_NEXTGEN_DESIGN.md` — **this plan deliberately does not re-cover canon**; it brings
> every OTHER surface and every UI STATE up to the same bar the canon HUD already set.
>
> This document is a **lens onto `RENOVATION_PLAN.md`**, not a replacement. Most premium-frontend
> work the audit found is already named there (P1-7, P1-8, P0-3/4, P1-9, P2-1/2/6, P3-1/4). This
> plan (a) DEDUPES the audit's overlapping gaps into one list, (b) tags each cluster as
> **[extends Pn-n]** or **[NEW — not in RENOVATION_PLAN]**, (c) re-orders by *impact-per-effort
> for the frontend specifically*, and (d) groups into independently-shippable waves. Where it
> conflicts with RENOVATION_PLAN's *whole-system* ordering, RENOVATION_PLAN's security-first
> sequence still wins for the repo; this is the frontend slice of that backlog.

---

## 1. The honest verdict: premium core, demo-grade everything-else

**Overall: MIXED — one genuinely premium surface surrounded by demo-grade ones.**

The audit is unanimous and it matches `RENOVATION_PLAN.md §1`: the **2D superbrain HUD (canon)
is production-grade premium** — honest dormancy, single-accent discipline, spring physics,
reactive reduced-motion, focus-on-approval, real data binding. **Everything beside it is a
visibly lower tier:**

| Surface | Verdict | Why |
|---|---|---|
| **Canon HUD** (out of scope here) | **Premium / working** | The bar. Honest states, real data, no fabrication. |
| **Organs (10 read-only ports)** | **Good, not done** | Inherit canon glass/reduced-motion + honest offline; but no *empty* state (≠ offline), `:focus` not `:focus-visible`, no shared error boundary, every port re-implements the same fetch machine. |
| **Conversation / Approval gate** | **Mixed** | Real data + honest states, but the approval bar never scrolls into view, no keyboard focus/Esc, no mobile height cap, no color-blind tier signal, no reduced-motion gate on its animation. |
| **Voice loop** | **Half-built / orphaned** | Web Speech STT only dumps text to the input — no `/api/v1/chat` wiring, no TTS speak-back, no `voice-speaking` pulse, no error escalation, no unmount cleanup, no browser-unsupported fallback. |
| **FORGE / Workbench (ForgePorts, CommandLine, LivePreview, CodeCanvas)** | **Demo-grade** | Fixed-px panels (500/410) pinned to 3D world coords with ZERO `@media`; CommandLine is a bare `busy` bool (no streaming/error/offline); silent workspace-fetch failures; Monaco loads from jsDelivr CDN (breaks offline in a local-first system); 3 staggered fetches re-mount Monaco; `key={srcDoc}` remounts the iframe every keystroke. |
| **Classic IDE (App.jsx / App.css)** | **Demo-grade** | 142 inline-style declarations (can't express `:focus-visible`/media-queries/reduced-motion); 28 JS-only hover/press controls invisible to keyboard/AT; the Run/Reject **approval buttons** have no focus ring; a **fabricated** "Amazon Bedrock connected" startup message; model-selector dropdown 380px fixed with no ARIA roles; no responsive breakpoints; only ONE error boundary in the whole app (WebGL). |
| **Production-grade cross-cut** | **Blocking** | 1.35MB undifferentiated chunk, no code-split, no `tsc --noEmit` on a TS-heavy canon, one error boundary, `specgloss.png` (264KB) shipped but sampled by nothing, no CI. |

**What's genuinely GOOD (don't "fix" it):** the canon HUD's state discipline; the organs'
honest offline + reduced-motion; the FORGE's real data flow (workspace via
`/api/v1/development/workspace`, approval-on-diff, cognition-bus flare) and clean component
separation; honest voice *error text* (it exists, it just doesn't escalate). The problem is
NOT architecture — it's the seams the discipline never reached, exactly per RENOVATION_PLAN.

**The 4 systemic root causes** (fix these and ~30 leaf gaps collapse):
1. **Inline styles** (142 in App.jsx, 28 hover handlers) → can't express `:focus-visible`,
   `@media`, reduced-motion. Root cause of half the a11y + responsive + motion gaps.
2. **No shared turn-state / fetch hooks** → CommandLine, voice, and 10 organs each re-implement
   (badly) the streaming/error/offline machine the canon bar already solved.
3. **Fixed-px world-pinned panels** → the entire FORGE is desktop-only by omission.
4. **Silent catches everywhere** → fetch fails, SSE corrupts, POST 500s all swallow with no UI
   signal. The "directive sent, nothing happened" failure repeats across every surface.

---

## 2. Top ~8 highest-leverage fixes (the frontend slice)

Ranked by premium-working impact per hour. Each is a *cluster* the audit raised in 2-6 lenses.

1. **Extract App.jsx's 142 inline styles + 28 hover handlers into real stylesheets**
   (App.css / ModelSelector.css / ApprovalBar.css) with canon tokens.
   **[extends P1-8]** — this is the unlock: it makes `:focus-visible`, `@media (prefers-reduced-motion)`,
   `@media (max-width)` *possible at all*. Closes ~6 a11y/responsive/motion gaps at once and is
   the prerequisite for fix #2.

2. **Add `:focus-visible` + accessible names to EVERY interactive control, prioritizing the
   approval buttons** (classic Run/Reject, HUD authorize/reject, ForgePorts `⟳`/tabs, CommandLine
   Execute, organ search, model-selector). The approval gate IS the trust contract and it is
   currently invisible to keyboard/AT users. **[extends P1-7 + P1-8]**

3. **Wire the marquee VOICE loop end-to-end** — STT → `/api/v1/chat` (shared `getSessionId()`),
   TTS speak-back, a NEW `voice-speaking` cognition-bus event so the brain pulses + an `aria-live`
   "Jarvis is speaking", push-to-talk, full error escalation (mic-denied/no-speech/unsupported →
   visible banner, not a tiny line), unmount cleanup, and a **voice→COGNITION FAULT** bridge so a
   failed spoken turn isn't silent on the brain. **[extends P1-2; depends on P1-3 session-id]**

4. **Replace the fabricated "Amazon Bedrock connected" startup message with honest probe state**
   — "Checking local Ollama…" → "Ready: Ollama" / "Offline — cloud Bedrock", driven by the
   `ollamaStatus`/`bedrockStatus` already probed. **[NEW — not separately in RENOVATION_PLAN;
   a direct DATA-TRUE violation; the only outright *lie* in the product].**

5. **Responsive FORGE: kill the fixed-px traps** — `clamp()` the editor/preview, stack vertical
   below ~900px, hide preview on phone; **and define the undefined `--sb-band-h` CSS variable**
   (used 4× in shell.css, currently silently falls back to 0 → manufacturing layout collapse).
   **[extends P1-7; the `--sb-band-h` undefined-variable is NEW and is a latent layout-collapse bug].**

6. **Build a `useCommandTurnState` hook + `useOrganFetch` hook and adopt them everywhere** —
   one honest streaming/error/offline/empty state machine for CommandLine, voice, and all 10
   organs. Adds the missing **empty state (≠ offline)** and a `case 'error'` for malformed SSE.
   **[extends P1-7 (CommandLine) + P2-2 (useOrganFetch) + P3-4 (cognition-fault)].**

7. **Approval-gate UX completion** — scroll-into-view + focus the primary button on
   `pendingAction`; Enter/Esc shortcuts (gated off the text input); mobile height cap (≤50vh) +
   stacked buttons; a color-blind tier signal (icon + "YELLOW TIER" text, not color alone);
   reduced-motion gate on the entrance/glow animation. **[extends P0-3 (single-source-of-truth)
   on the *interaction/responsive* axis; the scroll/focus/keyboard/mobile/color-blind items are
   NEW finishing work P0-3 doesn't name].**

8. **Production-grade cross-cut: error boundaries + code-split + typecheck + self-host Monaco.**
   Wrap App.jsx top-level and each major organ/panel in error boundaries with honest retry
   fallback (today: one WebGL boundary; an AlignmentPanel crash = white screen). Add
   `manualChunks` (three/drei+postprocessing/Monaco) to drop the 1.35MB chunk; delete
   `specgloss.png`; `tsc --noEmit` in CI; `loader.config({monaco})` so the editor works offline.
   **[error boundaries are NEW; the rest extends P2-6 + P1-9].**

---

## 3. Waves — each independently shippable, ordered by impact-per-effort

Effort: **S** ≈ hours–1 day · **M** ≈ 2–4 days · **L** ≈ 1 week+. Every wave ends green on
the existing vitest suites (and adds its own tests where logic is involved).

### WAVE 0 — Truth & quick a11y wins (S, ~1–2 days) — ship first
*No architecture change; pure honesty + cheap accessibility floor. De-risks demos immediately.*

| Item | Maps to | Effort |
|---|---|---|
| **W0-1** Replace fabricated "Amazon Bedrock connected" startup message with honest `ollamaStatus`/`bedrockStatus` probe state (loading → ready/offline). | **NEW** (DATA-TRUE) | S |
| **W0-2** Delete dead code: `BuildFeed.jsx` (97 LOC, 0 importers, also breaks one-accent with #a78bfa/#818cf8), `Workbench.jsx`; rewrite `QualityTierProvider` docstring to match declawed code (it claims auto-degrade — FIDELITY-forbidden). | **extends P3-1** | S |
| **W0-3** Add `aria-label` to all glyph-only buttons (ForgePorts `⟳`/tabs, classic Plus/Trash/voice/lang, terminal/git inputs); make the hover-hidden file-delete button keyboard-reachable (`:focus-within`). | **extends P1-7 + P1-8** | S |
| **W0-4** Delete `specgloss.png` (264KB, sampled by zero shaders). | **extends P2-6** | S |
| **W0-5** Define `--sb-band-h` explicitly (index.html `:root` or SuperbrainShell) — fixes the silent manufacturing-layout collapse. | **NEW** (latent bug) | S |

### WAVE 1 — The stylesheet/a11y substrate (M, ~3–4 days) — the unlock
*Extract inline styles so the whole a11y/responsive/motion floor becomes expressible. This is
the prerequisite that makes Waves 2-3 cheap.*

| Item | Maps to | Effort |
|---|---|---|
| **W1-1** Extract App.jsx's 142 inline styles + 28 hover handlers into App.css / ModelSelector.css / ApprovalBar.css with canon tokens. | **extends P1-8** | M |
| **W1-2** Add `:focus-visible { outline:2px solid var(--accent); outline-offset:2px }` to EVERY interactive control across classic IDE, ForgePorts, CommandLine, organs (replace organs' `:focus` → `:focus-visible`). Prioritize Run/Reject approval buttons. | **extends P1-7 + P1-8** | S |
| **W1-3** Add `@media (prefers-reduced-motion: reduce)` gates: classic breathe/pulse keyframes, approval entrance/glow, workbench `workspaceIn`/forge flares, BootSequence (make it use `useReducedMotion()` reactively, not a one-shot matchMedia read). | **extends P1-8 + P3-2** | S |
| **W1-4** Model selector ARIA: `role=combobox`/`aria-expanded`/`aria-haspopup=listbox` on trigger, `role=listbox`/`option`/`aria-selected` on list, roving `tabIndex`, responsive `clamp(300px,90vw,380px)` + off-screen reposition. | **NEW** (a11y; not in RENOVATION_PLAN) | M |
| **W1-5** Add `aria-live` regions: chat messages (`polite`), voice status/errors (`assertive`), CommandLine submit status. NewFileDialog focus-trap + `role=dialog`/`aria-modal` + `aria-label` on input. | **extends P1-8** | S |

### WAVE 2 — Shared state machines + honest states everywhere (M, ~4 days)
*One source of truth for streaming/error/offline/empty. Collapses ~12 duplicated leaf gaps.*

| Item | Maps to | Effort |
|---|---|---|
| **W2-1** Extract `useCommandTurnState(sendDirective)` from the canon bar (idle/pending/streaming/blocked-approval/error/offline); adopt in CommandLine so it gets streaming text, offline pre-flight guard, inline error recovery, aria-live. | **extends P1-7** | M |
| **W2-2** Extract `useOrganFetch(url,{events})`; adopt in all 10 organs. Add a real **empty** phase (≠ offline) to each ("No skills mastered yet", "Memory search has no results"); distinguish network-offline from 5xx (inspect `response.status`). | **extends P2-2** | M |
| **W2-3** Error-path UI on FORGE: red OFFLINE banner on `loadWorkspace` catch (today: silent); inline error + aria-live on CommandLine `/api/v1/chat` POST failure (today: silent "directive sent, nothing happened"); loading skeleton/spinner during workspace fetch. | **extends P1-7 + P3-4** | M |
| **W2-4** Cognition-bus error plumbing: add `'error'` to `CognitionEventType`; emit `WORKBENCH LINK LOST` when an organ goes offline, `COGNITION FAULT` on malformed/partial SSE (frontend) and from the FORGE on persistent sync failure. Add a `case 'error'` to the HUD SSE subscriber. Log structured warnings on SSE JSON-parse failures (counter → fault after N). | **extends P3-4** (frontend half of P1-4) | M |
| **W2-5** Honest first-load offline: replace the `hadDataRef` guard so a mount-time fetch that times out (4s) shows the offline placeholder during loading, not "loading forever". (ConversationPort/IntentPort/organs.) | **NEW** (state-truth gap) | S |

### WAVE 3 — The marquee VOICE loop + approval-gate finish (M, ~4 days)
*The operator's named priority and the highest emotional payoff. Lands after W1 (a11y substrate)
and W2 (turn-state hook) make it cheap and safe. Depends on P1-3 session-id + P0-7 input-shield
landing per RENOVATION_PLAN order.*

| Item | Maps to | Effort |
|---|---|---|
| **W3-1** Wire orphaned Web Speech STT → `POST /api/v1/chat` via shared `getSessionId()`; `lang` en-IN/hi-IN; SSE-stream the reply into the HUD reusing `useCommandTurnState`. | **extends P1-2 (dep P1-3)** | M |
| **W3-2** TTS speak-back + a NEW `voice-speaking` cognition-bus event → brain pulse + `aria-live` "Jarvis is speaking…" (so TTS presence is visible + AT-announced; today it plays silently). Sync the IntentPort alignment frame for voice turns too (typed turns do, voice don't). | **extends P1-2** | M |
| **W3-3** Voice robustness: escalate errors to a visible banner (`aria-live=assertive`), not a tiny line; clear stale error on success; browser-unsupported → disabled mic + tooltip; `recognitionRef` unmount cleanup; voice→COGNITION FAULT bridge on turn failure. | **extends P1-2** | S |
| **W3-4** Approval-gate UX finish: `scrollIntoView({block:'nearest'})` + focus primary button on `pendingAction`; Enter/Esc shortcuts (gated off text input); mobile `max-height:50vh` + stacked buttons `<360px`; color-blind tier signal (⚠ icon + "YELLOW TIER · approval required" text + `aria-label`). | **extends P0-3** (interaction/responsive finish) | M |

### WAVE 4 — Responsive FORGE + manufacturing on tablet/phone (M, ~3 days)
*Unlocks a real device story for the workbench without touching canon world-points.*

| Item | Maps to | Effort |
|---|---|---|
| **W4-1** FORGE responsive: `clamp(280px,85vw,500px)` editor / `clamp(200px,60vw,410px)` preview; `@media (max-width:900px)` stack vertical + hide preview; `@media (max-width:620px)` shrink padding/dock. DOM panel sizes adapt; 3D world-points stay sacred. | **extends P1-7** | M |
| **W4-2** Classic IDE responsive: `@media (max-width:1024px)` stack editor/preview vertically + hide terminal; `@media (max-width:768px/480px)` font scale, 44px touch targets, dialog `min-width:90vw`. | **extends P1-8** | M |
| **W4-3** Forge tabs overflow affordance on phone (visible scrollbar or dropdown picker); center-ports portrait/aspect-ratio handling; tablet breakpoint (768/1024) gap in superbrain.css console sizing. | **extends P1-7** | S |

### WAVE 5 — Production-grade hardening (M, ~4 days)
*Makes it deployable, not just demoable. Largely the frontend half of P2-6 + P1-9 + a NEW
error-boundary tranche.*

| Item | Maps to | Effort |
|---|---|---|
| **W5-1** Error boundaries: wrap App.jsx top-level + each major organ/panel (AlignmentPanel, ProposalsPanel, DiffView, LivePreview, CodeCanvas) with honest fallback + retry. (Today: only WebGLErrorBoundary.) | **NEW** | M |
| **W5-2** `manualChunks` (three / drei+postprocessing / Monaco+live-preview / main); lazy-mount the Canvas subtree so BootSequence paints first. Drops the 1.35MB chunk below the 500KB warning. | **extends P2-6** | M |
| **W5-3** Self-host Monaco: install `monaco-editor`, `loader.config({monaco})` so CodeCanvas works offline (local-first thesis). | **extends P2-6** | S |
| **W5-4** Add `typescript` + `tsc --noEmit` to scripts + CI; the cross-suite CI runs backend pytest + both vitest suites + `npm run build`. | **extends P1-9** | M |
| **W5-5** Perf: debounce ForgePorts' 3 staggered workspace fetches → one trailing fetch/turn + diff (hash) so only changed files re-mount Monaco; drop `key={srcDoc}` on the iframe (diff instead of remount-per-keystroke); batch streaming `onChunk` with `useDeferredValue`. | **extends P3-4 + P2-6** | M |

### WAVE 6 — Coverage + polish (L, ongoing)
*Raise the floor and finish micro-detail. Runs as the standing mandate alongside everything.*

| Item | Maps to | Effort |
|---|---|---|
| **W6-1** Vitest for the now-shared logic: `useCommandTurnState`, `useOrganFetch` (one test covers all 10 ports), SSE parser `processEvent`, pendingApproval reconciliation. | **extends P2-1** | L |
| **W6-2** Reconcile frontend origin (`config.js` localhost vs `aiosAdapter` 127.0.0.1) + vitest; assert all 4 session-id callsites import the one `getSessionId()`. | **extends P2-8 + P1-3** | S |
| **W6-3** First-run onboarding cue (canon-styled, dismissable) + keyboard-shortcut discovery hints (`aria-description` on model selector / chat input). | **extends P3-3** | M |
| **W6-4** WCAG contrast audit on glass-overlaid text (`--text-3` over variable-opacity glass slips below 4.5:1) — raise alpha to 1.0 on critical labels or add dark underlay; verify on a real dark scene, not isolation. | **NEW** (a11y) | M |
| **W6-5** ForgePorts grounding: faint tether line brain→port so pinned panels read as "nerve connected," not floating; in-context "Reject this write" on a PENDING file. | **extends P3-2** | M |

---

## 4. Reconciliation with RENOVATION_PLAN.md (no duplication, gaps flagged)

**Already covered by RENOVATION_PLAN — this plan only re-orders/details for the frontend:**
P1-2 (voice → W3), P1-3 (session-id → W6-2 assert), P1-7 (workbench tier-up → W2-1/W2-3/W4-1/W4-3),
P1-8 (classic a11y → W1/W4-2), P1-9 (CI/typecheck → W5-4), P0-3 (approval source-of-truth → W3-4
adds the interaction finish), P2-2 (useOrganFetch → W2-2), P2-6 (perf/Monaco/specgloss → W0-4/W5-2/
W5-3/W5-5), P2-8 (origin → W6-2), P3-1 (dead code → W0-2), P3-3 (onboarding → W6-3), P3-4
(cognition-fault/SSE → W2-3/W2-4/W5-5).

**NEW — surfaced by this audit, NOT in RENOVATION_PLAN (add these):**
- **W0-1** Fabricated "Amazon Bedrock connected" startup message — an outright DATA-TRUE violation;
  RENOVATION_PLAN names the orphaned voice STT but not this startup lie.
- **W0-5 / W4-1** Undefined `--sb-band-h` CSS variable (used 4× in shell.css) — latent
  manufacturing-layout collapse; not named anywhere.
- **W1-4** Model-selector ARIA roles (combobox/listbox) — a11y gap not in P1-8's scope (P1-8 is
  about the *classic approval/control* surface; the dropdown is separate).
- **W2-5** First-load `hadDataRef` offline trap (loading-forever on cold offline mount) — a
  state-truth gap distinct from P3-4's malformed-SSE case.
- **W5-1** Error boundaries beyond WebGL — RENOVATION_PLAN has no error-boundary item at all; a
  single component crash currently white-screens the app.
- **W6-4** Glass-overlay contrast audit — a11y; RENOVATION_PLAN's a11y items (P1-8/P3-2) don't
  name the variable-opacity `--text-3` contrast risk explicitly.

**Conflict / sequencing note (honest):** RENOVATION_PLAN sequences security-first (P0 CORS/
entrypoint/auth/input-shield) *before* the voice loop, for whole-system safety. This plan's W3
(voice) therefore must NOT jump ahead of P0-7 (prompt input-shield) + P1-3 (session-id) landing,
even though voice is the highest *frontend* payoff. The repo order stands: do the cheap P0 guards
first; this plan's frontend waves slot into RENOVATION_PLAN's "after step 8" runway (W0/W1 can run
in parallel with the P0 backend guards since they touch no backend perimeter).

**Out of scope (unchanged):** the 3D canon scene (handled by `SUPERBRAIN_NEXTGEN_DESIGN.md` —
enhance-never-replace, canon tag + goldens + before/after in HIS browser); backend perimeter/
security (RENOVATION_PLAN P0 + P0-7/P1-4 backend half); local-first voice hardening
(faster-whisper/Kokoro — deferred per FUTURE_FRONTIER voice-last caution).

---

## 5. The premium-working bar, per dimension (scorecard the waves close)

- **DATA-TRUE** → W0-1 (no fabricated startup), W2-2 (empty ≠ offline), W2-3/W2-4 (no silent
  failures), W2-5 (honest cold-offline).
- **ALL STATES** → W2 (loading skeletons, composed empty, inline error+recovery, offline,
  dormant) across CommandLine, FORGE, organs.
- **ACCESSIBLE** → W1 (focus-visible, reduced-motion, ARIA roles, aria-live, focus-trap),
  W3-4 (keyboard approval + color-blind tier), W6-4 (contrast).
- **RESPONSIVE** → W4 (clamp/stack FORGE + classic, no fixed-px traps, no horizontal scroll),
  W0-5 (manufacturing band).
- **SMOOTH** → W5-5 (debounce fetches, no Monaco/iframe remount churn, batched streaming),
  W1-3 (reduced-motion), W5-2 (code-split → first paint).
- **PRODUCTION-GRADE** → W5-1 (error boundaries), W5-2/W5-3 (bundle + offline Monaco),
  W5-4 (typecheck + CI), W6-1 (tests on the high-leverage logic).
