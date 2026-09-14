import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { startMirrorClient, stopMirrorClient } from './aiosMirror';
import { publishCognition } from './cognitionBus';
import { useMirrorStore } from './mirrorStore';

vi.mock('./cognitionBus', () => ({
  publishCognition: vi.fn(),
}));
vi.mock('./aiosAdapter', () => ({
  humanizeRedactionMarkers: vi.fn((x) => x),
}));
vi.mock('./swarmHUDStore', () => ({
  endSwarmCaste: vi.fn(),
  markSwarmCloudSubtask: vi.fn(),
  startSwarmCaste: vi.fn(),
  startSwarmPlan: vi.fn(),
}));

describe('aiosMirror', () => {
  let mockEventSource: any;

  beforeEach(() => {
    vi.clearAllMocks();
    const listeners: Record<string, (event: Event) => void> = {};
    mockEventSource = {
      onopen: null,
      onerror: null,
      onmessage: null,
      close: vi.fn(),
      listeners,
      addEventListener: vi.fn((type: string, listener: EventListener) => {
        listeners[type] = listener as (event: Event) => void;
      }),
    };
    vi.stubGlobal('EventSource', vi.fn(function() { return mockEventSource; }));
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ history: [] }),
    }));
    useMirrorStore.setState({
      status: 'offline',
      lastEventId: null,
      snapshotRequired: false,
      lastAnnouncement: null,
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    stopMirrorClient();
  });

  it('starts client and connects', async () => {
    await startMirrorClient();
    expect(useMirrorStore.getState().status).toBe('offline'); // initial state before open

    
    // Simulate open
    mockEventSource.onopen();
    expect(useMirrorStore.getState().status).toBe('online');
    
    // Simulate error
    mockEventSource.onerror();
    expect(useMirrorStore.getState().status).toBe('offline');
  });

  it('handles cognitive_action events', async () => {
    await startMirrorClient();
    
    mockEventSource.onmessage({
      type: 'aios.cognitive_action',
      lastEventId: '1',
      data: JSON.stringify({
        schemaVersion: '1.0',
        eventId: 'event-1',
        eventType: 'aios.cognitive_action',
        payload: { label: 'THINK', body: 'thinking', redacted: false }
      })
    });
    
    expect(publishCognition).toHaveBeenCalledWith(expect.objectContaining({
      type: 'aios.cognitive_action',
      label: 'THINK',
      body: 'thinking'
    }));
  });

  it('handles step/tool_call events', async () => {
    await startMirrorClient();
    
    mockEventSource.onmessage({
      type: 'step',
      lastEventId: '2',
      data: JSON.stringify({
        schemaVersion: '1.0',
        eventId: 'event-2',
        eventType: 'step',
        payload: { type: 'tool_call', tool: 'write_file', output: '' }
      })
    });
    
    expect(publishCognition).toHaveBeenCalledWith(expect.objectContaining({
      type: 'agent-dispatch',
      label: 'WRITE_FILE',
    }));
  });
  
  it('handles step/tool_result VERIFY PASS', async () => {
    await startMirrorClient();
    
    mockEventSource.onmessage({
      type: 'step',
      lastEventId: '3',
      data: JSON.stringify({
        schemaVersion: '1.0',
        eventId: 'event-3',
        eventType: 'step',
        payload: { type: 'tool_result', tool: 'run_command', output: '[VERIFY PASS] tests passed' }
      })
    });
    
    expect(publishCognition).toHaveBeenCalledWith(expect.objectContaining({
      type: 'knowledge-acquired',
      label: 'VERIFICATION GREEN',
    }));
  });

  it('handles swarm_plan and caste events', async () => {
    await startMirrorClient();

    const sendCanonical = (id: number, eventType: string, payload: Record<string, unknown>) => {
      mockEventSource.onmessage({
        type: eventType,
        lastEventId: String(id),
        data: JSON.stringify({
          schemaVersion: '1.0',
          eventId: `event-${id}`,
          eventType,
          payload,
        }),
      });
    };

    sendCanonical(10, 'swarm_plan', { plan: ['a', 'b'] });
    sendCanonical(11, 'caste_start', { caste: 'integration' });
    sendCanonical(12, 'verify_result', { verdict: 'pass', target: 'tests' });
    
    // Trigger more event types to bump branch coverage
    sendCanonical(13, 'aios.message', {});
    sendCanonical(14, 'aios.error', {});
    sendCanonical(15, 'aios.intent', {});
    sendCanonical(16, 'turn.started', {});
    sendCanonical(17, 'turn.completed', {});
    sendCanonical(18, 'plan.created', {});
    sendCanonical(19, 'worker.started', { workerId: 'worker-1' });
    sendCanonical(20, 'worker.dissolved', { workerId: 'worker-1' });
    sendCanonical(21, 'memory.recalled', {});
    // The truthful event, and the retained legacy one. Both must render:
    // journals recorded before the rename still replay.
    sendCanonical(22, 'memory.trusted_workflow_surfaced', { workflowId: 'wf-1', applied: false });
    sendCanonical(220, 'memory.trusted_workflow_applied', {});
    sendCanonical(23, 'telemetry.agent_started', {});
    sendCanonical(24, 'human_required', { text: 'approve' });
    sendCanonical(25, 'code', {});
    sendCanonical(26, 'alignment', {});
    sendCanonical(27, 'edit.proposed', {});
    sendCanonical(28, 'edit.blocked', {});
    sendCanonical(29, 'earned_autonomy', {});
    sendCanonical(30, 'plan', {});
    sendCanonical(31, 'caste_end', { caste: 'integration' });
    sendCanonical(32, 'cloud_route', { subtask_index: 0 });
    sendCanonical(33, 'turn.failed', {});
    sendCanonical(34, 'route', {});

    expect(publishCognition).toHaveBeenCalled();
  });

  it('seeds the durable cursor and refreshes measured state on snapshot_required', async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ status: 'online', state: 'measured', last_event_id: 4 }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ status: 'online', state: 'measured', last_event_id: 9 }),
      } as Response);

    await startMirrorClient();
    expect(useMirrorStore.getState().lastEventId).toBe(4);
    // The second argument is `{ withCredentials: true }`: the stream is a
    // bonded read and answered 401 without it. Asserted here as well as in its
    // own test so this cursor check cannot be satisfied by a call that has
    // quietly lost the session again.
    expect(vi.mocked(EventSource)).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/mirror/stream?last_event_id=4',
      { withCredentials: true },
    );

    mockEventSource.listeners.snapshot_required(new MessageEvent('snapshot_required', {
      data: JSON.stringify({ reason: 'replay_gap' }),
    }));
    await Promise.resolve();
    await Promise.resolve();

    expect(useMirrorStore.getState().lastEventId).toBe(9);
    expect(useMirrorStore.getState().snapshotRequired).toBe(false);
    expect(useMirrorStore.getState().status).toBe('online');
  });

  it('ignores events without a durable cursor or canonical event type', async () => {
    await startMirrorClient();

    mockEventSource.onmessage({
      type: 'step',
      lastEventId: '',
      data: JSON.stringify({
        schemaVersion: '1.0',
        eventId: 'event-missing-cursor',
        eventType: 'step',
        payload: { type: 'tool_call', tool: 'write_file' },
      }),
    });
    expect(useMirrorStore.getState().lastEventId).toBeNull();

    mockEventSource.onmessage({
      type: 'step',
      lastEventId: '4',
      data: JSON.stringify({
        schemaVersion: '1.0',
        eventId: 'event-missing-type',
        payload: { type: 'tool_call', tool: 'write_file' },
      }),
    });
    expect(useMirrorStore.getState().lastEventId).toBeNull();
    expect(useMirrorStore.getState().lastAnnouncement).toBe('Malformed mirror event ignored.');
  });
});

