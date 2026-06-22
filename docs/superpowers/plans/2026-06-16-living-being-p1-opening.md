# Living-Being P1 "The Opening" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship "The Opening" — the being arrives (coalescence on first load / awakening on return), settles to a breathing rest with its spinal cord present as a short brainstem, and reacts the first time the user speaks — entirely inside the existing R3F scene, as the trust proof before any later phase.

**Architecture:** A pure, three.js-free **lifecycle/posture state machine** (`BOOTING → ARRIVING → REST ↔ ATTENTIVE`) is the single source of truth, with pure **easing/timing helpers** and **shared motion tokens** beside it (all fully unit-tested). The existing scene **subscribes** to the machine and drives new shader-uniform "envelopes" (`uArrival` / `uIgnite` / `uAwaken`) in its frame loop — additive only, returning to the canon look at rest. `prefers-reduced-motion` lives in the same frame logic (skip the large-scale arrival, render settled REST). Every visual step is gated by a BROWSER-PROOF checkpoint + operator sign-off (FIDELITY law); logic steps are TDD.

**Tech Stack:** TypeScript, React, React Three Fiber + drei + three, Vitest. Path alias `@/* → frontend/src/superbrain/*`. Commands: `cd frontend && npm run test|typecheck|lint|dev` (dev on `:5173`).

> **Conventions for every commit in this plan:** work on a branch off `feat/renovation-p0` (e.g. `feat/living-being-p1`); end each commit message with the trailer `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. Never skip hooks. Visual tasks are NOT done until the operator signs off in his browser.

---

## File Structure

**Create:**
- `frontend/src/superbrain/lib/openingTokens.ts` — The ONE source of truth for opening motion (durations, cubic-bezier control points, breath cycle, scale floor), read by both the pure helpers and the shader envelopes so timing/easing never drift.
- `frontend/src/superbrain/lib/openingMotion.ts` — Pure easing/timing helpers: cubic-bezier solver, coalescence envelope, ignition pulse, awaken notice, the reduced-motion decision, and the "user spoke → awakening" trigger test. No three.js.
- `frontend/src/superbrain/lib/openingMotion.test.ts` — Vitest unit tests for the helpers.
- `frontend/src/superbrain/lib/lifecycleStateMachine.ts` — Pure posture state machine + a cognitionBus-style subscriber singleton. The being's posture; the scene subscribes, no three.js inside.
- `frontend/src/superbrain/lib/lifecycleStateMachine.test.ts` — Vitest unit tests for the machine.
- `frontend/src/superbrain/components/canvas/Brainstem.tsx` — The spinal cord present at rest: a short tapered luminous brainstem descending from the cortex base, parented to the brain group (breathes/leans with it), fading in during arrival. (Anatomy now; extends to the conductor spine in P4.)

**Modify:**
- `frontend/src/superbrain/components/canvas/SuperbrainScene.tsx` — Add `uArrival`/`uIgnite`/`uAwaken` uniform leaves; subscribe to the lifecycle machine; advance arrival/awaken envelopes in the root `useFrame`; gate brain scale/opacity/brighten, thought-wave suppression, and idle re-arm off posture; mount the Brainstem.
- `frontend/src/superbrain/components/canvas/AccretionCore.tsx` — Add `uArrival` uniform; modulate inflow so motes read as streaming-in coalescence during ARRIVING (shader-only).
- `frontend/src/superbrain/components/canvas/CosmicBackground.tsx` — Add `uArrival` uniform; gate the gravitational-pull/funnel strength to the arrival window (shader-only).
- `frontend/src/superbrain/components/canvas/NeuralAura.tsx` — Add `uArrival`; fade shells in from opacity 0 during coalescence (canon at rest unchanged).
- `frontend/src/superbrain/components/canvas/NervousSystem.tsx` — Add `uAwaken`; light nerves outward in a staggered ramp on awakening.
- `frontend/src/superbrain/components/ui/BootSequence.tsx` — On fade-out, drive the machine into ARRIVING (coalescence on first-ever load / awakening on return).
- `frontend/src/superbrain/components/canvas/WorkspaceCanvas.tsx` — Bridge `directive` cognition events into the machine (the "user spoke → awakening" trigger) + run the decay heartbeat.

---

### Task 1: Shared opening motion tokens (single source of timing/easing)

**Files:**
- Create: `frontend/src/superbrain/lib/openingTokens.ts`

- [ ] Create `frontend/src/superbrain/lib/openingTokens.ts` with the complete content below. These are the ONE place arrival/awakening timing + easing live, consumed by both the pure helpers and the shader envelopes. Values follow the design guidance (arrival 3.5s within the 3–4s band; breath ~5s; awakening notice ~320ms; a custom cubic-bezier, never bare ease).

```ts
// openingTokens.ts — the ONE source of truth for P1 "Opening" motion.
// Logic helpers (openingMotion.ts) and the scene shaders read the SAME
// numbers, so timing/easing never drift between the unit-tested curve and
// the rendered frame. Transform/opacity/filter only — no layout.

/** Coalescence + awakening durations (ms). Arrival is a RARE, cinematic
 *  event, so it lives at the top of the 3–4s band. */
export const OPENING_TIMINGS = {
  /** First-ever load: knowledge-field streams in and condenses. */
  coalescenceMs: 3500,
  /** Window inside coalescence where the ignition pulse peaks. */
  ignitionPeakMs: 2600,
  /** Every return: dormant cortex lights from a seed. */
  awakeningMs: 2600,
  /** First user-speak "notice" reaction (attentive lean + brighten). */
  awakenNoticeMs: 320,
  /** ATTENTIVE holds this long after the last directive, then eases to REST. */
  attentiveDecayMs: 5000,
  /** Breath cycle at rest — the one essential ambient loop. */
  breathCycleMs: 5000,
  /** Per-element nerve-lighting stagger. */
  nerveStaggerMs: 40,
} as const;

/** Custom cubic-bezier control points (NEVER bare ease / ease-in-out).
 *  Expressive ease-out for the rare arrival; tighter for the notice. */
export const OPENING_EASING = {
  /** Cinematic settle: slow-out, gentle overshoot-free landing. */
  coalescence: [0.16, 1, 0.3, 1] as const,
  /** Awakening seed spread. */
  awaken: [0.22, 1, 0.36, 1] as const,
  /** Quick attentive notice. */
  notice: [0.32, 0.72, 0, 1] as const,
} as const;

/** Coalescence never scales the cortex mesh from 0 — it fades + scales from
 *  this floor to 1 (design law: do NOT start scale from 0). */
