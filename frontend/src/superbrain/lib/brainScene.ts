// brainScene.ts — load the being's GLB WITHOUT drei's useGLTF.
//
// Why this exists: the strict CSP (script-src 'self') breaks drei/three-stdlib's
// MeshoptDecoder (WASM + a blob worker), and routing the load through drei's
// useGLTF / R3F useLoader (suspend-react) leaves the Suspense boundary stuck
// FOREVER — so the entire being scene never mounts and the canvas is black. A
// plain GLTFLoader().load() of the (uncompressed) GLB works perfectly. This wraps
// that direct load in a module-cached promise + a manual-Suspense hook, so the
// existing `<Suspense>` contract holds and every caller shares one parse.
import * as THREE from 'three';
import { GLTFLoader } from 'three-stdlib';

const BRAIN_GLB = '/models/brain.glb';

let cachedScene: THREE.Group | null = null;
let pending: Promise<void> | null = null;

function brainLoader(): GLTFLoader {
  const loader = new GLTFLoader();
  // The product GLB is stripped and every mesh receives a runtime shader, so the
  // legacy spec/gloss material extension is intentionally ignored after parse.
  loader.register(() => ({
    name: 'KHR_materials_pbrSpecularGlossiness',
    beforeRoot: () => Promise.resolve(),
  }));
  return loader;
}

function startLoad(): Promise<void> {
  if (!pending) {
    pending = new Promise<void>((resolve, reject) => {
      brainLoader().load(
        BRAIN_GLB,
        (gltf) => {
          cachedScene = gltf.scene;
          resolve();
        },
        undefined,
        (err) => reject(err),
      );
    });
  }
  return pending;
}

/** Kick the load early (mirrors useGLTF.preload) so the parse overlaps boot. */
export function preloadBrainScene(): void {
  void startLoad();
}

/**
 * Returns the loaded brain GLB scene. Suspends (throws the load promise) until
 * it resolves — standard React Suspense, no drei/useLoader. The same object is
 * returned to every caller; clone it (`scene.clone(true)`) before mutating, as
 * the previous useGLTF callers already do.
 */
export function useBrainScene(): THREE.Group {
  if (cachedScene) return cachedScene;
  throw startLoad();
}
