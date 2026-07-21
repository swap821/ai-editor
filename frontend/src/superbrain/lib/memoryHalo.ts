/**
 * memoryHalo — B4: supervised memory formation made tactile.
 *
 * Pending fact proposals (the backend's quarantined queue — nothing in it can
 * reach a prompt) orbit the cortex as narrative-green motes. The operator's
 * touch resolves them: ABSORB (approve — the mote spirals into the cortex and
 * the backend mints the fact THROUGH its contradiction check) or RELEASE
 * (reject — the mote drifts off and dims, never becoming knowledge). A
 * contradiction (409) FLARES and holds: the fact stays pending for an
 * explicit reconcile.
 *
 * This module is the halo's brain — polling, per-mote lifecycle, deterministic
 * orbit math. Pure and renderer-free; MemoryHalo.tsx is just its body.
 */
import {
  approveFactProposal,
  fetchPendingFacts,
  rejectFactProposal,
  type FactProposal,
} from './aiosAdapter';

export type MoteLifecycle =
  | 'orbiting'
  | 'presenting'
  | 'absorbing'
  | 'releasing'
  | 'flaring'
  | 'gone';

export interface HaloMote {
  proposal: FactProposal;
  lifecycle: MoteLifecycle;
  /** Render-clock seconds when the current lifecycle began; -1 = unstamped
   *  (the scene stamps it on the next frame, same pattern as the flinches). */
  lifecycleAt: number;
  /** Deterministic per-mote seed derived from the proposal id. */
  seed: number;
}

export interface HaloState {
  motes: HaloMote[];
  presentingId: number | null;
}

/** Durations (seconds) the scene uses to advance/retire lifecycle animations. */
export const HALO_TIMING = {
  absorb: 1.15,
  release: 1.0,
  flare: 1.6,
} as const;

let state: HaloState = { motes: [], presentingId: null };
const listeners = new Set<(next: HaloState) => void>();

function emit(next: HaloState): void {
  state = next;
  for (const listener of listeners) {
    try {
      listener(state);
    } catch {
      // One faulty listener never severs the rest of the nervous system.
    }
  }
}

export function getHalo(): HaloState {
  return state;
}

