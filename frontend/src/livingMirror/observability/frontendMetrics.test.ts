import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  clearFrontendMetricSamples,
  createMirrorReconnectTracker,
  createComposerFrameDrawCallSampler,
  getFrontendMetricSamples,
  getFrontendSceneDiagnostics,
  recordFrontendSceneDiagnostic,
  recordFrontendMetric,
  startFrameTimeSampler,
} from './frontendMetrics';

describe('frontend metrics', () => {
  beforeEach(() => clearFrontendMetricSamples());

  it('stores only bounded numeric samples and exposes no user content', () => {
    recordFrontendMetric('approval-render', 18);
    recordFrontendMetric('approval-render', Number.NaN);
    expect(getFrontendMetricSamples()).toEqual([
      expect.objectContaining({ name: 'approval-render', value: 18 }),
    ]);
  });

  it('keeps the sample buffer bounded', () => {
    for (let i = 0; i < 300; i += 1) recordFrontendMetric('3d-initialization', i);
    expect(getFrontendMetricSamples()).toHaveLength(256);
    expect(getFrontendMetricSamples()[0]?.value).toBe(44);
  });

  it('does not require a browser event target in a test environment', () => {
    const dispatch = vi.spyOn(window, 'dispatchEvent');
    recordFrontendMetric('mirror-reconnect', 4);
    expect(dispatch).toHaveBeenCalled();
  });

  it('exposes only the bounded metric buffer through the localhost evidence hook', () => {
    const host = window as typeof window & {
      __getFrontendMetrics?: () => readonly { name: string; value: number; at: number }[];
    };
    expect(host.__getFrontendMetrics?.()).toEqual([]);
    recordFrontendMetric('frame-time-p95', 18.5);
    expect(host.__getFrontendMetrics?.()).toEqual([
      expect.objectContaining({ name: 'frame-time-p95', value: 18.5 }),
    ]);
  });

  it('publishes only bounded content-free probes on the localhost document root', () => {
    recordFrontendMetric('frame-time-p95', 18.5);
    recordFrontendSceneDiagnostic({
      sceneObjects: 58,
      drawCalls: 1,
      geometries: 22,
      textures: 20,
      transientPoolSize: 0,
      workerBranchCount: 2,
      workerMoteCount: 2,
      materializationSurfaceCount: 1,
      lightningCount: 0,
    });

    expect(document.documentElement.getAttribute('data-gagos-metric-frame-time-p95')).toBe('18.5');
    expect(document.documentElement.getAttribute('data-gagos-scene-objects')).toBe('58');
    expect(document.documentElement.getAttribute('data-gagos-scene-worker-branches')).toBe('2');
    expect(document.documentElement.getAttribute('data-gagos-scene-materialization-surfaces')).toBe('1');
    expect(document.documentElement.outerHTML).not.toMatch(/prompt|filepath|workerId|authority/);

    clearFrontendMetricSamples();
    expect(document.documentElement.getAttribute('data-gagos-metric-frame-time-p95')).toBeNull();
    expect(document.documentElement.getAttribute('data-gagos-scene-objects')).toBeNull();
  });

  it('keeps scene diagnostics bounded and content-free', () => {
    for (let i = 0; i < 140; i += 1) {
      recordFrontendSceneDiagnostic({
        sceneObjects: i,
        drawCalls: i + 1,
        geometries: 4,
        textures: 2,
        transientPoolSize: i % 8,
        workerBranchCount: i % 9,
        workerMoteCount: i % 9,
        materializationSurfaceCount: i % 12,
        lightningCount: i % 4,
      });
    }

    expect(getFrontendSceneDiagnostics()).toHaveLength(128);
    expect(getFrontendSceneDiagnostics()[0]).toMatchObject({ sceneObjects: 12 });
    expect(JSON.stringify(getFrontendSceneDiagnostics())).not.toMatch(/prompt|filepath|workerId|authority/);
  });

  it('rejects invalid scene diagnostics without poisoning the bounded buffer', () => {
    recordFrontendSceneDiagnostic({
      sceneObjects: Number.NaN,
      drawCalls: 1,
      geometries: 1,
      textures: 1,
      transientPoolSize: 0,
      workerBranchCount: 0,
      workerMoteCount: 0,
      materializationSurfaceCount: 0,
      lightningCount: 0,
    });
    expect(getFrontendSceneDiagnostics()).toEqual([]);
  });

  it('aggregates draw calls across composer passes and resets once per completed frame', () => {
    const counters = { calls: 0 };
    const info = {
      autoReset: true,
      render: counters,
      reset: vi.fn(() => { counters.calls = 0; }),
    };
    const sampler = createComposerFrameDrawCallSampler(info);
    expect(sampler).not.toBeNull();

    const renderPass = (drawCalls: number) => {
      if (info.autoReset) info.reset();
      counters.calls += drawCalls;
    };

    renderPass(12);
    renderPass(4);
    expect(info.autoReset).toBe(false);
    expect(sampler?.capture()).toBe(16);

    renderPass(3);
    expect(sampler?.capture()).toBe(3);
    sampler?.dispose();
    expect(info.autoReset).toBe(true);
    expect(counters.calls).toBe(0);
  });

  it('reports unavailable instead of zero when composer draw counters are missing', () => {
    const reset = vi.fn();
    const sampler = createComposerFrameDrawCallSampler({ autoReset: true, render: {}, reset });
    expect(sampler?.capture()).toBeNull();
    expect(reset).toHaveBeenCalledOnce();

    recordFrontendSceneDiagnostic({
      sceneObjects: 1,
      drawCalls: null,
      geometries: null,
      textures: null,
      transientPoolSize: 0,
      workerBranchCount: 0,
      workerMoteCount: 0,
      materializationSurfaceCount: 0,
      lightningCount: 0,
    });
    expect(getFrontendSceneDiagnostics()[0]?.drawCalls).toBeNull();
    expect(getFrontendSceneDiagnostics()[0]?.geometries).toBeNull();
    expect(getFrontendSceneDiagnostics()[0]?.textures).toBeNull();
    expect(document.documentElement.getAttribute('data-gagos-scene-draw-calls')).toBe('unavailable');
    expect(document.documentElement.getAttribute('data-gagos-scene-geometries')).toBe('unavailable');
    expect(document.documentElement.getAttribute('data-gagos-scene-textures')).toBe('unavailable');
  });

  it('measures recovery from an established mirror to a fresh projection', () => {
    let clock = 100;
    const track = createMirrorReconnectTracker(() => clock);
    const fresh = { connection: 'connected', projection: 'fresh' } as const;

    track(fresh, { connection: 'connecting', projection: 'synchronizing' });
    expect(getFrontendMetricSamples()).toHaveLength(0);

    clock = 120;
    track({ connection: 'connecting', projection: 'stale' }, fresh);
    clock = 180;
    track({ connection: 'connected', projection: 'snapshot' }, { connection: 'connecting', projection: 'stale' });
    expect(getFrontendMetricSamples()).toHaveLength(0);

    clock = 250;
    track(fresh, { connection: 'connected', projection: 'snapshot' });
    expect(getFrontendMetricSamples()).toEqual([
      expect.objectContaining({ name: 'mirror-reconnect', value: 130 }),
    ]);
  });

  it('records frame percentiles and dropped-frame periods from the bounded sampler', () => {
    const callbacks: FrameRequestCallback[] = [];
    const request = vi.spyOn(window, 'requestAnimationFrame').mockImplementation((callback) => {
      callbacks.push(callback);
      return callbacks.length;
    });
    const cancel = vi.spyOn(window, 'cancelAnimationFrame').mockImplementation(() => undefined);
    vi.spyOn(performance, 'now').mockReturnValue(0);

    const stop = startFrameTimeSampler();
    let timestamp = 0;
    for (let index = 0; index < 120; index += 1) {
      timestamp += index === 10 ? 60 : 16;
      callbacks[callbacks.length - 1]?.(timestamp);
    }
    stop();

    const names = getFrontendMetricSamples().map((sample) => sample.name);
    expect(names).toContain('dropped-frame-period');
    expect(names).toContain('frame-time-p50');
    expect(names).toContain('frame-time-p95');
    expect(request).toHaveBeenCalledTimes(121);
    expect(cancel).toHaveBeenCalledWith(121);
  });

  it('does not classify a background-tab pause as a dropped frame', () => {
    const callbacks: FrameRequestCallback[] = [];
    vi.spyOn(window, 'requestAnimationFrame').mockImplementation((callback) => {
      callbacks.push(callback);
      return callbacks.length;
    });
    vi.spyOn(window, 'cancelAnimationFrame').mockImplementation(() => undefined);
    vi.spyOn(performance, 'now').mockReturnValue(0);
    const visibility = { value: 'visible' as DocumentVisibilityState };
    const visibilitySpy = vi.spyOn(document, 'visibilityState', 'get').mockImplementation(() => visibility.value);

    const stop = startFrameTimeSampler();
    visibility.value = 'hidden';
    document.dispatchEvent(new Event('visibilitychange'));
    callbacks[callbacks.length - 1]?.(2_000);
    visibility.value = 'visible';
    document.dispatchEvent(new Event('visibilitychange'));
    callbacks[callbacks.length - 1]?.(2_016);
    stop();

    expect(getFrontendMetricSamples().some((sample) => sample.name === 'dropped-frame-period')).toBe(false);
    visibilitySpy.mockRestore();
  });
});
