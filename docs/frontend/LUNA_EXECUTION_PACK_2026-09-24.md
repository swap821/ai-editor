# Luna execution pack: GAGOS living-being frontend

Status: proposed execution contract. Date: 2026-09-24.

Read [the blueprint](LIVING_BEING_BLUEPRINT_2026-09-24.md) first. Baseline when planned: `4782cfa356ad23015bf090f7a671b74967a373f8`. Check current master and the actual task branch before implementation; the baseline will change.

## Outcome and budget discipline

Deliver the official frontend as one coherent, responsive point-field being on desktop and mobile, with readable anatomical workspaces and truthful backend behavior. Preserve the animal/cage authority boundary, palette and protected textures.

Use GPT 5.6 Luna for bounded implementation, focused tests, ordinary extraction and documentation. Obtain stronger independent review at presentation-contract, shader/material, source-ownership, authority-adapter and release checkpoints when available. Model choice guarantees neither quality nor a fixed subscription cost. This pack limits repeated exploration and makes progress resumable; it does not promise a number of Plus sessions or an unattended finish date.

Start with one writer and one ticket. Parallel work is appropriate only when interfaces are stable and scopes do not overlap. Do not dispatch a swarm to rediscover this architecture.

## Reusable goal prompt

> Implement the GAGOS living-being frontend blueprint in `docs/frontend/LIVING_BEING_BLUEPRINT_2026-09-24.md`, using the ordered tickets in this execution pack. The official `frontend/` is the product; the external GAG demo is a visual reference and must not overwrite newer accepted product code. Desktop and mobile are equally important. Preserve existing backend authority, the current semantic kernel, palette, textures, source-port guards, accessibility and operational fallback.
>
> Work in an isolated Codex branch/worktree under repository coordination rules. First read the compact resume and ticket ledger, inspect the current branch and writer lease, and select the first dependency-ready ticket. Extend existing modules rather than creating parallel semantic systems. Complete a concrete bounded change, meaningful verification and a concise handoff before broadening scope. Keep fixtures, browser observations, live backend evidence, hardware measurements and human sign-off separate.
>
> Start with LB-01. Do not inflate line counts or test counts as evidence of success. Do not edit managed anatomy directly, weaken a guard, fake backend activity, silently remove an acceptance criterion, or redesign the application in one pass. Follow actual permissions for commits, pushes and merges; the operator chooses when to publish or merge. If a blocker affects only one ticket, document it and progress on an independent authorized ticket. Human-only visual/device/participant evidence must remain pending until supplied; never simulate it.

This is a proposed future goal. Preparing it does not start an automation, change this task's model, or authorize backend security changes.

## Ticket format and stopping rule

Record: user-visible outcome, dependencies, exact baseline, entry files, owned files, invariants, implementation, focused checks, browser/device check, evidence paths, remaining limitation and next ticket.

Prefer a coherent change reviewable in one sitting. Roughly 3–8 source files is a warning threshold, not a rule that forces bad abstractions. Split unrelated changes. Do not spend an entire usage window repeatedly rewriting a large component.

After two attempts with the same failure, record the reproducer and changed hypothesis. If the cause remains unclear after a third focused attempt, obtain review or mark that ticket blocked and choose independent work. This efficiency rule does not permit ignoring a failed required gate.

## Ordered backlog

All statuses below are **planned**. Existing code may satisfy part of a ticket after inspection; a similarly named file does not automatically complete it.

