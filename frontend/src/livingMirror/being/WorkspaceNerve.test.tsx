// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render } from '@testing-library/react';
import { WorkspaceNerve } from './WorkspaceNerve';
import type { WorkspaceNerveState } from './workspaceNerveState';

function makeState() {
  const geometryDispose = vi.fn();
  const particlesDispose = vi.fn();
  const state = {
    geometry: { dispose: geometryDispose },
    particles: { dispose: particlesDispose },
    uniforms: {},
    mesh: null,
    points: null,
    material: null,
  } as unknown as WorkspaceNerveState;
  return { state, geometryDispose, particlesDispose };
}

describe('WorkspaceNerve', () => {
  beforeEach(() => {
    // The R3F intrinsic elements are unknown tags to react-dom and produce warnings.
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('binds the mesh into state and hides it', () => {
    const { state } = makeState();
    const { container } = render(<WorkspaceNerve state={state} />);

    const meshEl = container.querySelector('mesh');
    expect(meshEl).not.toBeNull();
    expect(meshEl?.getAttribute('name')).toBe('workspace-nerve');
    expect(state.mesh).toBe(meshEl);
    expect(state.mesh?.visible).toBe(false);
  });

  it('binds the points into state and hides them', () => {
    const { state } = makeState();
    const { container } = render(<WorkspaceNerve state={state} />);

    const pointsEl = container.querySelector('points');
    expect(pointsEl).not.toBeNull();
    expect(state.points).toBe(pointsEl);
    expect(state.points?.visible).toBe(false);
    expect(state.points).not.toBe(state.mesh);
  });

  it('stores the mesh shader material in state', () => {
    const { state } = makeState();
    const { container } = render(<WorkspaceNerve state={state} />);

    const materialEl = container.querySelector('mesh > shadermaterial');
    expect(materialEl).not.toBeNull();
    expect(state.material).toBe(materialEl);
  });

  it('does not dispose geometry while mounted, and disposes each once on unmount', () => {
    const { state, geometryDispose, particlesDispose } = makeState();
    const { unmount } = render(<WorkspaceNerve state={state} />);

    expect(geometryDispose).not.toHaveBeenCalled();
    expect(particlesDispose).not.toHaveBeenCalled();

    unmount();

    expect(geometryDispose).toHaveBeenCalledTimes(1);
    expect(particlesDispose).toHaveBeenCalledTimes(1);
    expect(state.mesh).toBeNull();
    expect(state.points).toBeNull();
    expect(state.material).toBeNull();
  });

  it('disposes the previous state resources when given a new state', () => {
    const first = makeState();
    const second = makeState();
    const { rerender, container } = render(<WorkspaceNerve state={first.state} />);

    rerender(<WorkspaceNerve state={second.state} />);

    expect(first.geometryDispose).toHaveBeenCalledTimes(1);
    expect(first.particlesDispose).toHaveBeenCalledTimes(1);
    expect(second.geometryDispose).not.toHaveBeenCalled();
    expect(second.particlesDispose).not.toHaveBeenCalled();
    expect(second.state.mesh).toBe(container.querySelector('mesh'));
  });
});
