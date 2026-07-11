/**
 * Adapter contract tests for the swarm opt-in flag and the `plan` SSE event
 * (B2's mandatory plan stage finding its UI consumer). Lives in workbench/
 * because superbrain/lib is lab-synced; new workbench files are product-safe.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sendDirective, setSwarmMode } from '../superbrain/lib/aiosAdapter';


function sseBody(frames: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  let i = 0;
  return new ReadableStream<Uint8Array>({
    pull(controller) {
      if (i < frames.length) {
        controller.enqueue(encoder.encode(frames[i]));
        i += 1;
      } else {
        controller.close();
      }
    },
  });
}

const PLAN_FRAME =
  'event: plan\ndata: {"goal":"probe","requires_human":true,"native":false,' +
  '"steps":[{"step_id":"1","description":"a","confidence":0.9},' +
  '{"step_id":"2","description":"b","confidence":0.1}],' +
  '"approved":[],"escalate":[{"step":{"step_id":"2"},"reason":"low","action":"REQUIRE_HUMAN_REVIEW"}],' +
  '"calibrations":[]}\n\n';
const DONE_FRAME = 'event: done\ndata: {}\n\n';

describe('adapter swarm flag + plan event', () => {
  let calls: Array<{ url: string; body: string }> = [];

  beforeEach(() => {
    calls = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
        const urlText = String(url);
        calls.push({ url: urlText, body: String(init?.body ?? '') });
        if (urlText.includes('/api/generate')) {
          return {
            ok: true,
            status: 200,
            body: sseBody([PLAN_FRAME, DONE_FRAME]),
          } as unknown as Response;
        }
        // Session bootstrap and any other side call: succeed quietly.
        return {
          ok: true,
          status: 200,
          json: async () => ({}),
          headers: new Headers(),
        } as unknown as Response;
      }),
    );
  });

  afterEach(() => {
    setSwarmMode(false);
    vi.unstubAllGlobals();
  });

  function generateBody(): Record<string, unknown> {
    const call = calls.find((c) => c.url.includes('/api/generate'));
    expect(call).toBeDefined();
    return JSON.parse(call!.body);
  }

  it('omits the swarm field by default', async () => {
    await sendDirective('plain turn');
    expect('swarm' in generateBody()).toBe(false);
  });

  it('sends swarm: true after setSwarmMode(true)', async () => {
    setSwarmMode(true);
    await sendDirective('colony turn');
    expect(generateBody().swarm).toBe(true);
  });

  it('drops the swarm field again after setSwarmMode(false) — no latch', async () => {
    // The disable direction is the safety-relevant one: a latch bug (e.g. a
    // bad lab-sync mirror of the singleton) would trap the operator in swarm
    // mode for the session while both one-way tests stay green.
    setSwarmMode(true);
    setSwarmMode(false);
    await sendDirective('solo turn again');
    expect('swarm' in generateBody()).toBe(false);
  });

});
