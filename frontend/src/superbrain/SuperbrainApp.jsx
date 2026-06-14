/**
 * The superbrain experience, extracted byte-faithful from the operator's lab
 * (GAG demo/gag-orchestrator) — same components, same shaders, same CSS, the
 * same real-data bindings (the adapter talks to this very backend). Mounted
 * only behind the ?ui=superbrain flag so the classic frontend is untouched.
 */
import CyberCursor from '@/components/ui/CyberCursor';
import WorkspaceCanvas from '@/components/canvas/WorkspaceCanvas';
import './superbrain.css';
import OrgansDock from '../workbench/organs/OrgansDock';

export default function SuperbrainApp() {
  return (
    <div className="font-sans antialiased">
      <CyberCursor />
      <WorkspaceCanvas />
      {/* Additive, read-only governance/learning organs — mirrors SuperbrainShell.
          COLLAPSED BY DEFAULT and self-portals to document.body, so the canon home
          looks byte-identical except the small top-right ▣ ORGANS tab. The poll that
          feeds it (getAutonomy/getKnownTrails/telemetry) is already started by
          <WorkspaceCanvas/> once booted, so the organs get real data here too. */}
      <OrgansDock />
    </div>
  );
}
