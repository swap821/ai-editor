import type { BeingCoherence } from './semanticKernel';

export type BeingCadence = 'stable' | 'soft' | 'discontinuous' | 'fragmented' | 'frozen';

export interface BeingCoherenceSemantics {
  /** Multiplier for non-authoritative visual evidence. */
  opacity: number;
  /** Multiplier for non-authoritative travel/conduction motion. */
  motionScale: number;
  cadence: BeingCadence;
}

/**
 * Presentation-only coherence physics. A weaker or older projection is never
 * promoted to a current result; it is only made visibly less solid. The
 * renderer may apply these bounded multipliers but may not use them to decide
 * authority, execution, approval, or verification.
 */
export const BEING_COHERENCE_SEMANTICS: Record<BeingCoherence, BeingCoherenceSemantics> = {
  fresh: { opacity: 1, motionScale: 1, cadence: 'stable' },
  unverified: { opacity: 0.72, motionScale: 0.82, cadence: 'soft' },
  stale: { opacity: 0.38, motionScale: 0.18, cadence: 'discontinuous' },
  degraded: { opacity: 0.56, motionScale: 0.42, cadence: 'fragmented' },
  stopped: { opacity: 0.72, motionScale: 0, cadence: 'frozen' },
};

export function coherenceSemanticsFor(coherence: BeingCoherence): BeingCoherenceSemantics {
  return BEING_COHERENCE_SEMANTICS[coherence];
}
