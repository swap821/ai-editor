import { describe, expect, it } from 'vitest';
import { deriveHumanTaskState, isTerminalTaskState, taskStoryStepState } from './humanTaskStory';

const base = { hasGoal: true, turnPhase: 'idle' as const, pendingApproval: false, continuity: 'fresh' as const };

describe('human task story', () => {
  it('never upgrades an idle goal into completed work', () => {
    expect(deriveHumanTaskState({ ...base, hasGoal: false })).toBe('idle');
    expect(deriveHumanTaskState(base)).toBe('understood');
  });

  it('keeps preparation, permission, work and checking distinct', () => {
    expect(deriveHumanTaskState({ ...base, turnPhase: 'planning' })).toBe('preparing');
    expect(deriveHumanTaskState({ ...base, pendingApproval: true })).toBe('needs-permission');
    expect(deriveHumanTaskState({ ...base, turnPhase: 'acting' })).toBe('working');
    expect(deriveHumanTaskState({ ...base, turnPhase: 'checking' })).toBe('checking');
  });

  it('distinguishes verified, unverified, refusal, failure, restore, stop and stale', () => {
    expect(deriveHumanTaskState({ ...base, outcome: 'verified' })).toBe('done-verified');
    expect(deriveHumanTaskState({ ...base, outcome: 'unverified' })).toBe('done-unverified');
    expect(deriveHumanTaskState({ ...base, outcome: 'refused' })).toBe('refused');
    expect(deriveHumanTaskState({ ...base, outcome: 'failed' })).toBe('failed');
    expect(deriveHumanTaskState({ ...base, outcome: 'restored' })).toBe('restored');
    expect(deriveHumanTaskState({ ...base, outcome: 'stopped' })).toBe('stopped');
    expect(deriveHumanTaskState({ ...base, continuity: 'stale' })).toBe('stale');
    expect(isTerminalTaskState('done-unverified')).toBe(true);
  });

  it('marks only the current story step as current', () => {
    expect(taskStoryStepState('working', 'asked')).toBe('complete');
    expect(taskStoryStepState('working', 'working')).toBe('current');
    expect(taskStoryStepState('working', 'checking')).toBe('upcoming');
    expect(taskStoryStepState('needs-permission', 'permission')).toBe('current');
  });
});
