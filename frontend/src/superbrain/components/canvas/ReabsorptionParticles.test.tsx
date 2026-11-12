import { render } from '@testing-library/react';
import * as THREE from 'three';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import ReabsorptionParticles from './ReabsorptionParticles';

const world = vi.hoisted(() => ({
  frame: null as null | (() => void),
  anchor: [1, 2, 3] as [number, number, number],
  dockScale: 0.5,
}));

vi.mock('@react-three/fiber', () => ({
  useFrame: (cb: () => void) => {
    world.frame = cb;
  },
}));

vi.mock('@/lib/spineFusionBus', () => ({
  getCortexAnchor: () => world.anchor,
  getBrainDockScale: () => world.dockScale,
  getSpineFusion: () => ({ ready: false, spineScale: 1, weld: [0, 0, 0] }),
}));

vi.mock('@/lib/spineAnatomy', () => ({
  SEGMENT_ANCHORS: [
    { x: 0, y: 0, z: 0 },
    { x: 4, y: 6, z: 8 },
  ],
}));

const START = 1000;
const DURATION = 1300;

type Props = Partial<React.ComponentProps<typeof ReabsorptionParticles>>;

function setup(props: Props = {}) {
  const setAttribute = vi.spyOn(THREE.BufferGeometry.prototype, 'setAttribute');
  const view = render(
    <ReabsorptionParticles origin={[1, 1, 1]} startedAt={START} durationMs={DURATION} {...props} />,
  );
  const geometry = setAttribute.mock.results[0].value as THREE.BufferGeometry;
  const material = new THREE.PointsMaterial();
  const el = view.container.querySelector('points');
  if (!el) throw new Error('points element not rendered');
  Object.assign(el, { material });

  const run = (now: number) => {
    vi.spyOn(performance, 'now').mockReturnValue(now);
    world.frame?.();
    return geometry.attributes.position.array as Float32Array;
  };
  return { ...view, geometry, material, run };
}

describe('ReabsorptionParticles', () => {
  beforeEach(() => {
    world.frame = null;
    world.anchor = [1, 2, 3];
    world.dockScale = 0.5;
    vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.spyOn(Math, 'random').mockReturnValue(0.5);
  });
  afterEach(() => vi.restoreAllMocks());

  it('starts at the origin, fully bright', () => {
    const { run, material } = setup({ origin: [1, 1, 1] });
    const pos = run(START);
    expect(pos).toHaveLength(72 * 3);
    for (let i = 0; i < 72; i++) {
      expect(pos[i * 3]).toBeCloseTo(1);
      expect(pos[i * 3 + 1]).toBeCloseTo(1);
      expect(pos[i * 3 + 2]).toBeCloseTo(1);
    }
    expect(material.opacity).toBeCloseTo(0.95);
  });

  it('ends at the live cortex anchor scaled by the dock scale, faded out', () => {
    const { run, material } = setup();
    const pos = run(START + DURATION);
    for (let i = 0; i < 72; i++) {
      expect(pos[i * 3]).toBeCloseTo(0.5);
      expect(pos[i * 3 + 1]).toBeCloseTo(1);
      expect(pos[i * 3 + 2]).toBeCloseTo(1.5);
    }
    expect(material.opacity).toBeCloseTo(0);
  });

  it('does not travel up the spine when reducedMotion is set', () => {
    const { run, material } = setup({ origin: [1, 1, 1], reducedMotion: true });
    const pos = run(START + DURATION);
    expect(pos[0]).toBeCloseTo(1);
    expect(pos[1]).toBeCloseTo(1);
    expect(pos[2]).toBeCloseTo(1);
    expect(material.opacity).toBeCloseTo(0);
  });

  it('departs from the scaled seated vertebra instead of the origin', () => {
    const { run } = setup({ origin: [9, 9, 9], seatIndex: 1 });
    const pos = run(START);
    expect(pos[0]).toBeCloseTo(2);
    expect(pos[1]).toBeCloseTo(3);
    expect(pos[2]).toBeCloseTo(4);
  });

  it('releases its geometry on unmount', () => {
    const { geometry, unmount } = setup();
    const dispose = vi.spyOn(geometry, 'dispose');
    unmount();
    expect(dispose).toHaveBeenCalledOnce();
  });
});
