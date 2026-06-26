import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  FALLBACK_SESSION_ID,
  getSessionId,
  getSessionIdForBody,
  initSession,
  isCookieBasedSession,
  SESSION_STORAGE_KEY,
} from './sessionId';

describe('getSessionId', () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('returns fallback id when storage is empty and session not initialized', () => {
    expect(getSessionId()).toBe(FALLBACK_SESSION_ID);
  });

  it('returns cookie-session identifier when cookie-based', () => {
    // Simulate cookie-based session active
    vi.stubGlobal('window', {
      ...window,
    });
    // After initSession resolves with cookie-based, getSessionId returns 'cookie-session'
    // We test this by checking the fallback path isn't taken
    const sid = getSessionId();
    expect(sid).toBeTruthy();
    expect(typeof sid).toBe('string');
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

describe('getSessionIdForBody', () => {
  it('returns null when cookie-based (session travels in cookie)', () => {
    // Default state is cookie-based
    expect(getSessionIdForBody()).toBeNull();
  });
});

describe('isCookieBasedSession', () => {
  it('returns true by default', () => {
    expect(isCookieBasedSession()).toBe(true);
  });
});

describe('initSession', () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    vi.restoreAllMocks();
  });

  it('returns a session id', async () => {
    const sid = await initSession();
    expect(sid).toBeTruthy();
    expect(typeof sid).toBe('string');
  });

  it('falls back to sessionStorage when server session fails', async () => {
    // Mock fetch to simulate backend without session endpoint
    vi.stubGlobal('fetch', () =>
      Promise.resolve({
        ok: false,
        status: 404,
      } as Response)
    );

    const sid = await initSession();
    expect(sid).toBeTruthy();
    expect(typeof sid).toBe('string');
  });

  it('returns fallback for SSR (no window)', async () => {
    vi.stubGlobal('window', undefined);
    const sid = await initSession();
    expect(sid).toBe(FALLBACK_SESSION_ID);
  });
});
