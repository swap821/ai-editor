# GAGOS living-being acceptance and evidence ledger

Date: 2026-09-24. Status: LB-02 audit substantially recorded; physical-device selection remains open.

## Scope and pinned baseline

- Product: official `frontend/`; `GAG demo/` is the visual reference/authoring lab, not a source of truth to overwrite accepted product code.
- Baseline: `origin/master` `4782cfa356ad23015bf090f7a671b74967a373f8` (includes merged #362/#363/#364). Current implementation branch before this ledger: `codex/gagos-living-being-v2`, `c3181fd3`.
- The `docs/frontend/evidence/gagos-physical-*` reports were already present in the baseline via #364 (`c52f621f`); they are historical evidence reviewed for this ledger, not rerun here.
- LB-01 source restore is committed at `c3181fd3`. Its accepted product mirror and manifest remain unchanged. This ledger is documentation-only; no application suite is rerun.
- User-selected OS targets: latest stable Android and iOS. I interpret “latest” as stable-channel releases, not beta; as of this ledger date, official developer pages identify Android 17 as Android's latest release and iOS 27.0 as Apple's release. Exact Android/iPhone models are **TBD** (user-confirmed); physical availability is unconfirmed. An emulator or responsive viewport is supplemental, never a device pass.

## Source and runtime map

| Path | Observed role | Acceptance implication |
| --- | --- | --- |
| `frontend/src/superbrain/SuperbrainApp.jsx:5-8,32,160,165` | Root app calls `useBeingPresentation`; mounts `SuperbrainReactiveEffects` inside `WorkspaceCanvas` and mounts `LivingWorkspaceShell`. | The official root has a live DOM/3D route; this alone does not establish matching body posture for every event. |
| `frontend/src/livingMirror/being/semanticKernel.ts:120,271` | Current `BeingPresentation` contract and `deriveBeingPresentation(BeingFacts)`. | Use this as the semantic authority for presentation; do not add a second derivation system. |
| `frontend/src/livingMirror/being/presentationFromStores.ts:9-15,179-187` | Maps admitted mirror/tab/conversation stores into facts, derives the current semantic presentation and status text. | Store-to-presentation mapping is the source boundary to replay and test. |
| `frontend/src/livingMirror/being/useBeingPresentation.ts:9,13,26` | Hook subscribes to the current stores/phase and returns `beingPresentationFromStores(...)`. | Shared hook is consumed by DOM and reactive-effects paths. |
| `frontend/src/livingMirror/being/physicalSnapshot.ts:3-15,212,229` | Projects `BeingPresentation` into bounded physical targets (including worker visual slots); uses semantic transition mapping. | Worker slots are visual projection, not proof of live workers or stable backend worker identity. |
| `frontend/src/livingMirror/being/semanticEffects.ts:5,68` | Converts semantic changes to bounded effect transitions/worker visual states. | Effects are presentation only; they grant no backend authority. |
| `frontend/src/workbench/SuperbrainReactiveEffects.jsx:40-45,208-214,304,417` | Mounted canvas consumer of `useBeingPresentation`, `derivePhysicalSnapshot` and semantic transitions. A development/test override does not mutate stores. | This is the current semantic-to-3D effects seam. Prove state parity from the same event replay, not from fixture appearance alone. |
| `frontend/src/superbrain/core/CortexEngine.tsx:27-29,381,430-441` | Separately reads `getOrganismPhase()` and `getEffectiveOrganismPhase()`; the latter feeds `deriveBodyPosture` and posture tint/flow. | A second, older phase/posture input still influences the core body. Resolve or explicitly quarantine this split before claiming full DOM/body convergence. |
| `frontend/src/superbrain/components/canvas/BrainPointField.tsx:12,242`; `MaterializationLayer.tsx:22,402` | Additional phase/posture consumers; materialization derives posture from organism phase. | Include in the convergence audit; no broad deletion based on names. |
| `frontend/src/workbench/GagosChrome.jsx:63-65,307,623,840`; `frontend/src/livingMirror/LivingWorkspaceShell.tsx:13,83` | Active DOM consumes the new presentation/status, `deriveReceipt`/`ReceiptCard`, and `presentHistoryEvent`. | Receipts/history are production behavior to preserve through any consolidation. |

### Older #362 modules: runtime status, not a deletion list

Import search over production source (excluding tests) at `c3181fd3` found:

- `livingMirror/being/beingPresentation.ts`: no production runtime caller observed; remaining references are tests or type-only imports. The similarly named `semanticKernel.ts` is the current runtime derivation path.
- `beingScenePresentation.ts`: no live-root runtime import observed; its import of `beingPresentation.ts` is type-only and its runtime use is in tests.
- `BeingStatus.tsx`, `experience/GuidedTaskStory.tsx`, and `experience/OutcomeReceipt.tsx`: no import from the live root/runtime graph observed. `experience/copy.ts` and `humanTaskStory.ts` are used internally by these unmounted components; their internal imports do not make them active product behavior. Components and tests remain in source; this audit does not remove them.
- `experience/receipts.ts` and `experience/ReceiptCard.tsx`: active production path from `GagosChrome.jsx`; preserve and behavior-test before refactoring.
- `experience/historyPresentation.ts`: active path from the mounted `LivingWorkspaceShell`.

This is a point-in-time source import audit, not proof that modules are safe to delete. Search again and establish behavior parity in the change that proposes consolidation.

## Existing evidence and exact limits

Each evidence record below identifies its artifact, scenario, environment/proof type, result and limitation. Historical reports pin their document to the merged baseline (`c52f621f`) but do not consistently record the tested source-tree SHA or full browser build; the artifact commit is not silently treated as the run's code commit. Missing environment/source identity remains unknown.

| Evidence ID | Artifact | Scenario and environment / proof type | Result and limitation |
| --- | --- | --- | --- |
| `E-CHAT` | [live backend journey](evidence/gagos-physical-live-backend-journey.md) | 2026-09-24 disposable backend; authenticated API/SSE stream; no UI browser/device. | Cookie-backed session and chat terminal boundary observed. Not a browser-correlated UI, worker, hardware or human journey. |
| `E-HOLD` | [approval hold](evidence/gagos-physical-live-approval-cycle.md) | Authenticated `/api/generate` against disposable backend; API-level observation. | Server capability reached `human_required`; target stayed absent. No deny/UI correlation. |
| `E-EXEC` | [approved execution](evidence/gagos-physical-live-approved-execution.md) | Replayed capability against disposable backend; API/audit inspection. | Exact file created and YELLOW CREATE audited; `.txt` target emitted no verification event. |
| `E-VERIFY` | [verification boundary](evidence/gagos-physical-live-verification.md) | Disposable backend, default container then explicitly dev-only pytest runner; API and durable-event inspection. | Default Docker path failed closed; dev runner produced verified pass. Does not certify the default production container. |
| `E-WORKER` | [worker boundary](evidence/gagos-physical-live-worker-boundary.md) | Authenticated `swarm=true` API request, disposable backend; no phone/browser UI. | `strategy_unavailable` before WorkerFoundry; no worker lifecycle. |
| `E-GALLERY` | [gallery matrix](evidence/gagos-physical-gallery-matrix.md), [active runtime cycle](evidence/gagos-physical-active-runtime-cycle.md) | Dev-only `?physical-gallery=1`, 1280×720, browser build/model not captured; fixture/DOM/resource observation. | 21 fixtures and short cycle observed. No live backend parity or materialized workspace. |
| `E-IDLE` | [persistent soak](evidence/gagos-physical-persistent-soak.md) | Branch `codex/frontend-physical-embodiment`; Codex in-app browser, 481×778, 150 samples over ~36 minutes idle; device/GPU/browser build not identified. | Counts bounded; reported frame-time p95 16.8–17.1ms. Not 60-FPS certification, GPU-memory evidence, live worker/materialization, human acceptance or device test. |
| `E-ACTIVE` | [active worker-fixture soak](evidence/gagos-physical-active-worker-soak.md) | Dev gallery, visible browser, 1280×720, High/full motion, 150 samples over ~30.28 minutes; browser build/device not captured. | Stable 8 branches/4 motes. Fixture only; no live WorkerFoundry/materialization, hardware p95 or GPU-memory evidence. The separate 18.6-minute run is partial. |
| `E-A11Y` | [accessibility inspection](evidence/gagos-physical-accessibility.md) | Local Vite preview and dev gallery, 1280×720; DOM/accessibility-tree and selected keyboard/page interactions; exact browser build not captured. | Root and gallery semantics/live region observed. Not a human screen-reader, touch, mobile, operator visual or participant test; ReadPixels-stall and `THREE.Clock` warnings were reported. |
| `E-HUMAN` | [human validation packet](evidence/gagos-physical-human-validation-packet.md) | Protocol/document review only; no participant session. | Packet is prepared; zero participant, human screen-reader or operator sign-offs. |

The planning record also reports a 390×844 CSS viewport observation (390px document width, 44px request input, canvas ~390.4×354.2). It explicitly is not detailed mobile acceptance; there was no physical phone, mobile keyboard/touch, thermal, screen-reader or field-performance run. These records come from `LIVING_BEING_RESEARCH_NOTES_2026-09-24.md`, not a new test in LB-02.

## Device and browser profiles

| Profile | Target hardware/browser | Current selection/evidence |
| --- | --- | --- |
| `DESKTOP-IGPU` | Actual desktop-class system with integrated GPU; Chrome stable and Edge stable. | Model/CPU/RAM **TBD**; no desktop-class hardware selected or accepted run. |
| `LAB-LAPTOP-G15-IGPU` | Dell G15 5515 laptop, Ryzen 5 5600H, 16 GiB class, integrated AMD Radeon, Windows build 26200; Chrome and Edge. | Machine inventory confirmed locally. Installed browser builds on 2026-09-24: Chrome `153.0.8010.53`, Edge `153.0.4234.48`. Force/verify active WebGL adapter during a run; WMI's reported 512 MiB integrated adapter memory is not a VRAM measurement. This laptop is lab coverage, not the desktop-class profile; no accepted performance run yet. |
| `LAB-LAPTOP-G15-RTX3050` | Same laptop using NVIDIA GeForce RTX 3050 Laptop GPU; Chrome and Edge. | GPU and driver enumerated locally. This is a second mode of one laptop, not a separate desktop-class sample. No accepted performance run yet. |
| `ANDROID-MAINSTREAM` | Physical Android 17 stable handset + Chrome stable. | Model/chipset/RAM/browser build **TBD**; user has not selected a handset. Physical availability and run are unconfirmed. |
| `IOS-SAFARI` | Physical iPhone on iOS 27.0 stable + Safari. | Model/browser build **TBD**; user has not selected a handset. Physical availability and run are unconfirmed. |
| `MOBILE-ECONOMY` | Named constrained/economy physical phone and its stock browser, with an explicitly selected quality tier. | Device **TBD**. A desktop integrated GPU or emulator cannot substitute for a physical low-tier phone. |

Stable OS target references: [Android Developers — current Android platform](https://developer.android.com/about) and [Apple Developer — iOS 27.0 release](https://developer.apple.com/news/releases/?id=09142026a). Record exact model, OS build, browser build, viewport, active GPU/tier and power/thermal context when a physical run is scheduled. Responsive emulation is useful for early layout coverage only.

## Phone gateway, session and voice boundary

- `frontend/src/config.js` uses an empty relative API base in production (intended same-origin gateway) and defaults development to `http://localhost:8000`, unless `VITE_API_BASE` overrides it. The Vite config has no API `server.proxy` entry. On a phone, `localhost` is the phone itself; a desktop-served development UI therefore needs a deliberately reachable/configured backend, correct CORS/cookie policy and preferably a supported HTTPS same-origin gateway. None of those phone paths has been validated on a physical device.
- `frontend/src/superbrain/lib/sessionId.ts` first checks/creates the backend-managed httpOnly cookie session and uses `credentials: 'include'`. If cookie sessions are unavailable/blocked it falls back to `sessionStorage` and emits an explicit XSS-risk warning. `aiosAdapter.ts` also sends credentialed requests; the frontend does not embed an API bearer token. Mobile suspend/resume, cookie retention, logout and reconnect still require device verification.
- `frontend/src/workbench/hooks/useVoiceInput.js` checks backend voice capability, can use explicitly allowed browser speech recognition, or captures audio with `getUserMedia` + `MediaRecorder` and posts it for backend transcription. Typed input is the fallback. `workbench/voiceSpeak.ts` uses browser `speechSynthesis`; the adapter also exposes backend TTS. This is code capability, not proof that voice works on selected mobile browsers.
- Vite dev/preview response headers set `Permissions-Policy: ... microphone=() ...`; microphone capture is denied on those served surfaces. The production gateway's headers and voice behavior have not been audited. Do not advertise mobile voice as supported until the deployed gateway policy and physical-browser permission/denial/fallback paths are verified.

## Frozen acceptance denominator (100 points)

Freeze these IDs and weights before publishing progress. Each criterion is all-or-nothing for acceptance: partial tests, fixtures, backend-only probes, viewport emulation and implementation do not earn its weight. Report the strongest evidence stage separately from earned points. `Blocked` stays in the denominator. Critical truth/approval/Stop/mobile/fallback gates remain release blockers regardless of the average.

| ID | Criterion (weight) | Required acceptance proof | Current strongest evidence / status / credit |
| --- | --- | --- | --- |
| INT-01 | Accepted source reproducibility (3) | Clean-checkout restore, full manifest/hash validation, port test/check; accepted product bytes unchanged. | `c3181fd3`: restore 193 files, port check 193/no changes, `test:port` 14/14, product/manifest unchanged. `automated-verified`; **3**. |
| INT-02 | Authenticated chat + turn boundary (3) | Supported browser journey correlated with authenticated backend event IDs from request through terminal event. | `E-CHAT`; API stream only, browser correlation absent. `automated-verified` partial; **0**. |
| INT-03 | Freshness, replay and event ordering (3) | Duplicate/out-of-order/reconnect replay on supported route yields one truthful current projection in DOM and body. | Existing unit/fixture coverage; no pinned browser artifact or correlated replay. `automated-verified` partial; **0**. |
| INT-04 | Approval, denial and Stop authority (4) | Browser-correlated live allow/deny/Stop; server authority remains decisive; no gesture/animation grants approval; held target is not written. | `E-HOLD` + `E-EXEC`; API only, no deny/UI/Stop correlation. `automated-verified` partial; **0**. |
| INT-05 | Completion vs verification receipts (3) | Supported journey proves terminal completion, verified pass, unverified completion and failure are never conflated; production-selected verifier works. | `E-VERIFY`; default Docker failed closed, dev pass is non-production. `blocked`; **0**. |
| INT-06 | Failure, stale and recovery truth (2) | Live/browser error, stale, refusal, retry and recovery preserve the draft and do not fabricate success. | `E-GALLERY` plus unit fixtures; no live recovery journey. `browser-observed` partial; **0**. |
| INT-07 | Capability and worker honesty (2) | UI accurately represents supported live capability; admitted worker identity/lifecycle correlates end-to-end or remains explicitly unavailable. | `E-WORKER` + `E-GALLERY`; backend refuses strategy, fixtures are projections. `blocked`; **0**. |
| BODY-01 | DOM/body semantic agreement (5) | Same admitted event replay produces matching named semantic state in DOM and 3D across stale/approval/Stop/terminal states. | `E-GALLERY`; shared hook/tests and fixture states, no correlated parity recording. `automated-verified` partial; **0**. |
| BODY-02 | Continuous body/spine/workspace anatomy (5) | Operator-reviewed moving journey shows continuous attention→spine→nerve→readable work surface and stable return path. | `E-GALLERY`; no live materialization (0 surfaces). `browser-observed` fixture-only; **0**. |
| BODY-03 | Critical states legible without color/motion (5) | Human observers correctly distinguish permission, stale, refusal, stopped, verified/unverified and failure using labels/shape/pattern with motion/color disabled. | `E-GALLERY` + `E-A11Y`; fixture/DOM only, no human/operator acceptance. `browser-observed` partial; **0**. |
| BODY-04 | Authored motion and reduced-motion parity (4) | Reviewed keyframes/video plus reduced-motion and interruption run; controls, state and meaning remain immediate and equivalent. | `E-GALLERY` + `E-A11Y`; no operator motion acceptance. `automated-verified` partial; **0**. |
| BODY-05 | Palette/texture canon and visual acceptance (6) | Operator explicitly approves palette, protected texture/GLB, silhouette, hierarchy and 30–60s moving journey. | `E-HUMAN`; packet prepared, sign-off absent. `not-started`; **0**. |
| UX-01 | Ask-to-result single-task journey (4) | One correlated supported run from rest/input through real work, decision, honest receipt and reabsorption. | `E-CHAT` + `E-HOLD` + `E-EXEC` + `E-VERIFY`; backend slices separate, no browser journey. `automated-verified` partial; **0**. |
| UX-02 | Workspace identity/content/focus continuity (5) | Surface content, task identity, scroll/edit state and focus survive growth, interruption, resize, dismissal and reopening. | `E-GALLERY`; no live materialized tabs and no continuity run. `not-started`; **0**. |
| UX-03 | Multi-task focus and history reachability (3) | Concurrent streams, focus switching and history remain truthful and operable without stealing focus. | Active history/receipt source only; no acceptance scenario artifact. `implemented`; **0**. |
| UX-04 | Physical mobile composition/input parity (5) | Named physical Android + iPhone: 320px reflow, safe areas, virtual keyboard, 44px preferred targets, no clipped composer/decision, touch parity. | Handset models TBD; 390px emulation is not phone acceptance. `blocked`; **0**. |
| UX-05 | Draft/interruption/reconnect recovery (3) | Draft and pending decision survive network/app/background/renderer interruption; resume never duplicates work. | No qualifying physical/browser end-to-end evidence. `not-started`; **0**. |
| A11Y-01 | Keyboard-only critical journey (4) | Keyboard-only ask, inspect, approve/deny, Stop, recover and receipt journey, with visible/restored focus. | `E-A11Y`; limited root DOM/focus observations, not full journey. `browser-observed` partial; **0**. |
| A11Y-02 | Human assistive technology (5) | Human NVDA/Windows, VoiceOver/iOS and TalkBack/selected Android passes on supported root route, with factual notes. | `E-HUMAN`; no human session. `not-started`; **0**. |
| A11Y-03 | Reflow, zoom, text and target-size (3) | Physical-device 320px and enlarged-text/zoom matrix; no clipped/overlapping controls; WCAG 2.2 AA plus 44px product preference checked. | `E-A11Y` + research note; one 390×844 CSS viewport only. `browser-observed` partial; **0**. |
| A11Y-04 | Reduced motion, voice and non-voice fallback (3) | Physical browser verifies ambient pause/reduced motion, voice permission denial/unavailable, typing fallback and optional TTS behavior. | `E-GALLERY` + `E-A11Y`; voice not tested on phone. `automated-verified` partial; **0**. |
| PERF-01 | Desktop frame and input budget (4) | Named desktop/GPU/browser, complete composer frame accounting, p50/p95 and input latency against budgets frozen before visual-load changes. | `E-IDLE`; in-app browser soak is not named hardware; GPU adapter/pass accounting not accepted. `not-started`; **0**. |
| PERF-02 | Mobile frame, battery and thermal (4) | Selected physical Android/iPhone sustained journey with frame/input distributions, battery/thermal context and fallback/tier behavior. | Models TBD; no physical measurements. `blocked`; **0**. |
| PERF-03 | Startup and scene readiness (2) | Named-device cold/warm launch, input-ready and first-stable-scene timing under defined network/cache conditions. | Build exists; no accepted named-device measurements. `not-started`; **0**. |
| PERF-04 | Resource bounds and endurance (2) | 100 workspace cycles plus 30-minute active supported journey on named devices; bounded canvas/DOM/GPU resources and no monotonic growth. | `E-ACTIVE` + `E-IDLE`; active fixture plus idle browser soak, no 100-cycle/device proof. `browser-observed` partial; **0**. |
| REC-01 | Renderer/backend recovery (3) | Inject WebGL/context loss and network loss during work; preserve draft/decision/receipt, restore once, and prove no duplicate backend task. | Fallback source/tests only; no full loss/reconnect artifact. `automated-verified` partial; **0**. |
| REL-01 | Pinned reproducible evidence packet (2) | Commit/tree, scenario, exact device/browser, artifacts, result and limitations recorded for every required criterion. | This ledger + evidence artifacts; run-tree SHA/browser builds are missing from several historical reports. `implemented` partial; **0**. |
| REL-02 | Independent comprehension round (2) | Three non-builders complete the safe protocol; misunderstandings recorded, repeated confusion fixed and retested. | `E-HUMAN`; protocol prepared, no participants. `not-started`; **0**. |
| REL-03 | Independent review, operator approval and rollback (1) | Non-builder reviews a hash-pinned handoff; operator signs release packet; tested rollback/device support statement exists. | No review/sign-off/release packet. `not-started`; **0**. |
| **Total** | **Frozen denominator** | **All listed criteria remain in scope; no weight is silently removed.** | **100 points** |

Accepted completion at this ledger revision is **3/100 = 3%** (INT-01 only). This is an evidence-weighted acceptance score, not percent of lines, tests, blueprint pages or perceived visual quality. Partial evidence earns zero until its entire criterion threshold is met. Implementation work and acceptance evidence are tracked separately; no second “implemented percent” is asserted from code volume.

## LB-02 disposition and next gate

The import/runtime audit, existing-evidence scope, stable OS targets, desktop host inventory, gateway/session/voice limitations and fixed acceptance denominator are recorded. LB-02 is **partial, not closed**, because no exact Android or iPhone model is selected and the execution pack requires real hardware selection. Do not substitute an emulator or infer physical access. Next: operator identifies available phone model(s) (including whether a constrained/economy handset is available); then pin model/SoC/RAM/browser/build and proceed to LB-03 instrumentation baseline with mobile proof still open until exercised.
