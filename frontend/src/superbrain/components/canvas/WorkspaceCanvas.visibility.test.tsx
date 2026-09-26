import { act, cleanup, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const renderer = vi.hoisted(() => {
  let frameLoop: 'always' | 'demand' | 'never' = 'always';
  const clock = { elapsedTime: 12.5 };
  const setFrameLoop = vi.fn((next: 'always' | 'demand' | 'never') => {
    frameLoop = next;
    // Match the installed R3F setFrameloop implementation, which resets the
    // clock on a mode change. Production code must preserve scene time around it.
    clock.elapsedTime = 0;
  });

  return {
    clock,
    setFrameLoop,
    getFrameLoop: () => frameLoop,
    reset: () => {
      frameLoop = 'always';
      clock.elapsedTime = 12.5;
      setFrameLoop.mockClear();
    },
  };
});

vi.mock('@react-three/fiber', async () => {
  const React = await import('react');
  return {
    Canvas: ({ children }: { children: React.ReactNode }) => {
      const canvasChildren = React.Children.toArray(children).filter((child) => (
        !React.isValidElement(child)
        || typeof child.type !== 'string'
        || !['color', 'fog'].includes(child.type)
      ));
      return React.createElement('div', { 'data-testid': 'scene-canvas' }, canvasChildren);
    },
    useFrame: () => {},
    useThree: (select: (state: {
      clock: typeof renderer.clock;
      frameloop: 'always' | 'demand' | 'never';
      setFrameloop: typeof renderer.setFrameLoop;
    }) => unknown) => select({
      clock: renderer.clock,
      frameloop: renderer.getFrameLoop(),
      setFrameloop: renderer.setFrameLoop,
    }),
  };
});

vi.mock('@/components/QualityTierProvider', async () => {
  const React = await import('react');
  return {
    QualityTierProvider: ({ children }: { children: React.ReactNode }) => React.createElement(React.Fragment, null, children),
    useQualityTier: () => ({ tier: 'high', perfTier: 'high' }),
  };
});

vi.mock('../../core/CortexEngine', () => ({ default: () => null }));
vi.mock('./TierGovernor', () => ({ default: () => null }));
vi.mock('./WebGLErrorBoundary', async () => {
  const React = await import('react');
  return {
    WebGLErrorBoundary: ({ children }: { children: React.ReactNode }) => React.createElement(React.Fragment, null, children),
    WebGLFallback: () => null,
  };
});
vi.mock('@/lib/aiosAdapter', () => ({ startAiosPolling: () => () => {} }));
vi.mock('@/lib/cognitionBus', () => ({ subscribeCognition: () => () => {} }));
vi.mock('@/lib/lifecycleStateMachine', () => ({ notifyDirective: () => {}, tickLifecycle: () => {} }));

import WorkspaceCanvas from './WorkspaceCanvas';

describe('WorkspaceCanvas visibility scheduling', () => {
  let originalHidden: PropertyDescriptor | undefined;
  let getContext: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    renderer.reset();
    originalHidden = Object.getOwnPropertyDescriptor(document, 'hidden');
    Object.defineProperty(document, 'hidden', { configurable: true, value: false });
    act(() => document.dispatchEvent(new Event('visibilitychange')));
    getContext = vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({} as WebGLRenderingContext);
  });

  afterEach(() => {
    cleanup();
    getContext.mockRestore();
    if (originalHidden) Object.defineProperty(document, 'hidden', originalHidden);
    else Reflect.deleteProperty(document, 'hidden');
  });

  it('stops continuous scene frames while hidden and resumes without resetting scene time', () => {
    render(<WorkspaceCanvas />);
    expect(renderer.getFrameLoop()).toBe('always');
    expect(renderer.clock.elapsedTime).toBe(12.5);

    act(() => {
      Object.defineProperty(document, 'hidden', { configurable: true, value: true });
      document.dispatchEvent(new Event('visibilitychange'));
    });

    expect(renderer.setFrameLoop).toHaveBeenLastCalledWith('never');
    expect(renderer.getFrameLoop()).toBe('never');
    expect(renderer.clock.elapsedTime).toBe(12.5);
    // A queued visibility/state update must not let hidden wall time advance
    // the visual clock; waking restores the last foreground timestamp.
    renderer.clock.elapsedTime = 999;

    act(() => {
      Object.defineProperty(document, 'hidden', { configurable: true, value: false });
      document.dispatchEvent(new Event('visibilitychange'));
    });

    expect(renderer.setFrameLoop).toHaveBeenLastCalledWith('always');
    expect(renderer.getFrameLoop()).toBe('always');
    expect(renderer.clock.elapsedTime).toBe(12.5);
  });
});
