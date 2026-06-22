import { useEffect, useState } from 'react';
import { subscribeCognition, type CognitionEvent } from './cognitionBus';
import { postureHex, type BodyPostureKey } from './bodyPosture';

export type TurnMetabolismPhase = 'rest' | 'thinking' | 'working' | 'approval' | 'error' | 'settling';

export interface TurnMetabolismSignals {
  thinkingAt: number;
  workingAt: number;
  approvalAt: number;
  settlingAt: number;
  errorAt: number;
  approvalHeld: boolean;
}

export interface TurnMetabolismSnapshot {
  phase: TurnMetabolismPhase;
  intensity: number;
  surfaceExcitation: number;
  rootExcitation: number;
  breathGain: number;
  tint: string;
  held: boolean;
  changedAt: number;
}

export const REST_TURN_METABOLISM: TurnMetabolismSnapshot = {
  phase: 'rest',
  intensity: 0,
  surfaceExcitation: 0,
  rootExcitation: 0,
  breathGain: 0,
  tint: postureHex('rest'), // single source (was a hardcoded #79ebff drift)
  held: false,
  changedAt: 0,
};

const WINDOWS_MS: Record<Exclude<TurnMetabolismPhase, 'rest' | 'approval'>, number> = {
  thinking: 2400,
  working: 3600,
  error: 4600,
  settling: 1800,
};

// SINGLE SOURCE (P2.4): the metabolism tint is the sacred posture tetrad, mapped
// by intent — NOT a parallel hex map (the old one had drifted off the poster:
// rest/thinking were cyan instead of purple, working orange instead of the
// poster's "working = cyan", settling cyan instead of green). bodyPosture.postureHex
// is the one truth; this map only chooses WHICH posture each turn-phase wears.
const PHASE_POSTURE: Record<TurnMetabolismPhase, BodyPostureKey> = {
  rest: 'rest', // purple
  thinking: 'think', // purple
  working: 'stream', // cyan — the poster's "working" hue
  approval: 'hold', // orange — holding for the operator
  error: 'error', // orange-red
  settling: 'complete', // green
};
const PHASE_TINT: Record<TurnMetabolismPhase, string> = {
  rest: postureHex(PHASE_POSTURE.rest),
  thinking: postureHex(PHASE_POSTURE.thinking),
  working: postureHex(PHASE_POSTURE.working),
  approval: postureHex(PHASE_POSTURE.approval),
  error: postureHex(PHASE_POSTURE.error),
  settling: postureHex(PHASE_POSTURE.settling),
};

function nowMs(): number {
  return typeof performance !== 'undefined' ? performance.now() : Date.now();
}

function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value));
}

function round4(value: number): number {
  return Math.round(value * 10000) / 10000;
}

export function createTurnMetabolismSignals(): TurnMetabolismSignals {
  return {
    thinkingAt: Number.NEGATIVE_INFINITY,
    workingAt: Number.NEGATIVE_INFINITY,
    approvalAt: Number.NEGATIVE_INFINITY,
    settlingAt: Number.NEGATIVE_INFINITY,
    errorAt: Number.NEGATIVE_INFINITY,
    approvalHeld: false,
  };
}

function isErrorEvent(event: CognitionEvent): boolean {
  const label = String(event.label ?? '');
  const detail = String(event.detail ?? '');
  if (event.type === 'knowledge-acquired' && /VERIFICATION RED/i.test(label)) return true;
  if (event.type === 'synthesis' && /FAULT|ERROR|FAIL/i.test(`${label} ${detail}`)) return true;
  if (event.type === 'approval-resolved' && /rejected/i.test(label)) return true;
  return false;
}

export function reduceTurnMetabolismEvent(
  signals: TurnMetabolismSignals,
  event: CognitionEvent,
  now: number,
): TurnMetabolismSignals {
  const next = { ...signals };

  if (isErrorEvent(event)) {
    next.errorAt = now;
    next.approvalHeld = false;
    return next;
  }

  switch (event.type) {
    case 'approval-required':
      next.approvalAt = now;
      next.approvalHeld = true;
      break;
    case 'approval-resolved':
      next.approvalHeld = false;
      next.settlingAt = now;
      break;
    case 'directive':
    case 'route':
    case 'voice-speaking':
      next.thinkingAt = now;
      next.approvalHeld = false;
      break;
    case 'agent-dispatch':
      next.workingAt = now;
      break;
    case 'knowledge-acquired':
      next.workingAt = now;
      break;
    case 'synthesis':
      next.approvalHeld = false;
      next.settlingAt = now;
      break;
    default:
      break;
  }

  return next;
}

