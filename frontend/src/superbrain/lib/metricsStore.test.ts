import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
  METRIC_BASES,
  getMetricsSnapshot,
  isMetricLinkUp,
  routeMetric,
  setMetricBases,
  setMetricLink,
  subscribeMetrics,
} from './metricsStore';

type Snapshot = ReturnType<typeof getMetricsSnapshot>;

/**
 * The store used to keep an idle `(Math.random() - 0.5) * 1.6` wander that ran
 * only while the adapter's link was DOWN. A gauge that invents motion while the
 * backend is unreachable lies at exactly the moment the operator is trying to
 * tell whether anything is alive, so the wander was removed.
 *
 * These tests pin that by behaviour rather than by grepping for `Math.random`:
 * they drive the real 1800ms ticker with fake timers and assert the readout
 * holds still, then that it still moves for the two things that are real.
 */
describe('metricsStore holds still when nothing real happened', () => {
  let unsubscribe: () => void;

  beforeEach(() => {
    vi.useFakeTimers();
    setMetricLink(false);
    setMetricBases({ ...METRIC_BASES });
    // Subscribing is what starts the ticker; the store is lazy by design.
    unsubscribe = subscribeMetrics(() => {});
  });

  afterEach(() => {
    unsubscribe();
    vi.useRealTimers();
  });

  /**
   * Sample EVERY tick, not just the last one.
   *
   * The old wander was +-0.8 around an integer base, so any single tick had a
   * ~62% chance of rounding back to the starting value -- checking only the
   * final snapshot passes by luck about one run in seven. Measured: with the
   * drift restored, a final-snapshot-only assertion passed. Comparing all 20
   * samples makes a false pass ~0.625^80.
   */
  function samplesOver(ticks: number): Snapshot[] {
    const seen: Snapshot[] = [];
    for (let i = 0; i < ticks; i += 1) {
      vi.advanceTimersByTime(1800);
      seen.push({ ...getMetricsSnapshot() });
    }
    return seen;
  }

  /** One settling tick first: `current` is module state and carries over
   *  between tests, so the baseline must be what the ticker itself computes
   *  from `bases`, not whatever the previous test left behind. */
  function settledBaseline(): Snapshot {
    return samplesOver(1)[0];
  }

  it('does not drift across many ticks while the link is down', () => {
    const before = settledBaseline();
    for (const sample of samplesOver(20)) expect(sample).toEqual(before);
  });

  it('does not drift while the link is up either', () => {
    setMetricLink(true);
    const before = settledBaseline();
    for (const sample of samplesOver(20)) expect(sample).toEqual(before);
  });

  it('still moves when a real sample arrives, and only on that channel', () => {
    setMetricBases({ research: 41 });
    for (const sample of samplesOver(5)) {
      expect(sample.research).toBe(41);
      // Untouched channels stay exactly where they were, every tick.
      expect(sample.memory).toBe(METRIC_BASES.memory);
    }
  });

  it('reports link state so a consumer can mark the readout stale', () => {
    // `linkUp` was write-only once the drift it gated was removed; a frozen
    // number is only honest if a caller can say WHY it is frozen.
    setMetricLink(false);
    expect(isMetricLinkUp()).toBe(false);
    setMetricLink(true);
    expect(isMetricLinkUp()).toBe(true);
  });
});

describe('routeMetric sends an event to the channel it means', () => {
  it('routes by meaning, not by the literal channel name', () => {
    expect(routeMetric('VERIFICATION GREEN')).toBe('tools');
    expect(routeMetric('trail #7 reinforced')).toBe('memory');
    expect(routeMetric('archive search complete')).toBe('research');
    expect(routeMetric('router synthesised a plan')).toBe('signals');
  });

  it('returns null for a label it does not recognise', () => {
    // The caller rotates as a fallback; conflating "no match" with a match is
    // how every bump silently round-robined before.
    expect(routeMetric('zzzz')).toBeNull();
  });
});
