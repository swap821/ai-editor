import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { __resetAiosAdapterForTests, sendVoiceTurn } from '../superbrain/lib/aiosAdapter';
import { subscribeCognition } from '../superbrain/lib/cognitionBus';

/* P1-2 superbrain slice — the spoken conversational turn the HUD mic drives.
   sendVoiceTurn streams the CONVERSATIONAL /api/v1/chat (not the agentic forge)
   and narrates the turn with EXISTING cognition events so the brain reacts and
   the conversation organs refresh, with no new scene wiring. Pinned here:
   reply assembly + live progress, the conversational endpoint + shared session,
   bus narration (directive on send, synthesis on done), and honest failure. */

function sseResponse(frames) {
  const text = frames
    .map(([event, data]) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`)
    .join('');
  const bytes = new TextEncoder().encode(text);
  return {
    ok: true,
    status: 200,
    body: new ReadableStream({
      start(controller) {
        controller.enqueue(bytes);
        controller.close();
      },
    }),
  };
}

describe('sendVoiceTurn (superbrain voice -> /api/v1/chat)', () => {
  beforeEach(() => {
    __resetAiosAdapterForTests();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('streams the reply, reports progress, and narrates start + done on the bus', async () => {
    const events = [];
    const unsub = subscribeCognition((e) => events.push(e));
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        sseResponse([
          ['route', { provider: 'ollama', model: 'qwen2.5:7b', privacy: 'local' }],
          ['text_chunk', { text: 'Arre ' }],
          ['text_chunk', { text: 'haan!' }],
          ['done', {}],
        ]),
      ),
    );
    const chunks = [];
    const reply = await sendVoiceTurn('kaise ho?', { onChunk: (r) => chunks.push(r) });
    expect(reply).toBe('Arre haan!');
    expect(chunks).toEqual(['Arre ', 'Arre haan!']);
    const types = events.map((e) => e.type);
    expect(types[0]).toBe('directive'); // the spoken turn is narrated on send
    expect(types).toContain('synthesis'); // completion -> conversation organs refresh
    unsub();
  });

  it('POSTs the transcript + shared session to the conversational endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      sseResponse([['text_chunk', { text: 'ok' }], ['done', {}]]),
    );
    vi.stubGlobal('fetch', fetchMock);
    await sendVoiceTurn('build karo');
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain('/api/v1/chat'); // conversation, not /api/generate
    const body = JSON.parse(init.body);
    expect(body.transcript).toBe('build karo');
    expect(typeof body.sessionId).toBe('string'); // the shared aios_session_id
  });

  it('returns empty without calling the backend for a blank transcript', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    const reply = await sendVoiceTurn('   ');
    expect(reply).toBe('');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('throws on an error frame instead of fabricating a reply', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(sseResponse([['error', { text: 'voice mind unavailable' }]])),
    );
    await expect(sendVoiceTurn('hello')).rejects.toThrow('voice mind unavailable');
  });
});