| Ticket | Depends on | Outcome / entry points | Required proof |
| --- | --- | --- | --- |
| LB-01 | — | Reproducible accepted managed source; sync tool and manifest | Restore, hash equality, port tests/check, rejection of drift and unsafe/conflicting destinations |
| LB-02 | — | Current import/evidence map and device/browser profiles | Canonical/dead/legacy consumers identified; exact baseline; real hardware selection |
| LB-03 | LB-01,02 | Whole-frame and interaction baseline; existing observability | Composer pass accounting, unavailable-data behavior, repeatable traces |
| LB-04 | LB-02 | Three-keyframe art direction and motion table at desktop/mobile sizes | Operator reference review; states distinguishable without motion/color alone |
| LB-05 | LB-01,02 | Core body and effects consume canonical semantic targets | DOM/body agreement under replay, stale and stop; truth/approval regressions |
| LB-06 | LB-05 | Attention arbitration and stable entity-to-seat identity | Rapid focus/reorder/removal preserves identity; keyboard/touch equivalent |
| LB-07 | LB-03,04,05 | Cortex/spine material and silhouette refinement | Before/after keyframes and motion; canon checks; hardware frame comparison |
| LB-08 | LB-04,05,06 | One grown surface becomes a stable readable DOM work plane | Identity/content/focus survive interruption, resize and reduced motion |
| LB-09 | LB-08 | Mobile focused composition with keyboard and safe areas | Physical iOS/Android, 320px reflow, enlarged text, no clipped input/decisions |
| LB-10 | LB-08 | Permission/denial/Stop choreography using existing controls | Request identity preserved; immediate DOM truth; gestures do not grant authority |
| LB-11 | LB-08,10 | Verification, receipts, safe dismissal/reopening | Verified/unverified distinct; no inherited pass or lost unsaved work |
| LB-12 | LB-07,08,09,10,11 | Complete first vertical slice, fixture and supported live journey | Operator moving-visual acceptance; correlated browser evidence; mobile/fallback |
| LB-13 | LB-12 | Multiple-workspace focus, overview and history | Concurrent streams do not steal focus; aggregation truthful; mobile reachability |
| LB-14 | LB-06,12 | Bounded pooled workers with stable identity | 1/8/overflow workers; replay/held/terminal churn; pool settles; live evidence separate |
| LB-15 | LB-12 | Memory/recall/reflex from admitted evidence | Unknown stays unknown; promotions measured; no invented model work for reflex |
| LB-16 | LB-03,07,09 | Measured Auto/manual quality and startup loading | Named-device traces, hysteresis, no palette/meaning loss |
| LB-17 | LB-10,11,13,14,15,16 | Renderer/asset/connection recovery through the journey | Loss/reconnect preserve drafts and decisions; no duplicate task; freshness barrier intact |
| LB-18 | LB-09,12 | Real mobile gateway/session and honest voice capability | Supported HTTPS path, suspend/reconnect/logout, unavailable/denied mic, typing fallback |
| LB-19 | LB-13,14,15,16,17,18 | Hardware and accessibility qualification | Active 30-minute cycle, 100 workspace cycles, keyboard and human assistive technology |
| LB-20 | LB-19 | Pilot, independent review and release packet | Critical criteria pass; human evidence; operator approval; rollback/device statement |

Backend WorkerFoundry availability is an external dependency for LB-14's live acceptance, not fixture development. Backend/network-policy changes uncovered in LB-18 need their own scoped authorization. Frontend capability reporting must remain accurate meanwhile.

## LB-01: exact first implementation packet

**Problem:** clean checkouts contain `frontend/superbrain-source.json` and accepted product bytes, but omit ignored lab source. `port:check` fails at `components/QualityTierProvider.tsx`; `port:bootstrap` refuses an existing manifest. This repeatedly blocks managed core-body improvement.

**Proposed solution:** add a separate non-destructive restore-authoring-source operation to the existing sync tool. Validate the manifest and every managed product hash before writes; restore only missing authoring files from accepted product bytes; leave the manifest unchanged. Existing differing destinations cause a conflict report and no writes. Never seed from the older external demo.

1. Inspect the sync tool/tests in full; preserve port/check/bootstrap behavior.
2. Reuse managed-path validation; verify resolved targets and reject symlink/junction escapes in every destination path segment. Complete validation before writing anything.
3. Compare every managed product file with its declared hash. A mismatch fails the operation before any partial restore.
4. Leave identical existing destination bytes untouched; fail on differing bytes. Do not delete files or automatically archive the manifest.
5. Restore missing files only when the complete preflight passes; report restored/unchanged paths.
6. Make interrupted restoration safely resumable: an idempotent rerun fills missing files and preserves identical ones.
7. Add package script/docs and meaningful tests for missing lab, identical files, conflicts, hash mismatch, invalid manifest paths, destination escapes and rerun behavior.
8. Run port unit tests and restore/check in the isolated worktree. Generated product source must remain unchanged.

