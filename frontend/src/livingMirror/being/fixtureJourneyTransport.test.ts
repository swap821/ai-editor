import { afterEach, expect, it, vi } from 'vitest';
import { createFixtureJourneyTransport } from './fixtureJourneyTransport';
import { __resetAiosAdapterForTests, approvePendingApproval, getPendingApproval, rejectPendingApproval, sendDirective } from '../../superbrain/lib/aiosAdapter';
import { installFixtureJourney } from './installFixtureJourney';
import { startMirrorClient, stopMirrorClient } from '../../superbrain/lib/aiosMirror';
import { useMirrorStore } from '../../superbrain/lib/mirrorStore';

const fixtures: ReturnType<typeof createFixtureJourneyTransport>[] = [];
function fixture() {
  const assetFetch = vi.fn<typeof fetch>().mockResolvedValue(new Response('asset'));
  const transport = createFixtureJourneyTransport({ assetFetch, origin: 'http://127.0.0.1:5213' });
  fixtures.push(transport);
  return { transport, assetFetch };
}
afterEach(() => { stopMirrorClient(); fixtures.forEach((f) => f.dispose()); fixtures.length = 0; __resetAiosAdapterForTests(); useMirrorStore.setState(useMirrorStore.getInitialState(), true); vi.unstubAllGlobals(); });
async function drain(transport: ReturnType<typeof createFixtureJourneyTransport>, finished: () => boolean) {
  for (let count = 0; count < 30 && !finished(); count++) {
    await new Promise((resolve) => setTimeout(resolve, 0));
    if (transport.getSnapshot().pending) transport.advance();
  }
  expect(finished()).toBe(true);
}
it('delegates only same-origin static assets, never backend reads, writes, or remote assets', async () => {
  const { transport, assetFetch } = fixture();
  expect((await transport.fetch('/fonts/Inter-Regular.woff2')).ok).toBe(true);
  for (const [url, method] of [
    ['http://localhost:8000/api/v1/auth/enroll', 'POST'], ['/api/v1/unknown', 'GET'],
    ['https://example.com/fonts/Inter-Regular.woff2', 'GET'], ['/fonts/Inter-Regular.woff2', 'POST'],
    ['/fonts/../api/v1/stop.woff2', 'GET'], ['/fonts/Inter-Regular.woff2?secret=1', 'GET'],
  ]) expect((await transport.fetch(url, { method })).ok).toBe(false);
  expect(assetFetch).toHaveBeenCalledTimes(1);
});
it('holds real adapter output for permission and lets only the matching local replay complete', async () => {
  const { transport, assetFetch } = fixture(); vi.stubGlobal('fetch', transport.fetch);
  __resetAiosAdapterForTests();
  let finished = false;
  const original = sendDirective('Make the example').finally(() => { finished = true; });
  await drain(transport, () => finished);
  expect(await original).toMatchObject({ ok: true, paused: true, emittedCode: { filepath: 'fixture/hello.py' } });
  const token = getPendingApproval()!.token;
  expect(token).toMatch(/^fixture-/);
  expect(transport.getSnapshot().waitingForDecision).toBe(true);
  expect((await transport.fetch('/api/generate', { method: 'POST', body: JSON.stringify({ approvalTokens: ['foreign-token'] }) })).status).toBe(409);
  finished = false;
  const replay = approvePendingApproval({ expectedToken: token }).finally(() => { finished = true; });
  await drain(transport, () => finished);
  expect(await replay).toMatchObject({ ok: true, paused: false, emittedCode: { code: 'print("Hello from the fixture")\n' } });
  expect(getPendingApproval()).toBeNull();
  expect(transport.getSnapshot()).toMatchObject({ pending: false, waitingForDecision: false });
  expect(assetFetch).not.toHaveBeenCalled();
});
it('denies locally and refuses token reuse without sending an operation', async () => {
  const { transport, assetFetch } = fixture(); vi.stubGlobal('fetch', transport.fetch); __resetAiosAdapterForTests();
  let finished = false;
  const turn = sendDirective('Example').finally(() => { finished = true; });
  await drain(transport, () => finished); await turn;
  const token = getPendingApproval()!.token;
  expect(await rejectPendingApproval(token)).toEqual({ confirmed: true });
  expect((await transport.fetch('/api/generate', { method: 'POST', body: JSON.stringify({ approvalTokens: [token] }) })).status).toBe(409);
  expect(transport.getSnapshot().label).toMatch(/declined/i);
  expect(assetFetch).not.toHaveBeenCalled();
});
it('stops queued fixture frames on abort and does not pretend a partial stream finished', async () => {
  const { transport } = fixture(); vi.stubGlobal('fetch', transport.fetch); __resetAiosAdapterForTests();
  const controller = new AbortController();
  const turn = sendDirective('Example', controller.signal);
  await new Promise((resolve) => setTimeout(resolve, 0));
  controller.abort(); transport.advance();
  await expect(turn).rejects.toMatchObject({ name: 'AbortError' });
  expect(transport.getSnapshot()).toMatchObject({ pending: false, waitingForDecision: false });
  expect(getPendingApproval()).toBeNull();
});

