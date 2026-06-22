# GAGOS Performance Budget — the 60fps relief valve (P2.3)

**Landed:** 2026-06-23 (PR — `feat/perf-relief-valve`). Makes the poster's named
"must run smoothly at 60fps" guarantee REAL, without amputating the look.

## The principle (FIDELITY-sacred)

Only **resolution (DPR)** flexes to hold the frame rate. The structural tier
(geometry, particle counts, the sky), hue, palette, and textures are **never**
auto-changed — those move only on the operator's FIDELITY click. Resolution is
"smoothness"; everything else is the sacred look.

## How it works

- `TierGovernor` (inside the Canvas) runs drei's `PerformanceMonitor` watching the
  real render loop.
- FPS window `PERF_BOUNDS = [50, 58]` (targets 60). Below 50 → shed DPR; above 58 →
  restore it. `flipflops=3` before it gives up chasing.
- The monitor's 0..1 `factor` maps through `dprForFactor(tier, factor)` (pure,
  unit-tested) into the tier's DPR range and is applied live via `setDpr()`:

  | tier | DPR floor (max relief) | DPR ceiling (full sharp) |
  |---|---|---|
  | high | 1.0 | 1.5 |
  | medium | 1.0 | 1.25 |
  | low | 1.0 | 1.0 (never flexes) |

  Floor is never below 1.0 — we never blur below native device pixels.
- Runtime-only: the DPR breath is **not persisted**. It self-restores when the
  scene is smooth again. Only the operator's structural-tier click persists.
- Warmup: DPR relief arms at `DPR_WARMUP_MS = 4s` (reversible, so a brief early
  false-drop self-corrects); the structural-tier ADVISORY waits the full
  `ADVISORY_WARMUP_MS = 20s` (boot/shader-compile jank must never count).
- Escalation: if FPS is STILL low after DPR has bottomed out, the governor
  whispers a terminal advisory ("click FIDELITY…") — it never acts.

## How to profile (operator)

On `:5173`, read the live probe in the browser console (dev build only):

```js
window.__getPerf()  // → { fps, factor, dpr, tier }
```

- `fps` — rolling ~0.5s frame rate (PerfProbe samples every frame).
- `factor` — 1 = full quality; <1 = relief engaged (resolution shed).
- `dpr` — the device-pixel-ratio currently applied.

To watch the valve ENGAGE, load the scene heavily (open several work tabs, run a
generating turn) and watch `fps` dip then `dpr`/`factor` drop to recover it, then
recover when idle.

## Known RTX-3050 thresholds (prior measurement)

- Point-field RENDERING breaks at ~256k points; working threshold ~90k.
- `high` tier = 200k brain + 56k spine points (heavy; the DPR relief is the safety
  margin for fill-rate/overdraw — additive point sprites are overdraw-bound, which
  DPR directly relieves).
- Idle measured: **~120fps at DPR 1.5 (high)** on the operator's RTX (2026-06-23) —
  comfortable headroom; the valve only engages under real load.

## Deliberately NOT done

- `@pmndrs/detect-gpu` first-load tier probe — adds a dependency; the persisted
  operator tier + the runtime DPR relief already cover the need. Revisit only if a
  cold first-load on a weak GPU proves a problem.
- `r3f-perf` overlay dep — `window.__getPerf()` gives the numbers dep-free.
- Per-tier point-SIZE auto-scaling — point size is a tuned aesthetic (crisp look);
  auto-changing it would touch the sacred look, so it stays operator-controlled.