export const COALESCENCE_SCALE_FLOOR = 0.85;
```

- [ ] Create the branch and commit: `cd frontend && git switch -c feat/living-being-p1 && git add frontend/src/superbrain/lib/openingTokens.ts && git commit -m "P1: shared opening motion tokens"` (end the message with the Co-Authored-By trailer).

---

### Task 2 (TDD): Pure opening-motion helpers — easing, envelopes, reduced-motion, speak→awakening mapping

**Files:**
- Create: `frontend/src/superbrain/lib/openingMotion.ts`
- Test: `frontend/src/superbrain/lib/openingMotion.test.ts`

- [ ] Write the failing test file `frontend/src/superbrain/lib/openingMotion.test.ts` with the complete content below.

```ts
import { describe, it, expect } from 'vitest';
import {
  cubicBezier,
  coalescenceEnvelope,
  ignitionPulse,
  awakenNotice,
  shouldReduceMotion,
  isAwakeningTrigger,
} from './openingMotion';
import { OPENING_TIMINGS, COALESCENCE_SCALE_FLOOR } from './openingTokens';

describe('cubicBezier', () => {
  it('pins endpoints to 0 and 1', () => {
    const ease = cubicBezier(0.16, 1, 0.3, 1);
    expect(ease(0)).toBeCloseTo(0, 5);
    expect(ease(1)).toBeCloseTo(1, 5);
  });
  it('is monotonic non-decreasing across the unit interval', () => {
    const ease = cubicBezier(0.16, 1, 0.3, 1);
    let prev = -1;
    for (let t = 0; t <= 1.0001; t += 0.05) {
      const v = ease(Math.min(1, t));
      expect(v).toBeGreaterThanOrEqual(prev - 1e-6);
      prev = v;
    }
  });
});

describe('coalescenceEnvelope', () => {
  it('opacity starts at 0 and scale starts at the floor (never 0)', () => {
    const env = coalescenceEnvelope(0);
    expect(env.opacity).toBeCloseTo(0, 5);
    expect(env.scale).toBeCloseTo(COALESCENCE_SCALE_FLOOR, 5);
    expect(env.arrival).toBeCloseTo(1, 5); // 1 = fully in progress
  });
  it('lands settled at the end of coalescence', () => {
    const env = coalescenceEnvelope(OPENING_TIMINGS.coalescenceMs);
    expect(env.opacity).toBeCloseTo(1, 5);
    expect(env.scale).toBeCloseTo(1, 5);
    expect(env.arrival).toBeCloseTo(0, 5); // 0 = settled
  });
  it('clamps past the end', () => {
    const env = coalescenceEnvelope(OPENING_TIMINGS.coalescenceMs + 5000);
    expect(env.opacity).toBeCloseTo(1, 5);
    expect(env.arrival).toBeCloseTo(0, 5);
  });
});

describe('ignitionPulse', () => {
  it('is 0 at start, 0 at end, and peaks near the ignition time', () => {
    expect(ignitionPulse(0)).toBeCloseTo(0, 5);
    expect(ignitionPulse(OPENING_TIMINGS.coalescenceMs)).toBeCloseTo(0, 5);
    const peak = ignitionPulse(OPENING_TIMINGS.ignitionPeakMs);
    expect(peak).toBeGreaterThan(0.9);
  });
});

describe('awakenNotice', () => {
  it('rises from 0 to 1 over the notice window then holds', () => {
    expect(awakenNotice(0)).toBeCloseTo(0, 5);
    expect(awakenNotice(OPENING_TIMINGS.awakenNoticeMs)).toBeCloseTo(1, 5);
    expect(awakenNotice(OPENING_TIMINGS.awakenNoticeMs * 4)).toBeCloseTo(1, 5);
  });
});

describe('shouldReduceMotion', () => {
  it('returns true when the media query matches', () => {
    expect(shouldReduceMotion({ matchMedia: () => ({ matches: true }) } as unknown as Window)).toBe(true);
  });
  it('returns false when it does not match', () => {
    expect(shouldReduceMotion({ matchMedia: () => ({ matches: false }) } as unknown as Window)).toBe(false);
  });
  it('returns false when matchMedia is unavailable (SSR-safe)', () => {
    expect(shouldReduceMotion(undefined)).toBe(false);
  });
});

describe('isAwakeningTrigger (user spoke -> awakening)', () => {
  it('maps a directive event to an awakening trigger', () => {
    expect(isAwakeningTrigger({ type: 'directive', source: 'voice' })).toBe(true);
    expect(isAwakeningTrigger({ type: 'directive', source: 'hud' })).toBe(true);
  });
  it('ignores ambient/system events', () => {
    expect(isAwakeningTrigger({ type: 'burst', source: 'scene' })).toBe(false);
    expect(isAwakeningTrigger({ type: 'synthesis', source: 'idle' })).toBe(false);
    expect(isAwakeningTrigger(null)).toBe(false);
  });
});
```

- [ ] Run the test and confirm it FAILS (module not found / exports missing): `cd frontend && npm run test -- src/superbrain/lib/openingMotion.test.ts` — expected FAIL.
- [ ] Implement `frontend/src/superbrain/lib/openingMotion.ts` with the complete content below — minimal real code, reduced-motion path lives in the SAME module, transform/opacity/filter scalars only.

```ts
// openingMotion.ts — PURE timing/easing helpers for P1 "The Opening".
// No three.js, no React: unit-testable in isolation. Every value here is a
// transform/opacity/filter scalar consumed by the scene's frame loop.

import { OPENING_TIMINGS, OPENING_EASING, COALESCENCE_SCALE_FLOOR } from './openingTokens';
import type { CognitionEvent } from './cognitionBus';

/** Solve a CSS-style cubic-bezier(p1x,p1y,p2x,p2y) for y at a given x in
 *  [0,1] (Newton + bisection fallback). Endpoints (0,0) and (1,1) implied. */
export function cubicBezier(p1x: number, p1y: number, p2x: number, p2y: number): (x: number) => number {
  const cx = 3 * p1x;
  const bx = 3 * (p2x - p1x) - cx;
  const ax = 1 - cx - bx;
  const cy = 3 * p1y;
  const by = 3 * (p2y - p1y) - cy;
  const ay = 1 - cy - by;
  const sampleX = (t: number) => ((ax * t + bx) * t + cx) * t;
  const sampleY = (t: number) => ((ay * t + by) * t + cy) * t;
  const slopeX = (t: number) => (3 * ax * t + 2 * bx) * t + cx;
  return (x: number) => {
    if (x <= 0) return 0;
    if (x >= 1) return 1;
    let t = x;
    for (let i = 0; i < 8; i++) {
      const d = sampleX(t) - x;
      if (Math.abs(d) < 1e-6) return sampleY(t);
      const s = slopeX(t);
      if (Math.abs(s) < 1e-6) break;
      t -= d / s;
    }
    let lo = 0;
    let hi = 1;
    t = x;
    while (lo < hi) {
      const cur = sampleX(t);
      if (Math.abs(cur - x) < 1e-6) break;
      if (cur < x) lo = t;
      else hi = t;
      t = (lo + hi) / 2;
    }
    return sampleY(t);
  };
}

const easeCoalescence = cubicBezier(...OPENING_EASING.coalescence);
const easeNotice = cubicBezier(...OPENING_EASING.notice);

const clamp01 = (v: number) => (v < 0 ? 0 : v > 1 ? 1 : v);

export interface CoalescenceEnvelope {
  /** Cortex opacity 0 -> 1. */
  opacity: number;
  /** Cortex scale floor -> 1 (never starts at 0). */
  scale: number;
  /** 1 = fully arriving, 0 = settled. Shaders gate inflow/pull off this. */
  arrival: number;
}

