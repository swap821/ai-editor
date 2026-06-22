import { describe, it, expect } from 'vitest';
import { deriveDemoStatePlan, DEMO_STATE_NAMES, type DemoStateName } from './demoStates';

describe('deriveDemoStatePlan — proof-harness descriptors', () => {
  it('every canonical state name yields a well-formed plan', () => {
    for (const name of DEMO_STATE_NAMES) {
      const plan = deriveDemoStatePlan(name);
      expect(Array.isArray(plan.surfaces)).toBe(true);
      expect(typeof plan.reabsorbFocused).toBe('boolean');
      // distinct filepaths within a plan (else showContentSurface dedup-collapses)
      const paths = plan.surfaces.map((s) => s.filepath);
      expect(new Set(paths).size).toBe(paths.length);
    }
  });

  it('rest = bare body (no surfaces, no conversation)', () => {
    const p = deriveDemoStatePlan('rest');
    expect(p.surfaces).toEqual([]);
    expect(p.conversation).toBeNull();
    expect(p.reabsorbFocused).toBe(false);
  });

  it('orchestrate3 = three distinct surfaces on ascending seats (emergent conducting)', () => {
    const p = deriveDemoStatePlan('orchestrate3');
    expect(p.surfaces).toHaveLength(3);
    expect(new Set(p.surfaces.map((s) => s.filepath)).size).toBe(3);
    const seats = p.surfaces.map((s) => s.seatIndex);
    expect([...seats].sort((a, b) => a - b)).toEqual(seats); // ascending, no collision
    expect(new Set(seats).size).toBe(3);
    // structural phase is emergent from the 3 surfaces — no conversation override
    expect(p.conversation).toBeNull();
  });

  it('streaming/error/completion drive the matching conversation phase (override)', () => {
    expect(deriveDemoStatePlan('streaming').conversation).toBe('streaming');
    expect(deriveDemoStatePlan('error').conversation).toBe('error');
    expect(deriveDemoStatePlan('completion').conversation).toBe('complete');
  });

  it('reabsorbing = a surface + reabsorb flag (emergent reabsorbing phase)', () => {
    const p = deriveDemoStatePlan('reabsorbing');
    expect(p.surfaces).toHaveLength(1);
    expect(p.reabsorbFocused).toBe(true);
    expect(p.conversation).toBeNull();
  });

  it('rejects an unknown state name', () => {
    expect(() => deriveDemoStatePlan('nope' as DemoStateName)).toThrow(/unknown demo state/);
  });
});
