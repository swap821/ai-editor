import { describe, expect, it } from 'vitest';
import { reconcileWorkerSeats } from './workerSeatRegistry';

describe('reconcileWorkerSeats', () => {
  it('preserves admitted workers seats across reorder and fills the lowest free seat', () => {
    const previous = [
      { workerId: 'worker-alpha', seat: 0 },
      { workerId: 'worker-beta', seat: 1 },
    ];

    expect(reconcileWorkerSeats(previous, ['worker-gamma', 'worker-beta', 'worker-alpha'])).toEqual([
      { workerId: 'worker-gamma', seat: 2 },
      { workerId: 'worker-beta', seat: 1 },
      { workerId: 'worker-alpha', seat: 0 },
    ]);
  });

  it('releases removed seats and ignores duplicate or blank identities', () => {
    expect(reconcileWorkerSeats(
      [{ workerId: 'worker-old', seat: 3 }],
      ['worker-new', 'worker-new', '  '],
    )).toEqual([{ workerId: 'worker-new', seat: 0 }]);
  });

  it('rejects conflicting and out-of-range prior seats while respecting capacity', () => {
    expect(reconcileWorkerSeats([
      { workerId: 'worker-alpha', seat: 0 },
      { workerId: 'worker-beta', seat: 0 },
      { workerId: 'worker-gamma', seat: 9 },
    ], ['worker-alpha', 'worker-beta', 'worker-gamma', 'worker-delta'], 3)).toEqual([
      { workerId: 'worker-alpha', seat: 0 },
      { workerId: 'worker-beta', seat: 1 },
      { workerId: 'worker-gamma', seat: 2 },
    ]);
  });
});
