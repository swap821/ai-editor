import { act } from 'react';
import { _roots, advance, createRoot, extend, type RootState } from '@react-three/fiber';
import * as THREE from 'three';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import BrainPointField from '../../superbrain/components/canvas/BrainPointField';
import { SCENE_UNIFORMS } from '../../superbrain/components/canvas/SuperbrainScene.LEGACY';
import { deriveBodyPosture } from '../../superbrain/lib/bodyPosture';
import { __resetConversationPhaseForTests } from '../../superbrain/lib/conversationPhaseBus';
import { setOrganismPhase } from '../../superbrain/lib/organismPhaseBus';
import { __resetSpineFusionForTests } from '../../superbrain/lib/spineFusionBus';
import { __resetTabStoreForTests } from '../../superbrain/lib/tabStore';
import { deriveBeingPresentation, type BeingFacts } from './semanticKernel';
import { derivePhysicalSnapshot, type PhysicalSnapshot } from './physicalSnapshot';

vi.mock('../../superbrain/lib/brainScene', () => ({ preloadBrainScene() {} }));
extend({ Points: THREE.Points });
beforeEach(() => {
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
  localStorage.removeItem('gagos-pause-motion-v1');
  __resetConversationPhaseForTests(); __resetSpineFusionForTests(); __resetTabStoreForTests();
  setOrganismPhase('rest');
});
afterEach(() => {
  __resetConversationPhaseForTests(); __resetSpineFusionForTests(); __resetTabStoreForTests();
  setOrganismPhase('rest'); vi.restoreAllMocks(); vi.unstubAllGlobals();
});

const physical = (overrides: Partial<BeingFacts> = {}) => derivePhysicalSnapshot(deriveBeingPresentation({
  lifecycle: 'reabsorbing', transport: 'connected', projection: 'fresh', mirrorStatus: 'online',
  hasSnapshot: true, taskActivity: 'idle', verification: 'unknown', stop: 'clear', ...overrides,
}));

async function mount(reduced: boolean) {
  vi.stubGlobal('matchMedia', () => Object.assign(new EventTarget(), { matches: reduced }));
  const canvas = document.createElement('canvas'), root = createRoot(canvas), store = _roots.get(canvas)!.store;
  const source = new THREE.Mesh(new THREE.BoxGeometry(), new THREE.MeshBasicMaterial({ color: '#7bf5fb' }));
  const gl = { domElement: canvas, getPixelRatio: () => 1, setSize() {}, setPixelRatio() {}, render() {} } as unknown as RootState['gl'];
  await root.configure({ gl, camera: new THREE.PerspectiveCamera(), scene: new THREE.Scene(),
    frameloop: 'never', size: { width: 720, height: 720, left: 0, top: 0 } });
  const uniforms = { ...SCENE_UNIFORMS, uTime: { value: 0 }, uArrival: { value: 0 }, uIgnite: { value: 0 } };
  const render = async (projection?: PhysicalSnapshot) => act(async () => {
    root.render(<BrainPointField source={source} uniforms={uniforms} physical={projection} count={96} spineCount={32} />);
  });
  const step = (time: number) => act(() => advance(time, false, store.getState()));
  await render(physical({ lifecycle: 'rest' }));
  let field!: THREE.Points;
  store.getState().scene.traverse(object => { if (object instanceof THREE.Points) field = object; });
  return { render, step, field, scene: store.getState().scene, async close() {
    await act(async () => { root.unmount(); });
    source.geometry.dispose(); (source.material as THREE.Material).dispose();
  } };
}

