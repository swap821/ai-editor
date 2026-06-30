import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  __resetSessionForTests,
  ensureSession,
  FALLBACK_SESSION_ID,
  getSessionId,
  getSessionIdForBody,
  initSession,
  isCookieBasedSession,
  SESSION_STORAGE_KEY,
} from './sessionId';

describe('getSessionId', () => {
  beforeEach(() => {
    __resetSessionForTests();
    window.sessionStorage.clear();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('returns fallback id when storage is empty and session not initialized', () => {
    expect(getSessionId()).toBe(FALLBACK_SESSION_ID);
  });

  it('returns a stable client identifier while cookie state is unchecked', () => {
    const sid = getSessionId();
    expect(sid).toBe(FALLBACK_SESSION_ID);
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
  beforeEach(() => {
    __resetSessionForTests();
    window.sessionStorage.clear();
    vi.restoreAllMocks();
  });

  it('returns null when cookie-based (session travels in cookie)', () => {
    // Default state is cookie-based
    expect(getSessionIdForBody()).toBeNull();
  });
});

describe('isCookieBasedSession', () => {
  beforeEach(() => {
    __resetSessionForTests();
  });

  it('returns true by default', () => {
    expect(isCookieBasedSession()).toBe(true);
  });
});

describe('initSession', () => {
  beforeEach(() => {
    __resetSessionForTests();
    window.sessionStorage.clear();
    vi.restoreAllMocks();
  });

  it('returns a session id', async () => {
    const sid = await initSession();
    expect(sid).toBeTruthy();
    expect(typeof sid).toBe('string');
  });

  it('keeps cookie mode only after the created cookie verifies', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ authenticated: false }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ authenticated: true }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ authenticated: true }),
      } as Response);
    vi.stubGlobal('fetch', fetchMock);

    const session = await ensureSession();

    expect(session.cookieBased).toBe(true);
    expect(session.bodySessionId).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock.mock.calls.every(([, init]) => init?.credentials === 'include')).toBe(true);
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
    expect(isCookieBasedSession()).toBe(false);
    expect(getSessionIdForBody()).toBe(sid);
  });

  it('returns fallback for SSR (no window)', async () => {
    vi.stubGlobal('window', undefined);
    const sid = await initSession();
    expect(sid).toBe(FALLBACK_SESSION_ID);
  });
});
