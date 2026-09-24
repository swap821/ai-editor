import { coherenceSemanticsFor, type BeingCoherenceSemantics } from './coherenceSemantics';
import {
  deriveSemanticEffectTransition,
  type SemanticWorkerVisualState,
} from './semanticEffects';
import type {
  BeingAttention,
  BeingMotion,
  BeingPhase,
  BeingPresentation,
  BeingCoherence,
  HumanTaskState,
  BeingSignal,
  WorkerPresentationState,
} from './semanticKernel';

export type PhysicalCortexPosture = 'rest' | 'arrive' | 'attention' | 'conduct' | 'verify' | 'unverified' | 'recover' | 'stopped';
export type PhysicalConductorPosture = 'idle' | 'active' | 'held' | 'verifying' | 'reabsorbing' | 'stopped';
export type PhysicalConductorTravel = 'none' | 'inbound' | 'outbound' | 'held' | 'retracting' | 'frozen';
export type PhysicalMembraneState = 'clear' | 'held' | 'refused' | 'stopped';
export type PhysicalActionTravel = 'open' | 'closed';
export type PhysicalMemoryLayer = 'none' | 'recalled' | 'promoted' | 'reflex';
export type PhysicalMemoryPulse = 'none' | 'inward' | 'settle' | 'conduct';
export type PhysicalVerificationState = 'none' | 'pending' | 'pass' | 'fail' | 'unverified';
export type PhysicalVerificationSettlement = 'unsettled' | 'stable';

export interface PhysicalBranch {
  slot: number;
  state: WorkerPresentationState;
  visual: SemanticWorkerVisualState;
  terminal: boolean;
}

export interface PhysicalSnapshot {
  phase: BeingPhase;
  taskState: HumanTaskState;
  coherence: BeingCoherence;
  motion: BeingMotion;
  attention: BeingAttention;
  signals: BeingSignal[];
  coherencePhysics: BeingCoherenceSemantics;
  cortex: {
    posture: PhysicalCortexPosture;
    attention: number;
    activity: number;
    convergence: number;
  };
  conductor: {
    posture: PhysicalConductorPosture;
    travel: PhysicalConductorTravel;
    activeSeat: number | null;
  };
  branches: PhysicalBranch[];
  memory: {
    layer: PhysicalMemoryLayer;
    pulse: PhysicalMemoryPulse;
  };
  verification: {
    state: PhysicalVerificationState;
    settlement: PhysicalVerificationSettlement;
  };
  membrane: {
    state: PhysicalMembraneState;
    actionTravel: PhysicalActionTravel;
  };
}

const MAX_BRANCHES = 8;

function cortexPosture(presentation: BeingPresentation): PhysicalCortexPosture {
  const { phase, taskState, coherence } = presentation;
  if (phase === 'stopped' || coherence === 'stopped') return 'stopped';
  if (phase === 'recovering' || phase === 'stale' || phase === 'degraded') return 'recover';
  if (phase === 'awaiting-human') return 'attention';
  if (taskState === 'done-unverified' && phase === 'resting') return 'unverified';

  switch (phase) {
    case 'arriving': return 'arrive';
    case 'listening':
    case 'understanding':
    case 'planning':
    case 'learning':
      return 'attention';
    case 'acting':
    case 'reflex':
      return 'conduct';
    case 'verifying':
      return 'verify';
    default:
      return 'rest';
  }
}

function attentionLevel(attention: BeingAttention): number {
  switch (attention) {
    case 'human': return 0.88;
    case 'workspace': return 1;
    case 'approval': return 0.72;
    default: return 0;
  }
}

function activityLevel(phase: BeingPhase): number {
  switch (phase) {
    case 'acting':
    case 'reflex':
      return 1;
    case 'verifying':
      return 0.84;
    case 'recovering':
    case 'learning':
      return 0.7;
    case 'planning':
      return 0.62;
    case 'listening':
    case 'understanding':
    case 'awaiting-human':
      return 0.5;
    case 'arriving':
      return 0.38;
    case 'stopped':
      return 0;
    default:
      return 0.18;
  }
}

function convergenceLevel(phase: BeingPhase): number {
  switch (phase) {
    case 'acting':
    case 'reflex':
      return 0.78;
    case 'verifying':
      return 0.95;
    case 'learning':
      return 0.88;
    case 'planning':
      return 0.58;
    case 'recovering':
      return 0.42;
    case 'stopped':
      return 0;
    default:
      return 0.22;
  }
}

