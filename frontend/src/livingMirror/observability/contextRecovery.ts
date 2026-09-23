import { recordFrontendMetric, type FrontendMetricName } from './frontendMetrics';

type MetricRecorder = (name: FrontendMetricName, value: number) => void;

interface ContextRecoveryTrackerOptions {
  now?: () => number;
  record?: MetricRecorder;
}

export interface ContextRecoveryTracker {
  handleLost: () => void;
  handleRestored: () => void;
}

function defaultNow(): number {
  return typeof performance !== 'undefined' && typeof performance.now === 'function'
    ? performance.now()
    : Date.now();
}

/**
 * Tracks only a measured WebGL loss → restore pair. A restore without a
 * preceding loss is intentionally ignored so the UI never invents recovery.
 */
export function createContextRecoveryTracker({
  now = defaultNow,
  record = recordFrontendMetric,
}: ContextRecoveryTrackerOptions = {}): ContextRecoveryTracker {
  let lostAt: number | null = null;

  return {
    handleLost: () => {
      lostAt = now();
    },
    handleRestored: () => {
      if (lostAt === null) return;
      record('context-recovery', Math.max(0, now() - lostAt));
      lostAt = null;
    },
  };
}
