/**
 * The superbrain experience, extracted byte-faithful from the operator's lab
 * (GAG demo/gag-orchestrator) — same components, same shaders, same CSS, the
 * same real-data bindings (the adapter talks to this very backend). Mounted
 * only behind the ?ui=superbrain flag so the classic frontend is untouched.
 *
 * OPERATOR'S LAW — the home is PURE 3D: everything the operator sees is the
 * living being on the canvas, no 2D / DOM chrome anywhere. The only thing
 * mounted here is <WorkspaceCanvas/> (the one <Canvas> + the 3D scene). The
 * former DOM organs (CyberCursor, OrgansDock, ApprovalSafetyNet, the HUD, the
 * boot overlay, the atmosphere/grid layers) were removed; their lifecycle
 * wiring (AIOS polling, cognition bus, posture machine) lives on inside the
 * canvas so the being still arrives, listens and reacts.
 */
import WorkspaceCanvas from '@/components/canvas/WorkspaceCanvas';
import BrainstemIntake from '../workbench/BrainstemIntake';
import './superbrain.css';

export default function SuperbrainApp() {
  return (
    <div className="font-sans antialiased">
      <WorkspaceCanvas>
        <BrainstemIntake />
      </WorkspaceCanvas>
    </div>
  );
}
