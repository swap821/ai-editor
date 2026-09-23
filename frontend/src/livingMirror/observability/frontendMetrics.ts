/** Local-only frontend measurements. No prompt, file, model, worker, or user
 * identity data is accepted by this module. Consumers may read the bounded
 * sample buffer or listen to the namespaced browser event. */
export type FrontendMetricName =
  | 'boot-to-input-ready'
  | '3d-initialization'
  | 'frame-time-p50'
  | 'frame-time-p95'
  | 'dropped-frame-period'
  | 'workspace-materialization'
  | 'approval-render'
  | 'mirror-reconnect'
  | 'context-recovery';

export interface FrontendMetricSample {
  name: FrontendMetricName;
  value: number;
  at: number;
}

const MAX_SAMPLES = 256;
const samples: FrontendMetricSample[] = [];

export function recordFrontendMetric(name: FrontendMetricName, value: number): void {
  if (!Number.isFinite(value) || value < 0) return;
  const sample = { name, value, at: Date.now() } satisfies FrontendMetricSample;
  samples.push(sample);
  if (samples.length > MAX_SAMPLES) samples.splice(0, samples.length - MAX_SAMPLES);
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('gagos:frontend-metric', { detail: { name, value } }));
  }
}

export function getFrontendMetricSamples(): readonly FrontendMetricSample[] {
  return samples.slice();
}

export function clearFrontendMetricSamples(): void {
  samples.length = 0;
}

export function startFrameTimeSampler(): () => void {
  if (typeof window === 'undefined' || typeof window.requestAnimationFrame !== 'function') return () => {};
  let active = true;
  let previous = performance.now();
  const deltas: number[] = [];
  let raf = 0;
  // A background tab can pause requestAnimationFrame for seconds or minutes.
  // That is not a renderer drop, so reset the clock at the visibility boundary
  // instead of attributing the hidden interval to the next foreground frame.
  let hidden = typeof document !== 'undefined' && document.visibilityState === 'hidden';
  let ignoreNextForegroundFrame = hidden;
  const handleVisibilityChange = () => {
    hidden = typeof document !== 'undefined' && document.visibilityState === 'hidden';
    previous = performance.now();
    ignoreNextForegroundFrame = true;
  };
  if (typeof document !== 'undefined') {
    document.addEventListener('visibilitychange', handleVisibilityChange);
  }
  const sample = (now: number) => {
    if (!active) return;
    if (hidden || (typeof document !== 'undefined' && document.visibilityState === 'hidden')) {
      previous = now;
      raf = window.requestAnimationFrame(sample);
      return;
    }
    if (ignoreNextForegroundFrame) {
      previous = now;
      ignoreNextForegroundFrame = false;
      raf = window.requestAnimationFrame(sample);
      return;
    }
    const delta = Math.max(0, now - previous);
    previous = now;
    deltas.push(delta);
    if (delta >= 50) recordFrontendMetric('dropped-frame-period', delta);
    if (deltas.length >= 120) {
      const sorted = [...deltas].sort((a, b) => a - b);
      recordFrontendMetric('frame-time-p50', sorted[Math.floor(sorted.length * 0.5)] ?? 0);
      recordFrontendMetric('frame-time-p95', sorted[Math.floor(sorted.length * 0.95)] ?? 0);
      deltas.length = 0;
    }
    raf = window.requestAnimationFrame(sample);
  };
  raf = window.requestAnimationFrame(sample);
  return () => {
    active = false;
    window.cancelAnimationFrame(raf);
    if (typeof document !== 'undefined') {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    }
  };
}
