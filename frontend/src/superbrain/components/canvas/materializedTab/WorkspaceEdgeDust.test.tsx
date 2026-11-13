import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render } from '@testing-library/react';
import * as THREE from 'three';
import { WorkspaceEdgeDust } from './WorkspaceEdgeDust';

vi.mock('@react-three/fiber', () => ({
  useThree: (selector: (state: { viewport: { dpr: number } }) => unknown) =>
    selector({ viewport: { dpr: 2 } }),
}));

const reach = new THREE.Color('#ff0000');
const live = new THREE.Color('#00ff00');

function makeShape() {
  const shape = new THREE.Shape();
  const spaced = vi.spyOn(shape, 'getSpacedPoints').mockReturnValue([
    new THREE.Vector2(1, 2),
    new THREE.Vector2(3, 4),
    new THREE.Vector2(5, 6),
  ]);
  return { shape, spaced };
}

describe('WorkspaceEdgeDust', () => {
  let setAttribute: ReturnType<typeof vi.spyOn>;
  let dispose: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    setAttribute = vi.spyOn(THREE.BufferGeometry.prototype, 'setAttribute');
    dispose = vi.spyOn(THREE.BufferGeometry.prototype, 'dispose');
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  function attributeNamed(name: string): THREE.BufferAttribute {
    const call = setAttribute.mock.calls.find((args) => args[0] === name);
    if (!call) throw new Error(`attribute ${name} was not set`);
    return call[1] as THREE.BufferAttribute;
  }

  it('samples 143 spaced points and offsets each one outward with a deterministic jitter', () => {
    const { shape, spaced } = makeShape();

    render(<WorkspaceEdgeDust shape={shape} depth={3} reach={reach} live={live} />);

    expect(spaced).toHaveBeenCalledWith(143);
    const position = attributeNamed('position');
    expect(position.itemSize).toBe(3);
    expect(position.count).toBe(3);
    const values = Array.from(position.array);
    const expected = [
      1 * 1.014, 2 * 1.014, 3.018,
      3 * 1.022, 4 * 1.022, 3.018,
      5 * 1.03, 6 * 1.03, 3.018,
    ];
    expected.forEach((value, index) => {
      expect(values[index]).toBeCloseTo(value, 4);
    });
  });

  it('assigns a per-point weight derived from the index', () => {
    const { shape } = makeShape();

    render(<WorkspaceEdgeDust shape={shape} depth={0} reach={reach} live={live} />);

    const weight = attributeNamed('weight');
    expect(weight.itemSize).toBe(1);
    const values = Array.from(weight.array);
    expect(values).toHaveLength(3);
    expect(values[0]).toBeCloseTo(0.35, 5);
    expect(values[1]).toBeCloseTo(0.35 + 13 / 26, 5);
    expect(values[2]).toBeCloseTo(0.35 + 9 / 26, 5);
  });

  it('renders a points object named for the waiting workspace edge', () => {
    const { shape } = makeShape();

    const { container } = render(
      <WorkspaceEdgeDust shape={shape} depth={0} reach={reach} live={live} />,
    );

    expect(container.querySelector('points')?.getAttribute('name')).toBe(
      'waiting-workspace-edge',
    );
  });

  it('reuses the geometry on rerender, rebuilds it when depth changes, and disposes on unmount', () => {
    const { shape } = makeShape();
    const { rerender, unmount } = render(
      <WorkspaceEdgeDust shape={shape} depth={1} reach={reach} live={live} />,
    );
    expect(setAttribute).toHaveBeenCalledTimes(2);
    expect(dispose).not.toHaveBeenCalled();

    rerender(
      <WorkspaceEdgeDust shape={shape} depth={1} reach={new THREE.Color('#0000ff')} live={live} />,
    );
    expect(setAttribute).toHaveBeenCalledTimes(2);
    expect(dispose).not.toHaveBeenCalled();

    rerender(<WorkspaceEdgeDust shape={shape} depth={5} reach={reach} live={live} />);
    expect(setAttribute).toHaveBeenCalledTimes(4);
    expect(dispose).toHaveBeenCalledTimes(1);
    const latest = setAttribute.mock.calls
      .filter((args) => args[0] === 'position')
      .map((args) => args[1] as THREE.BufferAttribute)
      .pop();
    expect(latest?.array[2]).toBeCloseTo(5.018, 4);

    unmount();
    expect(dispose).toHaveBeenCalledTimes(2);
  });
});
