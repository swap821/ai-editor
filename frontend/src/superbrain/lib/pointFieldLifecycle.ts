/**
 * pointFieldLifecycle — maps OrganismLifecyclePhase to scalar animation targets
 * consumed by the point-field shader (grow, flow, arrival, reabsorb).
 *
 * Pure deterministic lookup. No rendering, no React.
 * Falls back to the `rest` row for any unknown phase.
 */
import type { OrganismLifecyclePhase } from './organismLifecycle';

export interface LifecycleTargets {
  /** 0 = unborn (not yet grown/breath gain), 1 = fully grown */
  grow: number;
  /** 0..1 flow-band speed gain through the body axis */
  flow: number;
  /** 0 = scattered inrush origin, 1 = condensed in place */
  arrival: number;
  /** 0 = present, 1 = dissolved up/away */
  reabsorb: number;
}

const PHASE_TARGETS: Record<OrganismLifecyclePhase, LifecycleTargets> = {
  booting:           { grow: 0,   flow: 0.16, arrival: 0, reabsorb: 0 },
  arrival:           { grow: 0.5, flow: 0.45, arrival: 1, reabsorb: 0 },
  rest:              { grow: 1,   flow: 0.16, arrival: 1, reabsorb: 0 },
  attentive:         { grow: 1,   flow: 0.5,  arrival: 1, reabsorb: 0 },
  intake:            { grow: 1,   flow: 0.55, arrival: 1, reabsorb: 0 },
  materializing:     { grow: 1,   flow: 0.9,  arrival: 1, reabsorb: 0 },
  working:           { grow: 1,   flow: 1.0,  arrival: 1, reabsorb: 0 },
  conducting:        { grow: 1,   flow: 1.0,  arrival: 1, reabsorb: 0 },
  approval_hold:     { grow: 1,   flow: 0.34, arrival: 1, reabsorb: 0 },
  error_repair:      { grow: 1,   flow: 0.22, arrival: 1, reabsorb: 0 },
  completion_settle: { grow: 1,   flow: 0.3,  arrival: 1, reabsorb: 0 },
  // POSTER LAW (phase 7): the BEING persists — "the voyage never stops". When a
  // work-tab reabsorbs, only the SLAB dies (ReabsorptionParticles + slab retract);
  // the brain+spine cloud must NOT evaporate. So reabsorb stays 0 here. A future
  // distinct `dying` phase would own the full-being dissolve (reabsorb→1).
  reabsorbing:       { grow: 1,   flow: 0.3,  arrival: 1, reabsorb: 0 },
};

const REST_FALLBACK: LifecycleTargets = PHASE_TARGETS.rest;

/**
 * Return the point-field animation targets for the given lifecycle phase.
 * Unknown phases fall back to the `rest` row (defensive default).
 */
export function lifecycleTargets(phase: OrganismLifecyclePhase): LifecycleTargets {
  return PHASE_TARGETS[phase] ?? REST_FALLBACK;
}
