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

// Use Date.now() so vi.setSystemTime() shims correctly in tests. The scene's
// frame loop reads performance.now() directly when computing sinceState — the
// singleton only needs consistent relative time, not high-res monotonic time.
const now = (): number => Date.now();

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

/** Heartbeat: recompute elapsed + run decay timers. Cheap; skips if no
 *  listeners AND the state is already at rest (nothing to decay). */
export function tickLifecycle(): void {
  const at = now();
  snapshot.elapsedInState = getElapsedInState(at, snapshot);
  const next = deriveNextState(at, snapshot, null, config);
  if (next.state === snapshot.state && listeners.size === 0) return;
  setState(next, 0);
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
