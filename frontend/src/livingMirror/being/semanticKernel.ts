/**
 * Presentation-only semantic kernel for the living being.
 *
 * This module translates already-admitted mirror facts into a small visual
 * vocabulary. It does not decide whether an action may happen, whether a
 * person has approved anything, or whether a capability is available. Those
 * decisions remain outside the frontend presentation layer.
 */

export type BeingPhase =
  | 'booting'
  | 'arriving'
  | 'resting'
  | 'listening'
  | 'understanding'
  | 'planning'
  | 'awaiting-human'
  | 'acting'
  | 'verifying'
  | 'learning'
  | 'reflex'
  | 'recovering'
  | 'stale'
  | 'degraded'
  | 'stopped';

export type BeingSignal =
  | 'worker-requested'
  | 'worker-born'
  | 'worker-active'
  | 'worker-returned'
  | 'worker-dissolved'
  | 'memory-recalled'
  | 'memory-promoted'
  | 'refusal'
  | 'injection-blocked'
  | 'verification-pass'
  | 'verification-fail'
  | 'route-local'
  | 'route-cloud'
  | 'council-dissent'
  | 'curriculum-mastered'
  | 'reflex-reused'
  | 'rollback'
  | 'emergency-stop';

export type HumanTaskState =
  | 'idle'
  | 'understood'
  | 'preparing'
  | 'needs-permission'
  | 'working'
  | 'checking'
  | 'done-verified'
  | 'done-unverified'
  | 'refused'
  | 'failed'
  | 'restored'
  | 'stopped'
  | 'stale';

export type BeingCoherence = 'fresh' | 'unverified' | 'stale' | 'degraded' | 'stopped';
/**
 * Shared motion vocabulary. These are semantic intents, not animation names:
 * scene and DOM layers decide how to express them at each quality tier.
 */
export type BeingMotion = 'calm' | 'attention' | 'materialize' | 'conduct' | 'verify' | 'refuse' | 'reabsorb' | 'stop';
export type BeingAttention = 'none' | 'human' | 'workspace' | 'approval';

export type WorkerPresentationState =
  | 'requested'
  | 'admitted'
  | 'active'
  | 'awaiting-capability'
  | 'returned'
  | 'dissolved'
  | 'failed'
  | 'killed';

export interface WorkerPresentationRecord {
  workerId: string;
  state: WorkerPresentationState;
  cursor: number;
}

export type MirrorTransport = 'disconnected' | 'connecting' | 'connected';
export type MirrorProjection = 'unknown' | 'synchronizing' | 'snapshot' | 'fresh' | 'stale' | 'unavailable';
export type MirrorStatus = 'offline' | 'online' | 'stale';
export type TaskActivity = 'idle' | 'streaming' | 'checking' | 'complete' | 'failed' | 'refused' | 'restored' | 'stopped';
export type VerificationState = 'unknown' | 'pending' | 'pass' | 'fail' | 'unavailable';
export type RouteClass = 'unknown' | 'local' | 'cloud';
export type StopState = 'unknown' | 'clear' | 'engaged';

/**
 * Facts admitted from product-owned stores. The names describe observations,
 * not decisions. `approvalPending` means a human boundary is being displayed;
 * it does not say what the human will decide.
 */
export interface BeingFacts {
  lifecycle?: string | null;
  transport: MirrorTransport;
  projection: MirrorProjection;
  mirrorStatus: MirrorStatus;
  hasSnapshot: boolean;
  inputActive?: boolean;
  hasInput?: boolean;
  hasUnderstanding?: boolean;
  hasPlan?: boolean;
  taskActivity: TaskActivity;
  approvalPending?: boolean;
  verification: VerificationState;
  route?: RouteClass;
  stop: StopState;
  reflexUsed?: boolean;
  learning?: boolean;
  memoryRecalled?: boolean;
  memoryPromoted?: boolean;
  injectionBlocked?: boolean;
  councilDissent?: boolean;
  curriculumMastered?: boolean;
  rollback?: boolean;
  workers?: readonly WorkerPresentationRecord[];
  signals?: readonly BeingSignal[];
}

