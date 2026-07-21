import { describe, expect, it } from 'vitest';
import { deriveTurnMetabolismSnapshot } from './turnMetabolism';
import { postureHex } from './bodyPosture';

describe('turnMetabolism', () => {
  it('derives rest state by default or when explicitly idle', () => {
    const snapshot1 = deriveTurnMetabolismSnapshot('idle');
    const snapshot2 = deriveTurnMetabolismSnapshot('unknown_phase');

    expect(snapshot1).toMatchObject({
      phase: 'rest',
      intensity: 0,
      surfaceExcitation: 0,
      rootExcitation: 0,
      held: false,
    });
    
    expect(snapshot2.phase).toBe('rest');
  });

  it('maps active phase to working metabolism', () => {
    const snapshot = deriveTurnMetabolismSnapshot('active');

    expect(snapshot.phase).toBe('working');
    expect(snapshot.intensity).toBeGreaterThan(0.5);
    expect(snapshot.surfaceExcitation).toBeGreaterThan(0);
    expect(snapshot.rootExcitation).toBeGreaterThan(0);
    expect(snapshot.tint).toBe(postureHex('stream'));
  });

  it('maps explicit phases exactly', () => {
    const thinking = deriveTurnMetabolismSnapshot('thinking');
    expect(thinking.phase).toBe('thinking');
    expect(thinking.tint).toBe(postureHex('think'));

    const error = deriveTurnMetabolismSnapshot('error');
    expect(error.phase).toBe('error');
    expect(error.tint).toBe(postureHex('error'));

    const settling = deriveTurnMetabolismSnapshot('settling');
    expect(settling.phase).toBe('settling');
    expect(settling.tint).toBe(postureHex('complete'));
  });

  it('marks approval phase as held', () => {
    const approval = deriveTurnMetabolismSnapshot('approval');
    expect(approval.phase).toBe('approval');
    expect(approval.held).toBe(true);
    expect(approval.breathGain).toBeLessThan(0);
  });
});
