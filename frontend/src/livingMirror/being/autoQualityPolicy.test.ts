import { expect, it } from 'vitest';
import { advanceAutoQuality, initialAutoQuality, setAutoSampling, startAutoQuality } from '../../superbrain/lib/renderQualityPolicy';

const ready = () => setAutoSampling(startAutoQuality(initialAutoQuality(), 1000), true, 1000);
it('rejects pre-useful, inactive, obsolete, nonfinite and time-regressing samples', () => {
  const cold = setAutoSampling(initialAutoQuality(), true, 0);
  expect(advanceAutoQuality(cold, 'slow', cold.revision, 999999, true)).toBe(cold);
  const state = ready();
  for (const at of [-1, NaN, Infinity, 20999]) expect(advanceAutoQuality(state, 'slow', state.revision, at, true)).toBe(state);
  expect(advanceAutoQuality(state, 'slow', state.revision - 1, 22000, true)).toBe(state);
  const inactive = setAutoSampling(state, false, 22000);
  expect(advanceAutoQuality(inactive, 'slow', inactive.revision, 90000, true)).toBe(inactive);
  const resumed = setAutoSampling(inactive, true, 90000);
  expect(advanceAutoQuality(resumed, 'slow', resumed.revision, 93999, true)).toBe(resumed);
  expect(advanceAutoQuality(resumed, 'slow', resumed.revision, 94000, true).stage).toBe(1);
});
it('requires distinct adjacent healthy windows and slower recovery, not duplicate reports or a brief hitch', () => {
  const state = ready();
  const reduced = advanceAutoQuality(state, 'slow', state.revision, 22000, true);
  expect(reduced.stage).toBe(1);
  expect(advanceAutoQuality(reduced, 'slow', reduced.revision, 25999, true).stage).toBe(1);
  const healthy = advanceAutoQuality(reduced, 'healthy', reduced.revision, 33000, true);
  expect(healthy.stage).toBe(1);
  expect(advanceAutoQuality(healthy, 'healthy', healthy.revision, 33000, true)).toBe(healthy);
  expect(advanceAutoQuality(healthy, 'healthy', healthy.revision, 32999, true)).toBe(healthy);
  expect(advanceAutoQuality(healthy, 'healthy', healthy.revision, 35500, true).stage).toBe(0);
  const separated = advanceAutoQuality(healthy, 'healthy', healthy.revision, 40000, true);
  expect(separated.stage).toBe(1);
});
