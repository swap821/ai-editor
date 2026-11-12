// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, renderHook } from '@testing-library/react';
import { Object3D } from 'three';
import { useBodyWorldFrame } from './useBodyWorldFrame';
import { clearBodyGroupWorldMatrix, setBodyGroupWorldMatrix } from './spineFusionBus';

vi.mock('./spineFusionBus', () => ({
  setBodyGroupWorldMatrix: vi.fn(),
  clearBodyGroupWorldMatrix: vi.fn(),
}));

type BodyRef = { current: Object3D | null };

describe('useBodyWorldFrame', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it('publishes the live matrixWorld of the body on mount and clears it on unmount', () => {
    const body = new Object3D();
    const ref: BodyRef = { current: body };

    const { unmount } = renderHook(() => useBodyWorldFrame(ref));

    expect(setBodyGroupWorldMatrix).toHaveBeenCalledTimes(1);
    const [matrixArg, bodyArg] = vi.mocked(setBodyGroupWorldMatrix).mock.calls[0] ?? [];
    expect(matrixArg).toBe(body.matrixWorld);
    expect(bodyArg).toBe(body);
    expect(clearBodyGroupWorldMatrix).not.toHaveBeenCalled();

    unmount();

    expect(clearBodyGroupWorldMatrix).toHaveBeenCalledTimes(1);
    expect(vi.mocked(clearBodyGroupWorldMatrix).mock.calls[0]?.[0]).toBe(body);
  });

  it('does nothing when the ref is empty', () => {
    const ref: BodyRef = { current: null };

    const { unmount } = renderHook(() => useBodyWorldFrame(ref));
    unmount();

    expect(setBodyGroupWorldMatrix).not.toHaveBeenCalled();
    expect(clearBodyGroupWorldMatrix).not.toHaveBeenCalled();
  });

  it('does not republish on rerender with the same ref', () => {
    const ref: BodyRef = { current: new Object3D() };

    const { rerender } = renderHook(() => useBodyWorldFrame(ref));
    rerender();
    rerender();

    expect(setBodyGroupWorldMatrix).toHaveBeenCalledTimes(1);
    expect(clearBodyGroupWorldMatrix).not.toHaveBeenCalled();
  });

  it('clears the old body and publishes the new one when the ref object changes', () => {
    const bodyA = new Object3D();
    const bodyB = new Object3D();
    const refA: BodyRef = { current: bodyA };
    const refB: BodyRef = { current: bodyB };

    const { rerender } = renderHook(({ target }: { target: BodyRef }) => useBodyWorldFrame(target), {
      initialProps: { target: refA },
    });

    rerender({ target: refB });

    expect(vi.mocked(clearBodyGroupWorldMatrix).mock.calls).toHaveLength(1);
    expect(vi.mocked(clearBodyGroupWorldMatrix).mock.calls[0]?.[0]).toBe(bodyA);

    expect(vi.mocked(setBodyGroupWorldMatrix).mock.calls).toHaveLength(2);
    const [matrixArg, bodyArg] = vi.mocked(setBodyGroupWorldMatrix).mock.calls[1] ?? [];
    expect(matrixArg).toBe(bodyB.matrixWorld);
    expect(bodyArg).toBe(bodyB);

    const clearOrder = vi.mocked(clearBodyGroupWorldMatrix).mock.invocationCallOrder[0] ?? 0;
    const secondSetOrder = vi.mocked(setBodyGroupWorldMatrix).mock.invocationCallOrder[1] ?? 0;
    expect(clearOrder).toBeLessThan(secondSetOrder);
  });
});
