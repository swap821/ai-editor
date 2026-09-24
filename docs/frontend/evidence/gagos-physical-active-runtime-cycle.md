# GAGOS physical embodiment — active runtime cycle

Captured 2026-09-24 in the development-only physical gallery at
`http://127.0.0.1:5187/?physical-gallery=1`, using a 1280×720 browser viewport,
High quality, and full motion. The gallery remained fixture-only; it did not
connect a live worker or materialization backend.

## Observed states

Each state was selected through its named gallery control, allowed to settle,
then sampled three times about one second apart from the existing numeric-only
scene probe. Every sample reported one render call and zero lightning objects.

| Fixture | Scene objects | Geometries | Textures | Transient pool | Branches / motes | Materialization surfaces |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| planning | 57 | 16 | 7 | 0–1 | 0 / 0 | 0 |
| acting | 60 | 18 | 7 | 1 | 1 / 1 | 0 |
| worker-burst | 71–83 | 26–34 | 21 | 4–9 | 8 / 4–8 | 0 |
| verification-pass | 60 | 19 | 21 | 1 | 0 / 0 | 0 |
| rollback-recovering | 61 | 19 | 7 | 2–3 | 1 / 0–1 | 0 |
| stale | 57 | 16 | 3 | 2 | 0 / 0 | 0 |
| stopped | 58 | 16 | 3 | 1 | 1 / 1 | 0 |
| resting | 57 | 16 | 7 | 0–1 | 0 / 0 | 0 |

The worker-burst formation sample briefly reported 83 objects, 34 geometries,
and a transient pool of 9 before settling to 71 objects, 26 geometries, and a
transient pool of 4. It remained capped at eight worker branches. Subsequent
samples for each selected fixture were stable at the ranges above; no
monotonic growth appeared in this short cycle.

The settled gallery rendering was visually inspected and the browser console
reported no errors. Existing warning behavior is tracked separately in the
implementation report. Because the gallery has no live workspace tabs,
materialization surfaces correctly remained zero.

## Evidence boundary

This is a short loaded active-state resource observation, not a product-hardware
performance result, frame-time p50/p95 measurement, GPU-memory measurement, or
30-minute active soak. The persistent idle/resource soak remains the stronger
long-run result. Live backend-driven worker/materialization behavior remains
blocked by the authenticated `strategy_unavailable` WorkerFoundry gate.

