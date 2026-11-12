import { describe, expect, it } from 'vitest';
import { MATERIALIZATION_REACH_MS, MATERIALIZATION_UNFURL_MS } from './materializationTiming';

describe('materializationTiming', () => {
  it('exposes the nerve reach duration in milliseconds', () => {
    expect(MATERIALIZATION_REACH_MS).toBe(900);
  });

  it('exposes the slab unfurl duration in milliseconds', () => {
    expect(MATERIALIZATION_UNFURL_MS).toBe(520);
  });

  it('keeps the nerve reach longer than the slab unfurl', () => {
    expect(MATERIALIZATION_REACH_MS).toBeGreaterThan(MATERIALIZATION_UNFURL_MS);
    expect(Number.isFinite(MATERIALIZATION_UNFURL_MS)).toBe(true);
    expect(MATERIALIZATION_UNFURL_MS).toBeGreaterThan(0);
  });
});
