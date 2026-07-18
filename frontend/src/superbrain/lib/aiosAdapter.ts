/**
 * aiosAdapter — binds the superbrain's nervous system to the REAL GAGOS backend.
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
import { __resetSessionForTests, ensureSession } from './sessionId';
import {
  resetSwarmHUD,
} from './swarmHUDStore';


export function humanizeRedactionMarkers(text: string | null | undefined): string {
  if (!text) return text as string;
  return text.replace(BACKEND_REDACTION_MARKER_RE, '(a sensitive value was withheld)');
}

export const AIOS_BASE =
  process.env.NEXT_PUBLIC_AIOS_URL ?? 'http://localhost:8000';

function authHeaders(): Record<string, string> {
  return {};
}

const FETCH_CREDENTIALS: RequestCredentials = 'include';
// Backend redaction markers (secret scanner / privacy filter) arrive as literal
// "[SENSITIVE: <id>]" (and sibling "[... REDACTED]") tokens. This is the ONE
// shared source pattern — GagosChrome's chip renderer imports it directly
// rather than keeping its own copy. It carries the /g flag, which is safe for
// String.prototype.split()/.replace() (today's two call sites; neither touches
// lastIndex) but NOT safe to share across a future .test()/.exec() caller in a
// loop — a stateful /g regex's lastIndex persists on the object between calls.
// Any future consumer needing test()/exec() semantics must clone this constant
// via `new RegExp(...)` first rather than calling test()/exec() on it directly.
export const BACKEND_REDACTION_MARKER_RE =
  /\[(?:SENSITIVE:\s*[^\]]*|CREDENTIAL REDACTED|PATH REDACTED|FILE CONTENT REDACTED[^\]]*)\]/g;



async function sessionBodyFields(): Promise<Record<string, string>> {
  const session = await ensureSession();
  return session.bodySessionId ? { sessionId: session.bodySessionId } : {};
}

// ---------------------------------------------------------------- directives

export interface DirectiveResult {
  /** The stream completed (done frame) or paused for approval. */
  ok: boolean;
  /** The turn paused on a human_required frame — approval is pending. */
  paused: boolean;
  /** Final synthesized answer text (possibly empty when paused/offline). */
  answer: string;
}

export interface SseFrame {
  event: string;
  data: Record<string, unknown>;
}

export async function* readSse(body: ReadableStream<Uint8Array>): AsyncGenerator<SseFrame> {
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
  /** Public URL when the ask is a browse fetch. */
  url: string;
  /** What kind of action is being authorized. */
  kind: 'create' | 'edit' | 'command' | 'browse' | 'other';
  /** Target file for write approvals (empty for commands / browse). */
  filepath: string;
  /** The full proposed file content for a CREATE (empty for edits/commands —
   *  edits carry only the unified `diff`). Lets a consumer (e.g. the forge
   *  editor) show the mind's ACTUAL proposed write, not a sample file. */
  content: string;
}

let pendingApproval: PendingApproval | null = null;

/** The approval currently awaiting the operator (null when none). */
export function getPendingApproval(): PendingApproval | null {
  return pendingApproval;
}

type ApprovalListener = (pending: PendingApproval | null) => void;
const approvalListeners = new Set<ApprovalListener>();

/** Subscribe to the PERSISTED pending-approval truth — the single source of
 *  truth the approval UI binds to. The listener is invoked IMMEDIATELY with the
 *  current value (so a late subscriber, or one that missed the transient
 *  'approval-required' bus event, still gets the real state) and again on every
 *  change. Returns an unsubscribe. A supervised pause must never be left
 *  un-actionable; binding the panel here, not to a fire-and-forget event,
 *  guarantees that. */
export function subscribePendingApproval(listener: ApprovalListener): () => void {
  approvalListeners.add(listener);
  listener(pendingApproval);
  return () => {
    approvalListeners.delete(listener);
  };
}

/** The ONLY writer of `pendingApproval`: assigns then notifies subscribers, so
 *  the persisted truth and every bound surface can never drift apart. */
function setPendingApprovalState(next: PendingApproval | null): void {
  pendingApproval = next;
  for (const listener of approvalListeners) listener(next);
}

