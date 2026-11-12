import { act, render } from '@testing-library/react';
import * as THREE from 'three';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import VertebraeRepoMapOverlay from './VertebraeRepoMapOverlay';

type Listener = (state: { activeFiles: Array<{ path: string; status: string; errorCount: number }> }) => void;

const h = vi.hoisted(() => ({
  listener: null as null | ((state: { activeFiles: unknown[] }) => void),
  unsubscribe: vi.fn(),
  frame: null as null | ((state: { clock: { elapsedTime: number } }) => void),
}));

vi.mock('@/lib/spineAnatomy', () => ({
  SEGMENT_COUNT: 3,
  SEGMENT_ANCHORS: [
    { x: 0, y: 0, z: 1 },
    { x: 1, y: 0, z: 1 },
    { x: 2, y: 0, z: 1 },
  ],
}));

vi.mock('@/lib/repoMapStore', () => ({
  subscribeRepoMap: (cb: (state: { activeFiles: unknown[] }) => void) => {
    h.listener = cb;
    return h.unsubscribe;
  },
}));

vi.mock('@react-three/fiber', () => ({
  useFrame: (cb: (state: { clock: { elapsedTime: number } }) => void) => {
    h.frame = cb;
  },
}));

const matrixCalls: Array<{ i: number; sx: number; z: number }> = [];
const colorCalls: Array<{ i: number; hex: number }> = [];
const instanceMatrix = { needsUpdate: false };

function push(files: Parameters<Listener>[0]['activeFiles']) {
  act(() => {
    h.listener?.({ activeFiles: files });
  });
}

describe('VertebraeRepoMapOverlay', () => {
  beforeEach(() => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    matrixCalls.length = 0;
    colorCalls.length = 0;
    instanceMatrix.needsUpdate = false;
    h.unsubscribe.mockClear();
    Object.defineProperty(HTMLElement.prototype, 'setMatrixAt', {
      configurable: true,
      value: (i: number, m: THREE.Matrix4) => {
        matrixCalls.push({ i, sx: m.elements[0], z: m.elements[14] });
      },
    });
    Object.defineProperty(HTMLElement.prototype, 'setColorAt', {
      configurable: true,
      value: (i: number, c: THREE.Color) => {
        colorCalls.push({ i, hex: c.getHex() });
      },
    });
    Object.defineProperty(HTMLElement.prototype, 'instanceMatrix', {
      configurable: true,
      value: instanceMatrix,
    });
  });

  afterEach(() => {
    Reflect.deleteProperty(HTMLElement.prototype, 'setMatrixAt');
    Reflect.deleteProperty(HTMLElement.prototype, 'setColorAt');
    Reflect.deleteProperty(HTMLElement.prototype, 'instanceMatrix');
    vi.restoreAllMocks();
  });

  it('renders nothing until the repo map reports active files', () => {
    const { container } = render(<VertebraeRepoMapOverlay />);
    expect(container.firstChild).toBeNull();
    expect(matrixCalls).toHaveLength(0);

    push([{ path: 'a.ts', status: 'editing', errorCount: 0 }]);
    expect(container.firstChild).not.toBeNull();
  });

  it('places, scales and colors instances per file and hides unused ones', () => {
    render(<VertebraeRepoMapOverlay />);
    push([
      { path: 'a.ts', status: 'editing', errorCount: 2 },
      { path: 'b.ts', status: 'approved', errorCount: 0 },
    ]);

    expect(matrixCalls.map((c) => c.i)).toEqual([0, 1, 2]);
    expect(matrixCalls[0].sx).toBeCloseTo(1.4);
    expect(matrixCalls[0].z).toBeCloseTo(1.35);
    expect(matrixCalls[1].sx).toBeCloseTo(1.0);
    expect(matrixCalls[2].sx).toBe(0);
    expect(instanceMatrix.needsUpdate).toBe(true);

    expect(colorCalls.map((c) => c.i)).toEqual([0, 1]);
    expect(colorCalls[1].hex).toBe(new THREE.Color('#36f07a').getHex());
    expect(colorCalls[0].hex).not.toBe(new THREE.Color('#19d4f0').getHex());
  });

  it('caps instances at the segment count', () => {
    render(<VertebraeRepoMapOverlay />);
    push([
      { path: 'a.ts', status: 'idle', errorCount: 0 },
      { path: 'b.ts', status: 'idle', errorCount: 0 },
      { path: 'c.ts', status: 'idle', errorCount: 0 },
      { path: 'd.ts', status: 'idle', errorCount: 0 },
      { path: 'e.ts', status: 'idle', errorCount: 0 },
    ]);
    expect(matrixCalls.map((c) => c.i)).toEqual([0, 1, 2]);
    expect(colorCalls).toHaveLength(3);
  });

  it('pulses only files that have errors on each frame', () => {
    render(<VertebraeRepoMapOverlay />);
    push([
      { path: 'a.ts', status: 'failed', errorCount: 2 },
      { path: 'b.ts', status: 'idle', errorCount: 0 },
    ]);
    matrixCalls.length = 0;
    instanceMatrix.needsUpdate = false;

    act(() => {
      h.frame?.({ clock: { elapsedTime: Math.PI / 10 } });
    });

    expect(matrixCalls).toHaveLength(1);
    expect(matrixCalls[0].i).toBe(0);
    expect(matrixCalls[0].sx).toBeCloseTo(1.4 * 1.2);
    expect(instanceMatrix.needsUpdate).toBe(true);
  });

  it('unsubscribes from the repo map on unmount', () => {
    const { unmount } = render(<VertebraeRepoMapOverlay />);
    expect(h.unsubscribe).not.toHaveBeenCalled();
    unmount();
    expect(h.unsubscribe).toHaveBeenCalledOnce();
  });
});
