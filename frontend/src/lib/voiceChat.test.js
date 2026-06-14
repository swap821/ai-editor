import { afterEach, describe, expect, it, vi } from 'vitest';
import { streamChatReply } from './voiceChat';

/* P1-2 voice loop — the reusable conversational streamer the voice mic drives.
   These pin: the assembled reply, live onChunk captioning, that it POSTs the
   transcript + shared sessionId to the conversational /api/v1/chat (NOT the
   agentic forge), and honest error surfacing (no fabricated reply). */

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

afterEach(() => {
  vi.restoreAllMocks();
});

it('assembles the streamed reply and reports live progress', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      sseResponse([
        ['route', { provider: 'ollama', model: 'qwen2.5:7b', privacy: 'local' }],
        ['text_chunk', { text: 'Arre ' }],
        ['text_chunk', { text: 'haan, ' }],
        ['text_chunk', { text: 'ho jayega!' }],
        ['done', {}],
      ]),
    ),
  );
  const chunks = [];
  const reply = await streamChatReply('kaise ho?', 'sess-1', {
    onChunk: (r) => chunks.push(r),
  });
  expect(reply).toBe('Arre haan, ho jayega!');
  // onChunk reports the cumulative reply as it grows.
  expect(chunks).toEqual(['Arre ', 'Arre haan, ', 'Arre haan, ho jayega!']);
});

it('POSTs the transcript + shared sessionId to the conversational endpoint', async () => {
  const fetchMock = vi.fn().mockResolvedValue(sseResponse([['text_chunk', { text: 'ok' }], ['done', {}]]));
  vi.stubGlobal('fetch', fetchMock);
  await streamChatReply('build karo', 'shared-session-id');
  const [url, init] = fetchMock.mock.calls[0];
  expect(String(url)).toContain('/api/v1/chat'); // the conversation, not /api/generate
  const body = JSON.parse(init.body);
  expect(body).toMatchObject({ transcript: 'build karo', sessionId: 'shared-session-id' });
});

it('throws on an error frame instead of fabricating a reply', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(sseResponse([['error', { text: 'No transcript provided.' }]])),
  );
  await expect(streamChatReply('   ', 'sess-1')).rejects.toThrow('No transcript provided.');
});

it('throws on a non-ok response', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 429, body: null }));
  await expect(streamChatReply('hi', 'sess-1')).rejects.toThrow('429');
});
