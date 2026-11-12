import { render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type * as THREE from 'three';
import NerveMesh, { COUNCIL_NODES } from './NerveMesh';

type FrameState = { clock: { elapsedTime: number } };
type FrameCallback = (state: FrameState) => void;

const frameCallbacks = vi.hoisted(() => [] as unknown[]);

vi.mock('./PulseShader', () => ({}));
vi.mock('@react-three/fiber', () => ({
  useFrame: (cb: unknown) => {
    frameCallbacks.push(cb);
  },
}));

type MatrixRecord = { index: number; position: number[] };
type ColorRecord = { index: number; hex: string };

const matrixRecords: MatrixRecord[] = [];
const colorRecords: ColorRecord[] = [];
const instanceMatrix = { needsUpdate: false };

// Under react-dom the instancedMesh ref is a plain element, so give it the
// small InstancedMesh surface the component writes to.
const meshStubs = {
  setMatrixAt: (index: number, matrix: THREE.Matrix4) => {
    matrixRecords.push({
      index,
      position: [matrix.elements[12], matrix.elements[13], matrix.elements[14]],
    });
  },
  setColorAt: (index: number, color: THREE.Color) => {
    colorRecords.push({ index, hex: color.getHexString() });
  },
  instanceMatrix,
};

describe('COUNCIL_NODES', () => {
  it('defines six distinct castes with hex colors', () => {
    const castes = COUNCIL_NODES.map((n) => n.caste);
    expect(new Set(castes).size).toBe(6);
    expect(castes).toEqual(
      expect.arrayContaining(['builder', 'scout', 'reviewer', 'planner', 'synthesizer', 'soldier']),
    );
    for (const node of COUNCIL_NODES) {
      expect(node.color).toMatch(/^#[0-9a-f]{6}$/);
    }
  });
});

describe('NerveMesh', () => {
  beforeEach(() => {
    frameCallbacks.length = 0;
    matrixRecords.length = 0;
    colorRecords.length = 0;
    instanceMatrix.needsUpdate = false;
    Object.assign(HTMLElement.prototype, meshStubs);
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
  });

  afterEach(() => {
    for (const key of Object.keys(meshStubs)) {
      Reflect.deleteProperty(HTMLElement.prototype, key);
    }
    vi.restoreAllMocks();
  });

  it('writes each council node position and color into the instanced mesh on mount', () => {
    render(<NerveMesh activeStates={new Float32Array(6)} />);

    expect(matrixRecords.map((r) => r.index)).toEqual([0, 1, 2, 3, 4, 5]);
    expect(colorRecords.map((r) => r.index)).toEqual([0, 1, 2, 3, 4, 5]);

    COUNCIL_NODES.forEach((node, i) => {
      const [x, y, z] = matrixRecords[i].position;
      expect(x).toBeCloseTo(node.position.x);
      expect(y).toBeCloseTo(node.position.y);
      expect(z).toBeCloseTo(node.position.z);
      expect(`#${colorRecords[i].hex}`).toBe(node.color);
    });
    expect(instanceMatrix.needsUpdate).toBe(true);
  });

  it('updates the material uTime from the clock on each frame', () => {
    const { container } = render(<NerveMesh activeStates={new Float32Array(6)} />);

    expect(frameCallbacks).toHaveLength(1);
    const onFrame = frameCallbacks[0] as FrameCallback;
    const material = container.querySelector('pulsematerial') as unknown as { uTime?: number };
    expect(material).not.toBeNull();

    onFrame({ clock: { elapsedTime: 3.5 } });
    expect(material.uTime).toBe(3.5);

    onFrame({ clock: { elapsedTime: 7.25 } });
    expect(material.uTime).toBe(7.25);
  });
});
