'use client';

/**
 * OrganSurface — the operator's hand-painted flesh cortex.
 *
 * BRAIN_SURFACE 'organ' replaces the dark emission shell with the textures he
 * painted into the GLB (diffuse flesh + sculpted normal map, locked behind the
 * spec-gloss extension where the loader never surfaced them). The living
 * neural web, aura shells, signals and thought-waves keep breathing ON TOP —
 * his organ under his energy skin, per reference-supermind.
 *
 * The textures load from product-copy PNGs (public/textures/brain/), never
 * from the GLB — so the product GLB keeps shipping stripped and his source
 * file stays untouched (VISION.md).
 *
 * Lights here exist ONLY in organ mode: the scene's ambient rig is tuned for
 * an additive shell and would render flesh near-black.
 */

import { useEffect, useMemo } from 'react';
import * as THREE from 'three';
import { useTexture } from '@react-three/drei';
import { useBrainScene } from '@/lib/brainScene';

export default function OrganSurface() {
  const scene = useBrainScene(); // manual loader (brainScene.ts) — drei useGLTF hangs under CSP
  const maps = useTexture({
    map: '/textures/brain/diffuse.png',
    normalMap: '/textures/brain/normal.png',
  });

  const organ = useMemo(() => {
    maps.map.colorSpace = THREE.SRGBColorSpace;
    maps.map.flipY = false; // GLB UV convention
    maps.normalMap.flipY = false;
    maps.map.needsUpdate = true;
    maps.normalMap.needsUpdate = true;
    const material = new THREE.MeshPhysicalMaterial({
      map: maps.map,
      normalMap: maps.normalMap,
      roughness: 0.42,
      metalness: 0,
      clearcoat: 0.28,
      clearcoatRoughness: 0.5,
    });
    const clone = scene.clone(true);
    clone.traverse((object) => {
      if (object instanceof THREE.Mesh) object.material = material;
    });
    return { clone, material };
  }, [scene, maps]);

  useEffect(() => {
    return () => {
      organ.material.dispose();
    };
  }, [organ]);

  return (
    <group>
      <primitive object={organ.clone} />
      {/* Organ-only lighting: warm key for the flesh, cool counter-rim so the
          dark side keeps the scene's deep-space identity. */}
      <directionalLight position={[3.5, 5, 6]} intensity={1.7} color="#ffe2d0" />
      <directionalLight position={[-5, 1.5, -4]} intensity={0.55} color="#8fb7ff" />
    </group>
  );
}
