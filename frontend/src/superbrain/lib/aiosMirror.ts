import { publishCognition } from './cognitionBus';
import { humanizeRedactionMarkers } from './aiosAdapter';
import { useMirrorStore } from './mirrorStore';
import {
  endSwarmCaste,
  markSwarmCloudSubtask,
  startSwarmCaste,
  startSwarmPlan,
} from './swarmHUDStore';

const AIOS_BASE = process.env.NEXT_PUBLIC_AIOS_URL ?? 'http://localhost:8000';

let mirrorEventSource: EventSource | null = null;

export async function startMirrorClient(): Promise<void> {
  if (mirrorEventSource) {
    return; // Already started
  }

  try {
    const res = await fetch(`${AIOS_BASE}/api/v1/mirror/snapshot`);
    if (res.ok) {
      const data = await res.json();
      useMirrorStore.getState().setSnapshot(data);
    }
  } catch (err) {
    console.warn('Failed to fetch mirror snapshot', err);
  }

  const es = new EventSource(`${AIOS_BASE}/api/v1/mirror/stream`);
  mirrorEventSource = es;

  es.onopen = () => {
    useMirrorStore.getState().setStatus('online');
  };

  es.onerror = () => {
    useMirrorStore.getState().setStatus('offline');
  };

  es.onmessage = (event) => {
    if (event.type === 'ping') return;
    
    let canonical;
    try {
      canonical = JSON.parse(event.data);
    } catch {
      return;
    }

    const idStr = event.lastEventId; 
    const id = idStr ? parseInt(idStr, 10) : Date.now();
    const eventType = event.type; 
    const payload = canonical.payload || {};

    useMirrorStore.getState().applyEvent(id, eventType, canonical);

    // Map backend canonical events to frontend visual reactions
    switch (eventType) {
      case 'aios.cognitive_action':
        publishCognition({
          type: 'aios.cognitive_action',
          spine_id: canonical.spine_id,
          label: humanizeRedactionMarkers(payload.label),
          body: humanizeRedactionMarkers(payload.body),
          redacted: payload.redacted,
        });
        break;
      case 'aios.message':
        publishCognition({
          type: 'message',
          spine_id: canonical.spine_id,
          label: humanizeRedactionMarkers(payload.label),
          body: humanizeRedactionMarkers(payload.body),
          role: payload.role,
          speaker: payload.speaker,
          metadata: payload.metadata,
        });
        break;
      case 'aios.error':
        publishCognition({
          type: 'error',
          spine_id: canonical.spine_id,
          label: humanizeRedactionMarkers(payload.label),
          body: humanizeRedactionMarkers(payload.body),
          code: payload.code,
          recoverable: payload.recoverable,
        });
        break;
      
      case 'aios.intent':
        publishCognition({
          type: 'aios.intent',
          spine_id: canonical.spine_id,
          label: humanizeRedactionMarkers(payload.label),
          body: humanizeRedactionMarkers(payload.body),
        });
        break;
        
      case 'turn.started':
        publishCognition({
          type: 'knowledge-acquired',
          label: 'TURN STARTED',
          detail: 'Superbrain active',
          intensity: 0.5,
          source: 'mirror',
        });
        break;
      case 'turn.completed':
        publishCognition({
          type: 'synthesis',
          label: 'SYNTHESIS COMPLETE',
          detail: 'Turn completed',
          intensity: 0.9,
          source: 'mirror',
        });
        break;
      case 'plan.created':
        publishCognition({
          type: 'knowledge-acquired',
          label: 'PLAN CREATED',
          detail: canonical.goal ? canonical.goal.slice(0, 140) : 'New architectural plan',
          intensity: 0.8,
          source: 'mirror',
        });
        break;
      case 'worker.started':
        publishCognition({
          type: 'agent-dispatch',
          label: payload.role ? payload.role.toUpperCase() : 'WORKER',
          detail: 'Worker online',
          intensity: 0.7,
          source: 'mirror',
        });
        break;
      case 'worker.dissolved':
        publishCognition({
          type: 'agent-dispatch',
          label: payload.role ? payload.role.toUpperCase() : 'WORKER',
          detail: 'Worker dissolved',
          intensity: 0.3,
          source: 'mirror',
        });
        break;
        
      // Maps from the original aiosAdapter.ts responses
      case 'step': {
        const kind = String(payload.type ?? '');
        const tool = String(payload.tool ?? '');
        const rawOutput = String(payload.output ?? '');
        const output = humanizeRedactionMarkers(rawOutput); // could humanize later
        
        if (kind === 'tool_call') {
          publishCognition({
            type: 'agent-dispatch',
            label: tool.toUpperCase(),
            detail: `tool engaged: ${tool}`,
            intensity: 0.8,
            source: 'mirror',
          });
        } else if (kind === 'tool_blocked') {
          publishCognition({
            type: 'agent-dispatch',
            label: `${tool.toUpperCase()} BLOCKED`,
            detail: humanizeRedactionMarkers(payload.reason ?? '').slice(0, 140),
            intensity: 0.4,
            source: 'mirror',
          });
        } else if (kind === 'tool_result') {
          if (rawOutput.startsWith('[VERIFY PASS]') || rawOutput.startsWith('[VERIFY FAIL]')) {
            publishCognition({
              type: 'knowledge-acquired',
              label: rawOutput.startsWith('[VERIFY PASS]') ? 'VERIFICATION GREEN' : 'VERIFICATION RED',
              detail: output.slice(0, 140),
              intensity: 1,
              source: 'mirror',
            });
          } else if (tool === 'swarm' || tool === 'role_pass') {
            const role = String(payload.role ?? '').replace(/-/g, ' ').toUpperCase();
            publishCognition({
              type: 'agent-dispatch',
              label: tool === 'swarm' ? 'SWARM' : 'ROLE-PASS',
              detail: role ? `${role} caste online` : output.slice(0, 80),
              intensity: 0.5,
              source: 'mirror',
            });
          } else {
            publishCognition({
              type: 'knowledge-acquired',
              label: tool ? tool.toUpperCase() : 'SIGNAL',
              detail: output.slice(0, 140),
              intensity: 0.6,
              source: 'mirror',
            });
          }
        }
        break;
      }
      case 'human_required':
        publishCognition({
          type: 'approval-required',
          label: 'OPERATOR APPROVAL REQUIRED',
          detail: String(payload.text ?? 'The supervised mind is waiting for its human.').slice(0, 160),
          intensity: 1,
          source: 'mirror',
        });
        break;
      case 'code':
        publishCognition({
          type: 'knowledge-acquired',
          label: 'CODE EMITTED',
          detail: `${payload.language ?? 'text'} · ${String(payload.code ?? '').split('\n').length} line(s)`,
          intensity: 0.7,
          source: 'mirror',
        });
        break;
      case 'alignment': {
        const intent = String(payload.intent ?? '');
        const confidence = payload.confidence;
        if (intent) {
          publishCognition({
            type: 'agent-dispatch',
            label: `INTENT ${intent.toUpperCase()}`,
            detail: typeof confidence === 'number' ? `declared understanding · confidence ${(confidence * 100).toFixed(0)}%` : 'declared understanding',
            intensity: 0.3,
            source: 'mirror',
          });
        }
        break;
      }
      case 'earned_autonomy': {
        const what = String(payload.command ?? payload.filepath ?? 'a write');
        publishCognition({
          type: 'knowledge-acquired',
          label: 'AUTONOMOUS ACTION',
          detail: `earned trust applied · ${what}`.slice(0, 140),
          intensity: 1,
          source: 'mirror',
        });
        break;
      }
      case 'plan': {
        const planSteps = Array.isArray(payload.steps) ? payload.steps : [];
        const escalated = Array.isArray(payload.escalate) ? payload.escalate : [];
        publishCognition({
          type: 'agent-dispatch',
          label: 'TASK PLAN',
          detail:
            `${planSteps.length} step(s) · ${escalated.length} awaiting human sign-off` +
            (payload.native ? ' · from verified experience' : ''),
          intensity: 0.5,
          source: 'mirror',
          data: payload,
        });
        break;
      }
      case 'swarm_plan': {
        const plan = Array.isArray(payload.plan) ? (payload.plan as string[]) : [];
        startSwarmPlan(plan);
        break;
      }
      case 'caste_start':
        startSwarmCaste(String(payload.caste ?? ''));
        break;
      case 'caste_end':
        endSwarmCaste(String(payload.caste ?? ''));
        break;
      case 'cloud_route': {
        const idx = Number(payload.subtask_index ?? -1);
        if (idx >= 0) markSwarmCloudSubtask(idx);
        break;
      }
      case 'verify_result': {
        const verdict = String(payload.verdict ?? '').toLowerCase();
        publishCognition({
          type: 'verify',
          label: verdict === 'pass' ? 'VERIFY PASS' : 'VERIFY FAIL',
          detail: String(payload.target ?? ''),
          intensity: verdict === 'pass' ? 0.75 : 0.95,
          source: 'mirror',
          data: payload,
        });
        break;
      }
      case 'turn.failed':
      case 'error':
        publishCognition({
          type: 'synthesis',
          label: 'COGNITION FAULT',
          detail: String(payload.text ?? 'unknown error').slice(0, 140),
          intensity: 0.4,
          source: 'mirror',
        });
        break;
      case 'route':
        publishCognition({
          type: 'route',
          label: 'ACTIVE BRAIN',
          detail: `${String(payload.provider ?? '?')}:${String(payload.model ?? '?')} (${String(payload.privacy ?? '?')})`,
          intensity: 0.3,
          source: 'mirror',
          data: payload,
        });
        break;
    }
  };
}

export function stopMirrorClient(): void {
  if (mirrorEventSource) {
    mirrorEventSource.close();
    mirrorEventSource = null;
    useMirrorStore.getState().setStatus('offline');
  }
}
