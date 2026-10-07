import { useSyncExternalStore } from 'react';
import { deriveLivingOrchestration } from './livingOrchestrator';
import { getContentSurfacePlacement } from './materializedSurfaceAnchors';

export type TabLifecycle = 'reaching' | 'unfurling' | 'live' | 'retracting';
export type MaterializedTabKind = 'content' | 'input' | 'approval';
export type AttentionTransferDirection = 'forward' | 'backward' | 'direct';

export interface MaterializedTabContent {
  code: string;
  language: string;
  filepath: string;
  /** Admitted mirror cursor for an unnamed code result; not a backend file,
   *  task, execution or verification identity. Never used as display text. */
  sourceEventId?: number;
  /** True while the being is still WRITING this surface (code may be empty or
   *  partial) — the slab shows a "writing…" cue + cursor. Cleared (false) once
   *  generation ends, including interruption or local cancellation. This flag
   *  alone does NOT establish a completed result. */
  streaming?: boolean;
  /** A retained nonterminal/partial result. Permission hold, submitted replay,
   *  decline and local cancellation imply neither completion nor verification;
   *  local cancellation does not establish backend termination. */
  completion?: 'incomplete' | 'cancelled' | 'awaiting-approval' | 'awaiting-replay' | 'declined';
  /** PREVIEW of the work's result: the verdict + captured run/verify output, so
   *  the focused slab can show what the code DID (not just what it says). Set when
   *  a verify_result for this file arrives. */
  verifyVerdict?: 'pass' | 'fail';
  verifyOutput?: string;
  /** Admitted mirror cursor of the check actually matched by the artifact
   *  owner. Not a backend version ID or an independently executed check.
   *  Retain only with the identical code/path/language snapshot. */
  verifyEventId?: number;
}

export interface MaterializedInputSurface {
  text: string;
}

export interface MaterializedApprovalSurface {
  requestRef: string;
  summary: string;
  explanation: string;
  diff: string;
  command: string;
  kindLabel: string;
  filepath: string;
  content: string;
}

export interface MaterializedTabRecord {
  id: string;
  kind: MaterializedTabKind;
  lifecycle: TabLifecycle;
  originLocal: [number, number, number];
  targetLocal: [number, number, number];
  seatIndex: number | null;
  content: MaterializedTabContent | null;
  input: MaterializedInputSurface | null;
  approval: MaterializedApprovalSurface | null;
  bornAt: number;
  phaseStartedAt: number;
  missionId?: string | null;
  workspaceId?: string | null;
  artifactId?: string | null;
  pinned?: boolean;
  /** Guards a renderer completion belonging to an older dismissal. */
  retractionToken?: number;
  /** Full late content is readable even when no physical anchor is free. */
  recoverySeatPending?: boolean;
}

export interface WorkspacePanel {
  id: string;
  title: string;
  kind: string;
  /** History remains readable when all body anchors are occupied. */
  seatIndex: number | null;
  open: boolean;
  pinned: boolean;
  file?: { path: string; name?: string; content: string };
}

export interface AttentionTransfer {
  fromId: string | null;
  toId: string;
  direction: AttentionTransferDirection;
  startedAt: number;
}

export interface TabSnapshot {
  tabs: MaterializedTabRecord[];
  focusId: string | null;
  attention: AttentionTransfer | null;
  panels?: WorkspacePanel[];
  selectedMissionId?: string | null;
  /** Session-only content retained by the same owner, never scene entities. */
  recoverableTabs?: MaterializedTabRecord[];
  recoveryIssue?: 'capacity' | 'seats-full' | 'grew' | null;
  /** The latest nonterminal local generation, independent of reader visibility.
   *  Not a backend outcome/stop/verifier receipt. Cleared by the next local
   *  request or whole-session privacy cleanup, not Close/Forget or visual decay. */
  workResultOutcome?: { tabId: string; completion: NonNullable<MaterializedTabContent['completion']> } | null;
}

// Bounds retained records and UTF-16 text payload, not total browser/GPU memory.
export const RECOVERABLE_RESULT_LIMIT = 12;
export const RECOVERABLE_TEXT_BYTES = 4 * 1024 * 1024;

