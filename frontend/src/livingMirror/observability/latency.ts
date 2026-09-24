/**
 * Converts two local monotonic clock readings into a safe duration. A missing
 * or invalid clock must not become a fabricated positive performance result.
 */
export function measuredLatency(startedAt: number, finishedAt: number): number {
  if (!Number.isFinite(startedAt) || !Number.isFinite(finishedAt)) return 0;
  return Math.max(0, finishedAt - startedAt);
}
