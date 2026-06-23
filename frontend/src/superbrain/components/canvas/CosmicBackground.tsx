import * as THREE from 'three';
import { useEffect, useMemo, useRef, type MutableRefObject } from 'react';
import { createSeededRandom } from '@/lib/seededRandom';
import { subscribeCognition } from '@/lib/cognitionBus';
import type { QualityTier } from '@/components/QualityTierProvider';
import { useFrame } from '@react-three/fiber';

// --- KNOWLEDGE GLYPH ATLAS GENERATOR ---
const GLYPHS = [
  // Math & Greek
  '∑', '∆', '∞', '∫', 'π', 'Ω', 'α', 'β', 'µ', 'λ', 'θ', 'σ',
  // Code & Logic
  '{', '}', '<', '>', '/', '\\', '&', '#', '@', '%', '!', '?',
  // Numerals
  '0', '1', '2', '3', '4', '5', '6', '7', '8', '9',
  // Alphabets
  'A', 'B', 'C', 'D', 'E', 'F', 'X', 'Y', 'Z',
  // Punctuation / Cyber
  '+', '-', '=', '*', '^', '~', '|', ':', ';', '.', ',', '"'
];

const ATLAS_SIZE = 64;
const atlasChars: string[] = [];
for (let i = 0; i < ATLAS_SIZE; i++) {
  atlasChars.push(GLYPHS[i % GLYPHS.length]);
}

let glyphAtlasTexture: THREE.CanvasTexture | null = null;
function getGlyphAtlas() {
  if (!glyphAtlasTexture && typeof document !== 'undefined') {
    const canvas = document.createElement('canvas');
    canvas.width = 512;
    canvas.height = 512;
    const ctx = canvas.getContext('2d')!;
    
    ctx.clearRect(0, 0, 512, 512);
    
    // Sleek, high-tech digital font for the matrix decoding effect
    ctx.font = 'bold 50px "Space Mono", "Roboto Mono", "Courier New", monospace';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillStyle = 'white';
    
    // Strong, sharp glow for premium feel
    ctx.shadowColor = 'rgba(255, 255, 255, 0.8)';
    ctx.shadowBlur = 8;
    
    for (let i = 0; i < 64; i++) {
      const col = i % 8;
      const row = Math.floor(i / 8);
      const char = atlasChars[i];
      const x = col * 64 + 32;
      const y = row * 64 + 32; 
      ctx.fillText(char, x, y + 2);
    }
    
    glyphAtlasTexture = new THREE.CanvasTexture(canvas);
    glyphAtlasTexture.minFilter = THREE.LinearMipmapLinearFilter;
    glyphAtlasTexture.magFilter = THREE.LinearFilter;
  }
  return glyphAtlasTexture;
}

/** Module-level uniform leaf (the field mounts once); frame-loop-mutable. */
const STARFIELD_TIME_UNIFORM = { value: 0 };

/** Star budget per quality tier — the field is pure backdrop, so it thins first. */
const STAR_COUNTS: Record<QualityTier, number> = {
  high: 3000,
  medium: 1800,
  low: 900,
};