/** Eased coalescence state at elapsed ms since arrival start. */
export function coalescenceEnvelope(elapsedMs: number): CoalescenceEnvelope {
  const p = easeCoalescence(clamp01(elapsedMs / OPENING_TIMINGS.coalescenceMs));
  return {
    opacity: p,
    scale: COALESCENCE_SCALE_FLOOR + (1 - COALESCENCE_SCALE_FLOOR) * p,
    arrival: 1 - p,
  };
}

/** Single-shot ignition pulse (0 -> 1 -> 0), peaking at ignitionPeakMs. */
export function ignitionPulse(elapsedMs: number): number {
  const peak = OPENING_TIMINGS.ignitionPeakMs;
  const span = OPENING_TIMINGS.coalescenceMs;
  if (elapsedMs <= 0 || elapsedMs >= span) return 0;
  const rise = clamp01(elapsedMs / peak);
  const fall = clamp01((span - elapsedMs) / (span - peak));
  // Asymmetric bell: fast bright ignition, gentle settle.
  return Math.pow(rise, 1.4) * Math.pow(fall, 0.8);
}

/** Attentive "notice" 0 -> 1 over the notice window, then held at 1. */
export function awakenNotice(elapsedMs: number): number {
  return easeNotice(clamp01(elapsedMs / OPENING_TIMINGS.awakenNoticeMs));
}

/** prefers-reduced-motion decision — SSR-safe, lives WITH the motion code. */
export function shouldReduceMotion(win: Window | undefined = typeof window !== 'undefined' ? window : undefined): boolean {
  if (!win || typeof win.matchMedia !== 'function') return false;
  return win.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/** THE SIGNAL: a user-issued directive (typed or voice) is the awakening
 *  trigger. Ambient/system events (burst/synthesis/idle) never wake it. */
export function isAwakeningTrigger(event: CognitionEvent | null | undefined): boolean {
  return !!event && event.type === 'directive';
}
```

- [ ] Run the test and confirm it PASSES: `cd frontend && npm run test -- src/superbrain/lib/openingMotion.test.ts` — expected PASS.
- [ ] NOTE: if `CognitionEvent` is not an exported type of `cognitionBus.ts`, define a minimal local `interface AwakenableEvent { type: string; source?: string }` in `openingMotion.ts` and type the param as that instead — confirm against the real export when implementing (the explore map says cognitionBus uses `{ type, label, source }` events).
- [ ] Commit: add both files, `git commit -m "P1: pure opening-motion helpers (TDD)"` with the Co-Authored-By trailer.

---

### Task 3 (TDD): Lifecycle / posture state machine

**Files:**
- Create: `frontend/src/superbrain/lib/lifecycleStateMachine.ts`
- Test: `frontend/src/superbrain/lib/lifecycleStateMachine.test.ts`

- [ ] Write the failing test file `frontend/src/superbrain/lib/lifecycleStateMachine.test.ts` with the complete content below. Tests cover the pure derivation, the speak→ATTENTIVE mapping, decay timers, and the subscriber singleton (using `vi.useFakeTimers` for `performance.now`).

```ts
import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  LifecycleState,
  ArrivalMode,
  deriveNextState,
  getElapsedInState,
  __resetLifecycleForTests,
  getLifecycleSnapshot,
  subscribeLifecycle,
  transitionToArriving,
  notifyDirective,
  tickLifecycle,
  DEFAULT_LIFECYCLE_CONFIG,
  type LifecycleSnapshot,
} from './lifecycleStateMachine';

const baseSnapshot = (over: Partial<LifecycleSnapshot> = {}): LifecycleSnapshot => ({
  state: LifecycleState.REST,
  arrivalMode: undefined,
  elapsedInState: 0,
  lastTransitionAt: 0,
  directiveCount: 0,
  ...over,
});

describe('deriveNextState (pure)', () => {
  const cfg = DEFAULT_LIFECYCLE_CONFIG;

  it('BOOTING stays BOOTING until an explicit transition', () => {
    const r = deriveNextState(1000, baseSnapshot({ state: LifecycleState.BOOTING }), null, cfg);
    expect(r.state).toBe(LifecycleState.BOOTING);
  });

  it('ARRIVING -> REST after arrivalDurationMs', () => {
    const snap = baseSnapshot({ state: LifecycleState.ARRIVING, lastTransitionAt: 0, arrivalMode: ArrivalMode.COALESCENCE });
    const r = deriveNextState(cfg.arrivalDurationMs + 1, snap, null, cfg);
    expect(r.state).toBe(LifecycleState.REST);
  });

  it('ARRIVING stays ARRIVING before the duration (cinematic priority, ignores directive)', () => {
    const snap = baseSnapshot({ state: LifecycleState.ARRIVING, lastTransitionAt: 0 });
    const r = deriveNextState(500, snap, { type: 'directive' }, cfg);
    expect(r.state).toBe(LifecycleState.ARRIVING);
  });

  it('REST -> ATTENTIVE on a directive event', () => {
    const r = deriveNextState(1000, baseSnapshot(), { type: 'directive' }, cfg);
    expect(r.state).toBe(LifecycleState.ATTENTIVE);
  });

  it('REST ignores ambient events', () => {
    const r = deriveNextState(1000, baseSnapshot(), { type: 'burst' }, cfg);
    expect(r.state).toBe(LifecycleState.REST);
  });

  it('ATTENTIVE -> REST after attentiveDecayMs of silence', () => {
    const snap = baseSnapshot({ state: LifecycleState.ATTENTIVE, lastTransitionAt: 0 });
    const r = deriveNextState(cfg.attentiveDecayMs + 1, snap, null, cfg);
    expect(r.state).toBe(LifecycleState.REST);
  });
});

describe('getElapsedInState', () => {
  it('returns now minus lastTransitionAt', () => {
    expect(getElapsedInState(1500, baseSnapshot({ lastTransitionAt: 500 }))).toBe(1000);
  });
});

