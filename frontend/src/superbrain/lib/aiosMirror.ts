/** Live backend connection for the truthful Living Mirror. */
import { useMirrorStore } from './mirrorStore';
import { dispatchLivingMirrorEvent } from './livingMirrorRegistry';
import { humanizeRedactionMarkers } from './aiosAdapter';

const AIOS_BASE = process.env.NEXT_PUBLIC_AIOS_URL ?? 'http://localhost:8000';

let mirrorEventSource: EventSource | null = null;

const isDurableEventId = (value: string): boolean => {
  if (!/^\d+$/.test(value)) return false;
  const id = Number(value);
  return Number.isSafeInteger(id) && id >= 0;
};

const readJsonRecord = (data: string): Record<string, unknown> | null => {
  try {
    const parsed = JSON.parse(data) as unknown;
    return parsed && typeof parsed === 'object' ? parsed as Record<string, unknown> : null;
  } catch {
    return null;
  }
};

async function refreshMirrorSnapshot(): Promise<void> {
  try {
    const response = await fetch(`${AIOS_BASE}/api/v1/mirror/snapshot`);
    if (response.ok) {
      const data = await response.json() as Record<string, unknown>;
      useMirrorStore.getState().setSnapshot(data);
    }
  } catch (error) {
    console.warn('Failed to refresh mirror snapshot', error);
  }
}

export async function startMirrorClient(): Promise<void> {
  if (mirrorEventSource) return;

  let lastEventId: number | null = null;
  try {
    const response = await fetch(`${AIOS_BASE}/api/v1/mirror/snapshot`);
    if (response.ok) {
      const data = await response.json() as Record<string, unknown>;
      useMirrorStore.getState().setSnapshot(data);
      if (typeof data.last_event_id === 'number'
        && Number.isSafeInteger(data.last_event_id)
        && data.last_event_id >= 0) {
        lastEventId = data.last_event_id;
      }
    }
  } catch (error) {
    console.warn('Failed to fetch mirror snapshot', error);
  }

  const streamUrl = lastEventId === null
    ? `${AIOS_BASE}/api/v1/mirror/stream`
    : `${AIOS_BASE}/api/v1/mirror/stream?last_event_id=${lastEventId}`;
  const source = new EventSource(streamUrl);
  mirrorEventSource = source;

  source.onopen = () => useMirrorStore.getState().setStatus('online');
  source.onerror = () => useMirrorStore.getState().setStatus('offline');
  source.addEventListener('snapshot_required', (rawEvent: Event) => {
    const event = rawEvent as MessageEvent<string>;
    const detail = readJsonRecord(event.data ?? '');
    const reason = typeof detail?.reason === 'string' ? detail.reason : undefined;
    useMirrorStore.getState().setSnapshotRequired(reason);
    void refreshMirrorSnapshot();
  });
  source.onmessage = (event) => {
    if (event.type === 'ping') return;
    const canonical = readJsonRecord(event.data);
    if (!canonical) {
      useMirrorStore.getState().setAnnouncement('Malformed mirror event ignored.');
      return;
    }
    if (!isDurableEventId(event.lastEventId)) {
      useMirrorStore.getState().setAnnouncement('Mirror event missing a durable cursor; event ignored.');
      return;
    }
    const eventType = typeof canonical.eventType === 'string' ? canonical.eventType.trim() : '';
    if (!eventType) {
      useMirrorStore.getState().setAnnouncement('Malformed mirror event ignored.');
      return;
    }
    const id = Number(event.lastEventId);
    const rawPayload = canonical.payload;
    const payload = rawPayload && typeof rawPayload === 'object'
      ? rawPayload as Record<string, unknown>
      : {};
    const safePayload = Object.fromEntries(
      Object.entries(payload).map(([key, value]) => [
        key,
        typeof value === 'string' ? humanizeRedactionMarkers(value) : value,
      ]),
    ) as Record<string, unknown>;
    dispatchLivingMirrorEvent({ id, eventType, canonical, payload: safePayload });
  };
}

export function stopMirrorClient(): void {
  if (!mirrorEventSource) return;
  mirrorEventSource.close();
  mirrorEventSource = null;
  useMirrorStore.getState().setStatus('offline');
}
