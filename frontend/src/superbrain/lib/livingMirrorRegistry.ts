/**
 * Typed operational reaction registry for the Living Mirror.
 *
 * Backend events are observations.  A registered event may update the mirror
 * read model and produce a bounded visual/accessibility reaction; unknown or
 * malformed events are logged and ignored.  Ambient animation is intentionally
 * absent from this registry so idle beauty cannot claim backend activity.
 */
import { publishCognition } from './cognitionBus';
import { humanizeRedactionMarkers } from './aiosAdapter';
import { useMirrorStore } from './mirrorStore';
import {
  endSwarmCaste,
  markSwarmCloudSubtask,
  startSwarmCaste,
  startSwarmPlan,
} from './swarmHUDStore';

export interface MirrorEventEnvelope {
  id: number;
  eventType: string;
  canonical: Record<string, unknown>;
  payload: Record<string, unknown>;
}

type ReactionSpec = {
  requiredFields?: readonly string[];
  announcement?: (payload: Record<string, unknown>) => string;
  react?: (event: MirrorEventEnvelope) => void;
  operational?: boolean;
};

const value = (payload: Record<string, unknown>, ...keys: string[]): unknown => {
  for (const key of keys) if (payload[key] !== undefined) return payload[key];
  return undefined;
};

const text = (payload: Record<string, unknown>, ...keys: string[]): string =>
  String(value(payload, ...keys) ?? '');

const publish = (event: Record<string, unknown>): void => {
  publishCognition(event as unknown as Parameters<typeof publishCognition>[0]);
};

const required = (fields: readonly string[] | undefined, payload: Record<string, unknown>): boolean =>
  !fields || fields.every((field) => {
    const snakeField = field.replace(/[A-Z]/g, (letter) => `_${letter.toLowerCase()}`);
    return value(payload, field, snakeField) !== undefined;
  });

