import { describe, expect, it } from 'vitest';
import {
  deriveSemanticEffectTransition,
  isActionPresentationStopped,
  pruneExpiredWorkerMotes,
  type SemanticWorkerVisualState,
} from './semanticEffects';
import type { BeingPresentation, WorkerPresentationState } from './semanticKernel';

const workerRecords = (...states: WorkerPresentationState[]) => states.map((state, cursor) => ({
  workerId: `worker-${cursor}`,
  state,
  cursor,
}));

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

describe('semantic organism effect transitions', () => {
  it('emits a cue only when a semantic signal enters the posture', () => {
    const previous = base({ signals: ['worker-requested'] });
    const current = base({ signals: ['worker-requested', 'verification-pass'], motion: 'verify' });

    expect(deriveSemanticEffectTransition(previous, current).enteredSignals).toEqual(['verification-pass']);
    expect(deriveSemanticEffectTransition(current, current).enteredSignals).toEqual([]);
  });

  it('maps bounded worker lifecycle states to temporary visual postures', () => {
    const current = base({
      workers: workerRecords('requested', 'admitted', 'active', 'awaiting-capability', 'returned', 'dissolved', 'failed', 'killed'),
    });

    const result = deriveSemanticEffectTransition(null, current);
    expect(result.workerVisualStates).toEqual<SemanticWorkerVisualState[]>([
      'bud', 'branch', 'conduct', 'held', 'returning', 'dissolved', 'held', 'held',
    ]);
  });

  it('does not request an action pulse for a stopped organism', () => {
    const current = base({ phase: 'stopped', motion: 'stop', coherence: 'stopped', signals: ['emergency-stop'] });
    expect(deriveSemanticEffectTransition(null, current).actionPulse).toBe(false);
  });

  it('freezes action-bearing worker visuals when Emergency Stop is engaged', () => {
    const current = base({
      phase: 'stopped',
      motion: 'stop',
      coherence: 'stopped',
      signals: ['emergency-stop', 'worker-active'],
      workers: workerRecords('requested', 'admitted', 'active', 'awaiting-capability'),
    });

    expect(deriveSemanticEffectTransition(null, current).workerVisualStates).toEqual([
      'held', 'held', 'held', 'held',
    ]);
  });

  it('marks all action-bearing effects suppressed for a stopped posture', () => {
    expect(isActionPresentationStopped(base({ phase: 'stopped', coherence: 'stopped', motion: 'stop' }))).toBe(true);
    expect(isActionPresentationStopped(base({ phase: 'resting', coherence: 'fresh', motion: 'calm' }))).toBe(false);
  });

  it('expires terminal worker motes even when no later mirror event arrives', () => {
    const motes = {
      active: { terminalAt: null },
      returning: { terminalAt: 1_000 },
      dissolved: { terminalAt: 1_000 },
    };

    expect(pruneExpiredWorkerMotes(motes, 2_599)).toEqual(motes);
    expect(pruneExpiredWorkerMotes(motes, 2_600)).toEqual({ active: { terminalAt: null } });
  });
});
