import { useEffect, useState } from 'react';
import type { CognitionEvent } from './cognitionBus';
import type { MaterializedTabRecord } from './tabStore';

export type CompletionReflexState = 'idle' | 'settling' | 'reabsorbing' | 'held';
export type CompletionReflexOutcome = 'verified' | 'accepted' | 'scar';

export interface CompletionReflexSignals {
  state: CompletionReflexState;
  outcome: CompletionReflexOutcome | null;
  stampedAt: number;
  reabsorbedAt: number;
  targetId: string | null;
  targetKind: MaterializedTabRecord['kind'] | null;
  targetSeatIndex: number | null;
  targetOriginLocal: [number, number, number] | null;
  targetTargetLocal: [number, number, number] | null;
  label: string;
  detail: string;
  sequence: number;
}

export interface CompletionReflexSnapshot {
  state: CompletionReflexState;
  outcome: CompletionReflexOutcome | null;
  targetId: string | null;
  targetKind: MaterializedTabRecord['kind'] | null;
  targetSeatIndex: number | null;
  targetOriginLocal: [number, number, number] | null;
  targetTargetLocal: [number, number, number] | null;
  intensity: number;
  settleProgress: number;
  beadProgress: number;
  memoryOpacity: number;
  reabsorbReady: boolean;
  hold: boolean;
  tint: string;
  label: string;
  detail: string;
  changedAt: number;
  sequence: number;
}

export const COMPLETION_SETTLE_MS = 1200;
export const COMPLETION_REABSORB_AFTER_MS = 1800;
export const COMPLETION_BEAD_TRAVEL_MS = 3400;
export const COMPLETION_MEMORY_WINDOW_MS = 5200;
export const COMPLETION_HOLD_WINDOW_MS = 7800;

export const REST_COMPLETION_REFLEX: CompletionReflexSnapshot = {
  state: 'idle',
  outcome: null,
  targetId: null,
  targetKind: null,
  targetSeatIndex: null,
  targetOriginLocal: null,
  targetTargetLocal: null,
  intensity: 0,
  settleProgress: 0,
  beadProgress: 0,
  memoryOpacity: 0,
  reabsorbReady: false,
  hold: false,
  tint: '#79ebff',
  label: '',
  detail: '',
  changedAt: 0,
  sequence: 0,
};

const TINT: Record<CompletionReflexOutcome, string> = {
  verified: '#8dffd1',
  accepted: '#a9fff3',
  scar: '#ff5f7a',
};

function nowMs(): number {
  return typeof performance !== 'undefined' && typeof performance.now === 'function' ? performance.now() : Date.now();
}

function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value));
}

function easing(value: number): number {
  return value * value * (3 - 2 * value);
}

function round4(value: number): number {
  return Math.round(value * 10000) / 10000;
}

function isResetEvent(event: CognitionEvent): boolean {
  if (event.type === 'directive' || event.type === 'agent-dispatch') return true;
  return event.type === 'knowledge-acquired' && /CODE EMITTED/i.test(String(event.label ?? ''));
}

