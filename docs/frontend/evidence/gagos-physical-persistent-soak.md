# GAGOS physical embodiment — persistent WebGL/resource evidence

Date: 2026-09-24  
Branch: `codex/frontend-physical-embodiment`  
URL: `http://localhost:5187/`  
Browser: Codex in-app browser, one persistent tab  
Viewport: 481×778  
Sampling: 150 samples, 12 seconds apart

## Idle soak

The persistent page identity remained loaded for 2,158,681 ms (about 36
minutes) from the first to the last scene diagnostic timestamp. No navigation,
reload, canvas loss, or page replacement occurred during the accepted run.

| Measurement | Observed range |
| --- | ---: |
| Samples | 150 |
| Canvas count | 1–1 |
| DOM nodes | 144–144 |
| Scene objects | 58–58 |
| Render calls | 1–1 |
| Geometries | 20–21 |
| Textures | 22–22 |
| Transient pool | 0–0 |
| Worker branches | 0–0 |
| Worker motes | 0–0 |
| Materialization surfaces | 0–0 |
| Lightning pool | 0–0 |
| Frame-time p50 | 16.7 ms |
| Frame-time p95 | 16.8–17.1 ms |
| Observed dropped-frame period | 50.0–67.1 ms |

The measurements came from the existing bounded frontend metric and scene
diagnostic buffers. A localhost-only DOM probe made those content-free values
visible to the persistent browser's isolated inspection context; it publishes
only numeric frame/scene/pool data and is removed by the existing clear path.
It does not publish prompts, records, identities, authority data, or backend
content. The focused metric test passed 10/10 after the probe was added.

## Representative physical states

The same persistent tab then exercised the dev-only gallery at the same
viewport. Each fixture was clicked semantically and read after 2.5 seconds.
These are state snapshots, not claims of a live backend turn:

| Fixture | Canvas | DOM | Scene objects | Geometries | Textures | Transient | Branches | Motes | Materialization surfaces |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Planning | 1 | 129 | 57 | 16 | 7 | 0 | 0 | 0 | 0 |
| Acting | 1 | 129 | 60 | 18 | 7 | 1 | 1 | 1 | 0 |
| Worker burst | 1 | 129 | 71 | 26 | 21 | 4 | 8 | 4 | 0 |
| Verification pass | 1 | 129 | 60 | 19 | 21 | 1 | 0 | 0 | 0 |
| Rollback / reabsorption | 1 | 129 | 61 | 19 | 7 | 2 | 1 | 0 | 0 |
| Stale | 1 | 129 | 57 | 16 | 3 | 2 | 0 | 0 | 0 |
| Emergency stop | 1 | 129 | 58 | 16 | 3 | 1 | 1 | 1 | 0 |

The worker-burst fixture visibly exercised the bounded eight-branch ceiling and
the diagnostic reported eight branches, four worker motes, and a transient pool
of four. The gallery has no live materialized tabs, so its materialization-surface
count is correctly zero; live workspace materialization remains an explicit
evidence gap rather than an invented pass.

## Console and interpretation boundaries

The persistent tab's final log read contained no errors and two existing
`THREE.Clock` deprecation warnings. Earlier headless inspection also recorded
`GL_CLOSE_PATH_NV` ReadPixels-stall warnings; this run does not claim those
warnings are absent on other browser paths.

This is a valid persistent idle/resource soak and a bounded representative-state
diagnostic run. It is not product-hardware certification, a 60-FPS claim, a
live backend worker/materialization journey, screen-reader validation, operator
visual approval, or three-person human validation.
