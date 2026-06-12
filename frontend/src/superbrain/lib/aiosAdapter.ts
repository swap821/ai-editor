/**
 * aiosAdapter — binds the superbrain's nervous system to the REAL AI-OS.
 *
 * Everything the demo used to fake now has a true source:
 *   - the command bar streams a real supervised turn (POST /api/generate,
 *     SSE) and every frame becomes a cognition event — tool calls dispatch
 *     agents, verifier verdicts light the cortex, a human_required pause
 *     publishes 'approval-required' (the organism holds its breath);
 *   - the pheromone map (GET /api/v1/development/trails) and development
 *     metrics feed the HUD's intake channels and fire 'knowledge-acquired'
 *     when a real trail is genuinely reinforced.
 *
 * Fault-isolated by design: if the backend is unreachable the adapter says
 * so honestly on the bus and the demo's idle imagination carries on. No
 * listener, poller, or stream error can break the render loop.
 */

import { publishCognition } from './cognitionBus';
import { setMetricBases } from './metricsStore';

export const AIOS_BASE =
  process.env.NEXT_PUBLIC_AIOS_URL ?? 'http://127.0.0.1:8000';

const SESSION_ID = 'gag-superbrain-hud';

// ---------------------------------------------------------------- directives

export interface DirectiveResult {
  /** The stream completed (done frame) or paused for approval. */
  ok: boolean;
  /** The turn paused on a human_required frame — approval is pending. */
  paused: boolean;
  /** Final synthesized answer text (possibly empty when paused/offline). */
  answer: string;
}

interface SseFrame {
  event: string;
  data: Record<string, unknown>;
}

async function* readSse(body: ReadableStream<Uint8Array>): AsyncGenerator<SseFrame> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let event = '';
  let dataLines: string[] = [];
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let newline = buffer.indexOf('\n');
    while (newline >= 0) {
      const line = buffer.slice(0, newline).replace(/\r$/, '');
      buffer = buffer.slice(newline + 1);
      newline = buffer.indexOf('\n');
      if (line === '') {
        if (event) {
          let data: Record<string, unknown> = {};
          try {
            data = JSON.parse(dataLines.join('\n') || '{}');
          } catch {
            // Malformed frame: surface nothing rather than break the stream.
          }
          yield { event, data };
        }
        event = '';
        dataLines = [];
      } else if (line.startsWith('event:')) {
        event = line.slice('event:'.length).trim();
      } else if (line.startsWith('data:')) {
        dataLines.push(line.slice('data:'.length).trim());
      }
    }
  }
}

function publishStep(data: Record<string, unknown>): void {
  const kind = String(data.type ?? '');
  const tool = String(data.tool ?? '');
  const output = String(data.output ?? '');
  if (kind === 'tool_call') {
    publishCognition({
      type: 'agent-dispatch',
      label: tool.toUpperCase(),
      detail: `tool engaged: ${tool}`,
      intensity: 0.8,
      source: 'aios',
    });
    return;
  }
  if (kind === 'tool_blocked') {
    publishCognition({
      type: 'agent-dispatch',
      label: `${tool.toUpperCase()} BLOCKED`,
      detail: String(data.reason ?? '').slice(0, 140),
      intensity: 0.4,
      source: 'aios',
    });
    return;
  }
  if (kind !== 'tool_result') return;
  if (output.startsWith('[VERIFY PASS]') || output.startsWith('[VERIFY FAIL]')) {
    publishCognition({
      type: 'knowledge-acquired',
      label: output.startsWith('[VERIFY PASS]') ? 'VERIFICATION GREEN' : 'VERIFICATION RED',
      detail: output.slice(0, 140),
      intensity: 1,
      source: 'aios',
    });
    return;
  }
  publishCognition({
    type: 'knowledge-acquired',
    label: tool ? tool.toUpperCase() : 'SIGNAL',
    detail: output.slice(0, 140),
    intensity: 0.6,
    source: 'aios',
  });
}

/** A pause the operator must resolve: the server-issued capability plus
 *  everything needed to judge it (the diff IS the decision surface). */
