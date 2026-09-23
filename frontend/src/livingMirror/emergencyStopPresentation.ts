import { useSyncExternalStore } from 'react';

/**
 * Presentation observation of the server emergency-stop latch.
 *
 * This store intentionally does not answer whether an action is authorized,
 * executable, or approved. It only lets the DOM action surface respond to a
 * confirmed or last-known latch while mirror events catch up.
 */
export type EmergencyStopPresentation = 'unknown' | 'clear' | 'engaged';

let current: EmergencyStopPresentation = 'unknown';
const listeners = new Set<() => void>();

export function getEmergencyStopPresentation(): EmergencyStopPresentation {
  return current;
}

export function setEmergencyStopPresentation(next: EmergencyStopPresentation): void {
  if (current === next) return;
  current = next;
  listeners.forEach((listener) => listener());
}

export function subscribeEmergencyStopPresentation(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useEmergencyStopPresentation(): EmergencyStopPresentation {
  return useSyncExternalStore(
    subscribeEmergencyStopPresentation,
    getEmergencyStopPresentation,
    getEmergencyStopPresentation,
  );
}

