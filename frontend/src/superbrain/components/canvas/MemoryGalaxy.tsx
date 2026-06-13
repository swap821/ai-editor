'use client';

/**
 * MemoryGalaxy — the brain's life, written in stars.
 *
 * Every REAL pheromone trail is a persistent star orbiting the mind:
 *   brightness = trail strength      size  = proven walks
 *   red pulse  = quarantined         flash = a reinforcement / recall NOW
 *
 * Placement is deterministic from skill_id, so a skill keeps ITS place in
 * the sky across sessions — over weeks the operator literally watches his
 * AI's skill-space grow. Honest dormancy: no trails, no stars; nothing here
 * is invented (the only inputs are the adapter's live trail field and the
 * bus events real polls publish).
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import * as THREE from 'three';
import { useFrame } from '@react-three/fiber';
import { subscribeCognition } from '@/lib/cognitionBus';
import { getKnownTrails, type TrailRow } from '@/lib/aiosAdapter';

const MAX_STARS = 128;
const TAU = Math.PI * 2;

/** Deterministic 0..1 from a skill id and salt — a star never moves house. */
function hash01(id: number, salt: number): number {
  const s = Math.sin(id * 127.1 + salt * 311.7) * 43758.5453;
  return s - Math.floor(s);
}

const GALAXY_VERTEX = /* glsl */ `
  attribute float aRadius;
  attribute float aAngle;
  attribute float aSpeed;
  attribute float aHeight;
  attribute float aWobble;
  attribute float aSize;
  attribute float aStrength;
  attribute float aQuarantine;
  attribute float aFlash;
  uniform float uTime;
  varying float vStrength;
  varying float vQuarantine;
  varying float vFlash;
  varying float vSeed;

  void main() {
    float angle = aAngle + uTime * aSpeed;
    vec3 pos = vec3(
      cos(angle) * aRadius,
      aHeight + sin(angle * 0.7 + aAngle * 3.0) * aWobble,
      sin(angle) * aRadius - 2.0
    );
    vec4 mv = modelViewMatrix * vec4(pos, 1.0);
    float flash = exp(-max(uTime - aFlash, 0.0) * 1.6);
    gl_PointSize = aSize * (1.0 + flash * 2.2) * (170.0 / -mv.z);
    vStrength = aStrength;
    vQuarantine = aQuarantine;
    vFlash = flash;
    vSeed = aAngle;
    gl_Position = projectionMatrix * mv;
  }
`;

const GALAXY_FRAGMENT = /* glsl */ `
  precision highp float;
  uniform float uTime;
  varying float vStrength;
  varying float vQuarantine;
  varying float vFlash;
  varying float vSeed;

  void main() {
    vec2 c = gl_PointCoord - 0.5;
    float d = length(c);
    float core = smoothstep(0.5, 0.0, d);
    core *= core;
    // Crisp nucleus so the newest (weak) skill-stars read as solid objects, not haze.
    core += 0.5 * smoothstep(0.08, 0.0, d);
    float twinkle = 0.85 + 0.15 * sin(uTime * 0.55 + vSeed * 37.0);
    // Healthy memory is icy starlight; quarantine stains it pulsing red.
    float stain = vQuarantine * (0.6 + 0.4 * sin(uTime * 4.4 + vSeed * 11.0));
    // sRGB->linear of the authored cyan/red (the pipeline is linear; raw sRGB
    // values washed the skill-stars into the sky's blue-white).
    vec3 color = mix(vec3(0.3424, 0.7484, 1.0), vec3(1.0, 0.0732, 0.0470), stain);
    float alpha = core * (0.34 + 0.66 * vStrength) * twinkle + vFlash * core;
    gl_FragColor = vec4(color * (0.8 + vFlash * 1.6), alpha);
  }
`;