// Dev aid (remote): inject a realistic pending approval to exercise the FULL approval
// render path (the being's approval surface) without a live LLM turn — so the elevated
// approval gate can be SEEN and tuned. window.__injectApproval(over?) / __clearApproval().
if (typeof window !== 'undefined' && process.env.NODE_ENV !== 'production') {
  const host = window as unknown as {
    __injectApproval?: (over?: Partial<PendingApproval>) => void;
    __clearApproval?: () => void;
  };
  host.__injectApproval = (over) =>
    setPendingApprovalState({
      token: 'dev-token',
      prompt: 'create a hello file',
      summary: 'Approval required to create hello_gate.py',
      explanation: 'The agent wants to create a new file. Review the contents and approve to write it.',
      diff: '--- /dev/null\n+++ b/hello_gate.py\n@@ -0,0 +1,3 @@\n+def main():\n+    print("hello from the gate")\n+    return 0',
      command: '',
      url: '',
      kind: 'create',
      filepath: 'hello_gate.py',
      content: 'def main():\n    print("hello from the gate")\n    return 0\n',
      ...over,
    });
  host.__clearApproval = () => setPendingApprovalState(null);
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
  const firstContent = (rows: unknown[]): string => {
    const head = (rows[0] ?? {}) as Record<string, unknown>;
    return String(head.content ?? '');
  };
  const rawCommand = commands.length > 0 ? String(commands[0]) : '';
  const isBrowse = rawCommand.startsWith('browse ');
  const kind: PendingApproval['kind'] =
    creations.length > 0 ? 'create' : edits.length > 0 ? 'edit' : isBrowse ? 'browse' : commands.length > 0 ? 'command' : 'other';
  setPendingApprovalState({
    token: String(input.approvalToken ?? ''),
    prompt: text,
    summary: String(data.text ?? 'Approval required'),
    explanation: String(input.explanation ?? ''),
    diff: String(input.diff ?? ''),
    command: isBrowse ? '' : rawCommand,
    url: isBrowse ? rawCommand.slice(7).trim() : '',
    kind,
    filepath: kind === 'create' ? firstPath(creations) : kind === 'edit' ? firstPath(edits) : '',
    content: kind === 'create' ? firstContent(creations) : '',
  });
}

/** Swarm opt-in (the command bar's toggle). Module singleton — like the
 *  pending-approval state — so approval REPLAYS (streamTurn with tokens)
 *  inherit the operator's current choice instead of silently dropping the
 *  colony mid-turn. LAB-SYNC: this block + the `swarm` body field + the
 *  `plan` SSE case below must be mirrored into the lab before `npm run port`. */
let swarmMode = false;

export function setSwarmMode(enabled: boolean): void {
  swarmMode = enabled;
}

export function getSwarmMode(): boolean {
  return swarmMode;
}

async function streamTurn(
  text: string,
  tokens: string[],
  signal?: AbortSignal,
  onChunk?: (answer: string) => void,
  onCodeChunk?: (code: string, language: string) => void,
): Promise<DirectiveResult> {
  let answer = '';
  let paused = false;
  try {
    const sessionFields = await sessionBodyFields();
    const response = await fetch(`${AIOS_BASE}/api/generate`, {
      method: 'POST',
      signal,
      credentials: FETCH_CREDENTIALS,
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({
        messages: [{ role: 'user', content: [{ text }] }],
        modelId: 'auto',
        ...sessionFields,
        approvalTokens: tokens,
        ...(swarmMode ? { swarm: true } : {}),
      }),
    });
    if (!response.ok || !response.body) {
      throw new Error(`backend responded ${response.status}`);
    }
    for await (const frame of readSse(response.body)) {
      switch (frame.event) {
        case 'text_chunk':
          answer += String(frame.data.text ?? '');
          onChunk?.(answer);
          break;
        case 'human_required':
          paused = true;
          captureApproval(text, frame.data);
          break;
        case 'code_chunk': {
          const code = String(frame.data.code ?? '');
          const language = String(frame.data.language ?? 'text');
          lastEmittedCode = { code, language, filepath: String(frame.data.filepath ?? '') };
          onCodeChunk?.(code, language);
          break;
        }
        case 'code': {
          const code = String(frame.data.code ?? '');
          const language = String(frame.data.language ?? 'text');
          lastEmittedCode = { code, language, filepath: String(frame.data.filepath ?? '') };
          break;
        }
        default:
          break;
      }
    }
    return { ok: true, paused, answer };
  } catch (err) {
    if (signal?.aborted || (err instanceof Error && err.name === 'AbortError')) {
      throw Object.assign(new Error('Turn aborted by operator'), { name: 'AbortError' });
    }
    
    return { ok: false, paused: false, answer };
  }
}