describe('singleton + subscribers', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(0);
    __resetLifecycleForTests();
  });

  it('starts in BOOTING and notifies new subscribers immediately', () => {
    const seen: LifecycleState[] = [];
    const unsub = subscribeLifecycle((s) => seen.push(s.state));
    expect(seen).toEqual([LifecycleState.BOOTING]);
    unsub();
  });

  it('transitionToArriving moves to ARRIVING with the given mode', () => {
    transitionToArriving(ArrivalMode.COALESCENCE);
    expect(getLifecycleSnapshot().state).toBe(LifecycleState.ARRIVING);
    expect(getLifecycleSnapshot().arrivalMode).toBe(ArrivalMode.COALESCENCE);
  });

  it('arriving auto-settles to REST after the duration on tick', () => {
    transitionToArriving(ArrivalMode.COALESCENCE);
    vi.setSystemTime(DEFAULT_LIFECYCLE_CONFIG.arrivalDurationMs + 10);
    tickLifecycle();
    expect(getLifecycleSnapshot().state).toBe(LifecycleState.REST);
  });

  it('a directive in REST wakes the being to ATTENTIVE and counts it', () => {
    transitionToArriving(ArrivalMode.COALESCENCE);
    vi.setSystemTime(DEFAULT_LIFECYCLE_CONFIG.arrivalDurationMs + 10);
    tickLifecycle();
    notifyDirective();
    expect(getLifecycleSnapshot().state).toBe(LifecycleState.ATTENTIVE);
    expect(getLifecycleSnapshot().directiveCount).toBe(1);
  });
});
```

- [ ] NOTE on the timers test: the module reads time via `performance.now()`; `vi.useFakeTimers()` shims `performance.now` in jsdom. If a case sees real time, switch those cases to inject time through the pure `deriveNextState(at, ...)` entrypoint (already covered) — the singleton cases are a convenience, the pure derivation is the contract.
- [ ] Run the test and confirm it FAILS: `cd frontend && npm run test -- src/superbrain/lib/lifecycleStateMachine.test.ts` — expected FAIL.
- [ ] Implement `frontend/src/superbrain/lib/lifecycleStateMachine.ts` with the complete content below. Mirrors the `cognitionBus.ts` pub/sub pattern (module `Set` of listeners, exception isolation, unsubscribe fn).

```ts
// lifecycleStateMachine.ts — the being's posture (P1: BOOTING -> ARRIVING ->
// REST <-> ATTENTIVE). Pure derivation + a cognitionBus-style singleton.
// No three.js: the scene SUBSCRIBES and drives uniforms off the snapshot.

import { OPENING_TIMINGS } from './openingTokens';
import type { CognitionEvent } from './cognitionBus';

export enum LifecycleState {
  BOOTING = 'booting',
  ARRIVING = 'arriving',
  REST = 'rest',
  ATTENTIVE = 'attentive',
}

export enum ArrivalMode {
  COALESCENCE = 'coalescence',
  AWAKENING = 'awakening',
}

export interface LifecycleSnapshot {
  state: LifecycleState;
  arrivalMode?: ArrivalMode;
  /** ms since this state was entered (filled by tick/derive helpers). */
  elapsedInState: number;
  /** performance.now() (or injected now) when the current state began. */
  lastTransitionAt: number;
  /** Directives received this session (0 = first awakening is still ahead). */
  directiveCount: number;
}

export interface LifecycleConfig {
  /** ARRIVING auto-settles to REST after this (ms). */
  arrivalDurationMs: number;
  /** ATTENTIVE eases back to REST after this much silence (ms). */
  attentiveDecayMs: number;
}

export const DEFAULT_LIFECYCLE_CONFIG: LifecycleConfig = {
  arrivalDurationMs: OPENING_TIMINGS.coalescenceMs,
  attentiveDecayMs: OPENING_TIMINGS.attentiveDecayMs,
};

const now = (): number => (typeof performance !== 'undefined' ? performance.now() : Date.now());

export function getElapsedInState(at: number, snapshot: LifecycleSnapshot): number {
  return at - snapshot.lastTransitionAt;
}

export interface DerivedState {
  state: LifecycleState;
  arrivalMode?: ArrivalMode;
  reason: string;
}

/** PURE: next state given current snapshot + (optional) event + config. */
export function deriveNextState(
  at: number,
  snapshot: LifecycleSnapshot,
  event: CognitionEvent | null,
  config: LifecycleConfig,
): DerivedState {
  if (snapshot.state === LifecycleState.BOOTING) {
    return { state: LifecycleState.BOOTING, reason: 'boot_in_progress' };
  }
  if (snapshot.state === LifecycleState.ARRIVING) {
    if (getElapsedInState(at, snapshot) >= config.arrivalDurationMs) {
      return { state: LifecycleState.REST, reason: 'arrival_complete' };
    }
    return { state: LifecycleState.ARRIVING, arrivalMode: snapshot.arrivalMode, reason: 'arrival_in_progress' };
  }
  if (snapshot.state === LifecycleState.ATTENTIVE) {
    if (getElapsedInState(at, snapshot) >= config.attentiveDecayMs) {
      return { state: LifecycleState.REST, reason: 'attentive_decay' };
    }
    return { state: LifecycleState.ATTENTIVE, reason: 'attentive_in_progress' };
  }
  // REST
  if (event && event.type === 'directive') {
    return { state: LifecycleState.ATTENTIVE, reason: 'directive_received' };
  }
  return { state: LifecycleState.REST, reason: 'steady_state' };
}

/* ---------- singleton (cognitionBus pattern) ---------- */

let config: LifecycleConfig = { ...DEFAULT_LIFECYCLE_CONFIG };
let snapshot: LifecycleSnapshot = {
  state: LifecycleState.BOOTING,
  arrivalMode: undefined,
  elapsedInState: 0,
  lastTransitionAt: now(),
  directiveCount: 0,
};

type Listener = (snapshot: Readonly<LifecycleSnapshot>) => void;
const listeners = new Set<Listener>();

function emit(): void {
  for (const listener of listeners) {
    try {
      listener(snapshot);
    } catch {
      // One faulty listener must never sever the rest.
    }
  }
}

export function getLifecycleSnapshot(): Readonly<LifecycleSnapshot> {
  return snapshot;
}

export function subscribeLifecycle(listener: Listener): () => void {
  listeners.add(listener);
  listener(snapshot); // immediate, like cognitionBus consumers expect
  return () => {
    listeners.delete(listener);
  };
}

function setState(next: DerivedState, directiveDelta: number): void {
  if (next.state === snapshot.state && directiveDelta === 0) return;
  const at = now();
  snapshot = {
    state: next.state,
    arrivalMode: next.state === LifecycleState.ARRIVING ? (next.arrivalMode ?? snapshot.arrivalMode) : undefined,
    elapsedInState: 0,
    lastTransitionAt: at,
    directiveCount: snapshot.directiveCount + directiveDelta,
  };
  emit();
}

/** BootSequence calls this on fade-out to begin the opening cinematic. */
export function transitionToArriving(mode: ArrivalMode): void {
  const at = now();
  snapshot = {
    state: LifecycleState.ARRIVING,
    arrivalMode: mode,
    elapsedInState: 0,
    lastTransitionAt: at,
    directiveCount: snapshot.directiveCount,
  };
  emit();
}

/** The "user spoke" signal: a directive wakes the being. Ignored unless in
 *  REST (ARRIVING keeps cinematic priority; ATTENTIVE is already awake). */
export function notifyDirective(): void {
  setState(deriveNextState(now(), snapshot, { type: 'directive' }, config), 1);
}

/** Heartbeat: recompute elapsed + run decay timers. Cheap; skips if idle. */
export function tickLifecycle(): void {
  if (listeners.size === 0) return;
  const at = now();
  snapshot.elapsedInState = getElapsedInState(at, snapshot);
  setState(deriveNextState(at, snapshot, null, config), 0);
}

