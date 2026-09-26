/**
 * Engage -> clear must un-freeze the being, through the REAL dispatch path.
 *
 * Found reviewing PR #363 (2026-09-24). stopState() reads the last
 * `emergency_stop` event in mirror.recentEvents. The backend only ever
 * published `governance.emergency_stop.engaged`, so after a legitimate clear
 * the last such event was still the engagement and the organism stayed frozen
 * for the rest of the session -- while the REST-backed control panel correctly
 * showed resumed.
 *
 * The backend now publishes `governance.emergency_stop.cleared`. This test
 * drives both events through dispatchLivingMirrorEvent -- not by writing
 * recentEvents directly -- because the bug had TWO halves: the backend never
 * sent the event, and dispatch() drops any type with no registry entry before
 * applyEvent() runs. A test that seeded recentEvents by hand would pass with
 * the registry entry missing, which is exactly the vacuous pass to avoid.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { dispatchLivingMirrorEvent } from '../../superbrain/lib/livingMirrorRegistry';
import { useMirrorStore } from '../../superbrain/lib/mirrorStore';
import { publishCognition } from '../../superbrain/lib/cognitionBus';
import type { TabSnapshot } from '../../superbrain/lib/tabStore';
import { beingFactsFromStores } from './presentationFromStores';

vi.mock('../../superbrain/lib/cognitionBus', () => ({ publishCognition: vi.fn() }));
vi.mock('../../superbrain/lib/aiosAdapter', () => ({ humanizeRedactionMarkers: (value: string) => value }));
vi.mock('../../superbrain/lib/swarmHUDStore', () => ({
  endSwarmCaste: vi.fn(),
  markSwarmCloudSubtask: vi.fn(),
  startSwarmCaste: vi.fn(),
  startSwarmPlan: vi.fn(),
}));

const NO_TABS: TabSnapshot = { tabs: [], focusId: null, attention: null };

const event = (id: number, eventType: string, payload: Record<string, unknown>) => ({
  id,
  eventType,
  canonical: { eventId: `event-${id}`, eventType, schema_version: '1', payload, ...payload },
  payload,
});

const stop = () => beingFactsFromStores(useMirrorStore.getState(), NO_TABS, 'idle').stop;

describe('emergency stop: engage then clear, through dispatch', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useMirrorStore.setState({ recentEvents: [], lastEventId: null, lastTurnStartedEventId: null, lastVerificationEventId: null, lastAnnouncement: null });
  });

  it('reads engaged after the engagement', () => {
    expect(dispatchLivingMirrorEvent(event(1, 'governance.emergency_stop.engaged', { reason: 'drill' }))).toBe(true);
    expect(stop()).toBe('engaged');
  });

  it('reads clear after the clear -- the organism is no longer frozen', () => {
    dispatchLivingMirrorEvent(event(1, 'governance.emergency_stop.engaged', { reason: 'drill' }));
    expect(stop()).toBe('engaged');

    // Must be ADMITTED, not dropped as an unsupported type.
    expect(dispatchLivingMirrorEvent(event(2, 'governance.emergency_stop.cleared', { operator_id: 'op' }))).toBe(true);
    expect(useMirrorStore.getState().recentEvents.some((e) => e.type === 'governance.emergency_stop.cleared')).toBe(true);
    expect(stop()).toBe('clear');
  });

  it('publishes no invented cognition type for the clear', () => {
    // There is no CognitionEventType for "restored". A reaction that invented
    // one would be the same defect this fix removes: a name nothing handles.
    dispatchLivingMirrorEvent(event(1, 'governance.emergency_stop.cleared', { operator_id: 'op' }));
    expect(publishCognition).not.toHaveBeenCalled();
  });

  it('is the registry entry that makes this work (negative control)', () => {
    // An unregistered spelling is refused by dispatch and never reaches the
    // being -- proving the entry, not something incidental, carries the fix.
    dispatchLivingMirrorEvent(event(1, 'governance.emergency_stop.engaged', { reason: 'drill' }));
    expect(dispatchLivingMirrorEvent(event(2, 'governance.emergency_stop.resumed', {}))).toBe(false);
    expect(stop()).toBe('engaged');
  });
});
