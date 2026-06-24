import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  FALLBACK_SESSION_ID,
  getSessionId,
  SESSION_STORAGE_KEY,
} from './sessionId';

describe('getSessionId', () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('returns an existing persisted id', () => {
    window.localStorage.setItem(SESSION_STORAGE_KEY, 'existing-session-123');
    expect(getSessionId()).toBe('existing-session-123');
  });

  it('mints and persists a new id when none exists', () => {
    const minted = 'minted-uuid-abc';
    vi.stubGlobal('crypto', {
      ...window.crypto,
      randomUUID: () => minted,
    });

    expect(getSessionId()).toBe(minted);
    expect(window.localStorage.getItem(SESSION_STORAGE_KEY)).toBe(minted);
  });

  it('returns the same id on repeated calls', () => {
    const first = getSessionId();
    const second = getSessionId();
    expect(second).toBe(first);
    expect(window.localStorage.getItem(SESSION_STORAGE_KEY)).toBe(first);
  });

  it('falls back to the stable fallback id when storage is blocked', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('storage blocked');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('storage blocked');
    });

    expect(getSessionId()).toBe(FALLBACK_SESSION_ID);
  });
});
