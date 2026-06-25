/**
 * The superbrain experience — the single official frontend at the clean root /.
 *
 * CHROME (2026-06-20): the home was PURE 3D, but raw in-world 3D text read as
 * floating debug labels (operator: "not professional"). The being stays the
 * diegetic 3D hero on the canvas; identity / live status / the conversation now
 * live in <GagosChrome/>, a crisp 2D product layer DOM-sibling to the canvas.
 * GagosChrome drives turns through the same adapter and cognition bus the being
 * already listens to, so the organism still arrives, listens and reacts.
 */
import { lazy, Suspense } from 'react';
import GagosChrome from '../workbench/GagosChrome';
import SuperbrainReactiveEffects from '../workbench/SuperbrainReactiveEffects';
import './superbrain.css';

const WorkspaceCanvas = lazy(() => import('@/components/canvas/WorkspaceCanvas'));

export default function SuperbrainApp() {
  return (
    <div className="font-sans antialiased">
      <Suspense fallback={null}>
        <WorkspaceCanvas>
          <SuperbrainReactiveEffects />
        </WorkspaceCanvas>
      </Suspense>
      <main aria-label="GAGOS">
        <GagosChrome />
      </main>
    </div>
  );
}