export interface PendingApproval {
  token: string;
  /** The directive whose replay redeems the token. */
  prompt: string;
  /** Plain-language ask, e.g. "Approval required to create x.py". */
  summary: string;
  explanation: string;
  /** Unified diff for writes; empty for command approvals. */
  diff: string;
  /** The exact command, when the ask is a command. */
  command: string;
}

let pendingApproval: PendingApproval | null = null;

/** The approval currently awaiting the operator (null when none). */
export function getPendingApproval(): PendingApproval | null {
  return pendingApproval;
}

function captureApproval(text: string, data: Record<string, unknown>): void {
  const input = (data.input ?? {}) as Record<string, unknown>;
  const commands = Array.isArray(input.commands) ? input.commands : [];
  pendingApproval = {
    token: String(input.approvalToken ?? ''),
    prompt: text,
    summary: String(data.text ?? 'Approval required'),
    explanation: String(input.explanation ?? ''),
    diff: String(input.diff ?? ''),
    command: commands.length > 0 ? String(commands[0]) : '',
  };
}

async function streamTurn(text: string, tokens: string[]): Promise<DirectiveResult> {
  let answer = '';
  let paused = false;
  try {
    const response = await fetch(`${AIOS_BASE}/api/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        messages: [{ role: 'user', content: [{ text }] }],
        modelId: 'auto',
        sessionId: SESSION_ID,
        approvalTokens: tokens,
      }),
    });
    if (!response.ok || !response.body) {
      throw new Error(`backend responded ${response.status}`);
    }
    for await (const frame of readSse(response.body)) {
      switch (frame.event) {
        case 'step':
          publishStep(frame.data);
          break;
        case 'text_chunk':
          answer += String(frame.data.text ?? '');
          break;
        case 'human_required':
          paused = true;
          captureApproval(text, frame.data);
          publishCognition({
            type: 'approval-required',
            label: 'OPERATOR APPROVAL REQUIRED',
            detail: String(frame.data.text ?? 'The supervised mind is waiting for its human.').slice(0, 160),
            intensity: 1,
            source: 'aios',
          });
          break;
        case 'error':
          publishCognition({
            type: 'synthesis',
            label: 'COGNITION FAULT',
            detail: String(frame.data.text ?? 'unknown error').slice(0, 140),
            intensity: 0.4,
            source: 'aios',
          });
          break;
        case 'done':
          if (!paused) {
            publishCognition({
              type: 'synthesis',
              label: 'SYNTHESIS COMPLETE',
              detail: answer.trim().slice(0, 160) || 'turn complete',
              intensity: 0.9,
              source: 'aios',
            });
          }
          break;
        default:
          break; // alignment and future frames are advisory to the scene
      }
    }
    return { ok: true, paused, answer };
  } catch {
    publishCognition({
      type: 'synthesis',
      label: 'LINK OFFLINE',
      detail: 'AI-OS backend unreachable — directive handled by imagination only.',
      intensity: 0.3,
      source: 'aios',
    });
    return { ok: false, paused: false, answer };
  }
}

/** Stream one REAL supervised turn through the AI-OS and narrate it on the bus. */
export async function sendDirective(text: string): Promise<DirectiveResult> {
  pendingApproval = null;
  return streamTurn(text, []);
}

/** The operator authorizes: redeem the capability by replaying the turn with
 *  the server-issued token. The replay may pause again on the NEXT caution
 *  action — a fresh PendingApproval is captured and the panel continues. */
export async function approvePendingApproval(): Promise<DirectiveResult> {
  const pending = pendingApproval;
  if (!pending?.token) return { ok: false, paused: false, answer: '' };
  pendingApproval = null;
  publishCognition({
    type: 'approval-resolved',
    label: 'approved',
    detail: pending.summary.slice(0, 140),
    intensity: 0.9,
    source: 'operator',
  });
  return streamTurn(pending.prompt, [pending.token]);
}

/** The operator declines: the rejection is recorded through the real
 *  endpoint (audited server-side) and the organism stands down. */
export async function rejectPendingApproval(): Promise<void> {
  const pending = pendingApproval;
  if (!pending?.token) return;
  pendingApproval = null;
  try {
    await fetch(`${AIOS_BASE}/api/v1/approval/req`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        approvalToken: pending.token,
        sessionId: SESSION_ID,
        approve: false,
      }),
    });
  } catch {
    // The token simply expires unredeemed; the visual still stands down.
  }
  publishCognition({
    type: 'approval-resolved',
    label: 'rejected',
    detail: pending.summary.slice(0, 140),
    intensity: 0.5,
    source: 'operator',
  });
}

// -------------------------------------------------------- trails + metrics

export interface TrailRow {
  skill_id: number;
  goal_pattern: string;
  status: string;
  quarantined: boolean;
  success_count: number;
  reuse_success_count: number;
  strength: number;
  freshness: number;
}

export function trailLabel(goal: string): string {
  return goal.replace(/\s+/g, ' ').trim().slice(0, 48).toUpperCase();
}

const seenTrailTotals = new Map<number, number>();
let linkUp = false;
/** The live pheromone map as of the last successful poll (empty offline). */
let knownTrails: TrailRow[] = [];

/** The brain's actual trail field — what the grasp system may recall. */
export function getKnownTrails(): readonly TrailRow[] {
  return knownTrails;
}

/** Test seam: clear the module's poll memory between test cases. */
export function __resetAiosAdapterForTests(): void {
  seenTrailTotals.clear();
  linkUp = false;
  knownTrails = [];
  pendingApproval = null;
}

/** One trails+metrics poll. Exported for tests; production runs it through
 *  {@link startAiosPolling}. */
export async function pollOnce(): Promise<void> {
  try {
    const [trailsRes, metricsRes] = await Promise.all([
      fetch(`${AIOS_BASE}/api/v1/development/trails`),
      fetch(`${AIOS_BASE}/api/v1/development/metrics`),
    ]);
    if (!trailsRes.ok || !metricsRes.ok) throw new Error('bad status');
    const trailMap = (await trailsRes.json()) as { trails: TrailRow[] };
    const metrics = (await metricsRes.json()) as Record<string, number>;

    if (!linkUp) {
      linkUp = true;
      publishCognition({
        type: 'synthesis',
        label: 'AI-OS LINK ESTABLISHED',
        detail: `live cognition: ${trailMap.trails.length} trail(s) on the pheromone map`,
        intensity: 0.7,
        source: 'aios',
      });
    }

    const trails = trailMap.trails ?? [];
    knownTrails = trails;
    const verified = trails.filter((t) => t.status === 'verified');
    const avg = (rows: TrailRow[], pick: (t: TrailRow) => number) =>
      rows.length ? rows.reduce((sum, t) => sum + pick(t), 0) / rows.length : NaN;
    setMetricBases({
      research: (metrics.verified_success_rate ?? NaN) * 100,
      tools: (metrics.verification_coverage ?? NaN) * 100,
      memory: avg(verified, (t) => t.strength) * 100,
      signals: avg(trails, (t) => t.freshness) * 100,
    });

    for (const trail of trails) {
      const total = trail.success_count + trail.reuse_success_count;
      const previous = seenTrailTotals.get(trail.skill_id);
      if (previous !== undefined && total > previous) {
        publishCognition({
          type: 'knowledge-acquired',
          label: trailLabel(trail.goal_pattern),
          detail: `trail #${trail.skill_id} reinforced — strength ${trail.strength.toFixed(3)}`,
          intensity: Math.max(0.4, Math.min(1, trail.strength)),
          source: 'aios',
        });
      }
      seenTrailTotals.set(trail.skill_id, total);
    }
  } catch {
    if (linkUp) {
      linkUp = false;
      publishCognition({
        type: 'synthesis',
        label: 'AI-OS LINK LOST',
        detail: 'pheromone map unreachable — cognition running on imagination.',
        intensity: 0.3,
        source: 'aios',
      });
    }
  }
}

/** Start the trails/metrics poll. Returns a stop function. */
export function startAiosPolling(intervalMs = 20_000): () => void {
  if (typeof window === 'undefined') return () => undefined;
  void pollOnce();
  const handle = window.setInterval(() => void pollOnce(), intervalMs);
  return () => window.clearInterval(handle);
}
