import { SEGMENT_ANCHORS, SEGMENT_COUNT } from '@/lib/spineAnatomy';
import { deriveSpinalRootActuator, type SpinalRootActuator, type SpinalRootFlow, type SpinalRootRole } from './spinalRootActuator';
import type { OrchestratedSurface } from './livingOrchestrator';
import type { OutcomeImprintSnapshot } from './outcomeImprint';
import type { TurnMetabolismSnapshot } from './turnMetabolism';

export type Vec3Tuple = [number, number, number];
export type AnatomicalRootSide = 'left' | 'right';
export type AnatomicalRootChannel = 'upper' | 'middle' | 'lower';

export interface AnatomicalRootSystemInput {
  surfaces: readonly OrchestratedSurface[];
  metabolism?: TurnMetabolismSnapshot | null;
  outcome?: OutcomeImprintSnapshot | null;
}

export interface AnatomicalRootStrand {
  id: string;
  tabId: string;
  kind: OrchestratedSurface['tab']['kind'];
  seatIndex: number;
  side: AnatomicalRootSide;
  channel: AnatomicalRootChannel;
  role: SpinalRootRole;
  flow: SpinalRootFlow;
  startLocal: Vec3Tuple;
  midALocal: Vec3Tuple;
  midBLocal: Vec3Tuple;
  endLocal: Vec3Tuple;
  radius: number;
  opacity: number;
  tension: number;
  stiffness: number;
  clampOpacity: number;
  beadSpeed: number;
  pulseRate: number;
  tint: string;
  secondaryTint: string;
  memoryTrace: number;
  flowDelay: number;
}

export interface CaudaEquinaTrace {
  id: string;
  tabId: string;
  sourceSeatIndex: number;
  side: AnatomicalRootSide;
  role: SpinalRootRole;
  flow: 'return' | 'bidirectional';
  startLocal: Vec3Tuple;
  midLocal: Vec3Tuple;
  endLocal: Vec3Tuple;
  radius: number;
  opacity: number;
  beadSpeed: number;
  tint: string;
  memoryStrength: number;
  flowDelay: number;
}

export interface AnatomicalRootSystemSnapshot {
  strands: AnatomicalRootStrand[];
  caudaTraces: CaudaEquinaTrace[];
  activeSeatIndexes: number[];
  waitingSeatIndexes: number[];
  heldSeatIndexes: number[];
  errorSeatIndexes: number[];
  reabsorbingSeatIndexes: number[];
  sprayIntensity: number;
  dominantRole: SpinalRootRole;
}

const CHANNELS: ReadonlyArray<{ channel: AnatomicalRootChannel; offset: number; depth: number }> = [
  { channel: 'upper', offset: 0.062, depth: 0.024 },
  { channel: 'middle', offset: 0, depth: 0.04 },
  { channel: 'lower', offset: -0.068, depth: 0.018 },
];

const ROLE_RANK: Record<SpinalRootRole, number> = {
  resting: 0,
  sensing: 1,
  gripping: 2,
  reabsorbing: 3,
  conducting: 4,
  error: 5,
  holding: 6,
};

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function round4(value: number): number {
  return Math.round(value * 10000) / 10000;
}

function tuple(x: number, y: number, z: number): Vec3Tuple {
  return [round4(x), round4(y), round4(z)];
}

function isValidSeat(seatIndex: unknown): seatIndex is number {
  return typeof seatIndex === 'number' && seatIndex >= 0 && seatIndex < SEGMENT_ANCHORS.length;
}

function sideSign(side: AnatomicalRootSide): number {
  return side === 'right' ? 1 : -1;
}

function sideLabel(sign: number): AnatomicalRootSide {
  return sign > 0 ? 'right' : 'left';
}

function roleMemoryTrace(role: SpinalRootRole, outcome?: OutcomeImprintSnapshot | null): number {
  const outcomeGain =
    outcome?.kind === 'verified' || outcome?.kind === 'accepted'
      ? outcome.rootGlow
      : outcome?.kind === 'scar'
        ? outcome.rootGlow * 0.72
        : 0;
  if (role === 'reabsorbing') return round4(clamp(0.72 + outcomeGain * 0.28, 0, 1));
  if (role === 'error') return round4(clamp(0.5 + outcomeGain * 0.32, 0, 0.9));
  if (role === 'holding') return 0.18;
  if (role === 'conducting') return round4(clamp(outcomeGain * 0.22, 0, 0.24));
  return 0;
}