it('fences optional socket, XHR, beacon and microphone routes before importing the app', async () => {
  const native = vi.fn(function () {});
  const host = {
    fetch: vi.fn<typeof fetch>(), EventSource: native, WebSocket: native, XMLHttpRequest: native,
    SpeechRecognition: native, webkitSpeechRecognition: native,
    location: { origin: 'http://127.0.0.1:5213' },
    navigator: { sendBeacon: native, mediaDevices: { getUserMedia: native } },
    addEventListener: vi.fn(),
  } as unknown as Window & typeof globalThis;
  const installed = installFixtureJourney(host); fixtures.push(installed);
  expect(() => new host.WebSocket('ws://localhost:8000/api/v1/stream/ws')).toThrow(/fixture/i);
  const xhr = new host.XMLHttpRequest();
  expect(() => xhr.open('POST', '/api/v1/stop')).toThrow(/fixture/i);
  expect(host.navigator.sendBeacon('/api/v1/stop', 'body')).toBe(false);
  await expect(host.navigator.mediaDevices.getUserMedia({ audio: true })).rejects.toThrow(/fixture/i);
  const speech = host as unknown as { SpeechRecognition: new () => object };
  expect(speech.SpeechRecognition).toBeUndefined();
  expect(native).not.toHaveBeenCalled();
});

it('keeps the original cancellation owner through a held permission, so a new turn can start', async () => {
  const { transport } = fixture(); vi.stubGlobal('fetch', transport.fetch); __resetAiosAdapterForTests();
  const controller = new AbortController(); let finished = false;
  const turn = sendDirective('Original', controller.signal).finally(() => { finished = true; });
  await drain(transport, () => finished); await turn;
  expect(transport.getSnapshot().waitingForDecision).toBe(true);
  controller.abort();
  expect(transport.getSnapshot().waitingForDecision).toBe(false);
  finished = false;
  const next = sendDirective('New example').finally(() => { finished = true; });
  await drain(transport, () => finished);
  expect(await next).toMatchObject({ ok: true, paused: true });
  expect(getPendingApproval()?.prompt).toBe('New example');
});

it('permits the local font loader without restoring native XHR or forwarding a redirect', async () => {
  const assetFetch = vi.fn<typeof fetch>().mockResolvedValue(new Response(new Uint8Array([0, 1, 0, 0])));
  const host = { fetch: assetFetch, EventSource: vi.fn(), WebSocket: vi.fn(), XMLHttpRequest: vi.fn(),
    location: { origin: 'http://127.0.0.1:5213' }, navigator: { sendBeacon: vi.fn() }, addEventListener: vi.fn(),
  } as unknown as Window & typeof globalThis;
  const installed = installFixtureJourney(host); fixtures.push(installed);
  const xhr = new host.XMLHttpRequest();
  xhr.open('GET', '/fonts/fixture-outfit.ttf', true); xhr.responseType = 'arraybuffer';
  const loaded = new Promise<void>((resolve, reject) => { xhr.onload = () => resolve(); xhr.onerror = () => reject(new Error('Font load failed')); });
  xhr.send(); await loaded;
  expect(xhr.status).toBe(200);
  expect(new Uint8Array(xhr.response)).toEqual(new Uint8Array([0, 1, 0, 0]));
  expect(assetFetch).toHaveBeenCalledWith('http://127.0.0.1:5213/fonts/fixture-outfit.ttf', expect.objectContaining({ credentials: 'omit', redirect: 'error' }));
});

it.each(['unverified', 'verified', 'failed'] as const)('admits %s through the real mirror cursor/barrier and adapter, not a presentation override', async (outcome) => {
  const { transport } = fixture();
  vi.stubGlobal('fetch', transport.fetch); vi.stubGlobal('EventSource', transport.EventSource);
  __resetAiosAdapterForTests(); useMirrorStore.setState(useMirrorStore.getInitialState(), true);
  await startMirrorClient(); await new Promise((resolve) => setTimeout(resolve, 0));
  expect(useMirrorStore.getState().projection).toBe('fresh');
  transport.setOutcome(outcome);
  let finished = false;
  const turn = sendDirective('Example').finally(() => { finished = true; });
  await drain(transport, () => finished); await turn;
  transport.setOutcome('failed'); // Cannot change the outcome of the held decision.
  expect(transport.getSnapshot().outcome).toBe(outcome);
  finished = false;
  const replay = approvePendingApproval().finally(() => { finished = true; });
  await drain(transport, () => finished);
  expect((await replay).ok).toBe(outcome !== 'failed');
  const mirror = useMirrorStore.getState();
  expect(mirror.projection).toBe('fresh');
  expect(mirror.snapshotRequired).toBe(false);
  expect(mirror.lastTurnStartedEventId).toBe(2);
  if (outcome === 'unverified') expect(mirror.lastVerification).toBeNull();
  else expect(mirror.lastVerification?.payload).toMatchObject({ verdict: outcome === 'verified' ? 'pass' : 'fail', target: 'fixture/hello.py' });
});
