import { cleanup, fireEvent, renderHook } from '@testing-library/react';
import { Vector4 } from 'three';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useBackdropControlMask } from './useBackdropControlMask';

const fiber = vi.hoisted(() => ({
  state: {
    gl: { domElement: null as HTMLCanvasElement | null },
    invalidate: vi.fn(),
  },
}));

vi.mock('@react-three/fiber', () => ({
  useThree: (selector: (state: typeof fiber.state) => unknown) => selector(fiber.state),
}));

function rect(left: number, top: number, width: number, height: number): DOMRect {
  return {
    left,
    top,
    width,
    height,
    right: left + width,
    bottom: top + height,
    x: left,
    y: top,
    toJSON: () => ({}),
  };
}

function makeUniforms() {
  return {
    uControlRects: { value: Array.from({ length: 16 }, () => new Vector4()) },
    uControlRectCount: { value: 0 },
  };
}

describe('useBackdropControlMask', () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    fiber.state.invalidate.mockReset();
  });

  it('leaves a standalone canvas unmodified', () => {
    fiber.state.gl.domElement = document.createElement('canvas');
    const uniforms = makeUniforms();

    const { result } = renderHook(() => useBackdropControlMask(uniforms));

    expect(result.current.current).toBe(false);
    expect(uniforms.uControlRectCount.value).toBe(0);
    expect(fiber.state.invalidate).not.toHaveBeenCalled();
  });

  it('measures visible controls and repaints only when the mask changes', () => {
    const host = document.createElement('div');
    host.className = 'lm-app';
    const canvas = document.createElement('canvas');
    const control = document.createElement('div');
    control.className = 'lm-header';
    host.append(canvas, control);
    fiber.state.gl.domElement = canvas;

    vi.spyOn(canvas, 'getBoundingClientRect').mockReturnValue(rect(100, 50, 200, 100));
    vi.spyOn(control, 'getBoundingClientRect').mockReturnValue(rect(120, 70, 40, 20));
    const uniforms = makeUniforms();

    const { result } = renderHook(() => useBackdropControlMask(uniforms));

    expect(result.current.current).toBe(true);
    expect(uniforms.uControlRectCount.value).toBe(1);
    expect(uniforms.uControlRects.value[0].toArray()).toEqual([0.06, 0.52, 0.34, 0.88]);
    expect(fiber.state.invalidate).toHaveBeenCalledOnce();

    fiber.state.invalidate.mockClear();
    fireEvent.resize(window);
    expect(fiber.state.invalidate).not.toHaveBeenCalled();

    vi.mocked(control.getBoundingClientRect).mockReturnValue(rect(110, 60, 20, 10));
    fireEvent.resize(window);
    expect(uniforms.uControlRects.value[0].toArray()).toEqual([0.01, 0.72, 0.19, 0.98]);
    expect(fiber.state.invalidate).toHaveBeenCalledOnce();
  });

  it('fails quiet when the canvas has no usable layout and stops listening on unmount', () => {
    const host = document.createElement('div');
    host.className = 'lm-app';
    const canvas = document.createElement('canvas');
    host.append(canvas);
    fiber.state.gl.domElement = canvas;
    const bounds = vi.spyOn(canvas, 'getBoundingClientRect').mockReturnValue(rect(0, 0, 100, 100));
    const uniforms = makeUniforms();

    const { result, unmount } = renderHook(() => useBackdropControlMask(uniforms));
    bounds.mockReturnValue(rect(0, 0, 0, 100));
    fireEvent.resize(window);

    expect(uniforms.uControlRectCount.value).toBe(-1);
    expect(fiber.state.invalidate).toHaveBeenCalledOnce();

    unmount();
    expect(result.current.current).toBe(false);
    bounds.mockReturnValue(rect(0, 0, 100, 100));
    fireEvent.resize(window);
    expect(uniforms.uControlRectCount.value).toBe(-1);
    expect(fiber.state.invalidate).toHaveBeenCalledOnce();
  });
});
