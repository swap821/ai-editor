import { act } from 'react';
import { _roots, advance, createRoot, extend, type RootState } from '@react-three/fiber';
import * as THREE from 'three';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import NodeLattice from '../../superbrain/components/canvas/NodeLattice';
import { SCENE_UNIFORMS } from '../../superbrain/components/canvas/SuperbrainScene.LEGACY';
import { publishCognition } from '../../superbrain/lib/cognitionBus';
import * as adapter from '../../superbrain/lib/aiosAdapter';
import type { QualityTier } from '../../superbrain/components/QualityTierProvider';

vi.mock('../../superbrain/lib/brainScene', () => ({ preloadBrainScene() {} }));
extend({ Group: THREE.Group });
beforeEach(() => {
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
  // External transport alone is unavailable. Real topology, instanced
  // transforms, materials, event subscription and frame scheduling run.
  vi.stubGlobal('fetch', async () => new Response('{}', { status: 404 }));
});
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

async function withLattice(tier: QualityTier, run: (nodes: THREE.InstancedMesh,
  scene: THREE.Scene, frame: () => void) => void | Promise<void>) {
  const canvas = document.createElement('canvas');
  const root = createRoot(canvas); const store = _roots.get(canvas)!.store;
  const gl = { domElement: canvas, render() {}, setSize() {}, setPixelRatio() {} } as unknown as RootState['gl'];
  await root.configure({ gl, scene: new THREE.Scene(), frameloop: 'never',
    size: { width: 398, height: 150.6, left: 0, top: 0 } });
  const uniforms = { ...SCENE_UNIFORMS, uTime: { value: 0 }, uBurst: { value: 0 },
    uHold: { value: 0 }, uArrival: { value: 0 } };
  try {
    await act(async () => { root.render(<NodeLattice uniforms={uniforms} tier={tier} reducedMotion />); });
    let nodes!: THREE.InstancedMesh;
    const scene = store.getState().scene;
    scene.traverse(object => { if (object instanceof THREE.InstancedMesh) nodes = object; });
    let time = 0;
    const frame = () => { act(() => advance(++time / 60, false, store.getState())); };
    await run(nodes, scene, frame);
  } finally { await act(async () => { root.unmount(); }); }
}

it.each([
  ['high', 125, 24], ['medium', 85, 16], ['low', 20, 3],
] as const)('keeps the %s node layer finer than cortex-region structure without deleting topology', async (tier, count, satellites) => {
  await withLattice(tier, (nodes, scene) => {
    expect(nodes.count).toBe(count);
    let draws = 0; scene.traverse(object => { if (object instanceof THREE.Mesh) draws++; });
    expect(draws).toBe(3); // same instanced nodes + merged local wires + backbone
    const matrix = new THREE.Matrix4(), position = new THREE.Vector3(), scale = new THREE.Vector3();
    const rotation = new THREE.Quaternion();
    const area = [0, 0, 0, 0, 0];
    for (let i = 0; i < count; i++) {
      nodes.getMatrixAt(i, matrix); matrix.decompose(position, rotation, scale);
      expect(scale.x).toBeGreaterThan(0); // remains visible, not a hidden layer
      expect(scale.y).toBeCloseTo(scale.x); expect(scale.z).toBeCloseTo(scale.x);
      const hub = i < 5 ? i : Math.floor((i - 5) / satellites);
      area[hub] += scale.x * scale.x;
    }
    // Independent optical budget: summed node-disc area is <=20% of each
    // 0.11-radius region's scatter disc (pi cancels), even before occlusion.
    // This proves actual transform allocation, NOT GPU bloom/pixel coverage.
    for (const filledArea of area) expect.soft(filledArea / (0.11 * 0.11)).toBeLessThanOrEqual(0.2);
  });
});

it('bounds a dense admitted trail region without removing its160 nodes or changing strength relationships', async () => {
  vi.spyOn(adapter, 'getKnownTrails').mockReturnValue(Array.from({ length: 160 }, (_, index) => ({
    skill_id: index + 1, goal_pattern: 'shared recalled skill', status: 'verified', quarantined: false,
    success_count: 12, reuse_success_count: 6, failure_count: 0, reuse_failure_count: 0,
    strength: index % 2 ? 1 : 0.5, freshness: 1,
  })));
  await withLattice('high', nodes => {
    expect(nodes.count).toBe(160);
    const matrix = new THREE.Matrix4(), scale = new THREE.Vector3();
    let totalArea = 0;
    const radii: number[] = [];
    for (let i = 0; i < nodes.count; i++) {
      nodes.getMatrixAt(i, matrix); scale.setFromMatrixScale(matrix);
      expect(scale.x).toBeGreaterThan(0);
      radii.push(scale.x); totalArea += scale.x * scale.x;
    }
    expect(totalArea / (0.11 * 0.11)).toBeLessThanOrEqual(0.200001); // Float32 transform precision
    // Stronger trails still have1.4/1.0 relative radius after the region's
    // shared presentation scale; actual strength-derived topology is intact.
    expect(Math.max(...radii) / Math.min(...radii)).toBeCloseTo(1.4, 5);
  });
});

it('retains real regional firing and stable node transforms under reduced motion', async () => {
  await withLattice('high', (nodes, _scene, frame) => {
    const matrices = Array.from(nodes.instanceMatrix.array);
    const colors = Array.from(nodes.instanceColor!.array);
    const geometry = nodes.geometry;
    const activation = geometry.getAttribute('aActivation');
    expect(Array.from(activation.array).every(value => value === 0)).toBe(true);
    publishCognition({ type: 'agent-dispatch', detail: 'tool engaged: create_file', source: 'fixture-test' });
    frame();
    const firing = Array.from(activation.array).map((value, index) => value > 0 ? index : -1).filter(index => index >= 0);
    // Literal topology: LATTICE is hub2, followed by its24 satellites at53..76.
    expect(firing).toEqual([2, ...Array.from({ length: 24 }, (_, index) => 53 + index)]);
    for (let tick = 0; tick < 100; tick++) frame();
    expect(Array.from(activation.array).every(value => value === 0)).toBe(true);
    expect(nodes.geometry).toBe(geometry);
    expect(Array.from(nodes.instanceMatrix.array)).toEqual(matrices);
    expect(Array.from(nodes.instanceColor!.array)).toEqual(colors);
    expect((nodes.material as THREE.ShaderMaterial).uniforms.uNodeGain.value).toBeGreaterThan(0);
  });
});
