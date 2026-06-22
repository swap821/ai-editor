'use client';

import { useEffect, useMemo, useRef } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import * as THREE from 'three';
import { samplePointField, type PointFieldSource, type PointFieldData } from '@/lib/pointFieldSampler';
import { buildSpinePoints, BODY_AXIS_MIN, BODY_AXIS_MAX } from '@/lib/spinePointField';
import { createPointFieldMaterial } from '@/lib/pointFieldMaterial';
import { lifecycleTargets } from '@/lib/pointFieldLifecycle';
import { getOrganismPhase } from '@/lib/organismPhaseBus';
import { getConversationPhase, conversationToOrganismPhase } from '@/lib/conversationPhaseBus';
import { setSpineFusion, setCortexAnchor, getCortexAnchor, getBrainDockScale } from '@/lib/spineFusionBus';
import { deriveCursorAttention } from '@/lib/cursorAttention';
import type { CognitionUniforms } from './SuperbrainScene';

/** Concatenate two point-field datasets into one (brain first, then spine). */
function mergeData(a: PointFieldData, b: PointFieldData): PointFieldData {
  const total = a.count + b.count;
  const m3 = (x: Float32Array, y: Float32Array) => {
    const o = new Float32Array(total * 3);
    o.set(x, 0); o.set(y, a.count * 3); return o;
  };
  const m1 = (x: Float32Array, y: Float32Array) => {
    const o = new Float32Array(total);
    o.set(x, 0); o.set(y, a.count); return o;
  };
  return {
    positions: m3(a.positions, b.positions),
    colors: m3(a.colors, b.colors),
    normals: m3(a.normals, b.normals),
    sizes: m1(a.sizes, b.sizes),
    phases: m1(a.phases, b.phases),
    speeds: m1(a.speeds, b.speeds),
    scatter: m3(a.scatter, b.scatter),
    births: m1(a.births, b.births),
    bands: m1(a.bands, b.bands),
    count: total,
  };
}

/** Centroid of the extreme-Y slice of a point set (lowest if `lowest`, else highest). */
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

/** Mean of a point set's upper region — the brain-HEAD/cortex centre (cloud-local).
 *  Biased to the top half so reabsorbing energy lands in the glowing head, not the
 *  lower brainstem. */
function headCentroid(pos: Float32Array, n: number): [number, number, number] {
  return extremeCentroid(pos, n, false, 0.55);
}

/**
 * The being's flesh as ONE additive point cloud (poster substrate).
 *   'brain' — sampled from the GLB clone; if `spineCount>0` the spine/roots are
 *             FUSED into the SAME geometry, with the cord-top welded to the brain's
 *             real brainstem vertices (computed centroid). One object, mounted in
 *             the brain's group → the join is perfect by construction and stays
 *             aligned from every orbit angle, permanently.
 *   'spine' — standalone cord (legacy / unused in the fused path).
 */