const core: Record<string, ReactionSpec> = {
  'aios.cognitive_action': {
    announcement: (p) => text(p, 'label', 'body').slice(0, 160),
    react: ({ canonical, payload }) => publish({
      type: 'aios.cognitive_action',
      spine_id: String(canonical.eventId ?? ''),
      label: humanizeRedactionMarkers(text(payload, 'label')),
      body: humanizeRedactionMarkers(text(payload, 'body')),
      redacted: payload.redacted,
    }),
  },
  'aios.message': {
    react: ({ canonical, payload }) => publish({
      type: 'message',
      spine_id: String(canonical.eventId ?? ''),
      label: humanizeRedactionMarkers(text(payload, 'label')),
      body: humanizeRedactionMarkers(text(payload, 'body')),
      role: payload.role,
      speaker: payload.speaker,
      metadata: payload.metadata,
    }),
  },
  'aios.error': {
    announcement: (p) => `Backend error: ${text(p, 'body', 'label') || 'unknown'}`.slice(0, 160),
    react: ({ canonical, payload }) => publish({
      type: 'error',
      spine_id: String(canonical.eventId ?? ''),
      label: humanizeRedactionMarkers(text(payload, 'label')),
      body: humanizeRedactionMarkers(text(payload, 'body')),
      code: payload.code,
      recoverable: payload.recoverable,
    }),
  },
  'aios.intent': {
    react: ({ canonical, payload }) => publish({
      type: 'aios.intent',
      spine_id: String(canonical.eventId ?? ''),
      label: humanizeRedactionMarkers(text(payload, 'label')),
      body: humanizeRedactionMarkers(text(payload, 'body')),
    }),
  },
  'turn.started': {
    announcement: () => 'A directive is active.',
    react: () => publish({ type: 'knowledge-acquired', label: 'TURN STARTED', detail: 'Superbrain active', intensity: 0.5, source: 'mirror' }),
  },
  'turn.completed': {
    announcement: () => 'Directive completed.',
    react: () => publish({ type: 'synthesis', label: 'SYNTHESIS COMPLETE', detail: 'Turn completed', intensity: 0.9, source: 'mirror' }),
  },
  'turn.failed': {
    announcement: (p) => `Directive failed: ${text(p, 'text', 'reason') || 'see history'}`.slice(0, 160),
    react: ({ payload }) => publish({ type: 'synthesis', label: 'COGNITION FAULT', detail: text(payload, 'text', 'reason') || 'unknown error', intensity: 0.4, source: 'mirror' }),
  },
  'plan.created': {
    announcement: (p) => `Plan created: ${text(p, 'goal') || 'bounded plan'}`.slice(0, 160),
    react: ({ payload }) => publish({ type: 'knowledge-acquired', label: 'PLAN CREATED', detail: text(payload, 'goal').slice(0, 140) || 'New architectural plan', intensity: 0.8, source: 'mirror' }),
  },
  'plan': {
    react: ({ payload }) => {
      const steps = Array.isArray(payload.steps) ? payload.steps : [];
      const escalated = Array.isArray(payload.escalate) ? payload.escalate : [];
      publish({
        type: 'agent-dispatch',
        label: 'TASK PLAN',
        detail: `${steps.length} step(s) · ${escalated.length} awaiting human sign-off${payload.native ? ' · from verified experience' : ''}`,
        intensity: 0.5,
        source: 'mirror',
        data: payload,
      });
    },
  },
  'memory.recalled': {
    react: ({ payload }) => publish({ type: 'knowledge-acquired', label: 'MEMORY RECALLED', detail: text(payload, 'text').slice(0, 140), intensity: 0.6, source: 'mirror' }),
  },
  'memory.trusted_workflow_applied': {
    react: ({ payload }) => publish({ type: 'knowledge-acquired', label: 'TRUSTED WORKFLOW', detail: text(payload, 'workflowId', 'workflow_id').slice(0, 140) || 'applied', intensity: 1, source: 'mirror' }),
  },
  'facts.proposed': {
    announcement: (p) => {
      const count = Number(value(p, 'count') ?? 0);
      return `${count} fact${count === 1 ? '' : 's'} proposed for memory.`;
    },
    react: ({ payload }) => {
      const count = Number(value(payload, 'count') ?? 0);
      publish({ type: 'knowledge-acquired', label: 'FACTS PROPOSED', detail: `${count} candidate fact(s)`, intensity: 0.5, source: 'mirror' });
    },
  },
  'memory.promoted': {
    announcement: () => 'Verified memory promoted with provenance.',
    react: ({ payload }) => publish({ type: 'knowledge-acquired', label: 'MEMORY PROMOTED', detail: text(payload, 'recordId', 'record_id', 'memoryType') || 'verified memory', intensity: 0.8, source: 'mirror' }),
  },
  'telemetry.agent_started': {
    announcement: () => 'Measured system telemetry updated.',
    react: () => publish({ type: 'agent-dispatch', label: 'TELEMETRY UPDATE', detail: 'Measured health state changed', intensity: 0.4, source: 'mirror' }),
  },
  'human_required': {
    requiredFields: ['text'],
    announcement: (p) => text(p, 'text').slice(0, 160) || 'Operator approval required.',
    react: ({ payload }) => publish({ type: 'approval-required', label: 'OPERATOR APPROVAL REQUIRED', detail: text(payload, 'text').slice(0, 160) || 'The supervised mind is waiting for its human.', intensity: 1, source: 'mirror' }),
  },
  'approval.required': {
    announcement: () => 'Operator approval required.',
    react: ({ payload }) => publish({ type: 'approval-required', label: 'OPERATOR APPROVAL REQUIRED', detail: text(payload, 'summary', 'text') || 'Review the exact capability request.', intensity: 1, source: 'mirror', data: payload }),
  },
  'approval.resolved': {
    announcement: (p) => `Approval ${text(p, 'decision', 'status') || 'resolved'}.`,
    react: ({ payload }) => publish({ type: 'approval-resolved', label: 'APPROVAL RESOLVED', detail: text(payload, 'decision', 'status') || 'resolved', intensity: 0.6, source: 'mirror', data: payload }),
  },
  'edit.proposed': {
    announcement: (p) => `Edit proposed: ${text(p, 'path', 'target') || 'review required'}`.slice(0, 160),
    react: ({ payload }) => publish({ type: 'approval-required', label: 'EDIT PROPOSED', detail: text(payload, 'path', 'target') || 'a file', intensity: 0.9, source: 'mirror' }),
  },
  'edit.blocked': {
    announcement: (p) => `Edit blocked: ${text(p, 'reason') || 'policy gate'}`.slice(0, 160),
    react: ({ payload }) => publish({ type: 'error', label: 'EDIT BLOCKED', detail: text(payload, 'reason') || 'gate intervention', intensity: 1, source: 'mirror' }),
  },
  'worker.requested': {
    announcement: (p) => `Worker requested: ${text(p, 'workerId', 'worker_id')}`.slice(0, 160),
    react: ({ payload }) => publish({ type: 'agent-dispatch', label: 'WORKER REQUESTED', detail: text(payload, 'reason') || 'awaiting admission', intensity: 0.3, source: 'mirror' }),
  },
  'worker.admitted': {
    announcement: (p) => `Worker admitted: ${text(p, 'workerId', 'worker_id')}`.slice(0, 160),
    react: ({ payload }) => publish({ type: 'agent-dispatch', label: 'WORKER ADMITTED', detail: text(payload, 'strategy') || 'scheduler admission', intensity: 0.5, source: 'mirror' }),
  },
  'worker.started': {
    requiredFields: ['workerId'],
    announcement: (p) => `Worker started: ${text(p, 'role', 'workerId')}`.slice(0, 160),
    react: ({ payload }) => publish({ type: 'agent-dispatch', label: text(payload, 'role').toUpperCase() || 'WORKER STARTED', detail: text(payload, 'workerId', 'worker_id') || 'temporary worker', intensity: 0.8, source: 'mirror' }),
  },
  'worker.awaiting_capability': {
    announcement: (p) => `Worker paused for capability: ${text(p, 'reason') || 'awaiting authority'}`.slice(0, 160),
    react: ({ payload }) => publish({ type: 'approval-required', label: 'WORKER AWAITING CAPABILITY', detail: text(payload, 'reason') || 'a capability grant is required to continue', intensity: 0.9, source: 'mirror' }),
  },
  'worker.failed': {
    announcement: (p) => `Worker failed: ${text(p, 'reason') || 'see history'}`.slice(0, 160),
    react: ({ payload }) => publish({ type: 'error', label: 'WORKER FAILED', detail: text(payload, 'reason') || text(payload, 'workerId', 'worker_id'), intensity: 0.95, source: 'mirror' }),
  },
  'worker.killed': {
    announcement: (p) => `Worker killed: ${text(p, 'reason') || 'cancelled'}`.slice(0, 160),
    react: ({ payload }) => publish({ type: 'error', label: 'WORKER KILLED', detail: text(payload, 'reason') || text(payload, 'workerId', 'worker_id'), intensity: 0.7, source: 'mirror' }),
  },
  'worker.completed': {
    announcement: (p) => `Worker completed: ${text(p, 'role', 'workerId')}`.slice(0, 160),
    react: ({ payload }) => publish({ type: 'synthesis', label: text(payload, 'role').toUpperCase() || 'WORKER COMPLETED', detail: text(payload, 'workerId', 'worker_id') || 'temporary worker', intensity: 0.8, source: 'mirror' }),
  },
  'worker.dissolved': {
    announcement: (p) => `Worker dissolved: ${text(p, 'role', 'workerId')}`.slice(0, 160),
    react: ({ payload }) => publish({ type: 'synthesis', label: text(payload, 'role').toUpperCase() || 'WORKER DISSOLVED', detail: text(payload, 'workerId', 'worker_id') || 'temporary worker', intensity: 0.3, source: 'mirror' }),
  },
  'mission.running': {
    announcement: (p) => `Mission running: ${text(p, 'missionId', 'mission_id') || 'active mission'}`,
    react: ({ payload }) => publish({ type: 'agent-dispatch', label: 'MISSION RUNNING', detail: text(payload, 'missionId', 'mission_id'), intensity: 0.7, source: 'mirror' }),
  },
  'mission.completed': {
    announcement: (p) => `Mission completed: ${text(p, 'missionId', 'mission_id') || 'mission'}`,
    react: ({ payload }) => publish({ type: 'synthesis', label: 'MISSION COMPLETED', detail: text(payload, 'missionId', 'mission_id'), intensity: 0.85, source: 'mirror' }),
  },
  'mission.failed': {
    announcement: (p) => `Mission failed: ${text(p, 'missionId', 'mission_id') || 'mission'}`,
    react: ({ payload }) => publish({ type: 'error', label: 'MISSION FAILED', detail: text(payload, 'missionId', 'mission_id'), intensity: 0.95, source: 'mirror' }),
  },
  'model.selected': {
    announcement: (p) => `Intelligence selected: ${text(p, 'model', 'model_id') || 'unavailable'}`,
    react: ({ payload }) => publish({ type: 'route', label: 'ACTIVE BRAIN', detail: `${text(payload, 'provider') || '?'}:${text(payload, 'model', 'model_id') || '?'} (${text(payload, 'privacy', 'data_classification') || '?'})`, intensity: 0.3, source: 'mirror', data: payload }),
  },
  'route': {
    announcement: (p) => `Intelligence route: ${text(p, 'provider') || '?'}:${text(p, 'model') || '?'}`,
    react: ({ payload }) => publish({ type: 'route', label: 'ACTIVE BRAIN', detail: `${text(payload, 'provider') || '?'}:${text(payload, 'model') || '?'} (${text(payload, 'privacy') || '?'})`, intensity: 0.3, source: 'mirror', data: payload }),
  },
  // The real canonical name (aios.core.events.CanonicalEventType.ROUTE_SELECTED)
  // -- aios/api/main.py's _sse() bridge always translates the raw "route" SSE
  // frame to "route.selected" before Cortex-bus publication, so this is the
  // one that actually reaches this registry via aiosMirror.ts; 'route' and
  // 'model.selected' above are unreachable through that pipeline today.
  'route.selected': {
    announcement: (p) => `Intelligence route: ${text(p, 'provider') || '?'}:${text(p, 'model') || '?'}`,
    react: ({ payload }) => publish({ type: 'route', label: 'ACTIVE BRAIN', detail: `${text(payload, 'provider') || '?'}:${text(payload, 'model') || '?'} (${text(payload, 'privacy') || '?'})`, intensity: 0.3, source: 'mirror', data: payload }),
  },
  'verify_result': {
    requiredFields: ['verdict'],
    announcement: (p) => `Verification ${text(p, 'verdict')}.`,
    react: ({ payload }) => {
      const verdict = text(payload, 'verdict').toLowerCase();
      publish({ type: 'verify', label: verdict === 'pass' ? 'VERIFY PASS' : 'VERIFY FAIL', detail: text(payload, 'target'), intensity: verdict === 'pass' ? 0.75 : 0.95, source: 'mirror', data: payload });
    },
  },
  'verification.passed': {
    announcement: () => 'Verification passed; evidence is available.',
    react: ({ payload }) => publish({ type: 'verify', label: 'VERIFY PASS', detail: text(payload, 'target'), intensity: 0.75, source: 'mirror', data: payload }),
  },
  'verification.failed': {
    announcement: () => 'Verification failed; promotion is guarded.',
    react: ({ payload }) => publish({ type: 'verify', label: 'VERIFY FAIL', detail: text(payload, 'target'), intensity: 0.95, source: 'mirror', data: payload }),
  },
  'earned_autonomy': {
    announcement: () => 'A previously verified action class was reused.',
    react: ({ payload }) => publish({ type: 'knowledge-acquired', label: 'AUTONOMOUS ACTION', detail: `earned trust applied · ${text(payload, 'command', 'filepath') || 'a write'}`.slice(0, 140), intensity: 1, source: 'mirror' }),
  },
  'swarm_plan': {
    react: ({ payload }) => startSwarmPlan(Array.isArray(payload.plan) ? payload.plan.map(String) : []),
  },
  'caste_start': {
    react: ({ payload }) => startSwarmCaste(text(payload, 'caste')),
  },
  'caste_end': {
    react: ({ payload }) => endSwarmCaste(text(payload, 'caste')),
  },
  'cloud_route': {
    react: ({ payload }) => {
      const index = Number(value(payload, 'subtask_index', 'subtaskIndex') ?? -1);
      if (index >= 0) markSwarmCloudSubtask(index);
    },
  },
  'step': {
    react: ({ payload }) => {
      const kind = text(payload, 'type');
      const tool = text(payload, 'tool');
      const rawOutput = text(payload, 'output');
      const output = humanizeRedactionMarkers(rawOutput);
      if (kind === 'tool_call') publish({ type: 'agent-dispatch', label: tool.toUpperCase(), detail: `tool engaged: ${tool}`, intensity: 0.8, source: 'mirror' });
      else if (kind === 'tool_blocked') publish({ type: 'agent-dispatch', label: `${tool.toUpperCase()} BLOCKED`, detail: humanizeRedactionMarkers(text(payload, 'reason')).slice(0, 140), intensity: 0.4, source: 'mirror' });
      else if (kind === 'tool_result' && (rawOutput.startsWith('[VERIFY PASS]') || rawOutput.startsWith('[VERIFY FAIL]'))) publish({ type: 'knowledge-acquired', label: rawOutput.startsWith('[VERIFY PASS]') ? 'VERIFICATION GREEN' : 'VERIFICATION RED', detail: output.slice(0, 140), intensity: 1, source: 'mirror' });
      else if (kind === 'tool_result' && (tool === 'swarm' || tool === 'role_pass')) publish({ type: 'agent-dispatch', label: tool === 'swarm' ? 'SWARM' : 'ROLE-PASS', detail: text(payload, 'role').replace(/-/g, ' ').toUpperCase() || output.slice(0, 80), intensity: 0.5, source: 'mirror' });
      else if (kind === 'tool_result') publish({ type: 'knowledge-acquired', label: tool.toUpperCase() || 'SIGNAL', detail: output.slice(0, 140), intensity: 0.6, source: 'mirror' });
    },
  },
  'code': {
    announcement: (p) => `Code emitted: ${text(p, 'language') || 'text'}.`,
    react: ({ payload }) => publish({ type: 'knowledge-acquired', label: 'CODE EMITTED', detail: `${text(payload, 'language') || 'text'} · ${text(payload, 'code').split('\n').length} line(s)`, intensity: 0.7, source: 'mirror' }),
  },
  'alignment': {
    react: ({ payload }) => {
      const intent = text(payload, 'intent');
      if (intent) publish({ type: 'agent-dispatch', label: `INTENT ${intent.toUpperCase()}`, detail: typeof payload.confidence === 'number' ? `declared understanding · ${(Number(payload.confidence) * 100).toFixed(0)}%` : 'declared understanding', intensity: 0.3, source: 'mirror' });
    },
  },
  'snapshot_required': {
    operational: false,
    announcement: () => 'Mirror replay paused; a fresh snapshot is required.',
    react: () => publish({ type: 'error', label: 'MIRROR SNAPSHOT REQUIRED', detail: 'Reconnect to measured state', intensity: 0.8, source: 'mirror' }),
  },
  'audit.integrity_failed': {
    announcement: () => 'Audit integrity failure requires operator attention.',
    react: ({ payload }) => publish({ type: 'error', label: 'AUDIT INTEGRITY FAILURE', detail: text(payload, 'reason') || 'audit chain is not verified', intensity: 1, source: 'mirror', data: payload }),
  },
};

