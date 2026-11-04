import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  __resetAuroraBridgeForTests,
  getAuroraState,
  setAuroraIntensity,
  subscribeAurora,
} from './verifyAuroraBridge';

describe('verifyAuroraBridge', () => {
  beforeEach(() => {
    __resetAuroraBridgeForTests();
  });

  it('starts with zero intensity and no verdict', () => {
    expect(getAuroraState()).toEqual({ intensity: 0, verdict: null });
  });

  it('updates intensity and keeps the previous verdict when none is given', () => {
    setAuroraIntensity(0.5, 'pass');
    expect(getAuroraState()).toEqual({ intensity: 0.5, verdict: 'pass' });

    setAuroraIntensity(0.8);
    expect(getAuroraState()).toEqual({ intensity: 0.8, verdict: 'pass' });

    setAuroraIntensity(0.2, 'fail');
    expect(getAuroraState()).toEqual({ intensity: 0.2, verdict: 'fail' });
  });

  it('clears the verdict when null is passed explicitly', () => {
    setAuroraIntensity(1, 'caution');
    setAuroraIntensity(0, null);
    expect(getAuroraState()).toEqual({ intensity: 0, verdict: null });
  });

  it('calls a new subscriber immediately and again on every update', () => {
    const listener = vi.fn();
    subscribeAurora(listener);

    expect(listener).toHaveBeenCalledTimes(1);
    expect(listener).toHaveBeenLastCalledWith({ intensity: 0, verdict: null });

    setAuroraIntensity(0.7, 'pass');
    expect(listener).toHaveBeenCalledTimes(2);
    expect(listener).toHaveBeenLastCalledWith({ intensity: 0.7, verdict: 'pass' });
  });

  it('stops notifying after unsubscribe without affecting other listeners', () => {
    const first = vi.fn();
    const second = vi.fn();
    const unsubscribeFirst = subscribeAurora(first);
    subscribeAurora(second);

    unsubscribeFirst();
    setAuroraIntensity(0.4, 'fail');

    expect(first).toHaveBeenCalledTimes(1);
    expect(second).toHaveBeenCalledTimes(2);
    expect(second).toHaveBeenLastCalledWith({ intensity: 0.4, verdict: 'fail' });
  });

  it('reset restores the initial state and drops all listeners', () => {
    const listener = vi.fn();
    subscribeAurora(listener);
    setAuroraIntensity(0.9, 'caution');
    listener.mockClear();

    __resetAuroraBridgeForTests();

    expect(getAuroraState()).toEqual({ intensity: 0, verdict: null });
    setAuroraIntensity(0.3);
    expect(listener).not.toHaveBeenCalled();
  });
});
