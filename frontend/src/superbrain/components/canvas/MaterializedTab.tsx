import { Html, Text } from '@react-three/drei';
import { Suspense, lazy, useEffect, useMemo, useRef } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import * as THREE from 'three';
import type { MaterializedTabRecord } from '@/lib/tabStore';
import { updateMaterializedTab } from '@/lib/tabStore';

const LazyCodeCanvas = lazy(() => import('../../../components/CodeCanvas'));

const REACH_DURATION_MS = 950;
const UNFURL_DURATION_MS = 560;
const SLAB_WIDTH = 0.86;
const SLAB_HEIGHT = 0.56;
const SLAB_RADIUS = 0.06;
const SLAB_THICKNESS = 0.02;
const SLAB_HTML_SCALE = SLAB_WIDTH / 720;
const UMBILICAL_RADIUS = 0.012;
const UMBILICAL_SEGMENTS = 40;
const UMBILICAL_RADIAL_SEGMENTS = 10;
const REACH_COLOR = new THREE.Color('#78eeff');
const LIVE_COLOR = new THREE.Color('#ffbf78');
const FRAME_COLOR = new THREE.Color('#ffd89b');
const BEAD_COUNT = 4;

function clamp01(value: number): number {
  return THREE.MathUtils.clamp(value, 0, 1);
}

function makeRoundedRectShape(width: number, height: number, radius: number): THREE.Shape {
  const halfW = width * 0.5;
  const halfH = height * 0.5;
  const r = Math.min(radius, halfW, halfH);
  const shape = new THREE.Shape();
  shape.moveTo(-halfW + r, -halfH);
  shape.lineTo(halfW - r, -halfH);
  shape.quadraticCurveTo(halfW, -halfH, halfW, -halfH + r);
  shape.lineTo(halfW, halfH - r);
  shape.quadraticCurveTo(halfW, halfH, halfW - r, halfH);
  shape.lineTo(-halfW + r, halfH);
  shape.quadraticCurveTo(-halfW, halfH, -halfW, halfH - r);
  shape.lineTo(-halfW, -halfH + r);
  shape.quadraticCurveTo(-halfW, -halfH, -halfW + r, -halfH);
  return shape;
}

function baseName(path: string): string {
  return String(path).split(/[\\/]/).pop() || path;
}

