/**
 * SuperbrainShell — the manufacturing form as THE EMBEDDED FORGE (?ui=shell).
 *
 * The brain stays canon-framed (full, NOT docked into a band — the band broke the
 * hardcoded nerve projection). In manufacturing mode the work surfaces are mounted
 * INSIDE the one canvas via <ForgePorts/> AT the canon nerve ports (-4.8 editor /
 * +4.8 preview), so the real, unchanged 3D nerves plug straight into the real
 * Monaco + preview — the mind wired into its tools. The command line sits where the
 * spinal nerve rendezvous projects (bottom-centre). ONE persistent <WorkspaceCanvas/>;
 * home (?ui=superbrain) renders it with no children and is byte-identical.
 */
import { useState } from 'react';
import CyberCursor from '@/components/ui/CyberCursor';
import WorkspaceCanvas from '@/components/canvas/WorkspaceCanvas';
import './superbrain.css';
import CommandLine from '../workbench/CommandLine';
import ForgePorts from '../workbench/ForgePorts';
import OrgansDock from '../workbench/organs/OrgansDock';
import ApprovalSafetyNet from '../workbench/approval/ApprovalSafetyNet';
import '../workbench/shell.css';
import '../workbench/forge.css';
// Loaded AFTER superbrain.css (unlayered → beats ported @layer rules); in
// manufacturing mode it hides the canon consoles whose ports the forge re-tenants.
import '../workbench/manufacturing.css';

export default function SuperbrainShell() {
  const [mode, setMode] = useState('home'); // 'home' | 'manufacture'
  const manufacturing = mode === 'manufacture';

  return (
    <div className="font-sans antialiased">
      <CyberCursor />
      <div className={`sb-shell sb-shell--${mode}`}>
        {/* ONE persistent voyaging brain, canon-framed. In manufacturing mode the
            forge ports mount INSIDE its canvas, at the nerve ports. */}
        <div className="sb-brain-stage">
          <WorkspaceCanvas>{manufacturing ? <ForgePorts /> : null}</WorkspaceCanvas>
        </div>

        {manufacturing ? (
          /* The directive bar sits at the spinal nerve's rendezvous (bottom-centre);
             the ported .command-bar is hidden by manufacturing.css. */
          <div className="sb-dock-bar">
            <button
              type="button"
              className="sb-voyage-btn"
              onClick={() => setMode('home')}
              title="Return to the full voyage"
            >
              <span className="sb-dot" />
              Voyage
            </button>
            <CommandLine />
          </div>
        ) : (
          <button
            type="button"
            className="sb-mode-toggle"
            onClick={() => setMode('manufacture')}
            title="Wire the brain into its forge"
          >
            <span className="sb-dot" />
            Enter workbench
          </button>
        )}
      </div>

      {/* Additive, read-only governance/learning organs. Collapsed by default;
          self-portals to document.body so the shell's stacking context is
          irrelevant. Renders in BOTH home and manufacturing modes — governance is
          always observable. The canon home (?ui=superbrain via SuperbrainApp) never
          renders this shell, so it stays byte-identical. */}
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
