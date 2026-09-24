/** Human-facing task progress derived from admitted runtime state. */
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

export type HumanTurnPhase = 'idle' | 'listening' | 'understanding' | 'planning' | 'acting' | 'checking' | 'recovering';
export type HumanTaskOutcome = 'verified' | 'unverified' | 'refused' | 'failed' | 'restored' | 'stopped' | null;

export interface HumanTaskInput {
  hasGoal: boolean;
  turnPhase: HumanTurnPhase;
  pendingApproval: boolean;
  continuity: 'fresh' | 'snapshot' | 'stale' | 'unknown' | 'stopped';
  outcome?: HumanTaskOutcome;
}

export function deriveHumanTaskState(input: HumanTaskInput): HumanTaskState {
  if (!input.hasGoal) return 'idle';
  if (input.continuity === 'stale') return 'stale';
  if (input.continuity === 'stopped' || input.outcome === 'stopped') return 'stopped';
  if (input.outcome === 'refused') return 'refused';
  if (input.outcome === 'restored') return 'restored';
  if (input.outcome === 'failed') return 'failed';
  if (input.outcome === 'verified') return 'done-verified';
  if (input.outcome === 'unverified') return 'done-unverified';
  if (input.pendingApproval) return 'needs-permission';
  switch (input.turnPhase) {
    case 'listening':
    case 'understanding': return 'understood';
    case 'planning': return 'preparing';
    case 'acting': return 'working';
    case 'checking': return 'checking';
    case 'recovering': return 'failed';
    default: return 'understood';
  }
}

export function isTerminalTaskState(state: HumanTaskState): boolean {
  return ['done-verified', 'done-unverified', 'refused', 'failed', 'restored', 'stopped'].includes(state);
}

export function taskStoryStepState(state: HumanTaskState, step: 'asked' | 'understood' | 'preparing' | 'permission' | 'working' | 'checking' | 'result'): 'complete' | 'current' | 'upcoming' {
  if (state === 'idle') return step === 'asked' ? 'current' : 'upcoming';
  const order = ['asked', 'understood', 'preparing', 'permission', 'working', 'checking', 'result'] as const;
  const index = order.indexOf(step);
  const current = state === 'understood' ? 1
    : state === 'preparing' ? 2
      : state === 'needs-permission' ? 3
        : state === 'working' ? 4
          : state === 'checking' ? 5
            : isTerminalTaskState(state) ? 6 : 1;
  if (state === 'needs-permission' && step === 'permission') return 'current';
  if (index < current) return 'complete';
  if (index === current) return 'current';
  return 'upcoming';
}
