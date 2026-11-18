import { describe, expect, it } from 'vitest';
import { computeTrustLevel } from './trustLevel';

describe('computeTrustLevel', () => {
  it('returns unknown for missing or non-finite metrics', () => {
    expect(computeTrustLevel(null)).toBe('unknown');
    expect(computeTrustLevel({})).toBe('unknown');
    expect(computeTrustLevel({
      human_intervention_rate: NaN,
      verification_coverage: 0.8,
    })).toBe('unknown');
    expect(computeTrustLevel({
      human_intervention_rate: 0.2,
      verification_coverage: Infinity,
    })).toBe('unknown');
    expect(computeTrustLevel({
      human_intervention_rate: '0.2',
      verification_coverage: 0.8,
    })).toBe('unknown');
  });

  it('returns healthy when intervention is below 0.3 and coverage is above 0.7', () => {
    expect(computeTrustLevel({
      human_intervention_rate: 0.2,
      verification_coverage: 0.8,
    })).toBe('healthy');
  });

  it('returns critical for intervention above 0.7 or coverage below 0.3', () => {
    expect(computeTrustLevel({
      human_intervention_rate: 0.8,
      verification_coverage: 0.8,
    })).toBe('critical');
    expect(computeTrustLevel({
      human_intervention_rate: 0.2,
      verification_coverage: 0.2,
    })).toBe('critical');
  });

  it('returns attention at the threshold boundaries', () => {
    expect(computeTrustLevel({
      human_intervention_rate: 0.3,
      verification_coverage: 0.8,
    })).toBe('attention');
    expect(computeTrustLevel({
      human_intervention_rate: 0.2,
      verification_coverage: 0.7,
    })).toBe('attention');
    expect(computeTrustLevel({
      human_intervention_rate: 0.7,
      verification_coverage: 0.5,
    })).toBe('attention');
    expect(computeTrustLevel({
      human_intervention_rate: 0.5,
      verification_coverage: 0.3,
    })).toBe('attention');
  });
});
