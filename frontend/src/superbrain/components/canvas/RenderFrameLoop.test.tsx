import { render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import RenderFrameLoop from './RenderFrameLoop';

const fiber = vi.hoisted(() => ({
  state: {} as Record<string, unknown>,
  frameCb: null as ((s: unknown) => void) | null,
}));

vi.mock('@react-three/fiber', () => ({
  addEffect: () => () => {},
  addAfterEffect: () => () => {},
  useFrame: (cb: (s: unknown) => void) => {
    fiber.frameCb = cb;
  },
  useThree: (selector: (s: unknown) => unknown) => selector(fiber.state),
}));

function makeState(frameloop: 'always' | 'demand' | 'never') {
  const clock = { elapsedTime: 5, getDelta: vi.fn() };
  const state = {
    frameloop,
    internal: { active: true, frames: 0 },
    invalidate: vi.fn(),
    clock,
    size: { width: 100, height: 100, left: 0, top: 0 },
    gl: { domElement: document.createElement('canvas') },
    setFrameloop: vi.fn((next: 'always' | 'demand' | 'never') => {
      state.frameloop = next;
      clock.elapsedTime = 0; // R3F resets elapsed time on every switch
    }),
    get: () => state,
  };
  return state;
}

function stubReducedMotion(reduced: boolean) {
  vi.stubGlobal(
    'matchMedia',
    vi.fn((query: string) => ({
      matches: reduced,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  );
}

describe('RenderFrameLoop', () => {
  let state: ReturnType<typeof makeState>;

  beforeEach(() => {
    fiber.frameCb = null;
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('switches to an always-running loop and preserves elapsed time when motion is allowed', () => {
    stubReducedMotion(false);
    state = makeState('demand');
    fiber.state = state;

    const { container } = render(<RenderFrameLoop sleeping={false} />);

    expect(container).toBeEmptyDOMElement();
    expect(state.setFrameloop).toHaveBeenCalledWith('always');
    expect(state.clock.elapsedTime).toBe(5);
    expect(state.invalidate).not.toHaveBeenCalled();
  });

  it('pauses the loop and drains queued frames while sleeping', () => {
    stubReducedMotion(false);
    state = makeState('always');
    state.internal.frames = 3;
    fiber.state = state;

    render(<RenderFrameLoop sleeping />);

    expect(state.setFrameloop).toHaveBeenCalledWith('never');
    expect(state.internal.frames).toBe(0);
    expect(state.clock.elapsedTime).toBe(5);
    expect(state.invalidate).not.toHaveBeenCalled();
  });

  it('under reduced motion paints on demand, settles for a finite window, and stops listening on unmount', () => {
    stubReducedMotion(true);
    state = makeState('demand');
    fiber.state = state;
    const now = vi.spyOn(performance, 'now').mockReturnValue(1000);

    const { unmount } = render(<RenderFrameLoop sleeping={false} />);

    expect(state.setFrameloop).not.toHaveBeenCalled();
    expect(state.invalidate).toHaveBeenCalled();

    // Inside the settle window every frame requests another one.
    state.invalidate.mockClear();
    now.mockReturnValue(1500);
    fiber.frameCb?.(state);
    expect(state.invalidate).toHaveBeenCalledTimes(1);

    // After the window the loop releases the RAF.
    state.invalidate.mockClear();
    now.mockReturnValue(1000 + 10000);
    fiber.frameCb?.(state);
    expect(state.invalidate).not.toHaveBeenCalled();

    // User input wakes a frame.
    window.dispatchEvent(new Event('keydown'));
    expect(state.invalidate).toHaveBeenCalledTimes(1);

    unmount();
    state.invalidate.mockClear();
    window.dispatchEvent(new Event('keydown'));
    expect(state.invalidate).not.toHaveBeenCalled();
  });
});
