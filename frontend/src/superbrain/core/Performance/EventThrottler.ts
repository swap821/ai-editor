/**
 * EventThrottler — strict performance gating for high-frequency events.
 *
 * Ensures event callbacks never fire more frequently than our 30Hz target
 * (~33.3ms), preventing React render thrashing and protecting the WebGL
 * performance budget.
 *
 * It guarantees the final event in a burst is always executed (trailing edge).
 */
export class EventThrottler {
  private lastFired = 0;
  private limitMs: number;
  private timer: number | null = null;

  constructor(limitMs = 33.3) {
    this.limitMs = limitMs;
  }

  /**
   * Returns a throttled version of the provided callback.
   * @param callback The function to throttle.
   * @returns A throttled wrapper function.
   */
  public throttle<T extends (...args: any[]) => void>(callback: T): (...args: Parameters<T>) => void {
    return (...args: Parameters<T>) => {
      const now = performance.now();
      const remaining = this.limitMs - (now - this.lastFired);

      if (remaining <= 0) {
        if (this.timer) {
          window.clearTimeout(this.timer);
          this.timer = null;
        }
        this.lastFired = now;
        callback(...args);
      } else if (!this.timer) {
        this.timer = window.setTimeout(() => {
          this.lastFired = performance.now();
          this.timer = null;
          callback(...args);
        }, remaining);
      }
    };
  }
}
