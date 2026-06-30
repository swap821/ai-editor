import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

function sseResponse(): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(encoder.encode('event: done\ndata: {}\n\n'));
      controller.close();
    },
  });
  return { ok: true, body } as Response;
}

function jsonResponse(body: Record<string, unknown>, ok = true): Response {
  return {
    ok,
    json: async () => body,
  } as Response;
}

describe('aiosAdapter session request shape', () => {
  beforeEach(() => {
    vi.resetModules();
    window.sessionStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('initializes cookie session before a directive and omits body sessionId', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ authenticated: false }))
      .mockResolvedValueOnce(jsonResponse({ authenticated: true }))
      .mockResolvedValueOnce(jsonResponse({ authenticated: true }))
      .mockResolvedValueOnce(sseResponse());
    vi.stubGlobal('fetch', fetchMock);
    const { sendDirective } = await import('./aiosAdapter');

    const result = await sendDirective('verify the loop');

    expect(result.ok).toBe(true);
    const generate = fetchMock.mock.calls.find(([url]) =>
      String(url).endsWith('/api/generate')
    );
    expect(generate).toBeTruthy();
    const init = generate?.[1] as RequestInit;
    expect(init.credentials).toBe('include');
    const body = JSON.parse(String(init.body)) as Record<string, unknown>;
    expect(body.sessionId).toBeUndefined();
    expect(body.messages).toBeTruthy();
  });

  it('uses a generated body sessionId only when cookie setup fails', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({}, false))
      .mockResolvedValueOnce(jsonResponse({}, false))
      .mockResolvedValueOnce(sseResponse());
    vi.stubGlobal('fetch', fetchMock);
    const { sendDirective } = await import('./aiosAdapter');
    const { FALLBACK_SESSION_ID } = await import('./sessionId');

    const result = await sendDirective('verify the loop');

    expect(result.ok).toBe(true);
    const generate = fetchMock.mock.calls.find(([url]) =>
      String(url).endsWith('/api/generate')
    );
    const init = generate?.[1] as RequestInit;
    expect(init.credentials).toBe('include');
    const body = JSON.parse(String(init.body)) as Record<string, unknown>;
    expect(typeof body.sessionId).toBe('string');
    expect(body.sessionId).not.toBe(FALLBACK_SESSION_ID);
  });
});
