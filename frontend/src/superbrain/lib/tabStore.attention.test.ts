import { beforeEach, expect, it } from 'vitest';
import {
  __resetTabStoreForTests,
  beginRetractingMaterializedTab,
  closeWorkspace,
  focusWorkspace,
  getOccupiedVertebraSeats,
  getTabStoreSnapshot,
  openWorkspacePanel,
  pinWorkspace,
  showContentSurface,
} from './tabStore';
import { useMirrorStore } from './mirrorStore';
beforeEach(() => __resetTabStoreForTests());
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
