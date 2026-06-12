import * as THREE from 'three';
import { useMemo, useRef, useEffect } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js';
import { createSeededRandom } from '@/lib/seededRandom';
import type { BurstRef, CognitionUniforms } from './SuperbrainScene';

const WIRE_VERTEX = `
  uniform float uTime;
  
  attribute vec3 aWireColor;
  attribute float aPhase;
  attribute float aSpeed;
  attribute float aPulse;

  varying vec2 vUv;
  varying vec3 vNormalV;
  varying vec3 vViewDirV;
  varying vec3 vColor;
  varying float vPhase;
  varying float vSpeed;
  varying float vPulse;

  void main() {
    vUv = uv;
    vColor = aWireColor;
    vPhase = aPhase;
    vSpeed = aSpeed;
    vPulse = aPulse;

    vNormalV = normalize(normalMatrix * normal);
    vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
    vViewDirV = -mvPosition.xyz;
    gl_Position = projectionMatrix * mvPosition;
  }
`;

const WIRE_FRAGMENT = `
  uniform float uTime;
  uniform float uBurst;
  uniform float uHold;

  varying vec2 vUv;
  varying vec3 vNormalV;
  varying vec3 vViewDirV;
  varying vec3 vColor;
  varying float vPhase;
  varying float vSpeed;
  varying float vPulse;

  void main() {
    vec3 N = normalize(vNormalV);
    vec3 V = normalize(vViewDirV);
    float dotNV = abs(dot(N, V)); 

    // Soft fresnel for the cylindrical wire look
    float fresnel = pow(1.0 - dotNV, 2.0);

    // Base color of the wire (keep it saturated, don't wash out with white)
    vec3 wireColor = vColor * (0.8 + fresnel * 0.5);

    // High-Speed Data Packet (pulse)
    float flow = fract(vUv.x * 4.0 - uTime * vSpeed + vPhase);
    float packet = smoothstep(0.85, 0.95, flow) * smoothstep(1.0, 0.95, flow);

    // Brain breath pulsing
    float breath = sin(uTime * 2.0 - vUv.x * 5.0 + vPhase) * 0.5 + 0.5;

    // Combine Visuals
    vec3 finalColor = wireColor;
    finalColor += vColor * packet * 1.5; // Soothing, colorful data pulse
    finalColor += vColor * breath * vPulse * 0.8; // Gentle breathing glow
    finalColor *= (1.0 + uBurst * 1.0);
    // Approval hold: the nervous system goes quiet while the mind defers.
    finalColor *= mix(1.0, 0.3, uHold);

    // Hard physical cut at the UI tabs (no fading to black!)
    if (vUv.x < 0.005 || vUv.x > 0.995) discard;

    // Fully opaque solid cable (no ghosting or fading)
    gl_FragColor = vec4(finalColor, 0.95);
  }
`;

/** Module-level uniform leaf (the bundle mounts once); frame-loop-mutable. */
const WIRE_BURST_UNIFORM = { value: 0 };

const COLORS = [
  new THREE.Color('#40e8ff'), // Cyan
  new THREE.Color('#e62bd4'), // Neon Pink/Magenta
  new THREE.Color('#9b3bff'), // Deep Violet
  new THREE.Color('#19d4f0'), // Bright Blue
  new THREE.Color('#ffffff'), // White
];

class SpiralWireCurve extends THREE.Curve<THREE.Vector3> {
  baseCurve: THREE.CatmullRomCurve3;
  angleOffset: number;
  radius: number;
  twists: number;
  frames: { tangents: THREE.Vector3[], normals: THREE.Vector3[], binormals: THREE.Vector3[] };

  constructor(baseCurve: THREE.CatmullRomCurve3, angleOffset: number, radius: number, twists: number) {
    super();
    this.baseCurve = baseCurve;
    this.angleOffset = angleOffset;
    this.radius = radius;
    this.twists = twists;
    this.frames = baseCurve.computeFrenetFrames(100, false);
  }

