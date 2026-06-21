'use client';

// GpuBrainPointField — the WebGPU/TSL substrate (flagged "Million-Mote Mind" spike).
// A DROP-IN for BrainPointField under ?gpu=webgpu: same props, same sampler, same
// lifecycle/posture buses — only the simulation+draw substrate changes (CPU vertex
// attrs → GPU compute particles). The default WebGL path (BrainPointField) is untouched;
// this module is dynamically imported, so three/webgpu never enters the default bundle.
//
// On-device fidelity/perf is the operator's RTX call (.aios/state/GAGOS_WEBGPU_SPIKE.md).
import { useEffect, useMemo } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import * as THREE from 'three';
import { samplePointField, type PointFieldSource, type PointFieldData } from '@/lib/pointFieldSampler';
import { buildSpinePoints, BODY_AXIS_MIN, BODY_AXIS_MAX } from '@/lib/spinePointField';
import { lifecycleTargets } from '@/lib/pointFieldLifecycle';
import { getOrganismPhase } from '@/lib/organismPhaseBus';
import { getConversationPhase, conversationToOrganismPhase } from '@/lib/conversationPhaseBus';
import { setSpineFusion } from '@/lib/spineFusionBus';
import { buildGpuPointField, type GpuAnchors } from '@/lib/gpuPointFieldTSL';
import type { CognitionUniforms } from './SuperbrainScene';

/** brain-first, then-spine concat (mirrors BrainPointField.mergeData). */
function mergeData(a: PointFieldData, b: PointFieldData): PointFieldData {
  const total = a.count + b.count;
  const m3 = (x: Float32Array, y: Float32Array) => {
    const o = new Float32Array(total * 3); o.set(x, 0); o.set(y, a.count * 3); return o;
  };
  const m1 = (x: Float32Array, y: Float32Array) => {
    const o = new Float32Array(total); o.set(x, 0); o.set(y, a.count); return o;
  };
  return {
    positions: m3(a.positions, b.positions), colors: m3(a.colors, b.colors),
    normals: m3(a.normals, b.normals), sizes: m1(a.sizes, b.sizes),
    phases: m1(a.phases, b.phases), speeds: m1(a.speeds, b.speeds),
    scatter: m3(a.scatter, b.scatter), births: m1(a.births, b.births),
    bands: m1(a.bands, b.bands), count: total,
  };
}

function extremeCentroid(pos: Float32Array, n: number, lowest: boolean, frac: number): [number, number, number] {
  let minY = Infinity, maxY = -Infinity;
  for (let i = 0; i < n; i++) { const y = pos[i * 3 + 1]; if (y < minY) minY = y; if (y > maxY) maxY = y; }
  const cut = lowest ? minY + (maxY - minY) * frac : maxY - (maxY - minY) * frac;
  let sx = 0, sy = 0, sz = 0, c = 0;
  for (let i = 0; i < n; i++) {
    const y = pos[i * 3 + 1];
    if (lowest ? y <= cut : y >= cut) { sx += pos[i * 3]; sy += y; sz += pos[i * 3 + 2]; c++; }
  }
  c = c || 1;
  return [sx / c, sy / c, sz / c];
}

