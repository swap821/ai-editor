/**
 * Translate admitted canonical mirror events into the small vocabulary the
 * living being can present. This is a projection only: unknown events stay
 * unknown instead of being promoted into a visual claim.
 */
export type BeingSignal =
  | 'worker-born'
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
  | 'reflex-reused';

export interface SemanticEventLike {
  type: string;
  /** Optional canonical payload. Never required for a signal mapping. */
  payload?: Record<string, unknown>;
}

const signalForType: Record<string, BeingSignal | undefined> = {
  'worker.requested': 'worker-born',
  'worker.admitted': 'worker-born',
  'worker.started': 'worker-born',
  'worker.completed': 'worker-returned',
  'worker.returned': 'worker-returned',
  'worker.dissolved': 'worker-dissolved',
  'memory.recalled': 'memory-recalled',
  'memory.promoted': 'memory-promoted',
  'security.refusal.recorded': 'refusal',
  'edit.blocked': 'refusal',
  'mission.refused': 'refusal',
  'security.injection.detected': 'injection-blocked',
  'cerebellum.replayed': 'reflex-reused',
  'council.dissent': 'council-dissent',
  'skill.mastered': 'curriculum-mastered',
};

function verificationSignal(event: SemanticEventLike): BeingSignal | undefined {
  if (!['verify_result', 'verification.completed', 'verification.passed', 'verification.failed'].includes(event.type)) return undefined;
  const verdict = String(event.payload?.verdict ?? event.payload?.status ?? '').toLowerCase();
  if (verdict === 'pass' || verdict === 'passed' || event.type === 'verification.passed') return 'verification-pass';
  if (verdict === 'fail' || verdict === 'failed' || event.type === 'verification.failed') return 'verification-fail';
  return undefined;
}

function routeSignal(event: SemanticEventLike): BeingSignal | undefined {
  if (!['route.selected', 'route', 'cloud_route'].includes(event.type)) return undefined;
  const provider = String(event.payload?.provider ?? event.payload?.route ?? '').toLowerCase();
  if (provider.includes('cloud') || ['gemini', 'bedrock', 'openai', 'anthropic'].some((name) => provider.includes(name))) return 'route-cloud';
  if (provider.includes('local') || provider.includes('ollama')) return 'route-local';
  // A route event without a provider is real but semantically incomplete.
  return undefined;
}

export function semanticSignalForEvent(event: SemanticEventLike): BeingSignal | undefined {
  return verificationSignal(event) ?? routeSignal(event) ?? signalForType[event.type];
}

export function deriveSemanticSignals(events: readonly SemanticEventLike[], limit = 8): BeingSignal[] {
  const signals: BeingSignal[] = [];
  for (const event of events.slice(-Math.max(0, limit * 2))) {
    const signal = semanticSignalForEvent(event);
    if (signal && !signals.includes(signal)) signals.push(signal);
  }
  return signals.slice(-limit);
}
