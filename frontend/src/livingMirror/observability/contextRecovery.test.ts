import { describe, expect, it } from 'vitest';
import { createContextRecoveryTracker } from './contextRecovery';

describe('context recovery tracker', () => {
  it('records the measured loss-to-restore duration only after a paired recovery', () => {
    let now = 100;
    const samples: Array<{ name: string; value: number }> = [];
    const tracker = createContextRecoveryTracker({
      now: () => now,
      record: (name, value) => samples.push({ name, value }),
    });

    tracker.handleLost();
    now = 142;
    tracker.handleRestored();

    expect(samples).toEqual([{ name: 'context-recovery', value: 42 }]);
  });

  it('does not invent a recovery duration when restoration arrives without loss', () => {
    const samples: Array<{ name: string; value: number }> = [];
    const tracker = createContextRecoveryTracker({
      now: () => 100,
      record: (name, value) => samples.push({ name, value }),
    });

    tracker.handleRestored();

    expect(samples).toEqual([]);
  });
});
