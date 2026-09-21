import { create } from 'zustand';
import { subscribeWithSelector } from 'zustand/middleware';
import { isRecord, stringList } from '../../livingMirror/contracts';
import type { MetricEnvelope } from '../../types/measuredState';
import { canonicalPayload } from '../../livingMirror/eventPayload';

type Observation = { status: 'measured' | 'derived' | 'stale' | 'unavailable'; source: string; observedAt: string | null; receivedAt: string | null; cursor: number | null };
type Entity = { id: string; missionId: string | null; state: string; observedAt: string | null; cursor: number; role?: string; payload: Record<string, unknown> };
type ObservedField = 'phase' | 'activeMissions' | 'activeWorkers' | 'activeCastes' | 'activeModels' | 'approvalRequired' | 'pendingEvents';
export interface CortexMirrorState {
  status: 'offline' | 'online' | 'stale';
  connection: 'disconnected' | 'connecting' | 'connected';
  projection: 'unknown' | 'synchronizing' | 'snapshot' | 'fresh' | 'stale' | 'unavailable';
  compatibility: string | null;
  snapshotReceivedAt: string | null;
  observations: Record<ObservedField, Observation>;
  metrics: Record<string, MetricEnvelope<unknown>>;
  pendingEvents: number;
  phase: string;
  activeCastes: string[];
  activeMissions: string[];
  activeWorkers: string[];
  activeModels: string[];
  missions: Record<string, Entity>;
  workers: Record<string, Entity>;
  approvals: Record<string, Entity>;
  verifications: Record<string, Entity>;
  approvalRequired: boolean;
  lastVerification: Record<string, unknown> | null;
  lastAnnouncement: string | null;
  snapshotRequired: boolean;
  recentEvents: Array<{ id: number; type: string; summary: string; occurredAt: string | null; receivedAt: string; missionId?: string; workerId?: string }>;
  lastEventId: number | null;
  bootFacts: Record<string, unknown> | null;
  setStatus: (status: 'offline' | 'online' | 'stale') => void;
  setConnection: (connection: CortexMirrorState['connection']) => void;
  setAnnouncement: (announcement: string | null) => void;
  setSnapshotRequired: (reason?: string) => void;
  setSnapshot: (data: Record<string, unknown>) => void;
  applyEvent: (id: number, type: string, payload: Record<string, unknown>) => boolean;
  markStale: (reason?: string) => void;
}
const fields: ObservedField[] = ['phase', 'activeMissions', 'activeWorkers', 'activeCastes', 'activeModels', 'approvalRequired', 'pendingEvents'];
const unknown = (): Observation => ({ status: 'unavailable', source: 'mirror', observedAt: null, receivedAt: null, cursor: null });
const initialObservations = () => Object.fromEntries(fields.map((key) => [key, unknown()])) as Record<ObservedField, Observation>;
const text = (p: Record<string, unknown>, ...keys: string[]): string | null => {
  for (const key of keys) if (typeof p[key] === 'string' && p[key]) return p[key] as string;
  return null;
};
const timestamp = (p: Record<string, unknown>) => {
  const value = text(p, 'occurredAt', 'occurred_at');
  return value && Number.isFinite(Date.parse(value)) ? value : null;
};
const terminal = new Set(['completed', 'failed', 'killed', 'dissolved', 'cancelled', 'rolled_back']);
const bounded = (records: Record<string, Entity>): Record<string, Entity> => {
  // Retain unresolved entities; bound historical terminal observations. Durable detail is fetched separately.
  const entries = Object.entries(records);
  const history = entries.filter(([, v]) => terminal.has(v.state)).sort((a, b) => b[1].cursor - a[1].cursor).slice(0, 256);
  return Object.fromEntries([...entries.filter(([, v]) => !terminal.has(v.state)), ...history]);
};

