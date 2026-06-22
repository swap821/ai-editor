import { describe, it, expect } from 'vitest';
import {
  deriveCursorAttention,
  ATTENTION_MAX_YAW,
  ATTENTION_MAX_PITCH,
  ATTENTION_BRIGHTEN,
} from './cursorAttention';

describe('deriveCursorAttention', () => {
  it('inactive: fully neutral', () => {
    const o = deriveCursorAttention({ pointerX: 1, pointerY: 1, active: false, reducedMotion: false });
    expect(o).toEqual({ leanYaw: 0, leanPitch: 0, brighten: 0 });
  });

  it('dead centre: no lean, no brighten', () => {
    const o = deriveCursorAttention({ pointerX: 0, pointerY: 0, active: true, reducedMotion: false });
    expect(o.leanYaw).toBe(0);
    expect(o.leanPitch).toBe(0);
    expect(o.brighten).toBe(0);
  });

  it('pointer right edge: leans right (+yaw), no pitch, full brighten', () => {
    const o = deriveCursorAttention({ pointerX: 1, pointerY: 0, active: true, reducedMotion: false });
    expect(o.leanYaw).toBeCloseTo(ATTENTION_MAX_YAW, 5);
    expect(o.leanPitch).toBe(0);
    expect(o.brighten).toBeCloseTo(ATTENTION_BRIGHTEN, 5);
  });

  it('pointer top edge: head tips up (-pitch, matches mesh sign), full brighten', () => {
    const o = deriveCursorAttention({ pointerX: 0, pointerY: 1, active: true, reducedMotion: false });
    expect(o.leanYaw).toBe(0);
    expect(o.leanPitch).toBeCloseTo(-ATTENTION_MAX_PITCH, 5);
    expect(o.brighten).toBeCloseTo(ATTENTION_BRIGHTEN, 5);
  });

  it('pointer left/bottom: opposite signs', () => {
    const o = deriveCursorAttention({ pointerX: -1, pointerY: -1, active: true, reducedMotion: false });
    expect(o.leanYaw).toBeCloseTo(-ATTENTION_MAX_YAW, 5);
    expect(o.leanPitch).toBeCloseTo(ATTENTION_MAX_PITCH, 5);
  });

  it('engagement scales brighten linearly toward the corner cap', () => {
    // (0.3, 0.4) → hypot 0.5 → half brighten.
    const half = deriveCursorAttention({ pointerX: 0.3, pointerY: 0.4, active: true, reducedMotion: false });
    expect(half.brighten).toBeCloseTo(0.5 * ATTENTION_BRIGHTEN, 4);
    // (0.6, 0.8) → hypot 1.0 → full brighten (diagonal reaches the cap).
    const full = deriveCursorAttention({ pointerX: 0.6, pointerY: 0.8, active: true, reducedMotion: false });
    expect(full.brighten).toBeCloseTo(ATTENTION_BRIGHTEN, 4);
  });

  it('clamps out-of-range pointer to the edge (no runaway lean)', () => {
    const o = deriveCursorAttention({ pointerX: 5, pointerY: -9, active: true, reducedMotion: false });
    expect(o.leanYaw).toBeCloseTo(ATTENTION_MAX_YAW, 5);
    expect(o.leanPitch).toBeCloseTo(ATTENTION_MAX_PITCH, 5);
    expect(o.brighten).toBeCloseTo(ATTENTION_BRIGHTEN, 5); // engagement capped at 1
  });

  it('reduced motion: no lean, but the cortex still brightens (luminance, not travel)', () => {
    const o = deriveCursorAttention({ pointerX: 1, pointerY: 1, active: true, reducedMotion: true });
    expect(o.leanYaw).toBe(0);
    expect(o.leanPitch).toBe(0);
    expect(o.brighten).toBeCloseTo(ATTENTION_BRIGHTEN, 5);
  });
});
