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
import '../workbench/shell.css';

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

        {/* The manufacturing surface floats in the same space, only when summoned. */}
        {manufacturing && (
          <div className="sb-workbench-stage">
            <Workbench />
          </div>
        )}

        <button
          type="button"
          className="sb-mode-toggle"
          onClick={() => setMode((m) => (m === 'home' ? 'manufacture' : 'home'))}
          title={manufacturing ? 'Return to the full voyage' : 'Bring the brain to the workbench'}
        >
          <span className="sb-dot" />
          {manufacturing ? 'Return to voyage' : 'Enter workbench'}
        </button>
      </div>
    </div>
  );
}
