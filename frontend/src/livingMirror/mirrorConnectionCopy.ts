import type { ExperienceMode } from './experienceMode';

export type MirrorConnectionTone = 'offline' | 'checking' | 'stale' | 'ready';

export type MirrorConnectionState = {
  status: 'offline' | 'online' | 'stale';
  connection: 'disconnected' | 'connecting' | 'connected';
  projection: 'unknown' | 'synchronizing' | 'snapshot' | 'fresh' | 'stale' | 'unavailable';
  snapshotReceivedAt: string | null;
  lastEventId: number | null;
};

export type MirrorConnectionCopy = {
  label: string;
  detail: string;
  tone: MirrorConnectionTone;
  canRetry: boolean;
  technical: string;
};

/**
 * Keep transport, snapshot, and continuity separate in the words shown to a
 * person. A socket opening is not evidence that the live projection is
 * current; only the mirror's explicit `fresh` projection earns ready copy.
 */
export function getMirrorConnectionCopy(
  state: MirrorConnectionState,
  mode: ExperienceMode = 'beginner',
): MirrorConnectionCopy {
  const hasSnapshot = Boolean(state.snapshotReceivedAt);
  const technical = `transport ${state.connection}; projection ${state.projection}; cursor ${state.lastEventId ?? 'unavailable'}`;

  if (state.projection === 'fresh' && state.connection === 'connected' && state.status === 'online') {
    return {
      label: mode === 'expert' ? 'Live projection ready' : 'GAGOS is ready',
      detail: mode === 'expert' ? 'Continuity has been confirmed.' : 'The live picture is current.',
      tone: 'ready',
      canRetry: false,
      technical,
    };
  }

  if (hasSnapshot && (state.projection === 'stale' || state.connection !== 'connected' || (state.status === 'stale' && state.projection !== 'snapshot'))) {
    return {
      label: mode === 'expert' ? 'Transport reconnecting' : 'Showing the last known picture',
      detail: mode === 'expert'
        ? 'The displayed projection is stale; new state is not confirmed.'
        : 'Reconnecting. New changes are not confirmed yet.',
      tone: 'stale',
      canRetry: true,
      technical,
    };
  }

  if (state.connection === 'connecting' || state.projection === 'synchronizing') {
    return {
      label: mode === 'expert' ? 'Transport connecting' : 'Connecting to GAGOS…',
      detail: mode === 'expert' ? 'Reading the local snapshot.' : 'Checking the local operational picture.',
      tone: 'checking',
      canRetry: false,
      technical,
    };
  }

  if (state.connection === 'connected' && state.projection === 'snapshot') {
    return {
      label: mode === 'expert' ? 'Transport connected' : 'GAGOS is connected',
      detail: mode === 'expert'
        ? 'Transport is open, but continuity is not yet confirmed.'
        : 'Checking that the live picture has no gap.',
      tone: 'checking',
      canRetry: false,
      technical,
    };
  }

  return {
    label: mode === 'expert' ? 'Operational state unavailable' : 'GAGOS is offline',
    detail: mode === 'expert' ? 'No confirmed operational snapshot is available.' : 'Start the local service, then try again.',
    tone: 'offline',
    canRetry: true,
    technical,
  };
}
