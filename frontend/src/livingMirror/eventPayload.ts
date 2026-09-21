import { isRecord } from './contracts';

/** CanonicalEvent.to_dict carries identity in the envelope; historical payload IDs remain supported. */
export function canonicalPayload(envelope: Record<string, unknown>, payload?: Record<string, unknown>): Record<string, unknown> {
  const result = { ...(payload ?? (isRecord(envelope.payload) ? envelope.payload : envelope)) };
  for (const [camel, snake] of [['missionId', 'mission_id'], ['workerId', 'worker_id'], ['turnId', 'turn_id']] as const) {
    const top = envelope[camel] ?? envelope[snake];
    if (typeof top === 'string' && top) {
      for (const nested of [result[camel], result[snake]]) {
        if (nested != null && nested !== top) throw new Error(`Conflicting ${camel} in canonical event`);
      }
      result[camel] = top;
    }
  }
  return result;
}
