import { useSyncExternalStore } from 'react';
import { deriveLivingOrchestration } from './livingOrchestrator';

export type TabLifecycle = 'reaching' | 'unfurling' | 'live' | 'retracting';
export type MaterializedTabKind = 'content' | 'input' | 'approval';
export type AttentionTransferDirection = 'forward' | 'backward' | 'direct';

export interface MaterializedTabContent {
  code: string;
  language: string;
  filepath: string;
}

export interface MaterializedInputSurface {
  text: string;
}

export interface MaterializedApprovalSurface {
  token: string;
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
}

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

let snapshot: TabSnapshot = { tabs: [], focusId: null, attention: null };
const listeners = new Set<() => void>();
let tabSequence = 0;

function emit() {
  for (const listener of listeners) listener();
}

function nextTabId(): string {
  tabSequence += 1;
  return `materialized-tab-${tabSequence}`;
}

function replaceSnapshot(next: TabSnapshot) {
  snapshot = next;
  emit();
}

function nowMs(): number {
  return typeof performance !== 'undefined' && typeof performance.now === 'function' ? performance.now() : Date.now();
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

export function getTabStoreServerSnapshot(): TabSnapshot {
  return snapshot;
}

export function useTabStore(): TabSnapshot {
  return useSyncExternalStore(subscribeTabStore, getTabStoreSnapshot, getTabStoreServerSnapshot);
}

export function getFirstMaterializedTab(): MaterializedTabRecord | null {
  return snapshot.tabs[0] ?? null;
}

export function getFocusedMaterializedTab(): MaterializedTabRecord | null {
  return snapshot.tabs.find((tab) => tab.id === snapshot.focusId) ?? snapshot.tabs[0] ?? null;
}

export function getMaterializedTabByKind(kind: MaterializedTabKind): MaterializedTabRecord | null {
  return snapshot.tabs.find((tab) => tab.kind === kind) ?? null;
}

export function getOccupiedVertebraSeats(): number[] {
  return snapshot.tabs
    .filter((tab) => tab.kind !== 'input' && tab.lifecycle !== 'retracting' && typeof tab.seatIndex === 'number')
    .map((tab) => tab.seatIndex as number);
}

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
  const fromId = deriveLivingOrchestration(snapshot).focusId;
  if (fromId === current.id) return;
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
    lifecycle: 'reaching',
    originLocal: options.originLocal ?? defaults.originLocal,
    targetLocal: options.targetLocal ?? defaults.targetLocal,
    seatIndex: options.seatIndex ?? null,
    content: options.content ?? null,
    input: options.input ?? null,
    approval: options.approval ?? null,
    bornAt,
    phaseStartedAt: bornAt,
  };
}

export function showContentSurface(
  content: MaterializedTabContent,
  options: {
    bornAt?: number;
    originLocal?: [number, number, number];
    targetLocal?: [number, number, number];
    seatIndex?: number | null;
  } = {},
): MaterializedTabRecord {
  const current = snapshot.tabs.find((tab) => tab.kind === 'content' && tab.content?.filepath === content.filepath);
  if (current) {
    const next = {
      ...current,
      content,
      originLocal: options.originLocal ?? current.originLocal,
      targetLocal: options.targetLocal ?? current.targetLocal,
      seatIndex: options.seatIndex ?? current.seatIndex,
    };
    replaceSnapshot({
      tabs: snapshot.tabs.map((tab) => (tab.id === current.id ? next : tab)),
      focusId: next.id,
      attention: null,
    });
    return next;
  }
  const tab = buildMaterializedTab('content', { ...options, content });
  replaceSnapshot({
    tabs: [...snapshot.tabs, tab],
    focusId: tab.id,
    attention: null,
  });
  return tab;
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
      approval,
      originLocal: options.originLocal ?? current.originLocal,
      targetLocal: options.targetLocal ?? current.targetLocal,
      seatIndex: options.seatIndex ?? current.seatIndex,
    };
    replaceSnapshot({
      tabs: snapshot.tabs.map((tab) => (tab.id === current.id ? next : tab)),
      focusId: next.id,
      attention: null,
    });
    return next;
  }
  const tab = buildMaterializedTab('approval', { ...options, approval });
  replaceSnapshot({
    tabs: [...snapshot.tabs, tab],
    focusId: tab.id,
    attention: null,
  });
  return tab;
}

export function updateMaterializedTab(
  id: string,
  patch: Partial<Omit<MaterializedTabRecord, 'id'>>,
): void {
  const current = snapshot.tabs.find((tab) => tab.id === id);
  if (!current) return;
  const tabs = snapshot.tabs.map((tab) => (tab.id === id ? { ...current, ...patch } : tab));
  replaceSnapshot({
    tabs,
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

export function beginRetractingMaterializedTab(id?: string, phaseStartedAt = performance.now()): void {
  const current = id ? snapshot.tabs.find((tab) => tab.id === id) : getFocusedMaterializedTab();
  if (!current) return;
  if (current.lifecycle === 'retracting') return;
  const tabs: MaterializedTabRecord[] = snapshot.tabs.map((tab) =>
    tab.id === current.id ? { ...tab, lifecycle: 'retracting', phaseStartedAt } : tab,
  );
  replaceSnapshot({
    tabs,
    focusId: snapshot.focusId === current.id ? null : snapshot.focusId,
    attention: keepAttentionForTabs(snapshot.attention, tabs),
  });
}

export function clearMaterializedTab(id?: string): void {
  if (!id) {
    replaceSnapshot({ tabs: [], focusId: null, attention: null });
    return;
  }
  const tabs = snapshot.tabs.filter((tab) => tab.id !== id);
  const focusId = snapshot.focusId === id ? tabs.find((tab) => tab.kind !== 'input')?.id ?? null : snapshot.focusId;
  replaceSnapshot({ tabs, focusId, attention: keepAttentionForTabs(snapshot.attention, tabs) });
}

export function __resetTabStoreForTests(): void {
  snapshot = { tabs: [], focusId: null, attention: null };
  tabSequence = 0;
  listeners.clear();
}
