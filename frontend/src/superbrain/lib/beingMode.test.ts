// frontend/src/superbrain/lib/beingMode.test.ts
import { describe, it, expect } from 'vitest';
import { readBeingMode } from './beingMode';

describe('readBeingMode', () => {
  it('returns points only for ?being=points', () => {
    expect(readBeingMode('?being=points')).toBe('points');
  });
  it('defaults to mesh when absent', () => {
    expect(readBeingMode('')).toBe('mesh');
  });
  it('returns mesh for ?being=mesh', () => {
    expect(readBeingMode('?being=mesh')).toBe('mesh');
  });
  it('falls back to mesh for unknown values', () => {
    expect(readBeingMode('?being=banana')).toBe('mesh');
  });
});
