import type {
  BeingPresentation,
  BeingSignal,
  WorkerPresentationState,
} from './semanticKernel';

export type SemanticWorkerVisualState = 'bud' | 'branch' | 'conduct' | 'held' | 'returning' | 'dissolved';

export interface SemanticEffectTransition {
  enteredSignals: BeingSignal[];
  workerVisualStates: SemanticWorkerVisualState[];
  actionPulse: boolean;
}

const MAX_VISUAL_WORKERS = 8;
export const WORKER_TERMINAL_LIFETIME_MS = 1_600;

export interface WorkerMoteLifecycle {
  terminalAt: number | null;
}

/**
 * Keeps terminal worker evidence visible for a short, bounded reabsorption
 * window. This is deliberately pure so the renderer can prune without
 * needing another mirror event, and invalid timestamps remain visible rather
 * than being treated as permission to discard evidence.
 */
export function pruneExpiredWorkerMotes<T extends WorkerMoteLifecycle>(
  motes: Record<string, T>,
  now: number,
  lifetimeMs = WORKER_TERMINAL_LIFETIME_MS,
): Record<string, T> {
  if (!Number.isFinite(now) || !Number.isFinite(lifetimeMs) || lifetimeMs < 0) return motes;
  const next: Record<string, T> = {};
  for (const [key, mote] of Object.entries(motes)) {
    if (mote.terminalAt === null || !Number.isFinite(mote.terminalAt) || now - mote.terminalAt < lifetimeMs) {
      next[key] = mote;
    }
  }
  return Object.keys(next).length === Object.keys(motes).length ? motes : next;
}

export function isActionPresentationStopped(presentation: BeingPresentation): boolean {
  return presentation.coherence === 'stopped' || presentation.phase === 'stopped';
}

function workerVisualState(state: WorkerPresentationState, stopped: boolean): SemanticWorkerVisualState {
  if (stopped && ['requested', 'admitted', 'active', 'awaiting-capability'].includes(state)) return 'held';
  switch (state) {
    case 'requested': return 'bud';
    case 'admitted': return 'branch';
    case 'active': return 'conduct';
    case 'awaiting-capability': return 'held';
    case 'returned': return 'returning';
    case 'dissolved': return 'dissolved';
    case 'failed':
    case 'killed':
      return 'held';
    default:
      return 'bud';
  }
}

/**
 * Converts an admitted semantic posture into bounded visual cues. This is a
 * presentation transition only: it cannot authorize, execute, or verify work.
 */
export function deriveSemanticEffectTransition(
  previous: BeingPresentation | null,
  current: BeingPresentation,
): SemanticEffectTransition {
  const previousSignals = new Set(previous?.signals ?? []);
  const stopped = isActionPresentationStopped(current);
  return {
    enteredSignals: current.signals.filter((signal) => !previousSignals.has(signal)),
    workerVisualStates: current.workers.slice(0, MAX_VISUAL_WORKERS).map((state) => workerVisualState(state, stopped)),
    actionPulse: !stopped && current.motion === 'conduct',
  };
}