export interface BeingPresentation {
  phase: BeingPhase;
  taskState: HumanTaskState;
  coherence: BeingCoherence;
  motion: BeingMotion;
  attention: BeingAttention;
  signals: BeingSignal[];
  /** Bounded worker posture for product-owned visual projection. */
  workers: WorkerPresentationRecord[];
}

const SIGNAL_ORDER: BeingSignal[] = [
  'emergency-stop',
  'rollback',
  'injection-blocked',
  'refusal',
  'verification-fail',
  'verification-pass',
  'worker-requested',
  'worker-born',
  'worker-active',
  'worker-returned',
  'worker-dissolved',
  'memory-recalled',
  'memory-promoted',
  'reflex-reused',
  'route-local',
  'route-cloud',
  'council-dissent',
  'curriculum-mastered',
];

function hasWorker(workers: readonly WorkerPresentationRecord[], ...states: WorkerPresentationState[]): boolean {
  return workers.some((worker) => states.includes(worker.state));
}

function deriveSignals(facts: BeingFacts): BeingSignal[] {
  const signals = new Set<BeingSignal>(facts.signals ?? []);
  const workers = facts.workers ?? [];

  if (facts.stop === 'engaged') signals.add('emergency-stop');
  if (facts.rollback) signals.add('rollback');
  if (facts.injectionBlocked) signals.add('injection-blocked');
  if (facts.taskActivity === 'refused') signals.add('refusal');
  if (facts.verification === 'pass') signals.add('verification-pass');
  if (facts.verification === 'fail') signals.add('verification-fail');
  if (facts.route === 'local') signals.add('route-local');
  if (facts.route === 'cloud') signals.add('route-cloud');
  if (facts.reflexUsed) signals.add('reflex-reused');
  if (facts.memoryRecalled) signals.add('memory-recalled');
  if (facts.memoryPromoted) signals.add('memory-promoted');
  if (facts.councilDissent) signals.add('council-dissent');
  if (facts.curriculumMastered) signals.add('curriculum-mastered');
  if (hasWorker(workers, 'requested')) signals.add('worker-requested');
  if (hasWorker(workers, 'admitted')) signals.add('worker-born');
  if (hasWorker(workers, 'active', 'awaiting-capability')) signals.add('worker-active');
  if (hasWorker(workers, 'returned')) signals.add('worker-returned');
  if (hasWorker(workers, 'dissolved')) signals.add('worker-dissolved');

  return SIGNAL_ORDER.filter((signal) => signals.has(signal));
}

function deriveCoherence(facts: BeingFacts): BeingCoherence {
  if (facts.stop === 'engaged') return 'stopped';
  if (facts.projection === 'stale' || facts.mirrorStatus === 'stale') return 'stale';
  if (facts.verification === 'fail' || facts.taskActivity === 'failed') return 'degraded';
  if (facts.taskActivity === 'complete' && facts.verification !== 'pass') return 'unverified';
  if (facts.projection === 'unknown' || facts.projection === 'unavailable' || facts.transport !== 'connected') {
    return facts.hasSnapshot ? 'stale' : 'degraded';
  }
  return 'fresh';
}

function deriveTaskState(facts: BeingFacts, coherence: BeingCoherence): HumanTaskState {
  if (facts.stop === 'engaged' || facts.taskActivity === 'stopped') return 'stopped';
  // A measured server-issued approval is the human boundary. Keep that
  // decision surface primary even when the surrounding mirror has become
  // stale or degraded; coherence still reports that transport truth below.
  if (facts.approvalPending) return 'needs-permission';
  if (coherence === 'stale') return 'stale';
  if (facts.taskActivity === 'refused') return 'refused';
  if (facts.taskActivity === 'failed' || facts.verification === 'fail') return 'failed';
  if (facts.taskActivity === 'restored' || facts.rollback) return 'restored';
  if (facts.taskActivity === 'complete') return facts.verification === 'pass' ? 'done-verified' : 'done-unverified';
  if (facts.taskActivity === 'checking' || facts.verification === 'pending') return 'checking';
  if (facts.taskActivity === 'streaming' || hasWorker(facts.workers ?? [], 'active', 'awaiting-capability')) return 'working';
  if (facts.hasPlan) return 'preparing';
  if (facts.hasUnderstanding || facts.hasInput) return 'understood';
  return 'idle';
}

