import { beforeEach, describe, expect, it } from 'vitest';
import {
  __resetTabStoreForTests,
  beginRetractingMaterializedTab,
  clearMaterializedTab,
  focusMaterializedTab,
  focusNextMaterializedTab,
  focusPreviousMaterializedTab,
  getFocusedMaterializedTab,
  getFirstMaterializedTab,
  getMaterializedTabByKind,
  getOccupiedVertebraSeats,
  getTabStoreSnapshot,
  setMaterializedTabLifecycle,
  showApprovalSurface,
  showContentSurface,
  upsertInputSurface,
  updateMaterializedTab,
} from './tabStore';

describe('tabStore', () => {
  beforeEach(() => {
    __resetTabStoreForTests();
  });

  it('spawns a single reaching tab', () => {
    const tab = showContentSurface({ code: 'print(1)', language: 'python', filepath: 'demo.py' }, { bornAt: 123 });
    expect(getTabStoreSnapshot().tabs).toHaveLength(1);
    expect(getTabStoreSnapshot().focusId).toBe(tab.id);
    expect(tab.kind).toBe('content');
    expect(tab.lifecycle).toBe('reaching');
    expect(tab.bornAt).toBe(123);
    expect(getFirstMaterializedTab()?.content?.filepath).toBe('demo.py');
  });

  it('keeps multiple content tabs and focuses the newest one', () => {
    const first = showContentSurface({ code: 'a', language: 'python', filepath: 'a.py' }, { bornAt: 1, seatIndex: 2 });
    const second = showContentSurface({ code: 'b', language: 'python', filepath: 'b.py' }, { bornAt: 2, seatIndex: 3 });
    expect(getTabStoreSnapshot().tabs).toHaveLength(2);
    expect(getFirstMaterializedTab()?.id).toBe(first.id);
    expect(getFocusedMaterializedTab()?.id).toBe(second.id);
    expect(getOccupiedVertebraSeats()).toEqual([2, 3]);
  });

  it('can move focus between seated workspace surfaces', () => {
    const first = showContentSurface({ code: 'a', language: 'python', filepath: 'a.py' }, { seatIndex: 2 });
    const second = showContentSurface({ code: 'b', language: 'python', filepath: 'b.py' }, { seatIndex: 3 });
    expect(getFocusedMaterializedTab()?.id).toBe(second.id);
    expect(getTabStoreSnapshot().attention).toBeNull();
    focusMaterializedTab(first.id);
    expect(getFocusedMaterializedTab()?.id).toBe(first.id);
    expect(getTabStoreSnapshot().attention).toMatchObject({
      fromId: second.id,
      toId: first.id,
      direction: 'direct',
    });
    expect(getTabStoreSnapshot().attention?.startedAt).toEqual(expect.any(Number));
  });

  it('conducts focus along vertebra order and wraps around the spine', () => {
    const lower = showContentSurface({ code: 'c', language: 'python', filepath: 'c.py' }, { bornAt: 1, seatIndex: 5 });
    const upper = showContentSurface({ code: 'a', language: 'python', filepath: 'a.py' }, { bornAt: 2, seatIndex: 2 });
    const middle = showContentSurface({ code: 'b', language: 'python', filepath: 'b.py' }, { bornAt: 3, seatIndex: 3 });

    expect(getFocusedMaterializedTab()?.id).toBe(middle.id);
    expect(focusNextMaterializedTab()?.id).toBe(lower.id);
    expect(getTabStoreSnapshot().attention).toMatchObject({
      fromId: middle.id,
      toId: lower.id,
      direction: 'forward',
    });
    expect(focusNextMaterializedTab()?.id).toBe(upper.id);
    expect(getTabStoreSnapshot().attention).toMatchObject({
      fromId: lower.id,
      toId: upper.id,
      direction: 'forward',
    });
    expect(focusPreviousMaterializedTab()?.id).toBe(lower.id);
    expect(getTabStoreSnapshot().attention).toMatchObject({
      fromId: upper.id,
      toId: lower.id,
      direction: 'backward',
    });
  });

  it('updates an existing content tab with the same filepath instead of duplicating it', () => {
    const first = showContentSurface({ code: 'a', language: 'python', filepath: 'a.py' }, { bornAt: 1, seatIndex: 2 });
    const updated = showContentSurface({ code: 'b', language: 'python', filepath: 'a.py' }, { bornAt: 2 });
    expect(getTabStoreSnapshot().tabs).toHaveLength(1);
    expect(updated.id).toBe(first.id);
    expect(getFocusedMaterializedTab()?.content?.code).toBe('b');
    expect(getFocusedMaterializedTab()?.seatIndex).toBe(2);
  });

  it('updates the live tab in place', () => {
    const tab = showContentSurface({ code: 'a', language: 'python', filepath: 'a.py' });
    updateMaterializedTab(tab.id, { lifecycle: 'live', content: { code: 'b', language: 'python', filepath: 'b.py' } });
    expect(getFirstMaterializedTab()?.lifecycle).toBe('live');
    expect(getFirstMaterializedTab()?.content?.code).toBe('b');
  });

  it('updates the input surface in place while typing', () => {
    const tab = upsertInputSurface('write a graph');
    const next = upsertInputSurface('write a graph in python');
    expect(getFirstMaterializedTab()?.kind).toBe('input');
    expect(getFirstMaterializedTab()?.id).toBe(tab.id);
    expect(next.id).toBe(tab.id);
    expect(getFirstMaterializedTab()?.input?.text).toContain('python');
  });

  it('keeps the input surface while an approval surface claims a vertebra', () => {
    upsertInputSurface('create a file');
    const approval = showApprovalSurface({
      token: 'tok-1',
      summary: 'Approval required to create demo.py',
      explanation: 'Needs write access',
      diff: '+print("hello")\n',
      command: '',
      kindLabel: 'create',
      filepath: 'demo.py',
      content: 'print("hello")\n',
    }, { seatIndex: 2 });
    expect(getTabStoreSnapshot().tabs).toHaveLength(2);
    expect(getMaterializedTabByKind('input')?.input?.text).toBe('create a file');
    expect(getMaterializedTabByKind('approval')?.id).toBe(approval.id);
    expect(getMaterializedTabByKind('approval')?.approval?.filepath).toBe('demo.py');
    expect(getFocusedMaterializedTab()?.id).toBe(approval.id);
    expect(getOccupiedVertebraSeats()).toEqual([2]);
  });

  it('can mark the current surface retracting with a fresh phase timestamp', () => {
    const tab = showContentSurface({ code: 'a', language: 'python', filepath: 'a.py' }, { bornAt: 10 });
    setMaterializedTabLifecycle(tab.id, 'live', 25);
    beginRetractingMaterializedTab(tab.id, 40);
    expect(getMaterializedTabByKind('content')?.lifecycle).toBe('retracting');
    expect(getMaterializedTabByKind('content')?.phaseStartedAt).toBe(40);
  });

  it('clears only the requested tab', () => {
    const first = showContentSurface({ code: 'a', language: 'python', filepath: 'a.py' });
    const tab = showContentSurface({ code: 'b', language: 'python', filepath: 'b.py' });
    clearMaterializedTab(tab.id);
    expect(getTabStoreSnapshot().tabs).toHaveLength(1);
    expect(getFirstMaterializedTab()?.id).toBe(first.id);
  });
});
