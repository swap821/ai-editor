/**
 * SuperbrainShell — Phase 2 composition shell (behind ?ui=shell).
 *
 * The superbrain is the LEAD character with two forms of the SAME voyaging mind:
 *   • home        — the full voyage (the canon experience, unchanged).
 *   • manufacture — the same brain DOCKED small (still travelling), with the
 *                   workbench (Monaco editor + live preview) floating in the
 *                   same infinite space below it.
 *
 * ONE persistent <WorkspaceCanvas/> instance the whole time — switching modes
 * only re-sizes its stage (never a second canvas, which would re-run the boot
 * and double the GPU load). Product-only: the lab canon and the ported
 * superbrain.css are untouched; the dock is pure wrapper CSS (see shell.css).
 */
import { useState } from 'react';
import CyberCursor from '@/components/ui/CyberCursor';
import WorkspaceCanvas from '@/components/canvas/WorkspaceCanvas';
import './superbrain.css';
import Workbench from '../workbench/Workbench';
import CommandLine from '../workbench/CommandLine';
import '../workbench/shell.css';
// Loaded AFTER superbrain.css (unlayered → beats the ported @layer rules); hides
// the cramming HUD in manufacturing mode, scoped to .sb-shell--manufacture only.
import '../workbench/manufacturing.css';

export default function SuperbrainShell() {
  const [mode, setMode] = useState('home'); // 'home' | 'manufacture'
  const manufacturing = mode === 'manufacture';

  return (
    <div className="font-sans antialiased">
      <CyberCursor />
      <div className={`sb-shell sb-shell--${mode}`}>
        {/* The ONE persistent voyaging brain. Fullscreen at home; docked small
            (still moving) when the workbench is up. */}
        <div className="sb-brain-stage">
          <WorkspaceCanvas />
        </div>

        {/* Manufacturing form: a cheap CSS cosmos continues the infinite below the
            band, a soft seam dissolves the voyage into it, the workbench slabs
            drift in that space, and the bottom dock holds the Voyage toggle + the
            unified command line (the ported command-bar is hidden by
            manufacturing.css, so there is no collision and no 100vw escape). */}
        {manufacturing ? (
          <>
            <div className="sb-cosmos" aria-hidden="true" />
            <div className="sb-seam" aria-hidden="true" />
            <div className="sb-workbench-stage">
              <Workbench />
            </div>
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
          </>
        ) : (
          <button
            type="button"
            className="sb-mode-toggle"
            onClick={() => setMode('manufacture')}
            title="Bring the brain to the workbench"
          >
            <span className="sb-dot" />
            Enter workbench
          </button>
        )}
      </div>
    </div>
  );
}