function classifyCompletionOutcome(event: CognitionEvent): CompletionReflexOutcome | null {
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

function resetSignals(sequence: number): CompletionReflexSignals {
  return {
    state: 'idle',
    outcome: null,
    stampedAt: Number.NEGATIVE_INFINITY,
    reabsorbedAt: Number.NEGATIVE_INFINITY,
    targetId: null,
    targetKind: null,
    targetSeatIndex: null,
    targetOriginLocal: null,
    targetTargetLocal: null,
    label: '',
    detail: '',
    sequence,
  };
}

function isEligibleTarget(tab: MaterializedTabRecord | null): tab is MaterializedTabRecord {
  return Boolean(tab && tab.kind !== 'input' && tab.lifecycle !== 'retracting');
}

export function createCompletionReflexSignals(): CompletionReflexSignals {
  return resetSignals(0);
}

export function reduceCompletionReflexEvent(
  signals: CompletionReflexSignals,
  event: CognitionEvent,
  focusedTab: MaterializedTabRecord | null,
  now: number,
): CompletionReflexSignals {
  if (isResetEvent(event)) return resetSignals(signals.sequence + 1);

  const outcome = classifyCompletionOutcome(event);
  if (!outcome || !isEligibleTarget(focusedTab)) return signals;

  return {
    state: outcome === 'scar' ? 'held' : 'settling',
    outcome,
    stampedAt: now,
    reabsorbedAt: Number.NEGATIVE_INFINITY,
    targetId: focusedTab.id,
    targetKind: focusedTab.kind,
    targetSeatIndex: focusedTab.seatIndex,
    targetOriginLocal: focusedTab.originLocal,
    targetTargetLocal: focusedTab.targetLocal,
    label: String(event.label ?? ''),
    detail: String(event.detail ?? ''),
    sequence: signals.sequence + 1,
  };
}

export function markCompletionReflexSignalsReabsorbing(
  signals: CompletionReflexSignals,
  targetId: string,
  now: number,
): CompletionReflexSignals {
  if (signals.state !== 'settling' || signals.targetId !== targetId || signals.outcome === 'scar') return signals;
  return {
    ...signals,
    state: 'reabsorbing',
    reabsorbedAt: now,
    sequence: signals.sequence + 1,
  };
}

export function deriveCompletionReflexSnapshot(
  signals: CompletionReflexSignals,
  now: number,
): CompletionReflexSnapshot {
  if (signals.state === 'idle' || !signals.outcome || !signals.targetId) {
    return { ...REST_COMPLETION_REFLEX, sequence: signals.sequence };
  }

  const age = now - signals.stampedAt;
  if (age < 0) return { ...REST_COMPLETION_REFLEX, sequence: signals.sequence };

  if (signals.state === 'held') {
    if (age > COMPLETION_HOLD_WINDOW_MS) return { ...REST_COMPLETION_REFLEX, sequence: signals.sequence };
    const falloff = 1 - age / COMPLETION_HOLD_WINDOW_MS;
    return {
      state: 'held',
      outcome: signals.outcome,
      targetId: signals.targetId,
      targetKind: signals.targetKind,
      targetSeatIndex: signals.targetSeatIndex,
      targetOriginLocal: signals.targetOriginLocal,
      targetTargetLocal: signals.targetTargetLocal,
      intensity: round4(0.24 + falloff * 0.76),
      settleProgress: 0,
      beadProgress: 0,
      memoryOpacity: 0,
      reabsorbReady: false,
      hold: true,
      tint: TINT.scar,
      label: signals.label,
      detail: signals.detail,
      changedAt: signals.stampedAt,
      sequence: signals.sequence,
    };
  }

  const memoryLimit =
    signals.state === 'reabsorbing' && Number.isFinite(signals.reabsorbedAt)
      ? Math.max(COMPLETION_MEMORY_WINDOW_MS, signals.reabsorbedAt - signals.stampedAt + 2200)
      : COMPLETION_MEMORY_WINDOW_MS;

  if (age > memoryLimit) return { ...REST_COMPLETION_REFLEX, sequence: signals.sequence };

  const settleProgress = easing(clamp01(age / COMPLETION_SETTLE_MS));
  const beadProgress = easing(clamp01(age / COMPLETION_BEAD_TRAVEL_MS));
  const fadeOut = clamp01((memoryLimit - age) / 1500);
  const fadeIn = clamp01(age / 360);
  const memoryOpacity = round4(fadeIn * fadeOut * (signals.state === 'reabsorbing' ? 0.9 : 0.62));
  const reabsorbReady =
    signals.state === 'settling' &&
    signals.targetKind !== 'input' &&
    signals.outcome !== 'scar' &&
    age >= COMPLETION_REABSORB_AFTER_MS;

  return {
    state: signals.state,
    outcome: signals.outcome,
    targetId: signals.targetId,
    targetKind: signals.targetKind,
    targetSeatIndex: signals.targetSeatIndex,
    targetOriginLocal: signals.targetOriginLocal,
    targetTargetLocal: signals.targetTargetLocal,
    intensity: round4((0.28 + (1 - clamp01(age / memoryLimit)) * 0.72) * fadeIn),
    settleProgress: round4(settleProgress),
    beadProgress: round4(beadProgress),
    memoryOpacity,
    reabsorbReady,
    hold: false,
    tint: TINT[signals.outcome],
    label: signals.label,
    detail: signals.detail,
    changedAt: signals.stampedAt,
    sequence: signals.sequence,
  };
}

type CompletionReflexListener = (snapshot: CompletionReflexSnapshot) => void;

let signals = createCompletionReflexSignals();
let currentSnapshot = REST_COMPLETION_REFLEX;
let tickHandle: number | null = null;
const listeners = new Set<CompletionReflexListener>();

function publishSnapshot(): void {
  currentSnapshot = deriveCompletionReflexSnapshot(signals, nowMs());
  for (const listener of listeners) listener(currentSnapshot);
}

export function ingestCompletionReflexEvent(
  event: CognitionEvent,
  focusedTab: MaterializedTabRecord | null,
  now = nowMs(),
): void {
  signals = reduceCompletionReflexEvent(signals, event, focusedTab, now);
  publishSnapshot();
}

export function markCompletionReflexReabsorbing(targetId: string, now = nowMs()): void {
  signals = markCompletionReflexSignalsReabsorbing(signals, targetId, now);
  publishSnapshot();
}

export function getCompletionReflexSnapshot(): CompletionReflexSnapshot {
  currentSnapshot = deriveCompletionReflexSnapshot(signals, nowMs());
  return currentSnapshot;
}

export function subscribeCompletionReflex(listener: CompletionReflexListener): () => void {
  listeners.add(listener);
  listener(getCompletionReflexSnapshot());
  if (tickHandle === null && typeof window !== 'undefined') {
    tickHandle = window.setInterval(publishSnapshot, 200);
  }
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0 && tickHandle !== null && typeof window !== 'undefined') {
      window.clearInterval(tickHandle);
      tickHandle = null;
    }
  };
}

export function useCompletionReflex(): CompletionReflexSnapshot {
  const [reflex, setReflex] = useState(getCompletionReflexSnapshot);
  useEffect(() => subscribeCompletionReflex(setReflex), []);
  return reflex;
}

export function __resetCompletionReflexForTests(): void {
  signals = createCompletionReflexSignals();
  currentSnapshot = REST_COMPLETION_REFLEX;
  listeners.clear();
  if (tickHandle !== null && typeof window !== 'undefined') {
    window.clearInterval(tickHandle);
    tickHandle = null;
  }
}
