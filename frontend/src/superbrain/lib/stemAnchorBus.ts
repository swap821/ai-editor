// stemAnchorBus — bridges the 3D being and the DOM NeuralCommandDock. The scene
// projects the being's BRAINSTEM (where the cord meets the head) to screen pixels
// each frame and publishes it here; the DOM CommandDockTether reads it to draw a
// nerve from the dock up into the living stem (and run command-beads along it on
// send). This is the DOM↔3D bridge that makes the dock feel grown FROM the being,
// not pasted over it.
//
// Module singleton, SSR-safe (no window/document at module scope). Screen coords
// are CSS pixels relative to the viewport (top-left origin), matching DOM layout.

export interface StemAnchor {
  /** screen x in CSS px (viewport-relative). */
  x: number;
  /** screen y in CSS px (viewport-relative). */
  y: number;
  /** false when the stem is behind the camera / off-screen — hide the tether. */
  visible: boolean;
}

let anchor: StemAnchor = { x: 0, y: 0, visible: false };

export function setStemAnchor(next: StemAnchor): void {
  anchor = next;
}

export function getStemAnchor(): StemAnchor {
  return anchor;
}

export function __resetStemAnchorForTests(): void {
  anchor = { x: 0, y: 0, visible: false };
}