Entry files: `frontend/tools/sync-superbrain.mjs`, `frontend/tools/sync-superbrain.test.mjs`, `frontend/package.json`, source-workflow section of `docs/frontend/LIVING_MIRROR_RENOVATION.md`. Inspect nested instructions first. This ticket does not copy protected assets, rewrite rendering, weaken hashes or modify the original external demo checkout.

Exit: a clean checkout can reproduce accepted source and pass the guard, with exact commands/results recorded. A later portable tracked-authoring-source migration is a separate reviewed change.

## LB-02: audit and acceptance packet

Create a concise living ledger covering:

- Imports from `semanticKernel` through `physicalSnapshot` to effects, and older bodyPosture/phase consumers in `CortexEngine`.
- Runtime consumers of older #362 `beingPresentation`/story/receipt modules. No deletion from filenames alone; preserve behavior before consolidation.
- Exact live evidence scope: chat, approval, approved write, development verifier, missing experimental worker strategy, default container availability, prior fixture soaks and human gaps.
- Named device/browser profiles: integrated-GPU desktop, mainstream Android Chrome, iPhone Safari, and constrained/economy tier. Emulation supplements real devices.
- Supported phone/backend gateway, session and voice capabilities.
- Fixed acceptance IDs and weights before completion percentages.

Do not rerun full application suites for a documentation-only inventory. Cite existing results with exact commits/limitations. Unknown hardware is unmeasured, never passing by inference.

**Current audit:** [LIVING_BEING_ACCEPTANCE_LEDGER_2026-09-24.md](LIVING_BEING_ACCEPTANCE_LEDGER_2026-09-24.md) records the source/runtime map, historical evidence limits, target OS versions, phone gateway/session/voice constraints and frozen 100-point acceptance list. Exact Android and iPhone models are still TBD per the operator; therefore LB-02 is partial and not accepted. Do not substitute emulation for handset selection or physical proof.

## LB-03: measurement packet

Use existing `livingMirror/observability/frontendMetrics.ts` and the scene diagnostic caller. Confirm composer counter reset/sampling before changing instrumentation. Aggregate complete rendered frames where needed. Missing counters explicitly report unavailable, not zero-cost rendering.

Capture idle, typing, materialization, streaming, eight-worker fixtures, verification, failure, reabsorption, stale and stop. Label fixtures. Separate RAF intervals, renderer draws, CPU/GPU time and input latency. Preserve bounded content-free buffers; never persist private content or identities.

Obtain a repeatable desktop baseline and physical-phone baseline before increasing visual load. If a phone is unavailable, continue independent projection work with that gate open. Validate accounting using a countable scene/pass chain and focused tests.

**Implementation checkpoint (partial, 2026-09-24):** `SuperbrainReactiveEffects.jsx` now disables Three.js `renderer.info.autoReset` before the priority-1 `EffectComposer` runs, samples its accumulated draw calls at R3F priority 2 after the composer, then resets once for the next frame. The local bounded scene sample calls this counter `drawCalls` (not composer passes); draw-call, geometry and texture counters preserve `null` as `unavailable`. Unit coverage simulates multiple internal passes and verifies per-frame reset and restoration. Focused metrics: 12/12 tests; 3D effects regression set: 19/19; full frontend: 175 files / 955 tests passed; typecheck and production build passed (4,316 modules transformed). Lint exited 0 with two hook-dependency warnings in unchanged memo blocks.

This does **not** close LB-03. The later `E-LOCAL-RENDER-SMOKE` observation confirms only four populated idle snapshots in the Codex in-app browser; exact browser build/host/active GPU and the artifact's source hash were unavailable. There is still no named desktop baseline, CPU/GPU timing, input-latency distribution, active-scenario trace or physical-phone run. No acceptance points are earned by the implementation or smoke checkpoint.

## LB-08 conversation rail checkpoint (2026-09-28; partial)

