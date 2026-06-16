import { beforeEach, describe, expect, it } from 'vitest';
import {
  __resetTabStoreForTests,
  beginRetractingMaterializedTab,
  clearMaterializedTab,
  getFirstMaterializedTab,
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
    expect(tab.kind).toBe('content');
    expect(tab.lifecycle).toBe('reaching');
    expect(tab.bornAt).toBe(123);
    expect(getFirstMaterializedTab()?.content?.filepath).toBe('demo.py');
  });

  it('replaces the existing tab on a second spawn', () => {
    showContentSurface({ code: 'a', language: 'python', filepath: 'a.py' }, { bornAt: 1 });
    const replacement = showContentSurface({ code: 'b', language: 'python', filepath: 'b.py' }, { bornAt: 2 });
    expect(getTabStoreSnapshot().tabs).toHaveLength(1);
    expect(getFirstMaterializedTab()?.id).toBe(replacement.id);
    expect(getFirstMaterializedTab()?.content?.filepath).toBe('b.py');
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

  it('replaces the input surface with an approval surface', () => {
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
    });
    expect(getFirstMaterializedTab()?.kind).toBe('approval');
    expect(getFirstMaterializedTab()?.id).toBe(approval.id);
    expect(getFirstMaterializedTab()?.approval?.filepath).toBe('demo.py');
  });

  it('can mark the current surface retracting with a fresh phase timestamp', () => {
    const tab = showContentSurface({ code: 'a', language: 'python', filepath: 'a.py' }, { bornAt: 10 });
    setMaterializedTabLifecycle(tab.id, 'live', 25);
    beginRetractingMaterializedTab(tab.id, 40);
    expect(getFirstMaterializedTab()?.lifecycle).toBe('retracting');
    expect(getFirstMaterializedTab()?.phaseStartedAt).toBe(40);
  });

  it('clears the tab', () => {
    const tab = showContentSurface({ code: 'a', language: 'python', filepath: 'a.py' });
    clearMaterializedTab(tab.id);
    expect(getTabStoreSnapshot().tabs).toHaveLength(0);
  });
});
