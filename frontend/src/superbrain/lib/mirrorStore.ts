import { create } from 'zustand';
import { subscribeWithSelector } from 'zustand/middleware';

export interface CortexMirrorState {
  status: 'offline' | 'online';
  pendingEvents: number;
  phase: string;
  activeCastes: string[];
  lastEventId: number | null;
  // Reducers
  setStatus: (status: 'offline' | 'online') => void;
  setSnapshot: (data: Record<string, unknown>) => void;
  applyEvent: (id: number, type: string, payload: Record<string, unknown>) => void;
}

export const useMirrorStore = create<CortexMirrorState>()(
  subscribeWithSelector((set) => ({
    status: 'offline',
    pendingEvents: 0,
    phase: 'idle',
    activeCastes: [],
    lastEventId: null,

    setStatus: (status) => set({ status }),
    
    setSnapshot: (data) => {
      set((state) => ({
        status: data.status === 'online' ? 'online' : state.status,
        pendingEvents: typeof data.pending_events === 'number' ? data.pending_events : state.pendingEvents,
        phase: typeof data.phase === 'string' ? data.phase : state.phase,
        activeCastes: Array.isArray(data.active_castes) ? data.active_castes : state.activeCastes,
      }));
    },

    applyEvent: (id, type, payload) => {
      set((state) => {
        if (state.lastEventId !== null && id <= state.lastEventId) {
          return state;
        }

        const nextState: Partial<CortexMirrorState> = { lastEventId: id };

        switch (type) {
          case 'worker.started': {
            const role = typeof payload.role === 'string' ? payload.role : '';
            if (role && !state.activeCastes.includes(role)) {
              nextState.activeCastes = [...state.activeCastes, role];
            }
            break;
          }
          case 'worker.dissolved': {
            const role = typeof payload.role === 'string' ? payload.role : '';
            if (role) {
              nextState.activeCastes = state.activeCastes.filter((c) => c !== role);
            }
            break;
          }
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
