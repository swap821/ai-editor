import type { MaterializedTabKind } from './tabStore';

export type Vec3Tuple = [number, number, number];

export interface LivingWorkspacePoseInput {
  kind: MaterializedTabKind;
  focused: boolean;
  targetLocal: Vec3Tuple;
  waitingIndex?: number;
  viewportWidth?: number;
  viewportHeight?: number;
  /** points-being: born tab grows as a LATERAL PEER beside the being (poster phase 4). */
  points?: boolean;
  /** number of active work tabs — drives the orchestration (2+) vs single-tab layout. */
  workCount?: number;
}

export interface LivingWorkspacePose {
  targetLocal: Vec3Tuple;
  scale: number;
  opacity: number;
  tubeOpacity: number;
}

export interface BrainPresenceInput {
  workspaceCount: number;
  viewportWidth?: number;
  viewportHeight?: number;
  /** points-being: dock the being clearly smaller on 2+ tabs so the center-forward focus tab owns the middle. */
  points?: boolean;
}

export interface BrainPresenceLayout {
  mode: 'rest' | 'docked';
  mainBrainScale: number;
  /** points orchestration: raise the being so the brain crowns the top (on top). */
  mainBrainOffsetY: number;
  miniBrainScale: number;
  miniBrainOpacity: number;
  miniBrainPosition: Vec3Tuple;
  pointerInfluence: number;
  compactness: number;
}

const ACTIVE_WORKSPACE_TARGET: Vec3Tuple = [0, -1.04, 0.82];

const WAITING_SLOTS: readonly Vec3Tuple[] = [
  [1.36, -1.08, 0.18],
  [1.18, -1.62, 0.08],
  [-1.34, -2.28, 0.0],
  [-1.44, -1.54, -0.04],
  [1.42, -2.72, -0.04],
  [-1.48, -2.86, -0.08],
];

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function tuple(x: number, y: number, z: number): Vec3Tuple {
  return [Number(x.toFixed(4)), Number(y.toFixed(4)), Number(z.toFixed(4))];
}

function round3(value: number): number {
  return Number(value.toFixed(3));
}

function viewportCompactness(width = 1440, height = 900): number {
  const safeWidth = Math.max(1, width);
  const safeHeight = Math.max(1, height);
  const aspect = safeWidth / safeHeight;
  const narrow = clamp((1.45 - aspect) / 0.65, 0, 1);
  const short = clamp((760 - safeHeight) / 360, 0, 1);
  return round3(clamp(Math.max(narrow, short * 0.85), 0, 1));
}

function deriveWaitingSlot(waitingIndex = 0): Vec3Tuple {
  const index = Math.max(0, waitingIndex);
  const slot = WAITING_SLOTS[index % WAITING_SLOTS.length];
  const ring = Math.floor(index / WAITING_SLOTS.length);
  const side = slot[0] < 0 ? -1 : 1;
  return tuple(
    slot[0] + side * ring * 0.16,
    slot[1] - ring * 0.08,
    slot[2] - ring * 0.05,
  );
}

