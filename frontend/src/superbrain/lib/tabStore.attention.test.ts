import { beforeEach, expect, it } from 'vitest';
import {
  __resetTabStoreForTests,
  beginRetractingMaterializedTab,
  clearMaterializedTab,
  closeWorkspace,
  focusWorkspace,
  focusNextMaterializedTab,
  focusPreviousMaterializedTab,
  getFocusedMaterializedTab,
  getOccupiedVertebraSeats,
  getTabStoreSnapshot,
  openWorkspacePanel,
  pinWorkspace,
  showContentSurface,
  showReplySurface,
  upsertInputSurface,
} from './tabStore';
import { useMirrorStore } from './mirrorStore';
beforeEach(() => __resetTabStoreForTests());
it.each(['same-file', 'new-file', 'unnamed', 'reply'] as const)('keeps explicit Conversation selected when %s content arrives', (kind) => {
  const first = showContentSurface({ filepath: 'a.py', code: 'first', language: 'python' });
  focusWorkspace(null);
  const incoming = kind === 'reply' ? showReplySurface('A real reply') : showContentSurface({
    filepath: kind === 'same-file' ? 'a.py' : kind === 'unnamed' ? '' : 'b.py',
    code: 'new content', language: 'python', ...(kind === 'unnamed' ? { sourceEventId: 7 } : {}),
  });
  expect(getTabStoreSnapshot().focusId).toBeNull();
  expect(getTabStoreSnapshot().attention).toBeNull();
  expect(getFocusedMaterializedTab()).toBeNull();
  expect(getTabStoreSnapshot().tabs.map((tab) => tab.id)).toEqual(kind === 'same-file' ? [first.id] : [first.id, incoming.id]);
  expect(getTabStoreSnapshot().tabs.find((tab) => tab.id === incoming.id)?.content?.code)
    .toBe(kind === 'reply' ? 'A real reply' : 'new content');
  focusWorkspace(incoming.id);
  expect(getFocusedMaterializedTab()?.id).toBe(incoming.id);
});

it('respects Conversation even before the first result and resets that choice at whole-session cleanup', () => {
  focusWorkspace(null);
  const first = showContentSurface({ filepath: 'first.py', code: 'first', language: 'python' });
  expect(getTabStoreSnapshot().focusId).toBeNull();
  expect(getTabStoreSnapshot().tabs.map((tab) => tab.id)).toEqual([first.id]);
  clearMaterializedTab();
  const nextSession = showContentSurface({ filepath: 'next.py', code: 'next', language: 'python' });
  expect(getFocusedMaterializedTab()?.id).toBe(nextSession.id);
});

it.each(['result', 'panel'] as const)('does not undo an explicit %s dismissal on the next content arrival', (kind) => {
  const first = showContentSurface({ filepath: 'a.py', code: 'first', language: 'python' });
  if (kind === 'panel') { openWorkspacePanel('missions', 'Missions'); closeWorkspace('missions'); }
  else closeWorkspace(first.id);
  const incoming = showContentSurface({ filepath: 'b.py', code: 'background', language: 'python' });
  expect(getTabStoreSnapshot().focusId).toBeNull();
  expect(getTabStoreSnapshot().tabs.find((tab) => tab.id === incoming.id)?.content?.code).toBe('background');
  if (kind === 'result') expect(getTabStoreSnapshot().recoverableTabs?.map((tab) => tab.id)).toEqual([first.id]);
});

it('background output and a second surface preserve the operator-selected workspace', () => {
  const first = showContentSurface({ filepath: 'a.py', code: 'first', language: 'python' });
  focusWorkspace(first.id); pinWorkspace(first.id);
  showContentSurface({ filepath: 'b.py', code: 'background', language: 'python' });
  expect(getTabStoreSnapshot().focusId).toBe(first.id);
});
it('closing a panel preserves execution and reopening preserves its seat and file draft', () => {
  useMirrorStore.setState({ activeWorkers: ['w1'] });
  openWorkspacePanel('file:a.py', 'a.py', 'file', { path: 'a.py', content: 'draft' });
  const seat = getTabStoreSnapshot().panels![0].seatIndex;
  closeWorkspace('file:a.py');
  expect(useMirrorStore.getState().activeWorkers).toEqual(['w1']);
  openWorkspacePanel('file:a.py', 'a.py', 'file', { path: 'a.py', content: 'new server text' });
  expect(getTabStoreSnapshot().panels![0]).toMatchObject({ seatIndex: seat, file: { content: 'draft' } });
});
it('a materialized artifact cannot steal focus from an inspection panel', () => {
  openWorkspacePanel('missions', 'Missions');
  showContentSurface({ filepath: 'b.py', code: 'background', language: 'python' });
  expect(getTabStoreSnapshot().focusId).toBe('missions');
  expect(getFocusedMaterializedTab()).toBeNull();
});

