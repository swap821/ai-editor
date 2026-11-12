import { render, screen } from '@testing-library/react';
import { forwardRef, useImperativeHandle } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import CorticalNerve from './CorticalNerve';

const h = vi.hoisted(() => ({
  frame: null as null | (() => void),
  setPositions: vi.fn(),
  anchor: [0, 0, 0] as [number, number, number],
  dock: 1,
}));

vi.mock('@react-three/fiber', () => ({
  useFrame: (cb: () => void) => {
    h.frame = cb;
  },
}));

vi.mock('@react-three/drei', () => ({
  Line: forwardRef<unknown, { color: string; opacity: number }>(function LineMock(props, ref) {
    useImperativeHandle(ref, () => ({ geometry: { setPositions: h.setPositions } }));
    return <div data-testid="line" data-color={props.color} data-opacity={props.opacity} />;
  }),
}));

vi.mock('@/lib/spineFusionBus', () => ({
  getCortexAnchor: () => h.anchor,
  getBrainDockScale: () => h.dock,
}));

const TARGET: [number, number, number] = [3, 4, 5];

function runFrame(): number[] {
  h.setPositions.mockClear();
  h.frame?.();
  expect(h.setPositions).toHaveBeenCalledOnce();
  return [...(h.setPositions.mock.calls[0][0] as number[])];
}

describe('CorticalNerve', () => {
  beforeEach(() => {
    h.frame = null;
    h.setPositions.mockClear();
    h.anchor = [0.5, 1, -2];
    h.dock = 2;
  });

  it('uses the poster cyan by default and accepts a custom colour', () => {
    const { rerender } = render(<CorticalNerve target={TARGET} />);
    expect(screen.getByTestId('line')).toHaveAttribute('data-color', '#7bf5fb');
    expect(screen.getByTestId('line')).toHaveAttribute('data-opacity', '0.6');
    rerender(<CorticalNerve target={TARGET} color="#ff00ff" />);
    expect(screen.getByTestId('line')).toHaveAttribute('data-color', '#ff00ff');
  });

  it('roots the strand at anchor x dock scale and ends at the target', () => {
    render(<CorticalNerve target={TARGET} />);
    const p = runFrame();
    expect(p).toHaveLength(60);
    expect(p[0]).toBeCloseTo(1);
    expect(p[1]).toBeCloseTo(2);
    expect(p[2]).toBeCloseTo(-4);
    expect(p[57]).toBeCloseTo(3);
    expect(p[58]).toBeCloseTo(4);
    expect(p[59]).toBeCloseTo(5);
  });

  it('falls back to a dock scale of 1 when the scale is 0', () => {
    h.dock = 0;
    render(<CorticalNerve target={TARGET} />);
    const p = runFrame();
    expect(p[0]).toBeCloseTo(0.5);
    expect(p[1]).toBeCloseTo(1);
    expect(p[2]).toBeCloseTo(-2);
  });

  it('re-aims every frame when the live anchor moves', () => {
    render(<CorticalNerve target={TARGET} />);
    runFrame();
    h.anchor = [2, 2, 2];
    h.dock = 1;
    const p = runFrame();
    expect(p.slice(0, 3)).toEqual([2, 2, 2]);
  });

  it('bows less in reduced-motion mode', () => {
    h.anchor = [0, 0, 0];
    h.dock = 1;
    const flatTarget: [number, number, number] = [1, 0, 0];
    const normal = render(<CorticalNerve target={flatTarget} />);
    const bowY = runFrame()[10 * 3 + 1];
    normal.unmount();
    render(<CorticalNerve target={flatTarget} reducedMotion />);
    const calmY = runFrame()[10 * 3 + 1];
    expect(bowY).toBeGreaterThan(calmY);
    expect(calmY).toBeGreaterThan(0);
  });
});
