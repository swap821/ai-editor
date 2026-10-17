import { act } from 'react';
import { _roots, advance, createRoot, extend, useFrame, type RootState } from '@react-three/fiber';
import * as THREE from 'three';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { BrainModel, SCENE_UNIFORMS } from '../../superbrain/components/canvas/SuperbrainScene.LEGACY';
import BodyIntakeAnchors from '../../superbrain/components/canvas/BodyIntakeAnchors';
import CommandNerve3D from '../../superbrain/components/canvas/CommandNerve3D';
import { __resetSpineFusionForTests } from '../../superbrain/lib/spineFusionBus';
import { __resetFunnelAnchorForTests, getFunnelAnchor } from '../../superbrain/lib/funnelAnchorBus';
import { __resetTabStoreForTests, getTabStoreSnapshot, openWorkspacePanel, setMaterializedTabLifecycle, showContentSurface } from '../../superbrain/lib/tabStore';
import type { PhysicalBodyProjection } from '../../superbrain/lib/bodyPosture';
import { ATTENTION_BRIGHTEN } from '../../superbrain/lib/cursorAttention';
import { __resetConversationPhaseForTests, getConversationPhase, setConversationPhase } from '../../superbrain/lib/conversationPhaseBus';
import { deriveBeingPresentation, type BeingFacts } from './semanticKernel';
import { derivePhysicalSnapshot } from './physicalSnapshot';
import { publishCognition } from '../../superbrain/lib/cognitionBus';

vi.mock('../../superbrain/lib/brainScene', async () => {
  const { Group, Mesh, BoxGeometry, MeshBasicMaterial } = await import('three');
  const scene = new Group();
  scene.add(new Mesh(new BoxGeometry(), new MeshBasicMaterial({ color: '#7bf5fb' })));
  return { preloadBrainScene() {}, useBrainScene: () => scene };
});
// Keep the real model, full low-tier field, material, attention eligibility,
// transforms, anchors and nerve. Only asset shape, non-owning decorations and
// WebGL are substituted; this is not protected-GLB/GPU/device acceptance.
vi.mock('../../superbrain/components/canvas/MemoryHalo', () => ({ default: () => null }));
vi.mock('../../superbrain/components/canvas/MaterializationLayer', () => ({ default: () => null }));
extend({ Points: THREE.Points, Group: THREE.Group, Mesh: THREE.Mesh,
  BufferGeometry: THREE.BufferGeometry, SphereGeometry: THREE.SphereGeometry,
  TorusGeometry: THREE.TorusGeometry, MeshBasicMaterial: THREE.MeshBasicMaterial,
  MeshStandardMaterial: THREE.MeshStandardMaterial });
beforeEach(() => {
  __resetSpineFusionForTests(); __resetFunnelAnchorForTests(); __resetTabStoreForTests(); __resetConversationPhaseForTests();
  localStorage.removeItem('gagos-pause-motion-v1');
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
  // The actual inner lattice runs; only its external graph transport is absent.
  vi.stubGlobal('fetch', async () => new Response('{}', { status: 404 }));
  SCENE_UNIFORMS.uArrival.value = 0; SCENE_UNIFORMS.uAwaken.value = 0;
  SCENE_UNIFORMS.uTime.value = 0; SCENE_UNIFORMS.uHold.value = 0;
  const send = document.createElement('button'); send.className = 'gagos-send'; document.body.append(send);
  vi.spyOn(send, 'getBoundingClientRect').mockReturnValue(new DOMRect(420, 640, 44, 44));
});
afterEach(() => {
  document.querySelector('.gagos-send')?.remove();
  __resetSpineFusionForTests(); __resetFunnelAnchorForTests(); __resetTabStoreForTests(); __resetConversationPhaseForTests();
  vi.restoreAllMocks(); vi.unstubAllGlobals();
});

