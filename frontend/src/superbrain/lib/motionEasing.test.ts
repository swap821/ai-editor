import { describe, it, expect } from 'vitest';
import {
  clamp01,
  easeOutExpo,
  easeOutQuint,
  easeOutBack,
  easeInCubic,
  layerProgress,
  flashBell,
} from './motionEasing';

describe('motionEasing', () => {
  describe('clamp01', () => {
    it('clamps to [0,1]', () => {
      expect(clamp01(-2)).toBe(0);
      expect(clamp01(0.5)).toBe(0.5);
      expect(clamp01(3)).toBe(1);
    });
  });

  describe('easeOutExpo / easeOutQuint', () => {
    it('pin the [0,1] boundary exactly', () => {
      for (const f of [easeOutExpo, easeOutQuint]) {
        expect(f(0)).toBe(0);
        expect(f(1)).toBe(1);
      }
    });
    it('decelerate — past the midpoint by t=0.5 (front-loaded)', () => {
      expect(easeOutExpo(0.5)).toBeGreaterThan(0.9);
      expect(easeOutQuint(0.5)).toBeGreaterThan(0.9);
    });
    it('are monotonic increasing', () => {
      let prev = -1;
      for (let t = 0; t <= 1.0001; t += 0.05) {
        const v = easeOutExpo(t);
        expect(v).toBeGreaterThanOrEqual(prev);
        prev = v;
      }
    });
  });

  describe('easeInCubic', () => {
    it('pins the [0,1] boundary exactly', () => {
      expect(easeInCubic(0)).toBe(0);
      expect(easeInCubic(1)).toBe(1);
    });
    it('accelerates — BELOW the midpoint by t=0.5 (back-loaded, opposite of ease-out)', () => {
      expect(easeInCubic(0.5)).toBeLessThan(0.2);
    });
    it('is monotonic increasing', () => {
      let prev = -1;
      for (let t = 0; t <= 1.0001; t += 0.05) {
        const v = easeInCubic(t);
        expect(v).toBeGreaterThanOrEqual(prev);
        prev = v;
      }
    });
  });

  describe('easeOutBack', () => {
    it('pins f(0)=0 and f(1)=1 exactly (settles, no end-overshoot)', () => {
      expect(easeOutBack(0)).toBe(0);
      expect(easeOutBack(1)).toBe(1);
    });
    it('OVERSHOOTS above 1 in the middle (the catch), then settles', () => {
      let peak = 0;
      for (let t = 0; t < 1; t += 0.01) peak = Math.max(peak, easeOutBack(t, 1.1));
      expect(peak).toBeGreaterThan(1.0); // genuinely overshoots
      expect(peak).toBeLessThan(1.12); // subtle, premium — not a cartoon bounce
    });
    it('a bigger overshoot peaks higher', () => {
      const peakOf = (k: number) => {
        let p = 0;
        for (let t = 0; t < 1; t += 0.01) p = Math.max(p, easeOutBack(t, k));
        return p;
      };
      expect(peakOf(2.0)).toBeGreaterThan(peakOf(1.1));
    });
  });

  describe('layerProgress', () => {
    it('returns 0 until the parent reaches the layer start', () => {
      expect(layerProgress(0.1, 0.3)).toBe(0);
      expect(layerProgress(0.3, 0.3)).toBe(0);
      expect(layerProgress(0.31, 0.3)).toBeGreaterThan(0);
    });
    it('reaches 1 when the parent reaches 1', () => {
      expect(layerProgress(1, 0.3)).toBe(1);
      expect(layerProgress(1, 0)).toBe(1);
    });
    it('a later layer trails an earlier one at the same parent progress', () => {
      const early = layerProgress(0.6, 0.0);
      const late = layerProgress(0.6, 0.45);
      expect(early).toBeGreaterThan(late);
    });
  });

  describe('flashBell', () => {
    it('is 0 at and outside the boundary', () => {
      expect(flashBell(0)).toBe(0);
      expect(flashBell(1)).toBe(0);
      expect(flashBell(-1)).toBe(0);
      expect(flashBell(2)).toBe(0);
    });
    it('peaks at ~1 at the peak position and is one-shot', () => {
      expect(flashBell(0.38, 0.38)).toBeCloseTo(1, 5);
      expect(flashBell(0.19, 0.38)).toBeCloseTo(0.5, 5); // rising
      expect(flashBell(0.69, 0.38)).toBeCloseTo(0.5, 5); // falling
    });
  });
});