export default function MemoryGalaxy() {
  const [starCount, setStarCount] = useState(() => getKnownTrails().length);
  const timeRef = useRef(0);

  const star = useMemo(() => {
    const geometry = new THREE.BufferGeometry();
    const make = (size = 1) => new THREE.BufferAttribute(new Float32Array(MAX_STARS * size), size);
    // gl_Position ignores `position`, but three requires it for draw count.
    geometry.setAttribute('position', make(3));
    for (const name of [
      'aRadius', 'aAngle', 'aSpeed', 'aHeight', 'aWobble',
      'aSize', 'aStrength', 'aQuarantine', 'aFlash',
    ]) {
      geometry.setAttribute(name, make(1));
    }
    // aFlash drives flash = exp(-max(uTime - aFlash, 0) * 1.6): a 0-init reads as
    // flash≈1, so every star ignites at mount. Seed it negative so the galaxy
    // stays calm until a real bus event sets aFlash = uTime.
    (geometry.getAttribute('aFlash').array as Float32Array).fill(-10);
    geometry.setDrawRange(0, 0);
    // Orbits span radius ~7.5-13: never culled while the camera breathes.
    geometry.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, 0.5, -2), 24);
    const material = new THREE.ShaderMaterial({
      vertexShader: GALAXY_VERTEX,
      fragmentShader: GALAXY_FRAGMENT,
      uniforms: { uTime: { value: 0 } },
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
    return { geometry, material, slotById: new Map<number, number>() };
  }, []);

  useEffect(() => {
    return () => {
      star.geometry.dispose();
      star.material.dispose();
    };
  }, [star]);

  useEffect(() => {
    const attr = (name: string) => star.geometry.getAttribute(name) as THREE.BufferAttribute;

    const sync = () => {
      const trails = [...getKnownTrails()].sort((a, b) => a.skill_id - b.skill_id).slice(0, MAX_STARS);
      star.slotById.clear();
      trails.forEach((trail: TrailRow, slot: number) => {
        star.slotById.set(trail.skill_id, slot);
        const id = trail.skill_id;
        attr('aRadius').setX(slot, 7.5 + hash01(id, 1) * 5.5);
        attr('aAngle').setX(slot, hash01(id, 2) * TAU);
        // Direction alternates by id parity; period is minutes, not seconds.
        attr('aSpeed').setX(slot, (0.008 + hash01(id, 3) * 0.014) * (id % 2 === 0 ? 1 : -1));
        attr('aHeight').setX(slot, -1.4 + hash01(id, 4) * 4.6);
        attr('aWobble').setX(slot, 0.2 + hash01(id, 5) * 0.5);
        const walks = trail.success_count + trail.reuse_success_count;
        attr('aSize').setX(slot, 2.4 + Math.min(walks, 12) * 0.55);
        attr('aStrength').setX(slot, THREE.MathUtils.clamp(trail.strength, 0, 1));
        attr('aQuarantine').setX(slot, trail.quarantined ? 1 : 0);
      });
      for (const name of [
        'aRadius', 'aAngle', 'aSpeed', 'aHeight', 'aWobble', 'aSize', 'aStrength', 'aQuarantine',
      ]) {
        attr(name).needsUpdate = true;
      }
      star.geometry.setDrawRange(0, trails.length);
      setStarCount(trails.length);
      if (process.env.NODE_ENV !== 'production') {
        (window as unknown as Record<string, unknown>).__gagGalaxyCount = trails.length;
      }
    };

    sync();
    const unsubscribe = subscribeCognition((event) => {
      if (event.type === 'telemetry') {
        sync();
        return;
      }
      // A reinforcement or a recall touching "trail #N" flashes ITS star.
      if (event.type !== 'knowledge-acquired' && event.type !== 'burst') return;
      const match = /trail #(\d+)/.exec(event.detail ?? '');
      if (!match) return;
      const slot = star.slotById.get(Number(match[1]));
      if (slot === undefined) return;
      const flash = attr('aFlash');
      flash.setX(slot, timeRef.current);
      flash.needsUpdate = true;
    });
    return unsubscribe;
  }, [star]);

  useFrame((state) => {
    timeRef.current = state.clock.elapsedTime;
    star.material.uniforms.uTime.value = state.clock.elapsedTime;
  });

  if (starCount === 0) return null; // dormant until real memory exists
  return <points geometry={star.geometry} material={star.material} renderOrder={1} />;
}
