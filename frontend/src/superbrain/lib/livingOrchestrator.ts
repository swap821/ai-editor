import type { AttentionTransfer, MaterializedTabRecord } from './tabStore';

export type LivingLifecycleState = 'booting' | 'arriving' | 'rest' | 'attentive';

export type LivingOrchestrationPhase =
  | 'booting'
  | 'arrival'
  | 'rest'
  | 'attentive'
  | 'materializing'
  | 'working'
  | 'conducting'
  | 'approval_hold'
  | 'reabsorbing';

export type OrchestratedSurfaceRole = 'intake' | 'focus' | 'waiting' | 'reabsorbing';

export interface OrchestratedSurface {
  tab: MaterializedTabRecord;
  role: OrchestratedSurfaceRole;
  focused: boolean;
  waitingIndex: number;
}

export interface LivingOrchestrationInput {
  lifecycleState?: LivingLifecycleState;
  tabs: readonly MaterializedTabRecord[];
  focusId: string | null;
  attention?: AttentionTransfer | null;
}

export interface LivingOrchestration {
  phase: LivingOrchestrationPhase;
  focusId: string | null;
  focusKind: MaterializedTabRecord['kind'] | null;
  activeSeatIndex: number | null;
  activeConductionIndex: number;
  previousFocusId: string | null;
  nextFocusId: string | null;
  conductorOrder: string[];
  attention: AttentionTransfer | null;
  workspaceCount: number;
  visibleCount: number;
  approvalHeld: boolean;
  materializing: boolean;
  reabsorbing: boolean;
  surfaces: OrchestratedSurface[];
}

function isWorkspace(tab: MaterializedTabRecord): boolean {
  return tab.kind !== 'input';
}

function isVisible(tab: MaterializedTabRecord): boolean {
  return tab.lifecycle !== 'retracting';
}

function isBeingBorn(tab: MaterializedTabRecord): boolean {
  return tab.lifecycle === 'reaching' || tab.lifecycle === 'unfurling';
}

function compareConductorOrder(a: MaterializedTabRecord, b: MaterializedTabRecord): number {
  const aSeat = typeof a.seatIndex === 'number' ? a.seatIndex : Number.POSITIVE_INFINITY;
  const bSeat = typeof b.seatIndex === 'number' ? b.seatIndex : Number.POSITIVE_INFINITY;
  if (aSeat !== bSeat) return aSeat - bSeat;
  if (a.bornAt !== b.bornAt) return a.bornAt - b.bornAt;
  return a.id.localeCompare(b.id);
}

function compareSurfaceRenderOrder(a: OrchestratedSurface, b: OrchestratedSurface): number {
  const rank = (surface: OrchestratedSurface): number => {
    if (surface.role === 'intake') return 0;
    if (surface.role === 'reabsorbing') return 1;
    if (surface.role === 'waiting') return 2 + surface.waitingIndex;
    return 99;
  };
  return rank(a) - rank(b);
}

export function deriveLivingOrchestration(input: LivingOrchestrationInput): LivingOrchestration {
  const lifecycleState = input.lifecycleState ?? 'rest';
  const workspaceTabs = input.tabs.filter(isWorkspace);
  const visibleWorkspaceTabs = workspaceTabs.filter(isVisible);
  const visibleTabs = input.tabs.filter(isVisible);
  const approvalHeld = visibleWorkspaceTabs.some((tab) => tab.kind === 'approval');
  const materializing = visibleWorkspaceTabs.some(isBeingBorn);
  const reabsorbing = input.tabs.some((tab) => tab.lifecycle === 'retracting');
  const conductorTabs = [...visibleWorkspaceTabs].sort(compareConductorOrder);

  const requestedFocus = conductorTabs.find((tab) => tab.id === input.focusId);
  const fallbackFocus = conductorTabs[conductorTabs.length - 1] ?? null;
  const focusedTab = requestedFocus ?? fallbackFocus;
  const resolvedFocusId = focusedTab?.id ?? null;
  const activeConductionIndex = resolvedFocusId ? conductorTabs.findIndex((tab) => tab.id === resolvedFocusId) : -1;
  const canConduct = conductorTabs.length > 1 && activeConductionIndex >= 0;
  const previousFocusId = canConduct
    ? conductorTabs[(activeConductionIndex - 1 + conductorTabs.length) % conductorTabs.length].id
    : null;
  const nextFocusId = canConduct
    ? conductorTabs[(activeConductionIndex + 1) % conductorTabs.length].id
    : null;

  const waitingTabs = conductorTabs.filter((tab) => tab.id !== resolvedFocusId);
  const waitingOrder = new Map(waitingTabs.map((tab, index) => [tab.id, index]));
  const conductorIds = new Set(conductorTabs.map((tab) => tab.id));
  const attention =
    input.attention &&
    input.attention.fromId &&
    conductorIds.has(input.attention.fromId) &&
    conductorIds.has(input.attention.toId)
      ? input.attention
      : null;

  const surfaces = input.tabs
    .map((tab): OrchestratedSurface => {
      if (tab.kind === 'input') {
        return { tab, role: 'intake', focused: true, waitingIndex: 0 };
      }
      if (tab.lifecycle === 'retracting') {
        return { tab, role: 'reabsorbing', focused: false, waitingIndex: waitingOrder.get(tab.id) ?? 0 };
      }
      if (tab.id === resolvedFocusId) {
        return { tab, role: 'focus', focused: true, waitingIndex: 0 };
      }
      return { tab, role: 'waiting', focused: false, waitingIndex: waitingOrder.get(tab.id) ?? 0 };
    })
    .sort(compareSurfaceRenderOrder);

  let phase: LivingOrchestrationPhase;
  if (approvalHeld) phase = 'approval_hold';
  else if (reabsorbing) phase = 'reabsorbing';
  else if (materializing) phase = 'materializing';
  else if (visibleWorkspaceTabs.length > 1) phase = 'conducting';
  else if (visibleWorkspaceTabs.length === 1) phase = 'working';
  else if (lifecycleState === 'booting') phase = 'booting';
  else if (lifecycleState === 'arriving') phase = 'arrival';
  else if (lifecycleState === 'attentive') phase = 'attentive';
  else phase = 'rest';

  return {
    phase,
    focusId: resolvedFocusId,
    focusKind: focusedTab?.kind ?? null,
    activeSeatIndex: focusedTab?.seatIndex ?? null,
    activeConductionIndex,
    previousFocusId,
    nextFocusId,
    conductorOrder: conductorTabs.map((tab) => tab.id),
    attention,
    workspaceCount: visibleWorkspaceTabs.length,
    visibleCount: visibleTabs.length,
    approvalHeld,
    materializing,
    reabsorbing,
    surfaces,
  };
}
