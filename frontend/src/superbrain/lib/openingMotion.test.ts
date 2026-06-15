import { describe, it, expect } from 'vitest';
import {
  cubicBezier,
  coalescenceEnvelope,
  ignitionPulse,
  awakenNotice,
  shouldReduceMotion,
  isAwakeningTrigger,
} from './openingMotion';
import { OPENING_TIMINGS, COALESCENCE_SCALE_FLOOR } from './openingTokens';

describe('cubicBezier', () => {
  it('pins endpoints to 0 and 1', () => {
    const ease = cubicBezier(0.16, 1, 0.3, 1);
    expect(ease(0)).toBeCloseTo(0, 5);
    expect(ease(1)).toBeCloseTo(1, 5);
  });
  it('is monotonic non-decreasing across the unit interval', () => {
    const ease = cubicBezier(0.16, 1, 0.3, 1);
    let prev = -1;
    for (let t = 0; t <= 1.0001; t += 0.05) {
      const v = ease(Math.min(1, t));
      expect(v).toBeGreaterThanOrEqual(prev - 1e-6);
      prev = v;
    }
  });
});

describe('coalescenceEnvelope', () => {
  it('opacity starts at 0 and scale starts at the floor (never 0)', () => {
    const env = coalescenceEnvelope(0);
    expect(env.opacity).toBeCloseTo(0, 5);
    expect(env.scale).toBeCloseTo(COALESCENCE_SCALE_FLOOR, 5);
    expect(env.arrival).toBeCloseTo(1, 5); // 1 = fully in progress
  });
  it('lands settled at the end of coalescence', () => {
    const env = coalescenceEnvelope(OPENING_TIMINGS.coalescenceMs);
    expect(env.opacity).toBeCloseTo(1, 5);
    expect(env.scale).toBeCloseTo(1, 5);
    expect(env.arrival).toBeCloseTo(0, 5); // 0 = settled
  });
  it('clamps past the end', () => {
    const env = coalescenceEnvelope(OPENING_TIMINGS.coalescenceMs + 5000);
    expect(env.opacity).toBeCloseTo(1, 5);
    expect(env.arrival).toBeCloseTo(0, 5);
  });
});

describe('ignitionPulse', () => {
  it('is 0 at start, 0 at end, and peaks near the ignition time', () => {
    expect(ignitionPulse(0)).toBeCloseTo(0, 5);
    expect(ignitionPulse(OPENING_TIMINGS.coalescenceMs)).toBeCloseTo(0, 5);
    const peak = ignitionPulse(OPENING_TIMINGS.ignitionPeakMs);
    expect(peak).toBeGreaterThan(0.9);
  });
});

describe('awakenNotice', () => {
  it('rises from 0 to 1 over the notice window then holds', () => {
    expect(awakenNotice(0)).toBeCloseTo(0, 5);
    expect(awakenNotice(OPENING_TIMINGS.awakenNoticeMs)).toBeCloseTo(1, 5);
    expect(awakenNotice(OPENING_TIMINGS.awakenNoticeMs * 4)).toBeCloseTo(1, 5);
  });
});

describe('shouldReduceMotion', () => {
  it('returns true when the media query matches', () => {
    expect(shouldReduceMotion({ matchMedia: () => ({ matches: true }) } as unknown as Window)).toBe(true);
  });
  it('returns false when it does not match', () => {
    expect(shouldReduceMotion({ matchMedia: () => ({ matches: false }) } as unknown as Window)).toBe(false);
  });
  it('returns false when matchMedia is unavailable (SSR-safe)', () => {
    expect(shouldReduceMotion(undefined)).toBe(false);
  });
});

describe('isAwakeningTrigger (user spoke -> awakening)', () => {
  it('maps a directive event to an awakening trigger', () => {
    expect(isAwakeningTrigger({ type: 'directive', source: 'voice' })).toBe(true);
    expect(isAwakeningTrigger({ type: 'directive', source: 'hud' })).toBe(true);
  });
  it('ignores ambient/system events', () => {
    expect(isAwakeningTrigger({ type: 'burst', source: 'scene' })).toBe(false);
    expect(isAwakeningTrigger({ type: 'synthesis', source: 'idle' })).toBe(false);
    expect(isAwakeningTrigger(null)).toBe(false);
  });
});