function Starfield({
  count,
  arrival,
  reducedMotion = false,
}: {
  count: number;
  arrival?: MutableRefObject<number>;
  reducedMotion?: boolean;
}) {
  const pointsRef = useRef<THREE.Points>(null);

  const stars = useMemo(() => {
    const positions = new Float32Array(count * 3);
    const colors = new Float32Array(count * 3);
    const sprites = new Float32Array(count);
    const sizes = new Float32Array(count);
    // House rule: never unseeded randomness — identical field every mount,
    // honest screenshot baselines. Same counts, ranges, and distribution.
    const random = createSeededRandom(0x564f5941);

    for (let i = 0; i < count; i++) {
      positions[i * 3 + 0] = (random() - 0.5) * 140;
      positions[i * 3 + 1] = (random() - 0.5) * 140;
      positions[i * 3 + 2] = (random() - 0.5) * 140 - 35;

      // Calmer field (polish #7): base glyph brightness pulled down ~30% (was
      // 0.6-1.0) so the cosmic point-field reads as a quiet backdrop, not a
      // competing layer. Near-organism density is preserved; the far field is
      // dimmed further by the depth-fog falloff in the vertex shader below.
      const shade = random() * 0.34 + 0.38; // 0.38-0.72 grey
      colors[i * 3 + 0] = shade;
      colors[i * 3 + 1] = shade;
      colors[i * 3 + 2] = shade;

      sprites[i] = Math.floor(random() * 64);
      sizes[i] = random() * 2.0 + 0.5;
    }
    
    const geom = new THREE.BufferGeometry();
    geom.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geom.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    geom.setAttribute('aSpriteIndex', new THREE.BufferAttribute(sprites, 1));
    geom.setAttribute('aSize', new THREE.BufferAttribute(sizes, 1));
    return geom;
  }, [count]);

  const uniforms = useMemo(() => ({
    uTime: STARFIELD_TIME_UNIFORM,
    uAtlas: { value: getGlyphAtlas() },
    // Coalescence funnel strength: 1 = arriving (stars funnel hard inward),
    // 0 = settled (canon drift-by). Default 0 keeps the canon REST field.
    uArrival: { value: 0 },
  }), []);

  // Approval hold: the VOYAGE ITSELF holds its breath — the field's clock
  // dilates to ~30% while the supervised mind defers to its operator, and
  // eases back the moment a decision lands. Accumulated time (not absolute
  // clock) is what makes the dilation seamless.
  const holdRef = useRef({ target: 0, blend: 0 });
  useEffect(
    () =>
      subscribeCognition((event) => {
        if (event.type === 'approval-required') holdRef.current.target = 1;
        else if (
          event.type === 'approval-resolved' ||
          event.type === 'directive' ||
          event.type === 'synthesis'
        ) {
          holdRef.current.target = 0;
        }
      }),
    [],
  );

  useFrame((_, delta) => {
    const hold = holdRef.current;
    hold.blend = THREE.MathUtils.damp(hold.blend, hold.target, 2.5, delta);
    // A11y (motion audit, true defect): the stars stream TOWARD the camera, an
    // expanding optical flow that is a classic vestibular / migraine trigger — and
    // it was never gated. Under OS reduced-motion, drop the stream to a near-frozen
    // parallax drift (~4%): the cosmic field stays present, but nothing looms.
    STARFIELD_TIME_UNIFORM.value += delta * (1 - 0.7 * hold.blend) * (reducedMotion ? 0.04 : 1);
    uniforms.uArrival.value = arrival?.current ?? 0;
  });

  return (
    <points ref={pointsRef} geometry={stars}>
      <pointsMaterial 
        vertexColors 
        transparent 
        depthWrite={false}
        sizeAttenuation={false}
        blending={THREE.AdditiveBlending}
        onBeforeCompile={(shader) => {
          shader.uniforms.uTime = uniforms.uTime;
          shader.uniforms.uAtlas = uniforms.uAtlas;
          shader.uniforms.uArrival = uniforms.uArrival;

          shader.vertexShader = shader.vertexShader.replace(
            '#include <common>',
            `#include <common>
             uniform float uTime;
             uniform float uArrival;
             attribute float aSpriteIndex;
             attribute float aSize;
             varying float vAlpha;
             varying float vSpriteIndex;
             varying float vPull;
            `
          );
          
          shader.vertexShader = shader.vertexShader.replace(
            '#include <begin_vertex>',
            `#include <begin_vertex>
             vSpriteIndex = aSpriteIndex;
             
             // Move straight towards camera like classic stars
             float speed = 1.0 + (aSize * 0.2);
             transformed.z += uTime * speed;
             
             // Infinite wrapping
             float range = 140.0;
             transformed.z = mod(transformed.z + 105.0, range) - 105.0;
             
             // --- INSTANT GRAVITATIONAL PULL ---
             // Calculate distance to the brain core (0,0,0)
             float distToCenter = length(transformed); 
             
             // The "grasp" range is 25 units.
             // As the particle enters this radius, pull goes from 0.0 to 1.0.
             // Coalescence widens the grasp radius and snaps stars in HARDER so
             // the field reads as funneling inward; uArrival==0 reproduces the
             // exact canon 25->2 grasp (purely additive, no canon change).
             float graspRange = mix(25.0, 42.0, uArrival);
             float pull = clamp(smoothstep(graspRange, 2.0, distToCenter) * (1.0 + uArrival * 0.6), 0.0, 1.0);

             if (pull > 0.0) {
                 // Instant, straight-line gravitational pull directly to the core
                 // pow() gives it a sharp, accelerating snap rather than a linear slide
                 float snap = pow(pull, 1.5);
                 transformed = mix(transformed, vec3(0.0), snap);
             }
             
             vPull = pull;
             
             // Smooth fade out as they fly past the camera lens (if they weren't grasped)
             float cameraDistance = abs(transformed.z - 4.5);
             vAlpha = smoothstep(0.0, 10.0, cameraDistance);

             // Depth-fog falloff (polish #7): the FAR field recedes — glyphs deep
             // behind the organism dim to ~40%, so the noisy scattered backdrop
             // stops competing with the surfaces while the near field stays bright.
             vAlpha *= 1.0 - smoothstep(34.0, 96.0, cameraDistance) * 0.6;
            `
          );
          
          shader.vertexShader = shader.vertexShader.replace(
            'gl_PointSize = size;',
            `// "Coming close becoming big"
             // Allow distanceScale to magnify the particle up to 2.5x when very close to camera
             float distanceScale = clamp(20.0 / length(mvPosition.xyz), 0.2, 1.5);
             
             // Larger so near glyphs READ as symbols (the knowledge-field), not dots
             float finalSize = aSize * 22.0 * distanceScale;

             // As it gets grasped by the brain, it physically shrinks (dissolves)
             finalSize *= (1.0 - (vPull * 0.8));

             // Cap so near glyphs are legible symbols, not giant rectangles
             gl_PointSize = clamp(finalSize, 2.0, 34.0);`
          );

          shader.fragmentShader = shader.fragmentShader.replace(
            '#include <common>',
            `#include <common>
             uniform sampler2D uAtlas;
             uniform float uTime;
             varying float vAlpha;
             varying float vSpriteIndex;
             varying float vPull;
            `
          );

          shader.fragmentShader = shader.fragmentShader.replace(
            '#include <color_fragment>',
            `#include <color_fragment>
             float cols = 8.0;
             float rows = 8.0;
             
             // No rotation, no decoding. Just the solid static alphabet.
             float col = mod(vSpriteIndex, cols);
             float row = floor(vSpriteIndex / cols);
             
             vec2 uv = gl_PointCoord;
             
             // Canvas textures have flipY=true by default.
             // gl_PointCoord.y=0 is top, so we add row and divide to get proper orientation.
             uv.x = (uv.x + col) / cols;
             uv.y = (uv.y + row) / rows;
             
             vec4 texColor = texture2D(uAtlas, uv);
             float alpha = texColor.a;
             alpha *= smoothstep(0.5, 0.42, length(gl_PointCoord - 0.5));
             if (alpha < 0.02) discard;
             
             // Pure white/grey
             vec3 finalColor = diffuseColor.rgb;
             
             // "Dissolves it inside" -> Rapidly fade opacity to 0 as it gets pulled into the brain
             float dissolve = 1.0 - smoothstep(0.4, 1.0, vPull);
             
             diffuseColor = vec4(finalColor, alpha * vAlpha * dissolve);
            `
          );
        }}
      />
    </points>
  );
}

export default function CosmicBackground({
  tier = 'high',
  arrival,
  reducedMotion = false,
}: {
  tier?: QualityTier;
  /** Shared coalescence scalar: 1 = arriving (funnel inward), 0 = settled. */
  arrival?: MutableRefObject<number>;
  /** OS reduced-motion: freezes the looming star-stream (vestibular safety). */
  reducedMotion?: boolean;
}) {
  return (
    <group>
      <Starfield count={STAR_COUNTS[tier]} arrival={arrival} reducedMotion={reducedMotion} />
    </group>
  );
}
