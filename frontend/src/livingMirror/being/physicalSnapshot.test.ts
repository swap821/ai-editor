import { describe, expect, it } from 'vitest';
import { derivePhysicalSnapshot } from './physicalSnapshot';
import type { BeingPresentation } from './semanticKernel';

const base = (overrides: Partial<BeingPresentation> = {}): BeingPresentation => ({
  phase: 'resting',
  taskState: 'idle',
  coherence: 'fresh',
  motion: 'calm',
  attention: 'none',
  signals: [],
  workers: [],
  ...overrides,
});

describe('derivePhysicalSnapshot', () => {
  it('maps an active semantic posture into a bounded cortex and conductor snapshot', () => {
    const snapshot = derivePhysicalSnapshot(base({
      phase: 'acting',
      motion: 'conduct',
      attention: 'workspace',
      signals: ['worker-active'],
      workers: ['active'],
    }));

    expect(snapshot.cortex).toEqual({
      posture: 'conduct',
      attention: 1,
      activity: 1,
      convergence: 0.78,
    });
    expect(snapshot.conductor).toEqual({
      posture: 'active',
      travel: 'outbound',
      activeSeat: 0,
    });
    expect(snapshot.branches).toEqual([
      { slot: 0, state: 'active', visual: 'conduct', terminal: false },
    ]);
  });

  it('turns approval and stop postures into a closed action membrane', () => {
    const held = derivePhysicalSnapshot(base({
      phase: 'awaiting-human',
      taskState: 'needs-permission',
      motion: 'attention',
      attention: 'approval',
      workers: ['active', 'awaiting-capability'],
    }));
    const stopped = derivePhysicalSnapshot(base({
      phase: 'stopped',
      taskState: 'stopped',
      coherence: 'stopped',
      motion: 'stop',
      signals: ['emergency-stop'],
      workers: ['active'],
    }));

    expect(held.membrane).toEqual({ state: 'held', actionTravel: 'closed' });
    expect(held.branches.map((branch) => branch.visual)).toEqual(['held', 'held']);
    expect(stopped.membrane).toEqual({ state: 'stopped', actionTravel: 'closed' });
    expect(stopped.conductor).toMatchObject({ posture: 'stopped', travel: 'frozen' });
  });

  it('keeps memory and reflex evidence distinct from transient action posture', () => {
    expect(derivePhysicalSnapshot(base({ signals: ['memory-recalled'] })).memory).toEqual({ layer: 'recalled', pulse: 'inward' });
    expect(derivePhysicalSnapshot(base({ signals: ['memory-promoted'] })).memory).toEqual({ layer: 'promoted', pulse: 'settle' });
    expect(derivePhysicalSnapshot(base({ phase: 'reflex', motion: 'conduct', signals: ['reflex-reused'] })).memory).toEqual({ layer: 'reflex', pulse: 'conduct' });
    expect(derivePhysicalSnapshot(base()).memory).toEqual({ layer: 'none', pulse: 'none' });
  });

  it('keeps verification pending or failed from receiving settled physical treatment', () => {
    expect(derivePhysicalSnapshot(base({ phase: 'verifying', motion: 'verify' })).verification).toEqual({
      state: 'pending',
      settlement: 'unsettled',
    });
    expect(derivePhysicalSnapshot(base({ signals: ['verification-pass'] })).verification).toEqual({
      state: 'pass',
      settlement: 'stable',
    });
    expect(derivePhysicalSnapshot(base({ phase: 'recovering', motion: 'reabsorb', signals: ['verification-fail'] })).verification).toEqual({
      state: 'fail',
      settlement: 'unsettled',
    });
  });

  it('caps branch presentation and contains no authority fields', () => {
    const snapshot = derivePhysicalSnapshot(base({
      workers: ['requested', 'admitted', 'active', 'awaiting-capability', 'returned', 'dissolved', 'failed', 'killed'],
    }));

    expect(snapshot.branches).toHaveLength(8);
    expect(Object.keys(snapshot)).not.toEqual(expect.arrayContaining([
      'approved', 'authorized', 'allowed', 'canExecute',
    ]));
  });
});
