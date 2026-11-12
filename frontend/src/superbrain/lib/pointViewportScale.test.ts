import { describe, expect, it } from 'vitest';
import { pointPresenceHeight, pointViewportScale } from './pointViewportScale';

describe('pointViewportScale', () => {
  it('scales down proportionally below the 168px reference', () => {
    expect(pointViewportScale(84)).toBe(0.5);
    expect(pointViewportScale(42)).toBe(0.25);
  });

  it('caps at 1 at and above the reference height', () => {
    expect(pointViewportScale(168)).toBe(1);
    expect(pointViewportScale(500)).toBe(1);
  });

  it('falls back to 1 for non-positive or non-finite heights', () => {
    expect(pointViewportScale(0)).toBe(1);
    expect(pointViewportScale(-50)).toBe(1);
    expect(pointViewportScale(Number.NaN)).toBe(1);
    expect(pointViewportScale(Number.POSITIVE_INFINITY)).toBe(1);
  });
});

describe('pointPresenceHeight', () => {
  it('uses the camera full height when the view is enabled', () => {
    const camera = { view: { enabled: true, fullHeight: 720 } };
    expect(pointPresenceHeight(camera, 300)).toBe(720);
  });

  it('uses the stage height when the view is disabled', () => {
    const camera = { view: { enabled: false, fullHeight: 720 } };
    expect(pointPresenceHeight(camera, 300)).toBe(300);
  });

  it('uses the stage height when the view is missing or null', () => {
    expect(pointPresenceHeight({}, 300)).toBe(300);
    expect(pointPresenceHeight({ view: null }, 240)).toBe(240);
  });
});
