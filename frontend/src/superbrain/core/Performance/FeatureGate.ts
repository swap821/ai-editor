/**
 * FeatureGate — environmental awareness for the mirror.
 *
 * "The mirror must know when the animal is sleeping vs. awake."
 * We detect when the browser tab is hidden and broadcast sleep events.
 * The 3D render loop can use this to drop to 0 FPS, freeze particles,
 * and aggressively throttle non-critical background processing.
 */
import { useEffect, useState } from 'react';

type Listener = (isSleeping: boolean) => void;

class FeatureGateImpl {
  private _isSleeping = false;
  private listeners = new Set<Listener>();

  constructor() {
    if (typeof document !== 'undefined') {
      this._isSleeping = document.hidden;
      document.addEventListener('visibilitychange', this.handleVisibilityChange);
    }
  }

  private handleVisibilityChange = () => {
    const sleeping = document.hidden;
    if (this._isSleeping !== sleeping) {
      this._isSleeping = sleeping;
      this.listeners.forEach((listener) => listener(sleeping));
    }
  };

  /**
   * Returns true if the mirror is currently in sleep mode (backgrounded).
   */
  public get isSleeping(): boolean {
    return this._isSleeping;
  }

  public subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  public dispose() {
    if (typeof document !== 'undefined') {
      document.removeEventListener('visibilitychange', this.handleVisibilityChange);
    }
    this.listeners.clear();
  }
}

export const FeatureGate = new FeatureGateImpl();

/**
 * React hook for components that need to respond to sleep/wake cycles.
 */
export function useFeatureGate(): boolean {
  const [isSleeping, setIsSleeping] = useState(FeatureGate.isSleeping);

  useEffect(() => {
    return FeatureGate.subscribe(setIsSleeping);
  }, []);

  return isSleeping;
}
