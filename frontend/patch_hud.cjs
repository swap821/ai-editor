const fs = require('fs');
let content = fs.readFileSync('frontend/src/superbrain/components/ui/SuperbrainHUD.tsx', 'utf8');

// replace subscribeCognition case
const start = content.indexOf("case 'telemetry': {");
const end = content.indexOf("case 'synthesis':", start);
if (start !== -1 && end !== -1) {
  content = content.slice(0, start) + content.slice(end);
}

// add subscribeTelemetry to imports
content = content.replace('getLastTelemetry,', 'getLastTelemetry, subscribeTelemetry, getLinkState,');

// add useEffect for telemetry
const effectTarget = 'const [telemetry, setTelemetry] = useState<AiosTelemetry | null>(() => getLastTelemetry());';
const newEffect = effectTarget + `
  useEffect(() => {
    return subscribeTelemetry(() => {
      const link = getLinkState();
      setLinkUp(link);
      if (!link) return;
      const t = getLastTelemetry();
      setTelemetry(t);
      if (!t) return;
      const prev = prevVerifiedRef.current;
      const delta = prev !== null && t.verified > prev ? t.verified - prev : null;
      prevVerifiedRef.current = t.verified;
      heartbeatCountRef.current += 1;
      if (delta !== null || heartbeatCountRef.current % 3 === 1) {
        appendTermLine(
          \`Telemetry · \${t.trails}t \${t.verified}v \${t.latencyMs}ms\`,
          false,
          { delta }
        );
      }
    });
  }, [appendTermLine]);`;

content = content.replace(effectTarget, newEffect);

fs.writeFileSync('frontend/src/superbrain/components/ui/SuperbrainHUD.tsx', content);
