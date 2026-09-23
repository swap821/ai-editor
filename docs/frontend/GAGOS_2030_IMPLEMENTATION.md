# GAGOS 2030 Living AI-OS Frontend Renovation

**Branch:** `codex/frontend-2030-v1`  
**Base:** `master` at `00dbf6f38956935e0c168a14c77ce5f9ed1e32cc`  
**Scope:** frontend-only, in a dedicated worktree. No backend authority,
security-core, mirror protocol, or generated canon asset was changed.

## Architecture implemented

The renovation keeps one `SuperbrainApp` environment and adds a product-owned
presentation bridge rather than replacing the existing organism. The bridge
reads admitted `mirrorStore`, `tabStore`, conversation phase, and lifecycle
observations, then derives a bounded posture for the body and human-facing
status. It never decides whether an action is executable, approved, authorized,
or allowed.

New product-owned layers:

- `livingMirror/being/semanticKernel.ts` — pure `BeingPhase`, `BeingSignal`,
  `HumanTaskState`, coherence, motion, attention, and bounded worker posture.
- `livingMirror/being/motionSemantics.ts` — shared motion meaning, lifecycle
  boundaries, and reduced-motion equivalents.
- `livingMirror/being/presentationFromStores.ts` — fail-closed adapter from
  existing mirror/cognition/tab truth into presentation facts.
- `livingMirror/being/useBeingPresentation.ts` — React subscription bridge.
- `livingMirror/being/semanticEffects.ts` — pure transition mapping from
  semantic posture to bounded worker visual states, entered signals, and action
  pulse intent.
- `livingMirror/experience/receipts.ts` and `ReceiptCard.tsx` — distinct
  verified, unverified, refusal, failure, and measured rollback language.
- `livingMirror/experience/historyPresentation.ts` — Guided-safe recent
  activity copy with identity-free worker/mission presentation, while Expert
  retains raw event details for inspection.
- `livingMirror/experience/workspaceVisibility.ts` — mode-only workspace
  visibility policy that prevents hidden Expert panels and shortcuts from
  leaking into Guided.
- `livingMirror/bootstrapReadinessCopy.ts` — measured setup state translated
  into provider-free Guided language.
- `livingMirror/GuidedAccountPanel.tsx` — read-only Guided account status and
  an explicit visibility handoff to Expert/Mirror; the existing authority
  ceremony remains Expert-only.
- `livingMirror/observability/frontendMetrics.ts` — bounded, local-only timing
  samples with no prompt, file, worker, model, or identity payload.

The root exposes semantic `data-being-*` attributes and an ARIA live status so
3D is an optional projection, never the only state channel.

## Guided experience

The product-owned emergency-stop presentation bridge publishes only the
measured server latch state. A confirmed engaged latch can hold approval
presentation while a mirror event catches up; unknown remains unknown and is
never treated as engaged.

The persisted/internal `beginner` enum is preserved; visible language is now
`Guided`. The default front door presents:

- one request input, typing first;
- optional voice and explicit copy that voice does not approve actions;
- three prefill-only paths: Ask & understand, Make something, Guide me;
- truthful connection/setup copy;
- a keyboard-reachable Emergency stop;
- human-language stop outcomes in Guided, with raw hook/operator/auth evidence
  retained for Expert/Mirror only;
- no model/provider, swarm, council, worker, or dense runtime dashboard in the
  Guided mount.

The onboarding forge hint is also Expert-only: Guided does not expose the
internal `ORGANS · forge` vocabulary, while the existing onboarding behavior
remains covered explicitly in Expert-mode tests.

The onboarding coach follows the same boundary after later milestones: Guided
uses human language for approval, checking, remote processing, and faster
verified routines, while Expert retains the existing technical milestone copy.
This prevents a returning Guided user from encountering internal terms such as
cloud factory or earned autonomy in a secondary coach surface.

The opening asks: “What would you like to get done?” Starter actions only fill
the input and focus it; they do not submit.

The Guided starter paths use the requested human wording: “Explain something,
compare options, or help me understand this project.”, “Create or improve
something useful.”, and “Help me finish a task one safe step at a time.”
The history presenter also maps the live `human_required` and
`approval.decided` mirror aliases to the same Permission needed / Permission
recorded language as their canonical approval events; Expert retains raw event
names and payload summaries.

The Guided account pill now opens a measured, read-only account status dialog.
Unknown remains unavailable, linked remains linked, and unlinked remains
unlinked; the panel does not expose operator IDs or credential/enrollment
language. “Open Expert / Mirror” is an explicit visibility handoff to the
existing technical sovereignty ceremony and does not approve, authorize, or
change any action.

Mode boundaries are enforced at render time as well as navigation time:
Guided only renders Tasks, Project files, file surfaces, and Recent activity;
an already-open Expert panel is retained in the store for continuity but is
not mounted or exposed until Expert/Mirror is selected. The terminal shortcut
and authority launcher are Expert-only. Setup readiness keeps backend summaries,
check names, and provider/model identities out of Guided copy while preserving
the measured ready/blocked/unavailable result.

## Sovereign interaction and receipts

The product-owned `livingMirror/GuidedApprovalPanel.tsx` retains the existing
adapter callbacks and server-issued token flow while explaining What, Where,
It can affect, and If you say no. Exact command/diff/explanation evidence is
behind `Explain`; the port-managed `superbrain/components/ui/ApprovalPanel.tsx`
remains the technical Expert/Mirror presentation and was not changed. Allow
once and Don’t allow are copy only: the adapter remains the sole authority
path.

Receipt derivation deliberately keeps completion separate from verification:

- a successful replay without verifier evidence is **Finished, but not
  verified**;
- only an admitted `verifyVerdict: pass` becomes **Done**;
- verification failure becomes recovery/failure language;
- refusal is presented as a calm governance result;
- rollback language is emitted only when a real restoration fact is supplied.

The store adapter treats retained recent events as history rather than as
permanent current-task state: terminal refusal, failure, rollback, learning,
and reflex signals are scoped to the latest measured turn marker when one is
available. A newly materialized content surface also remains unverified unless
that surface carries its own explicit verifier verdict; an older retained
`lastVerification` record cannot promote it.

Verified receipts accept an explicit `undoAvailable` presentation fact and the
receipt card exposes that action only through an explicit `onUndo` callback.
This keeps the requested See changes / Undo / Why verified sequence available
to a future caller that has a real guarded recovery capability without making
the current approval replay path claim one.

Unverified receipts now keep all three human actions visible: Review focuses
the existing evidence surface, Run a check prefills a next request without
submitting it, and Discard retracts only the local materialized surface while
leaving the receipt available as history. None of these actions upgrades
verification or changes backend authority.

Confirmed declines retain the calm refusal receipt. If the server does not
confirm the decline, the same safe receipt explicitly says that the decline is
unconfirmed and that this interface did not authorize the action; it does not
silently turn an unknown server outcome into a confirmed governance record.

The Guided surface also removes internal provider/model wording from optional
browser recognition and browse explanations. The user-facing copy describes a
browser speech service and sending page content to GAGOS; Expert/Mirror keeps
technical route and model detail available where it is measured.

The conversation progress cue also distinguishes model preparation from an
in-flight streamed reply: Guided/Expert shows `thinking…` only for the
measured thinking/awakening phase and `replying…` while response content is
streaming. Reflex reuse continues to suppress the model-thinking cue.

Approval mount focus moves to the first decision, keyboard focus is trapped
inside the modal while it is open, and the previous focus is restored on
close. The existing emergency-stop controller remains authoritative.
When the mirror admits `governance.emergency_stop.engaged`, the semantic
presentation bridge suppresses all approval actions and replaces the dialog
with a non-actionable hold notice. The pending request is retained; this
frontend change does not clear, approve, reject, or otherwise alter authority.
The controller also publishes the measured engaged/clear response through the
presentation store, so a confirmed latch suppresses approval actions even when
its mirror event has not arrived yet.

An approved replay can legitimately encounter another server-issued approval
before the original turn is complete. The Guided adapter now carries that
measured pause through the product-owned outcome, keeps the newly captured
approval as the only decision surface, and suppresses any receipt or work
retraction until the replay reaches a real terminal result. This closes the
gap between “this approval was accepted” and “the requested work completed.”

## Expert / Mirror

Expert mode remains a visibility mode, not an authority mode. Its technical
surfaces are progressively disclosed as five anatomy groups: Task (the plan,
work, and recent observations), Intelligence (workforce, hiring, and council
deliberation), Authority (governance, settings, and human preferences), Memory
(memory and memory trails), and Evidence (maintenance, feeds, resources, and
terminal). Only the Task group is expanded by default; the other groups remain
available without dumping every panel into the opening view. Guided uses only
Tasks, Project files, and Recent activity when workspace navigation is shown.
Mode switching preserves the same stores and current task; it does not grant or
change authority.

## 3D and organism behavior

The existing CortexEngine, anatomical conductor, spinal seats, materialized
surfaces, and renderer fallback remain in place. The semantic posture is
projected through the app root, ARIA status, and the product-owned R3F seam, so
body posture can evolve from real state without inventing backend events.

