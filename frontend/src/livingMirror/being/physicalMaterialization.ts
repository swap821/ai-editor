import type {
  AnatomicalConductorSnapshot,
  AnatomicalVertebraRole,
} from '../../superbrain/lib/anatomicalConductor';
import type {
  MaterializedTabKind,
  MaterializedTabRecord,
  TabLifecycle,
} from '../../superbrain/lib/tabStore';

export type PhysicalMaterializationPosture = 'approaching' | 'live' | 'reabsorbing';
export type PhysicalDomContinuity = 'mounted' | 'retracting';
export type PhysicalSurfaceRole = AnatomicalVertebraRole | 'input' | 'unseated';

export interface PhysicalMaterializedSurface {
  id: string;
  kind: MaterializedTabKind;
  lifecycle: TabLifecycle;
  seatIndex: number | null;
  role: PhysicalSurfaceRole;
  posture: PhysicalMaterializationPosture;
  focused: boolean;
  originLocal: [number, number, number];
  targetLocal: [number, number, number];
  domContinuity: PhysicalDomContinuity;
}

export interface PhysicalMaterializationInput {
  tabs: readonly MaterializedTabRecord[];
  conductor: AnatomicalConductorSnapshot;
  focusId: string | null;
}

const MAX_MATERIALIZED_SURFACES = 12;

function postureFor(lifecycle: TabLifecycle): PhysicalMaterializationPosture {
  if (lifecycle === 'reaching' || lifecycle === 'unfurling') return 'approaching';
  if (lifecycle === 'retracting') return 'reabsorbing';
  return 'live';
}

function roleFor(
  tab: MaterializedTabRecord,
  conductor: AnatomicalConductorSnapshot,
): PhysicalSurfaceRole {
  if (tab.kind === 'input') return 'input';
  const signal = conductor.vertebrae.find((candidate) => candidate.seatIndex === tab.seatIndex);
  return signal?.role ?? 'unseated';
}

/**
 * Projects canonical materialized surfaces into bounded physical continuity
 * cues. It does not mount, remove, focus, approve, or execute anything; the
 * tab store and DOM surfaces remain the lifecycle authority.
 */
export function derivePhysicalMaterialization(
  input: PhysicalMaterializationInput,
): PhysicalMaterializedSurface[] {
  return input.tabs.slice(0, MAX_MATERIALIZED_SURFACES).map((tab) => ({
    id: tab.id,
    kind: tab.kind,
    lifecycle: tab.lifecycle,
    seatIndex: tab.seatIndex,
    role: roleFor(tab, input.conductor),
    posture: postureFor(tab.lifecycle),
    focused: tab.id === input.focusId,
    originLocal: [...tab.originLocal] as [number, number, number],
    targetLocal: [...tab.targetLocal] as [number, number, number],
    domContinuity: tab.lifecycle === 'retracting' ? 'retracting' : 'mounted',
  }));
}