export function registeredMirrorEventTypes(): string[] {
  return Object.keys(core).sort();
}

export function dispatchLivingMirrorEvent(event: MirrorEventEnvelope): boolean {
  const spec = core[event.eventType];
  if (!spec) {
    // Unknown events are observations from a future/backend extension. They
    // never become frontend authority or animation.
    console.debug(`[living-mirror] ignored unknown event: ${event.eventType}`);
    return false;
  }

  const schemaVersion = event.canonical.schemaVersion ?? event.canonical.schema_version;
  if (schemaVersion !== undefined && schemaVersion !== '1' && schemaVersion !== '1.0') {
    useMirrorStore.getState().setAnnouncement(`Unsupported event schema: ${String(schemaVersion)}`);
    return true;
  }
  if (!required(spec.requiredFields, event.payload)) {
    useMirrorStore.getState().setAnnouncement('Incomplete backend event ignored.');
    return true;
  }
  useMirrorStore.getState().applyEvent(event.id, event.eventType, event.canonical);
  if (spec.announcement) useMirrorStore.getState().setAnnouncement(spec.announcement(event.payload));
  try {
    spec.react?.(event);
  } catch {
    useMirrorStore.getState().setAnnouncement('Backend event reaction unavailable.');
  }
  return true;
}

export function __resetLivingMirrorRegistryForTests(): void {
  useMirrorStore.getState().setAnnouncement(null);
}