The measured Emergency Stop latch now reaches the same presentation hook as
the mirror-derived posture. When the observation is engaged, the body is
projected as stopped with stop motion and preserved worker evidence; clear and
unknown observations leave the mirror-derived posture unchanged. This is a
presentation overlay only and does not answer or change authority decisions.

Guided Emergency Stop details now keep the human boundary legible without
exposing raw action-hook names or operator/authentication identifiers. Guided
reports whether recorded stop actions are complete or still being confirmed;
Expert/Mirror retains the exact hooks, IDs, and failure detail when the server
actually supplies them. This preserves inspectability without leaking internal
control vocabulary into the default experience.

The product-owned reactive seam applies that same boundary to transient 3D
effects: requested/admitted/active worker visuals become held, cloud-route
lightning and verification/conduction pulses are suppressed, and local
aurora/spine bridges are reset. Evidence trails and bounded worker surfaces
remain available for inspection. This prevents a previously admitted action
effect from continuing to look active after a measured stop.

The product-owned reactive effects now cap transient lightning and worker-mote
entities. Mote motion and transient pulse decay use refs/native scene objects;
React is no longer updated for every mote frame. Lifecycle expiry uses a coarse
timer. Semantic worker posture maps requested → bud, admitted → branch, active
→ conduct, awaiting capability → held, returned → reabsorbing, and dissolved
→ fading. A bounded semantic conduct pulse is ref-driven around the cortex;
verification aurora is triggered only when the admitted semantic verification
signal enters the posture. Raw swarm/cognition buses remain only for
evidence-specific projections (cloud-route lightning and stigmergy trail
updates), not for general posture branching. The cognition bridge also
distinguishes an admitted
`reflex-recall` from model-backed work: Guided shows “Using a verified routine”
and Expert shows “Used a verified routine. No model call.” It never presents a
reflex replay as simulated thinking.

The same product-owned seam now subscribes to the shared reduced-motion store.
When reduced motion is measured, worker evidence remains present as static
bounded markers while product-owned cloud lightning, verification bloom,
conduction pulse, and spine-travel effects are suppressed. The DOM/live status
and the existing canvas reduced-motion path remain the non-travel explanation;
the seam does not create a second preference or infer a state change. The
reduced-motion boundary has a deterministic R3F regression alongside the
Emergency Stop tests.

Coherence now has its own product-owned physics table. Fresh projections keep
stable opacity and cadence; unverified projections are softer; stale
projections are ghosted with discontinuous, slowed travel; degraded
projections remain readable but fragmented and slower; stopped projections
freeze action-bearing travel. These are bounded visual multipliers only. They
never promote stale data, completion, or visual settling into current,
verified, authorized, or executable truth. The coherence table and its stale
cloud-evidence projection have deterministic coverage.

The existing WebGL fallback keeps conversation, workspaces, approval, and
Emergency stop mounted if the renderer is unavailable. Context-loss recovery
remains owned by `WorkspaceCanvas`; no backend failure is inferred from a
visual failure.

The product-owned `RendererFallbackNotice` observes the managed
`.webgl-fallback` boundary and states, “Visual organism unavailable. GAGOS
controls are still working.” Its keyboard-accessible Retry visual organism
control delegates to the managed scene retry when that control exists; when
the browser has no usable WebGL context, it reloads the interface as the only
honest retry boundary. The notice and the `SuperbrainApp` DOM-to-presentation
bridge have deterministic unit and integration coverage. A forced browser
context-loss capture remains unperformed, so this is not evidence of a
measured recovery event.

The product-owned `RendererFailureBoundary` now wraps the lazy `Suspense`
organism subtree as well. A module/render failure that happens before the
managed `.webgl-fallback` marker can mount therefore still leaves the
conversation, approval, Emergency Stop, and workspace shell available. Its
explicit retry callback remains owned by `SuperbrainApp`; it does not approve,
stop, or execute work. The boundary has deterministic failure and retry
coverage, including a rejected `React.lazy` import and an integrated app
render failure that keeps the conversation shell mounted.

## Motion vocabulary

The semantic kernel maps phases to the shared motion vocabulary `calm`,
`attention`, `materialize`, `conduct`, `verify`, `refuse`, `reabsorb`, and
`stop`. Materialization and reabsorption are derived only from measured body or
tab lifecycle state; refusal and rollback are not conflated. Verification or
action failure now enters the same evidence-preserving reabsorption motion as
measured rollback/retraction, rather than falling back to a calm visual that
could imply the failed result had settled. Reduced-motion
behavior continues to use the existing reduced-motion architecture and
shell-wide CSS reduction. No new visual event is driven from an unadmitted
string-only event. The motion contract and reflex distinction are covered by
deterministic regression tests.

## Terminology

| Internal term | Guided term |
| --- | --- |
| Beginner | Guided |
| Governance | Why permission / Safety |
| Missions | Tasks |
| Experience / learned routines | What GAGOS remembers / routines |
| Capability | Permission |
| Ecosystem | System health |
| Local workforce / worker IDs | hidden in Guided |
| Provider/model/route | hidden in Guided unless materially relevant |
| Council / deliberation / stigmergy / terminal | Expert/Mirror only |

## Performance and observability

Phase 0 recorded 28 files containing `useFrame`, 40 call sites, 17 lazy
references, and a baseline browser capture on port 5177. The constrained
frontend baseline was 769 tests, with 249.48 seconds observed for the serial
run; typecheck, build, lint, port, canon, frozen-core, and whitespace checks
were green at baseline.

The renovation adds bounded local measurements for boot-to-input-ready, 3D
initialization, frame-time p50/p95, dropped-frame periods, workspace attention
materialization, approval render, mirror reconnect, and paired WebGL context
loss/recovery. The metric buffer is local and bounded at 256 samples. The
approval panel now records a measured monotonic mount-to-effect duration via
`observability/latency.ts`; it no longer emits a hard-coded zero. This is a
frontend render-latency sample, not a claim about backend approval delivery.
The context tracker records only a real loss → restore pair and is bound to the
actual scene canvas through the existing product-safe shell; it is not claimed
as measured until a browser context-loss capture is performed. An earlier
post-change suite completed in 52.69 seconds with 142 files and 802 tests
passing; this is a test-duration observation, not a frame-rate benchmark. The
latest focused semantic, motion, receipt, observability, Guided, approval,
voice, fallback, and reduced-motion gate remains recorded in the prior gates;
the new approval-observability addition contributes 3 tests across 2 new files.
The follow-up health/receipt regression gate now covers 9 tests across 2 files,
including the evidence-backed Undo opt-in; the human-language organism-status
bridge adds one focused accessibility regression. The task-outcome status copy
adds deterministic coverage for verified, unverified, refusal, failure, and
 restoration announcements. The pre-account-boundary full suite was 157 files
 and 859 tests,
including the renderer-fallback,
emergency-stop,
retry-control,
approval-presentation, stopped reactive-effects, Guided vocabulary-boundary,
accessible-chat-reply, keyboard skip-to-chat, and Expert-only lazy-loading
regressions.

No post-renovation frame benchmark or p75 field metric is claimed yet. The
existing Vite native-loader warning remains known debt. The pre-account-boundary
final-diff suite completed in 321.33 seconds with 157 files and 859 tests
passing with no unhandled errors; the later 158-file checkpoint is recorded
below. Typecheck, production build (4,304 modules transformed),
lint (0 errors / 120 warnings), port-unit (5/5), CSS/texture canon,
frozen-core, and diff checks also passed. The health-probe cleanup in the
product-safe shell now tolerates a late rejection after a document teardown
without dereferencing a missing `window`.
As part of the performance hardening pass, `GagosChrome` now loads the
Expert-only Council, workforce, operator-profile, and trust surfaces through
`React.lazy`/`Suspense`. The new regression fails if `CouncilDashboard` is
evaluated during a Guided mount; it passes, and the production build emits
separate Expert chunks for those four surfaces. The previous ineffective
dynamic-import warning is gone; the remaining native-loader warning is
unrelated existing build debt. `port:check` remains the documented lab-source
blocker below.

The focused semantic gate now also proves that a disconnected transport with
no admitted snapshot derives a degraded/unavailable posture rather than an
indefinite active-startup posture. A live 2026-09-23 tab reproduced the
disconnected state and exposed “GAGOS controls remain available, but the
organism picture is incomplete.” while keeping the request field and
Emergency stop usable; this is presentation truth only and does not infer
backend readiness.

### Latest follow-up checkpoint — 2026-09-23

The Guided account boundary was tightened after auditing the status pill: the
generated `SovereigntyPanel` is now mounted only in Expert/Mirror, while
Guided uses the product-owned `GuidedAccountPanel`. It has keyboard-reachable
close/keep-working controls, Escape handling, a trapped Tab cycle, focus
restoration to the status pill, and an explicit Expert/Mirror handoff. No
identity credential, operator ID, authority callback, or backend contract was
changed.

The follow-up focused Guided account integration passed 2 files / 15 tests;
typecheck passed. The route-provenance regression passed 1 file / 10 tests.
The serial frontend suite passed 159 files / 872 tests in 258.50 seconds.
Production build passed with 4,306 modules transformed; lint
passed with 0 errors / 120 warnings; port-unit passed 5/5; CSS/texture canon,
frozen-core, and `git diff --check` passed. This remains implementation
evidence, not production-readiness evidence.