function conductorFor(presentation: BeingPresentation, branchCount: number): PhysicalSnapshot['conductor'] {
  if (presentation.phase === 'stopped') return { posture: 'stopped', travel: 'frozen', activeSeat: null };
  const capabilityHeld = presentation.workers.includes('awaiting-capability');
  if (presentation.phase === 'awaiting-human' || presentation.taskState === 'needs-permission' || capabilityHeld) {
    return { posture: 'held', travel: 'held', activeSeat: branchCount > 0 ? 0 : null };
  }
  if (presentation.phase === 'verifying') {
    return { posture: 'verifying', travel: 'outbound', activeSeat: branchCount > 0 ? 0 : null };
  }
  if (presentation.motion === 'reabsorb' || presentation.phase === 'recovering') {
    return { posture: 'reabsorbing', travel: 'retracting', activeSeat: branchCount > 0 ? 0 : null };
  }
  if (presentation.phase === 'acting' || presentation.phase === 'reflex') {
    return { posture: 'active', travel: 'outbound', activeSeat: branchCount > 0 ? 0 : null };
  }
  if (presentation.phase === 'arriving' || presentation.motion === 'materialize') {
    return { posture: 'idle', travel: 'inbound', activeSeat: null };
  }
  return { posture: 'idle', travel: 'none', activeSeat: null };
}

function membraneFor(presentation: BeingPresentation): PhysicalSnapshot['membrane'] {
  const refusal = presentation.taskState === 'refused'
    || presentation.signals.includes('refusal')
    || presentation.signals.includes('injection-blocked');
  const capabilityHeld = presentation.workers.includes('awaiting-capability');
  const state: PhysicalMembraneState = presentation.phase === 'stopped'
    ? 'stopped'
    : presentation.taskState === 'needs-permission' || capabilityHeld
      ? 'held'
      : refusal
        ? 'refused'
        : 'clear';
  return { state, actionTravel: state === 'clear' ? 'open' : 'closed' };
}

function memoryFor(presentation: BeingPresentation): PhysicalSnapshot['memory'] {
  if (presentation.signals.includes('reflex-reused') || presentation.phase === 'reflex') {
    return { layer: 'reflex', pulse: 'conduct' };
  }
  if (presentation.signals.includes('memory-promoted') || presentation.signals.includes('curriculum-mastered')) {
    return { layer: 'promoted', pulse: 'settle' };
  }
  if (presentation.signals.includes('memory-recalled')) {
    return { layer: 'recalled', pulse: 'inward' };
  }
  return { layer: 'none', pulse: 'none' };
}

function verificationFor(presentation: BeingPresentation): PhysicalSnapshot['verification'] {
  if (presentation.signals.includes('verification-fail')) {
    return { state: 'fail', settlement: 'unsettled' };
  }
  if (presentation.signals.includes('verification-pass')) {
    return { state: 'pass', settlement: 'stable' };
  }
  if (presentation.phase === 'verifying') {
    return { state: 'pending', settlement: 'unsettled' };
  }
  if (presentation.taskState === 'done-unverified') {
    return { state: 'unverified', settlement: 'unsettled' };
  }
  return { state: 'none', settlement: 'unsettled' };
}

function branchesFor(presentation: BeingPresentation): PhysicalBranch[] {
  const workerVisualStates = deriveSemanticEffectTransition(null, presentation).workerVisualStates;
  const actionHeld = presentation.taskState === 'needs-permission' || presentation.taskState === 'refused';
  return presentation.workers.slice(0, MAX_BRANCHES).map((state, slot) => ({
    slot,
    state,
    visual: actionHeld && !['returned', 'dissolved', 'failed', 'killed'].includes(state)
      ? 'held'
      : workerVisualStates[slot],
    terminal: state === 'returned' || state === 'dissolved' || state === 'failed' || state === 'killed',
  }));
}

/**
 * Derives bounded physical inputs from the existing semantic presentation.
 * This is a projection only: it contains no authority, execution, or
 * verification decisions and does not create a new event or state bus.
 */
export function derivePhysicalSnapshot(presentation: BeingPresentation): PhysicalSnapshot {
  const branches = branchesFor(presentation);
  return {
    phase: presentation.phase,
    taskState: presentation.taskState,
    coherence: presentation.coherence,
    motion: presentation.motion,
    attention: presentation.attention,
    signals: [...presentation.signals],
    coherencePhysics: coherenceSemanticsFor(presentation.coherence),
    cortex: {
      posture: cortexPosture(presentation),
      attention: attentionLevel(presentation.attention),
      activity: activityLevel(presentation.phase),
      convergence: convergenceLevel(presentation.phase),
    },
    conductor: conductorFor(presentation, branches.length),
    branches,
    memory: memoryFor(presentation),
    verification: verificationFor(presentation),
    membrane: membraneFor(presentation),
  };
}
