// surfaceDialBus — the operator's live tuning dial for materialized-surface
// ANATOMY. In the points being the slab renders as clean dark glass: the
// LivingMembraneSkin (veins / nodes / thickness gradient / root-grip) and the
// OrganPointFieldSkin are gated OFF (the "dark-glass card" look). This bus lets
// the operator un-gate + tune that tissue LIVE on :5173 — `window.__SURFACE` —
// so the surfaces can read as membrane, not panel, without a rebuild. Defaults
// are byte-for-byte the current look, so the dial is ZERO regression until he
// flips it; once he lands the numbers I bake them as the new points defaults.
//
// Module singleton, SSR-safe (window wired lazily, guarded). React subscribes
// via useSurfaceDial(); the 3D scene re-renders when the operator turns a knob.
//
// Console ergonomics (both work):
//   window.__SURFACE = { membrane: true, membraneOpacity: 0.6 }   // merge object
//   window.__SURFACE.membrane = true                              // mutate one knob
//   window.__getSurfaceDial()                                     // read snapshot

import { useSyncExternalStore } from 'react';

export interface SurfaceDial {
  /** Un-gate the LivingMembraneSkin (veins/nodes/gradient/grip) in the points being. */
  membrane: boolean;
  /** Un-gate the OrganPointFieldSkin (dotted particle field) overlay in the points being. */
  pointSkin: boolean;
  /** Multiplier on the membrane fill opacity (tune tissue presence). */
  membraneOpacity: number;
  /** Multiplier on the vein-line opacity. */
  veinOpacity: number;
  /** Multiplier on the membrane node-dot opacity. */
  nodeOpacity: number;
  /** Slab contour RIM opacity (the lit membrane edge). Default matches the baked 0.38. */
  rimOpacity: number;
  /** Title/header-band opacity multiplier — de-emphasize the "card header" tell (1 = unchanged). */
  titleOpacity: number;
}

export const DEFAULT_SURFACE_DIAL: SurfaceDial = {
  membrane: false,
  pointSkin: false,
  membraneOpacity: 1,
  veinOpacity: 1,
  nodeOpacity: 1,
  rimOpacity: 0.38,
  titleOpacity: 1,
};

const KNOB_KEYS = Object.keys(DEFAULT_SURFACE_DIAL) as (keyof SurfaceDial)[];

let dial: SurfaceDial = { ...DEFAULT_SURFACE_DIAL };
const listeners = new Set<() => void>();

function notify(): void {
  for (const listener of listeners) listener();
}

/** Current dial snapshot. Stable reference until setSurfaceDial replaces it. */
export function getSurfaceDial(): SurfaceDial {
  return dial;
}

/** Merge a partial dial (only known knobs are applied) and notify subscribers. */
export function setSurfaceDial(partial: Partial<SurfaceDial>): SurfaceDial {
  if (!partial || typeof partial !== 'object') return dial;
  const next: SurfaceDial = { ...dial };
  let changed = false;
  for (const key of KNOB_KEYS) {
    if (key in partial && partial[key] !== undefined) {
      // @ts-expect-error indexed assign across the union is sound for our knob set
      next[key] = partial[key];
      changed = true;
    }
  }
  if (!changed) return dial;
  dial = next;
  notify();
  return dial;
}

export function subscribeSurfaceDial(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** React hook — re-renders the subscriber whenever a knob turns. */
export function useSurfaceDial(): SurfaceDial {
  return useSyncExternalStore(subscribeSurfaceDial, getSurfaceDial, getSurfaceDial);
}

export function __resetSurfaceDialForTests(): void {
  dial = { ...DEFAULT_SURFACE_DIAL };
  listeners.clear();
}

// --- window wiring (operator console dial) ----------------------------------
// Installed once per target, lazily, when the module first loads in a browser. A
// Proxy on the getter lets `window.__SURFACE.knob = x` route through setSurfaceDial.
const installedTargets = new WeakSet<object>();

export function installSurfaceDialWindow(target: typeof globalThis | undefined = typeof window !== 'undefined' ? window : undefined): void {
  if (!target || installedTargets.has(target)) return;
  installedTargets.add(target);
  const win = target as unknown as Record<string, unknown>;
  win.__getSurfaceDial = getSurfaceDial;
  win.__setSurfaceDial = setSurfaceDial;
  win.__resetSurfaceDial = () => setSurfaceDial({ ...DEFAULT_SURFACE_DIAL });
  Object.defineProperty(target, '__SURFACE', {
    configurable: true,
    get() {
      return new Proxy(
        { ...dial },
        {
          set(_obj, prop, value) {
            setSurfaceDial({ [prop as keyof SurfaceDial]: value } as Partial<SurfaceDial>);
            return true;
          },
        },
      );
    },
    set(value: Partial<SurfaceDial>) {
      setSurfaceDial(value);
    },
  });
}

installSurfaceDialWindow();
