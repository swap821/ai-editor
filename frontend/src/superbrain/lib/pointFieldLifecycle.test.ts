import { describe, it, expect } from 'vitest';
import { lifecycleTargets } from './pointFieldLifecycle';
import type { OrganismLifecyclePhase } from './organismLifecycle';

const ALL_PHASES: OrganismLifecyclePhase[] = [
  'booting',
  'arrival',
  'rest',
  'attentive',
  'intake',
  'materializing',
  'working',
  'conducting',
  'approval_hold',
  'error_repair',
  'completion_settle',
  'reabsorbing',
];

describe('lifecycleTargets', () => {
  it('arrival → arrival === 1, reabsorb === 0', () => {
    const t = lifecycleTargets('arrival');
    expect(t.arrival).toBe(1);
    expect(t.reabsorb).toBe(0);
  });

  it('booting → arrival === 0, grow === 0 (not yet grown/condensed)', () => {
    const t = lifecycleTargets('booting');
    expect(t.arrival).toBe(0);
    expect(t.grow).toBe(0);
  });

  it('rest → grow === 1, arrival === 1, reabsorb === 0, flow < 0.3', () => {
    const t = lifecycleTargets('rest');
    expect(t.grow).toBe(1);
    expect(t.arrival).toBe(1);
    expect(t.reabsorb).toBe(0);
    expect(t.flow).toBeLessThan(0.3);
  });

  it('working flow > rest flow', () => {
    const working = lifecycleTargets('working');
    const rest = lifecycleTargets('rest');
    expect(working.flow).toBeGreaterThan(rest.flow);
  });

  it('reabsorbing → reabsorb === 0 (the being persists; only the slab dies)', () => {
    // Poster phase 7: a work-tab reabsorption must NOT dissolve the brain+spine
    // cloud — "the voyage never stops". The slab death is owned elsewhere.
    const t = lifecycleTargets('reabsorbing');
    expect(t.reabsorb).toBe(0);
  });

  it('unknown phase falls back to rest row', () => {
    const unknown = lifecycleTargets('not_a_real_phase' as OrganismLifecyclePhase);
    const rest = lifecycleTargets('rest');
    expect(unknown).toEqual(rest);
  });

  it('every real phase returns all four fields as finite numbers in [0,1]', () => {
    for (const phase of ALL_PHASES) {
      const t = lifecycleTargets(phase);
      for (const [key, val] of Object.entries(t) as [string, number][]) {
        expect(
          Number.isFinite(val),
          `phase=${phase} field=${key} should be finite`,
        ).toBe(true);
        expect(
          val >= 0 && val <= 1,
          `phase=${phase} field=${key} value=${val} should be in [0,1]`,
        ).toBe(true);
      }
    }
  });
});