export const useMirrorStore = create<CortexMirrorState>()(subscribeWithSelector((set, get) => ({
  status: 'offline', connection: 'disconnected', projection: 'unknown', compatibility: null, snapshotReceivedAt: null,
  observations: initialObservations(), metrics: {}, pendingEvents: 0, phase: 'unknown', activeCastes: [], activeMissions: [], activeWorkers: [], activeModels: [],
  missions: {}, workers: {}, approvals: {}, verifications: {}, approvalRequired: false, lastVerification: null, lastAnnouncement: null,
  snapshotRequired: false, recentEvents: [], lastEventId: null, bootFacts: null,
  setStatus: (status) => set({ status }),
  setConnection: (connection) => set({ connection }),
  setAnnouncement: (lastAnnouncement) => set({ lastAnnouncement }),
  markStale: (reason) => set((s) => ({ status: s.snapshotReceivedAt ? 'stale' : 'offline', projection: s.snapshotReceivedAt ? 'stale' : 'unavailable',
    observations: Object.fromEntries(Object.entries(s.observations).map(([key, o]) => [key, { ...o, status: o.status === 'unavailable' ? 'unavailable' : 'stale' }])) as CortexMirrorState['observations'],
    lastAnnouncement: reason ?? s.lastAnnouncement })),
  setSnapshotRequired: (reason) => {
    get().markStale(reason ? `Mirror replay paused (${reason}); a fresh snapshot is required.` : 'Mirror replay paused; a fresh snapshot is required.');
    set({ snapshotRequired: true });
  },
  setSnapshot: (data) => set((s) => {
    const receivedAt = new Date().toISOString();
    const cursor = typeof data.last_event_id === 'number' && Number.isSafeInteger(data.last_event_id) && data.last_event_id >= 0 ? data.last_event_id : null;
    const partial: Partial<CortexMirrorState> = {};
    const observations = { ...s.observations };
    for (const [field, wire] of [['activeMissions', 'active_missions'], ['activeWorkers', 'active_workers'], ['activeCastes', 'active_castes'], ['activeModels', 'active_models']] as const) {
      if (stringList(data[wire])) partial[field] = [...new Set(data[wire])];
    }
    if (typeof data.phase === 'string') partial.phase = data.phase;
    if (typeof data.pending_events === 'number' && Number.isSafeInteger(data.pending_events) && data.pending_events >= 0) partial.pendingEvents = data.pending_events;
    const stale = data.state === 'stale' || data.snapshot_required === true;
    for (const field of fields) observations[field] = field in partial
      ? { status: stale ? 'stale' : 'measured', source: 'mirror/snapshot', observedAt: timestamp(data), receivedAt, cursor }
      : { ...observations[field], status: observations[field].status === 'unavailable' ? 'unavailable' : 'stale' };
    const valid = cursor !== null && data.status === 'online';
    return { ...partial, observations, status: valid ? 'stale' : s.status,
      projection: valid ? stale ? 'stale' : 'snapshot' : s.projection,
      snapshotReceivedAt: valid ? receivedAt : s.snapshotReceivedAt,
      snapshotRequired: data.snapshot_required === true, lastEventId: cursor ?? s.lastEventId,
      metrics: isRecord(data.metrics) ? data.metrics as CortexMirrorState['metrics'] : s.metrics,
      bootFacts: isRecord(data.boot_facts) ? data.boot_facts : s.bootFacts };
  }),
  applyEvent: (id, type, envelope) => {
    if (!Number.isSafeInteger(id) || id < 0 || (get().lastEventId !== null && id <= get().lastEventId!)) return false;
    let payload: Record<string, unknown>;
    try { payload = canonicalPayload(envelope); } catch { return false; }
    set((s) => {
      const p = payload;
      const occurredAt = timestamp(envelope), receivedAt = new Date().toISOString();
      const missionId = text(p, 'missionId', 'mission_id'), workerId = text(p, 'workerId', 'worker_id');
      const next: Partial<CortexMirrorState> = { lastEventId: id, observations: { ...s.observations },
        recentEvents: [...s.recentEvents, { id, type, summary: String(p.summary ?? p.label ?? p.reason ?? p.status ?? type).slice(0, 180), occurredAt, receivedAt,
          ...(missionId ? { missionId } : {}), ...(workerId ? { workerId } : {}) }].slice(-256) };
      const observe = (field: ObservedField, status: Observation['status'] = 'derived') => {
        next.observations![field] = { status, source: `mirror/event/${type}`, observedAt: occurredAt, receivedAt, cursor: id };
      };
      const entity = (entityId: string, state: string): Entity => ({ id: entityId, missionId, state, observedAt: occurredAt, cursor: id, payload: p });
      if (type.startsWith('worker.') && workerId) {
        const state = type.slice(7), old = s.workers[workerId];
        const role = text(p, 'role') ?? old?.role;
        const workers = bounded({ ...s.workers, [workerId]: { ...entity(workerId, state), missionId: missionId ?? old?.missionId ?? null, role } });
        next.workers = workers;
        if (state === 'started') next.activeWorkers = [...new Set([...s.activeWorkers, workerId])];
        else if (terminal.has(state)) next.activeWorkers = s.activeWorkers.filter((w) => w !== workerId);
        const activeIds = next.activeWorkers ?? s.activeWorkers;
        if (role && state === 'started') next.activeCastes = [...new Set([...s.activeCastes, role])];
        else if (role && terminal.has(state) && !activeIds.some((w) => workers[w]?.role === role)) {
          // Unknown snapshot workers may still hold the role: only remove when all identities are known.
          if (activeIds.every((w) => workers[w]?.role)) next.activeCastes = s.activeCastes.filter((r) => r !== role);
        }
        if (next.activeWorkers) observe('activeWorkers');
        if (next.activeCastes) observe('activeCastes');
      }
      if (type.startsWith('mission.') && missionId) {
        const state = type.slice(8);
        next.missions = bounded({ ...s.missions, [missionId]: entity(missionId, state) });
        if (['started', 'running'].includes(state)) { next.activeMissions = [...new Set([...s.activeMissions, missionId])]; next.phase = 'active'; observe('phase'); }
        else if (terminal.has(state)) next.activeMissions = s.activeMissions.filter((m) => m !== missionId);
        if (next.activeMissions) observe('activeMissions');
      }
      if (type.startsWith('model.')) {
        const model = text(p, 'model', 'model_id');
        if (model) { next.activeModels = terminal.has(type.slice(6)) ? s.activeModels.filter((m) => m !== model) : [...new Set([...s.activeModels, model])]; observe('activeModels'); }
      }
      if (['approval.required', 'human_required', 'approval.resolved', 'approval.decided'].includes(type)) {
        const requestId = text(p, 'requestId', 'request_id', 'approvalId', 'approval_id');
        const key = JSON.stringify([missionId, requestId]);
        const waiting = ['approval.required', 'human_required'].includes(type);
        const approvals = { ...s.approvals };
        if (waiting) approvals[requestId ? key : `unbound:${id}`] = entity(requestId ?? `event:${id}`, 'pending');
        else if (requestId && approvals[key]) approvals[key] = entity(requestId, text(p, 'decision', 'status') ?? 'resolved');
        next.approvals = approvals;
        next.approvalRequired = Object.values(approvals).some((a) => a.state === 'pending');
        observe('approvalRequired');
      }
      if (['verify_result', 'verification.passed', 'verification.failed', 'verification.completed'].includes(type)) {
        const evidenceId = text(p, 'evidenceId', 'evidence_id') ?? `event:${id}`;
        next.verifications = Object.fromEntries(Object.entries({ ...s.verifications, [evidenceId]: entity(evidenceId, text(p, 'verdict', 'status') ?? type) }).slice(-256));
        next.lastVerification = envelope; // legacy inspection only; never promotion authority
      }
      if (type === 'turn.started') { next.phase = 'active'; observe('phase'); }
      if (['turn.completed', 'turn.failed'].includes(type)) {
        next.phase = (next.activeMissions ?? s.activeMissions).length || (next.activeWorkers ?? s.activeWorkers).length ? 'active' : 'unknown'; observe('phase');
      }
      if (type === 'snapshot_required') { next.snapshotRequired = true; next.status = 'stale'; next.projection = 'stale'; }
      return next;
    });
    return true;
  },
})));
