'use client';

// GpuPostFX — the WebGPU post pass for the ?gpu=webgpu spike. The WebGL PostFX
// (@react-three/postprocessing EffectComposer) can't run on a WebGPURenderer, so
// under the flag we rebuild the chain in TSL. Order matches PostFX.tsx:
//   ChromaticAberration → Bloom → GradePre → Vignette → AgX(+sRGB via renderOutput)
//
// Parity scope: CA, bloom, GradePre (scene-referred log contrast), and vignette all
// run pre-tonemap, then renderOutput applies AgX + sRGB (the proven terminal). The
// post-tonemap GradePost split-tone + film grain are DEFERRED — they require a
// display-referred pass after AgX, which in TSL needs the manual tonemap→encode path
// (agxToneMapping/workingToColorSpace) that misbehaved here; best finished at the RTX.
//
// Takes over the render loop via useFrame priority 1 (compute dispatch at p0 first).
// Lazy-loaded → three/webgpu + the TSL bloom addon never enter the default bundle.
// Live dials for RTX tuning: window.__GPUBLOOM.{strength,radius,threshold} +
// window.__POINTFIELD_GPU.{uGlowMul,uSize}.
import { useEffect, useMemo } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import * as THREE from 'three/webgpu';
import {
  pass, renderOutput, screenUV, vec3, vec4, float, max, log2, exp2, smoothstep,
} from 'three/tsl';
import { bloom } from 'three/addons/tsl/display/BloomNode.js';
import { POST_FX } from '@/lib/constants';

// GPU-additive-field bloom (NOT POST_FX.bloomPoints — the 250k additive field has a
// far wider dynamic range; the WebGL knobs over-bloom it to a white sun).
const GPU_BLOOM = { strength: 0.35, radius: 0.55, threshold: 1.6 };

export default function GpuPostFX() {
  const gl = useThree((s) => s.gl);
  const scene = useThree((s) => s.scene);
  const camera = useThree((s) => s.camera);

  const post = useMemo(() => {
    const g = POST_FX.grade;
    const vig = POST_FX.vignettePoints;

    const pp = new THREE.PostProcessing(gl as unknown as THREE.WebGPURenderer);
    const scenePass = pass(scene, camera);
    const scenePassColor = scenePass.getTextureNode();

    // 1) Bloom on the scene → HDR (the proven base; scenePassColor is the render-wired
    // texture node — sampling the raw getTexture() at offset UVs returns black, which
    // is why ChromaticAberration is deferred rather than shipped broken).
    const bloomPass = bloom(scenePassColor, GPU_BLOOM.strength, GPU_BLOOM.radius, GPU_BLOOM.threshold);
    let hdr = (scenePassColor as unknown as ReturnType<typeof vec3>).rgb
      .add((bloomPass as unknown as ReturnType<typeof vec3>).rgb) as ReturnType<typeof vec3>;

    // 2) GradePre — log-space contrast around the mid-grey pivot, scene-referred.
    const lc = log2(max(hdr, vec3(1e-5))).add(9.72).div(17.52);
    const lc2 = lc.sub(0.4135884).mul(g.contrast).add(0.4135884);
    hdr = exp2(lc2.mul(17.52).sub(9.72)) as ReturnType<typeof vec3>;

    // 3) Vignette — frame the void as "home" (pre-tonemap multiply; AgX rolls it off).
    const d = screenUV.sub(0.5).length().mul(1.4142);
    const vignette = float(1.0).sub(smoothstep(vig.offset, 1.0, d).mul(vig.darkness));
    hdr = hdr.mul(vignette) as ReturnType<typeof vec3>;

    // 4) AgX tonemap + sRGB encode (renderer.toneMapping = AgX, set in the factory) —
    // the proven terminal. (GradePost split-tone + grain are post-tonemap; deferred.)
    pp.outputColorTransform = false;
    pp.outputNode = renderOutput(vec4(hdr, 1.0));
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
