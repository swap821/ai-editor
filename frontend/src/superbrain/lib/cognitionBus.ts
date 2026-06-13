/**
 * cognitionBus — the superbrain's nervous system.
 *
 * A tiny module-singleton pub/sub that lets the 3D scene and the DOM HUD
 * react to the same cognition events, so the interface reads as ONE living
 * organism: a grasp tendril acquires knowledge -> the terminal logs it, the
 * intake percentages tick, the accretion disc flares.
 *
 * SSR-safe: no window/document access. Subscribers are called synchronously
 * in publish order; exceptions in one listener never break the others.
 */

export type CognitionEventType =
  /** A retrieval packet reached the cortex — knowledge absorbed. */
  | 'knowledge-acquired'
  /** The user issued a directive via the command bar. */
  | 'directive'
  /** The periodic cognition burst fired in the 3D scene. */
  | 'burst'
  /** An agent in the mesh changed posture (dispatch / report). */
  | 'agent-dispatch'
  /** A synthesis cycle completed. */
  | 'synthesis'
  /** The AI-OS paused for human approval — the organism holds its breath.
   *  This is the product's thesis rendered as an event: a supervised mind
   *  visibly deferring to its operator. */
  | 'approval-required'
  /** The operator resolved a pending approval (approve or reject). */
  | 'approval-resolved'
  /** A successful adapter poll: real link/latency/trail/metric snapshot in
   *  `data` (AiosTelemetry). Link loss publishes one with link=false. */
  | 'telemetry'
  /** The active brain for a turn: which provider/model served it and whether it
   *  stayed local. `data` carries {provider, model, privacy, task, auto}. The
   *  sovereignty row shows it; additive, so the canon idle frame is untouched. */
  | 'route';

export interface CognitionEvent {
  type: CognitionEventType;
  /** Short lore label, e.g. "MYTHOS ARCHIVE SHARD". */
  label?: string;
  /** Longer human-readable detail for the terminal feed. */
  detail?: string;
  /** 0..1 — how hard downstream visuals should react. */
  intensity?: number;
  /** Originating system, e.g. "grasp", "hud", "scene". */
  source?: string;
  /** Structured payload for data-carrying events (e.g. telemetry). */
  data?: Record<string, unknown>;
}

type Listener = (event: CognitionEvent) => void;

const listeners = new Set<Listener>();

export function subscribeCognition(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function publishCognition(event: CognitionEvent): void {
  for (const listener of listeners) {
    try {
      listener(event);
    } catch {
      // One faulty listener must never sever the rest of the nervous system.
    }
  }
}
