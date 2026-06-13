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
import { setMetricBases, setMetricLink } from './metricsStore';

export const AIOS_BASE =
  process.env.NEXT_PUBLIC_AIOS_URL ?? 'http://127.0.0.1:8000';

// Bearer token (optional). Read from the Next-style env in the lab; the product
// (Vite) build injects the same name via vite.config `define` from
// VITE_AIOS_API_TOKEN. Empty by default (loopback dev) — only sent when set, so
// a token-protected / non-loopback backend no longer 401s the default UI.
const AIOS_TOKEN = process.env.NEXT_PUBLIC_AIOS_TOKEN ?? '';

function authHeaders(): Record<string, string> {
  return AIOS_TOKEN ? { Authorization: `Bearer ${AIOS_TOKEN}` } : {};
}

// One session per operator, SHARED with the classic UI (same localStorage key)
// so both faces of the AI-OS continue the SAME conversation. SSR-safe; falls
// back to the original constant when storage is unavailable.
const SESSION_ID: string = (() => {
  if (typeof window === 'undefined') return 'gag-superbrain-hud';
  try {
    const KEY = 'aios_session_id';
    const existing = window.localStorage.getItem(KEY);
    if (existing) return existing;
    const created =
      typeof window.crypto?.randomUUID === 'function'
        ? window.crypto.randomUUID()
        : `sb-${Date.now().toString(36)}`;
    window.localStorage.setItem(KEY, created);
    return created;
  } catch {
    return 'gag-superbrain-hud';
  }
})();

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
  if (tool === 'swarm' || tool === 'role_pass') {
    // Orchestration castes: narrate the mesh forming so a swarm / role-pass turn
    // reads as the decompose -> workers -> synthesize flow it actually is, rather
    // than a generic tool ping.
    const role = String(data.role ?? '').replace(/-/g, ' ').toUpperCase();
    publishCognition({
      type: 'agent-dispatch',
      label: tool === 'swarm' ? 'SWARM' : 'ROLE-PASS',
      detail: role ? `${role} caste online` : output.slice(0, 80),
      intensity: 0.5,
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
  /** What kind of action is being authorized. */
  kind: 'create' | 'edit' | 'command' | 'other';
  /** Target file for write approvals (empty for commands). */
  filepath: string;
}

let pendingApproval: PendingApproval | null = null;

/** The approval currently awaiting the operator (null when none). */
export function getPendingApproval(): PendingApproval | null {
  return pendingApproval;
}

function captureApproval(text: string, data: Record<string, unknown>): void {
  const input = (data.input ?? {}) as Record<string, unknown>;
  const commands = Array.isArray(input.commands) ? input.commands : [];
  // The backend names the exact target: creations carry {filepath, content},
  // edits carry the structured edit triple. Surface it so the panel can
  // title the decision precisely.
  const creations = Array.isArray(input.creations) ? input.creations : [];
  const edits = Array.isArray(input.edits) ? input.edits : [];
  const firstPath = (rows: unknown[]): string => {
    const head = (rows[0] ?? {}) as Record<string, unknown>;
    return String(head.filepath ?? head.path ?? '');
  };
  const kind: PendingApproval['kind'] =
    creations.length > 0 ? 'create' : edits.length > 0 ? 'edit' : commands.length > 0 ? 'command' : 'other';
  pendingApproval = {
    token: String(input.approvalToken ?? ''),
    prompt: text,
    summary: String(data.text ?? 'Approval required'),
    explanation: String(input.explanation ?? ''),
    diff: String(input.diff ?? ''),
    command: commands.length > 0 ? String(commands[0]) : '',
    kind,
    filepath: kind === 'create' ? firstPath(creations) : kind === 'edit' ? firstPath(edits) : '',
  };
}

async function streamTurn(text: string, tokens: string[]): Promise<DirectiveResult> {
  let answer = '';
  let paused = false;
  try {
    const response = await fetch(`${AIOS_BASE}/api/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
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
        case 'code': {
          // Generated code used to vanish into the default branch — at
          // minimum the organism announces the artifact honestly.
          const code = String(frame.data.code ?? '');
          const language = String(frame.data.language ?? 'text');
          publishCognition({
            type: 'knowledge-acquired',
            label: 'CODE EMITTED',
            detail: `${language} · ${code.split('\n').length} line(s)`,
            intensity: 0.7,
            source: 'aios',
          });
          break;
        }
        case 'alignment': {
          // The mind declares its understanding every turn; show it.
          const intent = String(frame.data.intent ?? '');
          const confidence = frame.data.confidence;
          if (intent) {
            publishCognition({
              type: 'agent-dispatch',
              label: `INTENT ${intent.toUpperCase()}`,
              detail:
                typeof confidence === 'number'
                  ? `declared understanding · confidence ${(confidence * 100).toFixed(0)}%`
                  : 'declared understanding',
              intensity: 0.3,
              source: 'aios',
            });
          }
          break;
        }
        case 'earned_autonomy': {
          // The mind acted on its OWN earned trust: a write whose class earned
          // autonomy by repeated verified success, applied with no human pause
          // (still gated + audited). The rarest, most-grown-up thing it does.
          const what = String(frame.data.command ?? frame.data.filepath ?? 'a write');
          publishCognition({
            type: 'knowledge-acquired',
            label: 'AUTONOMOUS ACTION',
            detail: `earned trust applied · ${what}`.slice(0, 140),
            intensity: 1,
            source: 'aios',
          });
          break;
        }
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
 *  endpoint (audited server-side) and the organism stands down. The bus
 *  only announces 'rejected' when the server CONFIRMED the decision —
 *  an unreachable backend gets the honest 'rejected (unconfirmed)'. */
export async function rejectPendingApproval(): Promise<void> {
  const pending = pendingApproval;
  if (!pending?.token) return;
  pendingApproval = null;
  let confirmed = false;
  try {
    const response = await fetch(`${AIOS_BASE}/api/v1/approval/req`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({
        approvalToken: pending.token,
        sessionId: SESSION_ID,
        approve: false,
      }),
    });
    if (response.ok) {
      const result = (await response.json()) as { decision?: string };
      confirmed = result.decision === 'rejected';
    }
  } catch {
    // The token simply expires unredeemed; the visual still stands down.
  }
  publishCognition({
    type: 'approval-resolved',
    label: confirmed ? 'rejected' : 'rejected (unconfirmed — token will expire)',
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
  failure_count: number;
  reuse_failure_count: number;
  strength: number;
  freshness: number;
}

interface TrailMapResponse {
  trails?: TrailRow[];
  summary?: { verified: number; candidate: number; quarantined: number; superseded: number };
}

/** One successful poll's worth of REAL system truth — everything the HUD
 *  shows about link/latency/trails/metrics flows from this snapshot. */
export interface AiosTelemetry {
  link: boolean;
  latencyMs: number;
  trails: number;
  verified: number;
  candidate: number;
  quarantined: number;
  superseded: number;
  tasks: number;
  lessons: number;
  repeatedMistakes: number;
  blockedActions: number;
  interventionRate: number;
  avgToolCalls: number;
  /** Audit hash-chain status (sampled every few polls): true = intact,
   *  false = TAMPER, null = not yet checked / unavailable. */
  chainValid: boolean | null;
  chainEntries: number;
  /** Earned-autonomy ledger summary (sampled): how many YELLOW action classes
   *  the brain has earned the right to act on WITHOUT a human, by verified
   *  evidence. earned > 0 is the brain's visible "grown-up" capability count. */
  earnedAutonomy: { enabled: boolean; earned: number; probation: number; revoked: number };
}

export function trailLabel(goal: string): string {
  return goal.replace(/\s+/g, ' ').trim().slice(0, 48).toUpperCase();
}

const seenTrailTotals = new Map<number, number>();
const seenTrailFailures = new Map<number, number>();
const seenTrailStatus = new Map<number, string>();
let linkUp = false;
/** The live pheromone map as of the last successful poll (empty offline). */
let knownTrails: TrailRow[] = [];
let lastTelemetry: AiosTelemetry | null = null;
let pollCount = 0;
let chainValid: boolean | null = null;
let chainEntries = 0;

/** Earned-autonomy ledger snapshot: which YELLOW action classes the brain has
 *  earned the right to do without a human, by repeated verified success. */
export interface AutonomySnapshot {
  enabled: boolean;
  min_successes: number;
  entries: Array<{
    signature: string;
    action_type: string;
    target_shape: string;
    status: string;
    success_count: number;
    streak: number;
  }>;
  summary: { earned: number; probation: number; revoked: number };
}
let lastAutonomy: AutonomySnapshot | null = null;
const seenAutonomyStatus = new Map<string, string>();

/** The brain's actual trail field — what the grasp system may recall. */
export function getKnownTrails(): readonly TrailRow[] {
  return knownTrails;
}

/** The earned-autonomy ledger as of the last poll (null offline / older backend). */
export function getAutonomy(): AutonomySnapshot | null {
  return lastAutonomy;
}

/** True while the last poll reached the real backend. */
export function getLinkState(): boolean {
  return linkUp;
}

/** The most recent telemetry snapshot (null before the first successful poll). */
export function getLastTelemetry(): AiosTelemetry | null {
  return lastTelemetry;
}

/** Test seam: clear the module's poll memory between test cases. */
export function __resetAiosAdapterForTests(): void {
  seenTrailTotals.clear();
  seenTrailFailures.clear();
  seenTrailStatus.clear();
  linkUp = false;
  knownTrails = [];
  pendingApproval = null;
  lastTelemetry = null;
  pollCount = 0;
  chainValid = null;
  chainEntries = 0;
  lastAutonomy = null;
  seenAutonomyStatus.clear();
}

/** Audit hash-chain probe — sampled every few polls (it walks the ledger). */
const CHAIN_PROBE_EVERY = 5;

/** One trails+metrics poll. Exported for tests; production runs it through
 *  {@link startAiosPolling}. */
export async function pollOnce(): Promise<void> {
  try {
    const startedAt = performance.now();
    const [trailsRes, metricsRes] = await Promise.all([
      fetch(`${AIOS_BASE}/api/v1/development/trails`, { headers: authHeaders() }),
      fetch(`${AIOS_BASE}/api/v1/development/metrics`, { headers: authHeaders() }),
    ]);
    if (!trailsRes.ok || !metricsRes.ok) throw new Error('bad status');
    const trailMap = (await trailsRes.json()) as TrailMapResponse;
    const metrics = (await metricsRes.json()) as Record<string, unknown>;
    const latencyMs = Math.max(1, Math.round(performance.now() - startedAt));
    const trails = trailMap.trails ?? [];

    if (!linkUp) {
      linkUp = true;
      setMetricLink(true);
      publishCognition({
        type: 'synthesis',
        label: 'AI-OS LINK ESTABLISHED',
        detail: `live cognition: ${trails.length} trail(s) on the pheromone map`,
        intensity: 0.7,
        source: 'aios',
      });
    }

    knownTrails = trails;
    const verified = trails.filter((t) => t.status === 'verified');
    const avg = (rows: TrailRow[], pick: (t: TrailRow) => number) =>
      rows.length ? rows.reduce((sum, t) => sum + pick(t), 0) / rows.length : NaN;
    const num = (value: unknown): number => (typeof value === 'number' ? value : NaN);
    setMetricBases({
      research: num(metrics.verified_success_rate) * 100,
      tools: num(metrics.verification_coverage) * 100,
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

      // MASTERY: a trail the system itself promoted candidate -> verified is
      // the rarest, most-earned event the brain has. The scene answers with
      // the full synapse storm.
      const previousStatus = seenTrailStatus.get(trail.skill_id);
      if (
        previousStatus !== undefined &&
        previousStatus !== 'verified' &&
        trail.status === 'verified'
      ) {
        publishCognition({
          type: 'knowledge-acquired',
          label: `SKILL MASTERED — TRAIL #${trail.skill_id}`,
          detail: trailLabel(trail.goal_pattern).toLowerCase(),
          intensity: 1,
          source: 'aios',
        });
      }
      seenTrailStatus.set(trail.skill_id, trail.status);

      // The dark side of stigmergy is signal too: failures weaken a trail.
      const failures = (trail.failure_count ?? 0) + (trail.reuse_failure_count ?? 0);
      const previousFailures = seenTrailFailures.get(trail.skill_id);
      if (previousFailures !== undefined && failures > previousFailures) {
        publishCognition({
          type: 'agent-dispatch',
          label: 'TRAIL WEAKENED',
          detail: `trail #${trail.skill_id} took a failure — strength ${trail.strength.toFixed(3)}`,
          intensity: 0.4,
          source: 'aios',
        });
      }
      seenTrailFailures.set(trail.skill_id, failures);
    }

    // Tamper-evidence: walk the audit hash-chain every few polls (it scans
    // the ledger — not a per-poll cost; first verdict ~5 polls after boot).
    pollCount += 1;
    if (pollCount % CHAIN_PROBE_EVERY === 0) {
      try {
        const chainRes = await fetch(`${AIOS_BASE}/api/v1/audit/verify`, { headers: authHeaders() });
        if (chainRes.ok) {
          const chain = (await chainRes.json()) as { valid?: boolean; total_entries?: number };
          const wasValid = chainValid;
          chainValid = chain.valid === true ? true : chain.valid === false ? false : null;
          chainEntries = typeof chain.total_entries === 'number' ? chain.total_entries : 0;
          if (chainValid === false && wasValid !== false) {
            publishCognition({
              type: 'synthesis',
              label: 'AUDIT CHAIN BROKEN',
              detail: 'tamper-evidence check FAILED — inspect the audit ledger',
              intensity: 1,
              source: 'aios',
            });
          }
        }
      } catch {
        chainValid = null; // unknown, never asserted
      }
    }

    // Earned autonomy: the brain's GROWN capabilities, read every poll so the
    // HUD shows them promptly (cheap ledger). A class crossing probation ->
    // earned means the mind earned the right to act without a human on that
    // class. Best-effort and SEPARATE from the critical trails+metrics fetch:
    // an older backend without the endpoint never breaks the poll/link.
    try {
      const autRes = await fetch(`${AIOS_BASE}/api/v1/development/autonomy`, { headers: authHeaders() });
      if (autRes.ok) {
        lastAutonomy = (await autRes.json()) as AutonomySnapshot;
        for (const entry of lastAutonomy.entries ?? []) {
          const prev = seenAutonomyStatus.get(entry.signature);
          if (prev !== undefined && prev !== 'earned' && entry.status === 'earned') {
            publishCognition({
              type: 'knowledge-acquired',
              label: 'CAPABILITY EARNED',
              detail: `${entry.action_type} ${entry.target_shape} — autonomous after ${entry.success_count} verified`,
              intensity: 1,
              source: 'aios',
            });
          }
          seenAutonomyStatus.set(entry.signature, entry.status);
        }
      }
    } catch {
      // autonomy is advisory to the scene; never break the poll on its absence
    }

    const summary = trailMap.summary;
    lastTelemetry = {
      link: true,
      latencyMs,
      trails: trails.length,
      verified: summary?.verified ?? verified.length,
      candidate: summary?.candidate ?? trails.filter((t) => t.status === 'candidate').length,
      quarantined: summary?.quarantined ?? trails.filter((t) => t.quarantined).length,
      superseded: summary?.superseded ?? 0,
      tasks: num(metrics.tasks) || 0,
      lessons: num(metrics.lessons) || 0,
      repeatedMistakes: num(metrics.repeated_mistakes) || 0,
      blockedActions: num(metrics.blocked_actions) || 0,
      interventionRate: num(metrics.human_intervention_rate) || 0,
      avgToolCalls: num(metrics.average_tool_calls) || 0,
      chainValid,
      chainEntries,
      earnedAutonomy: {
        enabled: lastAutonomy?.enabled ?? false,
        earned: lastAutonomy?.summary?.earned ?? 0,
        probation: lastAutonomy?.summary?.probation ?? 0,
        revoked: lastAutonomy?.summary?.revoked ?? 0,
      },
    };
    publishCognition({
      type: 'telemetry',
      source: 'aios',
      data: lastTelemetry as unknown as Record<string, unknown>,
    });
  } catch {
    if (linkUp) {
      linkUp = false;
      setMetricLink(false);
      lastTelemetry = lastTelemetry ? { ...lastTelemetry, link: false } : null;
      publishCognition({
        type: 'synthesis',
        label: 'AI-OS LINK LOST',
        detail: 'pheromone map unreachable — cognition running on imagination.',
        intensity: 0.3,
        source: 'aios',
      });
      publishCognition({
        type: 'telemetry',
        source: 'aios',
        data: { link: false },
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
