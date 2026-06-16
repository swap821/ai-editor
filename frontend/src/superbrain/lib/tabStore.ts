import { useSyncExternalStore } from 'react';

export type TabLifecycle = 'reaching' | 'unfurling' | 'live' | 'retracting';

export interface MaterializedTabContent {
  code: string;
  language: string;
  filepath: string;
}

export interface MaterializedTabRecord {
  id: string;
  lifecycle: TabLifecycle;
  originLocal: [number, number, number];
  targetLocal: [number, number, number];
  content: MaterializedTabContent | null;
  bornAt: number;
}

interface TabSnapshot {
  tabs: MaterializedTabRecord[];
}

const DEFAULT_ORIGIN_LOCAL: [number, number, number] = [0.0, 0.26, 0.48];
const DEFAULT_TARGET_LOCAL: [number, number, number] = [1.18, 0.22, 0.58];

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

export function spawnMaterializedTab(
  content: MaterializedTabContent | null,
  options: {
    bornAt?: number;
    originLocal?: [number, number, number];
    targetLocal?: [number, number, number];
  } = {},
): MaterializedTabRecord {
  const tab: MaterializedTabRecord = {
    id: nextTabId(),
    lifecycle: 'reaching',
    originLocal: options.originLocal ?? DEFAULT_ORIGIN_LOCAL,
    targetLocal: options.targetLocal ?? DEFAULT_TARGET_LOCAL,
    content,
    bornAt: options.bornAt ?? performance.now(),
  };
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
