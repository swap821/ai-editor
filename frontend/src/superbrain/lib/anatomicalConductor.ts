import { SEGMENT_ANCHORS } from '@/lib/spineAnatomy';
import type { LivingOrchestration, LivingOrchestrationPhase } from './livingOrchestrator';
import type { MaterializedTabRecord } from './tabStore';

export type AnatomicalVertebraRole = 'idle' | 'waiting' | 'active' | 'held' | 'reabsorbing';
export type Vec3Tuple = [number, number, number];

export interface AnatomicalVertebraSignal {
  seatIndex: number;
  role: AnatomicalVertebraRole;
  anchorLocal: Vec3Tuple;
  intensity: number;
  socketOpacity: number;
  rootOpacity: number;
  ringScale: number;
  tint: string;
  flowDelay: number;
}

export interface AnatomicalConductorSnapshot {
  phase: LivingOrchestrationPhase;
  activeSeatIndex: number | null;
  occupiedSeatIndexes: number[];
  conductingSeatIndexes: number[];
  vertebrae: AnatomicalVertebraSignal[];
  trunkIntensity: number;
  trunkTint: string;
  hold: boolean;
}

export interface AnatomicalConductorInput {
  tabs: readonly MaterializedTabRecord[];
  orchestration: Pick<LivingOrchestration, 'phase' | 'focusId' | 'activeSeatIndex'>;
}

const ROLE_RANK: Record<AnatomicalVertebraRole, number> = {
  idle: 0,
  waiting: 1,
  reabsorbing: 2,
  active: 3,
  held: 4,
};

const ROLE_PROFILE: Record<
  AnatomicalVertebraRole,
  { intensity: number; socketOpacity: number; rootOpacity: number; ringScale: number; tint: string }
> = {
  idle: { intensity: 0, socketOpacity: 0, rootOpacity: 0, ringScale: 1, tint: '#79ebff' },
  waiting: { intensity: 0.34, socketOpacity: 0.11, rootOpacity: 0.08, ringScale: 0.86, tint: '#6f9dff' },
  active: { intensity: 1, socketOpacity: 0.34, rootOpacity: 0.2, ringScale: 1.08, tint: '#8dffd1' },
  held: { intensity: 0.94, socketOpacity: 0.3, rootOpacity: 0.16, ringScale: 1.04, tint: '#ffb06e' },
  reabsorbing: { intensity: 0.72, socketOpacity: 0.22, rootOpacity: 0.13, ringScale: 0.96, tint: '#a9fff3' },
};

const PHASE_GAIN: Record<LivingOrchestrationPhase, number> = {
  booting: 0.2,
  arrival: 0.28,
  rest: 0,
  attentive: 0.32,
  materializing: 0.78,
  working: 0.86,
  conducting: 0.94,
  approval_hold: 0.74,
  reabsorbing: 0.68,
};

function round4(value: number): number {
  return Math.round(value * 10000) / 10000;
}

function tupleFromAnchor(seatIndex: number): Vec3Tuple {
  const anchor = SEGMENT_ANCHORS[seatIndex];
  return [round4(anchor.x), round4(anchor.y), round4(anchor.z)];
}

function isWorkspace(tab: MaterializedTabRecord): boolean {
  return tab.kind !== 'input' && typeof tab.seatIndex === 'number';
}

function isValidSeat(seatIndex: number): boolean {
  return seatIndex >= 0 && seatIndex < SEGMENT_ANCHORS.length;
}

function roleForTab(tab: MaterializedTabRecord, orchestration: AnatomicalConductorInput['orchestration']): AnatomicalVertebraRole {
  if (tab.lifecycle === 'retracting') return 'reabsorbing';
  if (tab.kind === 'approval' && orchestration.phase === 'approval_hold') return 'held';
  if (tab.id === orchestration.focusId) return 'active';
  return 'waiting';
}

