import { useSyncExternalStore } from 'react';

export type TabLifecycle = 'reaching' | 'unfurling' | 'live' | 'retracting';
export type MaterializedTabKind = 'content' | 'input' | 'approval';

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
  content: MaterializedTabContent | null;
  input: MaterializedInputSurface | null;
  approval: MaterializedApprovalSurface | null;
  bornAt: number;
  phaseStartedAt: number;
}

interface TabSnapshot {
  tabs: MaterializedTabRecord[];
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

let snapshot: TabSnapshot = { tabs: [] };
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

function buildMaterializedTab(
  kind: MaterializedTabKind,
  options: {
    bornAt?: number;
    originLocal?: [number, number, number];
    targetLocal?: [number, number, number];
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
  } = {},
): MaterializedTabRecord {
  const current = snapshot.tabs[0];
  if (current?.kind === 'content') {
    const next = {
      ...current,
      content,
    };
    replaceSnapshot({ tabs: [next] });
    return next;
  }
  const tab = buildMaterializedTab('content', { ...options, content });
  replaceSnapshot({ tabs: [tab] });
  return tab;
}

export function upsertInputSurface(
  text: string,
  options: {
    bornAt?: number;
    originLocal?: [number, number, number];
    targetLocal?: [number, number, number];
  } = {},
): MaterializedTabRecord {
  const current = snapshot.tabs[0];
  if (current?.kind === 'input') {
    const next = {
      ...current,
      input: { text },
    };
    replaceSnapshot({ tabs: [next] });
    return next;
  }
  const tab = buildMaterializedTab('input', { ...options, input: { text } });
  replaceSnapshot({ tabs: [tab] });
  return tab;
}

export function showApprovalSurface(
  approval: MaterializedApprovalSurface,
  options: {
    bornAt?: number;
    originLocal?: [number, number, number];
    targetLocal?: [number, number, number];
  } = {},
): MaterializedTabRecord {
  const current = snapshot.tabs[0];
  if (current?.kind === 'approval') {
    const next = {
      ...current,
      approval,
    };
    replaceSnapshot({ tabs: [next] });
    return next;
  }
  const tab = buildMaterializedTab('approval', { ...options, approval });
  replaceSnapshot({ tabs: [tab] });
  return tab;
}

export function updateMaterializedTab(
  id: string,
  patch: Partial<Omit<MaterializedTabRecord, 'id'>>,
): void {
  const current = snapshot.tabs[0];
  if (!current || current.id !== id) return;
  replaceSnapshot({
    tabs: [{ ...current, ...patch }],
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
  const current = snapshot.tabs[0];
  if (!current) return;
  if (id && current.id !== id) return;
  if (current.lifecycle === 'retracting') return;
  replaceSnapshot({
    tabs: [{ ...current, lifecycle: 'retracting', phaseStartedAt }],
  });
}

export function clearMaterializedTab(id?: string): void {
  if (!id || snapshot.tabs[0]?.id === id) {
    replaceSnapshot({ tabs: [] });
  }
}

export function __resetTabStoreForTests(): void {
  snapshot = { tabs: [] };
  tabSequence = 0;
  listeners.clear();
}