  getPoint(t: number, optionalTarget = new THREE.Vector3()) {
    const point = this.baseCurve.getPoint(t);
    
    // Interpolate frenet frames along the curve
    const frameIndex = t * 100;
    const i1 = Math.floor(frameIndex);
    const i2 = Math.min(i1 + 1, 100);
    const weight = frameIndex - i1;
    
    const normal = new THREE.Vector3().copy(this.frames.normals[i1]).lerp(this.frames.normals[i2], weight).normalize();
    const binormal = new THREE.Vector3().copy(this.frames.binormals[i1]).lerp(this.frames.binormals[i2], weight).normalize();
    
    // The spiral angle twists as it moves along the curve
    const currentAngle = this.angleOffset + t * Math.PI * 2 * this.twists;
    
    // Dynamic radius to create the "pile" effect
    let r = this.radius;
    if (t < 0.2) {
      // Wide deep inside the brain, pinching down through the stem
      r = THREE.MathUtils.lerp(this.radius * 3.0, this.radius * 0.6, t / 0.2);
    } else if (t < 0.5) {
      // Tight and bound together dropping down the spinal cord
      r = this.radius * 0.6;
    } else if (t < 0.8) {
      // Swelling and spreading out during the peripheral branch
      r = THREE.MathUtils.lerp(this.radius * 0.6, this.radius * 2.0, (t - 0.5) / 0.3);
    } else {
      // Pinching tightly into the UI port
      r = THREE.MathUtils.lerp(this.radius * 2.0, this.radius * 0.1, (t - 0.8) / 0.2);
    }

    optionalTarget.copy(point)
      .add(normal.multiplyScalar(Math.cos(currentAngle) * r))
      .add(binormal.multiplyScalar(Math.sin(currentAngle) * r));

    return optionalTarget;
  }
}

