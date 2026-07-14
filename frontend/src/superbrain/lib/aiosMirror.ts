/** Live backend connection for the truthful Living Mirror. */
import { useMirrorStore } from './mirrorStore';
import { dispatchLivingMirrorEvent } from './livingMirrorRegistry';
import { humanizeRedactionMarkers } from './aiosAdapter';

const AIOS_BASE = process.env.NEXT_PUBLIC_AIOS_URL ?? 'http://localhost:8000';

let mirrorEventSource: EventSource | null = null;

export async function startMirrorClient(): Promise<void> {
  if (mirrorEventSource) return;

  let lastEventId: number | null = null;
  try {
    const response = await fetch(`${AIOS_BASE}/api/v1/mirror/snapshot`);
    if (response.ok) {
      const data = await response.json() as Record<string, unknown>;
      useMirrorStore.getState().setSnapshot(data);
      if (typeof data.last_event_id === 'number') lastEventId = data.last_event_id;
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
  source.onmessage = (event) => {
    if (event.type === 'ping') return;
    let canonical: Record<string, unknown>;
    try {
      canonical = JSON.parse(event.data) as Record<string, unknown>;
    } catch {
      useMirrorStore.getState().setAnnouncement('Malformed mirror event ignored.');
      return;
    }
    const idValue = event.lastEventId ? Number.parseInt(event.lastEventId, 10) : Date.now();
    const id = Number.isFinite(idValue) ? idValue : Date.now();
    const eventType = String(canonical.eventType ?? event.type ?? '');
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
