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

## LB-03: measurement packet

Use existing `livingMirror/observability/frontendMetrics.ts` and the scene diagnostic caller. Confirm composer counter reset/sampling before changing instrumentation. Aggregate complete rendered frames where needed. Missing counters explicitly report unavailable, not zero-cost rendering.

Capture idle, typing, materialization, streaming, eight-worker fixtures, verification, failure, reabsorption, stale and stop. Label fixtures. Separate RAF intervals, renderer draws, CPU/GPU time and input latency. Preserve bounded content-free buffers; never persist private content or identities.

Obtain a repeatable desktop baseline and physical-phone baseline before increasing visual load. If a phone is unavailable, continue independent projection work with that gate open. Validate accounting using a countable scene/pass chain and focused tests.

## Review and verification cadence

After LB-05 independently review semantic precedence, replay, task identity and stale/stop/permission behavior. After LB-12 the operator reviews the moving journey, and an independent reviewer inspects authority/fallback. After LB-16 review actual device traces and material/tier equivalence. Before release use the repository's non-builder hash-pinned handoff.

Provide reviewers the ticket, bounded diff, invariants, evidence and limitations; do not repeatedly send the entire codebase/history. A stronger model must not rubber-stamp “100%” from unit tests.

Run focused meaningful checks after a behavioral change, then required full gates at stable code checkpoints. Do not repeat an unchanged full suite just to add another evidence row. Observe actual browser behavior after user-visible changes. Preserve failed measurements and explain why they cannot support a claim.

## Starter acceptance ledger

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
