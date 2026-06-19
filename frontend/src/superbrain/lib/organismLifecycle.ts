import type { AnatomicalRootSystemSnapshot } from './anatomicalRootSystem';
import type { CompletionReflexSnapshot } from './completionReflex';
import type { LivingOrchestration, OrchestratedSurface } from './livingOrchestrator';
import type { OutcomeImprintSnapshot } from './outcomeImprint';
import type { MaterializedTabRecord } from './tabStore';
import type { TurnMetabolismSnapshot } from './turnMetabolism';

export type OrganismLifecyclePhase =
  | 'booting'
  | 'arrival'
  | 'rest'
  | 'attentive'
  | 'intake'
  | 'materializing'
  | 'working'
  | 'conducting'
  | 'approval_hold'
  | 'error_repair'
  | 'completion_settle'
  | 'reabsorbing';

export type OrganismBodyPosture =
  | 'dormant'
  | 'waking'
  | 'breathing'
  | 'listening'
  | 'forming_surface'
  | 'focused_work'
  | 'conducting_work'
  | 'holding_decision'
  | 'repairing_scar'
  | 'settling_memory'
  | 'reabsorbing_memory';

export type OrganismBodyEvent =
  | 'none'
  | 'arrival_ignition'
  | 'intent_rise'
  | 'surface_birth'
  | 'work_grip'
  | 'attention_conduction'
  | 'approval_hold'
  | 'pain_return'
  | 'completion_settle'
  | 'memory_reabsorption';

export type OrganismSurfaceBodyRole =
  | 'intake'
  | 'active_work'
  | 'waiting_work'
  | 'approval_hold'
  | 'correction'
  | 'completion'
  | 'reabsorbing'
  | 'memory';

export interface OrganismSurfaceLifecycle {
  id: string;
  kind: MaterializedTabRecord['kind'];
  lifecycle: MaterializedTabRecord['lifecycle'];
  seatIndex: number | null;
  surfaceRole: OrchestratedSurface['role'];
  bodyRole: OrganismSurfaceBodyRole;
  focused: boolean;
  waitingIndex: number;
  stale: boolean;
  staleReason: string | null;
  filepath: string | null;
}

export interface OrganismLifecycleInput {
  orchestration: LivingOrchestration;
  metabolism?: TurnMetabolismSnapshot | null;
  outcome?: OutcomeImprintSnapshot | null;
  completion?: CompletionReflexSnapshot | null;
  rootSystem?: AnatomicalRootSystemSnapshot | null;
}

export interface OrganismLifecycleSnapshot {
  phase: OrganismLifecyclePhase;
  posture: OrganismBodyPosture;
  bodyEvent: OrganismBodyEvent;
  activeSurfaceId: string | null;
  activeSeatIndex: number | null;
  intakeSurfaceId: string | null;
  approvalSurfaceId: string | null;
  completionTargetId: string | null;
  waitingSurfaceIds: string[];
  reabsorbingSurfaceIds: string[];
  staleSurfaceIds: string[];
  conductorOrder: string[];
  surfaceCount: number;
  workspaceCount: number;
  visibleCount: number;
  metabolismPhase: TurnMetabolismSnapshot['phase'] | 'unknown';
  outcomeKind: OutcomeImprintSnapshot['kind'] | 'unknown';
  completionState: CompletionReflexSnapshot['state'] | 'unknown';
  rootDominantRole: AnatomicalRootSystemSnapshot['dominantRole'] | 'unknown';
  surfaces: OrganismSurfaceLifecycle[];
  invariant: {
    valid: boolean;
    violations: string[];
    corruptionSignature: string | null;
  };
}

function isLiveSurface(tab: MaterializedTabRecord): boolean {
  return tab.lifecycle !== 'retracting';
}

function isWorkspaceSurface(tab: MaterializedTabRecord): boolean {
  return tab.kind !== 'input' && isLiveSurface(tab);
}

