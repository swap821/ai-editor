import { render } from '@testing-library/react';
import type { ComponentProps } from 'react';
import * as THREE from 'three';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import CompletionMemoryBead from './CompletionMemoryBead';

vi.mock('@react-three/fiber', () => ({
  useFrame: vi.fn(),
}));

import { useFrame } from '@react-three/fiber';

type Reflex = ComponentProps<typeof CompletionMemoryBead>['reflex'];

function makeReflex(overrides: Record<string, unknown> = {}): Reflex {
  return {
    state: 'active',
    tint: '#66ccff',
    targetOriginLocal: [0.2, 0.1, 0],
    targetTargetLocal: [0, 0, 0],
    beadProgress: 0.5,
    memoryOpacity: 0.8,
    intensity: 0.6,
    sequence: 1,
    ...overrides,
  } as unknown as Reflex;
}

describe('CompletionMemoryBead', () => {
  beforeEach(() => {
    // R3F elements are unknown DOM tags under jsdom; silence React's warnings about them.
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.mocked(useFrame).mockClear();
  });

  it.each(['idle', 'held'])('renders nothing while the reflex is %s', (state) => {
    const { container } = render(
      <CompletionMemoryBead reflex={makeReflex({ state })} reducedMotion={false} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when either path endpoint is missing', () => {
    const noOrigin = render(
      <CompletionMemoryBead reflex={makeReflex({ targetOriginLocal: null })} reducedMotion={false} />,
    );
    expect(noOrigin.container).toBeEmptyDOMElement();

    const noTarget = render(
      <CompletionMemoryBead reflex={makeReflex({ targetTargetLocal: null })} reducedMotion />,
    );
    expect(noTarget.container).toBeEmptyDOMElement();
  });

  it('renders the path, three trail beads, the bead and the halo for an active reflex', () => {
    const { container } = render(
      <CompletionMemoryBead reflex={makeReflex()} reducedMotion={false} />,
    );
    expect(container.querySelectorAll('group')).toHaveLength(1);
    expect(container.querySelectorAll('mesh')).toHaveLength(6);
    expect(container.querySelectorAll('torusGeometry')).toHaveLength(1);
    expect(container.querySelectorAll('sphereGeometry')).toHaveLength(4);
  });

  it('registers a frame callback that is safe to run when there is no path', () => {
    render(
      <CompletionMemoryBead reflex={makeReflex({ targetOriginLocal: null })} reducedMotion={false} />,
    );
    const calls = vi.mocked(useFrame).mock.calls;
    expect(calls.length).toBeGreaterThan(0);
    const callback = calls[0][0] as (state: { clock: { elapsedTime: number } }) => void;
    expect(() => callback({ clock: { elapsedTime: 1.5 } })).not.toThrow();
  });

  it('disposes the path geometry on unmount', () => {
    const dispose = vi.spyOn(THREE.BufferGeometry.prototype, 'dispose');
    const { unmount } = render(
      <CompletionMemoryBead reflex={makeReflex()} reducedMotion={false} />,
    );
    expect(dispose).not.toHaveBeenCalled();
    unmount();
    expect(dispose).toHaveBeenCalledTimes(1);
  });
});
