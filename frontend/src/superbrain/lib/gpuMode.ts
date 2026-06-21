// frontend/src/superbrain/lib/gpuMode.ts
//
// FLAGGED WebGPU look-spike — "The Million-Mote Mind" (.aios/state/GAGOS_WEBGPU_SPIKE.md).
// Opt-IN only via ?gpu=webgpu AND capability-gated on navigator.gpu. The default
// (`/`, no params) ALWAYS returns 'webgl' — the shipping WebGL point-field renders
// exactly as today. This module is the single gate; nothing else decides the renderer.
export type GpuMode = 'webgl' | 'webgpu';

/** True only when the runtime exposes the WebGPU entry point. */
export function hasWebGpu(nav: Navigator | undefined = typeof navigator !== 'undefined' ? navigator : undefined): boolean {
  return !!nav && 'gpu' in nav;
}

/**
 * Resolve the render substrate. 'webgpu' requires BOTH the explicit ?gpu=webgpu
 * opt-in AND a WebGPU-capable runtime; otherwise it silently falls back to 'webgl'
 * (the proven path), so default users and unsupported browsers never hit the spike.
 * The deeper async adapter check (requestAdapter → null) is handled at renderer init.
 */
export function readGpuMode(
  search?: string,
  nav: Navigator | undefined = typeof navigator !== 'undefined' ? navigator : undefined,
): GpuMode {
  const raw = search ?? (typeof window !== 'undefined' ? window.location.search : '');
  const value = new URLSearchParams(raw).get('gpu');
  if (value !== 'webgpu') return 'webgl';
  return hasWebGpu(nav) ? 'webgpu' : 'webgl';
}
