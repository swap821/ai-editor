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
import { lazy, Suspense, useCallback, useState, useEffect } from 'react';
import BootSequence from '@/components/ui/BootSequence';
import GagosChrome from '../workbench/GagosChrome';
import SuperbrainReactiveEffects from '../workbench/SuperbrainReactiveEffects';
import FileTree from '../workbench/FileTree';
import TerminalPanel from '../workbench/TerminalPanel';
import CodeEditor from '../workbench/CodeEditor';
import BudgetMicroBar from '../workbench/BudgetMicroBar';
import CouncilDeliberationPanel from '../workbench/CouncilDeliberationPanel';
import EcosystemDashboard from '../workbench/EcosystemDashboard';
import MemoryBrowser from '../workbench/MemoryBrowser';
import SettingsPanel from '../workbench/SettingsPanel';
import StigmergyPanel from '../workbench/StigmergyPanel';
import VultureFeed from '../workbench/VultureFeed';
import VoiceCommandHandler from '../components/VoiceCommandHandler';
import MobileHUD from '../components/MobileHUD';
import PanelLauncher from '../workbench/PanelLauncher';
import ProductSpaces from '../workbench/ProductSpaces';
import './superbrain.css';

import { startMirrorClient, stopMirrorClient } from './lib/aiosMirror';

const WorkspaceCanvas = lazy(() => import('@/components/canvas/WorkspaceCanvas'));

export default function SuperbrainApp() {
  const [booted, setBooted] = useState(false);
  const [activeFile, setActiveFile] = useState(null);
  // Product spaces are the primary surface. Legacy panels remain available
  // through PanelLauncher, but do not cover the operator's first view.
  const [fileTreeOpen, setFileTreeOpen] = useState(false);
  const [councilOpen, setCouncilOpen] = useState(false);
  const [memoryOpen, setMemoryOpen] = useState(false);
  const [stigmergyOpen, setStigmergyOpen] = useState(false);
  const [vultureOpen, setVultureOpen] = useState(false);
  const [ecosystemOpen, setEcosystemOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [isListening] = useState(false);

  const handleBootComplete = useCallback(() => setBooted(true), []);

  useEffect(() => {
    startMirrorClient();
    return () => {
      stopMirrorClient();
    };
  }, []);

  const handleVoiceCommand = useCallback((transcript) => {
    console.log('[Voice Command Received]', transcript);
    // Ideally this would dispatch to the cognition bus or intent router
  }, []);

  return (
    <div className="font-sans antialiased" style={{ position: 'relative', width: '100vw', height: '100vh', overflow: 'hidden' }}>
      <BootSequence onComplete={handleBootComplete} />
      
      {/* Z-index: 0 */}
      <div style={{ position: 'absolute', inset: 0, zIndex: 0 }}>
        <Suspense fallback={null}>
          <WorkspaceCanvas booted={booted}>
            <SuperbrainReactiveEffects />
          </WorkspaceCanvas>
        </Suspense>
      </div>

      {/* Z-index: 10 */}
      <main aria-label="GAGOS" style={{ position: 'absolute', inset: 0, zIndex: 10, pointerEvents: 'none' }}>
        <GagosChrome />
      </main>

      <ProductSpaces />

      {/* Z-index: 15 (TerminalPanel handles its own fixed positioning) */}
      <div style={{ zIndex: 15, position: 'relative' }}>
        <TerminalPanel />
      </div>

      {/* Z-index: 20 */}
      <MobileHUD>
        <div style={{ position: 'absolute', inset: 0, zIndex: 20, pointerEvents: 'none' }}>
          <BudgetMicroBar />
          {fileTreeOpen && (
            <FileTree 
              onClose={() => setFileTreeOpen(false)} 
              onOpenFile={(file) => setActiveFile(file)} 
            />
          )}
          {activeFile && (
            <CodeEditor 
              file={activeFile} 
              onClose={() => setActiveFile(null)} 
            />
          )}
          {councilOpen && (
            <CouncilDeliberationPanel onClose={() => setCouncilOpen(false)} />
          )}
          {memoryOpen && (
            <MemoryBrowser onClose={() => setMemoryOpen(false)} />
          )}
          {stigmergyOpen && (
            <StigmergyPanel onClose={() => setStigmergyOpen(false)} />
          )}
          {vultureOpen && (
            <VultureFeed onClose={() => setVultureOpen(false)} />
          )}
          {ecosystemOpen && (
            <EcosystemDashboard onClose={() => setEcosystemOpen(false)} />
          )}
          {settingsOpen && (
            <SettingsPanel onClose={() => setSettingsOpen(false)} />
          )}
        </div>
      </MobileHUD>

      <VoiceCommandHandler
        isListening={isListening}
        onCommand={handleVoiceCommand}
      />

      <PanelLauncher
        panels={[
          { name: 'File Tree', isOpen: fileTreeOpen, setOpen: setFileTreeOpen },
          { name: 'Council', isOpen: councilOpen, setOpen: setCouncilOpen },
          { name: 'Memory', isOpen: memoryOpen, setOpen: setMemoryOpen },
          { name: 'Stigmergy', isOpen: stigmergyOpen, setOpen: setStigmergyOpen },
          { name: 'Vulture Feed', isOpen: vultureOpen, setOpen: setVultureOpen },
          { name: 'Ecosystem', isOpen: ecosystemOpen, setOpen: setEcosystemOpen },
          { name: 'Settings', isOpen: settingsOpen, setOpen: setSettingsOpen },
        ]}
      />
    </div>
  );
}
