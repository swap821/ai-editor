// @vitest-environment jsdom
import { act, cleanup, renderHook } from '@testing-library/react';
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { FeatureGate, useFeatureGate } from './FeatureGate';

let hidden = false;

function setHidden(value: boolean) {
  hidden = value;
  act(() => {
    document.dispatchEvent(new Event('visibilitychange'));
  });
}

describe('FeatureGate', () => {
  beforeAll(() => {
    Object.defineProperty(document, 'hidden', {
      configurable: true,
      get: () => hidden,
    });
  });

  afterAll(() => {
    Reflect.deleteProperty(document, 'hidden');
  });

  beforeEach(() => {
    // Normalise the singleton to the awake state before every test.
    setHidden(false);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('notifies subscribers only when the sleep state actually changes', () => {
    const listener = vi.fn();
    FeatureGate.subscribe(listener);

    setHidden(true);

    expect(FeatureGate.isSleeping).toBe(true);
    expect(listener).toHaveBeenCalledExactlyOnceWith(true);

    // Same state again: no extra notification.
    setHidden(true);
    expect(listener).toHaveBeenCalledTimes(1);

    setHidden(false);
    expect(FeatureGate.isSleeping).toBe(false);
    expect(listener).toHaveBeenCalledTimes(2);
    expect(listener).toHaveBeenLastCalledWith(false);
  });

  it('stops notifying a listener once it unsubscribes, without affecting others', () => {
    const removed = vi.fn();
    const kept = vi.fn();
    const unsubscribe = FeatureGate.subscribe(removed);
    FeatureGate.subscribe(kept);

    unsubscribe();
    setHidden(true);

    expect(removed).not.toHaveBeenCalled();
    expect(kept).toHaveBeenCalledExactlyOnceWith(true);
  });

  it('useFeatureGate follows sleep and wake events', () => {
    const { result } = renderHook(() => useFeatureGate());
    expect(result.current).toBe(false);

    setHidden(true);
    expect(result.current).toBe(true);

    setHidden(false);
    expect(result.current).toBe(false);
  });

  it('useFeatureGate starts asleep when the gate is already sleeping', () => {
    setHidden(true);

    const { result } = renderHook(() => useFeatureGate());

    expect(result.current).toBe(true);
  });

  it('dispose detaches the document listener and clears subscribers', () => {
    const listener = vi.fn();
    FeatureGate.subscribe(listener);

    FeatureGate.dispose();
    setHidden(true);

    expect(listener).not.toHaveBeenCalled();
    expect(FeatureGate.isSleeping).toBe(false);
  });
});
