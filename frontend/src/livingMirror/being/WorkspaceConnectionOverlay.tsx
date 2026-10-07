import { useCallback, useLayoutEffect, useRef, type RefObject } from 'react';
import { useFrame } from '@react-three/fiber';
import { Matrix4, Vector3 } from 'three';
import type { TabSnapshot } from '../../superbrain/lib/tabStore';
import { SEGMENT_ANCHORS } from '../../superbrain/lib/spineAnatomy';
import { readBeingMode } from '../../superbrain/lib/beingMode';
import { copyBodyGroupWorldMatrix, getBrainDockScale, getSpineFusion } from '../../superbrain/lib/spineFusionBus';
import { projectWorkspaceConnection, type ConnectionRect } from './workspaceConnection';

export function WorkspaceConnectionOverlay({ overlayRef }: { overlayRef: RefObject<SVGSVGElement | null> }) {
  return <svg ref={overlayRef} className="lm-workspace-connection" aria-hidden="true" focusable="false" style={{ visibility: 'hidden' }}>
    <path d="" /><circle r="3" />
  </svg>;
}
/** One spatial connection, not a stream, work status, verification or authority. */
export function WorkspaceConnectionProjection({ overlayRef, snapshot }: {
  overlayRef: RefObject<SVGSVGElement | null>;
  snapshot: TabSnapshot;
}) {
  const panel = snapshot.panels?.find((candidate) => candidate.open && candidate.id === snapshot.focusId);
  const artifact = snapshot.tabs.find((candidate) => candidate.id === snapshot.focusId && candidate.kind === 'content' && candidate.lifecycle !== 'retracting');
  const seat = (panel ?? artifact)?.seatIndex;
  const scratch = useRef({ origin: new Vector3(), projected: new Vector3(), world: new Matrix4() });
  const bounds = useRef<{ canvas: ConnectionRect; plane: ConnectionRect; overlay: ConnectionRect } | null>(null);
  const clear = useCallback(() => {
    const svg = overlayRef.current;
    const path = svg?.querySelector('path');
    if (path?.getAttribute('d')) path.setAttribute('d', '');
    if (svg && svg.style.visibility !== 'hidden') svg.style.visibility = 'hidden';
  }, [overlayRef]);
  useLayoutEffect(() => {
    const svg = overlayRef.current;
    const root = svg?.closest('.lm-app');
    const plane = root?.querySelector<HTMLElement>('.lm-surface');
    const canvas = root?.querySelector('canvas');
    bounds.current = null;
    clear();
    if (!svg || !plane || !canvas) return;
    const measure = () => {
      if (plane.hidden) { bounds.current = null; clear(); return; }
      const overlay = svg.getBoundingClientRect();
      bounds.current = { canvas: canvas.getBoundingClientRect(), plane: plane.getBoundingClientRect(), overlay };
      svg.setAttribute('viewBox', `0 0 ${overlay.width} ${overlay.height}`);
    };
    measure();
    const observer = typeof ResizeObserver === 'function' ? new ResizeObserver(measure) : null;
    [svg, plane, canvas].forEach((element) => observer?.observe(element));
    const attributes = new MutationObserver(measure);
    attributes.observe(root!, { attributes: true, attributeFilter: ['data-working', 'data-being-focus', 'data-experience-mode', 'style'] });
    attributes.observe(plane, { attributes: true, attributeFilter: ['hidden', 'data-workspace-collapsed'] });
    window.addEventListener('resize', measure);
    window.visualViewport?.addEventListener('resize', measure);
    window.visualViewport?.addEventListener('scroll', measure);
    return () => {
      observer?.disconnect(); attributes.disconnect();
      window.removeEventListener('resize', measure);
      window.visualViewport?.removeEventListener('resize', measure);
      window.visualViewport?.removeEventListener('scroll', measure);
      bounds.current = null; clear();
    };
  }, [clear, overlayRef, snapshot.focusId]);

  useFrame(({ camera }) => {
    const svg = overlayRef.current;
    const raw = typeof seat === 'number' && Number.isInteger(seat) ? SEGMENT_ANCHORS[seat] : undefined;
    const fusion = getSpineFusion();
    const points = readBeingMode() === 'points';
    if (!svg || !raw || !bounds.current || (points && !fusion.ready)
      || !copyBodyGroupWorldMatrix(scratch.current.world)) { clear(); return; }
    const origin = scratch.current.origin.copy(raw);
    if (points) origin.multiplyScalar(fusion.spineScale).add(scratch.current.projected.set(...fusion.weld));
    const connection = projectWorkspaceConnection({
      origin, bodyWorld: scratch.current.world, dockScale: getBrainDockScale(), camera, ...bounds.current,
    }, scratch.current.projected);
    if (!connection) { clear(); return; }
    const path = svg.querySelector('path');
    // Avoid DOM writes while a still/reduced-motion body remains at the same pixel.
    if (path?.getAttribute('d') !== connection.path) {
      path?.setAttribute('d', connection.path);
      const contact = svg.querySelector('circle');
      contact?.setAttribute('cx', String(connection.target.x));
      contact?.setAttribute('cy', String(connection.target.y));
    }
    if (svg.style.visibility !== 'visible') svg.style.visibility = 'visible';
  });
  return null;
}
