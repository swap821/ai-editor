'use client';

import { useEffect, useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import type { CognitiveMode } from '@/components/ui/SuperbrainHUD';
import type { CognitionUniforms } from './SuperbrainScene';
import { createSeededRandom } from '@/lib/seededRandom';

/* -------------------------------------------------------------------------- */
/*  Two-shell fake volume                                                      */
/*                                                                             */
/*  The aura no longer fakes the brain with spheres — both shells reuse the    */
/*  PROCESSED brain geometry (smooth normals + baked region vertex colors)     */
/*  cloned from the cortex, so the volume cues hug the real silhouette:        */
/*                                                                             */
/*    membrane (1.025, BackSide)  — a thin region-tinted atmosphere film just  */
/*                                  outside the cortex; depth-tested against   */
/*                                  the cortex so it survives only as a halo   */
/*                                  hugging the silhouette.                    */
/*    nucleus  (0.85, FrontSide)  — the rose SSS hue glowing brightest at the  */
/*                                  CENTER of the form. Drawn BEFORE the       */
/*                                  cortex (renderOrder -1) so it ghosts       */
/*                                  through the cortex's 0.94 alpha — a        */
/*                                  luminous interior, not a painted skin.     */
/*                                                                             */
/*  Both shells stay below 0.5 output luminance: volume cues, not light        */
/*  sources. Breath/burst arrive through the SHARED CognitionUniforms leaves   */
/*  written once per frame by SuperbrainScene, so the whole organism swells    */
/*  on the same systole. The old fresnel sphere + corona layers are folded     */
/*  into these shells; only the tiny orbiting sparks survive from the old      */
/*  aura.                                                                      */
/* -------------------------------------------------------------------------- */

const TAU = Math.PI * 2;

/** Membrane sits just off the cortex; nucleus glows deep inside it. */
const MEMBRANE_SCALE = 1.025;
const CORE_SCALE = 0.85;

/**
 * Brain-group-local center of the measured GLB bounds — keep in sync with
 * BRAIN_MIN / BRAIN_MAX in SuperbrainScene.tsx. The GLB's origin is OFFSET
 * from the anatomical center, so the shells must scale about this point or
 * the 0.85 nucleus would sag out of the skull.
 */
const BRAIN_CENTER = new THREE.Vector3(0.0015, 0.2055, 0.057);

/** Orbit radius in brain-group-local units (local brain radius ≈ 0.50). */
const SPARK_ORBIT_RADIUS = 0.48;
const SPARK_COUNT = 50;

/* ---------- mode-reactive spark color temperature ---------- */
const AURA_MODE_COLORS: Record<CognitiveMode, THREE.Color> = {
  observe: new THREE.Color('#40e8ff'),      // deep cool cyan — scanning
  synthesize: new THREE.Color('#aef2ff'),   // warmer, whiter — processing heat
  orchestrate: new THREE.Color('#8f7bff'),  // violet-shifted — commanding
};

/** YELLOW-zone amber for the approval hold — accent, never a theme. */
const AURA_HOLD_AMBER = new THREE.Color('#ffb454');


/*  Shell shaders (shared vertex pass — view-space normal + region color)      */
/* -------------------------------------------------------------------------- */

const SHELL_VERTEX_SHADER = /* glsl */ `
  varying vec3 vNormalV;
  varying vec3 vViewDirV;
  varying vec3 vColorV;

  void main() {
    vNormalV = normalize(normalMatrix * normal);
    vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
    vViewDirV = -mvPosition.xyz;
    vColorV = color;
    gl_Position = projectionMatrix * mvPosition;
  }
`;

const MEMBRANE_FRAGMENT_SHADER = /* glsl */ `
  uniform float uBreath;
  uniform float uBurst;

  varying vec3 vNormalV;
  varying vec3 vViewDirV;
  varying vec3 vColorV;

  void main() {
    vec3 N = normalize(vNormalV);
    vec3 V = normalize(vViewDirV);

    // BackSide hull: raw normals face AWAY from the camera, so dot(N, V) runs
    // 0 (silhouette) .. -1 (far pole). The lobe brightens just inside the
    // silhouette; the hard 0.25 cap keeps it a film, never a light source.
    float a = pow(max(0.6 - dot(N, V), 0.0), 4.0);
    a = min(a * (0.85 + 0.30 * uBreath + uBurst * 0.45), 0.25);

    // Region-tinted atmosphere: additive output peaks at 1.4 * 0.25 = 0.35.
    gl_FragColor = vec4(vColorV * 1.4, a);
  }
`;

const CORE_FRAGMENT_SHADER = /* glsl */ `
  uniform float uBreath;
  uniform float uBurst;

  varying vec3 vNormalV;
  varying vec3 vViewDirV;
  varying vec3 vColorV;

  void main() {
    vec3 N = normalize(vNormalV);
    vec3 V = normalize(vViewDirV);

    // Inverse fresnel: brightest at the CENTER of the form — a nucleus
    // ghosting through the dark cortex, the opposite falloff of a rim glow.
    float facing = pow(clamp(dot(N, V), 0.0, 1.0), 2.0);
    float a = min(facing * (0.70 + 0.45 * uBreath + uBurst * 0.50), 1.0);

    // The cortex SSS rose hue with a regional whisper, held at ~0.4 luminance
    // so the nucleus reads as interior light, never bloom.
    vec3 hue = mix(vec3(1.0, 0.25, 0.45), vColorV, 0.12);
    gl_FragColor = vec4(hue * 0.4, a);
  }
`;

/* -------------------------------------------------------------------------- */
/*  Synaptic sparks — tiny motes orbiting the cortex on great circles          */
/* -------------------------------------------------------------------------- */

interface SparkData {
  positions: Float32Array;
  axisX: Float32Array;
  axisY: Float32Array;
  axisZ: Float32Array;
  phases: Float32Array;
  speeds: Float32Array;
  tints: Float32Array;
}

function createSparkData(): SparkData {
  const random = createSeededRandom(0x4e455552);
  const positions = new Float32Array(SPARK_COUNT * 3);
  const axisX = new Float32Array(SPARK_COUNT);
  const axisY = new Float32Array(SPARK_COUNT);
  const axisZ = new Float32Array(SPARK_COUNT);
  const phases = new Float32Array(SPARK_COUNT);
  const speeds = new Float32Array(SPARK_COUNT);
  const tints = new Float32Array(SPARK_COUNT);

  for (let i = 0; i < SPARK_COUNT; i++) {
    // Random orbital axis (unit vector on sphere)
    const theta = random() * TAU;
    const phi = Math.acos(2 * random() - 1);
    axisX[i] = Math.sin(phi) * Math.cos(theta);
    axisY[i] = Math.sin(phi) * Math.sin(theta);
    axisZ[i] = Math.cos(phi);

    phases[i] = random() * TAU;
    speeds[i] = 0.4 + random() * 0.6;
    // 0 = mode color, 1 = pale star tint
    tints[i] = random() < 0.65 ? 0.0 : 1.0;
  }

  return { positions, axisX, axisY, axisZ, phases, speeds, tints };
}

const SPARK_VERTEX_SHADER = /* glsl */ `
  uniform float uTime;
  uniform float uActivity;
  uniform vec3 uColor;

  attribute float aAxisX;
  attribute float aAxisY;
  attribute float aAxisZ;
  attribute float aPhase;
  attribute float aSpeed;
  attribute float aTint;

  varying vec3 vColor;
  varying float vAlpha;

  void main() {
    // Build great-circle orbit: two orthonormal vectors perpendicular to the axis.
    vec3 axis = normalize(vec3(aAxisX, aAxisY, aAxisZ));
    // Choose an arbitrary "up" that isn't parallel to axis
    vec3 up = abs(axis.y) < 0.99 ? vec3(0.0, 1.0, 0.0) : vec3(1.0, 0.0, 0.0);
    vec3 tangent = normalize(cross(axis, up));
    vec3 bitangent = cross(axis, tangent);

    float angle = aPhase + uTime * aSpeed;
    float r = ${SPARK_ORBIT_RADIUS.toFixed(4)};
    vec3 transformed = (cos(angle) * tangent + sin(angle) * bitangent) * r;

    vec4 mvPosition = modelViewMatrix * vec4(transformed, 1.0);
    float distanceScale = 46.0 / max(8.0, -mvPosition.z);
    gl_PointSize = clamp((1.0 + aTint * 0.5) * distanceScale * (0.8 + uActivity * 0.4), 0.8, 2.8);
    gl_Position = projectionMatrix * mvPosition;

    // Flicker — per-spark phase offsets, never a body-wide pulse.
    float flicker = 0.7 + 0.3 * sin(uTime * 3.8 + aPhase * 11.0);

    // Pale star tint, never pure white (ACES clips white to paper).
    vec3 star = vec3(0.82, 0.88, 1.0);
    vColor = mix(uColor, star, aTint) * (1.2 + uActivity * 0.6);
    vAlpha = (0.45 + uActivity * 0.45) * flicker;
  }
`;

const SPARK_FRAGMENT_SHADER = /* glsl */ `
  varying vec3 vColor;
  varying float vAlpha;

  void main() {
    float radius = length(gl_PointCoord - vec2(0.5));
    if (radius > 0.5) discard;
    float core = 1.0 - smoothstep(0.0, 0.5, radius);
    gl_FragColor = vec4(vColor * (0.7 + core * 0.6), vAlpha * core);
  }
`;

/* -------------------------------------------------------------------------- */
/*  Component                                                                  */
/* -------------------------------------------------------------------------- */

export default function NeuralAura({
  activity,
  mode,
  source,
  uniforms,
  shells: shellBudget = 2,
}: {
  activity: number;
  mode: CognitiveMode;
  /** Processed brain clone (smooth normals + baked region vertex colors). */
  source: THREE.Object3D;
  uniforms: CognitionUniforms;
  /** Shell budget (quality tier): 2 = membrane + nucleus, 1 = membrane only. */
  shells?: 1 | 2;
}) {
  const sparkMaterialRef = useRef<THREE.ShaderMaterial>(null);
  const smoothedActivityRef = useRef(THREE.MathUtils.clamp(activity, 0, 1));

  const sparkData = useMemo(() => createSparkData(), []);

  const auraColor = useMemo(() => AURA_MODE_COLORS.observe.clone(), []);

  const sparkUniforms = useMemo(
    () => ({
      // Shared time leaf — sparks orbit on the same clock as the cortex.
      uTime: uniforms.uTime,
      uActivity: { value: 0 },
      uColor: { value: auraColor },
    }),
    [auraColor, uniforms],
  );

  // Both shells clone(true) the processed brain — the clones SHARE the baked
  // geometry (color attribute + smooth normals), so the shells read the same
  // region map as the cortex for free. Only the materials are replaced.
  const shells = useMemo(() => {
    const membraneMaterial = new THREE.ShaderMaterial({
      uniforms: { uBreath: uniforms.uBreath, uBurst: uniforms.uBurst },
      vertexShader: SHELL_VERTEX_SHADER,
      fragmentShader: MEMBRANE_FRAGMENT_SHADER,
      vertexColors: true,
      transparent: true,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      side: THREE.BackSide,
      toneMapped: false,
    });
    const coreMaterial = new THREE.ShaderMaterial({
      uniforms: { uBreath: uniforms.uBreath, uBurst: uniforms.uBurst },
      vertexShader: SHELL_VERTEX_SHADER,
      fragmentShader: CORE_FRAGMENT_SHADER,
      vertexColors: true,
      transparent: true,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      depthTest: true,
      side: THREE.FrontSide,
      toneMapped: false,
    });

    const dress = (root: THREE.Object3D, material: THREE.Material, renderOrder: number) => {
      root.traverse((object) => {
        if (!(object instanceof THREE.Mesh)) return;
        object.material = material;
        object.renderOrder = renderOrder;
      });
      return root;
    };

    return {
      // Membrane AFTER the cortex (renderOrder 1): depth-tested down to a
      // silhouette halo. Nucleus BEFORE the cortex (renderOrder -1): the
      // cortex's 0.94-alpha blend lets the interior glow ghost through.
      membrane: dress(source.clone(true), membraneMaterial, 1),
      core: dress(source.clone(true), coreMaterial, -1),
      membraneMaterial,
      coreMaterial,
    };
  }, [source, uniforms]);

  useEffect(
    () => () => {
      // Geometry is shared with the cortex — dispose only our materials.
      shells.membraneMaterial.dispose();
      shells.coreMaterial.dispose();
    },
    [shells],
  );

  const sparkGeometry = useMemo(() => {
    const geom = new THREE.BufferGeometry();
    geom.setAttribute('position', new THREE.BufferAttribute(sparkData.positions, 3));
    geom.setAttribute('aAxisX', new THREE.BufferAttribute(sparkData.axisX, 1));
    geom.setAttribute('aAxisY', new THREE.BufferAttribute(sparkData.axisY, 1));
    geom.setAttribute('aAxisZ', new THREE.BufferAttribute(sparkData.axisZ, 1));
    geom.setAttribute('aPhase', new THREE.BufferAttribute(sparkData.phases, 1));
    geom.setAttribute('aSpeed', new THREE.BufferAttribute(sparkData.speeds, 1));
    geom.setAttribute('aTint', new THREE.BufferAttribute(sparkData.tints, 1));
    return geom;
  }, [sparkData]);

  useEffect(() => {
    return () => {
      sparkGeometry.dispose();
    };
  }, [sparkGeometry]);

  useFrame((state, delta) => {
    smoothedActivityRef.current = THREE.MathUtils.damp(
      smoothedActivityRef.current,
      THREE.MathUtils.clamp(activity, 0, 1),
      4,
      delta,
    );

    const targetColor = AURA_MODE_COLORS[mode] || AURA_MODE_COLORS.observe;
    auraColor.lerp(targetColor, Math.min(1, delta * 2.5));
    // Approval hold: the atmosphere itself defers to YELLOW-zone amber.
    const holding = uniforms.uHold.value;
    if (holding > 0.01) {
      auraColor.lerp(AURA_HOLD_AMBER, Math.min(1, delta * 2.5) * holding);
    }

    if (sparkMaterialRef.current) {
      sparkMaterialRef.current.uniforms.uActivity.value = smoothedActivityRef.current;
    }
  });

  // Wrapper groups scale each shell about the measured brain CENTER (not the
  // offset GLB origin): position = center * (1 - s) compensates the shift.
  return (
    <group>
      {/* Shell 1 — membrane: region-tinted atmosphere just off the cortex */}
      <group
        position={[
          BRAIN_CENTER.x * (1 - MEMBRANE_SCALE),
          BRAIN_CENTER.y * (1 - MEMBRANE_SCALE),
          BRAIN_CENTER.z * (1 - MEMBRANE_SCALE),
        ]}
        scale={MEMBRANE_SCALE}
      >
        <primitive object={shells.membrane} />
      </group>

      {/* Shell 2 — nucleus: rose interior glow ghosting through the cortex.
          First shell dropped under a reduced tier budget (full-mesh overdraw). */}
      {shellBudget >= 2 && (
        <group
          position={[
            BRAIN_CENTER.x * (1 - CORE_SCALE),
            BRAIN_CENTER.y * (1 - CORE_SCALE),
            BRAIN_CENTER.z * (1 - CORE_SCALE),
          ]}
          scale={CORE_SCALE}
        >
          <primitive object={shells.core} />
        </group>
      )}

      {/* Synaptic sparks — tiny orbiting motes (the survivors of the old aura) */}
      <points geometry={sparkGeometry} frustumCulled={false}>
        <shaderMaterial
          ref={sparkMaterialRef}
          vertexShader={SPARK_VERTEX_SHADER}
          fragmentShader={SPARK_FRAGMENT_SHADER}
          uniforms={sparkUniforms}
          transparent
          depthWrite={false}
          blending={THREE.AdditiveBlending}
          toneMapped={false}
        />
      </points>
    </group>
  );
}
