import { describe, it, expect, beforeEach } from 'vitest';
import { getStemAnchor, setStemAnchor, __resetStemAnchorForTests } from './stemAnchorBus';

describe('stemAnchorBus', () => {
  beforeEach(() => __resetStemAnchorForTests());

  it('defaults to hidden at the origin', () => {
    expect(getStemAnchor()).toEqual({ x: 0, y: 0, visible: false });
  });

  it('publishes the projected stem screen anchor', () => {
    setStemAnchor({ x: 640, y: 880, visible: true });
    expect(getStemAnchor()).toEqual({ x: 640, y: 880, visible: true });
  });

  it('reset restores the hidden default', () => {
    setStemAnchor({ x: 5, y: 5, visible: true });
    __resetStemAnchorForTests();
    expect(getStemAnchor().visible).toBe(false);
  });
});
