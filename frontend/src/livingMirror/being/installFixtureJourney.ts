import { createFixtureJourneyTransport, isFixtureRenderAsset } from './fixtureJourneyTransport';
const installed = new WeakMap<object, ReturnType<typeof createFixtureJourneyTransport>>();

/** One-way page isolation: never restore live transports during an app remount. */
export function installFixtureJourney(host: Window & typeof globalThis) {
  const existing = installed.get(host);
  if (existing) return existing;
  const fixture = createFixtureJourneyTransport({ origin: host.location.origin, assetFetch: host.fetch.bind(host) });
  host.fetch = fixture.fetch;
  host.EventSource = fixture.EventSource;
  class UnavailableFixtureTransport {
    constructor() { throw new DOMException('Unavailable in the isolated fixture journey', 'SecurityError'); }
  }
  host.WebSocket = UnavailableFixtureTransport as unknown as typeof WebSocket;
  // Troika loads local TTF data with XHR. Adapt that narrow operation to the
  // same asset fence; never instantiate the native XHR or allow API routes.
  class FixtureAssetXHR extends EventTarget {
    responseType: XMLHttpRequestResponseType = '';
    response: unknown = null;
    responseText = ''; status = 0; statusText = ''; readyState = 0;
    onload: ((event: Event) => void) | null = null;
    onerror: ((event: Event) => void) | null = null;
    onreadystatechange: ((event: Event) => void) | null = null;
    private url: URL | null = null;
    private controller: AbortController | null = null;
    open(method: string, raw: string | URL, async = true) {
      const url = new URL(String(raw), host.location.origin);
      if (!async || !isFixtureRenderAsset(url, host.location.origin, method.toUpperCase())) {
        throw new DOMException('XHR unavailable in the isolated fixture', 'SecurityError');
      }
      this.url = url; this.readyState = 1;
    }
    send() {
      if (!this.url || this.controller) throw new DOMException('Fixture XHR not opened', 'InvalidStateError');
      const controller = new AbortController(); this.controller = controller;
      void fixture.fetch(this.url, { signal: controller.signal }).then(async (response) => {
        const data = this.responseType === 'arraybuffer' ? await response.arrayBuffer() : await response.text();
        if (controller.signal.aborted) return;
        this.status = response.status; this.statusText = response.statusText; this.readyState = 4;
        this.response = data; this.responseText = typeof data === 'string' ? data : '';
        const change = new Event('readystatechange'); this.onreadystatechange?.(change); this.dispatchEvent(change);
        const load = new Event('load'); this.onload?.(load); this.dispatchEvent(load);
      }).catch(() => {
        if (!controller.signal.aborted) { const error = new Event('error'); this.onerror?.(error); this.dispatchEvent(error); }
      });
    }
    abort() { this.controller?.abort(); }
  }
  host.XMLHttpRequest = FixtureAssetXHR as unknown as typeof XMLHttpRequest;
  const speechHost = host as unknown as Record<string, unknown>;
  for (const key of ['SpeechRecognition', 'webkitSpeechRecognition']) {
    // The real voice owner feature-detects these constructors. A truthy
    // throwing constructor would offer a route that crashes on opt-in.
    if (key in speechHost) speechHost[key] = undefined;
  }
  host.navigator.sendBeacon = () => false;
  if (host.navigator.mediaDevices) host.navigator.mediaDevices.getUserMedia = async () => {
    throw new DOMException('Microphone unavailable in the isolated fixture journey', 'NotAllowedError');
  };
  // Do not restore live routes on StrictMode/HMR/unmount. Reloading the page
  // is the only exit, and creates a fresh app/session state rather than
  // allowing fixture capabilities or retained work to reach a real backend.
  host.addEventListener('beforeunload', () => fixture.dispose(), { once: true });
  installed.set(host, fixture);
  return fixture;
}
