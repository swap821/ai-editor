# GAGOS Physical Embodiment Implementation

Status: in progress — Phase 2/3 physical projection slice 3 + gallery inspection surface

Branch: `codex/frontend-physical-embodiment`  
Baseline: `ba5d433a4f074cbfab1c83b1740c4dbcd72139ee` (`origin/master`, PR #363)  
Date: 2026-09-24

This report is an evidence log, not a production-readiness claim. The current
slice establishes the physical projection contract, adds point-field-compatible
cortex/conductor posture, memory/reflex cues, and materialization continuity,
and consumes them in the product-owned reactive seam. It does not yet replace
the existing visual effects with a complete pooled anatomical branch system.

## Architecture chosen

The implementation keeps the #363 semantic nervous system as the only source
of presentation truth:

```text
admitted mirror/store facts
  -> livingMirror/being/semanticKernel
  -> BeingPresentation
  -> physicalSnapshot.ts
  -> product-owned R3F reactive seam
  -> bounded Three.js effects
```

`frontend/src/livingMirror/being/physicalSnapshot.ts` is a pure projection
from `BeingPresentation`. It derives bounded physical inputs for:

- cortex posture, attention, activity and convergence;
- spinal-conductor posture, travel and selected seat;
- temporary worker-branch visual states and terminal evidence;
- memory/reflex layer and pulse direction;
- sovereign-membrane state and whether action-bearing travel is open;
- verification state and whether the result is physically settled;
- existing coherence opacity, motion scale and cadence.

`SuperbrainReactiveEffects.jsx` now consumes that projection for coherence,
stop presentation, worker lifecycle reconciliation, bounded three-point branch
geometry, static memory/reflex cues, materialized-surface continuity metadata,
the static sovereign membrane, a bounded verification field, and measured
council-dissent paths. The existing semantic transition helper
remains responsible for entered-signal pulses. No second semantic kernel, event
bus, authority path, backend contract, or generated Superbrain source was
added.

## Why this architecture

The projection is intentionally adjacent to the existing semantic kernel. It
keeps physical vocabulary separate from semantic vocabulary without inventing
new backend states. A pure function makes the mapping deterministic and
fixture-testable; the renderer can later consume the same snapshot at every
quality tier without teaching Three.js how authority works.

The first consumer is product-owned because the managed lab source is absent in
this worktree and `npm run port:check` correctly fails closed. The physical
slice therefore does not edit or copy generated anatomy to make the port gate
green.

## Cortex and spinal-conductor slice

The new product-owned projection reuses the canonical `tabStore`,
`livingOrchestrator`, and `anatomicalConductor` path. It does not create a
second workspace conductor. Occupied canonical vertebra seats are mapped
through the existing `SEGMENT_ANCHORS` and brain-dock scale, so the added path
and seat markers share the same point-field coordinate system as the managed
organism. The cortex posture field uses the physical snapshot's measured
posture, activity, convergence, and coherence rather than raw event names.

The conductor path is a bounded static projection: at most the canonical seat
count (12 points / 11 segment pairs) is mounted, with one seat marker per
occupied non-idle vertebra. Path and seat topology are not mutated from
`useFrame`; only the existing semantic pulse and worker-branch paths use the
bounded frame-loop mutations. High/medium/low tiers reduce marker geometry and
line width while retaining the same state meaning. Approval, refusal and a
worker awaiting capability tint the path as held, while stop removes
action-bearing travel and leaves the sovereign membrane/evidence boundary
visible. The worker-capability boundary is derived from the existing
`awaiting-capability` presentation state; it does not add authority or
execution logic.

The cortex now also exposes a bounded internal-current topology: three static
three-point paths at high tier, two at medium, and one at low. Their endpoints
contract toward the cortex as measured convergence rises, so planning and
verification read as coherent convergence rather than a loading spinner. The
paths are recomputed only when the physical snapshot or tier changes; they do
not allocate or mutate from the frame loop, and stopped posture removes them
while preserving the DOM truth surface.

Verification now has an explicit product-owned field: pending is an unsettled
amber ring, pass is a stable green ring, and fail is a smaller unsettled red
ring. The field is keyed by the existing `verification-pending`,
`verification-pass`, and `verification-fail` presentation signals; it is not
derived from convergence or animation completion. When the existing measured
`council-dissent` signal is present, the seam adds at most three quiet internal
paths, reduced to two/one by the quality tier. They have no labels or authority
semantics and disappear at stopped posture.

## Alternatives rejected

- A second event bus was rejected because the admitted `BeingPresentation`
  already provides the semantic boundary.
- A renderer-owned lifecycle state machine was rejected because it could turn
  easing or stale visual state into false execution truth.
- Direct edits to `frontend/src/superbrain/**` were rejected while the lab
  source is unavailable; those files remain port-managed.
- Replacing the existing worker motes immediately with a new branch geometry
  was deferred until a measured pool/material budget and representative state
  gallery exist.
- A WebGPU migration was rejected as outside V1 and unnecessary for this
  projection contract.

## Physical state map

| Existing semantic posture | Physical projection | Authority meaning |
| --- | --- | --- |
| `resting` / `booting` | calm cortex, idle conductor | none inferred |
| `listening` / `understanding` / `planning` | attention cortex | human input or preparation only |
| `acting` / `reflex` | conducting cortex and outbound conductor | admitted work presentation only |
| `awaiting-human` / `needs-permission` / `awaiting-capability` worker | held membrane and held action branches | human/capability boundary is still unresolved |
| `verifying` | verification cortex and outbound test path | result is unresolved |
| `recovering` / `reabsorb` | unsettled cortex and retracting conductor | recovery evidence remains visible |
| `stale` / `degraded` | weakened coherence physics | currentness is not promoted |
| `stopped` | frozen conductor and closed membrane | action visuals halt; evidence remains |

The projection never contains `approved`, `authorized`, `allowed`, or
`canExecute`. Verification is carried explicitly as `pending`, `pass`, `fail`
or `none`, with `stable` settlement only for an admitted pass; visual
convergence is not verification.

The `council-dissent` signal is rendered as bounded internal divergence only
when the semantic layer reports it; the renderer does not infer dissent from a
multi-point path or a single model response.

## Semantic-to-physical mapping

Worker presentation remains capped at eight entries. Requested, admitted,
active, capability-held, returned, dissolved, failed and killed map to bounded
bud/branch/conduct/held/returning/dissolved visuals. Approval and refusal close
action-bearing branch travel while preserving terminal evidence. Emergency Stop
maps to the existing stopped presentation and freezes the same physical path.

Memory is deliberately coarse until the backend exposes a stronger persistence
fact: `memory-recalled` is a temporary inward pulse, `memory-promoted` or
`curriculum-mastered` is a settling pulse, and `reflex-reused` is a fast
conduct pulse. No recalled item is rendered as a trusted permanent structure.

## Deterministic physical state gallery

`frontend/src/livingMirror/being/physicalStateGallery.ts` is explicitly a
development/test-only fixture and is not loaded by the production runtime. It
contains 21 deterministic presentation cases covering all 15 semantic phases,
the three existing `low`/`medium`/`high` quality tiers, every worker posture,
approval/refusal/stop membrane boundaries, and verification pending/pass/fail/
unverified completion.
`physicalStateGallery.test.ts` derives every case through the real physical
projection and checks the bounded branch cap, phase preservation, recalled /
promoted / reflex memory layers, and absence of authority-shaped fields. The
gallery is therefore a contract fixture, not a runtime demo mode or a second
source of state.

`PhysicalStateGalleryPage.tsx` is a Vite-development-only root inspection
surface at `/?physical-gallery=1`. It mounts the existing `CortexEngine` and
product-owned reactive seam with a narrow `presentationOverride` inspection
prop; production still renders the single live `SuperbrainApp` root. The
override is typed, deterministic and read-only: it cannot write stores,
backend facts or authority state.

The browser harness mounted the gallery at 1280×720 with all 21 fixture
buttons, one canvas, and the `resting` inspector. The inspected resting scene
is [gagos-physical-gallery-resting.png](evidence/gagos-physical-gallery-resting.png).
Selecting `verification-fail` updated the inspector to `recover / reabsorbing /
fail · unsettled` while retaining one canvas. A second chain enabled reduced
motion and selected the bounded `worker-burst` fixture: the inspector reported
`held · held` conductor travel, `8 bounded` branches, `membrane held`, one
canvas, and no semantic mutation. The high-tier
failure-state screenshot path timed out in the throttled browser and was not
accepted as visual evidence.
After a settled low-tier remount, the reduced-motion verification-fail state
was captured and inspected in [gagos-physical-gallery-verification-fail-low-reduced.png](evidence/gagos-physical-gallery-verification-fail-low-reduced.png): the
inspector showed `recover / reabsorbing`, one bounded branch and `fail ·
unsettled`. Its loaded diagnostic samples settled at 63 scene objects, 21
geometries, 21 textures, one render call and a transient pool of 3 with one
worker branch; this is a single-state bounded observation, not long-run proof.
The high-tier verification-pass fixture was then remounted in a fresh browser
chain and captured after the inspector settled: [gagos-physical-gallery-verification-pass-high.png](evidence/gagos-physical-gallery-verification-pass-high.png)
shows the living scene with `verification-pass · High`, `pass · stable`, and a
clear membrane. This is a settled gallery artifact, not live backend evidence.
An ordinary root check at `/` then mounted one canvas with zero gallery fixture
buttons and no gallery marker, confirming the inspection surface is not the
production default.

An authenticated disposable local backend journey is recorded in
[gagos-physical-live-backend-journey.md](evidence/gagos-physical-live-backend-journey.md).
It created a server-side session, enrolled and logged in a temporary operator,
measured the CSRF-bound authenticated session, streamed a real `/api/v1/chat`
turn through `turn.started → human_state → representative_context → route →
text_chunk… → done`, and read the resulting authenticated mirror snapshot.
This closes the basic backend-turn evidence gap, but it does not yet drive
every worker/approval/verification posture through the browser.

A second fresh disposable backend run is recorded in
[gagos-physical-live-approval-cycle.md](evidence/gagos-physical-live-approval-cycle.md).
After the same session/enrollment/login/reauthentication ceremony, an
authenticated `/api/generate` turn streamed a real `human_required` frame for
`create_file`, with a server-issued generation capability bound to the exact
`training_ground/physical-embodiment-live-approval.txt` target. The target did
not exist afterward because the capability was not replayed. This proves the
live YELLOW approval hold and its no-write boundary; it does not claim approved
execution or post-write verification.

A third fresh disposable backend run is recorded in
[gagos-physical-live-approved-execution.md](evidence/gagos-physical-live-approved-execution.md).
The exact capability was replayed through `/api/generate`; the target was
created, the stream emitted the create-file result and `done`, and the
temporary audit trail recorded the action in the YELLOW zone. Because the
target was intentionally a non-Python `.txt` file, the run emitted no
`verify_result` or `verification.completed` event. This closes the live
approval-replay/write evidence gap while keeping post-write verification open.

The live verification continuation is recorded in
[gagos-physical-live-verification.md](evidence/gagos-physical-live-verification.md).
With the normal container backend, the approved Python test reached a real
`verify_result=fail` and a durable `verification.completed` with
`passed=false` because Docker was unavailable. With the explicit development
host backend and the scope-compatible `pytest` runner, the same approval replay
reached `verify_result=pass`, `[VERIFY PASS] 1 passed, 0 failed
(strength=STRONG)`, durable `verification.completed` with `passed=true` and
`trust=verified`, and a terminal `done`. The development override proves the
complete verifier path without being presented as production-container
availability.

The live worker boundary is recorded in
[gagos-physical-live-worker-boundary.md](evidence/gagos-physical-live-worker-boundary.md).
An authenticated, non-mutating `/api/generate` request with `swarm=true`
returned `200 text/event-stream` but ended
`turn.started → alignment → step → plan → error(strategy_unavailable) → done`.
No `swarm_plan`, caste, worker, or materialization frame was emitted. The
backend's own gate directs the selector through WorkerFoundry before enabling;
the gallery's worker/materialization states therefore remain frontend
projection evidence, not a live cycle claim.

Fresh browser chains then exercised the representative matrix at its declared
fixture tiers. The resulting inspector values are recorded in
[gagos-physical-gallery-matrix.md](evidence/gagos-physical-gallery-matrix.md):
low/reduced listening, approval, verification-pending, memory recall, stale,
stopped, booting, and failed; high/reduced understanding, worker burst,
verification pass, degraded, and reflex; and medium/full-motion planning,
acting, unverified, learning, refusal, rollback/reabsorption, plus arriving.
Each chain loaded the gallery canvas first and read the inspector after the
fixture click; a daemon loss invalidated one attempted intermediate chain and
its output was not included.

### Visual acceptance matrix — current evidence strength

The fixture matrix exists for every requested posture, but a fixture or unit
assertion is not the same as a settled browser capture. The current evidence
is intentionally separated here:

| Requested posture | Deterministic fixture / projection | Current strongest evidence |
| --- | --- | --- |
| Rest | `resting` | inspected medium capture |
| Listening | `listening` | low/reduced browser inspector + pure projection |
| Understanding | `understanding` | high/reduced browser inspector + pure projection |
| Planning | `planning` | medium/full browser inspector + cortex-current tests |
| Approval hold | `approval-hold` | low/reduced browser inspector + live authenticated hold/replay evidence + membrane regression |
| Worker requested | `worker-burst` requested slot | high/reduced browser inspector + bounded lifecycle tests |
| Worker active / acting | `acting`, `worker-burst` | medium/full browser inspector + renderer lifecycle tests |
| Worker waiting | `worker-burst` awaiting-capability slot | high/reduced held membrane inspector + regression |
| Verifying | `verification-pending` | low/reduced browser inspector + verification renderer test |
| Verified | `verification-pass` | inspected high-tier settled capture + live durable development verification + pass/stable renderer test |
| Unverified | `unverified` | medium/full browser inspector + pure fixture regression |
| Refused | `refusal` | medium/full browser inspector + refusal membrane regression |
| Failed | `verification-fail` | high/reduced browser inspector + inspected low/reduced capture |
| Rolled back / reabsorbing | `rollback-recovering` | medium/full browser inspector + lifecycle tests |
| Learning | `learning` | medium/full browser inspector + promoted-memory renderer test |
| Reflex | `reflex` | high/reduced browser inspector + reflex-layer renderer test |
| Stale | `stale` | low/reduced browser inspector + coherence projection tests |
| Degraded | `degraded` | high/reduced browser inspector + coherence projection tests |
| Stopped | `stopped` | low/reduced browser inspector + stop renderer tests |

High/medium/low fixture tiers and reduced-motion handling are available in the
gallery. Representative browser inspector coverage now spans the requested
postures, and five real authenticated backend journeys are recorded (chat,
approval hold, approved write replay, durable development verification, and
the live worker-boundary refusal); backend-driven worker/materialization
cycles and product-hardware performance acceptance remain open. The current
live swarm probe records the fail-closed `strategy_unavailable` boundary rather
than pretending that a worker cycle exists.

## Scene architecture

The current scene remains one `SuperbrainApp` root with `WorkspaceCanvas`,
`CortexEngine`, `SuperbrainReactiveEffects`, GagosChrome and the
LivingWorkspaceShell. This slice inserts no extra scene root. The product-owned
seam now supplies the cortex/conductor, bounded branch, memory field,
membrane, and materialization-continuity projections below the existing R3F
scene. Remaining body work is richer pooling and loaded-scene validation for:

1. CortexField
2. SpinalConductor
3. TemporaryBranchPool
4. MemoryCerebellarField
5. SovereignMembrane

DOM remains the authority for conversation, approval, receipts, editor text,
focus, selection and accessibility. Three.js supplies spatial continuity,
attention, conduction, bounded branch motion and materialization cues.

## Shader and material architecture

No new shader family is introduced in this slice. The implementation preserves
the current centralized palette, shared uniforms, point-field shaders, existing
post-processing and the product-owned effect materials. The target architecture
continues to use at most three major families:

- living material for cortex, spine and temporary branches;
- human material for conversation, approval, stop and input;
- evidence material for verification, receipts and Expert inspection.

The next material change must be justified by a captured state gallery and a
quality-tier budget. No provider rainbow or unmeasured green verification glow
may be added.

## Worker physical lifecycle

The semantic lifecycle is now available as a physical branch record with a
stable pool slot and terminal flag. The current renderer augments each bounded
mote with one three-point branch line from its spinal origin to the worker
marker. The line uses a stable ref-mutated scratch pool in the frame loop and
is capped by the same eight worker records. This is an intermediate anatomical
branch, not yet a fully instanced branch material system. The worker burst,
teardown, stop, and reduced-motion boundaries are test-covered; a loaded-scene
rapid-cycle and resource-soak measurement remain open before expanding the
geometry.

## Workspace materialization lifecycle

No workspace authority or DOM lifecycle changed. Existing tab records,
anatomical conductor seats, materialized surfaces and DOM work content remain
the source of workspace truth. `physicalMaterialization.ts` projects at most
12 canonical surfaces into bounded continuity cues, preserving seat, lifecycle,
focus, origin, target, and whether the DOM surface is mounted or retracting.
The reactive seam consumes this projection only to decorate the canonical seat
markers; it does not mount, remove, focus, approve, or execute anything. It
must never delay an approval, result, error, verification or stop message.

## Verification, recovery and reabsorption

The projection preserves the existing distinctions between verification pass,
verification failure, unverified completion, refusal, rollback, stale
continuity and stopped presentation. A pass can later receive evidence
material treatment; this slice does not settle any result merely because a
physical convergence value is high. Failed or refused action remains
reabsorbing/unsettled and terminal worker evidence is retained for the existing
bounded window. The renderer now consumes the projected verification state
directly: pending and fail remain visibly unsettled, while only pass receives
the stable settlement treatment.

## Memory and reflex lifecycle

Reflex reuse is physically distinct from model-like planning through the
`reflex` layer and `conduct` pulse. Memory recall is inward and temporary;
promotion settles only when the semantic signal says so. The product seam now
renders one bounded cerebellar torus cue: recalled is inward, promoted is
settling, and reflex is conducting. It is static and quality-tier bounded, so
reduced motion retains the memory meaning without adding travel. The projection
does not fabricate lesson, skill or executable-playbook depth when the current
stores expose less information.

## Quality tiers and reduced motion

The existing High/Medium/Low quality provider, DPR relief, point-count caps,
post-processing controls and non-WebGL fallback remain the degradation
authority. This slice does not silently change the operator-selected structural
tier.

Reduced motion continues to suppress travel, orbit, bloom and pulse effects in
the existing shared path. The physical snapshot retains state meaning so the
renderer can show static branch/membrane/conductor and memory markers instead
of dropping the state entirely.

## Renderer failure behavior

The #363 `SuperbrainApp` and `WorkspaceCanvas` containment remains unchanged:
WebGL failure does not imply backend failure, and conversation, approval,
Emergency Stop, workspaces and receipts remain mounted. The physical slice
does not add a retry path or clear any semantic state.

The first browser verification of this slice exposed a real R3F integration
bug: semantic `data-*` props such as `data-posture` and `data-surface-posture`
were interpreted by Fiber's dashed-prop resolver as pierced Three.js paths,
causing a mount exception. The renderer now keeps only the existing test IDs
on scene objects and derives semantic assertions from the pure physical
projection instead; all semantic DOM metadata was removed from the 3D nodes.
After the repair, the local browser server emitted only the pre-existing
`THREE.Clock` deprecation warning. The in-app browser still could not provide
WebGL and therefore remained on the truthful fallback, so this is runtime
mount/fallback evidence rather than loaded-scene visual evidence.

A repository-headless browser probe then exercised the real
`WEBGL_lose_context` extension. `webglcontextlost` fired; after the four-second
grace/remount boundary the product-owned fallback notice was visible while
the Talk-to-GAGOS input and Emergency Stop remained present. Clicking the
explicit Retry visual organism control remounted one canvas and removed the
fallback notice. The browser did not emit `webglcontextrestored`, so this is
measured loss → truthful fallback → explicit remount recovery, not an
in-place restoration or a `context-recovery` latency claim.

The handoff's observability warning was also corrected. `mirror-reconnect` now
starts timing only after an already-connected mirror loses transport and records
the elapsed monotonic duration only when the projection reaches the measured
`fresh` barrier. Initial boot and a transport `connected` event before replay
and synchronization are intentionally not recorded as recovery latency.

## Performance evidence

The unchanged #363 baseline was 163 files / 901 tests, 4,311 transformed
modules, and a 70-file production asset output. After the physical projection,
gallery, worker branch, membrane, cortex, conductor, memory, and
materialization-continuity slices:

- focused renderer/diagnostic gate before this slice: 6 files / 20 tests passed;
- incremental verification/council renderer gate: 3 files / 9 tests passed;
- focused gallery/physical/verification gate: 5 files / 15 tests passed;
- gallery live-region contract added afterward: 1 file / 4 tests passed;
- full frontend suite: 169 files / 929 tests passed in 75.59 seconds on the
  latest checkpoint (the prior 928-test pass completed in 100.25 seconds);
- typecheck: passed;
- production build after gallery entry: 4,316 modules transformed in 4.25 seconds
  on the latest checkpoint;
- lint: 0 errors / 123 warnings;
- port unit tests: 5/5 passed;
- CSS canon, texture/GLB canon, frozen-core and whitespace checks: passed.

The current branch/membrane ceiling is eight worker branches, three points per
branch, or 16 segment-pair updates (32 `setXYZ` calls) per active frame. A
conductor path is capped at 12 points / 11 segment pairs with at most 12 static
seat markers; the low tier uses the smaller marker geometry. The memory field
is one static torus, and physical materialization continuity is capped at 12
surface records with one seat decoration per canonical occupied seat. A
Node/Three CPU microbenchmark of the actual pooled point-update helper over
60,000 synthetic frames averaged 0.000487 ms/frame; this is roughly 0.003% of
a 16.67 ms frame budget for that hot path only. The sovereign membrane is one
static torus and has no `useFrame` mutation. This is useful allocation/loop
evidence, not GPU, draw-call, field p50/p95, GPU-memory or 20–30 minute soak
evidence; the loaded branch state still needs operator/browser profiling.
The known Vite native-loader warning and existing lint warnings remain
unchanged.

The product-owned metric buffer now has a localhost-only bounded read hook,
covered by a unit test, so future browser evidence can read the already
recorded samples without exposing prompts, records, identities or authority
data. The current CUA read-only evaluation surface runs in an isolated world:
on a fresh 1280×720 port-5185 loaded-scene run, the canvas and `three.js r186`
engine were visible but `typeof window.__getFrontendMetrics` remained
`undefined`. No frame samples are claimed from that probe.

The repository headless browser harness did expose both the metric buffer and
the managed `__getPerf` probe on `localhost`. A valid loaded-page chain at
1280×720 kept one canvas and 142–145 DOM nodes while the harness reported
approximately 2 FPS, p50 frame time 483.3 ms, p95 frame time 566.7 ms, and a
maximum dropped-frame period of 966.6 ms. The relief governor moved its factor
from 1.0 toward 0.6 and its DPR from 1.0 toward 1.3. These are attributable to
the throttled headless/WebGL environment, not a product-hardware target; they
prove that the governor reacts and that the sampler is live, not that field
performance is acceptable. The browser also emitted the existing `THREE.Clock`
deprecation and `GL_CLOSE_PATH_NV` ReadPixels-stall warnings. The new
`tools/gagos-physical-soak.ps1` collector rejects a blank replacement tab, but
a 30-minute run could not remain in the same daemon page: batch 2/10 replaced
the loaded scene with `canvas=0`, so the soak is invalid and remains open.

The collector now builds one persistent browser chain for all requested batches
instead of invoking the daemon once per batch. A requested 150-batch,
30-minute single-chain attempt then failed closed before batch 1 because the
headless browser server lost its connection and timed out during startup. The
collector change is verified by a two-batch single-chain run, but the requested
long-run soak remains unavailable in this environment.

A single-chain scheduled page-world probe provided one additional bounded
loaded-scene observation: over roughly eight seconds it retained one canvas,
142–169 DOM nodes, and live `__getFrontendMetrics` / `__getPerf` hooks across
seven samples. The headless governor reported 2–7 FPS, with observed dropped
periods from 266.6–966.6 ms and a 2,689.8 ms 3D-initialization metric. This
confirms page identity and instrumentation during a short loaded run, but the
values remain harness-throttled and do not change the product-hardware or soak
limitations above.

The product-owned renderer now samples a separate localhost-only scene
diagnostic buffer once per second from the existing R3F frame loop. Each sample
contains scene-object count, render calls, live geometry/texture counts, and
bounded worker/lightning/materialization pool sizes; it never includes content,
identity, authority, or backend data. The short collector validation retained
one loaded canvas across two batches and observed scene objects 55–55,
geometries 19–20, textures 22–22, render calls 1–1 and transient pool size
0–0 before the cortex-current slice. After that slice, the same short idle
collector observed scene objects 58–58 and geometries 22–22, with textures
22–22, render calls 1–1 and transient pool size 0–0. This is instrumentation
and a short idle observation, not a repeated worker/materialization soak or a
proof of production GPU performance.

The collector's Windows PowerShell boundary was then repaired so the browser
receives nested command tuples as arrays and informational stderr does not
abort the run. A controlled three-batch attempt completed two valid loaded
scene batches with the same bounded identity (`canvas=1`, DOM 143, scene
objects 58, geometries 22, textures 22, render calls 1, transient pool 0;
governor factor 0.9–1.0 and DPR 1.0–1.45). Batch 3 failed closed when the
headless browser manager lost its renderer process during relaunch. This is a
better-validated collector boundary, not long-run or product-hardware
performance evidence; the soak remains open.

After the verification/council geometry change, a fresh two-batch loaded idle
collector run retained one canvas and 142 DOM nodes per batch. Scene objects
remained 58–58, geometries were 22–23, textures 22–22, render calls 1–1 and
the transient pool 0–0; the governor factor was 0.9–1.0 and DPR 1.0–1.0, with
a maximum observed dropped period of 950 ms. This is a short attributable
delta check only; it does not establish a long-run resource trend or a field
frame budget.

The existing bounded metric and scene buffers now also publish a localhost-only,
content-free numeric probe on the document root so a persistent browser
inspection context can read the same values without crossing the page-world
boundary. The probe has no prompt, record, identity, authority, or backend
fields and is cleared with the existing sampler reset. A persistent Codex
in-app browser run is recorded in
[gagos-physical-persistent-soak.md](evidence/gagos-physical-persistent-soak.md):
150 samples at 12-second intervals retained one canvas and 144 DOM nodes for
2,158,681 ms (about 36 minutes), with scene objects 58–58, render calls 1–1,
geometries 20–21, textures 22–22, transient/worker/materialization/lightning
pools 0–0, p50 16.7 ms, p95 16.8–17.1 ms, and observed dropped periods
50.0–67.1 ms. This is valid persistent idle/resource evidence in the stated
481×778 browser environment, not product-hardware certification.

The same persistent tab then exercised planning, acting, the eight-branch
worker burst, verification pass, rollback/reabsorption, stale, and emergency
stop gallery fixtures. The worker-burst diagnostic reported eight branches and
four worker motes with a transient pool of four. The gallery has no live tabs,
so materialization surfaces remained zero; live backend-driven materialization
and its resource trend remain unproven.

A fresh 1280×720 High/full-motion gallery cycle then sampled planning, acting,
worker-burst, verification-pass, rollback/recovering, stale, stopped, and
resting after fixture selection. Every sample held one render call and zero
lightning objects. The worker burst peaked at eight branches, briefly reached
83 scene objects / 34 geometries / transient pool 9 during formation, then
settled to 71 objects / 26 geometries / transient pool 4; the other states held
57–61 objects, 16–19 geometries, and bounded transient pools. No monotonic
growth appeared across the short samples, and the browser console reported no
errors. The file-backed observation is
[gagos-physical-active-runtime-cycle.md](evidence/gagos-physical-active-runtime-cycle.md).
This is short active-state resource evidence only: it is not a product-hardware
frame-time result, GPU-memory result, or 30-minute active soak, and the gallery
materialization count is correctly zero.

A persistent High/full-motion `worker-burst` run is recorded in
[gagos-physical-active-worker-soak.md](evidence/gagos-physical-active-worker-soak.md).
The first attempt produced 98 accepted samples over 1,116,942 ms (~18.6
minutes) before its tab handle disappeared. A fresh visible retry then produced
150 accepted samples over 1,816,723 ms (~30.28 minutes) at 71 scene objects,
26 geometries, 21 textures, one render call, transient pool 4, eight branches,
four motes, zero materialization surfaces, and zero lightning objects. One
observation timeout was re-polled successfully on the same tab; no samples were
inferred across it. This is valid 30-minute deterministic-gallery resource
evidence, not product-hardware performance or live backend materialization.

## Responsive and accessibility evidence

The existing #363 browser evidence remains valid for the unchanged shell:
Guided/Expert boundaries, keyboard skip-to-chat, focus restoration, 44px
targets, truthful unavailable copy and renderer fallback are preserved. This
slice adds no new DOM or touch surface and has not been presented as a fresh
viewport-matrix or screen-reader capture.

A prior 384×800 in-app browser capture after the branch/membrane wiring
rendered the actual point-field organism and spine as the visual anchor. A
fresh 1280×720 inspection on port 5183 mounted the repaired loaded scene: the
point-field organism and spine were visible, the canvas drawing surface
measured 832×720 CSS/backing pixels, and the canvas reported
`data-engine="three.js r186"`. Browser diagnostics contained no R3F exception;
the only warning was the existing `THREE.Clock` deprecation. Guided/Expert
mode remained switchable; Expert exposed the operational mirror and ambient
motion control, which was paused (`Resume ambient motion`, checked) and then
restored. Skip-to-chat focused the request field. Emergency Stop details
opened and closed with focus returning to the disclosure trigger. The shell
reported the unavailable live operational picture honestly while the renderer
remained visible. This is loaded-scene, shell, and focused accessibility
evidence; it is not a live backend journey, forced context-loss recovery,
viewport matrix, field-performance, soak, screen-reader, or human-validation
claim.

The reproducible loaded-scene capture is [gagos-physical-loaded-1280x720.png](evidence/gagos-physical-loaded-1280x720.png).
It is a visual handoff artifact only; it does not replace the state gallery,
operator review, or performance acceptance evidence.

After the verification/council renderer change, a fresh 1280×720 smoke chain
again mounted one canvas with `data-engine="three.js r186"`, no renderer
fallback marker, and the conversation input present. The shell exposed the
`Emergency stop` control. No new R3F mount exception appeared; the console
contained the known `THREE.Clock` deprecation and `GL_CLOSE_PATH_NV` GPU-stall
warnings, plus expected `ERR_CONNECTION_REFUSED` responses from the offline
backend. This is a renderer-integrity check, not a live state-cycle or
performance acceptance result.

The headless browser then checked the required responsive matrix at 320×568,
375×812, 768×1024, 1024×768 and 1440×900. Every viewport reported
`scrollWidth === innerWidth`, retained the Talk to GAGOS input and Emergency
stop control, mounted `three.js r186` without the fallback marker, and kept one
canvas. The measured canvas drawing surfaces were respectively 320×202,
375×336, 468×1024, 665×768 and 990×900 CSS/backing pixels. This proves layout
and control continuity in the harness; it is not screen-reader or human
validation.

A fresh 1280×720 local browser inspection is recorded in
[gagos-physical-accessibility.md](evidence/gagos-physical-accessibility.md).
The root accessibility tree exposed the skip-to-chat control, Guided/Expert
mode buttons with pressed state, the request textbox, voice controls, Send,
Emergency stop, and its Details disclosure. Activating skip-to-chat focused
the request field; Expert / Mirror changed its pressed state; and the
Emergency stop disclosure opened to expose Refresh, a Reason textbox, and
Close details. The dev-only gallery exposed the Quality combobox, Low/Medium/
High options, a Reduced motion checkbox, and all 21 named fixture buttons.
The resulting high-quality/reduced-motion gallery capture is
[gagos-physical-gallery-accessibility-1280x720.png](evidence/gagos-physical-gallery-accessibility-1280x720.png).
This is stronger DOM/keyboard-path evidence than the prior capture, but it is
still not a screen-reader session, operator approval, or human-validation
claim. The browser reported no errors and retained the known Clock/GPU-stall
warnings, so hardware and long-run performance remain open.

The gallery now also exposes its selected fixture, quality tier, and reduced-
motion mode through a bounded `role=status` live region. A fresh local browser
inspection selected the eight-branch worker-burst fixture and then enabled
Reduced motion; the announcement updated from `Full motion enabled` to
`Reduced motion enabled`. This strengthens the DOM accessibility path while
remaining explicitly short of human screen-reader evidence.

## Verification gates

The earlier focused renderer/projection gate passed 10 files / 33 tests. The
renderer/diagnostic regression passed 6 files / 20 tests before the latest
slice; the incremental verification/council gate passed 3 files / 9 tests,
including the
12-worker-to-eight-branch cap, teardown regression, canonical conductor path,
approval hold, low-tier marker budget, reduced-motion posture marker, memory
layer cues, reduced-motion memory retention, materialization continuity, and
measured mirror recovery and the bounded browser metric accessor. The full
suite now passes 169 files / 929 tests. Typecheck, build, lint, `test:port` (5/5), CSS canon,
texture/GLB canon, frozen-core and `git diff --check` passed. `npm run
port:check` remains blocked by `Lab source missing:
components/QualityTierProvider.tsx; deletion requires explicit migration.`
That blocker is recorded, not converted to green.

## Known limitations and next step

- The lab source must be reconciled before changing managed anatomy.
- The physical snapshot and materialization projection are pure and consumed,
  but the renderer still uses the existing mote/aurora/lightning geometry
  alongside the intermediate branch line rather than one fully pooled anatomy
  system.
- The deterministic gallery is covered by tests, and authenticated backend
  journeys now cover chat, approval hold, approved write replay and a durable
  development-mode verification pass. The normal container path is still
  unavailable on this machine, and no live backend journey has supplied every
  worker branch and membrane case to the browser.
- The loaded browser inspection confirms the organism and spine render after
  the R3F metadata repair, but it does not yet prove every physical gallery
  state. The capture is ephemeral and no scene-performance claim is made from
  one viewport.
- The loaded headless chain provides frame-time p50/p95 and dropped-period
  samples, but they are severely throttled and accompanied by GPU-stall
  warnings. No attributable product-hardware frame budget or GPU-memory result
  exists; the microbenchmark remains CPU-only for the product hot path. The
  browser fixture now has a valid 30-minute bounded resource soak, but that
  does not substitute for hardware evidence.
- The new scene diagnostic buffer is covered and the persistent idle soak now
  demonstrates a no-growth trend for the loaded resting scene. The accepted
  visible `worker-burst` retry demonstrates the same bounded no-growth trend for
  30.28 minutes in the deterministic gallery. No live backend-driven
  worker/materialization cycle has demonstrated it because the backend remains
  fail-closed at the WorkerFoundry strategy gate; gallery materialization is
  correctly zero.
- The existing frontend metric sampler has unit coverage for frame-time p50,
  p95, dropped-frame periods, measured mirror-reconnect recovery duration, and
  the new bounded localhost read hook. The managed canvas governor source
  contains a localhost-only live FPS/DPR probe. The isolated 127.0.0.1
  inspection context could not see the page-world window hooks, so the
  content-free DOM probe was added; the persistent localhost browser then
  produced the accepted idle p50/p95 and scene/resource ranges. Those values
  remain environment-scoped and are not field-performance evidence.
- The required responsive layout matrix is now captured in the headless
  harness, but screen-reader, touch-gesture, operator visual review, and
  human-validation evidence remain open.
- The operator-ready [human-validation packet](evidence/gagos-physical-human-validation-packet.md)
  now consolidates the three-participant script, human screen-reader checklist,
  and palette/texture operator sign-off without claiming any results.
- Operator visual review of the sacred palette and texture/GLB canon remains
  human-owned.
- Human validation from at least three non-builders remains open.

The next implementation slice is screen-reader, operator visual, and
three-person human validation. A live backend-driven worker/materialization
browser cycle is currently blocked by the measured `strategy_unavailable`
WorkerFoundry gate; keep the current eight-slot branch ceiling until that path
and the lab-source ownership gap are resolved. Do not expand geometry from the
CPU microbenchmark or idle soak alone. The idle soak is valid environment
evidence, not product-hardware certification.
