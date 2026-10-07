/** Development wire fixture. No backend operation or permission is performed. */
export type FixtureOutcome = 'unverified' | 'verified' | 'failed';
export interface FixtureJourneyState { pending: boolean; waitingForDecision: boolean; outcome: FixtureOutcome; label: string }
const FILEPATH = 'fixture/hello.py';
const FINAL_CODE = 'print("Hello from the fixture")\n';
const json = (data: object, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });
type WireFrame = { eventType: string; payload: Record<string, unknown>; id: number };
export function isFixtureRenderAsset(url: URL, origin: string, method: string) {
  return method === 'GET' && url.origin === origin && !url.search && !url.username && !url.password
    && /^\/(?:fonts\/[^/%]+\.(?:woff2?|ttf)|models\/brain\.glb|textures\/brain\/(?:diffuse|normal)\.png)$/.test(url.pathname);
}

export function createFixtureJourneyTransport(options: { assetFetch: typeof fetch; origin: string }) {
  let state: FixtureJourneyState = { pending: false, waitingForDecision: false, outcome: 'unverified', label: 'Type an example request in the real composer.' };
  const listeners = new Set<() => void>();
  const sources = new Set<FixtureEventSource>();
  const history: WireFrame[] = [];
  const queued: Array<{ label: string; run: () => void }> = [];
  let cursor = 0;
  let disposed = false;
  let runId = 0;
  let held: { token: string; prompt: string; outcome: FixtureOutcome } | null = null;
  let releaseHeldCancellation: (() => void) | null = null;
  let stopStream: (() => void) | null = null;
  const update = (patch: Partial<FixtureJourneyState>) => { state = { ...state, ...patch }; listeners.forEach((listener) => listener()); };
  const emit = (eventType: string, payload: Record<string, unknown> = {}) => {
    const frame = { eventType, payload: { ...payload, occurredAt: new Date().toISOString() }, id: ++cursor };
    history.push(frame); if (history.length > 256) history.shift();
    sources.forEach((source) => source.frame(frame));
  };
  const enqueue = (label: string, run: () => void) => { queued.push({ label, run }); };
  const pending = () => update({ pending: queued.length > 0, label: queued[0]?.label ?? state.label });
  const releaseHeld = () => { releaseHeldCancellation?.(); releaseHeldCancellation = null; };
  const abandon = (label: string) => { queued.length = 0; releaseHeld(); held = null; update({ pending: false, waitingForDecision: false, label }); emit('turn.failed', { reason: label }); };

  class FixtureEventSource extends EventTarget {
    readonly CONNECTING = 0; readonly OPEN = 1; readonly CLOSED = 2;
    readonly withCredentials = false;
    readyState = 0;
    onopen: ((event: Event) => void) | null = null;
    onerror: ((event: Event) => void) | null = null;
    onmessage: ((event: MessageEvent<string>) => void) | null = null;
    readonly url: string;
    constructor(raw: string | URL) {
      super();
      this.url = String(raw);
      const url = new URL(this.url, options.origin);
      if (disposed || url.pathname !== '/api/v1/mirror/stream') throw new DOMException('Fixture stream unavailable', 'SecurityError');
      sources.add(this);
      queueMicrotask(() => {
        if (this.readyState === 2 || disposed) return;
        this.readyState = 1;
        const open = new Event('open'); this.onopen?.(open); this.dispatchEvent(open);
        const watermark = Number(url.searchParams.get('last_event_id') ?? 0);
        history.filter((frame) => frame.id > watermark).forEach((frame) => this.frame(frame));
        this.dispatchEvent(new MessageEvent('sync_complete', { data: JSON.stringify({ cursor }) }));
      });
    }
    frame(frame: WireFrame) {
      if (this.readyState !== 1 || disposed) return;
      const event = new MessageEvent('message', { data: JSON.stringify({ eventType: frame.eventType, payload: frame.payload }), lastEventId: String(frame.id) });
      this.onmessage?.(event); this.dispatchEvent(event);
    }
    close() { this.readyState = 2; sources.delete(this); }
  }

  async function fixtureFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
    const request = input instanceof Request ? input : null;
    const url = new URL(request?.url ?? String(input), options.origin);
    const method = (init?.method ?? request?.method ?? 'GET').toUpperCase();
    const signal = init?.signal ?? request?.signal;
    if (signal?.aborted) throw new DOMException('Fixture request aborted', 'AbortError');
    if (disposed) return json({ detail: 'Fixture disposed; reload to reconnect.' }, 503);
    // Only immutable public render assets may leave this fixture boundary.
    // No query, credentials, POST, remote host, API prefix or encoded path.
    if (isFixtureRenderAsset(url, options.origin, method)) {
      return options.assetFetch(url.href, { signal, credentials: 'omit', redirect: 'error' });
    }
    if (method === 'GET' && url.pathname === '/api/v1/mirror/snapshot') return json({
      status: 'online', state: 'measured', phase: held || stopStream ? 'active' : 'unknown',
      last_event_id: cursor, active_workers: [], active_missions: [], active_castes: [], active_models: [],
      pending_events: 0, approval_required: false,
    });
    if (method === 'GET' && url.pathname === '/health') return json({ status: 'ok', fixture: true });
    // Prevent the real session helper's storage fallback; no cookie is sent or created.
    // Deliberately no operatorId: the fixture never claims a sovereign identity.
    if (['GET', 'POST'].includes(method) && url.pathname === '/api/v1/auth/session') return json({ authenticated: true, fixture: true });
    if (method === 'GET' && url.pathname === '/api/v1/onboarding/state') return json({ firstDirective: true, firstApproval: true, firstVerify: true, firstCloudRoute: false, firstAutonomy: false });
    if (method === 'GET' && url.pathname === '/api/v1/voice/models') return json({ stt: false, tts: false, fixture: true });
    let body: Record<string, unknown> = {};
    if (method === 'POST' && ['/api/generate', '/api/v1/approval/req', '/api/v1/intent/preview'].includes(url.pathname)) {
      try {
        const raw: unknown = JSON.parse(String(init?.body ?? (request ? await request.text() : '{}')));
        if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return json({ detail: 'Invalid fixture request' }, 400);
        body = raw as Record<string, unknown>;
      } catch { return json({ detail: 'Invalid fixture JSON' }, 400); }
    }
    if (method === 'POST' && url.pathname === '/api/v1/intent/preview') return json({ intent: 'code', confidence: 1, tool: 'fixture-only' });
    if (method === 'POST' && url.pathname === '/api/v1/approval/req') {
      if (!held || body.approve !== false || body.approvalToken !== held.token) return json({ detail: 'No matching local decision' }, 409);
      releaseHeld(); held = null; emit('turn.failed', { reason: 'Fixture action declined' });
      update({ waitingForDecision: false, label: 'Fixture declined. No file was written.' });
      return json({ decision: 'rejected', fixture: true });
    }
    if (method !== 'POST' || url.pathname !== '/api/generate') return json({ detail: 'Not provided by the isolated fixture. No backend request was sent.' }, 503);
    const tokens = body.approvalTokens;
    if (!Array.isArray(tokens) || stopStream) return json({ detail: 'Fixture already running or invalid tokens' }, 409);
    const messages = body.messages as Array<{ content?: Array<{ text?: unknown }> }> | undefined;
    const prompt = messages?.[0]?.content?.[0]?.text;
    const replay = tokens.length > 0;
    if (replay && (!held || tokens.length !== 1 || tokens[0] !== held.token || prompt !== held.prompt)) return json({ detail: 'No matching local replay' }, 409);
    if (!replay && (held || typeof prompt !== 'string' || !prompt.trim())) return json({ detail: 'Finish the current local decision first' }, 409);
    const current = replay ? held! : { token: `fixture-${++runId}`, prompt: prompt as string, outcome: state.outcome };
    releaseHeld(); held = null;
    update({ waitingForDecision: false });
    emit('turn.started', { fixture: true });
    let closed = false;
    let cancel = () => {};
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        const release = () => { signal?.removeEventListener('abort', abort); stopStream = null; };
        const frame = (event: string, data: object) => { if (!closed) controller.enqueue(new TextEncoder().encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`)); };
        const finish = () => { if (!closed) { closed = true; controller.close(); release(); } };
        const abort = () => { if (!closed) { closed = true; controller.error(new DOMException('Fixture aborted', 'AbortError')); release(); abandon('Fixture cancelled; backend stop was not requested.'); } };
        cancel = () => { if (!closed) { closed = true; release(); abandon('Fixture reader disconnected before completion.'); } };
        stopStream = abort;
        signal?.addEventListener('abort', abort, { once: true });
        enqueue('Advance to partial work', () => { frame('code_chunk', { code: '# Fixture preview — no file has been written\n', language: 'python', filepath: FILEPATH }); });
        if (!replay) {
          enqueue('Advance to the permission boundary', () => {
            held = current;
            // Reader completion is not cancellation of a held decision. Keep
            // the original request's cancellation owner until Deny/replay or
            // a superseding real composer submission aborts that generation.
            const cancelHeld = () => abandon('Fixture decision cancelled by a newer turn.');
            signal?.addEventListener('abort', cancelHeld, { once: true });
            releaseHeldCancellation = () => signal?.removeEventListener('abort', cancelHeld);
            frame('human_required', { text: 'Fixture permission to create hello.py — no real write', input: {
              approvalToken: current.token, creations: [{ filepath: FILEPATH, content: FINAL_CODE }],
              explanation: 'Development-only example. Allow/Deny stays in memory; nothing reaches the backend.',
              diff: '--- /dev/null\n+++ fixture/hello.py\n@@ -0,0 +1 @@\n+print("Hello from the fixture")',
            } });
            update({ waitingForDecision: true, label: 'Use the real Allow/Deny controls. No real permission is granted.' }); finish();
          });
        } else {
          enqueue('Advance to the streamed result', () => { frame('code_chunk', { code: FINAL_CODE, language: 'python', filepath: FILEPATH }); });
          if (current.outcome !== 'unverified') enqueue('Advance to the fixture verifier observation', () => {
            emit('verify_result', { verdict: current.outcome === 'verified' ? 'pass' : 'fail', target: FILEPATH, output: 'Fixture observation only; not an executed check.' });
          });
          enqueue('Advance to the fixture outcome', () => {
            const failed = current.outcome === 'failed';
            emit(failed ? 'turn.failed' : 'turn.completed', { fixture: true });
            frame(failed ? 'error' : 'done', failed ? { text: 'Fixture failure; partial work remains readable.' } : {});
            update({ label: failed ? 'Fixture failed. Partial work remains available.' : `Fixture ${current.outcome}. Try Close and Reopen in Recent activity.` }); finish();
          });
        }
        pending();
      },
      cancel() { cancel(); },
    });
    return new Response(stream, { headers: { 'Content-Type': 'text/event-stream' } });
  }
  return {
    fetch: fixtureFetch as typeof fetch,
    EventSource: FixtureEventSource as unknown as typeof EventSource,
    subscribe: (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    getSnapshot: () => state,
    advance: () => { if (disposed) return; const next = queued.shift(); next?.run(); pending(); },
    setOutcome: (outcome: FixtureOutcome) => { if (!queued.length && !held && !stopStream && ['unverified', 'verified', 'failed'].includes(outcome)) update({ outcome }); },
    dispose: () => { disposed = true; stopStream?.(); releaseHeld(); sources.forEach((source) => source.close()); queued.length = 0; held = null; update({ pending: false, waitingForDecision: false }); listeners.clear(); },
  };
}