The presentation adapter now scopes route labels to the current measured turn
window. A previous local/cloud route is not shown for a new turn until a
current-turn route event carries a real privacy observation; an event after
the current `turn.started` marker remains visible. This preserves route
inspectability without turning retained history into current truth.

Guided Emergency Stop copy now uses “Stop is on/off,” “Request resume,” and a
human reason instead of latch, operator, or privileged-authentication terms.
The measured stop endpoint, presentation latch, and Expert/Mirror diagnostic
copy remain unchanged. Focused Emergency Stop coverage passed 1 file / 6 tests.
The untouched default reason follows an experience-mode switch while a custom
operator-entered reason remains unchanged. The serial frontend suite then
passed 159 files / 873 tests in 257.70 seconds; this remains implementation
evidence, not production-readiness evidence.

The final gate refresh also passed typecheck, production build (4,306 modules),
lint (0 errors / 120 warnings), port-unit (5/5), CSS/texture canon,
generated/protected-path review, frozen security review, and `git diff --check`.
`npm run port:check` remains the known fail-closed ownership diagnostic: the
dedicated worktree has no lab tree and reports the pre-existing missing
`components/QualityTierProvider.tsx` source. No generated workaround was
applied.

### Latest browser validation — 2026-09-23

The isolated Vite preview rendered the actual WebGL organism as the focal
anchor. The `Make something` starter prefilled the primary request field
without submitting a turn. Switching to Expert/Mirror exposed the progressive
Task anatomy while preserving that request; returning to Guided preserved it
and exposed no internal model/provider/council/worker/latch/operator terms in
visible Guided copy. Emergency Stop details closed through its accessible
control and restored focus to the disclosure trigger. The browser console
reported only the existing Three.js deprecation warning. This run does not
claim forced context-loss recovery, reduced-motion emulation, full
screen-reader validation, or the complete required viewport matrix.

### Post-optimization browser smoke — 2026-09-23

The exact bytes after the mutable aurora/spine-flash frame-state optimization
were opened in the isolated Vite preview at `127.0.0.1:5173`. Guided mode
retained the real organism, Emergency Stop, primary request field, voice
controls, truthful disconnected/setup copy, and all three starter paths in the
narrow mobile composition. Selecting `Make something` filled `Create a simple
plan for this project` without adding a conversation item. The browser emitted
no new application errors. This is a shell/continuity smoke only; it does not
claim GPU context-loss recovery, OS reduced-motion emulation, p75 performance,
live backend mutation/verification, or human validation.

### Performance probe boundary — 2026-09-23

The browser harness's read-only page evaluator was queried directly on the
post-optimization preview. It exposed none of `performance`,
`requestAnimationFrame`, or `PerformanceObserver`, so it cannot provide an
attributable local frame sample or p75 comparison. The application-side metric
hooks remain implemented and tested; an operator-controlled browser or field
run is still required before reporting performance targets.

### Guided Tasks boundary — 2026-09-23

Guided now uses a product-owned read-only Tasks projection for the existing
measured task records. Expert/Mirror still mounts the generated technical
Missions surface. Guided reports only human-facing task status, permission
needed, and verification availability; it does not expose mission IDs,
Council/authority/worker terms, or technical decision controls. Focused Tasks
and shell coverage passed 2 files / 4 tests. The post-refactor serial frontend
suite passed 160 files / 875 tests in 270.18 seconds; typecheck, production
build (4,306 modules), lint (0 errors / 120 warnings), port-unit (5/5), canon,
protected-path, frozen-core, and diff checks also passed.

The surrounding Guided copy now says, “If a task needs your permission, GAGOS
will ask before the action.” This keeps the permission boundary truthful when a
task is already permitted or only being recorded; it does not change the
backend authority decision or imply that a prompt is guaranteed for every task.
The regression was red before the copy change, then a fresh full frontend
Vitest run passed 160 files / 875 tests in 65.88 seconds and typecheck passed.
The same refresh passed production build (4,308 modules), lint (0 errors / 120
warnings), port-unit (5/5), CSS/texture canon, protected-path, frozen-core, and
diff checks. `npm run port:check` remains a known fail-closed ownership gap
because the dedicated worktree does not contain the ignored lab source
`components/QualityTierProvider.tsx`; no generated source was copied to bypass
that check.

## Accessibility and responsive results

The compact live preview was also checked after boot at 481x778. The
conversation rail now uses a restrained near-black membrane, border, and
shadow so voice guidance and the primary request controls remain readable
when the rail shares vertical space with the organism; the being remains the
upper visual anchor.

The implementation preserves keyboard input, explicit focus targets, ARIA live
state, modal focus containment/restoration for approval, touch-sized controls, and a non-3D
conversation path. Guided hides technical dashboard mounts instead of merely
visually masking them. The browser smoke capture confirmed the Guided opening,
starter paths, input, connection notice, and Emergency stop render without a
backend session. A fresh Vite tab on 2026-09-22 additionally confirmed through
the accessibility tree that `Make something` fills
`Create a simple plan for this project` without submitting a user message,
Expert exposes Task plus collapsed Intelligence/Authority/Memory/Evidence
groups, and keyboard activation of `Skip to the chat` focuses the primary
input. The fresh tab reported no application errors; only the existing
Three.js Clock deprecation warning was logged. The required viewport matrix
passed with the input, Guided control, and Emergency stop present and no
page-level horizontal overflow at 320×568, 375×812, 768×1024, 1024×768, and
1440×900. The narrow 320px capture also verified the full multi-line composer
remains above the connection notice; the tablet pass verified the wrapped
composer keeps the primary field readable (225px at 768px wide and 283px at
1024px wide).

After the semantic R3F hook was memoized, a second fresh tab on 2026-09-22
repeated the Guided/Expert/prefill/keyboard checks successfully at
127.0.0.1:5177. It again showed truthful offline/setup copy, preserved the
empty conversation log after starter prefill, retained the five Expert anatomy
groups, and focused the primary textbox through the keyboard skip action.

The follow-up fresh tab also showed the standalone health pill as measured
offline after the local health request failed, while the unit regression holds
the pre-response state at `checking…` rather than claiming connected. A
measured `/health` response is now described as `reachable`, not `connected`,
because health reachability does not prove current mirror freshness. The
starter prefill, Expert anatomy, and 320px no-overflow checks were repeated;
the only browser console output was the existing Three.js Clock deprecation
warning.

Guided recent activity now uses measured human labels and omits raw event,
mission, and worker identities; Expert retains those details. Screen-reader
user validation, forced renderer-failure capture, and reduced-
motion browser capture remain required evidence before a production-readiness
claim.

On 2026-09-23, a newly opened tab initially restored the persisted Expert
preference. Activating Guided through the real mode control then showed Guided
selected and Expert unselected, hid model/swarm controls and the technical
anatomy, and retained the starter paths, setup copy, primary input, voice note,
and Emergency stop. This confirms the boundary after an actual mode switch;
it does not claim that persisted Expert state is silently reset.

A further live tab check on 2026-09-23 opened in Guided, activated `Make
something`, and observed the composer value `Create a simple plan for this
project` with no conversation item added. Switching to Expert exposed the
model/swarm controls and the five progressive anatomy groups; switching back
to Guided hid them again while preserving the draft. A live screenshot also
confirmed the being remains the visual focal point above the conversation
controls. Exact viewport-matrix and reduced-motion claims remain limited to
the dated captures above and their existing tests; this run did not fabricate
new viewport or motion metrics.

The 2026-09-23 browser QA pass repeated the required responsive matrix at
320×568, 375×812, 768×1024, 1024×768, and 1440×900. Each measured viewport
reported `scrollWidth === innerWidth`, with the primary input and Emergency
Stop visible within the viewport. The live accessibility path also activated
`Skip to the chat` with Enter and focused the `Talk to GAGOS` field; the
keyboard regression is included in the full suite. The browser stylesheet
inspection found 14 `prefers-reduced-motion` media rules across the loaded
stylesheets. The environment itself was not emulating reduced motion
(`matchMedia(...).matches === false`), so this strengthens CSS/test evidence
but is not a reduced-motion runtime capture.

The isolated-worktree Vite tab was rechecked on 2026-09-23 at
`127.0.0.1:5173`. Its accessibility tree exposed the degraded/unavailable
copy, the derived human-language organism status, Guided and Expert/Mirror
controls, the primary request field, all three starter paths, voice controls,
and Emergency stop; the same five viewport sizes again measured no horizontal
overflow and retained the input and stop control. Selecting a starter path
prefilled the request field without adding a conversation item, and switching
to Expert/Mirror then back to Guided preserved that draft. This is a
disconnected local-session observation, not evidence of a live backend
mutation or verification journey.

A subsequent normal-mode preview at the same local URL rendered the actual
WebGL organism rather than the fallback surface. The organism remained the
strong visual anchor while the request field, Guided/Expert switch, starter
paths, offline/setup state, and Emergency Stop remained visible. The supported
browser automation surface provided no media-emulation or forced-context-loss
control, so reduced-motion and renderer-recovery captures remain explicitly
unperformed rather than simulated. The temporary preview was stopped and port
5173 was verified released.