export default function BrainPointField({
  source,
  uniforms,
  count = 60000,
  kind = 'brain',
  baseSize = 2.0, // RTX-tuned crisp: smaller points resolve the dense cortex (folds + node lattice show; no white haze)
  spineScale = 1,
  spineCount = 0,
}: {
  /** processed brain clone (region-colored) — required for kind='brain'. */
  source?: THREE.Object3D;
  uniforms: CognitionUniforms;
  count?: number;
  kind?: 'brain' | 'spine';
  /** base point size in CSS px. */
  baseSize?: number;
  /** spine scene→brain-local scale (≈ 1/BRAIN_SCALE) when fusing the spine in. */
  spineScale?: number;
  /** if >0 and kind='brain', fuse a spine cloud into the SAME geometry (rigid join). */
  spineCount?: number;
}) {
  const materialRef = useRef<THREE.ShaderMaterial>(null);
  const gl = useThree((s) => s.gl);

  const geometry = useMemo(() => {
    let data: PointFieldData;
    if (kind === 'spine') {
      data = buildSpinePoints(count, 0x5350494e);
    } else {
      // aBand spans the FULL body axis so the flow band sweeps brain↔roots together.
      const brain = samplePointField(
        [{ object: source!, share: 1, axisMin: BODY_AXIS_MIN, axisMax: BODY_AXIS_MAX } as PointFieldSource],
        count,
        0x50494e54,
      );
      // Publish the brain-head centroid (cloud-local) so reabsorbing motes land in
      // the visible cortex (× the live brain dock scale), not a hardcoded point.
      setCortexAnchor(headCentroid(brain.positions, brain.count));
      if (spineCount > 0) {
        // FUSE the spine into the brain cloud — the cord grows from the brain's
        // REAL brainstem vertices, so the join is exact and orbit-proof by design.
        const spine = buildSpinePoints(spineCount, 0x5350494e);
        const anchor = extremeCentroid(brain.positions, brain.count, true, 0.04); // brain brainstem
        const cordTop = extremeCentroid(spine.positions, spine.count, false, 0.04); // spine cord-top
        const s = spineScale;
        // scale the scene-space spine to brain-local proportions, then translate so
        // its cord-top lands exactly on the brain's brainstem centroid.
        const tx = anchor[0] - cordTop[0] * s;
        const ty = anchor[1] - cordTop[1] * s;
        const tz = anchor[2] - cordTop[2] * s;
        // Publish the EXACT weld so work slabs can anchor onto the visible spine.
        setSpineFusion(s, [tx, ty, tz]);
        const sp = spine.positions;
        for (let i = 0; i < spine.count; i++) {
          sp[i * 3] = sp[i * 3] * s + tx;
          sp[i * 3 + 1] = sp[i * 3 + 1] * s + ty;
          sp[i * 3 + 2] = sp[i * 3 + 2] * s + tz;
          spine.sizes[i] *= 0.7; // spine dots a touch finer than the brain's
        }
        data = mergeData(brain, spine);
      } else {
        data = brain;
      }
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(data.positions, 3));
    g.setAttribute('aColor', new THREE.BufferAttribute(data.colors, 3));
    g.setAttribute('aNormal', new THREE.BufferAttribute(data.normals, 3));
    g.setAttribute('aSize', new THREE.BufferAttribute(data.sizes, 1));
    g.setAttribute('aPhase', new THREE.BufferAttribute(data.phases, 1));
    g.setAttribute('aSpeed', new THREE.BufferAttribute(data.speeds, 1));
    g.setAttribute('aScatter', new THREE.BufferAttribute(data.scatter, 3));
    g.setAttribute('aBirth', new THREE.BufferAttribute(data.births, 1));
    g.setAttribute('aBand', new THREE.BufferAttribute(data.bands, 1));
    return g;
  }, [source, count, kind, spineScale, spineCount]);

  const material = useMemo(
    () => {
      const m = createPointFieldMaterial({
        uTime: uniforms.uTime,
        uPostureColor: uniforms.uPosture,
        uPostureTint: uniforms.uPostureTint,
        uBreath: uniforms.uBreath, // phase-lock: points breathe on the shared organism clock
      });
      m.uniforms.uSize.value = baseSize;
      return m;
    },
    [uniforms, baseSize],
  );

  // Keep the on-screen point size DPR-correct: write the renderer's pixel ratio
  // into uPixelRatio (the vertex multiplies by it). Re-applied on resize/DPR change.
  const setDpr = () => {
    material.uniforms.uPixelRatio.value = gl.getPixelRatio();
  };
  useEffect(() => {
    setDpr();
    window.addEventListener('resize', setDpr);
    return () => {
      window.removeEventListener('resize', setDpr);
      geometry.dispose();
      material.dispose();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [geometry, material, gl]);

  // Honor reduced-motion: freeze the breathe/flow gains (the lit field stays
  // fully visible — we never blank it; large translations are the trigger).
  const reduce = useMemo(
    () =>
      typeof window !== 'undefined' &&
      !!window.matchMedia &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches,
    [],
  );

  // Dev-only live tuning dials: e.g. window.__POINTFIELD.uSize = 4,
  // window.__POINTFIELD.uGlowMul = 1.4, window.__POINTFIELD.uAttenK = 0.1.
  useEffect(() => {
    if (kind !== 'brain') return; // one dial owner (the brain material)
    if (typeof window === 'undefined' || process.env.NODE_ENV === 'production') return;
    (window as unknown as { __POINTFIELD?: unknown }).__POINTFIELD = new Proxy(
      {},
      {
        get: (_t, key: string) => material.uniforms[key]?.value,
        set: (_t, key: string, value: number) => {
          if (material.uniforms[key]) material.uniforms[key].value = value;
          return true;
        },
      },
    );
    // Proof hook for the reabsorption money-shot: the published cortex anchor
    // (cloud-local) × the live dock scale = the group-local point motes return to.
    (window as unknown as { __getCortexAnchor?: () => unknown }).__getCortexAnchor = () => ({
      anchor: getCortexAnchor(),
      dock: getBrainDockScale(),
      target: getCortexAnchor().map((v) => v * getBrainDockScale()),
    });
  }, [material, kind]);

  useFrame((state, delta) => {
    // uTime is the shared leaf (advanced by the scene); keep uPixelRatio fresh.
    setDpr();
    const u = material.uniforms;
    // Drive breathe / flow / arrival-inrush / reabsorption from the live organism
    // phase (the lifecycle gesture engine). All motion runs in the vertex shader;
    // here we only damp a few scalar uniforms via ref (zero per-point CPU).
    // A live chat turn drives the gesture targets (faster flow while streaming),
    // with priority over the idle organism phase.
    const organismPhase = getOrganismPhase();
    const convPhase = getConversationPhase();
    const phase = conversationToOrganismPhase(convPhase) ?? organismPhase;
    const t = lifecycleTargets(phase);
    // A pure CHAT reply streams with conversation phase 'streaming' (work-intent
    // turns deliberately set conversation to 'idle' so the lifecycle drives the
    // body — see GagosChrome). So 'streaming' here means the being is SPEAKING
    // BACK, not working a tab.
    const replyStreaming = convPhase === 'streaming';
    // Orchestrating/working: the brain cloud fades so the inner memory-node lattice
    // shows through (operator's reveal-while-working idea). Gate this on the REAL
    // lifecycle phase only — NEVER on a conversation reply. Previously a chat reply
    // mapped 'streaming'->'working' and wrongly dimmed the being mid-speech, the
    // opposite of the poster law (the cortex BRIGHTENS as it speaks, it never fades).
    const realWork =
      organismPhase === 'working' || organismPhase === 'conducting' || organismPhase === 'materializing';
    const bodyTarget = kind === 'brain' && realWork && !replyStreaming ? 0.28 : 1.0;
    // ARRIVAL bridge (poster phase 1): the scene's cinematic uArrival is INVERTED
    // from the point material's (scene: 1=mid-arrival/scattered, 0=settled; point
    // material: 0=scattered inrush origin, 1=condensed). Bridge them so the cloud
    // explodes-then-condenses in LOCKSTEP with the star funnel on load, and stays
    // condensed at rest. min() lets the lifecycle's own arrival stay authoritative
    // when it's lower (e.g. booting=0 keeps it scattered pre-ignition).
    const arrivalTarget = Math.min(t.arrival, 1 - uniforms.uArrival.value);
    if (reduce) {
      // reduced motion: snap to the settled state (no inrush/dissolve translation).
      u.uGrow.value = t.grow;
      u.uArrival.value = arrivalTarget;
      u.uReabsorb.value = t.reabsorb;
      u.uFlowSpeed.value = 0.05 + t.flow * 0.2;
      u.uBodyOpacity.value = bodyTarget;
    } else {
      u.uGrow.value = THREE.MathUtils.damp(u.uGrow.value, t.grow, 2, delta);
      u.uArrival.value = THREE.MathUtils.damp(u.uArrival.value, arrivalTarget, 1.6, delta);
      u.uReabsorb.value = THREE.MathUtils.damp(u.uReabsorb.value, t.reabsorb, 1.6, delta);
      u.uFlowSpeed.value = THREE.MathUtils.damp(u.uFlowSpeed.value, 0.05 + t.flow * 0.2, 3, delta);
      u.uBodyOpacity.value = THREE.MathUtils.damp(u.uBodyOpacity.value, bodyTarget, 3, delta);
    }
    // ARRIVAL ignition flash — direct passthrough of the scene's single-shot
    // ignition pulse (no damp, so the flash's timing/shape is preserved).
    if (u.uIgnite) u.uIgnite.value = uniforms.uIgnite.value;
    // AWAKENING (poster phase 3): the cortex HEATS while the being notices /
    // converses. Scoped to the NON-dimmed engaged phases (attentive=thinking,
    // intake) so it never fights the working-phase memory-node reveal (which
    // dims the cloud). Luminance only — the fragment weights it to the cortex.
    if (u.uAwaken) {
      // Cortex HEATS while the being notices (thinking = attentive/intake) AND
      // while it SPEAKS BACK (reply streaming) — the poster's "cortex brightens as
      // it speaks". Luminance only (the fragment weights it to the head/cortex).
      const phaseAwaken =
        phase === 'attentive' || phase === 'intake' ? 1 : replyStreaming ? 0.9 : 0;
      // THE BEING NOTICES YOU (poster phase 3): the cortex also warms toward the
      // pointer — a gentle floor (≤0.32) that the conversational heat above always
      // dominates. We feed the RAW pointer and let uAwaken's own damp smooth it
      // (so no extra ref); the lean direction lives in the scene (cursorAttention).
      const attn = deriveCursorAttention({
        pointerX: state.pointer.x,
        pointerY: state.pointer.y,
        active: kind === 'brain',
        reducedMotion: reduce,
      });
      const awakenTarget = Math.max(phaseAwaken, attn.brighten);
      u.uAwaken.value = reduce
        ? awakenTarget
        : THREE.MathUtils.damp(u.uAwaken.value, awakenTarget, 4, delta);
    }
    // REPLY RISE (poster phase 2/3): while the being speaks back, a luminance
    // bead-band climbs the spine into the cortex ("response flows back UP the
    // spine"). Reduced motion: no travelling band (the uAwaken cortex-heat above
    // still conveys "speaking"), avoiding vestibular travel.
    if (u.uReplyRise) {
      const riseTarget = replyStreaming ? 1 : 0;
      u.uReplyRise.value = reduce
        ? 0
        : THREE.MathUtils.damp(u.uReplyRise.value, riseTarget, 3, delta);
    }
    // ORCHESTRATION (poster phase 5): the spine/roots pulse with metabolic state
    // while the being works/conducts/materializes ("nerves carry the state").
    if (u.uStatePulse) {
      const stateTarget =
        phase === 'working' || phase === 'conducting' || phase === 'materializing' ? 1 : 0;
      u.uStatePulse.value = reduce
        ? stateTarget
        : THREE.MathUtils.damp(u.uStatePulse.value, stateTarget, 3, delta);
    }
    // VERTEBRAE REVEAL (poster phase 5): while orchestrating, the cord shows its
    // distinct vertebral segments (addressable seats). Same gate as the state-pulse;
    // eases in/out so the spine "extends and reveals vertebrae" rather than snapping.
    if (u.uVertebrae) {
      const vertTarget =
        phase === 'working' || phase === 'conducting' || phase === 'materializing' ? 1 : 0;
      u.uVertebrae.value = reduce
        ? vertTarget
        : THREE.MathUtils.damp(u.uVertebrae.value, vertTarget, 2.5, delta);
    }
    // REABSORPTION (poster phase 7): the brain inhales as a finished tab returns
    // its energy up the spine. The damp gives a smooth rise-then-fall around the
    // brief reabsorbing beat.
    if (u.uReabsorbGlow) {
      const reabsorbTarget = phase === 'reabsorbing' ? 1 : 0;
      u.uReabsorbGlow.value = reduce
        ? reabsorbTarget
        : THREE.MathUtils.damp(u.uReabsorbGlow.value, reabsorbTarget, 2.5, delta);
    }
  });

  return (
    <points geometry={geometry} frustumCulled={false} renderOrder={3}>
      <primitive object={material} ref={materialRef} attach="material" />
    </points>
  );
}
