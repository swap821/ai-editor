import { describe, expect, it } from 'vitest';
import { getMirrorConnectionCopy } from './mirrorConnectionCopy';

const base = {
  status: 'offline' as const,
  connection: 'disconnected' as const,
  projection: 'unknown' as const,
  snapshotReceivedAt: null,
  lastEventId: null,
};

describe('mirror connection copy', () => {
  it('uses plain recovery language before any operational snapshot exists', () => {
    expect(getMirrorConnectionCopy(base, 'beginner')).toMatchObject({
      label: 'GAGOS is offline',
      detail: 'Start the local service, then try again.',
      tone: 'offline',
      canRetry: true,
    });
  });

  it('describes an interrupted connection as last-known state, not current truth', () => {
    expect(getMirrorConnectionCopy({
      ...base,
      status: 'stale',
      connection: 'connecting',
      projection: 'stale',
      snapshotReceivedAt: '2026-09-21T12:00:00.000Z',
      lastEventId: 18,
    }, 'beginner')).toMatchObject({
      label: 'Showing the last known picture',
      detail: 'Reconnecting. New changes are not confirmed yet.',
      tone: 'stale',
      canRetry: true,
    });
  });

  it('does not call a transport connection a synchronized projection', () => {
    expect(getMirrorConnectionCopy({
      ...base,
      status: 'stale',
      connection: 'connected',
      projection: 'snapshot',
      snapshotReceivedAt: '2026-09-21T12:00:00.000Z',
      lastEventId: 18,
    }, 'beginner')).toMatchObject({
      label: 'Connection open',
      detail: 'Checking that the live picture has no gap.',
      tone: 'checking',
      canRetry: false,
    });
  });

  it('only uses ready language for a fresh projection', () => {
    expect(getMirrorConnectionCopy({
      ...base,
      status: 'online',
      connection: 'connected',
      projection: 'fresh',
      snapshotReceivedAt: '2026-09-21T12:00:00.000Z',
      lastEventId: 19,
    }, 'beginner')).toMatchObject({
      label: 'GAGOS is ready',
      detail: 'The live picture is current.',
      tone: 'ready',
      canRetry: false,
    });
  });

  it('distinguishes reachable service health from unavailable mirror access', () => {
    expect(getMirrorConnectionCopy({
      ...base,
      connection: 'connecting',
      projection: 'unavailable',
      lastAnnouncement: 'Snapshot unavailable (HTTP 401).',
    }, 'beginner')).toMatchObject({
      label: 'Operational picture unavailable',
      detail: 'GAGOS is reachable, but the live picture is unavailable in this session.',
      tone: 'unavailable',
      canRetry: true,
    });
  });

  it('keeps the technical evidence visible in Expert mode', () => {
    const copy = getMirrorConnectionCopy({
      ...base,
      status: 'stale',
      connection: 'connected',
      projection: 'snapshot',
      snapshotReceivedAt: '2026-09-21T12:00:00.000Z',
      lastEventId: 18,
    }, 'expert');

    expect(copy.label).toBe('Transport connected');
    expect(copy.detail).toContain('continuity is not yet confirmed');
    expect(copy.technical).toContain('cursor 18');
  });
});
