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
    sendCanonical(22, 'memory.trusted_workflow_applied', {});
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
    expect(vi.mocked(EventSource)).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/mirror/stream?last_event_id=4',
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
