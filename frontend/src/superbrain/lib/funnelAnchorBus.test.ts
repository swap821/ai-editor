import { beforeEach, describe, expect, it } from 'vitest';
import {
  __resetFunnelAnchorForTests,
  getFunnelAnchor,
  setFunnelAnchor,
  type FunnelAnchor,
} from './funnelAnchorBus';

const sample: FunnelAnchor = {
  x: 120,
  y: 480,
  visible: true,
  world: [1, -2, 3],
  presence: 0.5,
  intake: 0.8,
  flow: 0.25,
};

describe('funnelAnchorBus', () => {
  beforeEach(() => {
    __resetFunnelAnchorForTests();
  });

  it('starts hidden with zeroed values', () => {
    expect(getFunnelAnchor()).toEqual({
      x: 0,
      y: 0,
      visible: false,
      world: [0, 0, 0],
      intake: 0,
      flow: 0,
    });
  });

  it('returns the anchor most recently published', () => {
    setFunnelAnchor(sample);
    expect(getFunnelAnchor()).toBe(sample);

    const next: FunnelAnchor = { ...sample, x: 5, visible: false };
    setFunnelAnchor(next);
    expect(getFunnelAnchor()).toEqual(next);
    expect(getFunnelAnchor().x).toBe(5);
  });

  it('reset discards a published anchor', () => {
    setFunnelAnchor(sample);
    __resetFunnelAnchorForTests();
    const anchor = getFunnelAnchor();
    expect(anchor.visible).toBe(false);
    expect(anchor.x).toBe(0);
    expect(anchor.intake).toBe(0);
    expect(anchor.presence).toBeUndefined();
  });

  it('exposes a window console hook that reads the live anchor', () => {
    const hook = (window as unknown as { __getFunnelAnchor?: () => FunnelAnchor })
      .__getFunnelAnchor;
    expect(typeof hook).toBe('function');

    setFunnelAnchor(sample);
    expect(hook?.()).toBe(sample);
  });
});