function derivePhase(facts: BeingFacts, coherence: BeingCoherence, taskState: HumanTaskState): BeingPhase {
  if (facts.stop === 'engaged') return 'stopped';
  // Approval hold interrupts ordinary posture, including last-known/degraded
  // transport. This exposes the real human boundary without claiming that the
  // mirror is current or that the action is authorized.
  if (facts.approvalPending) return 'awaiting-human';
  if (facts.lifecycle === 'booting' && facts.transport !== 'disconnected') return 'booting';
  if (!facts.hasSnapshot && facts.transport === 'disconnected') return 'degraded';
  if (facts.lifecycle === 'arriving' || facts.lifecycle === 'arrival') return 'arriving';
  if (coherence === 'stale') return 'stale';
  if (facts.rollback || facts.taskActivity === 'failed' || facts.taskActivity === 'refused' || facts.verification === 'fail') return 'recovering';
  if (coherence === 'degraded') return 'degraded';
  if (facts.verification === 'pending' || facts.taskActivity === 'checking') return 'verifying';
  if (facts.learning || facts.memoryPromoted || facts.curriculumMastered) return 'learning';
  if (facts.reflexUsed && taskState !== 'done-verified' && taskState !== 'done-unverified') return 'reflex';
  if (taskState === 'working') return 'acting';
  if (facts.hasPlan) return 'planning';
  if (facts.inputActive) return 'listening';
  if (facts.hasUnderstanding || facts.hasInput) return 'understanding';
  return 'resting';
}

function motionForPhase(phase: BeingPhase, facts: BeingFacts): BeingMotion {
  if (facts.stop === 'engaged') return 'stop';
  if (facts.lifecycle === 'reabsorbing' || facts.rollback) return 'reabsorb';
  if (facts.taskActivity === 'refused' || facts.injectionBlocked) return 'refuse';
  // A failed verifier or failed action must leave the action-bearing surface
  // unsettled and moving toward recovery. A calm posture here would visually
  // imply that the failed result had safely settled, even though its receipt
  // is not verified truth.
  if (facts.verification === 'fail' || facts.taskActivity === 'failed') return 'reabsorb';
  if (facts.lifecycle === 'materializing' || phase === 'arriving') return 'materialize';
  switch (phase) {
    case 'listening':
    case 'understanding':
    case 'awaiting-human':
    case 'planning':
      return 'attention';
    case 'learning':
      return 'attention';
    case 'acting':
    case 'reflex':
      return 'conduct';
    case 'verifying':
      return 'verify';
    case 'stopped':
      return 'stop';
    default:
      return 'calm';
  }
}

function attentionForPhase(phase: BeingPhase): BeingAttention {
  if (phase === 'listening' || phase === 'understanding') return 'human';
  if (phase === 'awaiting-human') return 'approval';
  if (phase === 'acting' || phase === 'verifying' || phase === 'learning' || phase === 'reflex') return 'workspace';
  return 'none';
}

/** Purely derives a presentation posture from already-admitted observations. */
export function deriveBeingPresentation(facts: BeingFacts): BeingPresentation {
  const coherence = deriveCoherence(facts);
  const taskState = deriveTaskState(facts, coherence);
  const phase = derivePhase(facts, coherence, taskState);
  return {
    phase,
    taskState,
    coherence,
    motion: motionForPhase(phase, facts),
    attention: attentionForPhase(phase),
    signals: deriveSignals(facts),
    workers: [...(facts.workers ?? [])].slice(0, 8),
  };
}
