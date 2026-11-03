// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import {
  getRendererFallbackPresentation,
  rendererFallbackCopy,
  rendererFallbackVisible,
  setRendererFallbackPresentation,
  subscribeRendererFallbackPresentation,
  useRendererFallbackPresentation,
} from './rendererFallbackPresentation';

afterEach(() => {
  setRendererFallbackPresentation(false);
  document.body.innerHTML = '';
});

describe('rendererFallbackVisible', () => {
  it('detects the managed fallback element inside a given root only', () => {
    const withFallback = document.createElement('div');
    withFallback.innerHTML = '<section><div class="webgl-fallback"></div></section>';
    const without = document.createElement('div');
    without.innerHTML = '<canvas></canvas><div class="other"></div>';

    expect(rendererFallbackVisible(withFallback)).toBe(true);
    expect(rendererFallbackVisible(without)).toBe(false);
  });

  it('searches the global document when no root is given', () => {
    expect(rendererFallbackVisible()).toBe(false);
    document.body.innerHTML = '<div class="webgl-fallback"></div>';
    expect(rendererFallbackVisible()).toBe(true);
  });
});

describe('fallback presentation store', () => {
  it('notifies subscribers only when the value changes and stops after unsubscribe', () => {
    const listener = vi.fn();
    const unsubscribe = subscribeRendererFallbackPresentation(listener);

    expect(getRendererFallbackPresentation()).toBe(false);
    setRendererFallbackPresentation(false);
    expect(listener).not.toHaveBeenCalled();

    setRendererFallbackPresentation(true);
    expect(getRendererFallbackPresentation()).toBe(true);
    expect(listener).toHaveBeenCalledTimes(1);

    setRendererFallbackPresentation(true);
    expect(listener).toHaveBeenCalledTimes(1);

    unsubscribe();
    setRendererFallbackPresentation(false);
    expect(getRendererFallbackPresentation()).toBe(false);
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it('keeps independent subscribers each notified', () => {
    const a = vi.fn();
    const b = vi.fn();
    const offA = subscribeRendererFallbackPresentation(a);
    const offB = subscribeRendererFallbackPresentation(b);

    setRendererFallbackPresentation(true);
    expect(a).toHaveBeenCalledTimes(1);
    expect(b).toHaveBeenCalledTimes(1);

    offA();
    setRendererFallbackPresentation(false);
    expect(a).toHaveBeenCalledTimes(1);
    expect(b).toHaveBeenCalledTimes(2);
    offB();
  });
});

describe('useRendererFallbackPresentation', () => {
  it('reflects store updates in rendered hook output', () => {
    const { result } = renderHook(() => useRendererFallbackPresentation());
    expect(result.current).toBe(false);

    act(() => setRendererFallbackPresentation(true));
    expect(result.current).toBe(true);

    act(() => setRendererFallbackPresentation(false));
    expect(result.current).toBe(false);
  });

  it('reads the current value on mount', () => {
    setRendererFallbackPresentation(true);
    const { result } = renderHook(() => useRendererFallbackPresentation());
    expect(result.current).toBe(true);
  });
});

describe('rendererFallbackCopy', () => {
  it('tells the user visuals are down while controls still work', () => {
    expect(rendererFallbackCopy.title).toBe('Visual organism unavailable.');
    expect(rendererFallbackCopy.body).toBe('GAGOS controls are still working.');
    expect(rendererFallbackCopy.retry).toBe('Use the scene retry control to try again.');
  });
});
