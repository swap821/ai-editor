import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render } from '@testing-library/react';
import type { ComponentProps } from 'react';
import * as THREE from 'three';
import SignalParticles from './SignalParticles';

type Uniforms = ComponentProps<typeof SignalParticles>['uniforms'];
type FrameState = { viewport: { dpr: number } };
type FrameCallback = (state: FrameState, delta: number) => void;

const mocks = vi.hoisted(() => ({
  frame: { current: null as null | ((state: unknown, delta: number) => void) },
  build: vi.fn(),
}));

vi.mock('@react-three/fiber', () => ({
  useFrame: (cb: (state: unknown, delta: number) => void) => {
    mocks.frame.current = cb;
  },
}));

vi.mock('./ConductionPaths', () => ({
  buildFireflyGeometry: mocks.build,
}));

vi.mock('./RoutingShader', () => ({}));

function makeUniforms() {
  return {
    uTime: { value: 1.5 },
    uWaveOrigins: { value: [1, 2, 3] },
    uWaveTimes: { value: [4, 5] },
    uPosture: { value: { posture: true } },
    uPostureTint: { value: { tint: true } },
  } as unknown as Uniforms;
}

function runFrame(state: FrameState, delta: number) {
  const cb = mocks.frame.current as FrameCallback | null;
  if (!cb) throw new Error('useFrame callback was not registered');
  cb(state, delta);
}

function getMaterial(container: HTMLElement) {
  const el = container.querySelector('routingmaterial');
  if (!el) throw new Error('routingMaterial was not rendered');
  return el as unknown as Record<string, unknown>;
}

beforeEach(() => {
  mocks.frame.current = null;
  mocks.build.mockReset();
  mocks.build.mockImplementation(() => ({ dispose: vi.fn() }));
});

afterEach(() => {
  cleanup();
});

describe('SignalParticles geometry', () => {
  it('builds the firefly geometry from the source with the default count of 320', () => {
    const source = new THREE.Object3D();
    render(<SignalParticles activity={0} source={source} uniforms={makeUniforms()} />);

    expect(mocks.build).toHaveBeenCalledTimes(1);
    expect(mocks.build).toHaveBeenCalledWith(source, 320);
  });

  it('rebuilds with a new count and disposes the old geometry, then the last one on unmount', () => {
    const source = new THREE.Object3D();
    const uniforms = makeUniforms();
    const { rerender, unmount } = render(
      <SignalParticles activity={0} source={source} uniforms={uniforms} count={50} />,
    );
    expect(mocks.build).toHaveBeenLastCalledWith(source, 50);
    const first = mocks.build.mock.results[0].value as { dispose: ReturnType<typeof vi.fn> };

    rerender(<SignalParticles activity={0} source={source} uniforms={uniforms} count={80} />);
    expect(mocks.build).toHaveBeenCalledTimes(2);
    expect(mocks.build).toHaveBeenLastCalledWith(source, 80);
    const second = mocks.build.mock.results[1].value as { dispose: ReturnType<typeof vi.fn> };
    expect(first.dispose).toHaveBeenCalledTimes(1);
    expect(second.dispose).not.toHaveBeenCalled();

    unmount();
    expect(second.dispose).toHaveBeenCalledTimes(1);
    expect(first.dispose).toHaveBeenCalledTimes(1);
  });

  it('does not rebuild when only activity changes', () => {
    const source = new THREE.Object3D();
    const uniforms = makeUniforms();
    const { rerender } = render(
      <SignalParticles activity={0.1} source={source} uniforms={uniforms} />,
    );
    rerender(<SignalParticles activity={0.9} source={source} uniforms={uniforms} />);
    expect(mocks.build).toHaveBeenCalledTimes(1);
  });
});

describe('SignalParticles frame update', () => {
  it('copies shared uniforms onto the material and the viewport pixel ratio', () => {
    const uniforms = makeUniforms();
    const { container } = render(
      <SignalParticles activity={0} source={new THREE.Object3D()} uniforms={uniforms} />,
    );
    const material = getMaterial(container);
    material.uActivity = 0;

    runFrame({ viewport: { dpr: 2 } }, 0.016);

    expect(material.uPixelRatio).toBe(2);
    expect(material.uTime).toBe(1.5);
    expect(material.uWaveOrigins).toBe(uniforms.uWaveOrigins.value);
    expect(material.uWaveTimes).toBe(uniforms.uWaveTimes.value);
    expect(material.uPostureColor).toBe(uniforms.uPosture.value);
    expect(material.uPostureTint).toBe(uniforms.uPostureTint.value);
  });

  it('damps activity toward the value clamped to 1', () => {
    const { container } = render(
      <SignalParticles activity={5} source={new THREE.Object3D()} uniforms={makeUniforms()} />,
    );
    const material = getMaterial(container);
    material.uActivity = 0;

    runFrame({ viewport: { dpr: 1 } }, 0.25);

    // damp(0, 1, 4, 0.25) = 1 - exp(-1)
    expect(material.uActivity as number).toBeCloseTo(1 - Math.exp(-1), 10);
  });

  it('damps activity toward 0 when activity is negative', () => {
    const { container } = render(
      <SignalParticles activity={-3} source={new THREE.Object3D()} uniforms={makeUniforms()} />,
    );
    const material = getMaterial(container);
    material.uActivity = 0.5;

    runFrame({ viewport: { dpr: 1 } }, 0.25);

    // damp(0.5, 0, 4, 0.25) = 0.5 * exp(-1)
    expect(material.uActivity as number).toBeCloseTo(0.5 * Math.exp(-1), 10);
  });

  it('leaves activity unchanged for a zero time step', () => {
    const { container } = render(
      <SignalParticles activity={1} source={new THREE.Object3D()} uniforms={makeUniforms()} />,
    );
    const material = getMaterial(container);
    material.uActivity = 0.3;

    runFrame({ viewport: { dpr: 1 } }, 0);

    expect(material.uActivity as number).toBeCloseTo(0.3, 10);
  });
});
