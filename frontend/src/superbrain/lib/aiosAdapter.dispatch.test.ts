/** B1 "listen" — the body hears the typed event spine.
 *
 * The backend stamps additive `phase` / `seq` fields on every SSE frame and
 * emits `confidence.gated` when the mind pauses unsure. Before B1 the adapter
 * dropped both on the floor. These tests drive a full streamed turn through a
 * stubbed fetch and assert the cognition bus now carries the spine.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sendDirective, __resetAiosAdapterForTests } from './aiosAdapter';
import { subscribeCognition, type CognitionEvent } from './cognitionBus';

function sseResponse(frames: string[]): Response {
  const encoder = new TextEncoder();
  let i = 0;
  const stream = new ReadableStream<Uint8Array>({
    pull(controller) {
      if (i < frames.length) {
        controller.enqueue(encoder.encode(frames[i]));
        i += 1;
      } else {
        controller.close();
      }
    },
  });
  return new Response(stream, {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  });
}

function stubBackend(frames: string[]): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: RequestInfo | URL) => {
      if (String(url).includes('/api/generate')) return sseResponse(frames);
      return new Response('{}', {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }),
  );
}

describe('B1 — typed event spine reaches the cognition bus', () => {
  const seen: CognitionEvent[] = [];
  let unsub: () => void;

  beforeEach(() => {
    __resetAiosAdapterForTests();
    seen.length = 0;
    unsub = subscribeCognition((event) => {
      seen.push(event);
    });
  });

  afterEach(() => {
    unsub();
    vi.unstubAllGlobals();
  });

  it('forwards phase and seq from spine-carrying frames', async () => {
    stubBackend([
      'event: route\ndata: {"provider":"ollama","model":"qwen","privacy":"local","phase":"chemotaxis","seq":1}\n\n',
      'event: done\ndata: {"phase":"narrative","seq":9}\n\n',
    ]);
    const result = await sendDirective('map the spine');
    expect(result.ok).toBe(true);

    const route = seen.find((event) => event.type === 'route');
    expect(route?.phase).toBe('chemotaxis');
    expect(route?.seq).toBe(1);

    const synthesis = seen.find((event) => event.type === 'synthesis');
    expect(synthesis?.phase).toBe('narrative');
    expect(synthesis?.seq).toBe(9);
  });

  it('hears confidence.gated as a hesitation event carrying the emotion payload', async () => {
    stubBackend([
      'event: confidence.gated\ndata: {"confidence":0.41,"threshold":0.72,"question":"What should I clarify?","phase":"emotion","seq":2}\n\n',
      'event: text_chunk\ndata: {"text":"What should I clarify?"}\n\n',
      'event: done\ndata: {"phase":"narrative","seq":3}\n\n',
    ]);
    const result = await sendDirective('do something vague');
    expect(result.ok).toBe(true);

    const hesitation = seen.find((event) => event.type === 'hesitation');
    expect(hesitation).toBeDefined();
    expect(hesitation?.phase).toBe('emotion');
    expect(hesitation?.data?.confidence).toBe(0.41);
    expect(hesitation?.data?.threshold).toBe(0.72);
    expect(hesitation?.detail).toContain('What should I clarify?');
  });

  it('carries the alignment confidence value for the weather systems', async () => {
    stubBackend([
      'event: alignment\ndata: {"intent":"execute","confidence":0.92,"phase":"chemotaxis","seq":1}\n\n',
      'event: done\ndata: {}\n\n',
    ]);
    await sendDirective('confident work');

    const dispatch = seen.find((event) => event.type === 'agent-dispatch');
    expect(dispatch?.data?.confidence).toBe(0.92);
    expect(dispatch?.phase).toBe('chemotaxis');
  });

  it('announces curriculum mastery as SKILL MASTERED for the lattice (B5)', async () => {
    stubBackend([
      'event: skill.mastered\ndata: {"skill":"string-ops","level":1,"source":"curriculum","phase":"narrative","seq":7}\n\n',
      'event: done\ndata: {}\n\n',
    ]);
    await sendDirective('grow');

    const mastery = seen.find(
      (event) => event.type === 'knowledge-acquired' && /SKILL MASTERED/.test(event.label ?? ''),
    );
    expect(mastery).toBeDefined();
    expect(mastery?.label).toBe('SKILL MASTERED — STRING-OPS L1');
    expect(mastery?.phase).toBe('narrative');
  });

  it('stays backward compatible: frames without spine fields publish phase-free', async () => {
    stubBackend([
      'event: route\ndata: {"provider":"ollama","model":"qwen","privacy":"local"}\n\n',
      'event: done\ndata: {}\n\n',
    ]);
    await sendDirective('old backend');

    const route = seen.find((event) => event.type === 'route');
    expect(route).toBeDefined();
    expect(route?.phase).toBeUndefined();
    expect(route?.seq).toBeUndefined();
  });
});
