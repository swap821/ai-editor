import { render } from '@testing-library/react';
import type { ComponentProps } from 'react';
import * as THREE from 'three';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import NeuralAura from './NeuralAura';

type FrameCallback = (state: unknown, delta: number) => void;

const frame = vi.hoisted(() => ({ callback: null as null | ((state: unknown, delta: number) => void) }));

vi.mock('@react-three/fiber', () => ({
  useFrame: (callback: FrameCallback) => {
    frame.callback = callback;
  },
}));

type AuraProps = ComponentProps<typeof NeuralAura>;

function makeUniforms(): AuraProps['uniforms'] {
  return {
    uTime: { value: 0 },
    uBreath: { value: 0 },
    uBurst: { value: 0 },
    uHold: { value: 0 },
  } as unknown as AuraProps['uniforms'];
}

function makeSource(): THREE.Object3D {
  const root = new THREE.Group();
  root.add(new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), new THREE.MeshBasicMaterial()));
  return root;
}

describe('NeuralAura', () => {
  beforeEach(() => {
    frame.callback = null;
    // Three.js scene tags are unknown DOM elements under react-dom; silence the warnings.
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => vi.restoreAllMocks());

  it('renders membrane and nucleus shells at the default budget with their scales', () => {
    const { container } = render(
      <NeuralAura activity={0.5} mode="observe" source={makeSource()} uniforms={makeUniforms()} />,
    );

    expect(container.querySelectorAll('primitive')).toHaveLength(2);
    const shellGroups = Array.from(container.querySelectorAll('primitive')).map((node) => node.parentElement);
    expect(shellGroups[0]?.getAttribute('scale')).toBe('1.025');
    expect(shellGroups[1]?.getAttribute('scale')).toBe('0.85');
    expect(container.querySelector('points')).not.toBeNull();
  });

  it('drops the nucleus shell under a reduced shell budget', () => {
    const { container } = render(
      <NeuralAura activity={0.5} mode="observe" source={makeSource()} uniforms={makeUniforms()} shells={1} />,
    );

    const primitives = container.querySelectorAll('primitive');
    expect(primitives).toHaveLength(1);
    expect(primitives[0]?.parentElement?.getAttribute('scale')).toBe('1.025');
  });

  it('smooths spark activity toward the clamped target each frame', () => {
    const uniforms = makeUniforms();
    const source = makeSource();
    const props = { mode: 'observe', source, uniforms } as const;
    const { container, rerender } = render(<NeuralAura {...props} activity={0} />);

    const sparkMaterial = container.querySelector('shadermaterial') as unknown as {
      uniforms?: { uActivity: { value: number } };
    };
    sparkMaterial.uniforms = { uActivity: { value: -1 } };

    // Out-of-range activity must be clamped to 1 before damping.
    rerender(<NeuralAura {...props} activity={5} />);
    expect(frame.callback).not.toBeNull();
    frame.callback?.({}, 0.1);

    const expected = 1 - Math.exp(-4 * 0.1);
    expect(sparkMaterial.uniforms.uActivity.value).toBeCloseTo(expected, 4);

    frame.callback?.({}, 0.1);
    expect(sparkMaterial.uniforms.uActivity.value).toBeGreaterThan(expected);
    expect(sparkMaterial.uniforms.uActivity.value).toBeLessThanOrEqual(1);
  });
});
