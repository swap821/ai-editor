import { useSyncExternalStore } from 'react';

/** The managed canvas boundary is the source of truth for this presentation signal. */
export const RENDERER_FALLBACK_SELECTOR = '.webgl-fallback';

export const rendererFallbackCopy = {
  title: 'Visual organism unavailable.',
  body: 'GAGOS controls are still working.',
  retry: 'Use the scene retry control to try again.',
} as const;

export function rendererFallbackVisible(root?: ParentNode): boolean {
  const searchRoot = root ?? (typeof document === 'undefined' ? undefined : document);
  return Boolean(searchRoot?.querySelector(RENDERER_FALLBACK_SELECTOR));
}

let current = false;
const listeners = new Set<() => void>();

export function getRendererFallbackPresentation(): boolean {
  return current;
}

export function setRendererFallbackPresentation(next: boolean): void {
  if (current === next) return;
  current = next;
  listeners.forEach((listener) => listener());
}

export function subscribeRendererFallbackPresentation(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useRendererFallbackPresentation(): boolean {
  return useSyncExternalStore(
    subscribeRendererFallbackPresentation,
    getRendererFallbackPresentation,
    getRendererFallbackPresentation,
  );
}
