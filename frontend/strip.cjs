const fs = require('fs');
const files = [
  'frontend/src/superbrain/components/canvas/CognitiveGrasp.tsx',
  'frontend/src/superbrain/components/canvas/SubsystemErrorBoundary.tsx',
  'frontend/src/superbrain/components/canvas/SuperbrainScene.LEGACY.tsx',
  'frontend/src/superbrain/components/canvas/TierGovernor.tsx',
  'frontend/src/superbrain/components/canvas/WorkspaceCanvas.tsx',
  'frontend/src/superbrain/components/ui/BootSequence.tsx',
  'frontend/src/superbrain/components/ui/SuperbrainHUD.tsx',
  'frontend/src/superbrain/core/CortexEngine.tsx',
  'frontend/src/superbrain/lib/aiosAdapter.ts'
];
files.forEach(file => {
  let content = fs.readFileSync(file, 'utf8');
  // Remove multiline publishCognition calls
  content = content.replace(/publishCognition\(\s*\{[\s\S]*?\}\s*\);?/g, '');
  // Remove import
  content = content.replace(/import\s*\{\s*publishCognition[^}]*\}\s*from\s*['\"]@?\/lib\/cognitionBus['\"];?/g, '');
  // Fix empty brackets in imports if we stripped publishCognition
  content = content.replace(/import\s*\{\s*,\s*subscribeCognition\s*\}\s*from/g, 'import { subscribeCognition } from');
  content = content.replace(/import\s*\{\s*subscribeCognition\s*,\s*\}\s*from/g, 'import { subscribeCognition } from');
  // Remove leftover host.__gagCognition = publishCognition;
  content = content.replace(/host\.__gagCognition\s*=\s*publishCognition;/g, '');
  // Clean up empty imports
  content = content.replace(/import\s*\{\s*\}\s*from\s*['\"]@?\/lib\/cognitionBus['\"];?/g, '');
  fs.writeFileSync(file, content);
});
