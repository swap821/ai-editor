import { afterEach, describe, expect, it } from 'vitest';
import {
  __resetSpineFusionStateForTests,
  fuseSpinePoint,
  getSpineFusion,
  setSpineFusion,
} from './spineFusionState';

describe('spineFusionState', () => {
  afterEach(() => {
    __resetSpineFusionStateForTests();
  });

  it('starts as identity: not ready, and points pass through unchanged', () => {
    const state = getSpineFusion();
    expect(state.ready).toBe(false);
    expect(state.spineScale).toBe(1);
    expect(state.weld).toEqual([0, 0, 0]);
    expect(fuseSpinePoint([1, 2, 3])).toEqual([1, 2, 3]);
  });

  it('returns a copy of the input point when not ready', () => {
    const input: [number, number, number] = [4, 5, 6];
    const out = fuseSpinePoint(input);
    expect(out).toEqual(input);
    expect(out).not.toBe(input);
  });

  it('scales then welds points once fusion is set', () => {
    setSpineFusion(2, [10, 20, 30]);
    expect(getSpineFusion().ready).toBe(true);
    expect(getSpineFusion().spineScale).toBe(2);
    expect(fuseSpinePoint([1, 2, 3])).toEqual([12, 24, 36]);
    expect(fuseSpinePoint([0, 0, 0])).toEqual([10, 20, 30]);
  });

  it('copies the weld array so later mutation of the input does not leak', () => {
    const weld: [number, number, number] = [1, 1, 1];
    setSpineFusion(1, weld);
    weld[0] = 99;
    expect(getSpineFusion().weld).toEqual([1, 1, 1]);
    expect(fuseSpinePoint([0, 0, 0])).toEqual([1, 1, 1]);
  });

  it('reset returns the module to the identity state', () => {
    setSpineFusion(3, [1, 2, 3]);
    __resetSpineFusionStateForTests();
    expect(getSpineFusion().ready).toBe(false);
    expect(getSpineFusion().spineScale).toBe(1);
    expect(fuseSpinePoint([7, 8, 9])).toEqual([7, 8, 9]);
  });
});