function bodyRoleForSurface(
  surface: OrchestratedSurface,
  input: OrganismLifecycleInput,
): OrganismSurfaceBodyRole {
  const tab = surface.tab;
  if (tab.lifecycle === 'retracting') return 'reabsorbing';
  if (input.completion?.targetId === tab.id && input.completion.state === 'settling') return 'completion';
  if (input.completion?.targetId === tab.id && input.completion.state === 'reabsorbing') return 'memory';
  if (surface.role === 'intake') return 'intake';
  if (tab.kind === 'approval') return 'approval_hold';
  if (input.outcome?.kind === 'scar' && surface.focused) return 'correction';
  if (input.metabolism?.phase === 'error' && surface.focused) return 'correction';
  if (surface.role === 'waiting') return 'waiting_work';
  return 'active_work';
}

function duplicateWorkspaceFilepaths(surfaces: readonly OrchestratedSurface[]): Map<string, Set<string>> {
  const byPath = new Map<string, MaterializedTabRecord[]>();
  for (const surface of surfaces) {
    const path = surface.tab.content?.filepath || surface.tab.approval?.filepath || '';
    if (!path || surface.tab.kind === 'input' || surface.tab.lifecycle === 'retracting') continue;
    const current = byPath.get(path) ?? [];
    current.push(surface.tab);
    byPath.set(path, current);
  }

  const stale = new Map<string, Set<string>>();
  for (const [path, tabs] of byPath.entries()) {
    if (tabs.length < 2) continue;
    const sorted = [...tabs].sort((a, b) => b.bornAt - a.bornAt);
    for (const tab of sorted.slice(1)) {
      const reasons = stale.get(tab.id) ?? new Set<string>();
      reasons.add(`duplicate-workspace-filepath:${path}`);
      stale.set(tab.id, reasons);
    }
  }
  return stale;
}

function phaseFor(input: OrganismLifecycleInput): OrganismLifecyclePhase {
  const { orchestration, metabolism, outcome, completion } = input;
  const hasInput = orchestration.surfaces.some((surface) => surface.tab.kind === 'input' && isLiveSurface(surface.tab));
  const hasWorkspace = orchestration.surfaces.some((surface) => isWorkspaceSurface(surface.tab));

  if (outcome?.kind === 'scar' || metabolism?.phase === 'error' || completion?.state === 'held') return 'error_repair';
  if (orchestration.reabsorbing || completion?.state === 'reabsorbing') return 'reabsorbing';
  if (completion?.state === 'settling') return 'completion_settle';
  if (orchestration.approvalHeld || metabolism?.phase === 'approval') return 'approval_hold';
  if (orchestration.materializing) return 'materializing';
  if (orchestration.workspaceCount > 1) return 'conducting';
  if (orchestration.workspaceCount === 1 || hasWorkspace) return 'working';
  if (hasInput) return 'intake';
  if (orchestration.phase === 'booting') return 'booting';
  if (orchestration.phase === 'arrival') return 'arrival';
  if (orchestration.phase === 'attentive') return 'attentive';
  return 'rest';
}

function postureFor(phase: OrganismLifecyclePhase): OrganismBodyPosture {
  const postureByPhase: Record<OrganismLifecyclePhase, OrganismBodyPosture> = {
    booting: 'dormant',
    arrival: 'waking',
    rest: 'breathing',
    attentive: 'listening',
    intake: 'listening',
    materializing: 'forming_surface',
    working: 'focused_work',
    conducting: 'conducting_work',
    approval_hold: 'holding_decision',
    error_repair: 'repairing_scar',
    completion_settle: 'settling_memory',
    reabsorbing: 'reabsorbing_memory',
  };
  return postureByPhase[phase];
}

function eventFor(phase: OrganismLifecyclePhase): OrganismBodyEvent {
  const eventByPhase: Record<OrganismLifecyclePhase, OrganismBodyEvent> = {
    booting: 'none',
    arrival: 'arrival_ignition',
    rest: 'none',
    attentive: 'none',
    intake: 'intent_rise',
    materializing: 'surface_birth',
    working: 'work_grip',
    conducting: 'attention_conduction',
    approval_hold: 'approval_hold',
    error_repair: 'pain_return',
    completion_settle: 'completion_settle',
    reabsorbing: 'memory_reabsorption',
  };
  return eventByPhase[phase];
}