The official shell now gives welcome copy, conversation history, and status/receipt context one bounded scroll owner (`.gagos-chat__context`) while the request composer remains a sibling. A measured 1280×800 desktop field grew from 101px to 355px by moving the four frequent voice/send actions to their own row. For short landscape, connection truth and its retry action stay within the same 480px left rail rather than spanning the organism; at 844×390 the message and retry button both fit the 70px status slot. The 1024×480 and 768×521 edge cases also keep the composer inside its chat bounds.

Evidence: live Chromium viewport emulation at 1280×800, 1024×480, 844×390, 768×521, 390×844 and 320×568 showed no page overflow; input widths were 355px at desktop, 245px in compact landscape, and 298px/228px on mobile. Fresh full frontend **183 files / 1,038 tests**, typecheck, production build (**4,321 modules**), changed-JS ESLint (**0 errors / 8 existing warnings**), `test:port` (**16/16**), palette/protected-texture guards and `git diff --check` passed. The local preview stayed offline/resting; Expert/active-work and physical-device behavior were not accepted. This advances implementation only: **0 acceptance points**, total accepted evidence remains **3/100**.

### Narrow active reflow follow-up (2026-09-28; LB-08 partial / LB-09 emulation only)

At 320×568, Expert active mode had two reproducible UI defects: its workspace picker overlapped the wrapping navigation, and the panel began below its measured dock boundary and collapsed. A ≤360px composition now places the nav and picker side by side, moves the scrollable panel into the available band, and places its Expert-surface/workspace menus in viewport-bounded overlays. Local/offline CUA inspection opened both menus and scrolled the Recent observations body; the being remained truthfully resting and no backend request or send occurred. Full frontend **183 files / 1,039 tests**; typecheck; production build (**4,321 modules**); changed-JS lint **0 errors / 8 existing warnings**; `test:port` **16/16**; palette/protected-texture guards; `git diff --check` passed. The ≤360px-specific rule does not affect the previously checked 390px and desktop/landscape breakpoints, which were not remeasured here. This remains an emulated compact scroll shelf, not a phone-sized full work surface: physical Android/iOS and keyboard, accessibility and operator reviews are open; **0 new points**, accepted evidence **3/100**.

## Review and verification cadence

After LB-05 independently review semantic precedence, replay, task identity and stale/stop/permission behavior. After LB-12 the operator reviews the moving journey, and an independent reviewer inspects authority/fallback. After LB-16 review actual device traces and material/tier equivalence. Before release use the repository's non-builder hash-pinned handoff.

Provide reviewers the ticket, bounded diff, invariants, evidence and limitations; do not repeatedly send the entire codebase/history. A stronger model must not rubber-stamp “100%” from unit tests.

Run focused meaningful checks after a behavioral change, then required full gates at stable code checkpoints. Do not repeat an unchanged full suite just to add another evidence row. Observe actual browser behavior after user-visible changes. Preserve failed measurements and explain why they cannot support a claim.

## UX-04 implementation slice: keyboard-aware composer (2026-09-24)

On `codex/gagos-living-being-keyboard-safe`, commit `8b71d7c7358587c4e7e17f28a30eb3981b47d397` (base `975b9fb9`), the official app now adjusts its mobile conversation composer to the visual viewport only while a text-entry control inside that composer is focused. It clears the adjustment on blur/unmount and does not respond to button focus or pinch zoom. The occlusion calculation uses the app's measured bottom edge, covering the existing 520px minimum-height case; short visible heights contract the reserved gap and bound the connection notice's scroll area. No palette, texture, body motion or backend authority changed.

Verification: focused app tests **7/7**; serial frontend suite **175 files / 962 tests passed**; TypeScript passed; production build passed (**4,317 modules**); `test:port` **14/14**; full lint **0 errors / 123 warnings**; changed-file lint and `git diff --check` passed. `port:check` stops before comparing the product mirror because this isolated worktree lacks the ignored authoring-lab file `components/QualityTierProvider.tsx`; no port-check pass is claimed. No physical browser/device evidence was produced. UX-04 remains **0/5** and total accepted evidence remains **3/100** until named Android 17 and iOS 27 devices pass 320px, safe-area, keyboard, decision, touch and related checks.

## Starter acceptance ledger

