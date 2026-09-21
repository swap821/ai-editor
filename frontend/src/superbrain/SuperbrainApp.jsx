/** One operational shell, one conversation owner, and the preserved connected organism. */
import { lazy, Suspense, useCallback, useEffect, useState } from 'react';
import BootSequence from '@/components/ui/BootSequence';
import GagosChrome from '../workbench/GagosChrome';
import SuperbrainReactiveEffects from '../workbench/SuperbrainReactiveEffects';
import { LivingWorkspaceShell } from '../livingMirror/LivingWorkspaceShell';
import { readExperienceMode, writeExperienceMode } from '../livingMirror/experienceMode';
import { startMirrorClient, stopMirrorClient } from './lib/aiosMirror';
import { useTabStore } from './lib/tabStore';
import './superbrain.css';

const WorkspaceCanvas = lazy(() => import('@/components/canvas/WorkspaceCanvas'));

export default function SuperbrainApp() {
  const [booted, setBooted] = useState(false);
  const [experienceMode, setExperienceMode] = useState(() => readExperienceMode());
  const snapshot = useTabStore();
  const working = snapshot.panels?.some((p) => p.id === snapshot.focusId && p.open)
    || snapshot.tabs.some((t) => t.id === snapshot.focusId && t.kind === 'content' && t.lifecycle !== 'retracting');
  const handleBootComplete = useCallback(() => setBooted(true), []);
  const handleExperienceModeChange = useCallback((nextMode) => {
    writeExperienceMode(nextMode);
    setExperienceMode(nextMode);
  }, []);
  useEffect(() => { void startMirrorClient(); return stopMirrorClient; }, []);
  return <div className="lm-app" data-working={working ? 'true' : 'false'} data-experience-mode={experienceMode}>
    <BootSequence onComplete={handleBootComplete} />
    <div className="lm-scene"><Suspense fallback={<p className="lm-scene-loading">Loading the organism. Operational controls remain available.</p>}>
      <WorkspaceCanvas booted={booted}><SuperbrainReactiveEffects /></WorkspaceCanvas>
    </Suspense></div>
    <main aria-label="GAGOS conversation"><GagosChrome integrated experienceMode={experienceMode} onExperienceModeChange={handleExperienceModeChange} /></main>
    <LivingWorkspaceShell experienceMode={experienceMode} />
  </div>;
}