function corruptionSignature(violations: readonly string[]): string | null {
  if (violations.length === 0) return null;
  return violations.join('|');
}

export function deriveOrganismLifecycle(input: OrganismLifecycleInput): OrganismLifecycleSnapshot {
  const phase = phaseFor(input);
  const hasActiveWorkspace = input.orchestration.surfaces.some((surface) => isWorkspaceSurface(surface.tab));
  const duplicateReasons = duplicateWorkspaceFilepaths(input.orchestration.surfaces);
  const inputSurfaces = input.orchestration.surfaces.filter((surface) => surface.tab.kind === 'input' && isLiveSurface(surface.tab));
  const violations: string[] = [];

  if (inputSurfaces.length > 1) violations.push('multiple-live-intakes');
  if (input.completion && input.completion.state !== 'idle' && input.completion.targetId) {
    const target = input.orchestration.surfaces.find((surface) => surface.tab.id === input.completion?.targetId);
    if (!target) violations.push(`completion-target-missing:${input.completion.targetId}`);
  }

  const surfaces = input.orchestration.surfaces.map((surface): OrganismSurfaceLifecycle => {
    const staleReasons = duplicateReasons.get(surface.tab.id) ?? new Set<string>();
    if (surface.tab.kind === 'input' && hasActiveWorkspace && isLiveSurface(surface.tab)) {
      staleReasons.add('intake-overlaps-work');
    }
    const staleReason = staleReasons.size > 0 ? [...staleReasons].sort().join(',') : null;
    if (staleReason) violations.push(`${surface.tab.id}:${staleReason}`);

    return {
      id: surface.tab.id,
      kind: surface.tab.kind,
      lifecycle: surface.tab.lifecycle,
      seatIndex: surface.tab.seatIndex,
      surfaceRole: surface.role,
      bodyRole: bodyRoleForSurface(surface, input),
      focused: surface.focused,
      waitingIndex: surface.waitingIndex,
      stale: Boolean(staleReason),
      staleReason,
      filepath: surface.tab.content?.filepath ?? surface.tab.approval?.filepath ?? null,
    };
  });

  const activeSurface =
    surfaces.find((surface) => ['active_work', 'approval_hold', 'correction', 'completion'].includes(surface.bodyRole) && surface.focused) ??
    surfaces.find((surface) => surface.bodyRole === 'intake') ??
    null;

  const staleSurfaceIds = surfaces.filter((surface) => surface.stale).map((surface) => surface.id);
  const reabsorbingSurfaceIds = surfaces
    .filter((surface) => surface.lifecycle === 'retracting' || surface.bodyRole === 'reabsorbing' || surface.bodyRole === 'memory')
    .map((surface) => surface.id);

  const signature = corruptionSignature(violations);
  return {
    phase,
    posture: postureFor(phase),
    bodyEvent: eventFor(phase),
    activeSurfaceId: activeSurface?.id ?? null,
    activeSeatIndex: input.orchestration.activeSeatIndex,
    intakeSurfaceId: surfaces.find((surface) => surface.bodyRole === 'intake')?.id ?? null,
    approvalSurfaceId: surfaces.find((surface) => surface.bodyRole === 'approval_hold')?.id ?? null,
    completionTargetId: input.completion?.targetId ?? null,
    waitingSurfaceIds: surfaces.filter((surface) => surface.bodyRole === 'waiting_work').map((surface) => surface.id),
    reabsorbingSurfaceIds,
    staleSurfaceIds,
    conductorOrder: [...input.orchestration.conductorOrder],
    surfaceCount: surfaces.length,
    workspaceCount: input.orchestration.workspaceCount,
    visibleCount: input.orchestration.visibleCount,
    metabolismPhase: input.metabolism?.phase ?? 'unknown',
    outcomeKind: input.outcome?.kind ?? 'unknown',
    completionState: input.completion?.state ?? 'unknown',
    rootDominantRole: input.rootSystem?.dominantRole ?? 'unknown',
    surfaces,
    invariant: {
      valid: violations.length === 0,
      violations,
      corruptionSignature: signature,
    },
  };
}
