'use client';

// CorticalNerve (poster P1.3 — "a nerve grows out from the being's mind").
// A thin luminous strand that grows from the LIVE cortex (the published brain-head
// anchor × the eased dock scale) to a materialized work surface, re-aimed every
// frame so it stays rooted in the cortex as the being voyages / breathes / crowns.
//
// ADDITIVE to the vertebra seating: the tab still seats on its vertebra socket
// (#21/#22) and keeps its structural umbilical (MaterializedTab) — this only adds
// the cortical reach the poster shows ("the mind extends a nerve to the work").
// Points-mode only (the cortex anchor is published by the point cloud). Renders in
// brain-group-local space (same as MaterializationLayer), so anchor × dock lands on
// the visible head. Luminance/geometry only — sacred palette (a poster-tetrad hue).

import { useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { Line } from '@react-three/drei';
import * as THREE from 'three';
import { getCortexAnchor, getBrainDockScale } from '@/lib/spineFusionBus';

/** Sampled points along the cortex→slab strand (more = smoother bow). */
const SEG = 20;

type Line2Ref = { geometry: { setPositions: (a: number[]) => void } };

export default function CorticalNerve({
  target,
  color = '#7bf5fb',
  reducedMotion = false,
}: {
  /** the work surface the nerve reaches (brain-group-local). */
  target: [number, number, number];
  /** sacred-palette hue (default poster cyan). */
  color?: string;
  reducedMotion?: boolean;
}) {
  const lineRef = useRef<Line2Ref | null>(null);
  const tgt = useMemo(() => new THREE.Vector3(...target), [target]);
  // 3-control CatmullRom (cortex → bowed mid → slab); reused, re-aimed per frame.
  const curve = useMemo(
    () => new THREE.CatmullRomCurve3([new THREE.Vector3(), new THREE.Vector3(), new THREE.Vector3()]),
    [],
  );
  const initial = useMemo(() => Array.from({ length: SEG }, () => new THREE.Vector3()), []);
  const scratch = useMemo(() => new THREE.Vector3(), []);
  const flat = useMemo(() => new Array<number>(SEG * 3).fill(0), []);

  useFrame(() => {
    const line = lineRef.current;
    if (!line) return;
    // LIVE cortex root: published head centroid (cloud-local) × eased dock scale →
    // the visible head, in brain-group-local space (same space as `target`).
    const [ax, ay, az] = getCortexAnchor();
    const ds = getBrainDockScale() || 1;
    const ox = ax * ds;
    const oy = ay * ds;
    const oz = az * ds;
    const cp = curve.points;
    cp[0].set(ox, oy, oz); // rooted in the cortex
    // Bow the mid up a touch (reduced-motion keeps it straighter — calmer line).
    const bow = reducedMotion ? 0.02 : 0.07;
    cp[1].set((ox + tgt.x) / 2, (oy + tgt.y) / 2 + bow, (oz + tgt.z) / 2);
    cp[2].copy(tgt); // reaches the work surface
    for (let i = 0; i < SEG; i++) {
      curve.getPoint(i / (SEG - 1), scratch);
      flat[i * 3] = scratch.x;
      flat[i * 3 + 1] = scratch.y;
      flat[i * 3 + 2] = scratch.z;
    }
    line.geometry.setPositions(flat);
  });

  return (
    <Line
      ref={lineRef as never}
      points={initial}
      color={color}
      lineWidth={1.4}
      transparent
      opacity={0.6}
      renderOrder={10}
    />
  );
}