This seven-row table is the original seed only. For progress scoring it is superseded by the frozen, weighted [LB-02 acceptance ledger](LIVING_BEING_ACCEPTANCE_LEDGER_2026-09-24.md); do not report completion against this smaller list.

| ID | Criterion | Required proof | Status |
| --- | --- | --- | --- |
| SRC-01 | Restore accepted source without overwrite | Guard tests + clean-checkout run | planned |
| BODY-01 | Actual body and DOM agree | Event replay + browser recording | planned |
| UX-01 | Work/focus survive materialization/retraction | Integration + desktop/mobile observation | planned |
| SAFE-01 | Permission/Stop retain authority and truthful outcomes | Contracts + supported live journey | planned |
| MOB-01 | Phone uses supported backend securely | Physical-device end-to-end | planned |
| PERF-01 | Selected tiers meet declared targets | Named-hardware traces | planned |
| HUMAN-01 | Users understand task, permission and outcome | Consented observations | planned |

Add commit/tree, artifact and limitation columns during implementation. Expand the criterion list before scoring: this starter is not the complete denominator. Credit existing evidence only where it actually satisfies the requirement.

## Compact session handoff

Keep `.aios/state/RESUME.md` near one screen; details belong in the ticket/evidence ledger. Preserve dated evidence as history.

```text
Goal: [one sentence]
Branch / worktree / baseline: [exact values]
Current ticket: [ID and bounded outcome]
Last verified change: [what + evidence]
Files changed: [short list]
Known failures / human dependencies: [specific]
Next single action: [executable step]
Authority already granted: [scope and publication permission]
Do not repeat: [completed checks; failed hypothesis]
```

At low context/usage, finish a safe checkpoint and leave this handoff. Resume through the product/operator's supported mechanism; never claim the model can wake itself or guarantee available quota.

Each delivery reports the visible change, actual verification, accepted percentage if a fixed denominator exists, and next gate. A proposed design, implemented code, fixture demonstration and production proof are different achievements.

## LB-06 renewed-materialization checkpoint (2026-09-24)

If fresh content for the same filepath or a renewed approval request arrives during retraction, reuse the stable surface identity and seat but restart its lifecycle at `reaching` with a fresh phase timestamp. The lab owns `tabStore.ts` and its regressions; `npm run port` updates the managed product mirror and manifest. Regression proof: both cases failed before the change and pass after it. Focused store/orchestration/conductor: **5 files / 36 tests**; full frontend: **176 files / 968 tests**; typecheck, build (**4,316 modules**), port safety (**15/15**), `port:check` (**193 / no drift**) and current palette/texture guards pass. ESLint reports zero errors and one existing unused-variable warning. Commit: `f0d97ca7` on `codex/gagos-living-being-lb06-revival`.

This advances implementation only. It does not prove live browser choreography, touch/keyboard parity, human comprehension, operator visuals or device performance; no acceptance points are added and the accepted score remains **3/100**. Android/iPhone models and desktop hardware remain unselected. Next: hash-pin this clean branch for independent review; keep the earlier focus branch's review snapshot untouched.

## LB-06 focused-workspace fallback checkpoint (2026-09-24)

The managed lab's `getFocusedMaterializedTab()` previously returned the first tab whenever `snapshot.focusId` did not name a materialized tab. Since intake is deliberately inserted first, the helper could report transient input as a focused workspace; with a DOM workspace selected, it could report background scene work as focused. It now returns no materialized focus while an open DOM panel owns attention and otherwise resolves through the existing conductor, which excludes intake/retracting tabs and supplies the canonical seat-order fallback. The lab remains the source of truth and `npm run port` updates the product mirror.

Three focused assertions failed before the fix and pass afterward. Store/attention, living-orchestration and anatomical-conductor group: **4 files / 40 tests**; combined full frontend (including keyboard-safe composer slice `8b71d7c7`): **176 files / 973 tests**; TypeScript and production build (**4,317 modules**) passed; port safety **15/15**, `port:check` **193 / no drift**, palette and protected-texture guards passed. Full lint: **0 errors / 123 existing warnings**; changed-file lint clean; `git diff --check` passed with Git's expected LF/CRLF notices. Vite configLoader and Three.js CommonJS deprecation warnings and Vitest's jsdom setup summary were non-failing.

