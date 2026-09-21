import { describe, expect, it } from 'vitest';
import { computeTrustLevel } from './TrustHalo';

describe('computeTrustLevel', () => {
  it('keeps incomplete metrics unknown instead of treating them as zero', () => {
    expect(computeTrustLevel({})).toBe('unknown');
    expect(computeTrustLevel({ human_intervention_rate: 0 })).toBe('unknown');
    expect(computeTrustLevel({ verification_coverage: 0.8 })).toBe('unknown');
  });

  it('still evaluates explicitly measured zeroes', () => {
    expect(computeTrustLevel({ human_intervention_rate: 0, verification_coverage: 0.8 })).toBe('healthy');
  });
});