function shouldEmitCaudaTrace(role: SpinalRootRole, outcome?: OutcomeImprintSnapshot | null): boolean {
  return role === 'reabsorbing' || role === 'error' || outcome?.kind === 'verified' || outcome?.kind === 'accepted';
}

function dominantRole(roles: readonly SpinalRootRole[]): SpinalRootRole {
  return roles.reduce<SpinalRootRole>(
    (dominant, role) => (ROLE_RANK[role] > ROLE_RANK[dominant] ? role : dominant),
    'resting',
  );
}

function traceTintFor(role: SpinalRootRole, actuator: SpinalRootActuator, outcome?: OutcomeImprintSnapshot | null): string {
  if (role === 'error') return '#ff5f7a';
  if (role === 'reabsorbing' || outcome?.kind === 'verified' || outcome?.kind === 'accepted') return '#a9fff3';
  return actuator.tint;
}

export function deriveAnatomicalRootSystem(input: AnatomicalRootSystemInput): AnatomicalRootSystemSnapshot {
  const strands: AnatomicalRootStrand[] = [];
  const caudaTraces: CaudaEquinaTrace[] = [];
  const activeSeatIndexes = new Set<number>();
  const waitingSeatIndexes = new Set<number>();
  const heldSeatIndexes = new Set<number>();
  const errorSeatIndexes = new Set<number>();
  const reabsorbingSeatIndexes = new Set<number>();
  const roles: SpinalRootRole[] = [];

  for (const surface of input.surfaces) {
    const tab = surface.tab;
    if (tab.kind === 'input' || !isValidSeat(tab.seatIndex)) continue;

    const actuator = deriveSpinalRootActuator({
      kind: tab.kind,
      lifecycle: tab.lifecycle,
      focused: surface.focused,
      waitingIndex: surface.waitingIndex,
      metabolism: input.metabolism,
      outcome: input.outcome,
    });
    if (actuator.role === 'resting') continue;

    const seatIndex = tab.seatIndex;
    const anchor = SEGMENT_ANCHORS[seatIndex];
    const seatFactor = SEGMENT_COUNT <= 1 ? 0 : seatIndex / (SEGMENT_COUNT - 1);
    const surfaceSideSign = tab.targetLocal[0] >= anchor.x ? 1 : -1;
    const memoryTrace = roleMemoryTrace(actuator.role, input.outcome);
    roles.push(actuator.role);

    if (actuator.role === 'holding') heldSeatIndexes.add(seatIndex);
    else if (actuator.role === 'error') errorSeatIndexes.add(seatIndex);
    else if (actuator.role === 'reabsorbing') reabsorbingSeatIndexes.add(seatIndex);
    else if (surface.focused) activeSeatIndexes.add(seatIndex);
    else waitingSeatIndexes.add(seatIndex);

    for (const side of [-1, 1]) {
      for (const channel of CHANNELS) {
        const sign = side;
        const sameSideAsSurface = sign === surfaceSideSign;
        const reachBase = 0.34 + seatFactor * 0.54;
        const reach = reachBase * (sameSideAsSurface ? 1.08 : 0.86) + actuator.tension * 0.13;
        const droop = 0.06 + seatFactor * 0.24 + actuator.stiffness * 0.035;
        const yOffset = channel.offset * (1 + actuator.tension * 0.22);
        const endPull = sameSideAsSurface ? 0.07 + actuator.stiffness * 0.12 : -0.015 + actuator.tension * 0.02;
        const start = tuple(anchor.x + sign * 0.028, anchor.y + yOffset * 0.24, anchor.z + channel.depth * 0.18);
        const midA = tuple(
          anchor.x + sign * reach * 0.26,
          anchor.y + yOffset - droop * 0.16,
          anchor.z + 0.054 + channel.depth,
        );
        const midB = tuple(
          anchor.x + sign * reach * 0.66,
          anchor.y + yOffset - droop * 0.58,
          anchor.z + 0.04 + channel.depth * 0.62,
        );
        const end = tuple(
          anchor.x + sign * (reach + endPull),
          anchor.y + yOffset - droop * (0.96 + (channel.channel === 'lower' ? 0.12 : 0)),
          anchor.z + 0.028 + channel.depth * 0.28,
        );
        const channelGain = channel.channel === 'middle' ? 1.08 : channel.channel === 'lower' ? 0.96 : 1;
        const waitingScale = actuator.role === 'sensing' ? 0.72 : 1;

        strands.push({
          id: `${tab.id}-${seatIndex}-${sideLabel(sign)}-${channel.channel}`,
          tabId: tab.id,
          kind: tab.kind,
          seatIndex,
          side: sideLabel(sign),
          channel: channel.channel,
          role: actuator.role,
          flow: actuator.flow,
          startLocal: start,
          midALocal: midA,
          midBLocal: midB,
          endLocal: end,
          radius: round4(clamp((0.0028 + seatFactor * 0.0018) * actuator.radiusGain * channelGain, 0.0012, 0.008)),
          opacity: round4(clamp((0.08 + actuator.opacityGain * 0.13) * waitingScale, 0.025, 0.34)),
          tension: actuator.tension,
          stiffness: actuator.stiffness,
          clampOpacity: round4(clamp((0.12 + actuator.clampScale * 0.26 + actuator.stiffness * 0.22) * waitingScale, 0.08, 0.72)),
          beadSpeed: actuator.beadSpeed,
          pulseRate: actuator.pulseRate,
          tint: actuator.tint,
          secondaryTint: actuator.secondaryTint,
          memoryTrace,
          flowDelay: round4(seatIndex * 0.073 + (channel.channel === 'upper' ? 0.03 : channel.channel === 'lower' ? 0.11 : 0.07)),
        });
      }
    }

    if (shouldEmitCaudaTrace(actuator.role, input.outcome)) {
      const lowerAnchor = SEGMENT_ANCHORS[SEGMENT_ANCHORS.length - 1];
      const tint = traceTintFor(actuator.role, actuator, input.outcome);
      const memoryStrength = round4(clamp(memoryTrace || input.outcome?.rootGlow || 0.42, 0.22, 1));
      for (const side of [-1, 1]) {
        const sign = side;
        const reach = 0.56 + seatFactor * 0.34 + memoryStrength * 0.24;
        caudaTraces.push({
          id: `${tab.id}-cauda-${sideLabel(sign)}`,
          tabId: tab.id,
          sourceSeatIndex: seatIndex,
          side: sideLabel(sign),
          role: actuator.role,
          flow: actuator.flow === 'bidirectional' ? 'bidirectional' : 'return',
          startLocal: tuple(anchor.x + sign * 0.05, anchor.y - 0.02, anchor.z + 0.03),
          midLocal: tuple(lowerAnchor.x + sign * reach * 0.32, lowerAnchor.y + 0.1, lowerAnchor.z + 0.06),
          endLocal: tuple(lowerAnchor.x + sign * reach, lowerAnchor.y - 0.24 - memoryStrength * 0.12, lowerAnchor.z + 0.035),
          radius: round4(clamp(0.0024 + memoryStrength * 0.0026, 0.002, 0.006)),
          opacity: round4(clamp(0.06 + memoryStrength * 0.22, 0.05, 0.34)),
          beadSpeed: round4(clamp(0.08 + actuator.beadSpeed * 0.72 + memoryStrength * 0.08, 0.06, 0.38)),
          tint,
          memoryStrength,
          flowDelay: round4(seatIndex * 0.049 + (sign > 0 ? 0.17 : 0.04)),
        });
      }
    }
  }

  const sprayIntensity = caudaTraces.length
    ? round4(clamp(caudaTraces.reduce((sum, trace) => sum + trace.memoryStrength, 0) / caudaTraces.length, 0, 1))
    : 0;

  return {
    strands,
    caudaTraces,
    activeSeatIndexes: [...activeSeatIndexes].sort((a, b) => a - b),
    waitingSeatIndexes: [...waitingSeatIndexes].sort((a, b) => a - b),
    heldSeatIndexes: [...heldSeatIndexes].sort((a, b) => a - b),
    errorSeatIndexes: [...errorSeatIndexes].sort((a, b) => a - b),
    reabsorbingSeatIndexes: [...reabsorbingSeatIndexes].sort((a, b) => a - b),
    sprayIntensity,
    dominantRole: dominantRole(roles),
  };
}
