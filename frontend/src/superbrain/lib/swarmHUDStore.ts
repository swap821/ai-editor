/**
 * swarmHUDStore — reactive, read-only view of an ant-colony swarm turn.
 *
 * The adapter pushes `swarm_plan`, `caste_start`, and `caste_end` frames here
 * as they arrive from `/api/generate`. Components subscribe for immediate
 * render updates without parsing SSE frames themselves.
 */

export interface SwarmHUDState {
  /** True while any swarm leg is active. */
  active: boolean;
  /** Decomposed subtask plan (empty when no swarm plan has arrived). */
  plan: string[];
  /** Names of castes currently running. */
  activeCastes: string[];
  /** How many worker/quorum/synthesizer legs have completed. */
  completedLegs: number;
  /** Subtask indices that were routed to the cloud factory. */
  cloudIndices: number[];
}

const initialState: SwarmHUDState = {
  active: false,
  plan: [],
  activeCastes: [],
  completedLegs: 0,
  cloudIndices: [],
};

let state: SwarmHUDState = { ...initialState };

const listeners = new Set<(state: SwarmHUDState) => void>();

function notify(): void {
  for (const listener of listeners) listener(state);
}

function setState(next: Partial<SwarmHUDState>): void {
  state = { ...state, ...next };
  notify();
}

export function subscribeSwarmHUD(listener: (state: SwarmHUDState) => void): () => void {
  listeners.add(listener);
  listener(state);
  return () => listeners.delete(listener);
}

export function getSwarmHUDState(): SwarmHUDState {
  return state;
}

export function resetSwarmHUD(): void {
  setState({ ...initialState });
}

export function startSwarmPlan(plan: string[]): void {
  setState({
    active: true,
    plan,
    activeCastes: [],
    completedLegs: 0,
    cloudIndices: [],
  });
}

export function startSwarmCaste(caste: string): void {
  setState({
    active: true,
    activeCastes: [...state.activeCastes, caste],
  });
}

export function endSwarmCaste(caste: string): void {
  setState({
    activeCastes: state.activeCastes.filter((c) => c !== caste),
    completedLegs: state.completedLegs + 1,
  });
}

export function markSwarmCloudSubtask(index: number): void {
  if (!state.cloudIndices.includes(index)) {
    setState({ cloudIndices: [...state.cloudIndices, index] });
  }
}
