import { useEffect, useRef, useState } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { Stars, Sparkles, Float, MeshDistortMaterial, PerformanceMonitor } from '@react-three/drei';
import { EffectComposer, Bloom, ChromaticAberration, Vignette } from '@react-three/postprocessing';
import { Vector2 } from 'three';

/* ──────────────────────────────────────────────────────────────────────────
   SpatialScene — a real-time 3D backdrop that lives BEHIND the glass UI.

   A deep starfield + a morphing emissive "AI core" that spins up and glows
   violet while the agent generates, lit by violet/cyan rim-lights, finished
   with bloom + subtle chromatic aberration + vignette, and parallaxed by the
   cursor. It is the *backdrop* only (z-index:-1, pointer-events:none) — the
   editor/terminal stay crisp DOM on top.

   Hardware-aware: forces the discrete GPU (powerPreference high-performance),
   caps dpr and auto-downscales under load (PerformanceMonitor), pauses the
   render loop when the tab is hidden, and renders a single static frame under
   prefers-reduced-motion.
   ────────────────────────────────────────────────────────────────────────── */

const CA_OFFSET = new Vector2(0.0007, 0.0007);

function AiCore({ energyRef }) {
  const mesh = useRef();
  const mat = useRef();
  useFrame((_, delta) => {
    const e = energyRef.current;
    if (mesh.current) {
      mesh.current.rotation.y += delta * (0.12 + e * 0.6);
      mesh.current.rotation.x += delta * (0.05 + e * 0.25);
    }
    if (mat.current) {
      mat.current.distort = 0.26 + e * 0.32;
      mat.current.speed = 1.2 + e * 3.5;
      mat.current.emissiveIntensity = 0.5 + e * 1.9;
    }
  });
  return (
    <Float speed={1.4} rotationIntensity={0.5} floatIntensity={0.7}>
      <mesh ref={mesh}>
        <icosahedronGeometry args={[1.45, 14]} />
        <MeshDistortMaterial
          ref={mat}
          color="#241654"
          emissive="#7c3aed"
          emissiveIntensity={0.6}
          roughness={0.15}
          metalness={0.92}
          distort={0.28}
          speed={1.4}
        />
      </mesh>
    </Float>
  );
}

function Rig({ mouseRef, energyRef, targetRef }) {
  useFrame((state) => {
    // Ease the AI-energy toward its target, and parallax the camera to the cursor.
    energyRef.current += (targetRef.current - energyRef.current) * 0.04;
    const m = mouseRef.current;
    state.camera.position.x += (m.x * 0.9 - state.camera.position.x) * 0.04;
    state.camera.position.y += (m.y * 0.55 - state.camera.position.y) * 0.04;
    state.camera.lookAt(0, 0, 0);
  });
  return null;
}

export default function SpatialScene({ energy = 0.15 }) {
  const mouseRef = useRef({ x: 0, y: 0 });
  const energyRef = useRef(energy);
  const targetRef = useRef(energy);
  const [dpr, setDpr] = useState(1.25);
  const [frameloop, setFrameloop] = useState('always');
  const reduced =
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  useEffect(() => { targetRef.current = energy; }, [energy]);

  useEffect(() => {
    const onMove = (e) => {
      mouseRef.current.x = (e.clientX / window.innerWidth) * 2 - 1;
      mouseRef.current.y = -((e.clientY / window.innerHeight) * 2 - 1);
    };
    const onVis = () => setFrameloop(document.hidden ? 'never' : 'always');
    window.addEventListener('pointermove', onMove);
    document.addEventListener('visibilitychange', onVis);
    return () => {
      window.removeEventListener('pointermove', onMove);
      document.removeEventListener('visibilitychange', onVis);
    };
  }, []);

  return (
    <div aria-hidden="true" style={{ position: 'fixed', inset: 0, zIndex: -1, pointerEvents: 'none' }}>
      <Canvas
        dpr={dpr}
        frameloop={reduced ? 'demand' : frameloop}
        camera={{ position: [0, 0, 6], fov: 50 }}
        gl={{ powerPreference: 'high-performance', antialias: false, alpha: false, stencil: false }}
      >
        <color attach="background" args={['#050507']} />
        <fog attach="fog" args={['#050507', 6, 19]} />

        <ambientLight intensity={0.35} />
        <directionalLight position={[6, 4, 6]} intensity={2.2} color="#8b5cf6" />
        <directionalLight position={[-6, -3, 2]} intensity={1.6} color="#22d3ee" />
        <pointLight position={[0, 0, 3]} intensity={1.2} color="#3b82f6" />

        <AiCore energyRef={energyRef} />
        <Stars radius={60} depth={45} count={1300} factor={3.2} saturation={0.6} fade speed={0.5} />
        <Sparkles count={45} scale={[12, 8, 8]} size={3} speed={0.35} color="#a78bfa" opacity={0.6} />

        <Rig mouseRef={mouseRef} energyRef={energyRef} targetRef={targetRef} />

        {!reduced && (
          <PerformanceMonitor onDecline={() => setDpr(1)} onIncline={() => setDpr(1.25)} />
        )}

        <EffectComposer disableNormalPass>
          <Bloom intensity={1.25} luminanceThreshold={0.18} luminanceSmoothing={0.45} mipmapBlur radius={0.75} />
          <ChromaticAberration offset={CA_OFFSET} />
          <Vignette offset={0.32} darkness={0.85} />
        </EffectComposer>
      </Canvas>
    </div>
  );
}