// Removing return eligibility from the actual point-field subscriber must lose
// these shader uniforms even when canonical return metadata is still correct.
// Real sampler, material, semantic producer and R3F clock; only WebGL replaced.
it.each([false, true])('returns older energy without certifying current work; reduced=%s', async reduced => {
  const view = await mount(reduced), material = view.field.material as THREE.ShaderMaterial;
  const geometry = view.field.geometry;
  let time = 10;
  try {
    for (const [facts, key] of [
      [{}, 'rest'], [{ taskActivity: 'streaming' }, 'stream'],
      [{ hasPlan: true }, 'think'], [{ taskActivity: 'complete', verification: 'pass' }, 'complete'],
    ] as const) {
      await view.render(physical({ lifecycle: 'rest' })); view.step(time);
      const projection = physical(facts);
      expect(projection.motion).toBe('reabsorb');
      expect(deriveBodyPosture({ phase: 'reabsorbing', physical: projection }).key).toBe(key);
      await view.render(projection); view.step(time += 0.01);
      expect(material.uniforms.uReabsorbRise.value).toBe(0);
      view.step(time += 0.4);
      if (reduced) {
        expect(material.uniforms.uReabsorbRise.value).toBe(0);
        expect(material.uniforms.uReabsorbGlow.value).toBeGreaterThan(0.5);
      } else {
        expect(material.uniforms.uReabsorbRise.value).toBeGreaterThan(0.9);
        expect(material.uniforms.uReabsorbRise.value).toBeLessThan(1);
        expect(material.uniforms.uReabsorbGlow.value).toBeGreaterThan(0.5);
        // The original one-shot completes after a brief return beat ends.
        await view.render({ ...projection, motion: 'calm' });
        view.step(time += 0.315);
        expect(material.uniforms.uReabsorbGlow.value).toBeGreaterThan(0.99);
        view.step(time += 1);
        expect(material.uniforms.uReabsorbGlow.value).toBe(0);
        expect(material.uniforms.uReabsorbRise.value).toBe(1);
      }
      expect(view.scene.getObjectById(view.field.id)).toBe(view.field);
      expect(view.field.material).toBe(material); expect(view.field.geometry).toBe(geometry);
      time += 3;
    }
    // The unbound lab still uses its original lifecycle bus, not a new owner.
    await view.render(); setOrganismPhase('rest'); view.step(time);
    setOrganismPhase('reabsorbing'); view.step(time += 0.01); view.step(time += 0.4);
    expect(material.uniforms.uReabsorbGlow.value).toBeGreaterThan(0.5);
    if (reduced) expect(material.uniforms.uReabsorbRise.value).toBe(0);
    else {
      expect(material.uniforms.uReabsorbRise.value).toBeGreaterThan(0.9);
      expect(material.uniforms.uReabsorbRise.value).toBeLessThan(1);
    }
  } finally { await view.close(); }
});

it.each([false, true])('does not let old return motion override current boundaries; reduced=%s', async reduced => {
  const view = await mount(reduced), material = view.field.material as THREE.ShaderMaterial;
  let time = 10;
  try {
    setOrganismPhase('reabsorbing'); // stale standalone signal cannot override product truth
    for (const [facts, key] of [
      [{ approvalPending: true }, 'hold'], [{ stop: 'engaged' }, 'stopped'],
      [{ taskActivity: 'failed', verification: 'fail' }, 'error'],
      [{ projection: 'stale', mirrorStatus: 'stale' }, 'unconfirmed'],
      [{ taskActivity: 'awaiting-replay' }, 'unconfirmed'],
      [{ taskActivity: 'complete' }, 'unverified'],
    ] as const) {
      const projection = physical(facts);
      expect(deriveBodyPosture({ phase: 'reabsorbing', physical: projection }).key).toBe(key);
      await view.render(projection); view.step(time); view.step(time += 0.4);
      expect(material.uniforms.uReabsorbGlow.value).toBe(0);
      expect(material.uniforms.uReabsorbRise.value).toBe(reduced ? 0 : 1);
      time += 3;
    }
    await view.render(physical()); view.step(time); view.step(time += 0.4);
    expect(material.uniforms.uReabsorbGlow.value).toBeGreaterThan(0.5);
    await view.render(physical({ stop: 'engaged' })); view.step(time += 0.4);
    if (reduced) expect(material.uniforms.uReabsorbGlow.value).toBeLessThan(0.5);
    else expect(material.uniforms.uReabsorbGlow.value).toBe(0);
    view.step(time += 3);
    expect(material.uniforms.uReabsorbGlow.value).toBeLessThan(0.001);
  } finally { await view.close(); }
});
