import { describe, expect, it } from 'vitest';
import {
  advanceAutoQuality,
  autoQualityProfile,
  initialAutoQuality,
  isQualityPreference,
  setAutoSampling,
  startAutoQuality,
  type AutoQualityRuntime,
  type FrameLoadSignal,
} from './renderQualityPolicy';

function step(
  state: AutoQualityRuntime,
  signal: FrameLoadSignal,
  at: number,
  densityAllowed = true,
): AutoQualityRuntime {
  return advanceAutoQuality(state, signal, state.revision, at, densityAllowed);
}

function sampling(): AutoQualityRuntime {
  return setAutoSampling(startAutoQuality(initialAutoQuality(), 0), true, 0);
}

describe('isQualityPreference / autoQualityProfile', () => {
  it('accepts only the known preferences', () => {
    for (const v of ['auto', 'high', 'medium', 'low']) {
      expect(isQualityPreference(v)).toBe(true);
    }
    expect(isQualityPreference('ultra')).toBe(false);
    expect(isQualityPreference(undefined)).toBe(false);
    expect(isQualityPreference(1)).toBe(false);
  });

  it('degrades cost levers in stage order', () => {
    expect(autoQualityProfile(0)).toMatchObject({ multisampling: 4, skyTier: 'high', densityTier: 'high' });
    expect(autoQualityProfile(1).multisampling).toBe(0);
    expect(autoQualityProfile(2).skyTier).toBe('low');
    expect(autoQualityProfile(3).dpr).toEqual([1, 1.25]);
    expect(autoQualityProfile(5).densityTier).toBe('medium');
    expect(autoQualityProfile(6).densityTier).toBe('low');
  });
});

describe('startAutoQuality / setAutoSampling', () => {
  it('starts a warmup and bumps the revision', () => {
    const started = startAutoQuality(initialAutoQuality(), 1000);
    expect(started).toMatchObject({ revision: 1, readyAfter: 21000, lastChangedAt: 1000, stage: 0 });
    expect(startAutoQuality(started, -1)).toBe(started);
    expect(startAutoQuality(started, Number.NaN)).toBe(started);
  });

  it('extends readiness by the settle time when sampling resumes', () => {
    const started = startAutoQuality(initialAutoQuality(), 1000);
    const early = setAutoSampling(started, true, 2000);
    expect(early).toMatchObject({ sampling: true, revision: 2, readyAfter: 21000 });
    const late = setAutoSampling(started, true, 30000);
    expect(late.readyAfter).toBe(34000);
    expect(setAutoSampling(early, true, 3000)).toBe(early);
    expect(setAutoSampling(initialAutoQuality(), true, 5).readyAfter).toBeNull();
  });
});

describe('advanceAutoQuality', () => {
  it('ignores signals that are early, stale, or not sampling', () => {
    const s = sampling();
    expect(step(s, 'slow', 19999)).toBe(s);
    expect(advanceAutoQuality(s, 'slow', s.revision - 1, 25000, true)).toBe(s);
    const idle = { ...s, sampling: false };
    expect(step(idle, 'slow', 25000)).toBe(idle);
  });

  it('steps down on a slow signal and resets signal tracking', () => {
    const s1 = step(sampling(), 'slow', 20000);
    expect(s1).toMatchObject({ stage: 1, revision: 3, lastChangedAt: 20000, lastSignalAt: null });
    expect(step(s1, 'slow', 22000).stage).toBe(1);
    expect(step(s1, 'slow', 24000).stage).toBe(2);
  });

  it('holds density stages when density is not allowed', () => {
    let s = sampling();
    for (const at of [20000, 24000, 28000, 32000]) s = step(s, 'slow', at);
    expect(s.stage).toBe(4);
    const blocked = step(s, 'slow', 36000, false);
    expect(blocked).toMatchObject({ stage: 4, revision: s.revision, lastSignal: 'slow', lastSignalAt: 36000 });
    expect(step(s, 'slow', 36000, true).stage).toBe(5);
  });

  it('recovers after two adjacent healthy windows past the recovery time', () => {
    const s1 = step(sampling(), 'slow', 20000);
    const h1 = step(s1, 'healthy', 30000);
    expect(h1).toMatchObject({ stage: 1, healthyWindows: 1 });
    const h2 = step(h1, 'healthy', 32000);
    expect(h2).toMatchObject({ stage: 0, healthyWindows: 0, revision: h1.revision + 1 });
  });

  it('restarts the healthy count when windows are not adjacent or repeat a timestamp', () => {
    const h1 = step(step(sampling(), 'slow', 20000), 'healthy', 30000);
    const gap = step(h1, 'healthy', 35000);
    expect(gap).toMatchObject({ stage: 1, healthyWindows: 1 });
    expect(step(h1, 'healthy', 30000)).toBe(h1);
    expect(step(h1, 'slow', 31000).healthyWindows).toBe(0);
  });
});
