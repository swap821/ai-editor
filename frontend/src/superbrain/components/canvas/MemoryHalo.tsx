/**
 * MemoryHalo (B4) — supervised memory formation made tactile.
 *
 * Pending fact proposals orbit the cortex as narrative-green motes. Touch one
 * and it comes forward, revealing its triple as luminous body-speech; the
 * operator then ABSORBS it (approve — it spirals into the cortex and the
 * backend mints it through the contradiction check) or RELEASES it (reject —
 * it drifts off and dims, never knowledge). A contradiction FLARES reflex
 * orange and returns to orbit: the fact awaits an explicit reconcile.
 *
 * Laws: materializes from the being's own anatomy (the cortex), luminous 3D
 * text only (no DOM panel), sacred tetrad hues only, never covers the spine
 * (the halo rides the cortex, far above the seats). All lifecycle logic lives
 * in lib/memoryHalo (tested); this component is just its body.
 */
import * as THREE from 'three';
import { useEffect, useRef, useState } from 'react';
import { useFrame } from '@react-three/fiber';
import { Billboard, Text } from '@react-three/drei';
import {
  HALO_TIMING,
  absorbMote,
  dismissPresentation,
  getHalo,
  moteOrbitOffset,
  presentMote,
  releaseMote,
  retireMote,
  settleFlare,
  stampLifecycle,
  startHaloPolling,
  subscribeHalo,
  type HaloState,
} from '@/lib/memoryHalo';
import { getCortexAnchor } from '@/lib/spineFusionBus';

const MOTE_COLOR = '#54f0a0'; // narrative green — memory forming
const FLARE_COLOR = '#ff7e40'; // reflex orange — a gate said "not yet"
const RELEASE_NODE_COLOR = '#aacde1'; // existing snow-dust accent

const _base = new THREE.Vector3();
const _target = new THREE.Vector3();

interface MemoryHaloProps {
  reducedMotion: boolean;
}

