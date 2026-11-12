import { describe, expect, it, vi } from 'vitest';
import * as THREE from 'three';
import { preloadBrainScene, useBrainScene } from './brainScene';

const h = vi.hoisted(() => ({
  load: vi.fn(),
  register: vi.fn(),
}));

vi.mock('three-stdlib', () => ({
  GLTFLoader: class {
    load = h.load;
    register = h.register;
  },
}));

type LoadArgs = [
  string,
  (gltf: { scene: THREE.Group }) => void,
  unknown,
  (err: unknown) => void,
];

function catchThrown(fn: () => unknown): unknown {
  try {
    fn();
  } catch (e) {
    return e;
  }
  return undefined;
}

describe('brainScene', () => {
  it('shares one load, suspends until it resolves, then returns the cached scene', async () => {
    preloadBrainScene();
    expect(h.load).toHaveBeenCalledTimes(1);

    const firstThrown = catchThrown(() => useBrainScene());
    const secondThrown = catchThrown(() => useBrainScene());
    preloadBrainScene();

    expect(firstThrown).toBeInstanceOf(Promise);
    expect(secondThrown).toBe(firstThrown);
    expect(h.load).toHaveBeenCalledTimes(1);

    const [url, onLoad, onProgress, onError] = h.load.mock.calls[0] as LoadArgs;
    expect(typeof url).toBe('string');
    expect(onProgress).toBeUndefined();
    expect(typeof onError).toBe('function');

    const factory = h.register.mock.calls[0][0] as () => {
      beforeRoot: () => Promise<void>;
    };
    await expect(factory().beforeRoot()).resolves.toBeUndefined();

    const scene = new THREE.Group();
    onLoad({ scene });
    await firstThrown;

    expect(useBrainScene()).toBe(scene);
    expect(useBrainScene()).toBe(scene);

    preloadBrainScene();
    expect(h.load).toHaveBeenCalledTimes(1);
  });
});
