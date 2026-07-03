'use client';

/**
 * RegionPins — anatomical callouts pinned to the living cortex.
 *
 * Each pin binds a brain region to the SAME metricsStore channel the HUD
 * intake rows read (the store's law: the brain's region callouts and the
 * intake rows MUST display the same number). Anchors reuse the thought-wave
 * region origins from SuperbrainScene, so the pin, the wave landing zone and
 * the intake row all agree on where a channel lives in the cortex:
 *
 *   RESEARCH  frontal lobe   (causal/graph waves land here)
 *   MEMORY    temporal lobe  (archive/memory waves)
 *   TOOLS     parietal crown (semantic/lattice waves)
 *   SIGNALS   occipital      (signal/telemetry waves)
 *
 * Mounted INSIDE the brain group: pins breathe, drift and bank with the
 * organism — anchored to the anatomy, never painted on the glass.
 *
 * VISION.md: an additive layer, the operator's call — flip SHOW_REGION_PINS
 * in SuperbrainScene to remove it without a trace.
 */

import { useEffect, useMemo, useState } from 'react';
import * as THREE from 'three';
import { Html } from '@react-three/drei';
import { useMetric, useMetricHistory, type MetricKey } from '@/lib/metricsStore';

/** Group-local brain centroid (from the measured GLB bounds). */
const CENTER = new THREE.Vector3(0.0015, 0.2055, 0.057);

interface PinDef {
  key: MetricKey;
  name: string;
  /** Cortex-surface anchor, group-local (== thought-wave region origin). */
  anchor: THREE.Vector3;
  /** How far the label floats out along the anchor's radial direction. */
  reach: number;
  /** Hand nudge so labels clear the silhouette and never collide. */
  nudge: THREE.Vector3;
}

const PINS: PinDef[] = [
  {
    key: 'research',
    name: 'RESEARCH',
    anchor: new THREE.Vector3(0, 0.26, 0.48),
    reach: 0.34,
    nudge: new THREE.Vector3(0, 0.1, 0),
  },
  {
    key: 'memory',
    name: 'MEMORY',
    anchor: new THREE.Vector3(0.34, 0.16, 0.11),
    reach: 0.3,
    nudge: new THREE.Vector3(0.06, -0.04, 0),
  },
  {
    key: 'tools',
    name: 'TOOLS',
    anchor: new THREE.Vector3(0, 0.61, 0.11),
    // Short reach: the crown label must stay BELOW the GAGOS title
    // through the full sway/drift envelope.
    reach: 0.13,
    nudge: new THREE.Vector3(0.16, 0.0, 0),
  },
  {
    key: 'signals',
    name: 'SIGNALS',
    anchor: new THREE.Vector3(0.05, 0.31, -0.38),
    reach: 0.32,
    nudge: new THREE.Vector3(0.05, 0.08, 0),
  },
];

function labelPointFor(pin: PinDef): THREE.Vector3 {
  const outward = pin.anchor.clone().sub(CENTER).normalize();
  return pin.anchor.clone().addScaledVector(outward, pin.reach).add(pin.nudge);
}

export function PinChip({ pin, label }: { pin: PinDef; label: THREE.Vector3 }) {
  const value = useMetric(pin.key);
  /* Drill-in: a click unfolds the channel's REAL per-poll history. */
  const history = useMetricHistory(pin.key);
  const [open, setOpen] = useState(false);
  const path = useMemo(() => {
    if (history.length < 2) return null;
    const width = 84;
    const height = 24;
    const step = width / (history.length - 1);
    return history
      .map((v, i) => {
        const x = (i * step).toFixed(1);
        const y = (height - (Math.max(0, Math.min(99, v)) / 99) * height).toFixed(1);
        return `${i === 0 ? 'M' : 'L'}${x},${y}`;
      })
      .join(' ');
  }, [history]);
  return (
    <Html position={label} zIndexRange={[60, 0]}>
      <div
        className={`region-pin${open ? ' region-pin--open' : ''}`}
        style={{ transform: 'translate(-50%, -50%)' }}
        role="button"
        tabIndex={0}
        aria-expanded={open}
        title={`${pin.name} — click for real sample history`}
        onClick={() => setOpen((prev) => !prev)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            setOpen((prev) => !prev);
          }
        }}
      >
        <span>{pin.name}</span>
        <strong>{value}%</strong>
        {open ? (
          <span className="region-pin-graph">
            {path ? (
              <svg viewBox="0 0 84 24" aria-label={`${pin.name} history`}>
                <path d={path} />
              </svg>
            ) : (
              <em>no real samples yet</em>
            )}
          </span>
        ) : null}
      </div>
    </Html>
  );
}

export default function RegionPins() {
  const pins = useMemo(
    () =>
      PINS.map((pin) => {
        const label = labelPointFor(pin);
        const geometry = new THREE.BufferGeometry().setFromPoints([pin.anchor, label]);
        const material = new THREE.LineBasicMaterial({
          color: '#9ff0ff',
          transparent: true,
          opacity: 0.38,
          depthWrite: false,
        });
        const line = new THREE.Line(geometry, material);
        line.renderOrder = 3;
        return { pin, label, line, geometry, material };
      }),
    [],
  );

  // Geometry/material lifecycles belong to this component, not the GC.
  useEffect(() => {
    return () => {
      for (const { geometry, material } of pins) {
        geometry.dispose();
        material.dispose();
      }
    };
  }, [pins]);

  return (
    <group>
      {pins.map(({ pin, label, line }) => (
        <group key={pin.key}>
          <primitive object={line} />
          <mesh position={pin.anchor}>
            <sphereGeometry args={[0.011, 12, 12]} />
            <meshBasicMaterial color="#cfe9ff" transparent opacity={0.95} />
          </mesh>
          <PinChip pin={pin} label={label} />
        </group>
      ))}
    </group>
  );
}