export function deriveLivingWorkspacePose(input: LivingWorkspacePoseInput): LivingWorkspacePose {
  const compactness = viewportCompactness(input.viewportWidth, input.viewportHeight);

  if (input.kind === 'input') {
    return {
      targetLocal: input.targetLocal,
      scale: 1,
      opacity: 1,
      tubeOpacity: 1,
    };
  }

  if (input.focused) {
    // POSTER phase 4 (points being): the born tab is a LATERAL PEER beside the
    // being — it grows OUT to the side at ~cortex-mid height, not a panel tucked
    // low-center over the spine/cauda. The offset is brain-local so it rotates
    // WITH the being (stays a side-peer under orbit, never a fixed world-right).
    if (input.points) {
      // LOCKED ORCHESTRATION MODEL (2+ tabs): the attended tab owns DEAD-CENTER +
      // FORWARD — large, bright, pulled toward the viewer; the being docks small to
      // clear the center. (1 tab = "a tab is born" → the lateral peer below.)
      if ((input.workCount ?? 1) >= 2) {
        // HUD offsets (screen right/up): the focus sits CENTER but just BELOW the
        // docked mini-brain (prototype: brain on top, active tab center). Sized so
        // it never engulfs the being. MaterializedTab places it camera-relative.
        return {
          targetLocal: tuple(0, -0.34 + compactness * 0.06, 1.2),
          scale: round3(clamp(0.82 - compactness * 0.16, 0.6, 0.82)),
          opacity: 1,
          tubeOpacity: 1,
        };
      }
      // SINGLE tab — beside the CORTEX (poster panel 4: the born tab is a brain-
      // sized peer at cortex height, pulled forward), brain-local so it orbits.
      return {
        targetLocal: tuple(
          1.05 + compactness * 0.18,
          0.12 + compactness * 0.2,
          0.78 - compactness * 0.04,
        ),
        scale: round3(clamp(1.08 - compactness * 0.42, 0.72, 1.08)),
        opacity: 1,
        tubeOpacity: 1,
      };
    }
    return {
      targetLocal: tuple(
        ACTIVE_WORKSPACE_TARGET[0] + compactness * 0.44,
        ACTIVE_WORKSPACE_TARGET[1] + compactness * 0.3,
        ACTIVE_WORKSPACE_TARGET[2] - compactness * 0.04,
      ),
      scale: round3(clamp(1.2 - compactness * 0.44, 0.76, 1.2)),
      opacity: 1,
      tubeOpacity: 1,
    };
  }

  const index = Math.max(0, input.waitingIndex ?? 0);

  // ORCHESTRATION (poster phase 5, points being): waiting tabs sit at their OWN
  // vertebra seat (input.targetLocal), pushed BACK + dimmer with depth — "vertebrae
  // are addressable seats", front=focus / back=waiting. The seat offset is
  // brain-local so each tab stays on its vertebra under orbit.
  if (input.points) {
    // LOCKED ORCHESTRATION MODEL: waiting tabs park in the FOUR CORNERS — small,
    // dim, idling, nerve-tethered from the spine; pulled to center when attended.
    // index -> TL, TR, BL, BR; a 5th+ recesses deeper. Brain-local (rides orbit).
    const CORNERS: readonly Vec3Tuple[] = [
      [-1.32, 0.62, 0.25], // top-left
      [1.32, 0.62, 0.25], // top-right
      [-1.32, -1.02, 0.25], // bottom-left
      [1.32, -1.02, 0.25], // bottom-right
    ];
    const ring = Math.floor(index / 4);
    const [cx, cy, cz] = CORNERS[index % 4];
    return {
      targetLocal: tuple(cx * (1 + ring * 0.1), cy - ring * 0.22, cz - ring * 0.12),
      scale: round3(clamp(0.42 - ring * 0.05, 0.26, 0.42)),
      opacity: round3(clamp(0.4 - ring * 0.08, 0.2, 0.4)),
      tubeOpacity: round3(clamp(0.4 - ring * 0.06, 0.2, 0.4)),
    };
  }

  const waitingSlot = deriveWaitingSlot(index);
  return {
    targetLocal: tuple(
      waitingSlot[0] * (1 - compactness * 0.18),
      waitingSlot[1] + compactness * 0.16,
      waitingSlot[2] + compactness * 0.02,
    ),
    scale: round3(clamp(0.54 - index * 0.045 - compactness * 0.06, 0.28, 0.54)),
    opacity: round3(clamp(0.34 - index * 0.032 - compactness * 0.035, 0.14, 0.34)),
    tubeOpacity: round3(clamp(0.36 - index * 0.035 - compactness * 0.035, 0.14, 0.36)),
  };
}

export function deriveBrainPresenceLayout(input: BrainPresenceInput): BrainPresenceLayout {
  const workspaceCount = Math.max(0, input.workspaceCount);
  const mode: BrainPresenceLayout['mode'] = workspaceCount > 0 ? 'docked' : 'rest';
  const load = clamp((workspaceCount - 1) / 5, 0, 1);
  const compactness = viewportCompactness(input.viewportWidth, input.viewportHeight);

  if (mode === 'rest') {
    return {
      mode,
      mainBrainScale: 1,
      mainBrainOffsetY: 0,
      miniBrainScale: 0.205,
      miniBrainOpacity: 0.5,
      miniBrainPosition: [0.44, 0.16, 1.12],
      pointerInfluence: 1,
      compactness,
    };
  }

  // SOUL P1: in points ORCHESTRATION (2+ tabs) the brain CROWNS the top and SHRINKS
  // CONTINUOUSLY with tab count (it delegates attention down to the body as work
  // grows). 1 tab keeps the full being (the lateral-peer materialization). Mesh keeps
  // the mild dock. Tuned values; the BrainModel eases toward these.
  const pointsOrchestrating = !!input.points && workspaceCount >= 2;

  return {
    mode,
    mainBrainScale: round3(
      input.points
        ? pointsOrchestrating
          ? clamp(1.04 - workspaceCount * 0.13 - compactness * 0.04, 0.42, 0.78) // 2→0.78,3→0.65,4→0.52,5→0.42
          : clamp(1 - load * 0.16 - compactness * 0.05, 0.9, 1) // 1 tab: ~full
        : clamp(1 - load * 0.16 - compactness * 0.07, 0.76, 1),
    ),
    // raise the being so the (small) brain sits at the top of frame, spine descending
    // beneath it; more tabs -> a touch higher. Only when points-orchestrating.
    mainBrainOffsetY: round3(pointsOrchestrating ? clamp(1.1 + (workspaceCount - 2) * 0.12, 1.1, 1.7) : 0),
    miniBrainScale: round3(clamp(0.205 - workspaceCount * 0.007 - compactness * 0.03, 0.108, 0.205)),
    miniBrainOpacity: round3(clamp(0.68 + load * 0.18 - compactness * 0.04, 0.58, 0.88)),
    miniBrainPosition: tuple(0, 0.26 + compactness * 0.14 - load * 0.04, 1.06 + compactness * 0.04 - load * 0.035),
    pointerInfluence: round3(clamp(0.14 - load * 0.06 - compactness * 0.05, 0.025, 0.14)),
    compactness,
  };
}
