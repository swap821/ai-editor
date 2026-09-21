/** One generation-fenced owner for snapshot + canonical stream. */
import { useMirrorStore } from './mirrorStore';
import { dispatchLivingMirrorEvent } from './livingMirrorRegistry';
import { humanizeRedactionMarkers } from './aiosAdapter';
import { isRecord, stringList } from '../../livingMirror/contracts';
import { API_BASE } from '../../config';

let source: EventSource | null = null;
let controller: AbortController | null = null;
let timer: ReturnType<typeof setTimeout> | null = null;
let running = false;
let generation = 0;
let startPromise: Promise<void> | null = null;
let retryDelay = 1000;

const record = (raw: string): Record<string, unknown> | null => {
  try { const value: unknown = JSON.parse(raw); return isRecord(value) ? value : null; } catch { return null; }
};
const validSnapshot = (data: unknown): data is Record<string, unknown> => isRecord(data)
  && data.status === 'online' && ['measured', 'stale'].includes(String(data.state))
  && typeof data.last_event_id === 'number' && Number.isSafeInteger(data.last_event_id) && data.last_event_id >= 0
  && ['active_workers', 'active_missions', 'active_castes'].every((key) => stringList(data[key]))
  && typeof data.phase === 'string';

function cancelTransport() {
  controller?.abort(); controller = null;
  source?.close(); source = null;
  if (timer !== null) clearTimeout(timer);
  timer = null;
}

function reconnect(reason: string, immediate = false) {
  if (!running) return;
  generation += 1;
  cancelTransport();
  useMirrorStore.getState().markStale(reason);
  useMirrorStore.getState().setConnection('connecting');
  const delay = immediate ? 0 : retryDelay;
  retryDelay = Math.min(retryDelay * 2, 30000);
  timer = setTimeout(() => { timer = null; startPromise = connect(generation); }, delay);
}

async function connect(epoch: number): Promise<void> {
  const active = () => running && generation === epoch;
  const request = new AbortController();
  controller = request;
  useMirrorStore.getState().setConnection('connecting');
  if (!useMirrorStore.getState().snapshotReceivedAt) useMirrorStore.setState({ projection: 'synchronizing' });
  let watermark: number | null = null;
  try {
    const response = await fetch(`${API_BASE}/api/v1/mirror/snapshot`, { credentials: 'include', signal: request.signal });
    if (!active()) return;
    if (!response.ok) throw new Error(response.status === 401 ? 'Connect your operator session to inspect operational state.' : `Snapshot unavailable (HTTP ${response.status}).`);
    const data: unknown = await response.json();
    if (!active()) return;
    if (!validSnapshot(data)) throw new Error('Snapshot schema is incomplete; operational state remains unavailable.');
    useMirrorStore.getState().setSnapshot(data);
    watermark = data.last_event_id as number;
  } catch (error) {
    if (!active()) return;
    useMirrorStore.getState().markStale(error instanceof Error ? error.message : 'Snapshot unavailable.');
  }
  if (!active()) return;
  const stream = new EventSource(`${API_BASE}/api/v1/mirror/stream${watermark === null ? '' : `?last_event_id=${watermark}`}`, { withCredentials: true });
  source = stream;
  const owns = () => active() && source === stream;
  stream.onopen = () => {
    if (!owns()) return;
    retryDelay = 1000;
    useMirrorStore.getState().setConnection('connected');
    // This backend has no replay/live barrier. A connection is not a synchronized projection.
    useMirrorStore.getState().setAnnouncement('Event transport connected. Snapshot continuity is not yet confirmed.');
    // Periodically replace the snapshot so a silent replay/subscription gap cannot age invisibly.
    timer = setTimeout(() => reconnect('Refreshing the last-known snapshot.', true), 30000);
  };
  stream.onerror = () => { if (owns()) reconnect('Event connection interrupted; displayed records are last-known.'); };
  stream.addEventListener('snapshot_required', (event) => {
    if (!owns()) return;
    const data = record((event as MessageEvent<string>).data ?? '');
    useMirrorStore.getState().setSnapshotRequired(typeof data?.reason === 'string' ? data.reason : undefined);
    reconnect('A fresh snapshot is required before continuity can be assessed.', true);
  });
  stream.onmessage = (event) => {
    if (!owns()) return;
    const canonical = record(event.data);
    if (!canonical || typeof canonical.eventType !== 'string' || !canonical.eventType.trim() || !isRecord(canonical.payload)) {
      useMirrorStore.getState().setAnnouncement('Malformed mirror event ignored.'); return;
    }
    if (!/^\d+$/.test(event.lastEventId) || !Number.isSafeInteger(Number(event.lastEventId))) {
      useMirrorStore.getState().setAnnouncement('Mirror event missing a durable cursor; event ignored.'); return;
    }
    const payload = Object.fromEntries(Object.entries(canonical.payload).map(([key, value]) => [key, typeof value === 'string' ? humanizeRedactionMarkers(value) : value]));
    // Without a supported live barrier, replay and live delivery cannot be distinguished.
    // Admit observations but do not reenact them as present-tense animation or announcements.
    dispatchLivingMirrorEvent({ id: Number(event.lastEventId), eventType: canonical.eventType.trim(), canonical, payload, replay: true });
  };
}

export function startMirrorClient(): Promise<void> {
  if (running) return startPromise ?? Promise.resolve();
  running = true; generation += 1;
  startPromise = connect(generation);
  return startPromise;
}

export function stopMirrorClient(): void {
  running = false; generation += 1; startPromise = null; retryDelay = 1000;
  cancelTransport();
  useMirrorStore.getState().markStale();
  useMirrorStore.getState().setConnection('disconnected');
}
