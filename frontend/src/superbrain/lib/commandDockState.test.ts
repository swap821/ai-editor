import { describe, it, expect } from 'vitest';
import { deriveCommandDockState, type CommandDockStateInput } from './commandDockState';

const base: CommandDockStateInput = {
  hasText: false,
  focused: false,
  listening: false,
  sending: false,
  working: false,
  reducedMotion: false,
};

describe('deriveCommandDockState', () => {
  it('rest: calm + present, not engaged, no pulse', () => {
    const s = deriveCommandDockState(base);
    expect(s.active).toBe(false);
    expect(s.pulse).toBe('none');
    expect(s.particleFlow).toBe(0);
    expect(s.minimized).toBe(false);
    expect(s.intensity).toBeGreaterThan(0.2);
    expect(s.intensity).toBeLessThan(0.6);
  });

  it('focused/typing: engaged, brighter, pulses up the stem', () => {
    const s = deriveCommandDockState({ ...base, focused: true, hasText: true });
    expect(s.active).toBe(true);
    expect(s.pulse).toBe('up');
    expect(s.particleFlow).toBeGreaterThan(0);
    expect(s.intensity).toBeGreaterThan(0.7);
  });

  it('listening counts as engaged', () => {
    expect(deriveCommandDockState({ ...base, listening: true }).active).toBe(true);
  });

  it('sending: full bead flow up the stem', () => {
    const s = deriveCommandDockState({ ...base, sending: true });
    expect(s.pulse).toBe('up');
    expect(s.particleFlow).toBe(1);
    expect(s.intensity).toBeGreaterThan(0.7);
  });

  it('working (idle dock): subordinate — dim + minimized, yields to the work', () => {
    const s = deriveCommandDockState({ ...base, working: true });
    expect(s.minimized).toBe(true);
    expect(s.intensity).toBeLessThan(0.3);
  });

  it('working BUT focused: the operator wins — engaged, not minimized', () => {
    const s = deriveCommandDockState({ ...base, working: true, focused: true });
    expect(s.minimized).toBe(false);
    expect(s.active).toBe(true);
    expect(s.intensity).toBeGreaterThan(0.7);
  });

  it('reduced motion: no travelling pulse or beads (luminance still set)', () => {
    const s = deriveCommandDockState({ ...base, focused: true, sending: true, reducedMotion: true });
    expect(s.pulse).toBe('none');
    expect(s.particleFlow).toBe(0);
    expect(s.intensity).toBeGreaterThan(0.7); // brightness still conveys engagement
  });
});
