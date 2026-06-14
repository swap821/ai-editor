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
import ApprovalSafetyNet from '../workbench/approval/ApprovalSafetyNet';

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
      {/* Additive approval safety-net — reconciles the persisted adapter pending-approval
          truth on a poll/bus/visibility belt-and-suspenders, so a missed
          'approval-required' bus event can never leave a paused run with no clickable
          AUTHORIZE/REJECT. Self-portals to document.body; appears ONLY after a grace
          window the canon panel failed to fill (true fallback, zero double UI). Mounted
          on BOTH seams so the hang is caught wherever a turn can pause. */}
      <ApprovalSafetyNet />
    </div>
  );
}
