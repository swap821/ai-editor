import { act, cleanup, render } from '@testing-library/react';
import * as THREE from 'three';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import BrainPointField from './BrainPointField';

type FrameState = {
  camera: THREE.Camera;
  size: { width: number; height: number };
  clock: { elapsedTime: number };
  pointer: { x: number; y: number };
};
type FrameCallback = (state: FrameState, delta: number) => void;

const fiber = vi.hoisted(() => ({
  frameCallbacks: [] as unknown[],
  getPixelRatio: vi.fn(() => 2),
}));

vi.mock('@react-three/fiber', () => ({
  useFrame: (cb: unknown) => {
    fiber.frameCallbacks.push(cb);
  },
  useThree: (selector: (s: unknown) => unknown) =>
    selector({
      gl: { getPixelRatio: fiber.getPixelRatio },
      get: () => ({ size: { width: 800, height: 600 } }),
    }),
}));

function makeUniforms() {
  return {
    uTime: { value: 0 },
    uPosture: { value: new THREE.Color(1, 1, 1) },
    uPostureTint: { value: new THREE.Color(1, 1, 1) },
    uBreath: { value: 0 },
    uArrival: { value: 0 },
    uIgnite: { value: 0 },
  };
}

describe('BrainPointField', () => {
  beforeEach(() => {
    fiber.frameCallbacks.length = 0;
    fiber.getPixelRatio.mockClear();
    vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.spyOn(console, 'warn').mockImplementation(() => {});
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('reads the renderer pixel ratio on mount and registers a frame callback', () => {
    render(
      <BrainPointField
        kind="spine"
        count={64}
        uniforms={makeUniforms() as never}
      />,
    );
    expect(fiber.getPixelRatio).toHaveBeenCalled();
    expect(fiber.frameCallbacks.length).toBeGreaterThan(0);
  });

  it('re-reads the pixel ratio on window resize and stops after unmount', () => {
    const { unmount } = render(
      <BrainPointField
        kind="spine"
        count={64}
        uniforms={makeUniforms() as never}
      />,
    );
    const afterMount = fiber.getPixelRatio.mock.calls.length;

    act(() => {
      window.dispatchEvent(new Event('resize'));
    });
    const afterResize = fiber.getPixelRatio.mock.calls.length;
    expect(afterResize).toBe(afterMount + 1);

    unmount();
    const afterUnmount = fiber.getPixelRatio.mock.calls.length;
    window.dispatchEvent(new Event('resize'));
    expect(fiber.getPixelRatio.mock.calls.length).toBe(afterUnmount);
  });

  it('keeps the pixel ratio fresh on every rendered frame', () => {
    render(
      <BrainPointField
        kind="spine"
        count={64}
        uniforms={makeUniforms() as never}
      />,
    );
    const frame = fiber.frameCallbacks[fiber.frameCallbacks.length - 1] as FrameCallback;
    const state: FrameState = {
      camera: new THREE.PerspectiveCamera(45, 800 / 600, 0.1, 100),
      size: { width: 800, height: 600 },
      clock: { elapsedTime: 1 },
      pointer: { x: 0, y: 0 },
    };
    const before = fiber.getPixelRatio.mock.calls.length;
    frame(state, 0.016);
    expect(fiber.getPixelRatio.mock.calls.length).toBe(before + 1);
    frame(state, 0.016);
    expect(fiber.getPixelRatio.mock.calls.length).toBe(before + 2);
  });
});
