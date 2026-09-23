import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  clearFrontendMetricSamples,
  getFrontendMetricSamples,
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