function strongerRole(current: AnatomicalVertebraRole, next: AnatomicalVertebraRole): AnatomicalVertebraRole {
  return ROLE_RANK[next] > ROLE_RANK[current] ? next : current;
}

function targetSeatFromRoles(rolesBySeat: ReadonlyMap<number, AnatomicalVertebraRole>, activeSeatIndex: number | null): number | null {
  if (typeof activeSeatIndex === 'number' && isValidSeat(activeSeatIndex)) return activeSeatIndex;

  const preferred: AnatomicalVertebraRole[] = ['held', 'active', 'reabsorbing', 'waiting'];
  for (const role of preferred) {
    const match = [...rolesBySeat.entries()].find(([, candidateRole]) => candidateRole === role);
    if (match) return match[0];
  }
  return null;
}

function conductingPath(targetSeatIndex: number | null): number[] {
  if (targetSeatIndex === null) return [];
  return Array.from({ length: targetSeatIndex + 1 }, (_, index) => index);
}

function trunkTintFor(snapshot: {
  phase: LivingOrchestrationPhase;
  targetRole: AnatomicalVertebraRole;
}): string {
  if (snapshot.targetRole === 'held' || snapshot.phase === 'approval_hold') return '#ffb06e';
  if (snapshot.targetRole === 'reabsorbing' || snapshot.phase === 'reabsorbing') return '#a9fff3';
  return '#8dffd1';
}

export function deriveAnatomicalConductor(input: AnatomicalConductorInput): AnatomicalConductorSnapshot {
  const rolesBySeat = new Map<number, AnatomicalVertebraRole>();

  for (const tab of input.tabs) {
    if (!isWorkspace(tab)) continue;
    const seatIndex = tab.seatIndex as number;
    if (!isValidSeat(seatIndex)) continue;
    const nextRole = roleForTab(tab, input.orchestration);
    const currentRole = rolesBySeat.get(seatIndex) ?? 'idle';
    rolesBySeat.set(seatIndex, strongerRole(currentRole, nextRole));
  }

  const activeSeatIndex = targetSeatFromRoles(rolesBySeat, input.orchestration.activeSeatIndex);
  const targetRole = activeSeatIndex === null ? 'idle' : rolesBySeat.get(activeSeatIndex) ?? 'idle';
  const phaseGain = PHASE_GAIN[input.orchestration.phase] ?? 0.5;

  const vertebrae = SEGMENT_ANCHORS.map((_, seatIndex): AnatomicalVertebraSignal => {
    const role = rolesBySeat.get(seatIndex) ?? 'idle';
    const profile = ROLE_PROFILE[role];
    const signalGain = role === 'idle' ? 0 : Math.max(0.38, phaseGain);
    return {
      seatIndex,
      role,
      anchorLocal: tupleFromAnchor(seatIndex),
      intensity: round4(profile.intensity * signalGain),
      socketOpacity: round4(profile.socketOpacity * signalGain),
      rootOpacity: round4(profile.rootOpacity * signalGain),
      ringScale: round4(profile.ringScale),
      tint: profile.tint,
      flowDelay: round4(seatIndex * 0.071),
    };
  });

  const occupiedSeatIndexes = vertebrae
    .filter((signal) => signal.role !== 'idle')
    .map((signal) => signal.seatIndex);
  const conductingSeatIndexes = conductingPath(activeSeatIndex);
  const targetSignal = activeSeatIndex === null ? null : vertebrae[activeSeatIndex] ?? null;
  const trunkIntensity =
    conductingSeatIndexes.length > 0 ? round4(Math.max(targetSignal?.intensity ?? 0, 0.34) * Math.max(phaseGain, 0.42)) : 0;

  return {
    phase: input.orchestration.phase,
    activeSeatIndex,
    occupiedSeatIndexes,
    conductingSeatIndexes,
    vertebrae,
    trunkIntensity,
    trunkTint: trunkTintFor({ phase: input.orchestration.phase, targetRole }),
    hold: input.orchestration.phase === 'approval_hold' || targetRole === 'held',
  };
}
