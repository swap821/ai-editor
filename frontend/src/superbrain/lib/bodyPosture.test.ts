import { describe, it, expect } from 'vitest';
import type { OrganismLifecyclePhase } from './organismLifecycle';
import {
  BODY_POSTURES,
  deriveBodyPosture,
  postureColor01,
  postureKeyForPhase,
  type BodyPostureKey,
} from './bodyPosture';

describe('bodyPosture — spectral-v1 palette', () => {
  it('keeps the poster "STATUS FROM BODY" tetrad colors exactly', () => {
    expect(BODY_POSTURES.rest.color).toEqual([158, 120, 245]);
    expect(BODY_POSTURES.think.color).toEqual([176, 110, 255]); // poster purple #b06eff
    expect(BODY_POSTURES.stream.color).toEqual([123, 245, 251]); // poster cyan #7bf5fb
    expect(BODY_POSTURES.hold.color).toEqual([255, 126, 64]); // poster orange #ff7e40
    expect(BODY_POSTURES.complete.color).toEqual([84, 240, 160]); // poster green #54f0a0
    expect(BODY_POSTURES.error.color).toEqual([255, 92, 72]);
  });

  it('streaming flows fastest, rest slowest', () => {
    expect(BODY_POSTURES.stream.flow).toBeGreaterThan(BODY_POSTURES.think.flow);
    expect(BODY_POSTURES.think.flow).toBeGreaterThan(BODY_POSTURES.rest.flow);
  });

  it('carries the spectral-v1 per-posture tint strength (rest clean → stronger when active)', () => {
    expect(BODY_POSTURES.rest.tint).toBe(0);
    expect(BODY_POSTURES.stream.tint).toBeGreaterThan(BODY_POSTURES.think.tint);
    expect(BODY_POSTURES.error.tint).toBeGreaterThanOrEqual(BODY_POSTURES.stream.tint);
    expect(BODY_POSTURES.rest.tint).toBeLessThan(BODY_POSTURES.complete.tint);
    for (const p of Object.values(BODY_POSTURES)) expect(p.tint).toBeLessThanOrEqual(0.8);
  });
});

describe('postureKeyForPhase — real lifecycle phases map to postures', () => {
  const cases: Array<[OrganismLifecyclePhase, BodyPostureKey]> = [
    ['booting', 'rest'],
    ['arrival', 'think'],
    ['rest', 'rest'],
    ['attentive', 'think'],
    ['intake', 'think'],
    ['materializing', 'stream'],
    ['working', 'stream'],
    ['conducting', 'stream'],
    ['approval_hold', 'hold'],
    ['error_repair', 'error'],
    ['completion_settle', 'complete'],
    ['reabsorbing', 'complete'],
  ];
  it.each(cases)('phase %s -> posture %s', (phase, key) => {
    expect(postureKeyForPhase(phase)).toBe(key);
  });

  it('falls back to rest for an unknown phase', () => {
    expect(postureKeyForPhase('nonsense' as OrganismLifecyclePhase)).toBe('rest');
  });
});

describe('deriveBodyPosture + postureColor01', () => {
  it('derives the posture object for a phase', () => {
    expect(deriveBodyPosture({ phase: 'conducting' })).toBe(BODY_POSTURES.stream);
    expect(deriveBodyPosture({ phase: 'rest' })).toBe(BODY_POSTURES.rest);
  });

  it('normalizes an sRGB triple to 0..1 for Three uniforms', () => {
    expect(postureColor01([255, 0, 51])).toEqual([1, 0, 51 / 255]);
    const [r, g, b] = postureColor01(BODY_POSTURES.stream.color);
    expect(r).toBeCloseTo(123 / 255);
    expect(g).toBeCloseTo(245 / 255);
    expect(b).toBeCloseTo(251 / 255);
  });
});