it('reopens an existing workspace on a free seat without changing its identity or draft', () => {
  openWorkspacePanel('file:a.py', 'a.py', 'file', { path: 'a.py', content: 'draft' });
  const original = getTabStoreSnapshot().panels![0];
  closeWorkspace(original.id);
  openWorkspacePanel('terminal', 'Terminal');
  openWorkspacePanel(original.id, 'a.py', 'file', { path: 'a.py', content: 'new server text' });

  const panels = getTabStoreSnapshot().panels!;
  const reopened = panels.find((panel) => panel.id === original.id)!;
  const openSeats = panels.filter((panel) => panel.open).map((panel) => panel.seatIndex);
  expect(reopened).toMatchObject({ id: original.id, seatIndex: 3, open: true, file: { content: 'draft' } });
  expect(new Set(openSeats).size).toBe(openSeats.length);
});

it('keeps a retracting surface seat reserved until that surface is cleared', () => {
  const retiring = showContentSurface({ filepath: 'done.py', code: 'done', language: 'python' }, { seatIndex: 2 });
  beginRetractingMaterializedTab(retiring.id);
  openWorkspacePanel('terminal', 'Terminal');

  expect(getOccupiedVertebraSeats()).toEqual([2, 3]);
});

it('does not alias a thirteenth open workspace onto an occupied seat', () => {
  for (let index = 0; index < 12; index += 1) openWorkspacePanel(`panel-${index}`, `Panel ${index}`);
  const before = getTabStoreSnapshot().panels!.map((panel) => panel.seatIndex);

  openWorkspacePanel('overflow', 'Overflow');

  const panels = getTabStoreSnapshot().panels!;
  expect(panels).toHaveLength(12);
  expect(panels.some((panel) => panel.id === 'overflow')).toBe(false);
  expect(new Set(before).size).toBe(12);
});

it('keeps recovery History readable without a phantom seat and connects it only after an anchor is freed', () => {
  for (let index = 0; index < 12; index += 1) openWorkspacePanel(`panel-${index}`, `Panel ${index}`);
  const seats = getOccupiedVertebraSeats();
  openWorkspacePanel('history', 'Recent activity');
  expect(getTabStoreSnapshot().panels?.find((panel) => panel.id === 'history'))
    .toMatchObject({ open: true, seatIndex: null });
  expect(getTabStoreSnapshot().focusId).toBe('history');
  expect(getOccupiedVertebraSeats()).toEqual(seats);
  closeWorkspace('panel-0');
  focusWorkspace('history');
  expect(getTabStoreSnapshot().panels?.find((panel) => panel.id === 'history'))
    .toMatchObject({ open: true, seatIndex: 2 });
  expect(new Set(getOccupiedVertebraSeats()).size).toBe(12);
});

it('does not treat transient intake as a focused workspace when no work surface exists', () => {
  upsertInputSurface('Build the living workspace');

  expect(getFocusedMaterializedTab()).toBeNull();
  expect(focusNextMaterializedTab()).toBeNull();
  expect(focusPreviousMaterializedTab()).toBeNull();
  expect(getTabStoreSnapshot().focusId).toBeNull();
});

it('keeps conversation unselected until an explicit conductor command enters seat order', () => {
  upsertInputSurface('Build the living workspace');
  const first = showContentSurface({ filepath: 'first.py', code: 'first', language: 'python' }, { seatIndex: 2 });
  const last = showContentSurface({ filepath: 'last.py', code: 'last', language: 'python' }, { seatIndex: 4 });
  focusWorkspace(null);

  expect(getFocusedMaterializedTab()).toBeNull();
  expect(focusNextMaterializedTab()?.id).toBe(first.id);
  expect(focusPreviousMaterializedTab()?.id).toBe(last.id);
});
