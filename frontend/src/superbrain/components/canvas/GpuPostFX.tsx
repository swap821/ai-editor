'use client';

// GpuPostFX — the WebGPU post pass for the ?gpu=webgpu spike. The WebGL PostFX
// (@react-three/postprocessing EffectComposer) cannot run on a WebGPURenderer, so
// under the flag we rebuild the essential chain in TSL: scene → Bloom → AgX. This
// restores the highlight rolloff that keeps the dense brain canopy from clipping to
// white (additive >1 emission).
//
// The 250k-particle additive field has a MUCH wider dynamic range than the WebGL
// field (dense cortex vs sparse roots), so it needs GPU-SPECIFIC bloom params
// (gentler strength, higher threshold) than POST_FX.bloomPoints — otherwise the
// brain over-blooms into a sun. These + the emission are exposed as live dials:
//   window.__GPUBLOOM.strength / .radius / .threshold   (this pass)
//   window.__POINTFIELD_GPU.uGlowMul / .uSize            (per-particle emission)
// so the operator tunes the whole look on the real RTX. On-device fidelity = his call.
//
// Takes over the render loop via useFrame priority 1 (so the GpuBrainPointField
// compute dispatch at priority 0 runs first). Lazy-loaded → three/webgpu + the TSL
// bloom addon never enter the default WebGL bundle.
import { useEffect, useMemo } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import * as THREE from 'three/webgpu';
import { pass, renderOutput } from 'three/tsl';
import { bloom } from 'three/addons/tsl/display/BloomNode.js';

// GPU-additive-field bloom defaults (NOT POST_FX.bloomPoints — see note above).
const GPU_BLOOM = { strength: 0.35, radius: 0.55, threshold: 1.6 };

export default function GpuPostFX() {
  const gl = useThree((s) => s.gl);
  const scene = useThree((s) => s.scene);
  const camera = useThree((s) => s.camera);

  const post = useMemo(() => {
    const pp = new THREE.PostProcessing(gl as unknown as THREE.WebGPURenderer);
    const scenePass = pass(scene, camera);
    const scenePassColor = scenePass.getTextureNode();
    // bloom(node, strength, radius, threshold) — UnrealBloom-style soft-knee threshold.
    const bloomPass = bloom(scenePassColor, GPU_BLOOM.strength, GPU_BLOOM.radius, GPU_BLOOM.threshold);
    // Apply AgX (renderer.toneMapping, set in the WebGPU factory) + sRGB ONCE, on the
    // HDR (scene + bloom) — bloom on scene-referred linear, exactly like the WebGL chain.
    pp.outputColorTransform = false;
    pp.outputNode = renderOutput(scenePassColor.add(bloomPass));
    return { pp, bloomPass };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gl, scene, camera]);

  // Dev-only live bloom dial for the operator's RTX session.
  useEffect(() => {
    if (typeof window === 'undefined' || process.env.NODE_ENV === 'production') return;
    const bp = post.bloomPass as unknown as {
      strength: { value: number }; radius: { value: number }; threshold: { value: number };
    };
    (window as unknown as { __GPUBLOOM?: unknown }).__GPUBLOOM = new Proxy(
      {},
      {
        get: (_t, k: string) => bp[k as 'strength' | 'radius' | 'threshold']?.value,
        set: (_t, k: string, v: number) => {
          const u = bp[k as 'strength' | 'radius' | 'threshold'];
          if (u) u.value = v;
          return true;
        },
      },
    );
  }, [post]);

  useEffect(() => () => { post.pp.dispose?.(); }, [post]);

  // priority 1 → r3f hands us the render loop; we drive the post chain each frame.
  useFrame(() => {
    post.pp.renderAsync();
  }, 1);

  return null;
}
