import { describe, expect, it } from 'vitest';
import { guidedTaskStatus, guidedTaskVerification } from './guidedTaskPresentation';
import type { CouncilMission } from './contracts';

function mission(overrides: Record<string, unknown>): CouncilMission {
  return { status: 'unknown', ...overrides } as unknown as CouncilMission;
}

describe('guidedTaskStatus', () => {
  it('asks for permission first, even when the status says running', () => {
    expect(guidedTaskStatus(mission({ approvalNeeded: true, status: 'running' })))
      .toBe('Permission needed before GAGOS can continue.');
  });

  it('does not treat approvalNeeded=false as a permission request', () => {
    expect(guidedTaskStatus(mission({ approvalNeeded: false, status: 'running' })))
      .toBe('In progress.');
  });

  it.each([
    ['active', 'In progress.'],
    ['streaming', 'In progress.'],
    ['failed', 'This task needs attention.'],
    ['error', 'This task needs attention.'],
    ['refused', 'GAGOS did not continue.'],
    ['declined', 'GAGOS did not continue.'],
    ['completed', 'Finished.'],
    ['verified', 'Finished.'],
    ['queued', 'Preparing.'],
    ['deliberating', 'Preparing.'],
  ])('maps status %s to "%s"', (status, expected) => {
    expect(guidedTaskStatus(mission({ status }))).toBe(expected);
  });

  it('matches statuses case-insensitively', () => {
    expect(guidedTaskStatus(mission({ status: 'RUNNING' }))).toBe('In progress.');
    expect(guidedTaskStatus(mission({ status: 'Done' }))).toBe('Finished.');
  });

  it('falls back to unavailable for unrecognised statuses', () => {
    expect(guidedTaskStatus(mission({ status: 'mystery' }))).toBe('Status unavailable.');
  });
});

describe('guidedTaskVerification', () => {
  it('reports a recorded verified result', () => {
    expect(guidedTaskVerification(mission({ verificationPassed: true })))
      .toBe('Verified result recorded.');
  });

  it('reports a failed check', () => {
    expect(guidedTaskVerification(mission({ verificationPassed: false })))
      .toBe('The result did not pass its check.');
  });

  it('reports unavailable when verification is absent or null', () => {
    const expected = 'Verification status is not available yet.';
    expect(guidedTaskVerification(mission({}))).toBe(expected);
    expect(guidedTaskVerification(mission({ verificationPassed: null }))).toBe(expected);
  });
});
