// frontend/src/superbrain/lib/beingMode.ts
export type BeingMode = 'points' | 'mesh';

/**
 * Which being substrate to render. Default 'mesh' (the working scene) for the
 * whole build; opt into the point-field with ?being=points. The default flips
 * to 'points' only after operator FIDELITY sign-off (final task).
 */
export function readBeingMode(search?: string): BeingMode {
  const raw = search ?? (typeof window !== 'undefined' ? window.location.search : '');
  const value = new URLSearchParams(raw).get('being');
  return value === 'points' ? 'points' : 'mesh';
}
