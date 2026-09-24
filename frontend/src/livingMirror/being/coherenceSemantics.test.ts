import { describe, expect, it } from 'vitest';
import { BEING_COHERENCE_SEMANTICS, coherenceSemanticsFor } from './coherenceSemantics';
import type { BeingCoherence } from './semanticKernel';

describe('being coherence semantics', () => {
  it('covers every semantic coherence state with bounded physics', () => {
    const states: BeingCoherence[] = ['fresh', 'unverified', 'stale', 'degraded', 'stopped'];
    expect(Object.keys(BEING_COHERENCE_SEMANTICS).sort()).toEqual([...states].sort());
    for (const state of states) {
      const semantics = coherenceSemanticsFor(state);
      expect(semantics.opacity).toBeGreaterThan(0);
      expect(semantics.opacity).toBeLessThanOrEqual(1);
      expect(semantics.motionScale).toBeGreaterThanOrEqual(0);
      expect(semantics.motionScale).toBeLessThanOrEqual(1);
      expect(semantics.cadence).toEqual(expect.any(String));
    }
  });

  it('keeps old or incomplete truth visibly weaker than fresh truth', () => {
    expect(coherenceSemanticsFor('stale').opacity).toBeLessThan(coherenceSemanticsFor('degraded').opacity);
    expect(coherenceSemanticsFor('degraded').opacity).toBeLessThan(coherenceSemanticsFor('fresh').opacity);
    expect(coherenceSemanticsFor('unverified').cadence).toBe('soft');
    expect(coherenceSemanticsFor('stale').cadence).toBe('discontinuous');
    expect(coherenceSemanticsFor('degraded').cadence).toBe('fragmented');
  });

  it('freezes action-bearing travel only for stopped presentation', () => {
    expect(coherenceSemanticsFor('stopped')).toMatchObject({ motionScale: 0, cadence: 'frozen' });
    expect(coherenceSemanticsFor('stale').motionScale).toBeGreaterThan(0);
  });
});