The same responsive pass used the browser's native accessibility interaction at
320×568: after the app finished loading, Tab focused `Skip to the chat` and
Enter focused the `Talk to GAGOS` request field. A direct Playwright locator
click did not preserve that focus in this harness, so it was not counted as
product evidence; the native accessibility path is the authoritative result.

On 2026-09-23, a normal 1200×720 live preview exposed a desktop composition
issue: the integrated chat rail had a height cap but no internal overflow
boundary, so the welcome/starter content pushed the primary request bar below
the visible composition. The product-owned CSS now gives the desktop rail a
bounded flex height, scrolls welcome/history content inside that rail, and
keeps the request bar fixed at the bottom. The follow-up screenshot showed the
request field, voice/send controls, organism, and status strip in the first
composition; the accessibility tree was unchanged and browser error logs were
empty. This is a visual shell correction, not a new backend or mutation claim.

After the reduced-motion seam change, a fresh isolated preview on port 5174
again rendered the real WebGL organism and the complete Guided control path.
The browser's read-only evaluation surface did not expose `performance` or
`requestAnimationFrame`, so no runtime frame-time sample was accepted as
evidence. The app-side bounded frame sampler remains implemented and covered
by the existing instrumentation contract, but the Phase 0-to-renovation
frame comparison and field p75 metrics remain open.

A fresh live Guided DOM audit after the copy correction found none of the
internal vocabulary terms Governance, Stigmergy, Council, workforce, Hiring,
Vulture, Terminal, provider, model, worker ID, organ ID, or capability. It
also confirmed the browser speech-service disclosure and keyboard Enter
activation of `Skip to the chat` focusing the primary request field. This is
copy/accessibility evidence only; it does not claim a backend mutation path.

The Guided Emergency Stop boundary is also covered by a focused DOM regression:
partial/unknown stop confirmation remains human-readable while raw stop hooks,
operator IDs, and authentication IDs stay absent from Guided details. The
Expert/default rendering path still exposes those measured fields for mirror
inspection. Its details disclosure now exposes an explicit `aria-controls`
relationship and restores keyboard focus to the trigger when the disclosure
closes, so the optional technical explanation cannot strand keyboard users.
The focused Emergency Stop suite covers this restoration; the full constrained
suite contains 859 passing tests.

The follow-up live audit on 2026-09-23 at isolated port 5174 rendered the
actual organism and the complete Guided opening. Clicking `Ask & understand`
filled the primary request field without adding a conversation message or
submitting a request. Opening Emergency Stop details while the local service
was unavailable showed only last-known/unavailable human copy and no raw hook
or identity fields. Switching to Expert/Mirror exposed the progressive
Task/Intelligence/Authority/Memory/Evidence groups, then switching back restored
Guided without losing the prefilled request. This is local UI continuity and
copy evidence; it does not claim a mutation, approval, or verification journey.

A fresh isolated port-5173 preview on 2026-09-23 again rendered the actual
organism and kept the Guided input, starter paths, truthful offline/setup copy,
and Emergency Stop available after the fallback-retry change. The browser
surface still cannot force WebGL context loss or reduced-motion emulation, so
those recovery captures remain explicitly unperformed.

The follow-up isolated port-5173 preview opened the Guided account control and
exposed only “Account status unavailable”, measured-unavailable explanation,
and the human Expert/Mirror handoff; no sovereignty, credential, or operator
identity vocabulary appeared. Pressing Escape closed the dialog and restored
focus to the account control. Forward Tab from the last action wrapped to
Close, and reverse Shift+Tab from Close wrapped to Keep working. Activating
Open Expert / Mirror switched to the existing Expert progressive anatomy and
technical status surface. This is normal-mode visibility evidence only; it
does not claim an authenticated identity or mutation journey.

The live-region wording is task-state aware: verified completion announces that
verification passed, unverified completion explicitly remains unverified, and
refusal, failure, restoration, stopped, stale, and approval-hold states retain
their human-language distinction. The pure status derivation is covered by the
same full-suite checkpoint above; it does not infer authority or backend
verification.

The Guided approval boundary is exposed as a modal `alertdialog` with explicit
What, Where, impact, and denial semantics. Its `aria-modal="true"` contract,
initial focus, focus wrapping, and restoration are covered by the approval
regression suite; the same suite covers a replay that pauses on a newly issued
approval without presenting an interim receipt, an unconfirmed decline without
overstating the server outcome, and Guided browse copy without model/provider
terms. Its accessible name is the human-facing “GAGOS permission request”; the
technical Expert panel retains its own operational detail. When the
pending-approval record does not carry a complete effect
boundary, Guided names only the measured target or command and says that the
boundary is unavailable; it does not infer a project-wide scope. Authority
decisions still flow through the existing audited adapter callbacks. For browse
approvals, the privacy note is limited to the page and fields present in the
measured approval record; it does not make an unsupported claim about runtime
exposure. The
presentation kernel also keeps a real approval hold primary when mirror
coherence is stale or degraded: the user still sees the decision boundary,
while the body remains marked stale/degraded and does not imply currentness.
The integration approval suite also asserts this human-facing accessible name
across initial, held, and cleared approval states.

On 2026-09-23, a same-site local backend journey exercised the real Guided
conversation path. A first diagnostic run on port 5177 with the default
`localhost:8000` API exposed the expected development CORS/cookie host
mismatch; no product contract was changed. The controlled rerun used the
allowed Vite port 5173 with `VITE_API_BASE=http://127.0.0.1:8000`. Session
bootstrap succeeded, the real `/api/v1/chat` request returned HTTP 200, and the
final accessibility tree contained `GAGOS: Hello! How can I assist you today?`.
The source fix and regression test keep a real conversational reply in the DOM
conversation log, so Guided and assistive-technology users receive the same
answer that the voice/organism layer presents. This evidence covers a normal
read-only conversation only; it does not claim an authenticated mutation,
approval, or verification journey.

The post-semantic-correction live smoke pass at `127.0.0.1:5173` again exposed
the actual Guided opening: the exact Ask & understand description, three
prefill-only starter paths, voice disclosure, truthful unavailable setup copy,
and Emergency Stop. The starter filled the request without adding a
conversation item; Expert/Mirror revealed its technical groups and controls;
returning to Guided preserved the draft. This is normal-mode UI evidence only,
not authenticated mutation, approval, verification, or performance evidence.

## Changed files

See `git diff --name-only` for the exact working-tree list. The important
surfaces are `SuperbrainApp.jsx`, `GagosChrome.jsx/.css`, the product-owned
`GuidedApprovalPanel.tsx`, `LivingWorkspaceShell.tsx`,
`GuidedAccountPanel.tsx`,
`MirrorConnectionNotice.tsx`, the new semantic, receipt, observability, and
workspace-visibility, setup-copy, emergency-stop hold, Guided vocabulary and
stop-detail redaction, coherence physics, unavailable/degraded posture guard,
and human-validation
modules/tests, plus the bounded
reactive-effects path, including its Emergency Stop and coherence seam
regressions. Coherence semantics are owned by
`frontend/src/livingMirror/being/coherenceSemantics.ts` with pure tests. The
store adapter in `frontend/src/livingMirror/being/presentationFromStores.ts`
now scopes terminal signals to the current turn and requires a surface-local
verifier verdict before promoting new work;
`SuperbrainReactiveEffects.coherence.test.tsx` proves stale evidence is
visibly attenuated without changing the admitted event source.
The spine-flash hot path is now covered by a fixed scratch-pool implementation
in `SuperbrainReactiveEffects.jsx`; frame-metric behavior is regression-tested
in `frontend/src/livingMirror/observability/frontendMetrics.test.ts`.
Approval render timing is owned by
`frontend/src/livingMirror/observability/latency.ts` and its Guided approval
component regression. Receipt recovery opt-in is owned by
`frontend/src/livingMirror/experience/receipts.ts` and `ReceiptCard.tsx`, with
regressions in `receipts.test.ts` and `ReceiptCard.test.tsx`.
Expert-only deep surfaces are covered by
`frontend/src/workbench/GagosChrome.lazy.test.tsx` and remain out of Guided
startup; the latest production build emitted separate chunks for them. The port-managed
approval and HUD files remain unchanged. The baseline and this implementation
document are new evidence artifacts. The latest accessibility regression also
touches `frontend/src/workbench/hooks/useWorkMaterialization.js` and
`frontend/src/workbench/GagosChrome.voice.test.tsx`; the keyboard focus
regression is in `frontend/src/workbench/GagosChrome.status.test.tsx`, and the
Guided modal approval semantics are owned by
`frontend/src/livingMirror/GuidedApprovalPanel.tsx`, including its keyboard
focus containment and restoration regression. Replay-pause coverage is in
`GuidedApprovalPanel.observability.test.tsx` and
`GagosChrome.approval.test.tsx`.

### Bounded worker reabsorption — 2026-09-23

