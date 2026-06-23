import type { OrganismLifecyclePhase } from './organismLifecycle';

/**
 * intakeNerveDrive — how the command nerve (the being's INTAKE channel, dock → conus)
 * should behave in each lifecycle phase. The nerve is the mouth the operator speaks
 * into, so it BLAZES while the being is receiving you (attentive → intake) and QUIETS
 * as the being tucks its cauda tail and turns to the work surface (materializing →
 * working → conducting) — mirroring the uSprayHide tail-retract so the channel never
 * floats over the (now hidden) conus. It eases home through completion/reabsorbing to a
 * calm-but-present idle at rest. (Operator: "think how this adjusts in every phase.")
 */

export interface IntakeNerveDrive {
  /** 0..1 channel liveliness → nerve/node opacity + glow + pulse depth. */
  drive: number;
  /** 0..1 command-bead flow toward the socket (your words entering). */
  flow: number;
}

const DRIVE: Record<OrganismLifecyclePhase, IntakeNerveDrive> = {
  // not yet a being — no channel
  booting: { drive: 0, flow: 0 },
  arrival: { drive: 0, flow: 0 },
  // idle: present + calm, a quietly breathing mouth
  rest: { drive: 0.4, flow: 0 },
  // it noticed you — the channel warms, first beads stir
  attentive: { drive: 0.72, flow: 0.32 },
  // PEAK — your words pour down the nerve into the socket
  intake: { drive: 1.0, flow: 1.0 },
  // panel forming → tail retracting → the channel starts to quiet
  materializing: { drive: 0.34, flow: 0 },
  // work surface present → tail retracted → nerve nearly tucked away
  working: { drive: 0.12, flow: 0 },
  // deep multi-surface orchestration → most receded
  conducting: { drive: 0.08, flow: 0 },
  // waiting on YOUR approval → present + expectant (you may speak again)
  approval_hold: { drive: 0.46, flow: 0 },
  // repairing a scar → subdued, holding
  error_repair: { drive: 0.3, flow: 0 },
  // settling → a soft glow as the tail returns
  completion_settle: { drive: 0.5, flow: 0 },
  // inhaling home → easing back toward the idle channel
  reabsorbing: { drive: 0.22, flow: 0 },
};

export function intakeNerveDrive(phase: OrganismLifecyclePhase): IntakeNerveDrive {
  return DRIVE[phase] ?? DRIVE.rest;
}
