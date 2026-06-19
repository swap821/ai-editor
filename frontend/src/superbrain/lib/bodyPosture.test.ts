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
  it('keeps the spectral-v1 state colors exactly', () => {
    expect(BODY_POSTURES.rest.color).toEqual([150, 120, 255]);
    expect(BODY_POSTURES.think.color).toEqual([196, 78, 255]);
    expect(BODY_POSTURES.stream.color).toEqual([54, 214, 255]);
    expect(BODY_POSTURES.complete.color).toEqual([62, 240, 160]);
    expect(BODY_POSTURES.error.color).toEqual([255, 92, 72]);
  });

  it('streaming flows fastest, rest slowest', () => {
    expect(BODY_POSTURES.stream.flow).toBeGreaterThan(BODY_POSTURES.think.flow);
    expect(BODY_POSTURES.think.flow).toBeGreaterThan(BODY_POSTURES.rest.flow);
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
    expect(r).toBeCloseTo(54 / 255);
    expect(g).toBeCloseTo(214 / 255);
    expect(b).toBeCloseTo(1);
  });
});
