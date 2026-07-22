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

function sseResponseFromFrames(frames: string, close = true): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(encoder.encode(frames));
      if (close) controller.close();
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

  it('reports ok:false when the SSE connection drops before a terminal frame -- even with partial text already streamed', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ authenticated: false }))
      .mockResolvedValueOnce(jsonResponse({ authenticated: true }))
      .mockResolvedValueOnce(jsonResponse({ authenticated: true }))
      .mockResolvedValueOnce(
        sseResponseFromFrames('event: text_chunk\ndata: {"text":"partial reply, then "}\n\n'),
      );
    vi.stubGlobal('fetch', fetchMock);
    const { sendDirective } = await import('./aiosAdapter');

    const result = await sendDirective('verify the loop');

    expect(result.ok).toBe(false);
    expect(result.paused).toBe(false);
    expect(result.answer).toBe('partial reply, then ');
  });

  it('reports ok:true, paused:true when the turn legitimately pauses for approval, even with no done frame', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ authenticated: false }))
      .mockResolvedValueOnce(jsonResponse({ authenticated: true }))
      .mockResolvedValueOnce(jsonResponse({ authenticated: true }))
      .mockResolvedValueOnce(
        sseResponseFromFrames(
          'event: human_required\ndata: {"text":"authorize this write","token":"tok-1"}\n\n',
        ),
      );
    vi.stubGlobal('fetch', fetchMock);
    const { sendDirective } = await import('./aiosAdapter');

    const result = await sendDirective('write a file');

    expect(result.ok).toBe(true);
    expect(result.paused).toBe(true);
  });

  it('reports ok:false when the backend sends an explicit error frame', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ authenticated: false }))
      .mockResolvedValueOnce(jsonResponse({ authenticated: true }))
      .mockResolvedValueOnce(jsonResponse({ authenticated: true }))
      .mockResolvedValueOnce(
        sseResponseFromFrames('event: error\ndata: {"text":"provider unavailable"}\n\n'),
      );
    vi.stubGlobal('fetch', fetchMock);
    const { sendDirective } = await import('./aiosAdapter');

    const result = await sendDirective('verify the loop');

    expect(result.ok).toBe(false);
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

  it('includes an explicit modelId in the chat POST body when requested', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ authenticated: false }))
      .mockResolvedValueOnce(jsonResponse({ authenticated: true }))
      .mockResolvedValueOnce(jsonResponse({ authenticated: true }))
      .mockResolvedValueOnce(sseResponse());
    vi.stubGlobal('fetch', fetchMock);
    const { sendVoiceTurn } = await import('./aiosAdapter');

    await sendVoiceTurn('hello there', { modelId: 'gemini.gemini-2.5-flash' });

    const chat = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/api/v1/chat'));
    expect(chat).toBeTruthy();
    const init = chat?.[1] as RequestInit;
    const body = JSON.parse(String(init.body)) as Record<string, unknown>;
    expect(body.modelId).toBe('gemini.gemini-2.5-flash');
  });

  it('omits modelId from the chat POST body when not requested', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ authenticated: false }))
      .mockResolvedValueOnce(jsonResponse({ authenticated: true }))
      .mockResolvedValueOnce(jsonResponse({ authenticated: true }))
      .mockResolvedValueOnce(sseResponse());
    vi.stubGlobal('fetch', fetchMock);
    const { sendVoiceTurn } = await import('./aiosAdapter');

    await sendVoiceTurn('hello there');

    const chat = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/api/v1/chat'));
    expect(chat).toBeTruthy();
    const init = chat?.[1] as RequestInit;
    const body = JSON.parse(String(init.body)) as Record<string, unknown>;
    expect(body.modelId).toBeUndefined();
  });
});