/** Test-only: reset the singleton between cases. */
export function __resetLifecycleForTests(): void {
  config = { ...DEFAULT_LIFECYCLE_CONFIG };
  listeners.clear();
  snapshot = {
    state: LifecycleState.BOOTING,
    arrivalMode: undefined,
    elapsedInState: 0,
    lastTransitionAt: now(),
    directiveCount: 0,
  };
}
```

- [ ] Run the test and confirm it PASSES: `cd frontend && npm run test -- src/superbrain/lib/lifecycleStateMachine.test.ts` — expected PASS.
- [ ] Run the full gates to confirm baseline stays green: `cd frontend && npm run test && npm run typecheck && npm run lint` — expected PASS, test count = 80 + the new cases.
- [ ] Commit: add both files, `git commit -m "P1: lifecycle posture state machine (TDD)"` with the Co-Authored-By trailer.

---

### Task 4: Wire the BootSequence → ARRIVING handoff and the speak → ATTENTIVE bridge (logic only, gates stay green)

This connects the (already-green) state machine to the existing boot + cognition flow WITHOUT touching any visual yet, so the next task's browser proof is purely additive.

**Files:**
- Modify: `frontend/src/superbrain/components/ui/BootSequence.tsx`
- Modify: `frontend/src/superbrain/components/canvas/WorkspaceCanvas.tsx`

- [ ] In `BootSequence.tsx`, import the machine near the existing `import { publishCognition } from '@/lib/cognitionBus';` (~line 19): add `import { transitionToArriving, ArrivalMode } from '@/lib/lifecycleStateMachine';`.
- [ ] In `BootSequence.tsx`, inside the `phase === 'fade'` branch of the finale effect (after the existing `publishCognition({ type: 'synthesis', label: 'SUPERMIND ONLINE', ... })`, ~lines 209–215), drive the machine into the opening — first-ever load coalesces (A), a return awakens (C). Detect first-ever via a localStorage flag (sovereignty-safe try/catch like the existing `readStoredSky`):

```ts
// The kernel is online — begin the being's opening. First-ever load on this
// device coalesces (A); a return awakens (C). Reduced-motion is honored by
// the scene (it renders the settled REST state immediately).
let firstEver = true;
try {
  firstEver = window.localStorage.getItem('gag-has-arrived-v1') === null;
  window.localStorage.setItem('gag-has-arrived-v1', '1');
} catch {
  // Private mode: treat as first-ever (coalescence) — the richer opening.
}
transitionToArriving(firstEver ? ArrivalMode.COALESCENCE : ArrivalMode.AWAKENING);
```

- [ ] In `WorkspaceCanvas.tsx`, import near the other lib imports (~after line 18): `import { notifyDirective, tickLifecycle } from '@/lib/lifecycleStateMachine';` and (if not already imported) `import { subscribeCognition } from '@/lib/cognitionBus';`.
- [ ] In `WorkspaceInner`, add an effect (after the existing `__gagCognition` effect, ~line 174) that bridges the directive signal into the machine and runs the decay heartbeat:

```ts
// THE SIGNAL bridge: a user directive (typed or voice) wakes the being.
// A light heartbeat advances the posture machine's decay timers. The scene
// subscribes to the machine directly; this component only feeds it.
useEffect(() => {
  const unsub = subscribeCognition((event) => {
    if (event.type === 'directive') notifyDirective();
  });
  const heartbeat = window.setInterval(() => tickLifecycle(), 50);
  return () => {
    unsub();
    window.clearInterval(heartbeat);
  };
}, []);
```

- [ ] Run the gates (no visual change yet, so 80/80 must still hold): `cd frontend && npm run test && npm run typecheck && npm run lint` — expected PASS.
- [ ] Commit: `git add` the two files, `git commit -m "P1: wire boot->arriving and directive->attentive into lifecycle"` with the Co-Authored-By trailer.

---

### Task 5: Coalescence + ignition + settle (and the AWAKENING return variant) — FIRST BROWSER-PROVABLE MILESTONE

Add `uArrival`/`uIgnite`/`uAwaken` uniform leaves driven from the lifecycle snapshot + the pure envelopes. Gate brain scale/opacity, accretion inflow, and starfield funnel off `uArrival`. The reduced-motion path lives in the SAME frame logic (renders settled REST immediately). Milestone the operator signs off: **brain coalesces → settles → breathes** at the dev URL.

> Line numbers below are from the explore map and are INDICATIVE — open the file and place each edit at the matching construct (uniform interface, `createCognitionUniforms`, the root `useFrame`, `BrainModel`'s `useFrame`). Confirm the exact ref/uniform names in-file before editing.

**Files:**
- Modify: `frontend/src/superbrain/components/canvas/SuperbrainScene.tsx`
- Modify: `frontend/src/superbrain/components/canvas/AccretionCore.tsx`
- Modify: `frontend/src/superbrain/components/canvas/CosmicBackground.tsx`
- Modify: `frontend/src/superbrain/components/canvas/NeuralAura.tsx`

- [ ] In `SuperbrainScene.tsx`, extend the `CognitionUniforms` interface (after `uHold`, ~line 158) with three new leaves:

```ts
  /** Coalescence/awakening: 1 = arriving (field streaming in), 0 = settled. */
  uArrival: { value: number };
  /** Single-shot ignition pulse during coalescence, 0..1. */
  uIgnite: { value: number };
  /** First-speak attentive notice, 0..1 (drives cortex brighten + nerve light). */
  uAwaken: { value: number };
```

- [ ] In `createCognitionUniforms()` (after `uHold: { value: 0 }`, ~line 175) add the matching defaults — defaulting to the SETTLED state so any path that never animates (reduced-motion, tests) reads as REST:

```ts
  uArrival: { value: 0 },
  uIgnite: { value: 0 },
  uAwaken: { value: 0 },
