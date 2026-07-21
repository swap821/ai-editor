import { beforeEach, describe, expect, it } from 'vitest';
import {
  showContentSurface,
  updateMaterializedTab,
  getTabStoreSnapshot,
  __resetTabStoreForTests,
} from './tabStore';

describe('tabStore — streaming (writing) content state', () => {
  beforeEach(() => {
    __resetTabStoreForTests();
  });

  it('carries a streaming flag on a content slab and clears it on fill-by-id', () => {
    // A "writing" skeleton: empty code, streaming = true.
    const skeleton = showContentSurface({ code: '', language: 'text', filepath: 'hello.py', streaming: true });
    const created = getTabStoreSnapshot().tabs.find((t) => t.id === skeleton.id);
    expect(created?.content?.streaming).toBe(true);
    expect(created?.content?.code).toBe('');

    // The being finishes writing -> fill the SAME slab by id, streaming off.
    updateMaterializedTab(skeleton.id, {
      content: { code: 'print("hi")', language: 'python', filepath: 'hello.py', streaming: false },
    });
    const filled = getTabStoreSnapshot().tabs.find((t) => t.id === skeleton.id);
    expect(filled?.content?.streaming).toBe(false);
    expect(filled?.content?.code).toBe('print("hi")');
    // still one slab (filled in place, not duplicated)
    expect(getTabStoreSnapshot().tabs.filter((t) => t.kind === 'content').length).toBe(1);
  });
});
