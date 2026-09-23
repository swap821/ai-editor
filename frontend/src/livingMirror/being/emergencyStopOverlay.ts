import type { BeingPresentation } from './semanticKernel';

export type EmergencyStopObservation = 'unknown' | 'clear' | 'engaged';

/**
 * Presentation-only safety overlay.
 *
 * A measured engaged latch freezes action-bearing posture and preserves the
 * observed worker evidence for inspection. It does not decide whether work is
 * authorized, approved, executable, or reversible.
 */
export function applyEmergencyStopPresentation(
  presentation: BeingPresentation,
  observation: EmergencyStopObservation,
): BeingPresentation {
  if (observation !== 'engaged') return presentation;
  return {
    ...presentation,
    phase: 'stopped',
    taskState: 'stopped',
    coherence: 'stopped',
    motion: 'stop',
    attention: 'none',
    signals: presentation.signals.includes('emergency-stop')
      ? presentation.signals
      : ['emergency-stop', ...presentation.signals],
  };
}