// Omitting the existing eligible-input relay must leave the real shader fully
// withdrawn and its attached socket hidden while the human types. The cortex
// must acknowledge input independently of backend work, on the next frame.
// Assertions inspect actual renderer objects, not another gate implementation.
it.each([false, true])('welcomes eligible input without losing retained work; reduced=%s', async reduced => {
  vi.stubGlobal('matchMedia', () => Object.assign(new EventTarget(), { matches: reduced }));
  const canvas = document.createElement('canvas'), root = createRoot(canvas), store = _roots.get(canvas)!.store;
  const camera = new THREE.PerspectiveCamera(26, 1, 0.1, 100);
  camera.position.set(0, 0, 15); camera.updateMatrixWorld();
  let body!: THREE.Points, tube!: THREE.Mesh, socket!: THREE.Group, nodes!: THREE.InstancedMesh;
  let paints = 0;
  const gl = { domElement: canvas, getPixelRatio: () => 1, setSize() {}, setPixelRatio() {},
    render(scene: THREE.Scene) {
      paints++; scene.updateMatrixWorld(true);
      scene.traverse(object => {
        if (object instanceof THREE.Points) body = object;
        if (object instanceof THREE.InstancedMesh) nodes = object;
        if (!(object instanceof THREE.Mesh)) return;
        if (object.geometry instanceof THREE.TubeGeometry) tube = object;
        if (object.geometry instanceof THREE.SphereGeometry && object.geometry.parameters.radius === 0.034) socket = object.parent as THREE.Group;
      });
    },
  } as unknown as RootState['gl'];
  await root.configure({ gl, scene: new THREE.Scene(), camera, frameloop: 'never',
    size: { width: 720, height: 720, left: 0, top: 0 } });
  const physical: PhysicalBodyProjection = { phase: 'resting', taskState: 'done-unverified', coherence: 'fresh', motion: 'calm',
    cortex: { posture: 'unverified' }, verification: { state: 'unverified' }, membrane: { state: 'clear' } };
  const burst = { current: { intensity: 0, lastBurst: 0 } }, arrival = { current: 0 }, workPane = { current: true };
  function ComposerOwner() { useFrame(({ gl: renderer, scene, camera: view }) => renderer.render(scene, view), 1); return null; }
  const render = async (input: boolean, projection: PhysicalBodyProjection | null = physical) => {
    await act(async () => { root.render(<>
      <BrainModel activity={0} mode="observe" burst={burst} arrival={arrival} tier="low" uniforms={SCENE_UNIFORMS}
        physical={projection ?? undefined} workPaneRef={workPane} inputAttentionActive={input} />
      <BodyIntakeAnchors physical={projection ?? undefined} reducedMotion={reduced} />
      <CommandNerve3D reducedMotion={reduced} /><ComposerOwner />
    </>); });
  };
  const step = (time: number) => act(() => advance(time, false, store.getState()));
  try {
    // Inspection alone is already separate from materialized tabs. Preserve
    // that behavior instead of treating the initial hypothesis as a defect.
    act(() => openWorkspacePanel('history', 'Recent activity'));
    await render(false); step(100);
    const material = body.material as THREE.ShaderMaterial, geometry = body.geometry;
    expect(material.uniforms.uSprayHide.value).toBe(0);
    expect(geometry.getAttribute('position').count).toBe(51000);
    expect(nodes.count).toBe(20);
    const nodeGeometry = nodes.geometry, nodeMatrices = Array.from(nodes.instanceMatrix.array);
    const nodeColors = Array.from(nodes.instanceColor!.array);
    const activation = nodeGeometry.getAttribute('aActivation');
    const innerWires = store.getState().scene.children.flatMap(function collect(object): THREE.Mesh[] {
      return [...(object instanceof THREE.Mesh && (object.material as THREE.ShaderMaterial).uniforms?.uReducedMotion ? [object] : []),
        ...object.children.flatMap(collect)];
    });
    expect(innerWires).toHaveLength(2);
    let first!: ReturnType<typeof showContentSurface>, second!: ReturnType<typeof showContentSurface>;
    act(() => {
      first = showContentSurface({ filepath: 'fixture://retained-a', language: 'python', code: 'print("A")', streaming: false });
      second = showContentSurface({ filepath: 'fixture://retained-b', language: 'python', code: 'print("B")', streaming: false });
      setMaterializedTabLifecycle(first.id, 'live'); setMaterializedTabLifecycle(second.id, 'live');
    });
    step(110);
    expect(material.uniforms.uSprayHide.value).toBeGreaterThan(0.999);
    expect(material.uniforms.uAwaken.value).toBe(0);
    expect(socket.visible).toBe(false);
    await render(true); step(110 + 1 / 60);
    expect.soft(material.uniforms.uSprayHide.value, 'eligible input starts unfolding its actual cauda').toBeLessThan(0.999);
    expect.soft(material.uniforms.uAwaken.value, 'eligible input warms the actual cortex on the next frame').toBeGreaterThan(0);
    expect.soft(material.uniforms.uAwaken.value, 'local input is bounded human attention, not a work-onset catch').toBeLessThanOrEqual(ATTENTION_BRIGHTEN);
    step(120);
    expect.soft(material.uniforms.uSprayHide.value).toBeLessThan(0.001);
    expect.soft(material.uniforms.uAwaken.value).toBeCloseTo(ATTENTION_BRIGHTEN, 3);
    expect.soft(material.uniforms.uWakeWave.value).toBe(1);
    expect.soft(material.uniforms.uReplyRise.value).toBe(0);
    expect.soft(material.uniforms.uStatePulse.value).toBe(0);
    expect.soft(socket.visible && tube.visible).toBe(true);
    // Input engagement changes anatomy, not the measured outcome or pulse flow.
    expect(getFunnelAnchor().flow).toBe(0);
    expect(physical.taskState).toBe('done-unverified');
    await render(false); step(130);
    expect(material.uniforms.uSprayHide.value).toBeGreaterThan(0.999);
    expect(material.uniforms.uAwaken.value).toBeLessThan(0.001);
    expect(socket.visible).toBe(false);
    // A lingering legacy reply cannot overrule an admitted human boundary.
    // The real field must follow the projection even before this bus clears.
    act(() => setConversationPhase('streaming'));
    for (const projection of [
      { ...physical, phase: 'awaiting-human', taskState: 'needs-permission', membrane: { state: 'held' } },
      { ...physical, phase: 'stopped', taskState: 'stopped', cortex: { posture: 'stopped' } },
    ]) {
      await render(true, projection); step(140 + paints);
      expect(material.uniforms.uSprayHide.value).toBeGreaterThan(0.999);
      expect.soft(material.uniforms.uAwaken.value, 'a lingering reply cannot reheat a held/stopped cortex').toBeLessThan(0.001);
      expect.soft(material.uniforms.uWakeWave.value, 'a lingering reply cannot start a notice wave at the human boundary').toBe(1);
      expect.soft(material.uniforms.uReplyRise.value, 'a measured hold/Stop outranks the lingering reply signal').toBeLessThan(0.001);
      expect(socket.visible).toBe(false);
    }
    act(() => setConversationPhase('idle'));
    await render(true); step(170 + paints);
    // Attachments consume the field's previous frame while its existing
    // envelope unfolds. Match the initial two-frame intake witness above.
    step(180 + paints);
    expect(material.uniforms.uAwaken.value).toBeCloseTo(ATTENTION_BRIGHTEN, 3);
    expect(material.uniforms.uReplyRise.value).toBeLessThan(0.001);
    expect(material.uniforms.uSprayHide.value).toBeLessThan(0.001);
    const recoveredAnchor = getFunnelAnchor();
    expect(recoveredAnchor.presence).toBe(1);
    // This Box-asset fixture has a fixed camera, not the product's fit owner:
    // its fully settled normal-motion conus lands just outside the viewport.
    // Recovery restores intake presence but must retain real offscreen culling.
    expect(socket.visible).toBe(recoveredAnchor.visible);
    expect(tube.visible).toBe(recoveredAnchor.visible);
    // Use the actual semantic -> physical producer, not hand-shaped "quiet"
    // props. A raw reply must not contradict its admitted posture; genuine
    // replies remain expressive. Fixed literals are the independent oracle.
    const replyFacts: BeingFacts = { transport: 'connected', projection: 'fresh', mirrorStatus: 'online',
      hasSnapshot: true, taskActivity: 'streaming', verification: 'unknown', stop: 'clear' };
    const healthyReply = derivePhysicalSnapshot(deriveBeingPresentation(replyFacts));
    expect([healthyReply.phase, healthyReply.taskState]).toEqual(['acting', 'working']);
    act(() => setConversationPhase('streaming'));
    await render(false, healthyReply); step(210); step(220);
    act(() => publishCognition({ type: 'agent-dispatch', detail: 'tool engaged: read_file' }));
    step(220 + 1 / 60);
    // Literal low-tier ARCHIVE hub plus its three satellites. This reaches the
    // real lattice THROUGH BrainModel, so omitting the prop relay also fails.
    expect(Array.from(activation.array).map((value, index) => value > 0 ? index : -1).filter(index => index >= 0)).toEqual([1, 8, 9, 10]);
    expect(innerWires.every(wire => (wire.material as THREE.ShaderMaterial).uniforms.uReducedMotion.value === (reduced ? 1 : 0))).toBe(true);
    expect(material.uniforms.uAwaken.value).toBeGreaterThan(0.89);
    if (reduced) expect(material.uniforms.uReplyRise.value).toBe(0);
    else expect(material.uniforms.uReplyRise.value).toBeGreaterThan(0.999);
    expect(material.uniforms.uBodyOpacity.value).toBeGreaterThan(0.999);
    const quietCases: { patch: Partial<BeingFacts>; phase: string; taskState: string; heat: number; inputHeat?: number }[] = [
      { patch: { stop: 'engaged' }, phase: 'stopped', taskState: 'stopped', heat: 0, inputHeat: 0 },
      { patch: { approvalPending: true }, phase: 'awaiting-human', taskState: 'needs-permission', heat: 0, inputHeat: 0 },
      { patch: { projection: 'stale', mirrorStatus: 'stale' }, phase: 'stale', taskState: 'stale', heat: 0 },
      { patch: { transport: 'disconnected', projection: 'unavailable', mirrorStatus: 'offline', hasSnapshot: false },
        phase: 'degraded', taskState: 'working', heat: 0 },
      { patch: { taskActivity: 'awaiting-replay' }, phase: 'awaiting-response', taskState: 'waiting-response', heat: 0 },
      { patch: { taskActivity: 'refused' }, phase: 'recovering', taskState: 'refused', heat: 0 },
      { patch: { taskActivity: 'complete' }, phase: 'resting', taskState: 'done-unverified', heat: 0 },
      { patch: { taskActivity: 'complete', verification: 'pass' }, phase: 'resting', taskState: 'done-verified', heat: 0 },
      { patch: { taskActivity: 'checking', verification: 'pending' }, phase: 'verifying', taskState: 'checking', heat: 1 },
    ];
    let time = 220 + 1 / 60;
    for (const entry of quietCases) {
      await render(false, healthyReply);
      act(() => publishCognition({ type: 'agent-dispatch', detail: 'tool engaged: read_file' }));
      step(time + 1 / 60);
      expect(activation.getX(1)).toBeGreaterThan(0);
      const projection = derivePhysicalSnapshot(deriveBeingPresentation({ ...replyFacts, ...entry.patch }));
      expect([projection.phase, projection.taskState]).toEqual([entry.phase, entry.taskState]);
      const previousHeat = material.uniforms.uAwaken.value;
      const previousRise = material.uniforms.uReplyRise.value;
      await render(false, projection); step(time + 2 / 60);
      if (!reduced && entry.heat === 0 && previousHeat > 0.001) {
        expect.soft(material.uniforms.uAwaken.value, `${entry.phase}: quieting begins on the first frame`).toBeLessThan(previousHeat);
      }
      expect.soft(material.uniforms.uReplyRise.value, `${entry.phase}: the first frame cannot amplify an obsolete reply`).toBeLessThanOrEqual(previousRise);
      if (!reduced && previousRise > 0.001) expect.soft(material.uniforms.uReplyRise.value).toBeLessThan(previousRise);
      expect.soft(Array.from(activation.array).every(value => value === 0), `${entry.phase}: inner light retires with the outer body`).toBe(true);
      act(() => publishCognition({ type: 'agent-dispatch', detail: 'tool engaged: read_file' }));
      step(time + 3 / 60);
      expect.soft(Array.from(activation.array).every(value => value === 0), `${entry.phase}: obsolete tool cannot fire the inner cortex`).toBe(true);
      expect.soft(innerWires.every(wire => (wire.material as THREE.ShaderMaterial).uniforms.uReducedMotion.value === 1), `${entry.phase}: quiet state has no travelling compute packets`).toBe(true);
      step(time + 10);
      expect.soft(material.uniforms.uAwaken.value, `${entry.phase}: heat follows admitted state, not the lingering bus`).toBeCloseTo(entry.heat, 3);
      expect.soft(material.uniforms.uReplyRise.value, `${entry.phase}: a raw reply cannot assert current speech`).toBeLessThan(0.001);
      await render(true, projection); step(time + 20);
      expect.soft(material.uniforms.uAwaken.value, `${entry.phase}: local input retains its bounded acknowledgment unless held/stopped`).toBeCloseTo(entry.inputHeat ?? Math.max(entry.heat, 0.32), 3);
      expect.soft(material.uniforms.uReplyRise.value).toBeLessThan(0.001);
      expect(getConversationPhase()).toBe('streaming'); // renderer did not erase transport evidence
      time += 20;
    }
    await render(false, healthyReply); step(time + 1 / 60); step(time + 10);
    act(() => publishCognition({ type: 'agent-dispatch', detail: 'tool engaged: create_file' }));
    step(time + 10 + 1 / 60);
    expect(Array.from(activation.array).map((value, index) => value > 0 ? index : -1).filter(index => index >= 0)).toEqual([2, 11, 12, 13]);
    expect(innerWires.every(wire => (wire.material as THREE.ShaderMaterial).uniforms.uReducedMotion.value === (reduced ? 1 : 0))).toBe(true);
    expect(material.uniforms.uAwaken.value).toBeGreaterThan(0.89);
    if (reduced) expect(material.uniforms.uReplyRise.value).toBe(0);
    else expect(material.uniforms.uReplyRise.value).toBeGreaterThan(0.999);
    // The standalone lab still has no product projection and uses its existing
    // conversation fallback. This is not an excuse to blank genuine replies.
    await render(false, null); step(time + 20); step(time + 30);
    act(() => publishCognition({ type: 'route' })); step(time + 30 + 1 / 60);
    expect(activation.getX(4), 'standalone router signal remains admitted').toBeGreaterThan(0);
    expect(nodes.geometry).toBe(nodeGeometry);
    expect(Array.from(nodes.instanceMatrix.array)).toEqual(nodeMatrices);
    expect(Array.from(nodes.instanceColor!.array)).toEqual(nodeColors);
    expect(material.uniforms.uAwaken.value).toBeGreaterThan(0.89);
    if (reduced) expect(material.uniforms.uReplyRise.value).toBe(0);
    else expect(material.uniforms.uReplyRise.value).toBeGreaterThan(0.999);
    expect(body.geometry).toBe(geometry);
    expect(store.getState().internal.priority).toBe(1);
    expect(getTabStoreSnapshot().tabs.map(tab => [tab.id, tab.content?.code, tab.lifecycle])).toEqual([
      [first.id, 'print("A")', 'live'], [second.id, 'print("B")', 'live'],
    ]);
  } finally { await act(async () => { root.unmount(); }); }
});