```

- [ ] In `SuperbrainScene.tsx`, add imports near line 13: `import { subscribeLifecycle, LifecycleState, ArrivalMode } from '@/lib/lifecycleStateMachine';` and `import { coalescenceEnvelope, ignitionPulse, awakenNotice, shouldReduceMotion } from '@/lib/openingMotion';`.
- [ ] In the `SuperbrainScene` component body (after the `holdRef` ref, ~line 1015), add a posture ref, a reduced-motion flag (captured once), a shared arrival scalar ref, and the subscription:

```ts
// The being's posture, mirrored into a ref so the frame loop reads it
// without re-rendering. Reduced-motion is captured once and honored in the
// SAME frame logic below (no second code path, no auto-degrade of the look).
const reducedMotionRef = useRef(shouldReduceMotion());
const arrivalScalarRef = useRef(0); // shared with AccretionCore/CosmicBackground/NeuralAura
const postureRef = useRef({
  state: LifecycleState.BOOTING as LifecycleState,
  mode: ArrivalMode.COALESCENCE as ArrivalMode,
  enteredAt: 0,
});
useEffect(
  () =>
    subscribeLifecycle((snap) => {
      postureRef.current.state = snap.state;
      if (snap.arrivalMode) postureRef.current.mode = snap.arrivalMode;
      postureRef.current.enteredAt = performance.now();
    }),
  [],
);
```

- [ ] In the root `useFrame` of `SuperbrainScene` (~line 1136), immediately after `uniforms.uTime.value = time;` (~line 1166), compute and write the opening envelopes. Reduced-motion clamps straight to the settled targets. COALESCENCE streams in + ignites; AWAKENING (return) starts the cortex dim and lights from a seed (distinct beat). `uAwaken` (the first-speak notice) eases toward its target so it retargets / never blocks input:

```ts
/* ── opening envelopes: coalescence/awaken drive shader-side reveals ── */
const posture = postureRef.current;
const sinceState = performance.now() - posture.enteredAt;
let arrivalTarget = 0;
let igniteTarget = 0;
let awakenTarget = 0;
if (posture.state === LifecycleState.ARRIVING) {
  if (reducedMotionRef.current) {
    // Reduced-motion: skip the streaming coalescence; show settled REST now.
    arrivalTarget = 0;
    igniteTarget = 0;
  } else {
    const env = coalescenceEnvelope(sinceState);
    arrivalTarget = env.arrival;
    // Both arrival modes ignite from a seed; COALESCENCE also streams the
    // field in (uArrival > 0 drives the accretion inflow + star funnel).
    igniteTarget = ignitionPulse(sinceState);
  }
} else if (posture.state === LifecycleState.ATTENTIVE) {
  awakenTarget = reducedMotionRef.current ? 1 : awakenNotice(sinceState);
}
uniforms.uArrival.value = arrivalTarget;
uniforms.uIgnite.value = igniteTarget;
arrivalScalarRef.current = arrivalTarget;
// State-driven, interruptible (design law for the reaction).
uniforms.uAwaken.value = THREE.MathUtils.damp(uniforms.uAwaken.value, awakenTarget, 6, delta);
```

- [ ] In `BrainModel`'s `useFrame` (the scale line, ~849), fold the coalescence opacity/scale + attentive brighten in. Replace the existing scale assignment with:

```ts
const arrivalScale = THREE.MathUtils.lerp(1, /*floor*/0.85, uniforms.uArrival.value);
const scale = BRAIN_SCALE * (1 + uniforms.uBreath.value * 0.006) * arrivalScale
  + activity * 0.05 + burstPow * 0.15 + uniforms.uAwaken.value * 0.04;
```

- [ ] In `BrainModel`'s `useFrame`, make the cortex fade in with coalescence opacity AND dim-then-light for the AWAKENING return. Where the cortex material opacity / emissive is set, multiply opacity by the eased reveal and dip brightness while `uArrival` is high (so AWAKENING reads as "dark → lights up", COALESCENCE as "condenses into light"). Use the existing material handle; add:

```ts
// Reveal: opacity follows coalescence; the cortex is dimmer while arriving
// (a dormant being lighting up) and snaps to full canon emission at rest.
const reveal = 1 - uniforms.uArrival.value;          // 0 -> 1 across arrival
cortexMaterial.opacity = Math.max(cortexMaterial.opacity, reveal);
cortexMaterial.transparent = true;
// uIgnite adds the single-shot seed flash (NOT a loop).
const ignite = uniforms.uIgnite.value;
```

(Apply `reveal`/`ignite` to the existing rim/emissive gains rather than introducing a new material; confirm the cortex material variable name in-file.)

- [ ] In `BrainModel`'s `useFrame`, scale the existing `CURSOR_ATTENTION` lean by `uAwaken` so a fresh awakening leans a touch harder, then eases back — interruptible. Inside the `if (CURSOR_ATTENTION)` block, replace the two `groupRef.current.rotation.y/x +=` lines with:

```ts
        const awakenLean = 1 + uniforms.uAwaken.value * 0.6;
        groupRef.current.rotation.y += attend.x * 0.035 * awakenLean;
        groupRef.current.rotation.x += -attend.y * 0.022 * awakenLean;
```

- [ ] In `AccretionCore.tsx`, thread `uArrival`. Change the signature to accept `arrival: MutableRefObject<number>` (alongside `activity`, `burst`); add `uArrival: { value: 0 }` to the `uniforms` useMemo; in `useFrame` set `diskMaterialRef.current.uniforms.uArrival.value = arrival.current;`; declare `uniform float uArrival;` in the shader and multiply the inflow `vAlpha` by `(1.0 + uArrival * 0.8)` so motes read as streaming in, settling to canon when `uArrival` → 0. Update the mount in `SuperbrainScene.tsx` to `<AccretionCore activity={activeBoost} burst={burstRef} arrival={arrivalScalarRef} />`.
- [ ] In `CosmicBackground.tsx`, thread `uArrival` into the funnel. Accept `arrival?: MutableRefObject<number>`; add `uArrival: { value: 0 }` to the uniforms; register it in `onBeforeCompile`; declare `uniform float uArrival;` in the vertex `#include <common>`; gate the pull: `float pull = smoothstep(25.0, 2.0, distToCenter) * (0.25 + 0.75 * uArrival);` so stars funnel hard inward during coalescence and relax to canon drift-by once settled; in `Starfield`'s `useFrame` set `uniforms.uArrival.value = arrival?.current ?? 0;`. Update the mount to `<CosmicBackground tier={tier} arrival={arrivalScalarRef} />`.
- [ ] In `NeuralAura.tsx`, fade the shells in during arrival. Accept the same `arrival` ref pattern; add `uArrival`; declare `uniform float uArrival;` in the shell shaders; multiply shell output alpha by `(1.0 - uArrival)` so the membrane/nucleus emerge as the cortex condenses and are at full canon strength at rest. Mount: `<NeuralAura ... arrival={arrivalScalarRef} />`.
- [ ] In `SuperbrainScene.tsx`, suppress autonomous thought-waves during the opening. In the cognitionBus subscriber (~line 1023) add at the top of the listener: `if (postureRef.current.state === LifecycleState.ARRIVING) return;`. In the auto-wave scheduler (~line 1199) add `&& postureRef.current.state !== LifecycleState.ARRIVING` to the auto-fire guard.
- [ ] In `SuperbrainScene.tsx`, hold off idle attract-mode until REST. In the idle input effect (~line 1107) initialise `idle.lastInputMs = Number.POSITIVE_INFINITY;`, and in the root `useFrame` idle block (~line 1205) stamp real "now" only once posture is REST: `if (postureRef.current.state === LifecycleState.REST && idle.lastInputMs === Number.POSITIVE_INFINITY) idle.lastInputMs = performance.now();`.
- [ ] **BROWSER-PROOF CHECKPOINT (BEFORE / canon baseline)** — on the current build with NO P1 changes (`git stash` or a clean `feat/renovation-p0` checkout) run `cd frontend && npm run dev`, open `http://localhost:5173`, capture `before-arrival-postboot.png` (t≈2.7s, just after boot unmounts) and `before-rest.png` (t≈6s, resting brain). These are the canon the change must not damage.
- [ ] **BROWSER-PROOF CHECKPOINT (AFTER / coalescence)** — on the P1 branch, `npm run dev`, open `:5173`, clear the `gag-has-arrived-v1` localStorage key to force first-ever, reload. Capture: (1) t≈2.7s boot unmounts → starfield funnels inward + accretion motes stream in (brighter than canon), cortex ~0.85 scale + low opacity; (2) t≈4–5s ignition pulse peaks (single-shot brighten, NOT a loop) as cortex scales to 1.0 + full opacity; (3) t≈6s REST: centered brain breathing on the ~5s cycle, starfield relaxed to canon, no throbbing rings. Save `after-arrival-postboot.png`, `after-ignition.png`, `after-rest.png`. Confirm REST is pixel-identical to `before-rest.png` (arrival is purely additive).
- [ ] **BROWSER-PROOF CHECKPOINT (AFTER / awakening return)** — with `gag-has-arrived-v1` already set (return load), reload. Confirm the distinct C beat: the cortex starts DIM/dormant and lights from a seed (ignition) outward to full canon emission, no field-streaming required to read as "it woke." Save `after-awakening-arrival.png`.
- [ ] **BROWSER-PROOF CHECKPOINT (reduced-motion)** — in DevTools enable "Emulate prefers-reduced-motion: reduce", hard-reload. Confirm coalescence/funnel is SKIPPED and the being appears already settled at REST (final state preserved), breath continues but no large-scale streaming/zoom. Save `after-rest-reduced-motion.png`.
- [ ] **OPERATOR SIGN-OFF GATE** — present BEFORE/AFTER pairs (post-boot, ignition, rest, awakening-return, reduced-motion) in HIS browser. Do NOT mark done until he confirms the look and that the canon REST frame is untouched.
- [ ] Run the gates: `cd frontend && npm run test && npm run typecheck && npm run lint` — expected PASS (80/80 + new cases).
- [ ] Commit: `git add` the four scene files, `git commit -m "P1: coalescence + ignition + settle (and awakening-return) driven by lifecycle"` with the Co-Authored-By trailer.

