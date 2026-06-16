import { beforeEach, describe, expect, it } from 'vitest';
import {
  __resetTabStoreForTests,
  clearMaterializedTab,
  getFirstMaterializedTab,
  getTabStoreSnapshot,
  spawnMaterializedTab,
  updateMaterializedTab,
} from './tabStore';

describe('tabStore', () => {
  beforeEach(() => {
    __resetTabStoreForTests();
  });

  it('spawns a single reaching tab', () => {
    const tab = spawnMaterializedTab({ code: 'print(1)', language: 'python', filepath: 'demo.py' }, { bornAt: 123 });
    expect(getTabStoreSnapshot().tabs).toHaveLength(1);
    expect(tab.lifecycle).toBe('reaching');
    expect(tab.bornAt).toBe(123);
    expect(getFirstMaterializedTab()?.content?.filepath).toBe('demo.py');
  });

  it('replaces the existing tab on a second spawn', () => {
    spawnMaterializedTab({ code: 'a', language: 'python', filepath: 'a.py' }, { bornAt: 1 });
    const replacement = spawnMaterializedTab({ code: 'b', language: 'python', filepath: 'b.py' }, { bornAt: 2 });
    expect(getTabStoreSnapshot().tabs).toHaveLength(1);
    expect(getFirstMaterializedTab()?.id).toBe(replacement.id);
    expect(getFirstMaterializedTab()?.content?.filepath).toBe('b.py');
  });

  it('updates the live tab in place', () => {
    const tab = spawnMaterializedTab({ code: 'a', language: 'python', filepath: 'a.py' });
    updateMaterializedTab(tab.id, { lifecycle: 'live', content: { code: 'b', language: 'python', filepath: 'b.py' } });
    expect(getFirstMaterializedTab()?.lifecycle).toBe('live');
    expect(getFirstMaterializedTab()?.content?.code).toBe('b');
  });

  it('clears the tab', () => {
    const tab = spawnMaterializedTab({ code: 'a', language: 'python', filepath: 'a.py' });
    clearMaterializedTab(tab.id);
    expect(getTabStoreSnapshot().tabs).toHaveLength(0);
  });
});
