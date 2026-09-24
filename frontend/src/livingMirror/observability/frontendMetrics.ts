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

export interface FrontendSceneDiagnosticSample {
  at: number;
  sceneObjects: number;
  renderCalls: number;
  geometries: number;
  textures: number;
  transientPoolSize: number;
  workerBranchCount: number;
  workerMoteCount: number;
  materializationSurfaceCount: number;
  lightningCount: number;
}

export interface MirrorContinuitySnapshot {
  connection: 'disconnected' | 'connecting' | 'connected';
  projection: 'unknown' | 'synchronizing' | 'snapshot' | 'fresh' | 'stale' | 'unavailable';
}

const MAX_SAMPLES = 256;
const samples: FrontendMetricSample[] = [];
const MAX_SCENE_DIAGNOSTICS = 128;
const sceneDiagnostics: FrontendSceneDiagnosticSample[] = [];
const LOCAL_EVIDENCE_HOSTS = new Set(['localhost', '127.0.0.1']);

function localEvidenceRoot(): HTMLElement | null {
  if (
    typeof window === 'undefined' ||
    typeof document === 'undefined' ||
    !LOCAL_EVIDENCE_HOSTS.has(window.location.hostname)
  ) {
    return null;
  }
  return document.documentElement;
}

function publishLocalMetricProbe(name: FrontendMetricName, value: number): void {
  localEvidenceRoot()?.setAttribute(`data-gagos-metric-${name}`, String(value));
}

function publishLocalSceneProbe(sample: FrontendSceneDiagnosticSample): void {
  const root = localEvidenceRoot();
  if (!root) return;
  root.setAttribute('data-gagos-scene-at', String(sample.at));
  root.setAttribute('data-gagos-scene-objects', String(sample.sceneObjects));
  root.setAttribute('data-gagos-scene-render-calls', String(sample.renderCalls));
  root.setAttribute('data-gagos-scene-geometries', String(sample.geometries));
  root.setAttribute('data-gagos-scene-textures', String(sample.textures));
  root.setAttribute('data-gagos-scene-transient-pool', String(sample.transientPoolSize));
  root.setAttribute('data-gagos-scene-worker-branches', String(sample.workerBranchCount));
  root.setAttribute('data-gagos-scene-worker-motes', String(sample.workerMoteCount));
  root.setAttribute('data-gagos-scene-materialization-surfaces', String(sample.materializationSurfaceCount));
  root.setAttribute('data-gagos-scene-lightning', String(sample.lightningCount));
}

function clearLocalProbes(): void {
  const root = localEvidenceRoot();
  if (!root) return;
  for (const attribute of [...root.attributes]) {
    if (attribute.name.startsWith('data-gagos-metric-') || attribute.name.startsWith('data-gagos-scene-')) {
      root.removeAttribute(attribute.name);
    }
  }
}

export function recordFrontendMetric(name: FrontendMetricName, value: number): void {
  if (!Number.isFinite(value) || value < 0) return;
  const sample = { name, value, at: Date.now() } satisfies FrontendMetricSample;
  samples.push(sample);
  if (samples.length > MAX_SAMPLES) samples.splice(0, samples.length - MAX_SAMPLES);
  publishLocalMetricProbe(name, value);
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('gagos:frontend-metric', { detail: { name, value } }));
  }
}

export function getFrontendMetricSamples(): readonly FrontendMetricSample[] {
  return samples.slice();
}

/**
 * Records a bounded, content-free snapshot of the product-owned scene and
 * transient pools. This is intentionally sampled at a coarse cadence by the
 * renderer, not updated as React state and not sent across the backend
 * boundary.
 */
export function recordFrontendSceneDiagnostic(
  snapshot: Omit<FrontendSceneDiagnosticSample, 'at'> & { at?: number },
): void {
  const values = Object.entries(snapshot).filter(([key]) => key !== 'at');
  if (values.some(([, value]) => !Number.isFinite(value) || value < 0)) return;
  const sample: FrontendSceneDiagnosticSample = {
    at: snapshot.at ?? Date.now(),
    sceneObjects: Math.round(snapshot.sceneObjects),
    renderCalls: Math.round(snapshot.renderCalls),
    geometries: Math.round(snapshot.geometries),
    textures: Math.round(snapshot.textures),
    transientPoolSize: Math.round(snapshot.transientPoolSize),
    workerBranchCount: Math.round(snapshot.workerBranchCount),
    workerMoteCount: Math.round(snapshot.workerMoteCount),
    materializationSurfaceCount: Math.round(snapshot.materializationSurfaceCount),
    lightningCount: Math.round(snapshot.lightningCount),
  };
  sceneDiagnostics.push(sample);
  if (sceneDiagnostics.length > MAX_SCENE_DIAGNOSTICS) {
    sceneDiagnostics.splice(0, sceneDiagnostics.length - MAX_SCENE_DIAGNOSTICS);
  }
  publishLocalSceneProbe(sample);
}

export function getFrontendSceneDiagnostics(): readonly FrontendSceneDiagnosticSample[] {
  return sceneDiagnostics.slice();
}

/**
 * Local-only read hook for browser evidence. It exposes the existing bounded
 * sampler without exposing prompts, records, identities, or authority data.
 */
if (typeof window !== 'undefined' && ['localhost', '127.0.0.1'].includes(window.location.hostname)) {
  const host = window as typeof window & {
    __getFrontendMetrics?: () => readonly FrontendMetricSample[];
    __getFrontendSceneDiagnostics?: () => readonly FrontendSceneDiagnosticSample[];
  };
  host.__getFrontendMetrics = getFrontendMetricSamples;
  host.__getFrontendSceneDiagnostics = getFrontendSceneDiagnostics;
}

export function clearFrontendMetricSamples(): void {
  samples.length = 0;
  sceneDiagnostics.length = 0;
  clearLocalProbes();
}

/**
 * Measures an established mirror's actual continuity recovery. Initial boot
 * and transport-only reconnects are not latency samples: the projection must
 * reach the named `fresh` barrier before recovery is considered complete.
 */
export function createMirrorReconnectTracker(
  now: () => number = () => (typeof performance === 'undefined' ? Date.now() : performance.now()),
  record: (name: FrontendMetricName, value: number) => void = recordFrontendMetric,
): (state: MirrorContinuitySnapshot, previous: MirrorContinuitySnapshot) => void {
  let lostAt: number | null = null;
  return (state, previous) => {
    if (previous.connection === 'connected' && state.connection !== 'connected') {
      lostAt ??= now();
      return;
    }
    if (lostAt === null || state.connection !== 'connected' || state.projection !== 'fresh') return;
    record('mirror-reconnect', Math.max(0, now() - lostAt));
    lostAt = null;
  };
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
