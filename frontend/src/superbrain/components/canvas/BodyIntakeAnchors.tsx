import { useLayoutEffect, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { Matrix4, Vector3 } from 'three';
import { copyBodyGroupWorldMatrix, getBrainDockScale } from '@/lib/spineFusionBus';
import { getStemAnchor, setStemAnchor, type StemAnchor } from '@/lib/stemAnchorBus';
import { getFunnelAnchor, setFunnelAnchor, type FunnelAnchor } from '@/lib/funnelAnchorBus';
import { intakeNerveDrive } from '@/lib/intakeNerveDrive';
import { getEffectiveOrganismPhase } from '@/lib/conversationPhaseBus';
import { lifecyclePhaseForPhysicalProjection, type PhysicalBodyProjection } from '@/lib/bodyPosture';

/** Project AFTER the body and AmbientFloat, BEFORE its sibling command nerve.
 * Default frame priority preserves automatic/composer render ownership. These
 * are the existing authored sockets, not a new anatomical or semantic system.
 */
export default function BodyIntakeAnchors({ physical, reducedMotion }: {
  physical?: PhysicalBodyProjection;
  reducedMotion: boolean;
}) {
  const matrix = useRef(new Matrix4());
  const stemPoint = useRef(new Vector3());
  const funnelPoint = useRef(new Vector3());
  const stem = useRef<StemAnchor>({ x: 0, y: 0, visible: false });
  const funnel = useRef<FunnelAnchor>({ x: 0, y: 0, visible: false, world: [0, 0, 0], intake: 0, flow: 0 });

  useLayoutEffect(() => {
    const ownedStem = stem.current;
    const ownedFunnel = funnel.current;
    return () => {
      // A late old-root cleanup must not erase a replacement renderer's anchors.
      if (getStemAnchor() === ownedStem) setStemAnchor({ x: 0, y: 0, visible: false });
      if (getFunnelAnchor() === ownedFunnel) {
        setFunnelAnchor({ x: 0, y: 0, visible: false, world: [0, 0, 0], intake: 0, flow: 0 });
      }
    };
  }, []);

  useFrame(({ camera, size }) => {
    const dockScale = getBrainDockScale();
    const s = stem.current;
    const f = funnel.current;
    if (size.width <= 0 || size.height <= 0 || !Number.isFinite(dockScale) || dockScale <= 0 || !copyBodyGroupWorldMatrix(matrix.current)) {
      s.visible = f.visible = false;
      f.intake = f.flow = 0;
      setStemAnchor(s); setFunnelAnchor(f);
      return;
    }
    camera.updateWorldMatrix(true, false);
    // The point cloud is inside the eased visual scale, not just the outer pose.
    stemPoint.current.set(0, -0.35 * dockScale, 0).applyMatrix4(matrix.current).project(camera);
    s.x = size.left + (stemPoint.current.x * 0.5 + 0.5) * size.width;
    s.y = size.top + (0.5 - stemPoint.current.y * 0.5) * size.height;
    s.visible = inView(stemPoint.current);
    setStemAnchor(s);

    const dial = typeof window !== 'undefined' ? (window as { __FUNNEL_Y?: number }).__FUNNEL_Y : undefined;
    const localY = typeof dial === 'number' && Number.isFinite(dial) ? dial : -0.85;
    funnelPoint.current.set(0, localY * dockScale, 0).applyMatrix4(matrix.current);
    f.world[0] = funnelPoint.current.x;
    f.world[1] = funnelPoint.current.y;
    f.world[2] = funnelPoint.current.z;
    funnelPoint.current.project(camera);
    f.x = size.left + (funnelPoint.current.x * 0.5 + 0.5) * size.width;
    f.y = size.top + (0.5 - funnelPoint.current.y * 0.5) * size.height;
    f.visible = inView(funnelPoint.current);
    const phase = physical ? lifecyclePhaseForPhysicalProjection(physical) : getEffectiveOrganismPhase();
    const drive = intakeNerveDrive(phase);
    f.intake = drive.drive;
    f.flow = reducedMotion ? 0 : drive.flow;
    setFunnelAnchor(f);
  });
  return null;
}

function inView(point: Vector3): boolean {
  return Number.isFinite(point.x) && Number.isFinite(point.y) && Number.isFinite(point.z)
    && Math.abs(point.x) <= 1 && Math.abs(point.y) <= 1 && Math.abs(point.z) <= 1;
}