Terminal worker visuals now have a product-owned, pure expiry helper and a
coarse renderer-side prune timer that mounts only while terminal motes exist.
Returned, dissolved, failed, and killed worker evidence remains visible for
the measured reabsorption window, then is removed even if no later mirror event
arrives. Active and unknown-timestamp entries remain; the helper never treats
missing timing as permission to discard evidence. The visual pool remains
capped at eight workers and the change does not expose worker identities or
alter worker execution truth.

The focused semantic-effects regression passed 6/6 tests, the retained-worker
regression passed 2 files / 7 tests, the affected effects/reduced-motion
coverage passed 5 files / 10 tests, and typecheck passed. The refreshed full
frontend suite passed 161 files / 878 tests in 59.86s; build passed with 4,308
modules, lint passed with 0 errors / 120
warnings, port-unit passed 5/5, and CSS/texture canon, protected-path,
frozen-core, and `git diff --check` passed. `npm run port:check` remains the
pre-existing fail-closed ignored-lab source gap. No new browser worker-event
capture was claimed because the available page cannot synthesize the required
mirror worker lifecycle; prior responsive, keyboard, organism, and fallback
browser evidence remains valid for the unaffected shell paths.

### Renderer context-loss presentation bridge — 2026-09-23

The product-owned Superbrain shell now preserves a measured canvas-loss flag
alongside the managed `.webgl-fallback` marker. A real `webglcontextlost` event
immediately projects “Visual organism unavailable. GAGOS controls are still
working.”; `webglcontextrestored` clears that presentation only after the
managed fallback marker is re-read. This prevents the MutationObserver from
mistaking the notice's own DOM insertion for renderer recovery. The bridge
does not approve, stop, retry, or otherwise mutate backend work.

Focused renderer coverage passed 4 files / 12 tests, including loss → notice →
restore, lazy import/render failure, managed fallback observation, and context
recovery tracking. The full frontend Vitest suite then passed 160 files / 876
tests; typecheck, build (4,308 modules), lint (0 errors / 120 warnings),
port-unit (5/5), canon, protected-path, frozen-core, and diff checks passed.
The browser evaluator could not construct or dispatch a DOM/WebGL event in its
page sandbox, so a real GPU context-loss capture remains unclaimed.

### Frame-path allocation hardening — 2026-09-23

The product-owned `SuperbrainReactiveEffects` spine-flash path now reuses a
fixed scratch pool for its travelling bead and bounded point strip. Its aurora
and spine-flash decay state is also mutated in stable refs rather than spread
into new objects on every animation frame; event-time and initial-render
helpers retain their existing behavior. This reduces transient garbage without
changing phase, coherence, stop, reduced-motion, or verification semantics. The
worker pool remains capped at eight and the frame sampler continues to report
only local numeric metrics.

The focused organism/observability gate passed 5 files / 8 tests for this
follow-up; the preceding scratch-pool and frame-sampler gate passed 6 files /
12 tests, including a
new deterministic regression for p50, p95, and dropped-frame samples. The
refreshed full frontend suite then passed 161 files / 880 tests in 266.99
seconds;
typecheck and production build passed (4,308 modules), lint passed with 0
errors / 120 warnings, and the existing port-unit, canon, protected-path,
frozen-core, and diff checks remain green. This is implementation and
instrumentation evidence, not a claim of p75 field performance: the browser
surface still cannot provide an attributable before/after frame benchmark.

### Ambient-motion preference boundary — 2026-09-23

The product-owned workspace shell now keeps its explicit `Pause ambient motion`
control responsive even when the generated reduced-motion store cannot attach a
`matchMedia` listener (for example, an SSR-like or test environment). The
control still delegates the preference to the existing shared motion store and
does not alter backend authority or execution. Its `aria-pressed` state and
Pause/Resume label update immediately from the local product boundary.

The focused workspace visibility suite passed 4/4, including persistence of
the pause preference. The refreshed full frontend suite passed 161 files /
880 tests in 59.71 seconds; typecheck and production build passed (4,308
modules), lint passed with 0 errors / 120 warnings. A live 127.0.0.1:5173
preview exposed the Expert/Mirror `Pause ambient motion` button, and after
activation exposed `Resume ambient motion` with `aria-pressed=true`; browser
error logs were empty. This is direct manual-preference evidence, not a claim
that the browser harness emulated the OS `prefers-reduced-motion` media query.

### Guided first-run density correction — 2026-09-23

The live narrow composition showed that optional browser-voice consent and its
approval-safety explanation were taking priority over the first-run choices.
Guided now keeps that consent explicit inside a collapsed `Voice options
(optional)` disclosure; opening it exposes the existing checkbox, browser
processing notice, and “Voice is for conversation; actions still need your
approval” copy unchanged. Starter paths now precede the detailed local-setup
readiness panel, so the user’s first decision is visible at the initial scroll
position while setup truth remains available immediately after the choices.
No voice route is enabled implicitly and no authority callback changed.

The focused voice/starter/readiness gate passed 3 files / 21 tests; the full
serial frontend suite passed 161 files / 881 tests in 279.52 seconds;
typecheck and production build passed with 4,308 modules; lint passed with
0 errors / 120 warnings. A live 319×778 preview measured the compact voice
disclosure at 30px, placed the starter grid at 436px, retained the request
composer and Emergency Stop, and showed the disclosure contents through the
accessibility tree when opened. This is composition/accessibility evidence only;
it does not claim authenticated mutation, GPU context-loss, OS reduced-motion,
p75 performance, or human-validation evidence.

The follow-up desktop probe found the same density problem in a different form:
the un-dismissed first-run coach was consuming the integrated rail's available
height below the starter choices. In the integrated Guided shell the coach is
now suppressed because the primary guidance, starter paths, and setup detail
already provide the first-run path; Expert retains the existing coach. The
desktop rail remains bounded but grows to `min(62dvh, 440px)`, keeping the
composer at the bottom while the starter/readiness region scrolls internally.

At 1280×720, the loaded preview measured the chat rail at 440px high, the
starter grid beginning at 363px, the welcome viewport ending at 460px, and the
composer fixed from 498px to 566px. All three starter buttons, the primary
input, Guided control, and Emergency Stop remained in the accessibility tree;
document `scrollWidth` equaled `innerWidth` and the browser error log was
empty. The focused onboarding/voice/starter gate remained 3 files / 24 tests;
the refreshed serial suite passed 161 files / 881 tests in 267.35 seconds;
typecheck and production build passed with 4,308 modules; lint passed with
0 errors / 120 warnings. This improves first-run composition only and does
not claim full starter copy above the fold, GPU/reduced-motion/performance,
authenticated mutation, or human-validation evidence.

### SSR-safe motion preference boundary — 2026-09-23

The product-owned workspace shell now reads the platform reduced-motion query
through an SSR-safe helper. Missing `window` or `matchMedia` is treated as an
unavailable preference rather than a render exception; a real media query still
disables the manual ambient-motion toggle as before. The helper regression
passed 5 tests and typecheck passed. The refreshed full suite passed 161 files
/ 882 tests in 267.38 seconds; the production build transformed 4,308 modules
and lint passed with 0 errors / 120 warnings. This closes a render-safety edge
at the browser capability boundary; it does not claim OS reduced-motion
emulation in the available browser harness.

### Voice remains conversation-only at the approval boundary — 2026-09-23

The browser-recognition path only places a final transcript into the request
draft and focuses the input for human review. It does not call the supervised
approval replay. A strengthened regression now simulates a final spoken
“yes, go ahead” while a measured pending approval is present: the draft is
updated, `approvePendingApproval` is not called, and the Guided permission
dialog remains visible. The focused voice suite passed 17 tests; the refreshed
full suite passed 161 files / 883 tests in 267.11 seconds. This proves the
frontend boundary in deterministic coverage; it does not claim a live backend
mutation or verification journey.

### Presentation kernel authority contract — 2026-09-23

The semantic presentation tests now include a compile-time contract that
`BeingFacts` cannot grow `canExecute`, `approved`, `authorized`, or `allowed`
fields, plus a runtime assertion that the derived presentation does not expose
those keys. Approval remains a measured presentation boundary only; authority
continues to live in the existing audited adapter/backend path. The focused
semantic kernel/store gate passed 2 files / 24 tests, and the refreshed full
suite passed 161 files / 884 tests in 272.17 seconds. This is a future-drift
guard, not an authority implementation or a live approval claim.

### Background-tab frame evidence boundary — 2026-09-23

The bounded frame sampler now listens for document visibility changes and
discards the transition frame after a tab is hidden or shown. A browser may
pause `requestAnimationFrame` while the tab is backgrounded; that interval is
not renderer work and must not be reported as a dropped-frame period or folded
into p50/p95. The sampler remains local-only, capped, and numeric. Deterministic
coverage proves a simulated two-second background pause produces no dropped
frame sample; this improves evidence quality but is not a browser p75 or GPU
benchmark.

### Current-turn verification boundary — 2026-09-23

The presentation adapter now treats `mirror.lastVerification` as retained
inspection data unless a verification event is present after the latest
measured `turn.started` marker. An explicit verdict attached to the focused
content surface remains valid because it is bound to that surface. This keeps
an older pass from turning a later completed-but-unverified turn into verified
truth while preserving current-turn verification evidence. Focused
presentation-store coverage now passes 12 tests, including both the retained
pass rejection and current-turn pass acceptance. No backend, authority, or
mirror storage contract changed.

