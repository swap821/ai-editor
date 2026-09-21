import { beforeEach, expect, it } from 'vitest';
import { __resetTabStoreForTests, closeWorkspace, focusWorkspace, getTabStoreSnapshot, openWorkspacePanel, pinWorkspace, showContentSurface } from './tabStore';
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
