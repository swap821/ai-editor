import { render } from '@testing-library/react';
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';
import * as THREE from 'three';
import KnowledgeHorizon from './KnowledgeHorizon';

type FrameState = {
  pointer: { x: number; y: number };
  clock: { elapsedTime: number };
};
type FrameCallback = (state: FrameState, delta: number) => void;

const frame = vi.hoisted(() => ({ current: null as unknown }));

vi.mock('@react-three/fiber', () => ({
  useFrame: (callback: unknown) => {
    frame.current = callback;
  },
}));

function makeUniforms() {
  return {
    uTime: { value: -1 },
    uActivity: { value: -1 },
    uPointer: { value: new THREE.Vector2(0, 0) },
  };
}

function mountSky(activity: number) {
  const view = render(<KnowledgeHorizon activity={activity} />);
  const material = view.container.querySelector('shadermaterial');
  if (!material) throw new Error('shader material was not rendered');
  const uniforms = makeUniforms();
  Object.assign(material, { uniforms });
  return { ...view, uniforms };
}

function runFrame(state: FrameState, delta: number) {
  (frame.current as FrameCallback)(state, delta);
}

const state = (x: number, y: number, elapsedTime: number): FrameState => ({
  pointer: { x, y },
  clock: { elapsedTime },
});

describe('KnowledgeHorizon', () => {
  beforeEach(() => {
    frame.current = null;
    vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.spyOn(console, 'warn').mockImplementation(() => {});
  });
  afterEach(() => vi.restoreAllMocks());

  it('renders a sky dome mesh and registers a frame callback', () => {
    const { container } = mountSky(0);
    expect(container.querySelector('mesh')).not.toBeNull();
    expect(container.querySelector('spheregeometry')).not.toBeNull();
    expect(typeof frame.current).toBe('function');
  });

  it('writes the clock time into the time uniform', () => {
    const { uniforms } = mountSky(0);
    runFrame(state(0, 0, 12.5), 0.016);
    expect(uniforms.uTime.value).toBe(12.5);
  });

  it('eases activity toward the prop instead of jumping to it', () => {
    const { rerender, uniforms } = mountSky(0);
    rerender(<KnowledgeHorizon activity={1} />);
    runFrame(state(0, 0, 1), 0.1);
    const expected = 1 - Math.exp(-3 * 0.1);
    expect(uniforms.uActivity.value).toBeCloseTo(expected, 5);
    expect(uniforms.uActivity.value).toBeGreaterThan(0);
    expect(uniforms.uActivity.value).toBeLessThan(1);

    runFrame(state(0, 0, 2), 0.1);
    expect(uniforms.uActivity.value).toBeGreaterThan(expected);
  });

  it('clamps out-of-range activity to the 0..1 range', () => {
    const high = mountSky(0);
    high.rerender(<KnowledgeHorizon activity={5} />);
    runFrame(state(0, 0, 1), 0.1);
    expect(high.uniforms.uActivity.value).toBeCloseTo(1 - Math.exp(-0.3), 5);
    high.unmount();

    const low = mountSky(0);
    low.rerender(<KnowledgeHorizon activity={-4} />);
    runFrame(state(0, 0, 1), 0.1);
    expect(low.uniforms.uActivity.value).toBeCloseTo(0, 5);
  });

  it('damps the pointer uniform toward the live pointer', () => {
    const { uniforms } = mountSky(0);
    runFrame(state(1, -1, 1), 0.1);
    const step = 1 - Math.exp(-3 * 0.1);
    expect(uniforms.uPointer.value.x).toBeCloseTo(step, 5);
    expect(uniforms.uPointer.value.y).toBeCloseTo(-step, 5);

    runFrame(state(1, -1, 2), 0.1);
    expect(uniforms.uPointer.value.x).toBeCloseTo(step + (1 - step) * step, 5);
    expect(uniforms.uPointer.value.x).toBeLessThan(1);
  });
});