### Live Guided/Expert browser evidence — 2026-09-23

A fresh in-app browser preview at `http://127.0.0.1:5173/` exercised the
narrow Guided composition through its accessibility tree. Clicking
`Ask & understand` only prefilled “What can you help me with?”; the welcome
surface and Send control remained present, so no submission was inferred.
Switching to Expert / Mirror exposed the progressive Task, Intelligence,
Authority, Memory, and Evidence groups while preserving that draft. Returning
to Guided hid the technical groups and preserved the draft. Opening Guided
Emergency Stop exposed only “Stop state unavailable,” last-known/unavailable
copy, Refresh, Reason, and Close controls; raw hook, operator, and
authentication identifiers were absent. The backend was offline during this
probe, so this is composition/accessibility evidence only—not authenticated
mutation, verification, GPU context-loss, reduced-motion, or screen-reader
evidence.

### Narrow Guided keyboard and starter recheck — 2026-09-23

The fresh local preview at `127.0.0.1:5173` retained the primary request
field, Emergency Stop, and all three Guided starter paths without horizontal
overflow (`scrollWidth` 319px, viewport width 319px). The native keyboard path
`Tab → Skip to the chat → Enter` moved focus to `Talk to GAGOS`. Selecting
`Ask & understand` filled `What can you help me with?` while leaving the
conversation log without a user message and without submitting the turn.

A visible-copy scan found no Guided internal vocabulary. The only substring
match for `organ` was the truthful disconnected-state phrase “organism picture
is incomplete,” not an organ identifier or technical navigation label. The
backend was offline during this check, so mutation, approval, verification,
renderer-loss, reduced-motion, screen-reader, performance, and human-
validation evidence remain unclaimed.

### Live API reachability versus authenticated mirror state — 2026-09-23

The isolated backend was started with the canonical local command for a
read-only runtime probe. `GET /health` returned 200 and the Guided shell
showed the service as reachable, while `GET /api/v1/auth/session` returned
`authenticated:false` and both `/api/v1/mirror/snapshot` and
`/api/v1/mirror/stream` returned 401. The frontend therefore kept the
organism projection degraded/unavailable instead of treating API reachability
as a current mirror or authority state. No account was created, no credentials
were entered, and no mutation or approval was attempted. The temporary API
process was stopped after the probe. Authenticated approval, verification,
replay/live-barrier, and rollback evidence remain backend/session-owned.

### Operational picture unavailable boundary — 2026-09-23

The first implementation keyed the unavailable copy only to the raw 401
announcement, but the existing mirror client can replace that announcement
with a later reconnect message. The presentation copy now also treats the
admitted `projection: unavailable` state as the product boundary. Guided shows
“Operational picture unavailable” and “GAGOS is reachable, but the live picture
is unavailable in this session,” with a retry action; it does not expose 401,
unauthorized, session, or provider vocabulary. Expert retains only the existing
technical transport/projection evidence. This changes presentation wording
only; it does not grant access, alter mirror transport, or change authority.

Focused copy coverage passed 6/6 tests; the live unauthenticated probe showed
the revised copy and retry control; typecheck passed. The refreshed full suite
passed 161 files / 888 tests in 279.00s; production build transformed 4,309
modules; lint passed with 0 errors / 120 warnings; port-unit passed 5/5; CSS
canon, texture canon, frozen-core, and diff checks passed. `npm run port:check`
still fails closed on the pre-existing ignored-lab source gap.

### Mirror retry touch target — 2026-09-23

The product-owned mirror retry action now uses a 44px minimum height instead of
the earlier 32px compact target. A fresh 1280×720 preview measured the live
“Try again” button at 44px high with `min-height: 44px`; the same audit reported
no horizontal overflow. This is a narrow touch-target/composition check, not a
claim of complete screen-reader, mobile-device, or human accessibility
validation.

### Exact-tree verification refresh — 2026-09-23

The review tree was re-run without source changes after the touch-target
follow-up. The serial frontend suite passed 161 test files / 888 tests in
282.66 seconds. Lint passed with 0 errors / 120 warnings; port-unit passed
5/5; CSS canon, texture/GLB canon, frozen-core, and `git diff --check` passed.
The existing production build/typecheck evidence remains valid for this same
source snapshot. These automated gates do not close the authenticated live
journey, GPU context-loss, OS reduced-motion, field p75, full screen-reader,
or human-validation gaps.

### Core Guided touch-target expansion — 2026-09-23

The browser audit found four compact Guided controls below the intended touch
target: account status (31px), Guided/Expert mode choices (28px), the optional
voice disclosure (30px), and setup recovery disclosure (17px). Product-owned
CSS now gives each a 44px minimum target while preserving the existing
keyboard/ARIA controls. HMR verification measured account, both mode choices,
voice disclosure, recovery disclosure, and mirror retry at 44px; the 1280×720
preview retained `scrollWidth === innerWidth`.

Affected Guided/connection coverage passed 4 files / 22 tests; the refreshed
serial suite passed 161 files / 888 tests in 279.82 seconds. Typecheck and
production build passed with 4,309 modules; lint passed with 0 errors / 120
warnings. This is direct browser geometry evidence, not full device,
screen-reader, reduced-motion, or human validation.

### Primary request input touch target — 2026-09-23

The same live audit found the primary `Talk to GAGOS` input itself rendered at
25px, despite its surrounding composer controls meeting the target. The
product-owned composer CSS now gives the input a 44px minimum height. A fresh
preview measured the input and all previously audited controls at 44px with no
horizontal overflow at 1280×720. Focused Guided/connection coverage remained
22/22, typecheck/build/lint passed, and the prior exact-tree full suite remains
green; this is not a full device or screen-reader validation claim.

### Exact post-input suite and generated ownership audit — 2026-09-23

The exact post-input source tree passed the serial frontend suite: 161 test
files / 888 tests in 269.69 seconds. CSS canon, texture/GLB canon, frozen-core,
and `git diff --check` passed. The managed generated
`ApprovalPanel.tsx` and `SuperbrainHUD.tsx` files remain untouched in content:
normal Git status shows mixed LF/CRLF working-tree metadata, while
`git diff --ignore-space-at-eol` and the word diff are empty. No generated
artifact was restored, ported, or edited to satisfy this audit.

### Guided voice copy boundary — 2026-09-23

The product-owned `livingMirror/voicePresentation.ts` mapper now keeps raw
voice state at the presentation boundary. Guided maps measured local voice
states into human copy such as `Voice input unavailable`, `Listening`, and
`Ready to review`, with a typing fallback when voice cannot be used. Expert /
Mirror preserves the raw status and error text so technical diagnosis remains
available. This mapper is presentation-only: voice still updates a draft and
never calls or implies approval of a mutation.

The change followed a deliberate red/green test cycle: the new mapper test
first failed because the production module did not exist, then passed 4/4
after implementation. The integrated voice/onboarding coverage passed 3 files
/ 28 tests. A live isolated preview showed `Voice input unavailable` in
Guided and retained `local transcription unavailable` plus `Voice route` in
Expert / Mirror, confirming the copy boundary without backend mutation.
The exact post-change serial frontend suite passed 162 files / 892 tests in
279.00 seconds; typecheck and production build passed with 4,310 transformed
modules; lint passed with 0 errors / 120 warnings; port-unit passed 5/5; CSS
canon, texture/GLB canon, frozen-core, diff, and experience-log checks passed.
No authority, backend, generated Superbrain, or security-core contract
changed.

### Mobile connection notice spacing — 2026-09-23

A fresh 319px browser audit found a real responsive defect that the earlier
overflow-only check did not catch: the 111px Guided connection notice covered
about 24px of the composer action row. The product-owned mobile CSS now
reserves a stable 132px lower band for Guided copy. Expert keeps its raw
technical transport/projection detail, which measured 146px in the same
preview, so it receives a 168px reserve and a shorter narrow-screen work area.

After HMR, Guided measured 13px between the connection notice and composer,
with 24px between the notice and the action row. Expert measured 14px and 25px
respectively; its navigation remained above the work area. Both modes reported
`scrollWidth === innerWidth` at the 319px viewport. Focused shell coverage
passed 3 files / 13 tests; the exact serial frontend suite passed 162 files /
892 tests in 279.68 seconds; typecheck and production build passed with 4,310
modules; lint passed with 0 errors / 120 warnings; port-unit passed 5/5; CSS
canon, texture/GLB canon, frozen-core, and diff checks passed. This is direct
narrow-browser evidence; 375px/768px/1024px/1440px and OS media-query
emulation remain covered by the earlier matrix or explicitly unclaimed where
the browser harness lacks that capability.

### Guided shell vocabulary regression guard — 2026-09-23

The Guided shell now has a rendered accessibility-DOM regression that scans
the complete `GAGOS conversation` surface for internal architecture terms:
governance, council, workforce, provider/model, worker, organ, capability,
policy, swarm, and related technical labels. This complements the existing
focused guards for approval, voice, tasks, stop details, history, and lazy
Expert surfaces; it does not scan source comments or hide Expert content.

