import * as THREE from 'three';
import { useLayoutEffect, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { getFunnelAnchor } from '@/lib/funnelAnchorBus';
import { getWeather, installWeather, phaseHueOf } from '@/lib/phaseWeather';

/**
 * CommandNerve3D — the operator's command nerve as a REAL 3D tube in the scene
 * (operator: "nerve should be also 3D, like a live"), replacing the flat DOM SVG.
 *
 * It bridges the DOM dock to the living being: each frame it reads the SEND (->)
 * button's screen rect, unprojects it INTO the scene at the conus's depth, and grows a
 * glowing purple tube from there UP into the CONUS NECK — the bottom end of the cord
 * where the willow nerve-roots branch out. The nerve reads as one more root coming out
 * of the brainstem's bottom end. BOTH ENDS carry a LAYERED JUNCTION NODE (crisp solid
 * core + soft halo) so it plugs in strongly + beautifully.
 *
 * PHASE-AWARE (operator: "think how this adjusts in every phase/posture"): the nerve is
 * the being's INTAKE channel, so it BLAZES while receiving you (attentive → intake) —
 * command-beads pour down into the socket — and RECEDES as the being tucks its cauda
 * tail to work (materializing → working → conducting), mirroring uSprayHide so it never
 * floats over the hidden conus. Position rides the group's voyage/orbit/posture/lift for
 * free (the anchor is a fixed group-local point). The phase drive arrives via the funnel
 * anchor bus (intake + flow), damped here so transitions are smooth, never snapped.
 */

const TUBE_SEGMENTS = 48;
const RADIAL_SEGMENTS = 10;
const TUBE_RADIUS = 0.013;
const BEAD_COUNT = 6;

const _conv = new THREE.Vector3();
const _convNdc = new THREE.Vector3();
const _btn = new THREE.Vector3();
const _c1 = new THREE.Vector3();
const _c2 = new THREE.Vector3();
const _controlNdc = new THREE.Vector3();
const _clearance = new THREE.Vector3();
const _cameraRight = new THREE.Vector3();
const _cameraUp = new THREE.Vector3();
const INTERIOR_CONTROLS = [_c1, _c2];
const _beadPos = new THREE.Vector3();
const REBUILD_EPS = 0.004; // world units — rebuild the tube only when an endpoint moved enough

// PHASE CHORD (B2): damp targets for the intake nerve's phase tint — module
// scope so no colors are allocated per frame. Base = the nerve's canon purple.
const NERVE_BASE_COLOR = new THREE.Color('#b06eff');
const NERVE_TINT_TARGET = new THREE.Color();
const NERVE_PHASE_COLOR = new THREE.Color();

interface CommandNerve3DProps {
  reducedMotion: boolean;
}

export default function CommandNerve3D({ reducedMotion }: CommandNerve3DProps) {
  const meshRef = useRef<THREE.Mesh>(null);
  const ownedTube = useRef<THREE.TubeGeometry | null>(null);
  const tubeMatRef = useRef<THREE.MeshStandardMaterial>(null);
  const btnNodeRef = useRef<THREE.Group>(null);
  const cordNodeRef = useRef<THREE.Group>(null);
  const beadGroupRef = useRef<THREE.Group>(null);
  const beadRefs = useRef<(THREE.Mesh | null)[]>([]);
  const driveRef = useRef(0); // damped channel liveliness (0..1)
  const flowRef = useRef(0); // damped bead flow (0..1)
  const beadTRef = useRef(0); // bead travel phase
  // Geometry belongs to this renderer. A replacement at identical endpoints
  // must build its own tube, not inherit another root's rebuild cache.
  const lastBtn = useRef(new THREE.Vector3(1e9, 1e9, 1e9));
  const lastConv = useRef(new THREE.Vector3(1e9, 1e9, 1e9));
  const lastProjection = useRef(new THREE.Matrix4());
  const lastCameraWorld = useRef(new THREE.Matrix4());
  // A convex control hull cannot overshoot its last bend below the canvas as
  // Catmull-Rom did. The same endpoints and vertical cauda approach remain.
  const curveRef = useRef<THREE.CubicBezierCurve3>(
    new THREE.CubicBezierCurve3(
      new THREE.Vector3(),
      new THREE.Vector3(),
      new THREE.Vector3(),
      new THREE.Vector3(),
    ),
  );

  // R3F owns the JSX placeholder, not the imperative generated replacement.
  // Release our final generation when this subtree leaves a surviving canvas.
  useLayoutEffect(() => () => {
    ownedTube.current?.dispose();
    ownedTube.current = null;
  }, []);

  useFrame((state, delta) => {
    const mesh = meshRef.current;
    const btnNode = btnNodeRef.current;
    const cordNode = cordNodeRef.current;
    const beadGroup = beadGroupRef.current;
    if (!mesh) return;
    // PHASE CHORD (B2): the intake nerve hints the mind's ACTIVE cognitive
    // phase — canon purple at rest, blended 35% toward the phase's tetrad hue
    // mid-turn (phaseWeather; wonder deliberately yields no single hue). Damped
    // so phase changes glide, never snap; reduced-motion keeps the tint too
    // (it is a slow color, not a large translation).
    installWeather();
    if (tubeMatRef.current) {
      const phaseHue = phaseHueOf(getWeather());
      if (phaseHue) {
        NERVE_TINT_TARGET.copy(NERVE_BASE_COLOR).lerp(NERVE_PHASE_COLOR.set(phaseHue), 0.35);
      } else {
        NERVE_TINT_TARGET.copy(NERVE_BASE_COLOR);
      }
      tubeMatRef.current.color.lerp(NERVE_TINT_TARGET, Math.min(1, delta * 2.5));
    }
    const funnel = getFunnelAnchor();
    const presence = funnel.presence === undefined ? 1
      : Number.isFinite(funnel.presence) ? THREE.MathUtils.clamp(funnel.presence, 0, 1) : 0;
    const sendBtn = typeof document !== 'undefined' ? document.querySelector('.gagos-send') : null;

    // damp the phase-driven channel toward its target every frame, so the nerve eases
    // between blaze (intake) and tuck-away (working) instead of snapping.
    let driveTarget = funnel.visible && sendBtn ? funnel.intake : 0;
    let flowTarget = funnel.visible && sendBtn ? funnel.flow : 0;
    // dev preview/tuning (remote): window.__NERVE_DRIVE = { drive, flow } overrides the
    // phase drive so each phase's look can be previewed without driving the lifecycle.
    if (typeof window !== 'undefined') {
      const dial = (window as { __NERVE_DRIVE?: { drive?: number; flow?: number } }).__NERVE_DRIVE;
      if (dial) {
        if (typeof dial.drive === 'number') driveTarget = dial.drive;
        if (typeof dial.flow === 'number') flowTarget = dial.flow;
      }
    }
    driveRef.current = THREE.MathUtils.damp(driveRef.current, driveTarget, 3.4, delta);
    flowRef.current = THREE.MathUtils.damp(flowRef.current, flowTarget, 4.5, delta);
    const drive = driveRef.current;
    const flow = flowRef.current;

    // fully gone (no being / off-screen / deep-work recede) → hide everything cheaply
    if (!funnel.visible || !sendBtn || drive < 0.02 || presence <= 0.02) {
      mesh.visible = false;
      if (btnNode) btnNode.visible = false;
      if (cordNode) cordNode.visible = false;
      if (beadGroup) beadGroup.visible = false;
      return;
    }
    mesh.visible = true;

    // conus (cord bottom end) world pos + its depth in NDC
    _conv.set(funnel.world[0], funnel.world[1], funnel.world[2]);
    _convNdc.copy(_conv).project(state.camera);

    // the -> button's screen centre -> NDC at the conus depth -> world point
    const r = (sendBtn as HTMLElement).getBoundingClientRect();
    const ndcX = ((r.left + r.width * 0.5 - state.size.left) / state.size.width) * 2 - 1;
    const ndcY = -(((r.top + r.height * 0.5 - state.size.top) / state.size.height) * 2 - 1);
    _btn.set(ndcX, ndcY, _convNdc.z).unproject(state.camera);

    // CHANNEL GLOW scales with the phase drive: present+calm at rest, ablaze at intake.
    if (tubeMatRef.current) {
      tubeMatRef.current.opacity = (0.05 + 0.9 * drive) * presence;
      tubeMatRef.current.emissiveIntensity = 1.1 + 0.85 * drive;
    }

    // junction NODES track the endpoints; their breath deepens with the drive (steady
    // under reduced motion). The socket breathes a touch slower/deeper — the living mouth.
    const t = state.clock.elapsedTime;
    const breath = reducedMotion ? 0 : 1;
    const nodeFade = (0.18 + 0.82 * drive) * presence;
    if (btnNode) {
      btnNode.visible = true;
      btnNode.position.copy(_btn);
      btnNode.scale.setScalar(1 + breath * 0.1 * drive * Math.sin(t * 2.4));
      setGroupOpacity(btnNode, nodeFade);
    }
    if (cordNode) {
      cordNode.visible = true;
      cordNode.position.copy(_conv);
      cordNode.scale.setScalar(1 + breath * 0.13 * drive * Math.sin(t * 2.0 + 1.1));
      setGroupOpacity(cordNode, nodeFade);
    }

    // The interior clearance is camera-relative even when both world contacts
    // stay still. Preserve endpoint hysteresis, but invalidate an old lens/pose.
    if (
      _btn.distanceToSquared(lastBtn.current) >= REBUILD_EPS * REBUILD_EPS ||
      _conv.distanceToSquared(lastConv.current) >= REBUILD_EPS * REBUILD_EPS ||
      !lastProjection.current.equals(state.camera.projectionMatrix) ||
      !lastCameraWorld.current.equals(state.camera.matrixWorld)
    ) {
      lastBtn.current.copy(_btn);
      lastConv.current.copy(_conv);
      lastProjection.current.copy(state.camera.projectionMatrix);
      lastCameraWorld.current.copy(state.camera.matrixWorld);

      // Leave the button level, sweep across, then rise into the cauda from
      // below. Keep the authored approach, without a spline's overshoot.
      const dist = _btn.distanceTo(_conv);
      _c1.lerpVectors(_btn, _conv, 0.36);
      _c1.y -= dist * 0.08;
      _c2.lerpVectors(_btn, _conv, 0.8);
      _c2.x = _conv.x;
      _c2.z = _conv.z;
      _c2.y = _conv.y - dist * 0.14;

      // Leave room for the tube's radial envelope in this camera's full-stage
      // viewport, not just for its centerline. Only its two interior controls
      // adapt near an edge; the DOM and anatomical contacts never move.
      _cameraRight.setFromMatrixColumn(state.camera.matrixWorld, 0);
      _cameraUp.setFromMatrixColumn(state.camera.matrixWorld, 1);
      _clearance.copy(_conv).addScaledVector(_cameraRight, TUBE_RADIUS * 3)
        .addScaledVector(_cameraUp, TUBE_RADIUS * 3).project(state.camera);
      const padX = Math.abs(_clearance.x - _convNdc.x);
      const padY = Math.abs(_clearance.y - _convNdc.y);
      for (const control of INTERIOR_CONTROLS) {
        _controlNdc.copy(control).project(state.camera);
        _controlNdc.x = THREE.MathUtils.clamp(_controlNdc.x, -1 + padX, 1 - padX);
        _controlNdc.y = THREE.MathUtils.clamp(_controlNdc.y, -1 + padY, 1 - padY);
        control.copy(_controlNdc.unproject(state.camera));
      }

      const curve = curveRef.current;
      curve.v0.copy(_btn);
      curve.v1.copy(_c1);
      curve.v2.copy(_c2);
      curve.v3.copy(_conv);

      const next = new THREE.TubeGeometry(curve, TUBE_SEGMENTS, TUBE_RADIUS, RADIAL_SEGMENTS, false);
      ownedTube.current?.dispose();
      ownedTube.current = next;
      mesh.geometry = next;
    }

    // Update travelling words AFTER the current tube, including first paint
    // and viewport changes. Retain the same clock, phase and pause policy.
    if (beadGroup) {
      const beadsLive = !reducedMotion && flow > 0.02;
      beadGroup.visible = beadsLive;
      if (beadsLive) {
        beadTRef.current = (beadTRef.current + delta * (0.35 + flow * 0.95)) % 1;
        const curve = curveRef.current;
        for (let i = 0; i < BEAD_COUNT; i++) {
          const b = beadRefs.current[i];
          if (!b) continue;
          const u = (beadTRef.current + i / BEAD_COUNT) % 1;
          curve.getPoint(u, _beadPos);
          b.position.copy(_beadPos);
          const mat = b.material as THREE.MeshBasicMaterial;
          mat.opacity = flow * Math.sin(u * Math.PI) * 0.95 * presence;
          b.scale.setScalar(0.7 + 0.5 * Math.sin(u * Math.PI));
        }
      }
    }
  });

  return (
    <group renderOrder={8}>
      {/* the nerve tube — the dock's send-purple, self-lit so it glows like the being's own nerves */}
      <mesh ref={meshRef} frustumCulled={false}>
        {/* placeholder — replaced by the real tube geometry on the first frame */}
        <bufferGeometry />
        <meshStandardMaterial
          ref={tubeMatRef}
          color="#b06eff"
          emissive="#7c3aed"
          emissiveIntensity={1.5}
          roughness={0.25}
          metalness={0.2}
          transparent
          opacity={0.4}
          toneMapped={false}
        />
      </mesh>

      {/* SYNAPSE — where the nerve roots into the -> button (crisp core + soft halo) */}
      <group ref={btnNodeRef} frustumCulled={false}>
        <mesh renderOrder={12}>
          <sphereGeometry args={[0.026, 18, 18]} />
          <meshBasicMaterial color="#f3e9ff" transparent opacity={0.96} depthWrite={false} toneMapped={false} />
        </mesh>
        <mesh renderOrder={10}>
          <sphereGeometry args={[0.075, 18, 18]} />
          <meshBasicMaterial color="#b06eff" transparent opacity={0.4} blending={THREE.AdditiveBlending} depthWrite={false} toneMapped={false} />
        </mesh>
      </group>

      {/* SOCKET — where the nerve merges into the conus (bottom end of the cord). A
          stronger, brighter junction so it owns the convergence amid the willow dots. */}
      <group ref={cordNodeRef} frustumCulled={false}>
        <mesh renderOrder={12}>
          <sphereGeometry args={[0.034, 20, 20]} />
          <meshBasicMaterial color="#f6efff" transparent opacity={0.98} depthWrite={false} toneMapped={false} />
        </mesh>
        <mesh renderOrder={11}>
          <sphereGeometry args={[0.058, 20, 20]} />
          <meshBasicMaterial color="#d8b8ff" transparent opacity={0.55} blending={THREE.AdditiveBlending} depthWrite={false} toneMapped={false} />
        </mesh>
        <mesh renderOrder={10}>
          <sphereGeometry args={[0.13, 20, 20]} />
          <meshBasicMaterial color="#b06eff" transparent opacity={0.32} blending={THREE.AdditiveBlending} depthWrite={false} toneMapped={false} />
        </mesh>
      </group>

      {/* COMMAND-BEADS — pulses of the operator's words flowing INTO the socket */}
      <group ref={beadGroupRef} frustumCulled={false} renderOrder={11}>
        {Array.from({ length: BEAD_COUNT }).map((_, i) => (
          <mesh
            key={i}
            ref={(el) => {
              beadRefs.current[i] = el;
            }}
          >
            <sphereGeometry args={[0.02, 12, 12]} />
            <meshBasicMaterial color="#e6d4ff" transparent opacity={0} blending={THREE.AdditiveBlending} depthWrite={false} toneMapped={false} />
          </mesh>
        ))}
      </group>
    </group>
  );
}

/** Fade a junction group's layered spheres together (preserves each layer's own ratio). */
const BASE_OPACITY = new WeakMap<THREE.Material, number>();
function setGroupOpacity(group: THREE.Group, fade: number): void {
  group.traverse((obj) => {
    const mesh = obj as THREE.Mesh;
    if (!mesh.isMesh) return;
    const mat = mesh.material as THREE.MeshBasicMaterial;
    let base = BASE_OPACITY.get(mat);
    if (base === undefined) {
      base = mat.opacity;
      BASE_OPACITY.set(mat, base);
    }
    mat.opacity = base * fade;
  });
}