---

### Task 6: Brainstem-at-rest — the spinal cord present (spec State 2)

The spec puts the spinal cord in P1: at rest it reads as a short brainstem descending from the cortex, brain + cord one body (it extends into the conductor spine in P4). This is net-new, additive geometry parented to the brain group so it breathes/leans with the being and fades in with `uArrival`.

**Files:**
- Create: `frontend/src/superbrain/components/canvas/Brainstem.tsx`
- Modify: `frontend/src/superbrain/components/canvas/SuperbrainScene.tsx`

- [ ] Create `frontend/src/superbrain/components/canvas/Brainstem.tsx` with the content below — a short tapered cord descending from the cortex base, emissive in the canon palette (violet→cyan), fading in with arrival. It takes the shared `arrival` ref so it reveals with the cortex.

```tsx
import { useMemo, useRef, type MutableRefObject } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';

/** The spinal cord present at rest: a short tapered brainstem descending from
 *  the cortex base. Part of the being's body (parented to the brain group),
 *  so it breathes/leans with it. Fades in with arrival; in P4 this same cord
 *  extends downward into the conductor spine. Additive — canon look at rest
 *  is unchanged when no tabs exist. */
export default function Brainstem({
  arrival,
  baseY = -2.0,
  length = 1.1,
}: {
  arrival: MutableRefObject<number>;
  /** Local-Y of the cortex base where the stem attaches (tune in browser). */
  baseY?: number;
  /** Stem length in local units (short at rest). */
  length?: number;
}) {
  const matRef = useRef<THREE.MeshStandardMaterial>(null);

  // Tapered nub: wider where it meets the cortex, narrowing downward.
  const geometry = useMemo(() => {
    const g = new THREE.CylinderGeometry(0.16, 0.07, length, 20, 1, true);
    g.translate(0, baseY - length / 2, 0);
    return g;
  }, [baseY, length]);

  useFrame(() => {
    if (!matRef.current) return;
    // Reveal with the cortex: invisible while the field is still streaming in,
    // full canon emission at rest. No loop of its own (breath comes from the
    // parent group's scale).
    const reveal = 1 - arrival.current;
    matRef.current.opacity = reveal;
    matRef.current.emissiveIntensity = 0.9 * reveal;
  });

  return (
    <mesh geometry={geometry}>
      <meshStandardMaterial
        ref={matRef}
        color={'#5b6bd6'}
        emissive={'#5ad8e6'}
        emissiveIntensity={0.9}
        transparent
        opacity={0}
        roughness={0.4}
        metalness={0.0}
        side={THREE.DoubleSide}
      />
    </mesh>
  );
}
```

- [ ] In `SuperbrainScene.tsx`, import it: `import Brainstem from './Brainstem';`. Mount it INSIDE the brain group (the same group that owns `groupRef` / `BRAIN_SCALE` in `BrainModel`) so it inherits breath + lean, passing the shared arrival ref: `<Brainstem arrival={arrivalScalarRef} />`. (Confirm the in-group mount point; if `BrainModel` is a separate component, add the `<Brainstem/>` as a child of its returned `<group ref={groupRef}>`.)
- [ ] **BROWSER-PROOF CHECKPOINT** — `cd frontend && npm run dev`, `:5173`. Confirm at REST a short luminous brainstem descends from the cortex base, breathes/leans WITH the brain (not detached), and during arrival it fades in with the cortex (absent while the field streams in). Tune `baseY`/`length` so it reads as "attached anatomy," not a stick. Capture `before-rest.png` (no stem, from Task 5) vs `after-brainstem-rest.png`.
- [ ] **OPERATOR SIGN-OFF GATE** — confirm in his browser that the brainstem reads as part of the body (the spinal cord present), per the spec emphasis. Adjust palette/offset to his eye before marking done.
- [ ] Run the gates: `cd frontend && npm run test && npm run typecheck && npm run lint` — expected PASS.
- [ ] Commit: `git add` the new + modified file, `git commit -m "P1: brainstem-at-rest — the spinal cord present (anatomy)"` with the Co-Authored-By trailer.

---

### Task 7: First awakening on speak — attentive lean + cortex brighten + staggered nerve-lighting

The state machine + `uAwaken` are already wired (Tasks 3–5). This makes the visual reaction land: cortex brighten and a frontal thought-wave on the FIRST directive, plus staggered nerve-lighting, all state-driven and interruptible.

**Files:**
- Modify: `frontend/src/superbrain/components/canvas/SuperbrainScene.tsx`
- Modify: `frontend/src/superbrain/components/canvas/NervousSystem.tsx`

- [ ] In `SuperbrainScene.tsx`, fire a single frontal awakening thought-wave the first time the being wakes. In the cognitionBus subscriber's `directive` branch (~line 1048), after the existing intensity bump, queue a wave from the frontal/CAUSAL anchor (reuse the existing `waveOriginForLabel('CAUSAL DECISION', waves.random)` helper):

```ts
          // First contact: the being NOTICES — a wave breaks from the frontal
          // (planning) anchor as it leans in. Subsequent directives still
          // surge the wires (above) but don't re-fire the "first notice".
          const waves = waveRef.current;
          if (waves.pending.length < 3) {
            waves.pending.push(waveOriginForLabel('CAUSAL DECISION', waves.random));
          }
```

