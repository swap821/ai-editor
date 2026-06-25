import { describe, it, expect } from 'vitest';
import { readSse, type SseFrame } from './aiosAdapter';

function streamOf(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  let i = 0;
  return new ReadableStream<Uint8Array>({
    pull(controller) {
      if (i < chunks.length) {
        controller.enqueue(encoder.encode(chunks[i]));
        i += 1;
      } else {
        controller.close();
      }
    },
  });
}

async function collect(body: ReadableStream<Uint8Array>): Promise<SseFrame[]> {
  const out: SseFrame[] = [];
  for await (const frame of readSse(body)) {
    out.push(frame);
  }
  return out;
}

describe('readSse parser', () => {
  it('parses a single event frame', async () => {
    const body = streamOf(['event: text_chunk\ndata: {"text":"hello"}\n\n']);
    const frames = await collect(body);
    expect(frames).toHaveLength(1);
    expect(frames[0]).toEqual({ event: 'text_chunk', data: { text: 'hello' } });
  });

  it('parses multiple frames in one chunk', async () => {
    const body = streamOf([
      'event: step\ndata: {"type":"tool_call","tool":"edit_file"}\n\nevent: done\ndata: {}\n\n',
    ]);
    const frames = await collect(body);
    expect(frames).toHaveLength(2);
    expect(frames[0]).toEqual({ event: 'step', data: { type: 'tool_call', tool: 'edit_file' } });
    expect(frames[1]).toEqual({ event: 'done', data: {} });
  });

  it('reassembles event/data split across chunk boundaries', async () => {
    const body = streamOf(['event: text_chunk\n', 'data: {"text":"split"}\n\n']);
    const frames = await collect(body);
    expect(frames).toHaveLength(1);
    expect(frames[0]).toEqual({ event: 'text_chunk', data: { text: 'split' } });
  });

  it('supports multi-line data joined into one JSON payload', async () => {
    const body = streamOf([
      'event: code\ndata: {"code":"line1\\nline2",\n',
      'data:"language":"python"}\n\n',
    ]);
    const frames = await collect(body);
    expect(frames).toHaveLength(1);
    expect(frames[0].event).toBe('code');
    expect(frames[0].data).toEqual({ code: 'line1\nline2', language: 'python' });
  });

  it('strips trailing carriage returns', async () => {
    const body = streamOf(['event: text_chunk\r\ndata: {"text":"crlf"}\r\n\r\n']);
    const frames = await collect(body);
    expect(frames).toHaveLength(1);
    expect(frames[0]).toEqual({ event: 'text_chunk', data: { text: 'crlf' } });
  });

  it('surfaces malformed JSON as an empty data object instead of throwing', async () => {
    const body = streamOf(['event: step\ndata: not-json\n\n']);
    const frames = await collect(body);
    expect(frames).toHaveLength(1);
    expect(frames[0].event).toBe('step');
    expect(frames[0].data).toEqual({});
  });

  it('ignores unknown field lines and empty dispatch lines', async () => {
    const body = streamOf([
      ':heartbeat\n\nevent: text_chunk\nunknown: ignored\ndata: {"text":"ok"}\n\n',
    ]);
    const frames = await collect(body);
    expect(frames).toHaveLength(1);
    expect(frames[0]).toEqual({ event: 'text_chunk', data: { text: 'ok' } });
  });
});