The focused status/onboarding/approval coverage passed 3 files / 24 tests,
including the new guard. The refreshed serial frontend suite passed 162 files /
893 tests in 290.59 seconds; typecheck passed; production build transformed
4,310 modules; lint passed with 0 errors / 120 warnings; port-unit passed 5/5;
CSS canon, texture/GLB canon, frozen-core, diff, and experience-log checks
passed. No authority, backend, generated Superbrain, or security-core contract
changed.

### Integrated Guided approval fact guard — 2026-09-23

The real `GagosChrome` approval journey now asserts the complete human decision
boundary in the rendered Guided DOM: `What`, `Where`, `It can affect`, and `If
you say no`, alongside the explicit Allow once / Don't allow actions. This is
an integration regression guard over the product shell, complementing the
component-level honesty tests for missing effect boundaries. Focused approval
coverage passed 2 files / 13 tests. It does not create authority, infer scope,
or claim that an authenticated backend mutation completed.

The post-change serial frontend suite passed 162 files / 894 tests in 262.16s;
typecheck and production build passed (4,310 modules), lint passed with 0
errors / 120 warnings, and the port-unit, CSS canon, texture/GLB canon,
frozen-core, JSONL, managed-content, and diff checks remained green.

### Full Guided workspace vocabulary guard — 2026-09-23

The vocabulary regression now covers the actual `LivingWorkspaceShell` rather
than only the conversation component harness. Guided renders the human
`Tasks`, `Project files`, and `Recent activity` navigation while the shell
asserts that internal architecture terms remain absent; Expert surfaces remain
covered by their existing technical-mode tests. The focused status/workspace
coverage passed 2 files / 18 tests. This guards presentation only and does not
alter the persisted `beginner` mode or authority behavior.

### Fresh isolated browser composition check — 2026-09-23

The current isolated Vite preview rendered the real WebGL organism. At the
browser evaluator's available 473×778 viewport, `Make something` prefilled
`Create a simple plan for this project` while the conversation log remained at
zero messages; the request input measured 44px high, the composer ended at
635px, and the unavailable operational-picture notice began at 675.91px, so
the notice did not cover the composer. `document.documentElement.scrollWidth`
matched the 473px viewport. Switching to Expert exposed the Task anatomy and
technical voice/transport copy, then returning to Guided preserved the draft
and returned to human copy. Browser logs contained only the existing Three.js
deprecation warning. This is live composition evidence, not the full required
320/375/768/1024/1440 matrix, GPU context-loss, reduced-motion, authenticated
mutation, field-performance, or human-validation evidence; this evaluator did
not expose a viewport override capability.

The same 473px Expert check kept the technical navigation inside its own
scroll container: the navigation viewport measured 449px while its internal
content measured 1,098px, and the page remained 473px wide. This preserves
Expert access without creating page-level horizontal scrolling; it is not a
claim that the full desktop anatomy is reproduced on mobile.

### Fresh Emergency Stop browser check — 2026-09-23

The live Guided Emergency Stop control remained keyboard-visible and opened its
human details surface. Because the local session could not authenticate the
stop-state read, the surface showed `Stop state unavailable`, `Local service
could not be reached`, and `Delivery or outcome is unknown`; it did not claim
that the stop engaged. Closing the details surface removed the panel. The
browser evaluator did not preserve focus after its synthetic locator click, so
this run does not claim live focus-restoration evidence; the product-owned
focus restoration remains covered by `EmergencyControl.test.tsx`.

### Bounded spine-flash geometry follow-up — 2026-09-23

The first fresh renderer audit exposed a real repeated
`THREE.BufferGeometry: Buffer size too small for points data` warning while the
product-owned spine flash was active. The cause was a generic
`BufferGeometry.setFromPoints()` call against Drei's `LineGeometry`, whose
actual contract is a bounded interleaved `instanceStart`/`instanceEnd` segment
pool. The frame path now mutates those existing segment attributes in place,
refreshes the small geometry bounds, and keeps the flash line frustum-safe;
there is no per-frame geometry replacement. The updater is isolated in
`frontend/src/workbench/lineGeometry.js` so the React effect module remains a
clean component export.

Focused geometry/effects coverage passed 2 files / 6 tests and typecheck passed.
A fresh isolated preview after the change produced no BufferGeometry warnings;
the only browser warning was the pre-existing Three.js `Clock` deprecation.
This is a renderer-warning regression result, not a p75 frame-time or GPU
benchmark claim.

### Final constrained verification refresh — 2026-09-23

After the geometry follow-up, the serial frontend suite passed **163 files /
899 tests** in **269.93 seconds**. Typecheck passed; the production build
transformed **4,311 modules**; lint passed with **0 errors / 120 existing
warnings**; and the port-unit suite passed **5/5**. CSS canon, texture/GLB
canon, frozen-core, JSONL, generated/protected review, and `git diff --check`
also passed. `npm run port:check` still fails closed on the pre-existing
missing lab source `components/QualityTierProvider.tsx`; no generated source
was copied or edited to bypass that ownership boundary.

### Mobile Expert progressive disclosure — 2026-09-23

On narrow viewports, `LivingWorkspaceShell` now presents Expert/Mirror as one
bounded `Expert surfaces` disclosure with nested Task, Intelligence, Authority,
Memory, and Evidence groups. The desktop Expert navigation remains unchanged;
the narrow branch uses native `details` controls so technical surfaces stay
keyboard-available without reproducing the full desktop anatomy or creating
page-level horizontal scrolling. Existing surface actions and mode continuity
are preserved; this is presentation compression only and does not change
authority or execution behavior.

The focused responsive shell test passed 1 file / 7 tests. The refreshed
serial frontend suite passed 162 files / 895 tests in 274.05 seconds; typecheck,
production build (4,310 modules), lint (0 errors / 120 warnings), port-unit
(5/5), CSS canon, texture/GLB canon, frozen-core, managed-content, JSONL, and
diff checks passed. The browser evaluator reported a CSS viewport of 1,280px
even when the physical surface was narrow and exposed no viewport override, so
this run does not claim a live mobile Expert capture; the `matchMedia`-true
branch is covered by the deterministic test. GPU context-loss, reduced-motion
browser emulation, field performance, authenticated journeys, and human
validation remain unperformed rather than inferred.

### Shared motion preference boundary — 2026-09-23

The product-owned Guided/Expert DOM shells now project the shared reduced-motion
preference through `data-motion-reduced`. This covers both the OS
`prefers-reduced-motion` signal and the existing Expert `Pause ambient motion`
control, which already governs the 3D seam. When active, DOM travel, pulses,
typing/caret decoration, and transitions stop while task copy, focus, input,
approval, stop, and workspace controls remain mounted and usable. No backend
state or authority behavior changes.

Focused shell/status coverage passed 2 files / 20 tests. The refreshed serial
frontend suite passed 162 files / 896 tests in 280.87 seconds; typecheck,
production build (4,310 modules), lint (0 errors / 120 warnings), port-unit
(5/5), CSS canon, texture/GLB canon, frozen-core, managed-content, JSONL, and
diff checks passed. A live preview switched Expert `Pause ambient motion` →
`Resume ambient motion` → `Pause ambient motion`; the control stayed keyboard
focused and its checked state remained exposed in the accessibility tree. This
is preference/DOM evidence, not OS emulation, GPU context-loss, field
performance, screen-reader, authenticated journey, or human-validation proof.

The follow-up system-preference regression passed 1 file / 8 tests and was
included in the subsequent full run: 162 files / 897 tests in 271.18 seconds.
It measures `prefers-reduced-motion: reduce`, disables the ambient-motion
control with the explicit `Motion reduced by system` label, and confirms that
Conversation and Emergency stop remain present. This is deterministic media
query coverage; it does not claim OS-level browser emulation or screen-reader
validation.

### Live Guided boundary spot check — 2026-09-23

The isolated Vite preview was inspected at its actual CSS viewport of
1280×720. `document.documentElement.scrollWidth` matched `window.innerWidth`
at 1,280px and the document reported `overflow-x: hidden`, so this desktop
capture showed no page-level horizontal overflow. This is desktop evidence
only; the current browser binding did not expose a temporary viewport override
for the required 320px, 375px, 768px, 1024px, and 1440px matrix.

Switching to Guided exposed `Guided front door`, human starter paths, typing,
optional voice copy, and Emergency Stop. Clicking `Ask & understand` changed
the request field to `What can you help me with?` without adding a message to
the conversation log or submitting the request. Opening Emergency Stop showed
`Stop state unavailable` and `Delivery or outcome is unknown` in the
unauthenticated local session; the interface did not claim that a stop engaged.
This spot check does not claim authenticated action delivery, renderer
context-loss recovery, OS reduced-motion emulation, screen-reader validation,
or human usability validation.

## Latest live browser checkpoint — 1200×720 Guided shell

On 2026-09-23, a fresh isolated Vite preview at `127.0.0.1:5180` was inspected
with the browser accessibility tree and screenshot. The real point-field
organism remained the visual anchor while the Guided front door retained its
primary `Talk to GAGOS` field, optional voice disclosure, all three starter
paths, and the visible Emergency Stop control. The unauthenticated session
reported offline/operational-picture-unavailable states without implying that
the stop engaged or that a backend action completed. The screenshot is
composition evidence only; it does not prove the required mobile viewport
matrix, authenticated mutation delivery, GPU context-loss recovery, reduced
motion emulation, screen-reader behavior, field p75, or human validation.