/** Stream one REAL supervised turn through GAGOS and narrate it on the bus. */
export async function sendDirective(
  text: string,
  signal?: AbortSignal,
  onChunk?: (answer: string) => void,
  onCodeChunk?: (code: string, language: string) => void,
): Promise<DirectiveResult> {
  setPendingApprovalState(null);
  resetSwarmHUD();
  return streamTurn(text, [], signal, onChunk, onCodeChunk);
}

/** Stream one CONVERSATIONAL turn through the GAGOS voice mind (POST
 *  /api/v1/chat) and narrate it on the bus. This is the spoken channel: it is a
 *  DIRECTIVE/conversation, never consent — the endpoint runs NO tools and has NO
 *  approval mechanism, so a spoken word can never redeem an approval token (a
 *  spoken "yes" cannot authorize anything; the agentic forge stays on the typed
 *  sendDirective path). Reuses the adapter's base/auth/shared-session + SSE
 *  reader, and publishes ONLY existing cognition events (directive on send, the
 *  real route, synthesis on done) so the brain reacts through its current
 *  handlers and the conversation organs refresh — no new scene wiring. `onChunk`
 *  reports the reply as it streams; resolves with the full reply or throws on a
 *  transport/backend error (callers surface it honestly, never a fake reply). */
export async function sendVoiceTurn(
  transcript: string,
  opts: { onChunk?: (reply: string) => void; signal?: AbortSignal; modelId?: string } = {},
): Promise<string> {
  const text = transcript.trim();
  if (!text) return '';
  
  let reply = '';
  const { signal, modelId } = opts;
  try {
    const sessionFields = await sessionBodyFields();
    const response = await fetch(`${AIOS_BASE}/api/v1/chat`, {
      method: 'POST',
      signal,
      credentials: FETCH_CREDENTIALS,
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ transcript: text, modelId, ...sessionFields }),
    });
    if (!response.ok || !response.body) {
      throw new Error(`voice backend responded ${response.status}`);
    }
    for await (const frame of readSse(response.body)) {
      const data = frame.data as Record<string, unknown>;
      if (frame.event === 'text_chunk') {
        reply += String(data.text ?? '');
        opts.onChunk?.(reply);
      } else if (frame.event === 'route' && typeof data.model === 'string' && data.model) {
        // (route event handled by aiosMirror)
      } else if (frame.event === 'error') {
        throw new Error(String(data.text ?? 'The voice mind could not answer.'));
      }
    }
    
    return reply;
  } catch (err) {
    if (signal?.aborted || (err instanceof Error && err.name === 'AbortError')) {
      throw Object.assign(new Error('Turn aborted by operator'), { name: 'AbortError' });
    }
    
    throw err;
  }
}

/** POST audio to local STT backend. Returns transcribed text. */
export async function transcribeAudio(
  audioBlob: Blob,
  opts: { signal?: AbortSignal; language?: string } = {},
): Promise<{ text: string; language: string; confidence: number }> {
  const form = new FormData();
  form.append('file', audioBlob, 'recording.wav');
  if (opts.language) form.append('language', opts.language);
  const response = await fetch(`${AIOS_BASE}/api/v1/voice/transcribe`, {
    method: 'POST',
    signal: opts.signal,
    credentials: FETCH_CREDENTIALS,
    headers: authHeaders(),
    body: form,
  });
  if (!response.ok) throw new Error(`STT backend responded ${response.status}`);
  return response.json();
}

/** POST text to local TTS backend. Returns audio ArrayBuffer (WAV). */
export async function speakText(
  text: string,
  opts: { voice?: string; signal?: AbortSignal } = {},
): Promise<ArrayBuffer> {
  const response = await fetch(`${AIOS_BASE}/api/v1/voice/speak`, {
    method: 'POST',
    signal: opts.signal,
    credentials: FETCH_CREDENTIALS,
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ text, voice: opts.voice }),
  });
  if (!response.ok) throw new Error(`TTS backend responded ${response.status}`);
  return response.arrayBuffer();
}

/** The operator authorizes: redeem the capability by replaying the turn with
 *  the server-issued token. The replay may pause again on the NEXT caution
 *  action — a fresh PendingApproval is captured and the panel continues. */
export async function approvePendingApproval(): Promise<DirectiveResult> {
  const pending = pendingApproval;
  if (!pending?.token) return { ok: false, paused: false, answer: '' };
  setPendingApprovalState(null);
  
  return streamTurn(pending.prompt, [pending.token]);
}

