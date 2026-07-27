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

export function displayValue<T>(state: MeasuredState<T>, fallback: string = 'unavailable', formatter?: (val: T) => string): string {
  if (state._status === 'loading') {
    return 'loading';
  }
  if (state._status === 'unavailable') {
    return fallback;
  }
  return formatter ? formatter(state.value) : String(state.value);
}
