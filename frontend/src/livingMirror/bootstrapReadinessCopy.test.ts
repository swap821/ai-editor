import { describe, expect, it } from 'vitest';
import { getBootstrapReadinessHumanCopy } from './bootstrapReadinessCopy';

describe('getBootstrapReadinessHumanCopy', () => {
  it('ignores failed checks for loading, ready and unavailable states', () => {
    const checks = [{ passed: false }, { passed: false }];

    expect(getBootstrapReadinessHumanCopy({ state: 'loading', checks })).toEqual({
      detail: 'Checking the local setup needed to begin.',
      failedCheckCount: 0,
    });
    expect(getBootstrapReadinessHumanCopy({ state: 'ready', checks })).toEqual({
      detail: 'GAGOS confirmed the local setup needed to begin.',
      failedCheckCount: 0,
    });
    expect(getBootstrapReadinessHumanCopy({ state: 'unavailable', checks })).toEqual({
      detail: 'GAGOS could not confirm the local setup yet.',
      failedCheckCount: 0,
    });
  });

  it('uses singular copy when exactly one check failed while blocked', () => {
    const result = getBootstrapReadinessHumanCopy({
      state: 'blocked',
      checks: [{ passed: true }, { passed: false }, { passed: true }],
    });

    expect(result).toEqual({
      detail: 'One local setup check needs attention.',
      failedCheckCount: 1,
    });
  });

  it('reports the count of failed checks when several failed while blocked', () => {
    const result = getBootstrapReadinessHumanCopy({
      state: 'blocked',
      checks: [{ passed: false }, { passed: true }, { passed: false }, { passed: false }],
    });

    expect(result).toEqual({
      detail: '3 local setup checks need attention.',
      failedCheckCount: 3,
    });
  });

  it('falls back to generic plural copy when blocked with no failed check recorded', () => {
    const noChecks = getBootstrapReadinessHumanCopy({ state: 'blocked', checks: [] });
    const allPassed = getBootstrapReadinessHumanCopy({
      state: 'blocked',
      checks: [{ passed: true }],
    });

    expect(noChecks).toEqual({
      detail: 'Some local setup checks need attention.',
      failedCheckCount: 0,
    });
    expect(allPassed).toEqual(noChecks);
  });
});
