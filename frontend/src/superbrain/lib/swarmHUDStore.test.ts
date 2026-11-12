import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  endSwarmCaste,
  getSwarmHUDState,
  markSwarmCloudSubtask,
  resetSwarmHUD,
  startSwarmCaste,
  startSwarmPlan,
  subscribeSwarmHUD,
} from './swarmHUDStore';

describe('swarmHUDStore', () => {
  beforeEach(() => {
    resetSwarmHUD();
  });

  afterEach(() => {
    resetSwarmHUD();
  });

  it('starts from a clean, unobserved state after reset', () => {
    startSwarmPlan(['a']);
    resetSwarmHUD();
    expect(getSwarmHUDState()).toEqual({
      hasObserved: false,
      active: false,
      plan: [],
      activeCastes: [],
      completedLegs: 0,
      cloudIndices: [],
    });
  });

  it('startSwarmPlan stores the plan and clears prior progress', () => {
    startSwarmCaste('scout');
    endSwarmCaste('scout');
    markSwarmCloudSubtask(1);
    startSwarmPlan(['one', 'two']);
    expect(getSwarmHUDState()).toEqual({
      hasObserved: true,
      active: true,
      plan: ['one', 'two'],
      activeCastes: [],
      completedLegs: 0,
      cloudIndices: [],
    });
  });

  it('tracks castes starting and ending, counting completed legs', () => {
    startSwarmPlan(['x']);
    startSwarmCaste('scout');
    startSwarmCaste('worker');
    expect(getSwarmHUDState().activeCastes).toEqual(['scout', 'worker']);
    expect(getSwarmHUDState().active).toBe(true);

    endSwarmCaste('scout');
    expect(getSwarmHUDState().activeCastes).toEqual(['worker']);
    expect(getSwarmHUDState().completedLegs).toBe(1);

    endSwarmCaste('worker');
    expect(getSwarmHUDState().activeCastes).toEqual([]);
    expect(getSwarmHUDState().completedLegs).toBe(2);
  });

  it('marks each cloud subtask index only once', () => {
    markSwarmCloudSubtask(2);
    markSwarmCloudSubtask(0);
    markSwarmCloudSubtask(2);
    expect(getSwarmHUDState().cloudIndices).toEqual([2, 0]);
    expect(getSwarmHUDState().hasObserved).toBe(true);
  });

  it('does not notify listeners for a duplicate cloud index', () => {
    markSwarmCloudSubtask(5);
    const listener = vi.fn();
    const unsubscribe = subscribeSwarmHUD(listener);
    expect(listener).toHaveBeenCalledTimes(1);
    markSwarmCloudSubtask(5);
    expect(listener).toHaveBeenCalledTimes(1);
    unsubscribe();
  });

  it('subscribers get the current state immediately and each update until unsubscribed', () => {
    const listener = vi.fn();
    const unsubscribe = subscribeSwarmHUD(listener);
    expect(listener).toHaveBeenCalledTimes(1);
    expect(listener.mock.calls[0][0].hasObserved).toBe(false);

    startSwarmPlan(['p']);
    expect(listener).toHaveBeenCalledTimes(2);
    expect(listener.mock.calls[1][0].plan).toEqual(['p']);

    unsubscribe();
    startSwarmCaste('scout');
    expect(listener).toHaveBeenCalledTimes(2);
  });
});
