// frontend/src/superbrain/lib/beingMode.test.ts
import { describe, it, expect } from 'vitest';
import { readBeingMode } from './beingMode';

describe('readBeingMode', () => {
  it('returns points for ?being=points', () => {
    expect(readBeingMode('?being=points')).toBe('points');
  });
  it('defaults to points when absent (the official voyaging mind)', () => {
    expect(readBeingMode('')).toBe('points');
  });
  it('returns mesh only for the explicit ?being=mesh escape hatch', () => {
    expect(readBeingMode('?being=mesh')).toBe('mesh');
  });
  it('falls back to points for unknown values', () => {
    expect(readBeingMode('?being=banana')).toBe('points');
  });
});
