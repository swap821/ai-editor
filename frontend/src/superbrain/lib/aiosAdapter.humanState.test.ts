import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

function sseResponseFromFrames(frames: string): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(encoder.encode(frames));
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

const SESSION_INIT_RESPONSES = [
  jsonResponse({ authenticated: false }),
  jsonResponse({ authenticated: true }),
  jsonResponse({ authenticated: true }),
];

describe('aiosAdapter organ 30: human-state frame + correction', () => {
  beforeEach(() => {
    vi.resetModules();
    window.sessionStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('invokes onHumanState with the real frame data before the reply completes', async () => {
    const frames =
      'event: human_state\n' +
      'data: {"state":"frustrated","confidence":0.6,"visible_reason":"repeated-complaint markers","turn_id":"turn-abc"}\n\n' +
      'event: text_chunk\ndata: {"text":"ok"}\n\n' +
      'event: done\ndata: {}\n\n';
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(SESSION_INIT_RESPONSES[0])
      .mockResolvedValueOnce(SESSION_INIT_RESPONSES[1])
      .mockResolvedValueOnce(SESSION_INIT_RESPONSES[2])
      .mockResolvedValueOnce(sseResponseFromFrames(frames));
    vi.stubGlobal('fetch', fetchMock);
    const { sendVoiceTurn } = await import('./aiosAdapter');

    const seen: unknown[] = [];
    await sendVoiceTurn('ugh still broken', { onHumanState: (h) => seen.push(h) });

    expect(seen).toEqual([
      {
        turnId: 'turn-abc',
        state: 'frustrated',
        confidence: 0.6,
        visibleReason: 'repeated-complaint markers',
      },
    ]);
  });

  it('never calls onHumanState when the frame is malformed (missing state/turn_id)', async () => {
    const frames =
      'event: human_state\ndata: {"confidence":0.6}\n\n' + 'event: done\ndata: {}\n\n';
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(SESSION_INIT_RESPONSES[0])
      .mockResolvedValueOnce(SESSION_INIT_RESPONSES[1])
      .mockResolvedValueOnce(SESSION_INIT_RESPONSES[2])
      .mockResolvedValueOnce(sseResponseFromFrames(frames));
    vi.stubGlobal('fetch', fetchMock);
    const { sendVoiceTurn } = await import('./aiosAdapter');

    const seen: unknown[] = [];
    await sendVoiceTurn('hello', { onHumanState: (h) => seen.push(h) });

    expect(seen).toEqual([]);
  });

  it('correctHumanState posts the real turn/state/session and resolves true on success', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(SESSION_INIT_RESPONSES[0])
      .mockResolvedValueOnce(SESSION_INIT_RESPONSES[1])
      .mockResolvedValueOnce(SESSION_INIT_RESPONSES[2])
      .mockResolvedValueOnce(jsonResponse({ recorded: true }));
    vi.stubGlobal('fetch', fetchMock);
    const { correctHumanState } = await import('./aiosAdapter');

    const result = await correctHumanState('turn-abc', 'neutral');

    expect(result).toBe(true);
    const call = fetchMock.mock.calls.find(([url]) =>
      String(url).endsWith('/api/v1/chat/human-state/correct'),
    );
    expect(call).toBeTruthy();
    const init = call?.[1] as RequestInit;
    const body = JSON.parse(String(init.body)) as Record<string, unknown>;
    expect(body.turnId).toBe('turn-abc');
    expect(body.correctedState).toBe('neutral');
  });

  it('correctHumanState resolves false (never throws) on a transport failure', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(SESSION_INIT_RESPONSES[0])
      .mockResolvedValueOnce(SESSION_INIT_RESPONSES[1])
      .mockResolvedValueOnce(SESSION_INIT_RESPONSES[2])
      .mockRejectedValueOnce(new Error('network down'));
    vi.stubGlobal('fetch', fetchMock);
    const { correctHumanState } = await import('./aiosAdapter');

    await expect(correctHumanState('turn-abc', 'neutral')).resolves.toBe(false);
  });

  it('correctHumanState resolves false on a non-ok server response', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(SESSION_INIT_RESPONSES[0])
      .mockResolvedValueOnce(SESSION_INIT_RESPONSES[1])
      .mockResolvedValueOnce(SESSION_INIT_RESPONSES[2])
      .mockResolvedValueOnce(jsonResponse({}, false));
    vi.stubGlobal('fetch', fetchMock);
    const { correctHumanState } = await import('./aiosAdapter');

    await expect(correctHumanState('turn-abc', 'neutral')).resolves.toBe(false);
  });

  it('getHumanStateAccuracy maps a real backend report', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(
      jsonResponse({
        total_corrected: 3,
        agreements: 2,
        accuracy: 0.6666666666666666,
        by_state: { frustrated: { total: 2, agreements: 1 } },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);
    const { getHumanStateAccuracy } = await import('./aiosAdapter');

    const report = await getHumanStateAccuracy();

    expect(report).toEqual({
      totalCorrected: 3,
      agreements: 2,
      accuracy: 0.6666666666666666,
      byState: { frustrated: { total: 2, agreements: 1 } },
    });
  });

  it('getHumanStateAccuracy resolves null (never throws) on a transport failure', async () => {
    const fetchMock = vi.fn().mockRejectedValueOnce(new Error('network down'));
    vi.stubGlobal('fetch', fetchMock);
    const { getHumanStateAccuracy } = await import('./aiosAdapter');

    await expect(getHumanStateAccuracy()).resolves.toBeNull();
  });
});