export default function MaterializedTab({
  tab,
  reducedMotion,
}: {
  tab: MaterializedTabRecord;
  reducedMotion: boolean;
}) {
  const camera = useThree((state) => state.camera);
  const orientationRef = useRef<THREE.Group>(null);
  const slabRef = useRef<THREE.Group>(null);
  const tubeRef = useRef<THREE.Mesh>(null);
  const bodyRef = useRef<THREE.Mesh>(null);
  const frameRef = useRef<THREE.LineSegments>(null);
  const labelRef = useRef<THREE.Object3D>(null);
  const beadRefs = useRef<THREE.Mesh[]>([]);

  const curve = useMemo(() => {
    const origin = new THREE.Vector3(...tab.originLocal);
    const target = new THREE.Vector3(...tab.targetLocal);
    const midA = origin.clone().lerp(target, 0.28).add(new THREE.Vector3(0.08, 0.12, 0.1));
    const midB = origin.clone().lerp(target, 0.7).add(new THREE.Vector3(0.04, 0.06, 0.05));
    return new THREE.CatmullRomCurve3([origin, midA, midB, target]);
  }, [tab.originLocal, tab.targetLocal]);

  const tubeGeometry = useMemo(
    () => new THREE.TubeGeometry(curve, UMBILICAL_SEGMENTS, UMBILICAL_RADIUS, UMBILICAL_RADIAL_SEGMENTS, false),
    [curve],
  );
  const slabShape = useMemo(() => makeRoundedRectShape(SLAB_WIDTH, SLAB_HEIGHT, SLAB_RADIUS), []);
  const slabShapeGeometry = useMemo(() => new THREE.ShapeGeometry(slabShape, 24), [slabShape]);
  const slabBodyGeometry = useMemo(
    () => new THREE.ExtrudeGeometry(slabShape, { depth: SLAB_THICKNESS, bevelEnabled: false, steps: 1 }),
    [slabShape],
  );
  const slabFrameGeometry = useMemo(() => new THREE.EdgesGeometry(slabShapeGeometry), [slabShapeGeometry]);

  useEffect(() => {
    return () => {
      tubeGeometry.dispose();
      slabBodyGeometry.dispose();
      slabShapeGeometry.dispose();
      slabFrameGeometry.dispose();
    };
  }, [slabBodyGeometry, slabFrameGeometry, slabShapeGeometry, tubeGeometry]);

  useFrame((state) => {
    const now = performance.now();
    const reachProgress = reducedMotion ? 1 : clamp01((now - tab.bornAt) / REACH_DURATION_MS);
    const slabProgress = reducedMotion ? 1 : clamp01((now - tab.bornAt - REACH_DURATION_MS * 0.72) / UNFURL_DURATION_MS);
    const liveProgress = reducedMotion ? 1 : clamp01((now - tab.bornAt - REACH_DURATION_MS) / UNFURL_DURATION_MS);

    if (!reducedMotion && tab.lifecycle === 'reaching' && reachProgress >= 1) {
      updateMaterializedTab(tab.id, { lifecycle: 'unfurling' });
    }
    if (tab.lifecycle !== 'live' && liveProgress >= 1) {
      updateMaterializedTab(tab.id, { lifecycle: 'live' });
    }

    if (tubeRef.current) {
      const geometry = tubeRef.current.geometry;
      const drawCount = geometry.getIndex()?.count ?? geometry.getAttribute('position').count;
      geometry.setDrawRange(0, Math.max(2, Math.floor(drawCount * Math.max(reachProgress, 0.02))));
      const mat = tubeRef.current.material as THREE.MeshStandardMaterial;
      mat.color.copy(REACH_COLOR).lerp(LIVE_COLOR, liveProgress);
      mat.emissive.copy(REACH_COLOR).lerp(LIVE_COLOR, liveProgress);
      mat.emissiveIntensity = 0.9 + liveProgress * 0.7;
    }

    if (orientationRef.current) {
      orientationRef.current.lookAt(camera.position);
    }

    if (slabRef.current) {
      const eased = slabProgress * slabProgress * (3 - 2 * slabProgress);
      slabRef.current.scale.set(
        0.72 + eased * 0.28,
        Math.max(0.01, eased),
        0.65 + eased * 0.35,
      );
      slabRef.current.position.copy(curve.getPoint(1));
    }

    if (bodyRef.current) {
      const mat = bodyRef.current.material as THREE.MeshStandardMaterial;
      mat.opacity = 0.18 + slabProgress * 0.76;
      mat.emissive.copy(REACH_COLOR).lerp(LIVE_COLOR, liveProgress * 0.9);
      mat.emissiveIntensity = 0.42 + slabProgress * 0.36;
    }

    if (frameRef.current) {
      const mat = frameRef.current.material as THREE.LineBasicMaterial;
      mat.color.copy(FRAME_COLOR).lerp(LIVE_COLOR, liveProgress * 0.5);
      mat.opacity = 0.24 + slabProgress * 0.6;
    }

    if (labelRef.current) {
      labelRef.current.scale.setScalar(0.96 + slabProgress * 0.04);
    }

    const beadTravel = (state.clock.elapsedTime * 0.28) % 1;
    beadRefs.current.forEach((bead, index) => {
      if (!bead) return;
      const t = clamp01((beadTravel + index * 0.19) % 1);
      const pathT = clamp01(0.08 + t * 0.86 * Math.max(reachProgress, 0.25));
      bead.position.copy(curve.getPointAt(pathT));
      bead.scale.setScalar(0.45 + liveProgress * 0.7);
      const mat = bead.material as THREE.MeshBasicMaterial;
      mat.color.copy(REACH_COLOR).lerp(LIVE_COLOR, liveProgress);
      mat.opacity = 0.25 + liveProgress * 0.65;
    });
  });

  const interactive = tab.lifecycle === 'live';
  const headerLabel = tab.content?.filepath ? baseName(tab.content.filepath) : 'materialized tab';
  const languageLabel = tab.content?.language ?? 'text';
  const code = tab.content?.code ?? '';

  return (
    <group>
      <mesh ref={tubeRef} geometry={tubeGeometry} renderOrder={6} frustumCulled={false}>
        <meshStandardMaterial
          color="#78eeff"
          emissive="#78eeff"
          emissiveIntensity={1.1}
          roughness={0.18}
          metalness={0.22}
          transparent
          opacity={0.95}
        />
      </mesh>

      {Array.from({ length: BEAD_COUNT }, (_, index) => (
        <mesh
          key={`materialized-bead-${index}`}
          ref={(mesh) => {
            if (mesh) beadRefs.current[index] = mesh;
          }}
          renderOrder={7}
        >
          <sphereGeometry args={[0.016, 12, 12]} />
          <meshBasicMaterial color="#78eeff" transparent opacity={0.78} />
        </mesh>
      ))}

      <group ref={orientationRef}>
        <group ref={slabRef}>
          <group rotation={[-0.06, 0.12, 0]}>
            <mesh ref={bodyRef} renderOrder={8}>
              <primitive object={slabBodyGeometry} attach="geometry" />
              <meshStandardMaterial
                color="#08111b"
                emissive="#3fa8ff"
                emissiveIntensity={0.58}
                roughness={0.28}
                metalness={0.36}
                transparent
                opacity={0.92}
              />
            </mesh>
            <lineSegments ref={frameRef} geometry={slabFrameGeometry} position={[0, 0, SLAB_THICKNESS + 0.001]} renderOrder={9}>
              <lineBasicMaterial color="#ffd89b" transparent opacity={0.7} />
            </lineSegments>
            <Text
              ref={labelRef}
              position={[0, SLAB_HEIGHT * 0.38, SLAB_THICKNESS + 0.014]}
              color="#d7ecff"
              fontSize={0.048}
              maxWidth={SLAB_WIDTH * 0.78}
              anchorX="center"
              anchorY="middle"
              outlineWidth={0.003}
              outlineColor="#08111b"
              renderOrder={10}
            >
              {headerLabel}
            </Text>
            <Text
              position={[0, -SLAB_HEIGHT * 0.42, SLAB_THICKNESS + 0.014]}
              color="#8fd1ff"
              fontSize={0.028}
              anchorX="center"
              anchorY="middle"
              renderOrder={10}
            >
              {languageLabel}
            </Text>
            <group position={[0, 0, SLAB_THICKNESS + 0.012]} scale={[SLAB_HTML_SCALE, SLAB_HTML_SCALE, SLAB_HTML_SCALE]}>
              <Html
                transform
                occlude="blending"
                style={{ pointerEvents: interactive ? 'auto' : 'none' }}
              >
                <div
                  style={{
                    width: 720,
                    height: 420,
                    borderRadius: 24,
                    overflow: 'hidden',
                    background: 'rgba(5, 11, 18, 0.92)',
                    border: '1px solid rgba(143, 209, 255, 0.28)',
                    boxShadow: '0 24px 60px rgba(0, 0, 0, 0.42), inset 0 1px 0 rgba(255,255,255,0.06)',
                    pointerEvents: interactive ? 'auto' : 'none',
                  }}
                >
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '10px 14px',
                      background: 'linear-gradient(180deg, rgba(24,45,69,0.95), rgba(11,18,30,0.84))',
                      borderBottom: '1px solid rgba(143, 209, 255, 0.18)',
                      color: '#d7ecff',
                      fontFamily: 'ui-monospace, SFMono-Regular, SFMono, Menlo, Consolas, monospace',
                      fontSize: 12,
                      letterSpacing: 0,
                    }}
                  >
                    <span>{headerLabel}</span>
                    <span style={{ color: '#8fd1ff' }}>{languageLabel}</span>
                  </div>
                  <div style={{ width: '100%', height: 'calc(100% - 41px)' }}>
                    <Suspense fallback={<div style={{ color: '#8fd1ff', padding: 16 }}>Materializing editor...</div>}>
                      <LazyCodeCanvas
                        code={code}
                        language={languageLabel}
                        onChange={(nextCode?: string) => {
                          if (!tab.content) return;
                          updateMaterializedTab(tab.id, {
                            content: {
                              ...tab.content,
                              code: nextCode ?? '',
                            },
                          });
                        }}
                      />
                    </Suspense>
                  </div>
                </div>
              </Html>
            </group>
          </group>
        </group>
      </group>
    </group>
  );
}