export function subscribeHalo(listener: (next: HaloState) => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function seedOf(id: number): number {
  // Deterministic, well-spread in [0, 2π) — golden-angle spacing by id.
  return (id * 2.399963229728653) % (Math.PI * 2);
}

/** Merge a fresh server queue into the halo. Known motes KEEP their lifecycle
 *  (a poll must never snap an animation); unknown ids are born orbiting;
 *  motes mid-resolution stay until their animation retires them even if the
 *  server no longer lists them. */
export function syncProposals(proposals: FactProposal[]): void {
  const known = new Map(state.motes.map((mote) => [mote.proposal.id, mote]));
  const fresh: HaloMote[] = proposals.map((proposal) => {
    const existing = known.get(proposal.id);
    return existing ?? { proposal, lifecycle: 'orbiting', lifecycleAt: -1, seed: seedOf(proposal.id) };
  });
  const freshIds = new Set(proposals.map((proposal) => proposal.id));
  const inFlight = state.motes.filter(
    (mote) =>
      !freshIds.has(mote.proposal.id) &&
      (mote.lifecycle === 'absorbing' || mote.lifecycle === 'releasing'),
  );
  const presentingSurvives = [...fresh, ...inFlight].some(
    (mote) => mote.proposal.id === state.presentingId,
  );
  emit({
    motes: [...fresh, ...inFlight],
    presentingId: presentingSurvives ? state.presentingId : null,
  });
}

function setLifecycle(id: number, lifecycle: MoteLifecycle): void {
  emit({
    ...state,
    motes: state.motes.map((mote) =>
      mote.proposal.id === id ? { ...mote, lifecycle, lifecycleAt: -1 } : mote,
    ),
  });
}

/** The scene stamps an unstamped lifecycle with its render-clock time. */
export function stampLifecycle(id: number, clockSeconds: number): void {
  state = {
    ...state,
    motes: state.motes.map((mote) =>
      mote.proposal.id === id && mote.lifecycleAt < 0
        ? { ...mote, lifecycleAt: clockSeconds }
        : mote,
    ),
  };
}

/** Bring one mote forward to present its triple; only one presents at a time. */
export function presentMote(id: number): void {
  if (!state.motes.some((mote) => mote.proposal.id === id && mote.lifecycle === 'orbiting')) return;
  emit({
    presentingId: id,
    motes: state.motes.map((mote) => {
      if (mote.proposal.id === id) return { ...mote, lifecycle: 'presenting', lifecycleAt: -1 };
      if (mote.lifecycle === 'presenting') return { ...mote, lifecycle: 'orbiting', lifecycleAt: -1 };
      return mote;
    }),
  });
}

/** Send the presenting mote back to orbit without resolving it. */
export function dismissPresentation(): void {
  if (state.presentingId === null) return;
  emit({
    presentingId: null,
    motes: state.motes.map((mote) =>
      mote.lifecycle === 'presenting' ? { ...mote, lifecycle: 'orbiting', lifecycleAt: -1 } : mote,
    ),
  });
}

/** ABSORB: the operator mints this fact. Optimistically spirals inward; a
 *  contradiction flares and returns the mote to orbit (still pending on the
 *  server, awaiting reconcile); a failure returns it to orbit unchanged. */
export async function absorbMote(id: number): Promise<void> {
  setLifecycle(id, 'absorbing');
  if (state.presentingId === id) emit({ ...state, presentingId: null });
  const outcome = await approveFactProposal(id);
  if (outcome === 'approved') {
    // The animation retires it; the next sync no longer lists it.
    return;
  }
  setLifecycle(id, outcome === 'contradiction' ? 'flaring' : 'orbiting');
}

/** RELEASE: the operator declines — the mote drifts away, never knowledge. */
export async function releaseMote(id: number): Promise<void> {
  setLifecycle(id, 'releasing');
  if (state.presentingId === id) emit({ ...state, presentingId: null });
  const ok = await rejectFactProposal(id);
  if (!ok) setLifecycle(id, 'orbiting');
}

/** The scene retires a mote once its exit animation has fully played. */
export function retireMote(id: number): void {
  emit({
    presentingId: state.presentingId === id ? null : state.presentingId,
    motes: state.motes.filter((mote) => mote.proposal.id !== id),
  });
}

/** A flare has finished burning: the contradiction mote returns to orbit. */
export function settleFlare(id: number): void {
  const mote = state.motes.find((entry) => entry.proposal.id === id);
  if (mote?.lifecycle === 'flaring') setLifecycle(id, 'orbiting');
}

/** Deterministic orbit offset (group-local, relative to the cortex anchor).
 *  A slow ring with a gentle vertical bob; reduced motion pins each mote to
 *  its seed angle (a static constellation, no drift). */
export function moteOrbitOffset(
  seed: number,
  tSeconds: number,
  reducedMotion: boolean,
): [number, number, number] {
  const angle = reducedMotion ? seed : seed + tSeconds * 0.12;
  const radius = 0.55 + 0.08 * Math.sin(seed * 3.1);
  const bob = reducedMotion ? 0 : 0.045 * Math.sin(tSeconds * 0.6 + seed * 2.0);
  return [
    Math.cos(angle) * radius,
    0.16 + bob + 0.06 * Math.sin(seed * 5.7),
    Math.sin(angle) * radius * 0.62,
  ];
}

let stopPolling: (() => void) | null = null;

/** Poll the pending queue on a slow cadence. Idempotent; returns stop. */
export function startHaloPolling(intervalMs = 20_000): () => void {
  if (typeof window === 'undefined') return () => undefined;
  if (stopPolling) return stopPolling;
  const tick = async (): Promise<void> => {
    syncProposals(await fetchPendingFacts());
  };
  void tick();
  const handle = window.setInterval(() => void tick(), intervalMs);
  stopPolling = () => {
    window.clearInterval(handle);
    stopPolling = null;
  };
  return stopPolling;
}

export function __resetHaloForTests(): void {
  state = { motes: [], presentingId: null };
}

/** Dev-only drive/inspect hooks (house pattern: __POINTFIELD, __injectApproval).
 *  Lets the operator or a live session exercise the EXACT same code paths the
 *  3D touch targets call — absorb/release here IS the click's path. */
export function installHaloDevHooks(): void {
  if (typeof window === 'undefined' || process.env.NODE_ENV === 'production') return;
  (window as unknown as { __HALO?: unknown }).__HALO = {
    state: getHalo,
    present: presentMote,
    dismiss: dismissPresentation,
    absorb: (id: number) => void absorbMote(id),
    release: (id: number) => void releaseMote(id),
    sync: () => void fetchPendingFacts().then(syncProposals),
  };
}