/** The operator declines: the rejection is recorded through the real
 *  endpoint (audited server-side) and the organism stands down. The bus
 *  only announces 'rejected' when the server CONFIRMED the decision —
 *  an unreachable backend gets the honest 'rejected (unconfirmed)'. */
export async function rejectPendingApproval(): Promise<void> {
  const pending = pendingApproval;
  if (!pending?.token) return;
  setPendingApprovalState(null);
  let confirmed = false;
  try {
    const sessionFields = await sessionBodyFields();
    const response = await fetch(`${AIOS_BASE}/api/v1/approval/req`, {
      method: 'POST',
      credentials: FETCH_CREDENTIALS,
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({
        approvalToken: pending.token,
        ...(pending.command ? { command: pending.command } : {}),
        ...sessionFields,
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
  
}

/** The operator cancelled the turn while an approval slab was showing.
 *  The surface retracts immediately; the server token is left to expire
 *  (a rejected call would race the operator's intent and is unnecessary). */
export function cancelPendingApproval(): void {
  const pending = pendingApproval;
  if (!pending) return;
  setPendingApprovalState(null);
  
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

/** The brain's most-recent emitted code artifact (the `code` SSE frame), captured
 *  so the forge can show what it actually wrote (was previously discarded). Null
 *  until the first emission this session. */
let lastEmittedCode: { code: string; language: string; filepath: string } | null = null;
export function getLastEmittedCode(): { code: string; language: string; filepath: string } | null {
  return lastEmittedCode;
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

export interface IntentPreview {
  intent: string;
  confidence: number;
  tool: string | null;
}

/** Lightweight rule-based intent preview for the command dock.
 *  Falls back to 'chat' if the backend is unreachable. */
export async function previewIntent(text: string): Promise<IntentPreview> {
  try {
    const res = await fetch(`${AIOS_BASE}/api/v1/intent/preview`, {
      method: 'POST',
      credentials: FETCH_CREDENTIALS,
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ text }),
    });
    if (!res.ok) return { intent: 'chat', confidence: 0.5, tool: null };
    const data = (await res.json()) as Record<string, unknown>;
    return {
      intent: typeof data.intent === 'string' ? data.intent : 'chat',
      confidence: typeof data.confidence === 'number' ? data.confidence : 0.5,
      tool: typeof data.tool === 'string' ? data.tool : null,
    };
  } catch {
    return { intent: 'chat', confidence: 0.5, tool: null };
  }
}

export interface OnboardingState {
  firstDirective: boolean;
  firstApproval: boolean;
  firstVerify: boolean;
  firstCloudRoute: boolean;
  firstAutonomy: boolean;
}

/** Read which first-run milestones the operator has reached.
 *  Returns all-false if the backend is unreachable. */
export async function fetchOnboardingState(): Promise<OnboardingState> {
  const empty: OnboardingState = {
    firstDirective: false,
    firstApproval: false,
    firstVerify: false,
    firstCloudRoute: false,
    firstAutonomy: false,
  };
  try {
    const res = await fetch(`${AIOS_BASE}/api/v1/onboarding/state`, {
      credentials: FETCH_CREDENTIALS,
      headers: authHeaders(),
    });
    if (!res.ok) return empty;
    const data = (await res.json()) as Record<string, unknown>;
    return {
      firstDirective: Boolean(data.firstDirective),
      firstApproval: Boolean(data.firstApproval),
      firstVerify: Boolean(data.firstVerify),
      firstCloudRoute: Boolean(data.firstCloudRoute),
      firstAutonomy: Boolean(data.firstAutonomy),
    };
  } catch {
    return empty;
  }
}

export interface OperatorModel {
  preferences: Array<{ predicate: string; object: string }>;
  attributes: Record<string, string>;
  projectContext: Array<{ predicate: string; object: string }>;
}

/** Read the structured snapshot of what the system knows about the operator.
 *  Returns all-empty sections if the backend is unreachable. */
export async function fetchOperatorModel(): Promise<OperatorModel> {
  const empty: OperatorModel = { preferences: [], attributes: {}, projectContext: [] };
  try {
    const res = await fetch(`${AIOS_BASE}/api/v1/operator/model`, {
      credentials: FETCH_CREDENTIALS,
      headers: authHeaders(),
    });
    if (!res.ok) return empty;
    const data = (await res.json()) as Record<string, unknown>;
    return {
      preferences: Array.isArray(data.preferences) ? (data.preferences as OperatorModel['preferences']) : [],
      attributes: (data.attributes && typeof data.attributes === 'object'
        ? (data.attributes as Record<string, string>)
        : {}),
      projectContext: Array.isArray(data.project_context)
        ? (data.project_context as OperatorModel['projectContext'])
        : [],
    };
  } catch {
    return empty;
  }
}

/** Test seam: clear the module's poll memory between test cases. */
export function __resetAiosAdapterForTests(): void {
  __resetSessionForTests();
  seenTrailTotals.clear();
  seenTrailFailures.clear();
  seenTrailStatus.clear();
  linkUp = false;
  knownTrails = [];
  setPendingApprovalState(null);
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
      fetch(`${AIOS_BASE}/api/v1/development/trails`, {
        credentials: FETCH_CREDENTIALS,
        headers: authHeaders(),
      }),
      fetch(`${AIOS_BASE}/api/v1/development/metrics`, {
        credentials: FETCH_CREDENTIALS,
        headers: authHeaders(),
      }),
    ]);
    if (!trailsRes.ok || !metricsRes.ok) throw new Error('bad status');
    const trailMap = (await trailsRes.json()) as TrailMapResponse;
    const metrics = (await metricsRes.json()) as Record<string, unknown>;
    const latencyMs = Math.max(1, Math.round(performance.now() - startedAt));
    const trails = trailMap.trails ?? [];

    if (!linkUp) {
      linkUp = true;
      setMetricLink(true);
      
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
        
      }
      seenTrailStatus.set(trail.skill_id, trail.status);

      // The dark side of stigmergy is signal too: failures weaken a trail.
      const failures = (trail.failure_count ?? 0) + (trail.reuse_failure_count ?? 0);
      const previousFailures = seenTrailFailures.get(trail.skill_id);
      if (previousFailures !== undefined && failures > previousFailures) {
        
      }
      seenTrailFailures.set(trail.skill_id, failures);
    }

    // Tamper-evidence: walk the audit hash-chain every few polls (it scans
    // the ledger — not a per-poll cost; first verdict ~5 polls after boot).
    pollCount += 1;
    if (pollCount % CHAIN_PROBE_EVERY === 0) {
      try {
        const chainRes = await fetch(`${AIOS_BASE}/api/v1/audit/verify`, {
          credentials: FETCH_CREDENTIALS,
          headers: authHeaders(),
        });
        if (chainRes.ok) {
          const chain = (await chainRes.json()) as { valid?: boolean; total_entries?: number };
          const wasValid = chainValid;
          chainValid = chain.valid === true ? true : chain.valid === false ? false : null;
          chainEntries = typeof chain.total_entries === 'number' ? chain.total_entries : 0;
          if (chainValid === false && wasValid !== false) {
            
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
      const autRes = await fetch(`${AIOS_BASE}/api/v1/development/autonomy`, {
        credentials: FETCH_CREDENTIALS,
        headers: authHeaders(),
      });
      if (autRes.ok) {
        lastAutonomy = (await autRes.json()) as AutonomySnapshot;
        for (const entry of lastAutonomy.entries ?? []) {
          const prev = seenAutonomyStatus.get(entry.signature);
          if (prev !== undefined && prev !== 'earned' && entry.status === 'earned') {
            
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
    notifyTelemetry();
  } catch {
    if (linkUp) {
      linkUp = false;
      setMetricLink(false);
      lastTelemetry = lastTelemetry ? { ...lastTelemetry, link: false } : null;
      notifyTelemetry();
    }
  }
}

export type TelemetryListener = () => void;
const telemetryListeners = new Set<TelemetryListener>();

export function subscribeTelemetry(listener: TelemetryListener): () => void {
  telemetryListeners.add(listener);
  return () => telemetryListeners.delete(listener);
}

function notifyTelemetry(): void {
  for (const listener of telemetryListeners) listener();
}

/* -------------------------------------------------------- facts graph */

/** A single edge from the backend knowledge-graph. */
export interface FactEdge {
  subject: string;
  predicate: string;
  object: string;
  depth: number;
}

interface FactGraphResponse {
  edges?: FactEdge[];
}

/**
 * Fetch the knowledge-graph neighbourhood around `start`.
 * Returns the edge array, or [] on any error (never throws).
 */
export async function fetchFactGraph(
  start = 'project',
  depth = 2,
): Promise<FactEdge[]> {
  try {
    const res = await fetch(
      `${AIOS_BASE}/api/v1/memory/facts/graph?start=${encodeURIComponent(start)}&depth=${depth}`,
      { credentials: FETCH_CREDENTIALS, headers: authHeaders() },
    );
    if (!res.ok) return [];
    const body = (await res.json()) as FactGraphResponse;
    return Array.isArray(body.edges) ? body.edges : [];
  } catch {
    return [];
  }
}

/* ------------------------------------------------- pending fact proposals */

/** One auto-extracted fact awaiting the operator's touch (B4 memory halo). */
export interface FactProposal {
  id: number;
  subject: string;
  predicate: string;
  object: string;
  source: string;
}

interface PendingFactsResponse {
  proposals?: FactProposal[];
}

/** Fetch the quarantined pending-fact queue. [] on any error (never throws). */
export async function fetchPendingFacts(): Promise<FactProposal[]> {
  try {
    const res = await fetch(`${AIOS_BASE}/api/v1/memory/facts/pending`, {
      credentials: FETCH_CREDENTIALS,
      headers: authHeaders(),
    });
    if (!res.ok) return [];
    const body = (await res.json()) as PendingFactsResponse;
    return Array.isArray(body.proposals) ? body.proposals : [];
  } catch {
    return [];
  }
}

export type ProposalResolution = 'approved' | 'contradiction' | 'failed';

/** Approve one proposal — the operator's touch mints knowledge THROUGH the
 *  backend's contradiction check. 'contradiction' (409) means the fact stays
 *  pending for an explicit reconcile; the halo flares and holds the mote. */
export async function approveFactProposal(id: number): Promise<ProposalResolution> {
  try {
    const res = await fetch(`${AIOS_BASE}/api/v1/memory/facts/pending/${id}/approve`, {
      method: 'POST',
      credentials: FETCH_CREDENTIALS,
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ resolvedBy: 'operator' }),
    });
    if (res.status === 409) return 'contradiction';
    return res.ok ? 'approved' : 'failed';
  } catch {
    return 'failed';
  }
}

/** Reject one proposal — it resolves without ever touching recall. */
export async function rejectFactProposal(id: number): Promise<boolean> {
  try {
    const res = await fetch(`${AIOS_BASE}/api/v1/memory/facts/pending/${id}/reject`, {
      method: 'POST',
      credentials: FETCH_CREDENTIALS,
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ resolvedBy: 'operator' }),
    });
    return res.ok;
  } catch {
    return false;
  }
}

/* ------------------------------------------------- living mirror extensions */

export async function fetchHiringProposals(): Promise<any[]> {
  try {
    const res = await fetch(`${AIOS_BASE}/api/v1/hiring/proposals`, {
      credentials: FETCH_CREDENTIALS,
      headers: authHeaders(),
    });
    if (!res.ok) return [];
    const body = await res.json();
    return Array.isArray(body?.items) ? body.items : [];
  } catch {
    return [];
  }
}

export async function fetchSkills(): Promise<any[]> {
  try {
    const res = await fetch(`${AIOS_BASE}/api/v1/skills`, {
      credentials: FETCH_CREDENTIALS,
      headers: authHeaders(),
    });
    if (!res.ok) return [];
    const body = await res.json();
    return Array.isArray(body?.items) ? body.items : [];
  } catch {
    return [];
  }
}

export async function fetchMaintenanceFindings(): Promise<any[]> {
  try {
    const res = await fetch(`${AIOS_BASE}/api/v1/maintenance/findings`, {
      credentials: FETCH_CREDENTIALS,
      headers: authHeaders(),
    });
    if (!res.ok) return [];
    const body = await res.json();
    return Array.isArray(body?.items) ? body.items : [];
  } catch {
    return [];
  }
}

export async function fetchMaintenanceScans(): Promise<any[]> {
  try {
    const res = await fetch(`${AIOS_BASE}/api/v1/maintenance/scans`, {
      credentials: FETCH_CREDENTIALS,
      headers: authHeaders(),
    });
    if (!res.ok) return [];
    const body = await res.json();
    return Array.isArray(body?.items) ? body.items : [];
  } catch {
    return [];
  }
}

/** Start the trails/metrics poll. Returns a stop function. */
export function startAiosPolling(intervalMs = 20_000): () => void {
  if (typeof window === 'undefined') return () => undefined;
  void pollOnce();
  const handle = window.setInterval(() => void pollOnce(), intervalMs);
  return () => window.clearInterval(handle);
}
