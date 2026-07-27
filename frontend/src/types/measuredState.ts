export type MetricStatus = 'measured' | 'derived' | 'unavailable' | 'stale' | 'simulated';

export interface MetricEnvelope<T = unknown> {
  value: T | null;
  status: MetricStatus;
  measured_at: string | null;
  source: string;
  freshness: number | null;
}

// Discriminator for UI
export type MeasuredState<T> = 
  | { _status: 'loading' }
  | { _status: 'unavailable', envelope: MetricEnvelope<T> }
  | { _status: 'measured', value: T, envelope: MetricEnvelope<T> }
  | { _status: 'stale', value: T, envelope: MetricEnvelope<T> }
  | { _status: 'simulated', value: T, envelope: MetricEnvelope<T> }
  | { _status: 'derived', value: T, envelope: MetricEnvelope<T> };

export function fromEnvelope<T>(envelope: MetricEnvelope<T> | null | undefined): MeasuredState<T> {
  if (!envelope) {
    return { _status: 'loading' };
  }

  if (envelope.status === 'unavailable' || envelope.value === null || envelope.value === undefined) {
    return { _status: 'unavailable', envelope };
  }

  switch (envelope.status) {
    case 'measured':
      return { _status: 'measured', value: envelope.value as T, envelope };
    case 'stale':
      return { _status: 'stale', value: envelope.value as T, envelope };
    case 'simulated':
      return { _status: 'simulated', value: envelope.value as T, envelope };
    case 'derived':
      return { _status: 'derived', value: envelope.value as T, envelope };
    default:
      // Fallback if backend adds a status we don't know, treat it as unavailable to be safe and honest.
      return { _status: 'unavailable', envelope };
  }
}

/** Suffixes that keep a non-measured reading from reading as a measured one.
 *
 * `MetricStatus` carefully distinguishes measured / derived / stale /
 * simulated, and then rendering them all as a bare value threw that
 * distinction away at the exact moment it mattered -- a simulated number
 * appeared on screen identically to a real one. In a panel whose whole
 * purpose is truthfulness, that is the failure mode, not a cosmetic gap.
 *
 * `measured` is deliberately unsuffixed: it is the only status that needs no
 * qualification, so annotating it would just add noise to the common case.
 */
const STATUS_SUFFIX: Record<string, string> = {
  derived: ' (derived)',
  stale: ' (stale)',
  simulated: ' (simulated)',
};

export function displayValue<T>(state: MeasuredState<T>, fallback: string = 'unavailable', formatter?: (val: T) => string): string {
  if (state._status === 'loading') {
    return 'loading';
  }
  if (state._status === 'unavailable') {
    return fallback;
  }
  const rendered = formatter ? formatter(state.value) : String(state.value);
  return `${rendered}${STATUS_SUFFIX[state._status] ?? ''}`;
}

/** Whether this reading was actually measured, as opposed to absent, still
 * loading, or qualified (derived/stale/simulated).
 *
 * Exists because the tempting shorthand `envelope?.value ? a : b` silently
 * collapses "we measured false" and "we do not know" into the same branch --
 * which is how an unknown reading ends up painted as a confident red or, worse,
 * a reassuring green. */
export function isMeasured<T>(state: MeasuredState<T>): state is { _status: 'measured', value: T, envelope: MetricEnvelope<T> } {
  return state._status === 'measured';
}

/** Three-way tone for a boolean reading: true, false, and genuinely unknown.
 *
 * A two-way ternary on a boolean envelope cannot express "unknown", so every
 * such call site had to pick a lie -- either claiming failure it never
 * observed, or claiming health it never observed. */
export function booleanTone<T>(
  envelopeState: MeasuredState<T>,
  tones: { whenTrue: string; whenFalse: string; whenUnknown: string },
): string {
  if (!isMeasured(envelopeState)) {
    return tones.whenUnknown;
  }
  return envelopeState.value ? tones.whenTrue : tones.whenFalse;
}