export default function GpuBrainPointField({
  source,
  uniforms,
  count = 250000,
  spineScale = 1,
  spineCount = 0,
  baseSize = 1.5, // with-bloom default (GpuPostFX rolls off >1; see gpuPointFieldTSL note)
}: {
  source?: THREE.Object3D;
  uniforms: CognitionUniforms;
  count?: number;
  spineScale?: number;
  spineCount?: number;
  baseSize?: number;
}) {
  const gl = useThree((s) => s.gl) as unknown as { computeAsync?: (node: unknown) => void };

  const reduce = useMemo(
    () => typeof window !== 'undefined' && !!window.matchMedia &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches,
    [],
  );

  // Build the merged anchor set (same brain + fused-spine geometry as the WebGL path),
  // then hand it to the GPU compute+render builder.
  const field = useMemo(() => {
    const brain = samplePointField(
      [{ object: source!, share: 1, axisMin: BODY_AXIS_MIN, axisMax: BODY_AXIS_MAX } as PointFieldSource],
      count,
      0x50494e54,
    );
    let data: PointFieldData = brain;
    if (spineCount > 0) {
      const spine = buildSpinePoints(spineCount, 0x5350494e);
      const anchor = extremeCentroid(brain.positions, brain.count, true, 0.04);
      const cordTop = extremeCentroid(spine.positions, spine.count, false, 0.04);
      const s = spineScale;
      const tx = anchor[0] - cordTop[0] * s;
      const ty = anchor[1] - cordTop[1] * s;
      const tz = anchor[2] - cordTop[2] * s;
      setSpineFusion(s, [tx, ty, tz]); // work slabs anchor onto the visible spine
      const sp = spine.positions;
      for (let i = 0; i < spine.count; i++) {
        sp[i * 3] = sp[i * 3] * s + tx;
        sp[i * 3 + 1] = sp[i * 3 + 1] * s + ty;
        sp[i * 3 + 2] = sp[i * 3 + 2] * s + tz;
        spine.sizes[i] *= 0.7;
      }
      data = mergeData(brain, spine);
    }
    const anchors: GpuAnchors = {
      positions: data.positions, colors: data.colors, scatter: data.scatter,
      births: data.births, bands: data.bands, sizes: data.sizes, count: data.count,
    };
    const built = buildGpuPointField(anchors);
    built.P.uSize.value = baseSize;
    return built;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [source, count, spineScale, spineCount]);

  // Dev-only live dials on the GPU field (parity with __POINTFIELD): e.g.
  // window.__POINTFIELD_GPU.uSize = 3.2, .uGlowMul = 2.2.
  useEffect(() => {
    if (typeof window === 'undefined' || process.env.NODE_ENV === 'production') return;
    (window as unknown as { __POINTFIELD_GPU?: unknown }).__POINTFIELD_GPU = new Proxy(
      {},
      {
        get: (_t, k: string) => (field.P as Record<string, { value: number }>)[k]?.value,
        set: (_t, k: string, v: number) => {
          const u = (field.P as Record<string, { value: number }>)[k];
          if (u) u.value = v;
          return true;
        },
      },
    );
  }, [field]);

  useFrame((_state, delta) => {
    const phase = conversationToOrganismPhase(getConversationPhase()) ?? getOrganismPhase();
    const t = lifecycleTargets(phase);
    const { U, P } = field;
    U.uDt.value = Math.min(delta, 1 / 30);

    // ARRIVAL bridge (poster phase 1) — inverted from the scene's cinematic uArrival,
    // identical to BrainPointField so the cloud condenses in lockstep with the funnel.
    const arrivalTarget = Math.min(t.arrival, 1 - uniforms.uArrival.value);
    const curlTarget = 0.012 + t.flow * 0.02;
    if (reduce) {
      U.uGrow.value = t.grow;
      U.uArrival.value = arrivalTarget;
      U.uReabsorb.value = t.reabsorb;
      U.uCurlAmp.value = 0.004; // calm churn only
    } else {
      U.uGrow.value = THREE.MathUtils.damp(U.uGrow.value, t.grow, 2, delta);
      U.uArrival.value = THREE.MathUtils.damp(U.uArrival.value, arrivalTarget, 1.6, delta);
      U.uReabsorb.value = THREE.MathUtils.damp(U.uReabsorb.value, t.reabsorb, 1.6, delta);
      U.uCurlAmp.value = THREE.MathUtils.damp(U.uCurlAmp.value, curlTarget, 3, delta);
    }

    // SACRED hue passthrough + luminance flashes (never recolored on the GPU).
    P.uPostureColor.value.copy(uniforms.uPosture.value as unknown as THREE.Color);
    P.uPostureTint.value = uniforms.uPostureTint.value;
    P.uIgnite.value = uniforms.uIgnite.value;
    const awakenTarget = phase === 'attentive' || phase === 'intake' ? 1 : 0;
    const stateTarget = phase === 'working' || phase === 'conducting' || phase === 'materializing' ? 1 : 0;
    P.uAwaken.value = reduce ? awakenTarget : THREE.MathUtils.damp(P.uAwaken.value, awakenTarget, 4, delta);
    P.uStatePulse.value = reduce ? stateTarget : THREE.MathUtils.damp(P.uStatePulse.value, stateTarget, 3, delta);

    // dispatch the simulation for this frame (no-op if the renderer isn't WebGPU)
    gl.computeAsync?.(field.computeStep);
  });

  useEffect(
    () => () => {
      (field.mesh.material as THREE.Material)?.dispose?.();
    },
    [field],
  );

  return <primitive object={field.mesh} />;
}