This is source/automated evidence only. No browser journey, actual mobile keyboard/touch run, device trace, human assistive-technology pass, operator visual sign-off or desktop GPU baseline was collected. Android 17 and iOS 27 are OS targets; exact handset models remain **TBD**. UX-04 remains **0/5**; this checkpoint adds **0 acceptance points**, leaving accepted completion at **3/100**. LB-06 remains partial and the combined branch requires independent review.

## LB-09 mobile focused-work follow-up — implementation only (2026-09-28)

The active phone layout now keeps the selected workspace full-width and scrollable while retaining the composer and recovery action. From 361–767px, navigation and workspace selection have separate halves of one row; the work sheet begins below a short presence band. At ≤360px the existing paired row and compact sheet remain. The conversation is raised above the selected sheet so its input/accessories cannot disappear behind the work surface. On compact layouts, human-readable connection state and retry remain visible; longer explanation and Expert transport/cursor evidence are available through a native disclosure. When open, the disclosure moves above the measured composer; keyboard controls remain reachable. The work-sheet membrane uses only the existing surface token at partial opacity and adds no blur, new palette color, anatomy or texture.

Local offline preview screenshots: 320×568 and 390×844. The workspace body, composer and retry were visible; expanded diagnostics did not cover the composer. No chat send or retry was invoked. These captures are viewport emulation, not named phone/browser evidence. The 320px point-field silhouette is still mostly obscured, and the panel is short; do not call it the target living-being mobile experience.

Fresh verification: **183 frontend files / 1,042 tests**, typecheck, production build (**4,321 modules**), changed-file ESLint, `test:port` (**16/16**), CSS canon (**12 files / 9 tokens**), protected-texture guard and `git diff --check`. No physical device/software-keyboard, assistive-technology/user study, field performance, authenticated journey or operator review. Phone models remain TBD. **0 acceptance points; score remains 3/100.** Continue by improving mobile being-presence while retaining readable work content and reachable controls.

### LB-09 ≤360px work-plane disclosure follow-up (2026-09-28; implementation proof)

The 320px active Expert surface now has a collapsed-by-default header that preserves more of the organism canvas. Its content remains mounted while hidden, opens on demand, and returns focus to the disclosure on collapse; Pin/Close remain available. At 361px+, the panel remains expanded with no extra control. This is an incremental composition fix, not a claim that the silhouette, body/work nerve, or alive presence is complete.

The focused shell group passed 13/13; the full frontend passed 184 files / 1,044 tests, TypeScript and production build (4,321 modules), `test:port` 16/16, and palette/protected-texture guards. Changed-file lint exited 0 with eight warnings in the carried `GagosChrome.jsx`; the branch-local browser review is still pending. `port:check` cannot verify the external lab because `components/QualityTierProvider.tsx` is missing from this isolated checkout. No phone, keyboard-open, accessibility/human, live journey, performance or operator acceptance. 0 new evidence points; the score remains 3/100.

### LB-09 mobile Expert menu handoff correction (2026-09-28; emulated)

Browser inspection found the nested Expert surface/category disclosure remained open after workspace selection, covering the compact panel and part of the composer. Selecting a surface now closes both native menu layers; regression coverage verifies closure and focus handoff. On current branch, 320×568 closed/expanded views keep the composer, accessories and offline Retry reachable; live focus returns to the disclosure on collapse. At 390×844 no compact toggle is present and the page width equals 390px. Browser errors: none. The client stayed offline; no message or Retry action was used.

Fresh gates after this correction: frontend **185 files / 1,045 tests**, TypeScript, build (**4,321 modules**), focused changed-file ESLint, `test:port` **16/16**, palette and protected-texture guards, diff check. The 3D field remains only partially visible and the view is still viewport emulation; no physical handset/keyboard, human accessibility, performance, live service or operator acceptance. `port:check` still cannot resolve the absent external `components/QualityTierProvider.tsx`. No new evidence points; accepted score remains 3/100.