- [ ] In `SuperbrainScene.tsx`, feed the attentive brighten into the cortex via the existing rim/SSS gains in the root `useFrame` (after the `uRimGain`/`uSssScale` writes, ~lines 1176–1177):

```ts
// Awakening brighten: the cortex lifts a touch while attentive, eased by the
// state-driven uAwaken (already retargeting), then settles back to canon.
uniforms.uRimGain.value *= 1 + uniforms.uAwaken.value * 0.22;
uniforms.uSssScale.value *= 1 + uniforms.uAwaken.value * 0.15;
```

- [ ] In `NervousSystem.tsx`, light the nerves outward in a stagger on awakening. Add a `uAwaken` uniform to the nerve `ShaderMaterial` (sourced from the shared `uniforms` prop); bake a per-tube `aDelay` attribute (0..1 along bundle order); in the fragment shader declare `uniform float uAwaken;`, compute `float lit = smoothstep(aDelay, aDelay + 0.12, uAwaken);` and multiply the nerve emission by `(0.6 + 0.4 * lit)` (the 0.12 window yields the ~`nerveStaggerMs` visual stagger). Wire `mat.uniforms.uAwaken.value = uniforms.uAwaken.value;` in the existing frame loop.
- [ ] **BROWSER-PROOF CHECKPOINT** — capture `before-awakening.png` (resting brainstem + nerves). Then `npm run dev`, `:5173`, let it reach REST and SPEAK to it (use the existing command path, or the dev hook `window.__gagCognition({ type: 'directive', label: 'hello', source: 'hud' })`). Capture AFTER at the notice (~300ms): cortex brighter, brain leaning attentively, nerves lighting outward in a visible stagger, a single frontal thought-wave. Save `after-awakening-notice.png` + `after-awakening-settle.png` (~5s later, eased back to REST). Confirm it is interruptible: a second directive / pointer move retargets smoothly without a hard cut.
- [ ] **BROWSER-PROOF CHECKPOINT (reduced-motion)** — with prefers-reduced-motion emulated, speak again. Confirm the awakening is an INSTANT state change (cortex brightened + nerves lit immediately, no eased ramp). Save `after-awakening-reduced-motion.png`.
- [ ] **OPERATOR SIGN-OFF GATE** — present BEFORE/AFTER awakening pairs in his browser. Do NOT mark done without his confirming the lean + brighten + nerve-light reads as "it noticed me" and the canon REST frame is unharmed.
- [ ] Run the gates: `cd frontend && npm run test && npm run typecheck && npm run lint` — expected PASS.
- [ ] Commit: `git add` the two files, `git commit -m "P1: first awakening on speak — attentive lean, cortex brighten, staggered nerve-lighting"` with the Co-Authored-By trailer.

---

### Task 8: Accessibility, pause-ambient affordance, and final P1 verification

**Files:**
- Modify: `frontend/src/superbrain/lib/lifecycleStateMachine.ts`
- Test: `frontend/src/superbrain/lib/lifecycleStateMachine.test.ts` (extend)
- Modify: `frontend/src/superbrain/components/canvas/SuperbrainScene.tsx`

- [ ] (TDD) In `lifecycleStateMachine.test.ts`, add a failing test: after `__resetLifecycleForTests()`, subscribing then `setAmbientPaused(true)` flips `getLifecycleSnapshot().ambientPaused` to true and notifies listeners; `setAmbientPaused(false)` restores it. Run `cd frontend && npm run test -- src/superbrain/lib/lifecycleStateMachine.test.ts` — expected FAIL.
- [ ] Implement `setAmbientPaused(paused: boolean)` + an `ambientPaused: boolean` field on `LifecycleSnapshot` (default false), emitting on change, in `lifecycleStateMachine.ts` (and reset it in `__resetLifecycleForTests`). Run the test — expected PASS. This is the design-required "way to pause ambient motion (voyage/breath)".
- [ ] In `SuperbrainScene.tsx`, honor `ambientPaused` in the root `useFrame`: when true, freeze the breath (hold `uBreath` at its current value, like the existing hold path) and stop advancing `idle.yaw`. Mirror the flag into `postureRef` in the `subscribeLifecycle` callback.
- [ ] Confirm keyboard reachability + visible focus of the intake: verify the existing in-scene/command input is reachable by Tab and shows a focus ring (spec requires the intake be keyboard-reachable). If the only reachable control is still the retiring HUD path, leave it for P1 (HUD retirement is P2) but confirm focus is NOT trapped by the canvas — note this explicitly for the operator. (Code change only if focus is broken: add `tabIndex` + a `:focus-visible` outline to the intake affordance.)
- [ ] **FULL GATES** — `cd frontend && npm run test && npm run typecheck && npm run lint` — expected PASS; test count = original 80 + all P1 cases, zero failures (80/80 baseline preserved, no auto-degrade anywhere).
- [ ] **FINAL BROWSER-PROOF** — `cd frontend && npm run dev`; capture the full P1 reel in HIS browser: arrival (coalescence→ignition→settle) → awakening-return variant → REST (breathing brain + brainstem) → first awakening on speak, plus the reduced-motion variant and the ambient-pause toggle. Assemble all BEFORE/AFTER pairs.
- [ ] **OPERATOR SIGN-OFF GATE (P1 ship)** — present the complete reel + before/after set for the operator's final P1 approval in his browser (P1 is the trust proof, reviewed before P2). Do not consider P1 done until he signs off.
- [ ] Commit: `git add` the changed files, `git commit -m "P1: ambient-pause affordance + accessibility + final verification"` with the Co-Authored-By trailer.

---

## Spec coverage (self-review)

| Spec P1 requirement | Covered by |
|---|---|
| Arrival — coalescence (A, first load) | Tasks 4, 5 |
| Arrival — awakening (C, every return), distinct dormant→seed beat | Tasks 4, 5 (AWAKENING branch + checkpoint) |
| Rest — centered, breathing, voyaging | Task 5 (settle), existing breath/voyage |
| Rest — spinal cord present as short brainstem (brain+cord one body) | **Task 6** |
| First awakening on speak (attentive lean + cortex brighten + nerves light) | Tasks 4, 5, 7 |
| The being notices the user (attention) | Task 5 (lean), Task 7 |
| Nerve-as-status / staggered nerve-lighting | Task 7 |
| Transitions are continuous / interruptible | Tasks 5, 7 (state-driven damp, no fixed keyframes) |
| prefers-reduced-motion (skip large-scale, settled state) | Tasks 2, 5, 7 (same-code path) |
| Pause ambient motion (voyage/breath) | Task 8 |
| No gratuitous looping pulses (motion gotcha) | Honored throughout (only the breath loops; ignition/awaken are single-shot/eased) |
| FIDELITY: proof in his browser, before/after, no auto-degrade, canon untouched, gates green | Browser-proof + operator-sign-off gates in Tasks 5–8; gate runs every task |

**Deferred to later phases (out of P1 scope):** HUD retirement / status-fully-off-the-body (P2); materialization of tabs (P3); the conductor spine + orchestration (P4); reabsorption (P5). The brainstem here is anatomy-at-rest only; it extends into the conductor spine in P4.