function ageStrength(now: number, then: number, windowMs: number): number {
  const age = now - then;
  if (age < 0 || age > windowMs) return 0;
  return 1 - age / windowMs;
}

function snapshot(
  phase: TurnMetabolismPhase,
  intensity: number,
  changedAt: number,
  held = false,
): TurnMetabolismSnapshot {
  const i = round4(clamp01(intensity));
  const profile = {
    rest: { surface: 0, root: 0, breath: 0 },
    thinking: { surface: 0.24, root: 0.2, breath: 0.12 },
    working: { surface: 0.55, root: 0.7, breath: 0.32 },
    approval: { surface: 0.68, root: 0.78, breath: -0.18 },
    error: { surface: 0.72, root: 0.56, breath: 0.22 },
    settling: { surface: 0.2, root: 0.16, breath: 0.08 },
  }[phase];

  return {
    phase,
    intensity: i,
    surfaceExcitation: round4(profile.surface * i),
    rootExcitation: round4(profile.root * i),
    breathGain: round4(profile.breath * i),
    tint: PHASE_TINT[phase],
    held,
    changedAt,
  };
}

export function deriveTurnMetabolismSnapshot(
  signals: TurnMetabolismSignals,
  now: number,
): TurnMetabolismSnapshot {
  if (signals.approvalHeld) {
    return snapshot('approval', 1, signals.approvalAt, true);
  }

  const error = ageStrength(now, signals.errorAt, WINDOWS_MS.error);
  if (error > 0) return snapshot('error', 0.42 + error * 0.58, signals.errorAt);

  const working = ageStrength(now, signals.workingAt, WINDOWS_MS.working);
  if (working > 0) return snapshot('working', 0.35 + working * 0.65, signals.workingAt);

  const thinking = ageStrength(now, signals.thinkingAt, WINDOWS_MS.thinking);
  if (thinking > 0) return snapshot('thinking', 0.28 + thinking * 0.52, signals.thinkingAt);

  const settling = ageStrength(now, signals.settlingAt, WINDOWS_MS.settling);
  if (settling > 0) return snapshot('settling', 0.22 + settling * 0.32, signals.settlingAt);

  return REST_TURN_METABOLISM;
}

type MetabolismListener = (snapshot: TurnMetabolismSnapshot) => void;

let signals = createTurnMetabolismSignals();
let currentSnapshot = REST_TURN_METABOLISM;
let cognitionUnsubscribe: (() => void) | null = null;
let tickHandle: number | null = null;
const listeners = new Set<MetabolismListener>();

function publishSnapshot(): void {
  currentSnapshot = deriveTurnMetabolismSnapshot(signals, nowMs());
  for (const listener of listeners) listener(currentSnapshot);
}

function ensureCognitionSubscription(): void {
  if (cognitionUnsubscribe) return;
  cognitionUnsubscribe = subscribeCognition((event) => {
    signals = reduceTurnMetabolismEvent(signals, event, nowMs());
    publishSnapshot();
  });
}

export function getTurnMetabolismSnapshot(): TurnMetabolismSnapshot {
  currentSnapshot = deriveTurnMetabolismSnapshot(signals, nowMs());
  return currentSnapshot;
}

export function subscribeTurnMetabolism(listener: MetabolismListener): () => void {
  ensureCognitionSubscription();
  listeners.add(listener);
  listener(getTurnMetabolismSnapshot());
  if (tickHandle === null && typeof window !== 'undefined') {
    tickHandle = window.setInterval(publishSnapshot, 250);
  }
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0 && tickHandle !== null && typeof window !== 'undefined') {
      window.clearInterval(tickHandle);
      tickHandle = null;
    }
  };
}

export function useTurnMetabolism(): TurnMetabolismSnapshot {
  const [metabolism, setMetabolism] = useState(getTurnMetabolismSnapshot);
  useEffect(() => subscribeTurnMetabolism(setMetabolism), []);
  return metabolism;
}
