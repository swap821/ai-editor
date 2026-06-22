// frontend/src/superbrain/lib/beingMode.ts
export type BeingMode = 'points' | 'mesh';

/**
 * Which being substrate to render. Default 'points' — the official voyaging mind.
 * Operator FIDELITY sign-off given 2026-06-21: the point-field IS the frontend.
 * ?being=mesh is retained only as an internal escape hatch.
 */
export function readBeingMode(search?: string): BeingMode {
  const raw = search ?? (typeof window !== 'undefined' ? window.location.search : '');
  const value = new URLSearchParams(raw).get('being');
  return value === 'mesh' ? 'mesh' : 'points';
}
