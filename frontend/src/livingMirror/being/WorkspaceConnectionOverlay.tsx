import { useCallback, useLayoutEffect, useRef, type RefObject } from 'react';
import { useFrame } from '@react-three/fiber';
import { Matrix4, Vector3 } from 'three';
import type { TabSnapshot } from '../../superbrain/lib/tabStore';
import { SEGMENT_ANCHORS } from '../../superbrain/lib/spineAnatomy';
import { readBeingMode } from '../../superbrain/lib/beingMode';
import { copyBodyGroupWorldMatrix, getBrainDockScale, getCortexAnchor, getSpineFusion } from '../../superbrain/lib/spineFusionBus';
import type { WorkPlaneAttentionTarget } from '../../superbrain/lib/brainAttentionPosture';
import { MATERIALIZATION_REACH_MS } from '../../superbrain/lib/materializationTiming';
import { easeOutExpo } from '../../superbrain/lib/motionEasing';
import { useReducedMotion } from '../../superbrain/lib/reducedMotion';
import { projectWorkspaceConnection, type ConnectionRect } from './workspaceConnection';

export function WorkspaceConnectionOverlay({ overlayRef }: { overlayRef: RefObject<SVGSVGElement | null> }) {
  return <svg ref={overlayRef} className="lm-workspace-connection" aria-hidden="true" focusable="false" style={{ visibility: 'hidden' }}>
    <path d="" pathLength="1" strokeDasharray="1" strokeDashoffset="0" /><circle r="3" style={{ visibility: 'hidden' }} />
  </svg>;
}
/** One spatial connection, not a stream, work status, verification or authority. */
export function WorkspaceConnectionProjection({ overlayRef, snapshot, attentionTargetRef }: {
  overlayRef: RefObject<SVGSVGElement | null>;
  snapshot: TabSnapshot;
  attentionTargetRef?: RefObject<WorkPlaneAttentionTarget | null>;
}) {
  const reducedMotion = useReducedMotion();
  const panel = snapshot.panels?.find((candidate) => candidate.open && candidate.id === snapshot.focusId);
  const artifact = snapshot.tabs.find((candidate) => candidate.id === snapshot.focusId && candidate.kind === 'content' && candidate.lifecycle !== 'retracting');
  // Same ownership contract as useDomWorkPlane: only the current adapter's
  // conversation approval delegates its slab to this readable dialog. A lab
  // proposal or missing seat must never borrow the selected reader's address.
  const approval = snapshot.tabs.find((candidate) => candidate.kind === 'approval'
    && candidate.lifecycle !== 'retracting' && candidate.approval?.requestRef === 'conversation-approval');
  const readerSeat = (panel ?? artifact)?.seatIndex;
  const scratch = useRef({ origin: new Vector3(), projected: new Vector3(), cortex: new Vector3(), world: new Matrix4(),
    target: { targetId: '', lateral: 0, vertical: 0 } });
  const bounds = useRef<{ canvas: ConnectionRect; plane: ConnectionRect; overlay: ConnectionRect;
    occluders: ConnectionRect[]; seat: number; decision: boolean; targetId: string } | null>(null);
  const retireAttention = useCallback(() => {
    if (attentionTargetRef?.current === scratch.current.target) attentionTargetRef.current = null;
  }, [attentionTargetRef]);
  const paint = useRef({ svg: null as SVGSVGElement | null, path: null as SVGPathElement | null,
    contact: null as SVGCircleElement | null, pathData: '', offset: '', contactVisibility: 'hidden', visible: false });
  const clear = useCallback(() => {
    const current = paint.current;
    if (current.pathData !== '') { current.path?.setAttribute('d', ''); current.pathData = ''; }
    // A child's explicit visible value overrides its parent's hidden value.
    // Retire both paints on Close, unavailable geometry and renderer teardown.
    if (current.contactVisibility !== 'hidden') {
      if (current.contact) current.contact.style.visibility = 'hidden';
      current.contactVisibility = 'hidden';
    }
    if (current.visible) { if (current.svg) current.svg.style.visibility = 'hidden'; current.visible = false; }
  }, []);
  useLayoutEffect(() => {
    const svg = overlayRef.current;
    const boundPaint = paint.current;
    // The overlay owns these nodes and paint values. Cache them at binding,
    // not by querying/reading attributes or styles during every render frame.
    boundPaint.svg = svg;
    boundPaint.path = svg?.querySelector('path') ?? null;
    boundPaint.contact = svg?.querySelector('circle') ?? null;
    const root = svg?.closest('.lm-app');
    const canvas = root?.querySelector('canvas');
    bounds.current = null;
    retireAttention();
    clear();
    if (!svg || !root || !canvas) return;
    let plane: HTMLElement | null = null;
    let observedOccluders: Element[] = [];
    const watchMutations = () => {
      attributes.disconnect();
      attributes.observe(root, { attributes: true, attributeFilter: ['data-working', 'data-being-focus', 'data-experience-mode', 'style'] });
      if (plane) attributes.observe(plane, { attributes: true, attributeFilter: ['hidden', 'data-workspace-id', 'data-workspace-collapsed', 'style', 'class'] });
      // Direct owner changes only, not every streaming text mutation.
      for (const owner of root.querySelectorAll('.gagos-chrome, .lm-stop')) attributes.observe(owner,
        { childList: true, attributes: true, attributeFilter: ['data-approval-pending'] });
    };
    const measure = () => {
      const pendingOwner = root.querySelector('.gagos-chrome[data-approval-pending="true"]');
      const decision = pendingOwner !== null;
      const nextPlane = decision
        ? pendingOwner.querySelector<HTMLElement>('.approval-panel[role="alertdialog"]')
        : root.querySelector<HTMLElement>('.lm-surface');
      if (nextPlane !== plane) {
        if (plane) observer?.unobserve(plane);
        plane = nextPlane;
        if (plane) observer?.observe(plane);
        watchMutations();
      }
      const seat = decision ? approval?.seatIndex : readerSeat;
      const targetId = decision ? approval?.id : panel?.id ?? artifact?.id;
      const style = plane ? getComputedStyle(plane) : null;
      if (!plane || plane.closest('[hidden]') || style?.display === 'none' || style?.visibility === 'hidden'
        || !targetId || (!decision && plane.dataset.workspaceId !== targetId)
        || typeof seat !== 'number' || !Number.isInteger(seat) || !SEGMENT_ANCHORS[seat]) {
        bounds.current = null; retireAttention(); clear(); return;
      }
      const overlay = svg.getBoundingClientRect();
      const nextOccluders = Array.from(root.querySelectorAll('.approval-panel, .lm-stop__detail')).filter(element => element !== plane);
      for (const element of observedOccluders) if (!nextOccluders.includes(element)) observer?.unobserve(element);
      for (const element of nextOccluders) if (!observedOccluders.includes(element)) observer?.observe(element);
      observedOccluders = nextOccluders;
      bounds.current = { canvas: canvas.getBoundingClientRect(), plane: plane.getBoundingClientRect(), overlay,
        seat, decision, targetId, occluders: nextOccluders.map(element => element.getBoundingClientRect()).filter(rect => rect.width > 0 && rect.height > 0) };
      svg.setAttribute('viewBox', `0 0 ${overlay.width} ${overlay.height}`);
      svg.setAttribute('data-connection-kind', decision ? 'approval' : 'workspace');
    };
    const observer = typeof ResizeObserver === 'function' ? new ResizeObserver(measure) : null;
    const attributes = new MutationObserver(measure);
    watchMutations();
    measure();
    [svg, canvas].forEach((element) => observer?.observe(element));
    window.addEventListener('resize', measure);
    window.visualViewport?.addEventListener('resize', measure);
    window.visualViewport?.addEventListener('scroll', measure);
    return () => {
      observer?.disconnect(); attributes.disconnect();
      window.removeEventListener('resize', measure);
      window.visualViewport?.removeEventListener('resize', measure);
      window.visualViewport?.removeEventListener('scroll', measure);
      bounds.current = null; retireAttention(); clear();
      boundPaint.svg = null; boundPaint.path = null; boundPaint.contact = null;
    };
  }, [approval?.id, approval?.seatIndex, artifact?.id, clear, overlayRef, panel?.id, readerSeat, retireAttention, snapshot.focusId]);

  useFrame(({ camera }) => {
    const current = paint.current;
    const { svg, path, contact } = current;
    const raw = bounds.current ? SEGMENT_ANCHORS[bounds.current.seat] : undefined;
    const fusion = getSpineFusion();
    const points = readBeingMode() === 'points';
    if (!svg || !raw || !bounds.current || (points && !fusion.ready)
      || !copyBodyGroupWorldMatrix(scratch.current.world)) { retireAttention(); clear(); return; }
    // The readable plane and cable share ownership, not a fabricated work
    // signal. Project the actual cortex (not its lower feeding vertebra).
    // Cached layout plus existing live matrices only; no frame-loop DOM read,
    // React update, allocation or independently advancing attention clock.
    if (attentionTargetRef) {
      const { canvas, plane, targetId } = bounds.current;
      const head = scratch.current.cortex.set(...getCortexAnchor()).multiplyScalar(getBrainDockScale())
        .applyMatrix4(scratch.current.world).project(camera);
      const canvasValid = Number.isFinite(canvas.left + canvas.top + canvas.width + canvas.height) && canvas.width > 0 && canvas.height > 0;
      const planeValid = Number.isFinite(plane.left + plane.top + plane.width + plane.height) && plane.width > 0 && plane.height > 0;
      if (!canvasValid || !planeValid || !Number.isFinite(head.x + head.y + head.z)
        || Math.abs(head.x) > 1 || Math.abs(head.y) > 1 || Math.abs(head.z) > 1) retireAttention();
      else {
        const target = scratch.current.target;
        const x = canvas.left + (head.x + 1) * canvas.width / 2;
        const y = canvas.top + (1 - head.y) * canvas.height / 2;
        target.targetId = targetId;
        target.lateral = Math.max(-1, Math.min(1, (plane.left + plane.width / 2 - x) / (canvas.width / 2)));
        target.vertical = Math.max(-1, Math.min(1, (plane.top + plane.height / 2 - y) / (canvas.height / 2)));
        attentionTargetRef.current = target;
      }
    }
    const origin = scratch.current.origin.copy(raw);
    if (points) origin.multiplyScalar(fusion.spineScale).add(scratch.current.projected.set(...fusion.weld));
    const connection = projectWorkspaceConnection({
      origin, bodyWorld: scratch.current.world, dockScale: getBrainDockScale(), camera, ...bounds.current,
    }, scratch.current.projected);
    if (!connection) { clear(); return; }
    // Avoid DOM writes while a still/reduced-motion body remains at the same pixel.
    if (current.pathData !== connection.path) {
      path?.setAttribute('d', connection.path);
      current.pathData = connection.path;
      contact?.setAttribute('cx', String(connection.target.x));
      contact?.setAttribute('cy', String(connection.target.y));
    }
    // The same birth owner keeps running when its slab yields to the DOM.
    // Restore that existing nerve reach, not a second animation/timer or an
    // entrance delay on readable work. Focus/stream updates do not reset it.
    const reach = !bounds.current.decision && artifact?.lifecycle === 'reaching' && !reducedMotion
      ? Math.min(1, Math.max(0, (performance.now() - artifact.phaseStartedAt) / MATERIALIZATION_REACH_MS)) : 1;
    const offset = String(1 - Math.max(0.03, easeOutExpo(reach)));
    if (current.offset !== offset) { path?.setAttribute('stroke-dashoffset', offset); current.offset = offset; }
    const contactVisibility = reach >= 1 ? 'visible' : 'hidden';
    if (current.contactVisibility !== contactVisibility) {
      if (contact) contact.style.visibility = contactVisibility;
      current.contactVisibility = contactVisibility;
    }
    if (!current.visible) { svg.style.visibility = 'visible'; current.visible = true; }
  });
  return null;
}
