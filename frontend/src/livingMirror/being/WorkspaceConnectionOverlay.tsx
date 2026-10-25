import type { RefObject } from 'react';

export function WorkspaceConnectionOverlay({ overlayRef }: { overlayRef: RefObject<SVGSVGElement | null> }) {
  return <svg ref={overlayRef} className="lm-workspace-connection" aria-hidden="true" focusable="false" style={{ visibility: 'hidden' }}>
    <path d="" pathLength="1" strokeDasharray="1" strokeDashoffset="0" /><circle r="3" style={{ visibility: 'hidden' }} />
  </svg>;
}
