import { render } from '@testing-library/react';
import type { ComponentProps } from 'react';
import { describe, expect, it } from 'vitest';
import { WorkspaceRimPoints } from './WorkspaceRimPoints';

type RimState = ComponentProps<typeof WorkspaceRimPoints>['state'];

function makeState(): RimState {
  return {
    points: null,
    material: null,
    positions: new Float32Array(6),
    normals: new Float32Array(4),
    data: new Float32Array(4),
    returnAlpha: new Float32Array(2),
    uniforms: {},
  } as unknown as RimState;
}

describe('WorkspaceRimPoints', () => {
  it('registers the points object on the state and hides it initially', () => {
    const state = makeState();
    render(<WorkspaceRimPoints state={state} />);

    const points = state.points as unknown as (Element & { visible?: boolean }) | null;
    expect(points).not.toBeNull();
    expect(points?.localName).toBe('points');
    expect(points?.visible).toBe(false);
  });

  it('registers the shader material on the state', () => {
    const state = makeState();
    render(<WorkspaceRimPoints state={state} />);

    const material = state.material as unknown as Element | null;
    expect(material).not.toBeNull();
    expect(material?.localName).toBe('shadermaterial');
  });

  it('clears the state references on unmount', () => {
    const state = makeState();
    const { unmount } = render(<WorkspaceRimPoints state={state} />);
    expect(state.points).not.toBeNull();
    expect(state.material).not.toBeNull();

    unmount();

    expect(state.points).toBeNull();
    expect(state.material).toBeNull();
  });

  it('moves the bindings to a new state object when the state prop changes', () => {
    const first = makeState();
    const second = makeState();
    const { rerender } = render(<WorkspaceRimPoints state={first} />);
    expect(first.points).not.toBeNull();

    rerender(<WorkspaceRimPoints state={second} />);

    expect(first.points).toBeNull();
    expect(first.material).toBeNull();
    expect(second.points).not.toBeNull();
    expect(second.material).not.toBeNull();
  });
});
