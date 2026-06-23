// funnelAnchorBus — the DOM<->3D bridge for the being's INTAKE FUNNEL (operator's
// idea, 2026-06-23): the chat command dock should connect to the being's TAIL — the
// cauda intake funnel where the "you speak here" rings already live — not to the
// brainstem. The scene projects the funnel's mouth (group-local, low on the spine)
// to screen pixels each frame and publishes it here; the DOM CommandDockTether reads
// it to grow a nerve from the dock DOWN into the intake mouth and pour command-beads
// into it on send. Input enters through the root intake, the anatomically true path.
//
// Module singleton, SSR-safe. Screen coords are CSS px (viewport-relative, top-left).

export interface FunnelAnchor {
  /** screen x in CSS px (viewport-relative). */
  x: number;
  /** screen y in CSS px (viewport-relative). */
  y: number;
  /** false when the funnel is behind the camera / off-screen — hide the tether. */
  visible: boolean;
  /** WORLD position of the convergence (for the 3D command nerve to reach). */
  world: [number, number, number];
  /** 0..1 phase-driven channel liveliness: blazes while RECEIVING you (intake),
   *  recedes as the being tucks its tail to work (mirrors uSprayHide). */
  intake: number;
  /** 0..1 command-bead flow toward the socket (your words entering); 0 under reduced motion. */
  flow: number;
}

let anchor: FunnelAnchor = { x: 0, y: 0, visible: false, world: [0, 0, 0], intake: 0, flow: 0 };

export function setFunnelAnchor(next: FunnelAnchor): void {
  anchor = next;
}

export function getFunnelAnchor(): FunnelAnchor {
  return anchor;
}

// Dev aid (remote placement): read the live convergence anchor from the console
// while dialing window.__FUNNEL_Y, so the cord-end socket can be placed precisely.
if (typeof window !== 'undefined') {
  (window as unknown as { __getFunnelAnchor?: () => FunnelAnchor }).__getFunnelAnchor =
    getFunnelAnchor;
}

export function __resetFunnelAnchorForTests(): void {
  anchor = { x: 0, y: 0, visible: false, world: [0, 0, 0], intake: 0, flow: 0 };
}