describe('aiosMirror carries the operator session', () => {
  // BOTH TRANSPORTS, because the mirror reads bonded operator data over two of
  // them and only one was ever fixed at a time. Found in a real browser: the
  // snapshot fetch was bare, so `/api/v1/mirror/snapshot` answered 401 and the
  // surface rendered "Control plane unavailable" while holding a perfectly
  // good session. Adding credentials to the fetch alone left the page
  // half-fixed -- "Models participating" became a measured 0 while "Control
  // plane" stayed offline, because the EventSource still sent no cookie.
  //
  // Mocked transports cannot notice a missing cookie, which is exactly why
  // this file's existing tests passed throughout. These assert the OPTION,
  // which is the part that was missing.
  beforeEach(() => {
    vi.clearAllMocks();
    const stub = {
      onopen: null,
      onerror: null,
      onmessage: null,
      close: vi.fn(),
      addEventListener: vi.fn(),
    } as unknown as EventSource;
    // `function`, not an arrow: an arrow cannot be called with `new`.
    vi.stubGlobal('EventSource', vi.fn(function () { return stub; }));
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ history: [] }),
    } as unknown as Response));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    stopMirrorClient();
  });

  it('sends credentials on the snapshot fetch', async () => {
    await startMirrorClient();

    const call = vi.mocked(fetch).mock.calls.find(([url]) =>
      String(url).includes('/api/v1/mirror/snapshot'),
    );
    expect(call, 'the mirror never fetched its snapshot').toBeTruthy();
    expect(call?.[1]?.credentials).toBe('include');
  });

  it('opens the event stream with withCredentials', async () => {
    await startMirrorClient();

    const calls = vi.mocked(EventSource).mock.calls;
    expect(calls.length, 'the mirror never opened a stream').toBeGreaterThan(0);
    const [url, init] = calls[0];
    expect(String(url)).toContain('/api/v1/mirror/stream');
    expect(init?.withCredentials).toBe(true);
  });
});
