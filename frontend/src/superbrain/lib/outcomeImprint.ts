import { useEffect, useState } from 'react';
import { subscribeCognition, type CognitionEvent } from './cognitionBus';

export type OutcomeImprintKind = 'none' | 'verified' | 'scar' | 'accepted';

export interface OutcomeImprintSignals {
  kind: OutcomeImprintKind;
  stampedAt: number;
  label: string;
  detail: string;
  sequence: number;
}

export interface OutcomeImprintSnapshot {
  kind: OutcomeImprintKind;
  intensity: number;
  ringOpacity: number;
  scarOpacity: number;
  rootGlow: number;
  surfaceGlow: number;
  tint: string;
  label: string;
  detail: string;
  changedAt: number;
}

export const REST_OUTCOME_IMPRINT: OutcomeImprintSnapshot = {
  kind: 'none',
  intensity: 0,
  ringOpacity: 0,
  scarOpacity: 0,
  rootGlow: 0,
  surfaceGlow: 0,
  tint: '#79ebff',
  label: '',
  detail: '',
  changedAt: 0,
};

const WINDOW_MS: Record<Exclude<OutcomeImprintKind, 'none'>, number> = {
  verified: 6200,
  accepted: 4200,
  scar: 7800,
};

const TINT: Record<OutcomeImprintKind, string> = {
  none: '#79ebff',
  verified: '#8dffd1',
  accepted: '#a9fff3',
  scar: '#ff5f7a',
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

export function createOutcomeImprintSignals(): OutcomeImprintSignals {
  return {
    kind: 'none',
    stampedAt: Number.NEGATIVE_INFINITY,
    label: '',
    detail: '',
    sequence: 0,
  };
}

function classifyOutcome(event: CognitionEvent): OutcomeImprintKind | null {
  const label = String(event.label ?? '');
  const detail = String(event.detail ?? '');
  const text = `${label} ${detail}`;

  if (event.type === 'knowledge-acquired' && /VERIFICATION GREEN|SKILL MASTERED/i.test(text)) return 'verified';
  if (event.type === 'knowledge-acquired' && /VERIFICATION RED/i.test(text)) return 'scar';
  if (event.type === 'synthesis' && /FAULT|ERROR|FAIL/i.test(text)) return 'scar';
  if (event.type === 'approval-resolved' && /rejected/i.test(text)) return 'scar';
  if (event.type === 'approval-resolved' && /approved/i.test(text)) return 'accepted';
  return null;
}

export function reduceOutcomeImprintEvent(
  signals: OutcomeImprintSignals,
  event: CognitionEvent,
  now: number,
): OutcomeImprintSignals {
  const kind = classifyOutcome(event);
  if (!kind) return signals;

  return {
    kind,
    stampedAt: now,
    label: String(event.label ?? ''),
    detail: String(event.detail ?? ''),
    sequence: signals.sequence + 1,
  };
}

function profile(kind: OutcomeImprintKind, intensity: number): OutcomeImprintSnapshot {
  if (kind === 'none') return REST_OUTCOME_IMPRINT;

  const i = round4(clamp01(intensity));
  const isScar = kind === 'scar';
  const isVerified = kind === 'verified';

  return {
    kind,
    intensity: i,
    ringOpacity: round4((isVerified ? 0.28 : kind === 'accepted' ? 0.18 : 0.1) * i),
    scarOpacity: round4((isScar ? 0.46 : 0.1) * i),
    rootGlow: round4((isScar ? 0.7 : isVerified ? 0.68 : 0.38) * i),
    surfaceGlow: round4((isScar ? 0.12 : isVerified ? 0.15 : 0.1) * i),
    tint: TINT[kind],
    label: '',
    detail: '',
    changedAt: 0,
  };
}

export function deriveOutcomeImprintSnapshot(
  signals: OutcomeImprintSignals,
  now: number,
): OutcomeImprintSnapshot {
  if (signals.kind === 'none') return REST_OUTCOME_IMPRINT;

  const windowMs = WINDOW_MS[signals.kind];
  const age = now - signals.stampedAt;
  if (age < 0 || age > windowMs) return REST_OUTCOME_IMPRINT;

  const falloff = 1 - age / windowMs;
  const shaped = signals.kind === 'scar' ? 0.18 + falloff * 0.82 : Math.pow(falloff, 0.72);
  return {
    ...profile(signals.kind, shaped),
    label: signals.label,
    detail: signals.detail,
    changedAt: signals.stampedAt,
  };
}

type OutcomeImprintListener = (snapshot: OutcomeImprintSnapshot) => void;

let signals = createOutcomeImprintSignals();
let currentSnapshot = REST_OUTCOME_IMPRINT;
let cognitionUnsubscribe: (() => void) | null = null;
let tickHandle: number | null = null;
const listeners = new Set<OutcomeImprintListener>();

function publishSnapshot(): void {
  currentSnapshot = deriveOutcomeImprintSnapshot(signals, nowMs());
  for (const listener of listeners) listener(currentSnapshot);
}

function ensureCognitionSubscription(): void {
  if (cognitionUnsubscribe) return;
  cognitionUnsubscribe = subscribeCognition((event) => {
    signals = reduceOutcomeImprintEvent(signals, event, nowMs());
    publishSnapshot();
  });
}

export function getOutcomeImprintSnapshot(): OutcomeImprintSnapshot {
  currentSnapshot = deriveOutcomeImprintSnapshot(signals, nowMs());
  return currentSnapshot;
}

export function subscribeOutcomeImprint(listener: OutcomeImprintListener): () => void {
  ensureCognitionSubscription();
  listeners.add(listener);
  listener(getOutcomeImprintSnapshot());
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

export function useOutcomeImprint(): OutcomeImprintSnapshot {
  const [imprint, setImprint] = useState(getOutcomeImprintSnapshot);
  useEffect(() => subscribeOutcomeImprint(setImprint), []);
  return imprint;
}
