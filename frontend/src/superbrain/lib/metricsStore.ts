/**
 * metricsStore — single source of truth for every live metric on screen.
 *
 * The brain's region callouts and the HUD's intake rows MUST display the same
 * number for the same channel; two readouts disagreeing is the fastest way to
 * prove the numbers are painted on. Everything subscribes here.
 *
 * The store idles with a gentle drift around each base value and reacts to
 * cognitionBus 'knowledge-acquired' events with a bump that eases back.
 * SSR-safe: the ticker starts lazily in the browser; the server snapshot is
 * the static base values, so hydration always matches.
 */

import { useSyncExternalStore } from 'react';
import { subscribeCognition } from './cognitionBus';

export type MetricKey = 'research' | 'memory' | 'tools' | 'signals';

export const METRIC_BASES: Record<MetricKey, number> = {
  research: 93,
  memory: 89,
  tools: 78,
  signals: 83,
};

const METRIC_KEYS = Object.keys(METRIC_BASES) as MetricKey[];

/** Semantic routing of a knowledge-acquired label to its metric channel, by what
 *  the event MEANS. (BUG-B: the old `label.includes(key)` over the metric KEYS
 *  never matched a real label like "VERIFICATION GREEN" or "trail #N reinforced",
 *  so every bump silently round-robined.) Returns null for an unrecognized label. */
const METRIC_ROUTES: ReadonlyArray<readonly [RegExp, MetricKey]> = [
  [/verif|build|\bcode\b|create|edit|exec|\brun\b|test|compile|tool/i, 'tools'],
  [/recall|memory|skill|trail|master|capab|lesson|reflect|knowledge/i, 'memory'],
  [/research|read|search|archive|web|fetch|grep|inspect|list|mythos/i, 'research'],
  [/signal|route|synth|telemetr|intent|autonom|titan|delta/i, 'signals'],
];

export function routeMetric(label: string): MetricKey | null {
  for (const [re, key] of METRIC_ROUTES) if (re.test(label)) return key;
  return null;
}

type Snapshot = Record<MetricKey, number>;

/** Live base values the ticker drifts around. Defaults to the demo lore
 *  numbers; the AI-OS adapter overwrites them with REAL series so the same
 *  drift/bump animation suddenly tells the truth. */
const bases: Snapshot = { ...METRIC_BASES };

/** True while the adapter's link is up. Online, the idle drift is zeroed —
 *  the displayed number only moves on real polls and real acquisition
 *  bumps. Offline, the demo imagination keeps its gentle wander. */
let linkUp = false;

export function setMetricLink(up: boolean): void {
  linkUp = up;
}

/** Real history per channel (one sample per successful adapter poll), the
 *  truth source for the HUD sparklines. Arrays are replaced, not mutated,
 *  so useSyncExternalStore sees referential change. */
const HISTORY_MAX = 8;
let history: Record<MetricKey, number[]> = {
  research: [],
  memory: [],
  tools: [],
  signals: [],
};

export function getMetricHistory(): Record<MetricKey, number[]> {
  return history;
}

/** Point the metric channels at real data (NaN/undefined entries ignored). */
export function setMetricBases(next: Partial<Record<MetricKey, number>>): void {
  let historyChanged = false;
  const nextHistory = { ...history };
  for (const key of METRIC_KEYS) {
    const value = next[key];
    if (typeof value === 'number' && Number.isFinite(value)) {
      bases[key] = Math.round(Math.max(5, Math.min(99, value)));
      nextHistory[key] = [...nextHistory[key], bases[key]].slice(-HISTORY_MAX);
      historyChanged = true;
    }
  }
  if (historyChanged) {
    history = nextHistory;
    emit();
  }
}

let current: Snapshot = { ...METRIC_BASES };
/** Transient offsets from acquisition bumps; eased back toward 0 each tick. */
const bumps: Record<MetricKey, number> = { research: 0, memory: 0, tools: 0, signals: 0 };
const listeners = new Set<() => void>();

let tickerStarted = false;
let rotation = 0;
let tickerInterval: number | null = null;
let cognitionUnsubscribe: (() => void) | null = null;

function emit() {
  for (const listener of listeners) listener();
}

function startTicker() {
  if (tickerStarted || typeof window === 'undefined') return;
  tickerStarted = true;

  tickerInterval = window.setInterval(() => {
    const next: Snapshot = { ...current };
    for (const key of METRIC_KEYS) {
      bumps[key] *= 0.82; // acquisition bumps ease back to baseline
      // Online the number is REAL — it moves only on polls and bumps.
      // Offline the demo imagination keeps its gentle wander.
      const drift = linkUp ? 0 : (Math.random() - 0.5) * 1.6;
      const target = bases[key] + bumps[key] + drift;
      next[key] = Math.round(Math.max(1, Math.min(99, target)));
    }
    current = next;
    emit();
  }, 1800);

  cognitionUnsubscribe = subscribeCognition((event) => {
    if (event.type !== 'knowledge-acquired') return;
    // Route the bump to the channel the event MEANS; rotate only as a genuine
    // fallback for an unrecognized label (BUG-B fix — see routeMetric).
    const key = routeMetric(event.label ?? '') ?? METRIC_KEYS[rotation++ % METRIC_KEYS.length];
    bumps[key] += 2.5 + (event.intensity ?? 0.5) * 1.5;
  });
}

function stopTicker() {
  if (!tickerStarted) return;
  if (tickerInterval !== null) {
    window.clearInterval(tickerInterval);
    tickerInterval = null;
  }
  if (cognitionUnsubscribe) {
    cognitionUnsubscribe();
    cognitionUnsubscribe = null;
  }
  tickerStarted = false;
}

export function subscribeMetrics(listener: () => void): () => void {
  if (listeners.size === 0) startTicker();
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0) stopTicker();
  };
}

export function getMetricsSnapshot(): Snapshot {
  return current;
}

function getServerSnapshot(): Snapshot {
  return METRIC_BASES;
}

/** React hook — one live value, identical everywhere it is displayed. */
export function useMetric(key: MetricKey): number {
  const snapshot = useSyncExternalStore(subscribeMetrics, getMetricsSnapshot, getServerSnapshot);
  return snapshot[key];
}

const EMPTY_HISTORY: number[] = [];

function getServerHistory(): Record<MetricKey, number[]> {
  return { research: EMPTY_HISTORY, memory: EMPTY_HISTORY, tools: EMPTY_HISTORY, signals: EMPTY_HISTORY };
}

/** React hook — the channel's REAL sample history (one point per poll). */
export function useMetricHistory(key: MetricKey): number[] {
  const snapshot = useSyncExternalStore(subscribeMetrics, getMetricHistory, getServerHistory);
  return snapshot[key];
}
