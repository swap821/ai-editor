# GAGOS physical embodiment — active worker soak (partial)

Captured 2026-09-24 in the development-only physical gallery at
`http://127.0.0.1:5187/?physical-gallery=1`, with a 1280×720 viewport, High
quality, full motion, and the deterministic `worker-burst` fixture selected.
This is frontend fixture evidence; it is not a live WorkerFoundry cycle.

## Accepted window

The same persistent page was sampled 98 times over 1,116,942 ms
(approximately 18.6 minutes). The first sample was taken after worker
formation had settled. Every accepted sample reported the same bounded
snapshot:

| Metric | Value |
| --- | ---: |
| Scene objects | 71 |
| Geometries | 26 |
| Textures | 21 |
| Render calls | 1 |
| Transient pool | 4 |
| Worker branches | 8 |
| Worker motes | 4 |
| Materialization surfaces | 0 |
| Lightning objects | 0 |

The page URL was still the intended gallery route at the midpoint check, and
the browser reported no console errors at that check. The materialization count
is correctly zero because the deterministic gallery contains no live workspace
tabs.

## Boundary and limitation

The browser session stopped accepting DOM observations after the 98th sample;
the tab handle disappeared from the active browser session. The run therefore
did not reach 30 minutes and is not accepted as a full soak. It is accepted as
an attributable 18.6-minute active worker/resource window with no observed
growth, while the earlier 36-minute idle soak remains the long-run idle
evidence. No frame-time p50/p95, GPU-memory, product-hardware, live backend
worker, or materialization claim is made from this run.

## Accepted visible retry

A fresh visible-browser retry used the same 1280×720 viewport, High quality,
full motion, route, and deterministic `worker-burst` fixture. It produced 150
accepted samples over 1,816,723 ms (approximately 30.28 minutes), beginning
after formation had settled. One DOM observation timed out during the run; a
same-handle re-poll confirmed the page was still present at the intended URL,
the selected control was unchanged, and the console error log was empty before
sampling resumed. The timeout is recorded as an observation interruption, not
filled with inferred samples.

The final check reported the intended gallery URL and title, the single
selected state `worker-burst · High`, zero console errors, and one normalized
scene/resource state across the accepted samples:

| Metric | Value |
| --- | ---: |
| Scene objects | 71 |
| Geometries | 26 |
| Textures | 21 |
| Render calls | 1 |
| Transient pool | 4 |
| Worker branches | 8 |
| Worker motes | 4 |
| Materialization surfaces | 0 |
| Lightning objects | 0 |

This satisfies the frontend deterministic-fixture 30-minute active resource
window. It does not represent a live backend WorkerFoundry cycle, workspace
materialization, product-hardware frame-time p50/p95, GPU-memory, or field
performance result; the zero materialization count is expected for this gallery
fixture.
