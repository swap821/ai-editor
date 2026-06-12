/**
 * The superbrain experience, extracted byte-faithful from the operator's lab
 * (GAG demo/gag-orchestrator) — same components, same shaders, same CSS, the
 * same real-data bindings (the adapter talks to this very backend). Mounted
 * only behind the ?ui=superbrain flag so the classic frontend is untouched.
 */
import CyberCursor from '@/components/ui/CyberCursor';
import WorkspaceCanvas from '@/components/canvas/WorkspaceCanvas';
import './superbrain.css';

export default function SuperbrainApp() {
  return (
    <div className="font-sans antialiased">
      <CyberCursor />
      <WorkspaceCanvas />
    </div>
  );
}