The same browser run opened Emergency Stop details and then closed them. The
accessibility tree showed the unavailable stop state, and focus returned to the
`Inspect emergency stop` trigger after closing. This strengthens the keyboard
focus-restoration evidence without claiming server delivery or engagement.

## Response security-header checkpoint — 2026-09-23

A viewport-capable preview audit exposed two browser console errors from
ineffective HTML meta delivery of `frame-ancestors` and `X-Frame-Options`. The
product-safe Vite configuration now delivers the complete CSP and response
security headers through dev/preview HTTP responses, while the static CSP meta
omits the response-only `frame-ancestors` directive. The ineffective
`X-Frame-Options` and `X-Content-Type-Options` meta claims were removed from
`index.html`; this does not weaken the intended response policy because those
headers are now present on the HTTP response.

Verification: the post-change serial frontend suite passed 163 files / 899
tests; typecheck, production build (4,311 modules), and lint (0 errors / 120
warnings) passed. Port-unit 5/5, CSS/texture canon, frozen-core, and
`git diff --check` also passed. A fresh 320×568 preview returned HTTP 200,
reported no browser console errors, kept `scrollWidth` equal to the viewport with
`overflow-x: hidden`, and confirmed no `frame-ancestors` CSP meta. A direct
response inspection confirmed CSP with `frame-ancestors 'none'`,
`X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, Referrer-Policy,
and Permissions-Policy. This validates the local dev/preview boundary; the
production gateway must preserve the same headers.

## Production preview checkpoint — 2026-09-23

The production bundle was served through Vite preview on `127.0.0.1:5183`
after the header-boundary change. Direct HTTP inspection returned 200 and
preserved the complete response policy: CSP including `frame-ancestors 'none'`,
`X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, strict Referrer-
Policy, and the configured Permissions-Policy. A fresh browser session at
1440×900 had no frontend JavaScript exceptions after the console was cleared and
reloaded, no horizontal overflow, and retained the
Guided input, Emergency Stop, and three starter paths. The same production
preview at 320×568 also had no frontend JavaScript exceptions after reload,
`scrollWidth` equal to the
viewport, `overflow-x: hidden`, all core controls present, and no ineffective
`frame-ancestors` meta claim.

The network trace also showed the expected unavailable-backend boundary when
the API was not running: preview-only `/api/v1/mirror/stream` returned 404 and
the configured `localhost:8000` file-tree request was refused/pending. Static
assets and the GLB loaded successfully; this is not API or gateway health
evidence. The checkpoint does not establish screen-reader behavior, OS
reduced-motion behavior, authenticated mutation/rollback delivery, field p75
performance, or human validation.

## Forced renderer context-loss checkpoint — 2026-09-23

In the rebuilt Vite preview at 1024×768, the browser intentionally invoked the
WebGL `WEBGL_lose_context` extension. The product shell immediately removed the
lost canvas before the post-processing boundary could loop, announced
“Visual organism unavailable. GAGOS controls are still working.”, and kept the
conversation input, voice control, Guided/Expert mode switch, workspace shell,
and Emergency Stop available. Clicking `Retry visual organism` remounted a
fresh canvas, cleared the fallback, preserved `scrollWidth === innerWidth`, and
did not reproduce the earlier Drei post-processing `null.alpha` exception.

The product-safe change is limited to `SuperbrainApp.jsx`: it tracks the measured
loss, unmounts the invalid canvas, and uses a keyed remount on explicit retry;
generated `WorkspaceCanvas` remains untouched. Focused renderer coverage passed
4 tests, the full serial frontend suite passed 163 files / 900 tests, typecheck
and build passed (4,311 modules), lint passed with 0 errors / 120 warnings, and
port-unit/canon/frozen-core/diff/JSONL checks passed. This proves isolated
browser containment and remount recovery, not field GPU recovery or a backend
availability guarantee.

## Known limitations / backend truth still missing

The emergency-stop presentation store and its regression tests are product
owned; they observe the server latch only and do not replace the backend
controller or authority contract.

- Recent mirror event summaries intentionally omit route payloads; the
  presentation adapter therefore reports route as unknown unless a real
  privacy observation is available elsewhere. It never infers local/cloud.
- `npm run port:check` remains blocked by a pre-existing lab mirror gap. The
  dedicated worktree intentionally excludes the ignored `GAG demo/` lab tree,
  so its first diagnostic is the absent
  `components/QualityTierProvider.tsx`. A read-only check from the untouched
  main checkout reaches the lab and reports the underlying scope: 193 managed
  manifest files versus 49 lab files, with 163 manifest sources missing; the
  first reported missing path there is
  `components/canvas/AnatomicalConductorOverlay.tsx`. This requires an
  explicit lab/port migration by its owner. No generated Superbrain file was
  edited or copied to bypass it.
- The current adapter exposes completion (`DirectiveResult.ok`) separately from
  a verifier result. Guided receipts remain unverified until tab evidence says
  pass.
- The current approval replay `PendingApproval` contract does not supply a
  guarded undo capability, so Guided does not render Undo for ordinary replay
  receipts. The product-owned receipt kernel supports the action only when a
  caller supplies `undoAvailable: true` from real recovery evidence and binds
  an explicit `onUndo` callback. No frontend-only tab operation is presented as
  undo; the existing Expert Council rollback surface remains the backend-owned
  recovery path where its measured snapshot contract exists.
- Exact per-worker role/ID evidence remains Expert/Mirror-owned; Guided worker
  presentation is intentionally identity-free and bounded.
- Context-loss fallback exists, including a keyboard-accessible product retry
  control. A measured canvas-loss event projects the product notice immediately,
  removes the invalid canvas before post-processing can continue against a lost
  target, and retries through a keyed product-owned remount; restoration
  re-reads the managed marker before clearing it. The product-owned boundary
  also covers a lazy renderer import or render failure before the managed
  fallback marker can mount. The forced browser capture now proves isolated
  containment/remount recovery, but field GPU recovery, browser/driver diversity,
  and an attributable production p75 context-recovery metric remain unmeasured.
- Local browser evidence requires a same-site host/API pairing: using
  `127.0.0.1:5173` with the default `localhost:8000` API can fail CORS or
  `SameSite=Strict` session-cookie checks in development. The verified rerun
  used `VITE_API_BASE=http://127.0.0.1:8000`; this is a local harness detail,
  not a changed production contract.
- The application now records honest foreground frame samples, but no field
  p75 metric or attributable before/after GPU comparison is claimed. The
  available browser evaluator does not expose the performance APIs needed for
  that evidence.

## Human validation still required

No human evidence is fabricated. The participant protocol is prepared in
`docs/frontend/GAGOS_2030_HUMAN_VALIDATION_PROTOCOL.md`; at least three
non-builders still need to run it: ask a normal question; request a bounded
change; deny and approve permission; identify verified versus unverified; stop;
recover/undo where the backend offers it; find an explanation; and optionally
enter Expert mode. Their hesitations, vocabulary confusion, misclicks, and
questions must be recorded before calling the renovation production-ready.

## Explicit V1 exclusions

No backend contract changes, security-core changes, WebGPU migration, new model
provider, authority weakening, generated/lab-source direct rewrite, or claim of
production readiness is included in this V1 worktree.

## Narrow Guided accessibility checkpoint — 2026-09-23

A fresh production preview on `127.0.0.1:5185` was inspected through the
available browser accessibility surface. The narrow portrait composition kept
the Guided request field, optional voice disclosure, all three starter paths,
Emergency Stop, and the truthful unavailable operational-picture message in
the accessibility tree. The real organism remained visible as the visual
anchor; no backend action was submitted.

The keyboard skip control focused `Talk to GAGOS`. Activating `Ask &
understand` changed the request field to its starter text and left the
conversation log empty, proving prefill rather than auto-submit in this
session. Opening Emergency Stop exposed the measured unavailable stop state
and unknown delivery; closing its details restored focus to the disclosure
trigger.

This is narrow browser accessibility-tree and focus evidence only. It does
not establish authenticated execution, screen-reader conformance, OS
reduced-motion emulation, field performance, or the complete required viewport
matrix. The local preview was stopped after capture.

## Resumed human-boundary and integrity gate checkpoint — 2026-09-23

After the review task was explicitly resumed, the focused Guided approval and
receipt suite passed 3 files / 16 tests in 24.79 seconds. This covers approval
focus containment, approval render measurement, replay-pause truth, refusal,
finished-but-unverified work, verified success, failure/rollback, and guarded
Undo presentation.

The constrained refresh also passed typecheck, production build (4,311
modules), lint (0 errors / 120 warnings), port-unit (5/5), CSS/texture canon,
frozen-core, JSONL, and whitespace checks. The authoritative `npm run
port:check` invocation from `frontend/` remains the known fail-closed ownership
diagnostic for the missing lab source `components/QualityTierProvider.tsx`;
the lab and generated Superbrain sources were not modified to bypass it.
