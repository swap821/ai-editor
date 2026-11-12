import { cleanup, render } from '@testing-library/react';
import * as THREE from 'three';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import OrganSurface from './OrganSurface';

const mocks = vi.hoisted(() => ({
  useTexture: vi.fn(),
  useBrainScene: vi.fn(),
}));

vi.mock('@react-three/drei', () => ({ useTexture: mocks.useTexture }));
vi.mock('@/lib/brainScene', () => ({ useBrainScene: mocks.useBrainScene }));

describe('OrganSurface', () => {
  let scene: THREE.Group;
  let meshA: THREE.Mesh;
  let meshB: THREE.Mesh;
  let originalMaterial: THREE.MeshBasicMaterial;
  let maps: { map: THREE.Texture; normalMap: THREE.Texture };

  beforeEach(() => {
    // R3F intrinsic elements are unknown tags under react-dom; silence the warnings.
    vi.spyOn(console, 'error').mockImplementation(() => {});

    originalMaterial = new THREE.MeshBasicMaterial();
    meshA = new THREE.Mesh(new THREE.BufferGeometry(), originalMaterial);
    meshB = new THREE.Mesh(new THREE.BufferGeometry(), originalMaterial);
    const nested = new THREE.Group();
    nested.add(meshB);
    scene = new THREE.Group();
    scene.add(meshA, nested, new THREE.Object3D());

    maps = { map: new THREE.Texture(), normalMap: new THREE.Texture() };
    mocks.useTexture.mockReset();
    mocks.useBrainScene.mockReset();
    mocks.useTexture.mockReturnValue(maps);
    mocks.useBrainScene.mockReturnValue(scene);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('requests a diffuse map and a normal map and configures them for GLB UVs', () => {
    expect(maps.map.flipY).toBe(true);
    expect(maps.normalMap.flipY).toBe(true);

    render(<OrganSurface />);

    expect(Object.keys(mocks.useTexture.mock.calls[0][0] as object)).toEqual(['map', 'normalMap']);
    expect(maps.map.colorSpace).toBe(THREE.SRGBColorSpace);
    expect(maps.map.flipY).toBe(false);
    expect(maps.normalMap.flipY).toBe(false);
    expect(maps.map.version).toBeGreaterThan(0);
    expect(maps.normalMap.version).toBeGreaterThan(0);
  });

  it('paints every cloned mesh with the flesh material and leaves the source scene alone', () => {
    const cloneSpy = vi.spyOn(scene, 'clone');

    render(<OrganSurface />);

    expect(cloneSpy).toHaveBeenCalledWith(true);
    const clone = cloneSpy.mock.results[0]?.value as THREE.Group;
    expect(clone).not.toBe(scene);

    const materials: THREE.Material[] = [];
    clone.traverse((object) => {
      if (object instanceof THREE.Mesh) materials.push(object.material as THREE.Material);
    });
    expect(materials).toHaveLength(2);
    expect(materials[0]).toBe(materials[1]);

    const material = materials[0] as THREE.MeshPhysicalMaterial;
    expect(material).toBeInstanceOf(THREE.MeshPhysicalMaterial);
    expect(material.map).toBe(maps.map);
    expect(material.normalMap).toBe(maps.normalMap);
    expect(material.roughness).toBe(0.42);
    expect(material.metalness).toBe(0);
    expect(material.clearcoat).toBe(0.28);
    expect(material.clearcoatRoughness).toBe(0.5);

    expect(meshA.material).toBe(originalMaterial);
    expect(meshB.material).toBe(originalMaterial);
  });

  it('renders the warm key and cool rim lights', () => {
    const { container } = render(<OrganSurface />);

    expect(container.querySelectorAll('[color="#ffe2d0"]')).toHaveLength(1);
    expect(container.querySelectorAll('[color="#8fb7ff"]')).toHaveLength(1);
  });

  it('builds the material once across re-renders and disposes it on unmount', () => {
    const disposeSpy = vi.spyOn(THREE.MeshPhysicalMaterial.prototype, 'dispose');
    const cloneSpy = vi.spyOn(scene, 'clone');

    const { rerender, unmount } = render(<OrganSurface />);
    rerender(<OrganSurface />);

    expect(cloneSpy).toHaveBeenCalledTimes(1);
    expect(disposeSpy).not.toHaveBeenCalled();

    unmount();

    expect(disposeSpy).toHaveBeenCalledTimes(1);
    expect(disposeSpy.mock.contexts[0]).toBeInstanceOf(THREE.MeshPhysicalMaterial);
  });
});