const SURFACE_DEFAULTS: Record<
  MaterializedTabKind,
  { originLocal: [number, number, number]; targetLocal: [number, number, number] }
> = {
  content: {
    originLocal: [0.0, 0.26, 0.48],
    targetLocal: [1.18, 0.22, 0.58],
  },
  input: {
    originLocal: [0.02, -0.1, 0.24],
    targetLocal: [0.14, -0.52, 0.84],
  },
  approval: {
    originLocal: [0.06, 0.18, 0.42],
    targetLocal: [0.72, 0.08, 0.78],
  },
};

const WORKSPACE_SEAT_ORDER = [2, 3, 1, 4, 5, 0, 6, 7, 8, 9, 10, 11];

let snapshot: TabSnapshot = { tabs: [], focusId: null, attention: null };
const listeners = new Set<() => void>();
let tabSequence = 0;
let retractionSequence = 0;

function recoveryFits(tabs: readonly MaterializedTabRecord[]): boolean {
  return tabs.length <= RECOVERABLE_RESULT_LIMIT && tabs.reduce((bytes, tab) => {
    const content = tab.content;
    return bytes + 2 * [content?.code, content?.language, content?.filepath, content?.verifyOutput,
      tab.missionId, tab.workspaceId, tab.artifactId].reduce<number>((size, value) => size + (value?.length ?? 0), 0);
  }, 0) <= RECOVERABLE_TEXT_BYTES;
}

function emit() {
  for (const listener of listeners) listener();
}

function nextTabId(): string {
  tabSequence += 1;
  return `materialized-tab-${tabSequence}`;
}

function replaceSnapshot(next: TabSnapshot) {
  snapshot = { ...snapshot, ...next };
  emit();
}

function nowMs(): number {
  return typeof performance !== 'undefined' && typeof performance.now === 'function' ? performance.now() : Date.now();
}

function reviveRetraction(
  tab: MaterializedTabRecord,
): Pick<MaterializedTabRecord, 'lifecycle' | 'phaseStartedAt' | 'retractionToken'> | null {
  return tab.lifecycle === 'retracting'
    ? { lifecycle: 'reaching', phaseStartedAt: nowMs(), retractionToken: undefined }
    : null;
}

function keepAttentionForTabs(
  attention: AttentionTransfer | null,
  tabs: readonly MaterializedTabRecord[],
): AttentionTransfer | null {
  if (!attention) return null;
  const toTab = tabs.find((tab) => tab.id === attention.toId && tab.kind !== 'input' && tab.lifecycle !== 'retracting');
  if (!toTab) return null;
  if (!attention.fromId) return attention;
  const fromTab = tabs.find((tab) => tab.id === attention.fromId && tab.kind !== 'input');
  return fromTab ? attention : null;
}

