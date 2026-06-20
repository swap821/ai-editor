/**
 * The superbrain experience, extracted byte-faithful from the operator's lab
 * (GAG demo/gag-orchestrator) — same components, same shaders, same CSS, the
 * same real-data bindings (the adapter talks to this very backend). Mounted
 * only behind the ?ui=superbrain flag so the classic frontend is untouched.
 *
 * CHROME (2026-06-20): the home was PURE 3D, but raw in-world 3D text read as
 * floating debug labels (operator: "not professional"). The being stays the
 * diegetic 3D hero on the canvas; identity / live status / the conversation now
 * live in <GagosChrome/>, a crisp 2D product layer DOM-sibling to the canvas.
 * GagosChrome drives turns through the same adapter and cognition bus the being
 * already listens to, so the organism still arrives, listens and reacts.
 */
import WorkspaceCanvas from '@/components/canvas/WorkspaceCanvas';
import GagosChrome from '../workbench/GagosChrome';
import './superbrain.css';

export default function SuperbrainApp() {
  return (
    <div className="font-sans antialiased">
      <WorkspaceCanvas />
      <GagosChrome />
    </div>
  );
}
