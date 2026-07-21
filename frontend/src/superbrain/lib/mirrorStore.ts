import { create } from 'zustand';
import { subscribeWithSelector } from 'zustand/middleware';

export interface CortexMirrorState {
  status: 'offline' | 'online' | 'stale';
  pendingEvents: number;
  phase: string;
  activeCastes: string[];
  activeMissions: string[];
  activeWorkers: string[];
  activeModels: string[];
  approvalRequired: boolean;
  lastVerification: Record<string, unknown> | null;
  lastAnnouncement: string | null;
  snapshotRequired: boolean;
  recentEvents: Array<{
    id: number;
    type: string;
    summary: string;
    occurredAt: string;
    missionId?: string;
    workerId?: string;
  }>;
  lastEventId: number | null;
  bootFacts: Record<string, unknown> | null;
  // Reducers
  setStatus: (status: 'offline' | 'online' | 'stale') => void;
  setAnnouncement: (announcement: string | null) => void;
  setSnapshotRequired: (reason?: string) => void;
  setSnapshot: (data: Record<string, unknown>) => void;
  applyEvent: (id: number, type: string, payload: Record<string, unknown>) => void;
}

export const useMirrorStore = create<CortexMirrorState>()(
  subscribeWithSelector((set) => ({
    status: 'offline',
    pendingEvents: 0,
    phase: 'idle',
    activeCastes: [],
    activeMissions: [],
    activeWorkers: [],
    activeModels: [],
    approvalRequired: false,
    lastVerification: null,
    lastAnnouncement: null,
    snapshotRequired: false,
    recentEvents: [],
    lastEventId: null,
    bootFacts: null,

    setStatus: (status) => set({ status }),
    setAnnouncement: (lastAnnouncement) => set({ lastAnnouncement }),
    setSnapshotRequired: (reason) => set({
      status: 'stale',
      snapshotRequired: true,
      lastAnnouncement: reason
        ? `Mirror replay paused (${reason}); a fresh snapshot is required.`
        : 'Mirror replay paused; a fresh snapshot is required.',
    }),
    
    setSnapshot: (data) => {
      set((state) => ({
        status: data.state === 'stale' || data.snapshot_required ? 'stale' : data.status === 'online' ? 'online' : state.status,
        pendingEvents: typeof data.pending_events === 'number' ? data.pending_events : state.pendingEvents,
        phase: typeof data.phase === 'string' ? data.phase : state.phase,
        activeCastes: Array.isArray(data.active_castes) ? data.active_castes : state.activeCastes,
        activeMissions: Array.isArray(data.active_missions) ? data.active_missions : state.activeMissions,
        activeWorkers: Array.isArray(data.active_workers) ? data.active_workers : state.activeWorkers,
        activeModels: Array.isArray(data.active_models) ? data.active_models : state.activeModels,
        snapshotRequired: data.snapshot_required === true,
        lastEventId: typeof data.last_event_id === 'number'
          && Number.isSafeInteger(data.last_event_id)
          && data.last_event_id >= 0
          ? data.last_event_id
          : state.lastEventId,
        bootFacts: data.boot_facts && typeof data.boot_facts === 'object' ? data.boot_facts as Record<string, unknown> : state.bootFacts,
      }));
    },

    applyEvent: (id, type, payload) => {
      set((state) => {
        if (state.lastEventId !== null && id <= state.lastEventId) {
          return state;
        }

        const eventPayload = payload.payload && typeof payload.payload === 'object'
          ? payload.payload as Record<string, unknown>
          : payload;
        const summaryValue = eventPayload.summary ?? eventPayload.label ?? eventPayload.reason ?? eventPayload.status ?? type;
        const eventSummary = {
          id,
          type,
          summary: String(summaryValue).slice(0, 180),
          occurredAt: typeof payload.occurredAt === 'string' ? payload.occurredAt : new Date().toISOString(),
          ...(typeof eventPayload.missionId === 'string' ? { missionId: eventPayload.missionId } : {}),
          ...(typeof eventPayload.mission_id === 'string' ? { missionId: eventPayload.mission_id } : {}),
          ...(typeof eventPayload.workerId === 'string' ? { workerId: eventPayload.workerId } : {}),
          ...(typeof eventPayload.worker_id === 'string' ? { workerId: eventPayload.worker_id } : {}),
        };
        const nextState: Partial<CortexMirrorState> = {
          lastEventId: id,
          recentEvents: [...state.recentEvents, eventSummary].slice(-40),
        };

        switch (type) {
          case 'worker.started': {
            const role = typeof eventPayload.role === 'string' ? eventPayload.role : '';
            const workerId = typeof eventPayload.workerId === 'string' ? eventPayload.workerId : typeof eventPayload.worker_id === 'string' ? eventPayload.worker_id : '';
            if (workerId && !state.activeWorkers.includes(workerId)) nextState.activeWorkers = [...state.activeWorkers, workerId];
            if (role && !state.activeCastes.includes(role)) {
              nextState.activeCastes = [...state.activeCastes, role];
            }
            break;
          }
          case 'worker.dissolved': {
            const role = typeof eventPayload.role === 'string' ? eventPayload.role : '';
            const workerId = typeof eventPayload.workerId === 'string' ? eventPayload.workerId : typeof eventPayload.worker_id === 'string' ? eventPayload.worker_id : '';
            if (workerId) nextState.activeWorkers = state.activeWorkers.filter((worker) => worker !== workerId);
            if (role) {
              nextState.activeCastes = state.activeCastes.filter((c) => c !== role);
            }
            break;
          }
          case 'worker.completed':
          case 'worker.failed':
          case 'worker.killed': {
            const workerId = typeof eventPayload.workerId === 'string' ? eventPayload.workerId : typeof eventPayload.worker_id === 'string' ? eventPayload.worker_id : '';
            if (workerId) nextState.activeWorkers = state.activeWorkers.filter((worker) => worker !== workerId);
            break;
          }
          case 'mission.running':
          case 'mission.started': {
            const missionId = typeof eventPayload.missionId === 'string' ? eventPayload.missionId : typeof eventPayload.mission_id === 'string' ? eventPayload.mission_id : '';
            if (missionId && !state.activeMissions.includes(missionId)) nextState.activeMissions = [...state.activeMissions, missionId];
            break;
          }
          case 'mission.completed':
          case 'mission.failed':
          case 'mission.cancelled':
          case 'mission.rolled_back': {
            const missionId = typeof eventPayload.missionId === 'string' ? eventPayload.missionId : typeof eventPayload.mission_id === 'string' ? eventPayload.mission_id : '';
            if (missionId) nextState.activeMissions = state.activeMissions.filter((mission) => mission !== missionId);
            break;
          }
          case 'model.selected':
          case 'model.started': {
            const modelId = typeof eventPayload.model === 'string' ? eventPayload.model : typeof eventPayload.model_id === 'string' ? eventPayload.model_id : '';
            if (modelId && !state.activeModels.includes(modelId)) nextState.activeModels = [...state.activeModels, modelId];
            break;
          }
          case 'model.completed':
          case 'model.failed':
          case 'model.dissolved': {
            const modelId = typeof eventPayload.model === 'string' ? eventPayload.model : typeof eventPayload.model_id === 'string' ? eventPayload.model_id : '';
            if (modelId) nextState.activeModels = state.activeModels.filter((model) => model !== modelId);
            break;
          }
          case 'approval.required':
          case 'human_required':
            nextState.approvalRequired = true;
            break;
          case 'approval.resolved':
            nextState.approvalRequired = false;
            break;
          case 'verify_result':
          case 'verification.passed':
          case 'verification.failed':
            nextState.lastVerification = payload;
            break;
          case 'snapshot_required':
            nextState.snapshotRequired = true;
            nextState.status = 'stale';
            break;
          case 'turn.started':
            nextState.phase = 'active';
            break;
          case 'turn.completed':
            nextState.phase = 'idle';
            break;
        }

        return nextState;
      });
    },
  }))
);