export default function NervousSystem({
  burst,
  uniforms,
}: {
  burst: BurstRef;
  uniforms: CognitionUniforms;
}) {
  const groupRef = useRef<THREE.Group>(null);
  const { viewport, size } = useThree();

  useFrame((state) => {
    if (!groupRef.current) return;
    const time = state.clock.elapsedTime;
    
    // Perfect synchronization with the brain's physical sway
    groupRef.current.position.x = Math.sin(time * 0.16) * 0.24 + Math.cos(time * 0.09) * 0.1;
    groupRef.current.position.y = 0.12 + Math.cos(time * 0.2) * 0.14 + Math.sin(time * 0.14) * 0.07;
    groupRef.current.position.z = -1.2; 
  });

  // We hardcode tabX based on the target Z distance (7.5) to prevent the geometry from rebuilding 
  // 60 times a second while the camera drifts, which would tank the framerate.
  // At Z=7.5 with 45deg FOV on a 16:9 screen, the width is ~12.4. tabX targets ~82% of the half-width.
  const tabX = 4.82; 

  const material = useMemo(() => {
    return new THREE.ShaderMaterial({
      vertexShader: WIRE_VERTEX,
      fragmentShader: WIRE_FRAGMENT,
      uniforms: {
        uTime: uniforms.uTime,
        uBurst: WIRE_BURST_UNIFORM,
        uHold: uniforms.uHold,
      },
      transparent: true,
      blending: THREE.NormalBlending, // Normal blending prevents colors from stacking up into blinding white
      depthWrite: true, // We want the wires to properly occlude each other in the pile
    });
  }, [uniforms]);

  // Update burst uniform dynamically
  useFrame(() => {
    WIRE_BURST_UNIFORM.value = burst.current.intensity;
  });

  // Generate the Massive Biological Wire Bundle
  const mergedGeometry = useMemo(() => {
    const geometries: THREE.BufferGeometry[] = [];
    // House rule: never unseeded randomness — keeps the braid identical
    // across mounts and keeps the screenshot baselines honest.
    const random = createSeededRandom(0x57495245);
    
    // UI panels are now locked into the 3D scene graph using <Html transform>
    const leftTargetX = -4.8;
    const rightTargetX = 4.8;

    const addWireBundle = (
      numWires: number, 
      controlPoints: THREE.Vector3[],
      baseSpread: number,
      colors: THREE.Color[]
    ) => {
      // The core path of this bundle
      const mainPath = new THREE.CatmullRomCurve3(controlPoints);

      for (let i = 0; i < numWires; i++) {
        // Base angle for this wire in the spiral
        const angleOffset = (i / numWires) * Math.PI * 2 * 3.0; // Distribute them cleanly around the circle
        
        // Use square root distribution for perfectly even, dense packing (no messy randomness)
        // Avoid 0 radius so they don't clip exactly in the center
        const layerRadius = baseSpread * (0.2 + 0.8 * Math.sqrt(i / numWires));
        
        // Exact same twist rate for all wires creates a clean, parallel braided cable
        const twists = 4.0;

        const curve = new SpiralWireCurve(mainPath, angleOffset, layerRadius, twists);
        
        // Clean uniform thickness for a polished look
        const thickness = 0.006 + (i % 3) * 0.002;
        
        const geom = new THREE.TubeGeometry(curve, 100, thickness, 6, false);
        
        // Generate custom attributes for the shader
        const vertCount = geom.attributes.position.count;
        const colorArray = new Float32Array(vertCount * 3);
        const phaseArray = new Float32Array(vertCount);
        const speedArray = new Float32Array(vertCount);
        const pulseArray = new Float32Array(vertCount);
        
        // Pick colors sequentially to create a perfect rainbow spiral
        const wireColor = colors[i % colors.length];
        const phase = random() * Math.PI * 2;
        const speed = 0.5 + random() * 1.5;
        const pulse = random() > 0.5 ? 1.0 : 0.0; // Only some wires breathe
        
        for (let v = 0; v < vertCount; v++) {
          colorArray[v * 3 + 0] = wireColor.r;
          colorArray[v * 3 + 1] = wireColor.g;
          colorArray[v * 3 + 2] = wireColor.b;
          phaseArray[v] = phase;
          speedArray[v] = speed;
          pulseArray[v] = pulse;
        }
        
        geom.setAttribute('aWireColor', new THREE.BufferAttribute(colorArray, 3));
        geom.setAttribute('aPhase', new THREE.BufferAttribute(phaseArray, 1));
        geom.setAttribute('aSpeed', new THREE.BufferAttribute(speedArray, 1));
        geom.setAttribute('aPulse', new THREE.BufferAttribute(pulseArray, 1));
        
        geometries.push(geom);
      }
    };

    // Brain-matched color palette (All colors of the brain mixed together)
    const allColors = [
      new THREE.Color('#ff3b28'), // Frontal Red-Orange
      new THREE.Color('#ff7a26'), // Burnt Orange
      new THREE.Color('#19d4f0'), // Electric Cyan
      new THREE.Color('#a8e62b'), // Lime Green
      new THREE.Color('#9b3bff'), // Occipital Violet
      new THREE.Color('#36f07a'), // Temporal Green
      new THREE.Color('#e62bd4'), // Magenta
      new THREE.Color('#6a35ff'), // Cerebellum Deep Violet
      new THREE.Color('#ffffff'), // Core White
    ];

    // Shared Spinal Cord points for all bundles
    const deepCore = new THREE.Vector3(0.0, 0.5, -0.4);
    const stemExit = new THREE.Vector3(0.0, -0.5, -0.5);
    const spinalDrop = new THREE.Vector3(0.0, -1.2, -0.4);

    // 1. Left Peripheral Branch (Clean, vertical insertion without loops)
    addWireBundle(
      45,
      [
        deepCore,
        stemExit,
        spinalDrop,
        new THREE.Vector3(leftTargetX + 2.0, -2.2, -0.2),  // Gentle swoop outwards
        new THREE.Vector3(leftTargetX, -2.4, -0.05), // Directly below port, completes horizontal movement
        new THREE.Vector3(leftTargetX, -1.7, 0.0)    // Port entry (terminates at the bottom edge)
      ],
      0.07, // Tight base spread
      allColors
    );

    // 2. Right Peripheral Branch (Clean, vertical insertion without loops)
    addWireBundle(
      45,
      [
        deepCore,
        stemExit,
        spinalDrop,
        new THREE.Vector3(rightTargetX - 2.0, -2.2, -0.2),   // Gentle swoop outwards
        new THREE.Vector3(rightTargetX, -2.4, -0.05),  // Directly below port, completes horizontal movement
        new THREE.Vector3(rightTargetX, -1.5, 0.0)    // Port entry (terminates at the bottom edge)
      ],
      0.07, // Tight base spread
      allColors
    );

    // 3. Lower Spinal Cord continuation (Plugging into Command Bar)
    addWireBundle(
      35,
      [
        deepCore,
        stemExit,
        spinalDrop,
        new THREE.Vector3(0.0, -2.0, 0.2), // Continue straight down
        new THREE.Vector3(0.0, -2.6, 1.5) // Plug into TOP of chat box
      ],
      0.07, // Tight base spread
      allColors
    );

    // Merge all 115 TubeGeometries into ONE massive BufferGeometry (1 draw call)
    const finalGeom = mergeGeometries(geometries);
    
    // Clean up individual geometries to save memory
    geometries.forEach(g => g.dispose());
    
    return finalGeom;
  }, [tabX]);

  useEffect(() => {
    return () => {
      if (mergedGeometry) mergedGeometry.dispose();
    };
  }, [mergedGeometry]);

  return (
    <group ref={groupRef}>
      <mesh geometry={mergedGeometry} material={material} frustumCulled={false} />
    </group>
  );
}
