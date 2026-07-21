const fs = require('fs');

function ensureSubscribeCognition(filepath) {
  let content = fs.readFileSync(filepath, 'utf8');
  if (content.includes('subscribeCognition') && !content.includes('cognitionBus')) {
    const importStr = "import { subscribeCognition } from '@/lib/cognitionBus';\n";
    content = importStr + content;
    fs.writeFileSync(filepath, content);
  }
}

['frontend/src/superbrain/components/ui/SuperbrainHUD.tsx',
 'frontend/src/superbrain/core/CortexEngine.tsx',
 'frontend/src/superbrain/components/canvas/SuperbrainScene.LEGACY.tsx',
 'frontend/src/superbrain/components/canvas/WorkspaceCanvas.tsx'
].forEach(ensureSubscribeCognition);

// Fix duplicate getLinkState and appendTermLine in SuperbrainHUD
let hud = fs.readFileSync('frontend/src/superbrain/components/ui/SuperbrainHUD.tsx', 'utf8');
hud = hud.replace('  getLastTelemetry, subscribeTelemetry, getLinkState,\n  getLinkState,', '  getLastTelemetry, subscribeTelemetry, getLinkState,');

const hookStart = hud.indexOf('  useEffect(() => {\n    return subscribeTelemetry(() => {');
const hookEnd = hud.indexOf('  }, [appendTermLine]);') + 23;
if (hookStart !== -1) {
  const hookContent = hud.substring(hookStart, hookEnd);
  hud = hud.substring(0, hookStart) + hud.substring(hookEnd);
  
  const appendTermLineTarget = 'const appendTermLine = useCallback(';
  const insertIndex = hud.indexOf(appendTermLineTarget);
  if (insertIndex !== -1) {
    // Find the end of appendTermLine useCallback
    let bracketCount = 1;
    let i = hud.indexOf('{', insertIndex) + 1;
    while (bracketCount > 0 && i < hud.length) {
      if (hud[i] === '{') bracketCount++;
      if (hud[i] === '}') bracketCount--;
      i++;
    }
    const endOfAppend = hud.indexOf('],', i) + 2;
    if (endOfAppend > 2) {
      hud = hud.substring(0, endOfAppend) + '\n\n' + hookContent + '\n' + hud.substring(endOfAppend);
    }
  }
}
fs.writeFileSync('frontend/src/superbrain/components/ui/SuperbrainHUD.tsx', hud);