export function subscribeTabStore(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function getTabStoreSnapshot(): TabSnapshot {
  return snapshot;
}

export function setWorkResultOutcome(outcome: TabSnapshot['workResultOutcome']): void {
  replaceSnapshot({ ...snapshot, workResultOutcome: outcome ?? null });
}

export function getTabStoreServerSnapshot(): TabSnapshot {
  return snapshot;
}

export function useTabStore(): TabSnapshot {
  return useSyncExternalStore(subscribeTabStore, getTabStoreSnapshot, getTabStoreServerSnapshot);
}

export function getFirstMaterializedTab(): MaterializedTabRecord | null {
  return snapshot.tabs[0] ?? null;
}

/** A stable local reading label, never an invented filename/backend identity. */
export function getMaterializedTabLabel(tab: Pick<MaterializedTabRecord, 'id' | 'kind' | 'content'>): string {
  if (tab.content?.filepath.trim()) return tab.content.filepath;
  if (tab.kind !== 'content') return tab.kind === 'approval' ? 'Approval review' : 'Input';
  const localOrdinal = /^materialized-tab-(\d+)$/.exec(tab.id)?.[1];
  return localOrdinal ? `Generated result ${localOrdinal}` : 'Generated result';
}

export function getFocusedMaterializedTab(): MaterializedTabRecord | null {
  const focusedPanel = snapshot.panels?.some((panel) => panel.open && panel.id === snapshot.focusId);
  if (focusedPanel) return null;

  const focusId = deriveLivingOrchestration(snapshot).focusId;
  return focusId ? snapshot.tabs.find((tab) => tab.id === focusId) ?? null : null;
}

export function getMaterializedTabByKind(kind: MaterializedTabKind): MaterializedTabRecord | null {
  return snapshot.tabs.find((tab) => tab.kind === kind) ?? null;
}

export function getOccupiedVertebraSeats(): number[] {
  return [...snapshot.tabs
    .filter((tab) => tab.kind !== 'input' && typeof tab.seatIndex === 'number')
    .map((tab) => tab.seatIndex as number), ...(snapshot.panels ?? [])
    .filter((p) => p.open && typeof p.seatIndex === 'number').map((p) => p.seatIndex as number)];
}

function nextAvailableWorkspaceSeat(occupied: ReadonlySet<number>): number | null {
  return WORKSPACE_SEAT_ORDER.find((seat) => !occupied.has(seat)) ?? null;
}

function availableRecoveryPlacement(tab: MaterializedTabRecord): Pick<MaterializedTabRecord,
  'seatIndex' | 'originLocal' | 'targetLocal' | 'recoverySeatPending'> {
  const original = { seatIndex: tab.seatIndex, originLocal: tab.originLocal,
    targetLocal: tab.targetLocal, recoverySeatPending: tab.recoverySeatPending };
  if (tab.seatIndex === null && !tab.recoverySeatPending) return original;
  const occupied = new Set([
    ...snapshot.tabs.filter((other) => other.id !== tab.id && other.kind !== 'input' && other.seatIndex !== null)
      .map((other) => other.seatIndex!),
    ...(snapshot.panels ?? []).filter((panel) => panel.open && typeof panel.seatIndex === 'number')
      .map((panel) => panel.seatIndex as number),
  ]);
  const seatIndex = tab.seatIndex !== null && !occupied.has(tab.seatIndex)
    ? tab.seatIndex : nextAvailableWorkspaceSeat(occupied);
  if (seatIndex === null) return { ...original, seatIndex: null, recoverySeatPending: true };
  return {
    ...(seatIndex !== tab.seatIndex ? getContentSurfacePlacement(seatIndex) : original),
    seatIndex, recoverySeatPending: false,
  };
}

/** One attention owner for DOM workspaces and materialized scene surfaces. No backend commands here. */
export function openWorkspacePanel(id: string, title: string, kind = id, file?: WorkspacePanel['file']): void {
  const panels = snapshot.panels ?? [];
  const current = panels.find((panel) => panel.id === id);
  const occupied = new Set(getOccupiedVertebraSeats());
  const currentSeat = current?.seatIndex ?? null;
  const currentSeatIsValid = typeof currentSeat === 'number' && Number.isInteger(currentSeat)
    && currentSeat >= 0 && currentSeat < WORKSPACE_SEAT_ORDER.length;
  const canReuseCurrentSeat = currentSeatIsValid && (current?.open || !occupied.has(currentSeat));
  const seatIndex = canReuseCurrentSeat ? currentSeat : nextAvailableWorkspaceSeat(occupied);
  // Recovery must not require freeing an anchor by first losing a result.
  // Only the existing History reader may open without a spatial connection.
  if (seatIndex === null && (current?.kind ?? kind) !== 'history') return;
  const panel: WorkspacePanel = current
    ? { ...current, seatIndex, open: true }
    : { id, title, kind, file, seatIndex, open: true, pinned: false };
  replaceSnapshot({ ...snapshot, panels: current ? panels.map((p) => p.id === id ? panel : p) : [...panels, panel], focusId: id, attention: null });
}

export function focusWorkspace(id: string | null): void {
  const panel = snapshot.panels?.find((candidate) => candidate.id === id && candidate.open);
  if (panel?.seatIndex === null) {
    openWorkspacePanel(panel.id, panel.title, panel.kind, panel.file);
  } else if (id === null || panel) {
    replaceSnapshot({ ...snapshot, focusId: id, attention: null });
  } else if (snapshot.recoverableTabs?.some((tab) => tab.id === id)) {
    reopenMaterializedTab(id);
  } else focusMaterializedTab(id);
}

export function closeWorkspace(id: string): void {
  if (snapshot.panels?.some((panel) => panel.id === id)) {
    replaceSnapshot({ ...snapshot, panels: snapshot.panels.map((p) => p.id === id ? { ...p, open: false } : p), focusId: snapshot.focusId === id ? null : snapshot.focusId });
  } else beginRetractingMaterializedTab(id);
}

export function pinWorkspace(id: string): void {
  replaceSnapshot({ ...snapshot, panels: snapshot.panels?.map((p) => p.id === id ? { ...p, pinned: !p.pinned } : p),
    recoverableTabs: snapshot.recoverableTabs?.map((tab) => tab.id === id ? { ...tab, pinned: !tab.pinned } : tab),
    tabs: snapshot.tabs.map((tab) => tab.id === id ? { ...tab, pinned: !tab.pinned } : tab) });
}

export function selectMission(id: string | null): void { replaceSnapshot({ ...snapshot, selectedMissionId: id }); }

export function getSeatForPendingApproval(filepath?: string): number | null {
  const approval = snapshot.tabs.find((tab) => {
    if (tab.kind !== 'approval' || typeof tab.seatIndex !== 'number') return false;
    if (!filepath) return true;
    return tab.approval?.filepath === filepath;
  });
  return approval?.seatIndex ?? null;
}

function focusMaterializedTabWithDirection(id: string, direction: AttentionTransferDirection): void {
  const current = snapshot.tabs.find((tab) => tab.id === id);
  if (!current || current.kind === 'input' || current.lifecycle === 'retracting') return;
  if (current.recoverySeatPending) {
    const placement = availableRecoveryPlacement(current);
    replaceSnapshot({
      tabs: snapshot.tabs.map((tab) => tab.id === id ? { ...tab, ...placement,
        lifecycle: placement.recoverySeatPending ? 'live' : 'reaching', phaseStartedAt: nowMs() } : tab),
      focusId: id, attention: null,
    });
    return;
  }
  const fromId = deriveLivingOrchestration(snapshot).focusId;
  // Scene fallback attention is not the DOM selection (e.g. History is open).
  if (snapshot.focusId === current.id) return;
  replaceSnapshot({
    tabs: snapshot.tabs,
    focusId: current.id,
    attention: {
      fromId,
      toId: current.id,
      direction,
      startedAt: nowMs(),
    },
  });
}

export function focusMaterializedTab(id: string): void {
  focusMaterializedTabWithDirection(id, 'direct');
}

export function focusNextMaterializedTab(): MaterializedTabRecord | null {
  const nextId = deriveLivingOrchestration(snapshot).nextFocusId;
  if (!nextId) return getFocusedMaterializedTab();
  focusMaterializedTabWithDirection(nextId, 'forward');
  return getFocusedMaterializedTab();
}

export function focusPreviousMaterializedTab(): MaterializedTabRecord | null {
  const previousId = deriveLivingOrchestration(snapshot).previousFocusId;
  if (!previousId) return getFocusedMaterializedTab();
  focusMaterializedTabWithDirection(previousId, 'backward');
  return getFocusedMaterializedTab();
}

function buildMaterializedTab(
  kind: MaterializedTabKind,
  options: {
    bornAt?: number;
    originLocal?: [number, number, number];
    targetLocal?: [number, number, number];
    seatIndex?: number | null;
    recoverySeatPending?: boolean;
    content?: MaterializedTabContent | null;
    input?: MaterializedInputSurface | null;
    approval?: MaterializedApprovalSurface | null;
  },
): MaterializedTabRecord {
  const bornAt = options.bornAt ?? performance.now();
  const defaults = SURFACE_DEFAULTS[kind];
  return {
    id: nextTabId(),
    kind,
    lifecycle: options.recoverySeatPending ? 'live' : 'reaching',
    originLocal: options.originLocal ?? defaults.originLocal,
    targetLocal: options.targetLocal ?? defaults.targetLocal,
    seatIndex: options.seatIndex ?? null,
    ...(options.recoverySeatPending ? { recoverySeatPending: true } : {}),
    content: options.content ?? null,
    input: options.input ?? null,
    approval: options.approval ?? null,
    bornAt,
    phaseStartedAt: bornAt,
  };
}

// ── Work-materialization claim ───────────────────────────────────────────────
// GagosChrome (the 2D driver) and the backend's `CODE EMITTED` event (handled in
// MaterializationLayer) are TWO triggers for the same work tab. When the backend
// emits during a GagosChrome work turn, BOTH fire -> duplicate tabs. GagosChrome
// claims the turn so the auto-fire steps aside; whoever isn't claiming materializes.
let workMaterializationClaimUntil = 0;

/** GagosChrome claims this work turn (it will materialize the tab itself). */
export function claimWorkMaterialization(windowMs = 15000): void {
  workMaterializationClaimUntil =
    (typeof performance !== 'undefined' ? performance.now() : Date.now()) + windowMs;
}

/** Release early (e.g. an approval pause hands materialization back to the backend flow). */
export function releaseWorkMaterialization(): void {
  workMaterializationClaimUntil = 0;
}

/** True while GagosChrome owns work materialization — the CODE EMITTED auto-fire skips. */
export function isWorkMaterializationClaimed(): boolean {
  return (typeof performance !== 'undefined' ? performance.now() : Date.now()) < workMaterializationClaimUntil;
}

export function showContentSurface(
  content: MaterializedTabContent,
  options: {
    bornAt?: number;
    originLocal?: [number, number, number];
    targetLocal?: [number, number, number];
    seatIndex?: number | null;
    recoverySeatPending?: boolean;
  } = {},
): MaterializedTabRecord {
  const current = snapshot.tabs.find((tab) => tab.kind === 'content'
    && tab.content?.filepath === content.filepath
    && (Boolean(content.filepath.trim()) || tab.content.sourceEventId === content.sourceEventId));
  if (current) {
    const next = {
      ...current,
      ...(reviveRetraction(current) ?? {}),
      content,
      // Placement options allocate a surface, not a fresh anatomical address
      // on each content update. A previously unseated surface may acquire one.
      ...(current.seatIndex === null ? {
        originLocal: options.originLocal ?? current.originLocal,
        targetLocal: options.targetLocal ?? current.targetLocal,
        seatIndex: options.seatIndex ?? current.seatIndex,
      } : {}),
      ...(current.recoverySeatPending ? availableRecoveryPlacement(current) : {}),
    };
    const tabs = snapshot.tabs.map((tab) => (tab.id === current.id ? next : tab));
    replaceSnapshot({
      tabs,
      // An in-flight same-file turn resumes the existing identity, not a
      // second hidden DOM copy with the same key.
      recoverableTabs: snapshot.recoverableTabs?.filter((tab) => tab.id !== current.id),
      focusId: snapshot.focusId ?? next.id,
      attention: keepAttentionForTabs(snapshot.attention, tabs),
    });
    return next;
  }
  const tab = buildMaterializedTab('content', { ...options, content });
  const tabs = [...snapshot.tabs, tab];
  replaceSnapshot({
    tabs,
    focusId: snapshot.focusId ?? tab.id,
    attention: keepAttentionForTabs(snapshot.attention, tabs),
  });
  return tab;
}

/** Sentinel filepath that marks a content surface as the being's spoken reply
 *  (so MaterializedTab renders it as the being's voice, not a code file). */
export const REPLY_FILEPATH = 'gagos://reply';

/** The being's reply, materialized on the existing vertebra-seated content slab.
 *  Reuses showContentSurface so the slab unfurl/retract + line-by-line reveal
 *  ("speaking") come for free; the REPLY_FILEPATH sentinel re-skins the chrome. */
export function showReplySurface(
  text: string,
  options: {
    bornAt?: number;
    originLocal?: [number, number, number];
    targetLocal?: [number, number, number];
    seatIndex?: number | null;
  } = {},
): MaterializedTabRecord {
  // language is intentionally empty: the renderer branches on REPLY_FILEPATH before inspecting it
  return showContentSurface({ code: text, language: '', filepath: REPLY_FILEPATH }, options);
}

export function upsertInputSurface(
  text: string,
  options: {
    bornAt?: number;
    originLocal?: [number, number, number];
    targetLocal?: [number, number, number];
    seatIndex?: number | null;
  } = {},
): MaterializedTabRecord {
  const current = snapshot.tabs.find((tab) => tab.kind === 'input');
  if (current?.kind === 'input') {
    const next = {
      ...current,
      input: { text },
      originLocal: options.originLocal ?? current.originLocal,
      targetLocal: options.targetLocal ?? current.targetLocal,
    };
    replaceSnapshot({
      tabs: snapshot.tabs.map((tab) => (tab.id === current.id ? next : tab)),
      focusId: snapshot.focusId,
      attention: keepAttentionForTabs(snapshot.attention, snapshot.tabs),
    });
    return next;
  }
  const tab = buildMaterializedTab('input', { ...options, input: { text } });
  replaceSnapshot({
    tabs: [tab, ...snapshot.tabs],
    focusId: snapshot.focusId,
    attention: keepAttentionForTabs(snapshot.attention, [tab, ...snapshot.tabs]),
  });
  return tab;
}

export function showApprovalSurface(
  approval: MaterializedApprovalSurface,
  options: {
    bornAt?: number;
    originLocal?: [number, number, number];
    targetLocal?: [number, number, number];
    seatIndex?: number | null;
  } = {},
): MaterializedTabRecord {
  const current = snapshot.tabs.find((tab) => tab.kind === 'approval');
  if (current?.kind === 'approval') {
    const next = {
      ...current,
      ...(reviveRetraction(current) ?? {}),
      approval,
      originLocal: options.originLocal ?? current.originLocal,
      targetLocal: options.targetLocal ?? current.targetLocal,
      seatIndex: options.seatIndex ?? current.seatIndex,
    };
    replaceSnapshot({
      tabs: snapshot.tabs.map((tab) => (tab.id === current.id ? next : tab)),
      focusId: snapshot.focusId ?? next.id,
      attention: null,
    });
    return next;
  }
  const tab = buildMaterializedTab('approval', { ...options, approval });
  replaceSnapshot({
    tabs: [...snapshot.tabs, tab],
    focusId: snapshot.focusId ?? tab.id,
    attention: null,
  });
  return tab;
}

export function updateMaterializedTab(
  id: string,
  patch: Partial<Omit<MaterializedTabRecord, 'id'>>,
): void {
  const saved = snapshot.recoverableTabs?.find((tab) => tab.id === id);
  const current = snapshot.tabs.find((tab) => tab.id === id) ?? saved;
  if (!current) return;
  // Late content may arrive while closed. A stale frame cannot reopen it.
  let next = { ...current, ...patch, ...(saved ? {
    lifecycle: current.lifecycle, phaseStartedAt: current.phaseStartedAt,
    retractionToken: current.retractionToken,
  } : {}) };
  let recoverableTabs = snapshot.recoverableTabs ?? [];
  let tabs = snapshot.tabs;
  let recoveryIssue = snapshot.recoveryIssue;
  if (saved) {
    recoverableTabs = recoverableTabs.map((tab) => tab.id === id ? next : tab);
    if (!recoveryFits(recoverableTabs)) {
      // Never truncate a growing result to preserve a cache budget. Release its
      // cached copy and keep the full result available as an ordinary workspace.
      recoverableTabs = recoverableTabs.filter((tab) => tab.id !== id);
      const placement = availableRecoveryPlacement(next);
      next = { ...next, ...placement, lifecycle: placement.recoverySeatPending ? 'live' : 'reaching',
        phaseStartedAt: nowMs(), retractionToken: undefined };
      recoveryIssue = 'grew';
      if (!tabs.some((tab) => tab.id === id)) tabs = [...tabs, next];
    }
  }
  tabs = tabs.map((tab) => tab.id === id ? next : tab);
  replaceSnapshot({
    tabs,
    recoverableTabs,
    recoveryIssue,
    focusId: snapshot.focusId,
    attention: keepAttentionForTabs(snapshot.attention, tabs),
  });
}

export function setMaterializedTabLifecycle(
  id: string,
  lifecycle: TabLifecycle,
  phaseStartedAt = performance.now(),
): void {
  updateMaterializedTab(id, { lifecycle, phaseStartedAt });
}

export function beginRetractingMaterializedTab(id?: string, phaseStartedAt = performance.now()): boolean {
  const current = id ? snapshot.tabs.find((tab) => tab.id === id) : getFocusedMaterializedTab();
  if (!current) return false;
  if (current.lifecycle === 'retracting') return true;
  const retiring: MaterializedTabRecord = {
    ...current, lifecycle: 'retracting', phaseStartedAt, retractionToken: ++retractionSequence,
  };
  const keepContent = current.kind === 'content'
    && !!(current.content?.code || current.content?.verifyOutput);
  const recoverableTabs = keepContent
    ? [...(snapshot.recoverableTabs ?? []).filter((tab) => tab.id !== current.id), retiring]
    : snapshot.recoverableTabs ?? [];
  if (keepContent && !recoveryFits(recoverableTabs)) {
    replaceSnapshot({ ...snapshot, recoveryIssue: 'capacity' });
    return false;
  }
  const tabs: MaterializedTabRecord[] = snapshot.tabs.map((tab) =>
    tab.id === current.id ? retiring : tab,
  );
  replaceSnapshot({
    tabs,
    recoverableTabs,
    recoveryIssue: null,
    focusId: snapshot.focusId === current.id ? null : snapshot.focusId,
    attention: keepAttentionForTabs(snapshot.attention, tabs),
  });
  // A readable-only overflow result has no renderer to retire its geometry.
  if (current.recoverySeatPending) finishMaterializedTabRetraction(current.id, retiring.retractionToken);
  return true;
}

/** Retire visual geometry only. This is not data deletion or backend completion. */
export function finishMaterializedTabRetraction(id: string, token?: number): void {
  const current = snapshot.tabs.find((tab) => tab.id === id);
  if (!current || current.lifecycle !== 'retracting' || current.retractionToken !== token) return;
  const tabs = snapshot.tabs.filter((tab) => tab.id !== id);
  replaceSnapshot({ tabs, focusId: snapshot.focusId === id ? null : snapshot.focusId,
    attention: keepAttentionForTabs(snapshot.attention, tabs) });
}

export function reopenMaterializedTab(id: string): boolean {
  const saved = snapshot.recoverableTabs?.find((tab) => tab.id === id);
  if (!saved) return false;
  const placement = availableRecoveryPlacement(saved);
  if (placement.recoverySeatPending) {
    replaceSnapshot({ ...snapshot, recoveryIssue: 'seats-full' });
    return false;
  }
  const reopened: MaterializedTabRecord = {
    ...saved,
    ...placement,
    lifecycle: 'reaching', phaseStartedAt: nowMs(), retractionToken: undefined,
  };
  const tabs = snapshot.tabs.some((tab) => tab.id === id)
    ? snapshot.tabs.map((tab) => tab.id === id ? reopened : tab) : [...snapshot.tabs, reopened];
  replaceSnapshot({ tabs, recoverableTabs: snapshot.recoverableTabs!.filter((tab) => tab.id !== id),
    recoveryIssue: null, focusId: id, attention: null });
  return true;
}

/** Explicit, confirmed forgetting, never a renderer/timer operation. */
export function forgetRecoverableMaterializedTab(id: string): void {
  if (snapshot.recoverableTabs?.some((tab) => tab.id === id)) clearMaterializedTab(id);
}

export function clearMaterializedTab(id?: string): void {
  if (!id) {
    replaceSnapshot({ tabs: [], recoverableTabs: [], recoveryIssue: null, workResultOutcome: null, focusId: null, attention: null });
    return;
  }
  const tabs = snapshot.tabs.filter((tab) => tab.id !== id);
  const focusId = snapshot.focusId === id ? tabs.find((tab) => tab.kind !== 'input')?.id ?? null : snapshot.focusId;
  replaceSnapshot({ tabs, recoverableTabs: snapshot.recoverableTabs?.filter((tab) => tab.id !== id),
    recoveryIssue: null, focusId, attention: keepAttentionForTabs(snapshot.attention, tabs) });
}

export function __resetTabStoreForTests(): void {
  snapshot = { tabs: [], focusId: null, attention: null };
  tabSequence = 0;
  retractionSequence = 0;
  listeners.clear();
  workMaterializationClaimUntil = 0;
}
