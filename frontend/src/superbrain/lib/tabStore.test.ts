import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  __resetTabStoreForTests,
  beginRetractingMaterializedTab,
  claimWorkMaterialization,
  clearMaterializedTab,
  focusMaterializedTab,
  focusNextMaterializedTab,
  focusPreviousMaterializedTab,
  getFocusedMaterializedTab,
  getFirstMaterializedTab,
  getMaterializedTabByKind,
  getOccupiedVertebraSeats,
  getTabStoreSnapshot,
  isWorkMaterializationClaimed,
  releaseWorkMaterialization,
  setMaterializedTabLifecycle,
  showApprovalSurface,
  showContentSurface,
  showReplySurface,
  REPLY_FILEPATH,
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

describe('showReplySurface', () => {
  beforeEach(() => __resetTabStoreForTests());

  it('materializes the reply as a content tab tagged with REPLY_FILEPATH', () => {
    const tab = showReplySurface('Main theek hoon.', { seatIndex: 2 });
    expect(tab.kind).toBe('content');
    expect(tab.content?.filepath).toBe(REPLY_FILEPATH);
    expect(tab.content?.code).toBe('Main theek hoon.');
    expect(tab.seatIndex).toBe(2);
    expect(getMaterializedTabByKind('content')?.id).toBe(tab.id);
  });

  it('updates the SAME tab on a follow-up reply (no duplicate slabs)', () => {
    const first = showReplySurface('one', { seatIndex: 2 });
    const second = showReplySurface('one two', { seatIndex: 2 });
    expect(second.id).toBe(first.id);
    expect(second.content?.code).toBe('one two');
    expect(getTabStoreSnapshot().tabs.filter((t) => t.content?.filepath === REPLY_FILEPATH)).toHaveLength(1);
  });
});

describe('work-materialization claim', () => {
  beforeEach(() => {
    __resetTabStoreForTests();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('is unclaimed by default', () => {
    expect(isWorkMaterializationClaimed()).toBe(false);
  });

  it('is claimed for the given window and expires after it', () => {
    claimWorkMaterialization(15000);
    expect(isWorkMaterializationClaimed()).toBe(true);

    vi.advanceTimersByTime(14999);
    expect(isWorkMaterializationClaimed()).toBe(true);

    vi.advanceTimersByTime(2);
    expect(isWorkMaterializationClaimed()).toBe(false);
  });

  it('releaseWorkMaterialization ends the claim immediately', () => {
    claimWorkMaterialization(15000);
    expect(isWorkMaterializationClaimed()).toBe(true);
    releaseWorkMaterialization();
    expect(isWorkMaterializationClaimed()).toBe(false);
  });

  // Regression for the 2026-07-10 audit: GagosChrome claimed materialization
  // once at turn start with the default 15s window and never refreshed it
  // during streaming, so any turn running longer than 15s before its first
  // re-claim point (tool calls/agent dispatch before the final code
  // emission is a normal turn shape) let the claim lapse mid-flight and the
  // backend's CODE EMITTED auto-fire would materialize a duplicate tab.
  // GagosChrome now re-claims on every streaming chunk (onWritingChunk /
  // onWritingCodeChunk) -- this proves that repeated re-claiming genuinely
  // keeps the window alive past where a single claim would have expired.
  it('repeated re-claiming (simulating streaming chunks) keeps the window alive past a single claim window', () => {
    claimWorkMaterialization(15000);

    // Five chunks, 5s apart -- a 25s turn total, well past the original
    // 15s window, each chunk refreshing the claim like onWritingChunk does.
    for (let i = 0; i < 5; i += 1) {
      vi.advanceTimersByTime(5000);
      expect(isWorkMaterializationClaimed()).toBe(true);
      claimWorkMaterialization();
    }

    // Without a final re-claim, the window still correctly expires 15s
    // after the LAST refresh (not held open forever).
    vi.advanceTimersByTime(15001);
    expect(isWorkMaterializationClaimed()).toBe(false);
  });
});