export default function MemoryHalo({ reducedMotion }: MemoryHaloProps) {
  const [halo, setHalo] = useState<HaloState>(getHalo());
  const [hoverId, setHoverId] = useState<number | null>(null);
  const groupRefs = useRef(new Map<number, THREE.Group>());
  const coreRefs = useRef(new Map<number, THREE.MeshBasicMaterial>());

  useEffect(() => {
    const unsubscribe = subscribeHalo(setHalo);
    const stopPolling = startHaloPolling();
    return () => {
      unsubscribe();
      stopPolling();
    };
  }, []);

  useFrame((state) => {
    const t = state.clock.elapsedTime;
    const anchor = getCortexAnchor();
    for (const mote of getHalo().motes) {
      const id = mote.proposal.id;
      const node = groupRefs.current.get(id);
      const core = coreRefs.current.get(id);
      if (!node) continue;
      stampLifecycle(id, t);
      const since = mote.lifecycleAt >= 0 ? t - mote.lifecycleAt : 0;
      const [ox, oy, oz] = moteOrbitOffset(mote.seed, t, reducedMotion);
      _base.set(anchor[0] + ox, anchor[1] + oy, anchor[2] + oz);
      let scale = 1;
      let opacity = hoverId === id ? 1 : 0.72;
      let color = MOTE_COLOR;

      switch (mote.lifecycle) {
        case 'presenting': {
          // Come forward and slightly up — presented to the operator, still
          // tethered above the cortex (never near the spine's seats).
          _target.set(anchor[0], anchor[1] + 0.42, anchor[2] + 0.72);
          const k = reducedMotion ? 1 : Math.min(1, since / 0.45);
          _base.lerp(_target, easeOut(k));
          scale = 1.7;
          opacity = 1;
          break;
        }
        case 'absorbing': {
          // Spiral inward: the cortex accepts a new belief.
          const k = Math.min(1, since / HALO_TIMING.absorb);
          const spiral = reducedMotion ? 0 : (1 - k) * 4.2 * k;
          _target.set(anchor[0], anchor[1], anchor[2]);
          _base.lerp(_target, easeOut(k));
          _base.x += Math.cos(mote.seed + spiral) * 0.16 * (1 - k);
          _base.z += Math.sin(mote.seed + spiral) * 0.16 * (1 - k);
          scale = 1 - k * 0.9;
          opacity = 1 - k * 0.4;
          if (k >= 1) retireMote(id);
          break;
        }
        case 'releasing': {
          // Drift away and dim: declined, never knowledge.
          const k = Math.min(1, since / HALO_TIMING.release);
          _base.x += Math.cos(mote.seed) * k * 0.9;
          _base.y += k * 0.25;
          _base.z += Math.sin(mote.seed) * k * 0.9;
          scale = 1 - k * 0.6;
          opacity = (1 - k) * 0.72;
          if (k >= 1) retireMote(id);
          break;
        }
        case 'flaring': {
          // The contradiction gate: flare reflex orange, hold, settle.
          const k = Math.min(1, since / HALO_TIMING.flare);
          color = FLARE_COLOR;
          scale = 1 + Math.sin(k * Math.PI) * 0.9;
          opacity = 1;
          if (k >= 1) settleFlare(id);
          break;
        }
        default:
          break;
      }

      node.position.copy(_base);
      node.scale.setScalar(scale);
      if (core) {
        core.opacity = opacity;
        core.color.set(color);
      }
    }
  });

  if (halo.motes.length === 0) return null;
  const presenting = halo.motes.find((mote) => mote.proposal.id === halo.presentingId) ?? null;

  return (
    <group>
      {halo.motes.map((mote) => {
        const id = mote.proposal.id;
        return (
          <group
            key={id}
            ref={(node) => {
              if (node) groupRefs.current.set(id, node);
              else groupRefs.current.delete(id);
            }}
          >
            <mesh
              renderOrder={11}
              onClick={(event) => {
                event.stopPropagation();
                if (halo.presentingId === id) dismissPresentation();
                else presentMote(id);
              }}
              onPointerOver={(event) => {
                event.stopPropagation();
                setHoverId(id);
              }}
              onPointerOut={() => setHoverId((prev) => (prev === id ? null : prev))}
            >
              <sphereGeometry args={[0.03, 14, 14]} />
              <meshBasicMaterial
                ref={(mat) => {
                  if (mat) coreRefs.current.set(id, mat);
                  else coreRefs.current.delete(id);
                }}
                color={MOTE_COLOR}
                transparent
                opacity={0.72}
                blending={THREE.AdditiveBlending}
                depthWrite={false}
                toneMapped={false}
              />
            </mesh>
            {/* soft halo shell */}
            <mesh renderOrder={10} scale={2.1}>
              <sphereGeometry args={[0.03, 10, 10]} />
              <meshBasicMaterial
                color={MOTE_COLOR}
                transparent
                opacity={0.14}
                blending={THREE.AdditiveBlending}
                depthWrite={false}
                toneMapped={false}
              />
            </mesh>
            {presenting?.proposal.id === id && (
              <Billboard>
                <Text
                  position={[0.09, 0.1, 0]}
                  fontSize={0.058}
                  maxWidth={1.5}
                  lineHeight={1.35}
                  anchorX="left"
                  anchorY="bottom"
                  color={MOTE_COLOR}
                  outlineWidth={0.006}
                  outlineColor="#02040a"
                  material-toneMapped={false}
                  renderOrder={12}
                >
                  {`${mote.proposal.subject} — ${mote.proposal.predicate} — ${mote.proposal.object}`}
                </Text>
                <Text
                  position={[0.09, 0.04, 0]}
                  fontSize={0.034}
                  anchorX="left"
                  anchorY="bottom"
                  color={RELEASE_NODE_COLOR}
                  material-toneMapped={false}
                  renderOrder={12}
                >
                  a memory asks to form
                </Text>
                {/* ABSORB node — the operator mints this belief */}
                <group position={[0.16, -0.12, 0]}>
                  <mesh
                    renderOrder={12}
                    onClick={(event) => {
                      event.stopPropagation();
                      void absorbMote(id);
                    }}
                  >
                    <sphereGeometry args={[0.036, 14, 14]} />
                    <meshBasicMaterial
                      color={MOTE_COLOR}
                      transparent
                      opacity={0.95}
                      blending={THREE.AdditiveBlending}
                      depthWrite={false}
                      toneMapped={false}
                    />
                  </mesh>
                  <Text
                    position={[0.07, 0, 0]}
                    fontSize={0.04}
                    anchorX="left"
                    color={MOTE_COLOR}
                    material-toneMapped={false}
                    renderOrder={12}
                  >
                    absorb
                  </Text>
                </group>
                {/* RELEASE node — declined, drifts back to the void */}
                <group position={[0.16, -0.22, 0]}>
                  <mesh
                    renderOrder={12}
                    onClick={(event) => {
                      event.stopPropagation();
                      void releaseMote(id);
                    }}
                  >
                    <sphereGeometry args={[0.028, 12, 12]} />
                    <meshBasicMaterial
                      color={RELEASE_NODE_COLOR}
                      transparent
                      opacity={0.7}
                      blending={THREE.AdditiveBlending}
                      depthWrite={false}
                      toneMapped={false}
                    />
                  </mesh>
                  <Text
                    position={[0.07, 0, 0]}
                    fontSize={0.04}
                    anchorX="left"
                    color={RELEASE_NODE_COLOR}
                    material-toneMapped={false}
                    renderOrder={12}
                  >
                    release
                  </Text>
                </group>
              </Billboard>
            )}
          </group>
        );
      })}
    </group>
  );
}

function easeOut(t: number): number {
  return 1 - Math.pow(1 - Math.min(1, Math.max(0, t)), 3);
}
