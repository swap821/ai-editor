# Local renderer idle smoke — 2026-09-24

Status: limited browser observation; not an accepted device or performance baseline.

## Run identity

- Product route: official `frontend/`, production preview at `http://127.0.0.1:4173/`.
- Branch: `codex/gagos-living-being-v2`; the current branch head during capture was `5133587d`. The renderer source change is committed as `c7255640` (`fix(frontend): account complete post-processing frames`), and later commits were documentation-only.
- Preview: existing `frontend/dist` artifact; `index.html` last written 2026-09-24 16:36:37 Asia/Kolkata (11:06:37 UTC). The relevant source files' last-write times precede that artifact timestamp, but the artifact does not carry a captured source-tree hash and no rebuild was run for this observation. Therefore source-to-artifact identity is not independently pinned.
- Browser: Codex In-app Browser (`iab`). Exact browser engine/build, OS build, physical host profile and active WebGL adapter were not exposed by the available browser interface. Do not attribute this result to either G15 GPU mode or a desktop-class machine.
- Observation window: 2026-09-24 11:17:12–11:17:16 UTC; four idle snapshots about 1.01 seconds apart.
- Product state: Guided/resting screen. The page visibly reported “Operational picture unavailable”; backend setup was unavailable. Worker and materialization values below were zero in that observed scene, not evidence of a live work journey.

## Observed values

| Sample | RAF p50 | RAF p95 | Three.js draw calls | Geometries | Textures | Worker branches / motes | Materialization surfaces |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 8.3 ms | 8.5 ms | 40 | 21 | 22 | 0 / 0 | 0 |
| 2 | 8.3 ms | 8.5 ms | 40 | 21 | 22 | 0 / 0 | 0 |
| 3 | 8.3 ms | 8.4 ms | 40 | 21 | 22 | 0 / 0 | 0 |
| 4 | 8.3 ms | 8.5 ms | 40 | 21 | 22 | 0 / 0 | 0 |

The counter attribute stayed populated at `40` over all four samples. The served page exposes the diagnostic attribute; the source implementation in `c7255640` captures it at the R3F priority after the priority-1 EffectComposer callback. Because the served artifact's source hash was not pinned, this browser smoke alone does not prove that exact implementation was in the artifact. `drawCalls` counts Three.js draw submissions; it is not a composer-pass count. Missing renderer counters were not observed in this run, so this run does not independently re-test the unavailable-counter branch.

## Limits and interpretation

- This confirms that the served local resting scene publishes a populated, stable renderer-counter snapshot. It is a production-preview smoke, not a source-hash-pinned composer verification or desktop baseline: machine/browser/GPU identity is unverified, no budget was frozen, and no input-latency distribution was captured.
- RAF values are not CPU time or GPU time. Active adapter, CPU/GPU duration, battery/thermal state and input latency are unavailable.
- No typing, materialization, streaming, eight-worker, verification, failure, stale, Stop or reabsorption scenario was exercised; this was one offline resting scene only.
- One existing console warning was observed: `THREE.Clock` is deprecated in the Three.js bundle. The captured console error/warning query returned no runtime errors.
- A screenshot was visually inspected but not retained as an artifact. The point-field organism was visible; the product itself displayed its unavailable operational-picture fallback.
- Acceptance remains **3/100**. This smoke earns no points and does not close LB-03, PERF-01, PERF-02 or PERF-03.

## Reproduction

With the existing preview artifact present, run `npm run preview -- --host 127.0.0.1 --port 4173 --strictPort` from `frontend/`, open the local route in a browser that exposes its identity, and sample the root `data-gagos-*` attributes after the scene has mounted. For an accepted device run, pin the exact machine/OS/browser build and active GPU before measurement; record RAF, draw-call, CPU/GPU and input-latency evidence separately. Do not use the in-app browser result as a substitute for those fields.
