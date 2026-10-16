import { act, useRef } from 'react';
import { _roots, advance, createRoot, extend, useFrame, type RootState } from '@react-three/fiber';
import * as THREE from 'three';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import BrainPointField from '../../superbrain/components/canvas/BrainPointField';
import { SCENE_UNIFORMS } from '../../superbrain/components/canvas/SuperbrainScene.LEGACY';
import { __resetSpineFusionForTests, getSpineFusion, setBrainDockScale } from '../../superbrain/lib/spineFusionBus';
import { useBodyWorldFrame } from '../../superbrain/lib/useBodyWorldFrame';
import { __resetTabStoreForTests, showContentSurface, beginRetractingMaterializedTab } from '../../superbrain/lib/tabStore';
import SuperbrainReactiveEffects from '../../workbench/SuperbrainReactiveEffects';
import { __resetAuroraBridgeForTests } from '../../workbench/verifyAuroraBridge';
import { __resetSpineFlashBridgeForTests } from '../../workbench/spineFlashBridge';
import type { BeingPresentation } from './semanticKernel';
import { derivePhysicalSnapshot } from './physicalSnapshot';

vi.mock('../../superbrain/lib/brainScene', () => ({ preloadBrainScene() {} }));
extend({ Group: THREE.Group, Points: THREE.Points, Mesh: THREE.Mesh, BufferGeometry: THREE.BufferGeometry,
  SphereGeometry: THREE.SphereGeometry, TorusGeometry: THREE.TorusGeometry,
  MeshBasicMaterial: THREE.MeshBasicMaterial });
beforeEach(() => {
  __resetSpineFusionForTests(); __resetTabStoreForTests();
  __resetAuroraBridgeForTests(); __resetSpineFlashBridgeForTests();
  localStorage.removeItem('gagos-pause-motion-v1');
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
});
afterEach(() => {
  __resetSpineFusionForTests(); __resetTabStoreForTests();
  __resetAuroraBridgeForTests(); __resetSpineFlashBridgeForTests();
  vi.restoreAllMocks(); vi.unstubAllGlobals();
});

function testId(object: THREE.Object3D): string | undefined {
  return (object as THREE.Object3D & { __r3f?: { props: Record<string, unknown> } }).__r3f?.props['data-testid'] as string | undefined;
}

// Removing the actual field->effect attachment must displace these real cue
// meshes and the typing-current endpoint. Real sampler/material/LineGeometry,
// scene effects, stores and R3F callbacks run; only WebGL is substituted. The
// analytic head is not the protected GLB, shader raster or a physical device.
it.each([
  { reduced: false, seat: null }, { reduced: true, seat: null },
  { reduced: false, seat: 0 }, { reduced: true, seat: 0 },
  { reduced: false, seat: 11 }, { reduced: true, seat: 11 },
])(
  'keeps fixed-size cortex cues and attention on live anatomy; reduced=$reduced seat=$seat', async ({ reduced, seat }) => {
    vi.stubGlobal('matchMedia', () => Object.assign(new EventTarget(), { matches: reduced }));
    const canvas = document.createElement('canvas'), root = createRoot(canvas), store = _roots.get(canvas)!.store;
    const camera = new THREE.PerspectiveCamera(26, 1, 0.1, 100);
    camera.position.set(0, 0, 15); camera.updateMatrixWorld();
    const source = new THREE.Mesh(new THREE.BoxGeometry(), new THREE.MeshBasicMaterial({ color: '#7bf5fb' }));
    const uniforms = { ...SCENE_UNIFORMS, uTime: { value: 0 }, uArrival: { value: 0 }, uIgnite: { value: 0 } };
    const being: BeingPresentation = { phase: 'resting', taskState: 'done-unverified', coherence: 'fresh', motion: 'calm',
      attention: 'none', signals: ['memory-recalled'], workers: [] };
    const physical = derivePhysicalSnapshot(being);
    let bodyRoot!: THREE.Group, dock!: THREE.Group, field!: THREE.Points, cue!: THREE.Mesh, memory!: THREE.Mesh, verification!: THREE.Mesh;
    let inputLine!: THREE.Object3D & { geometry: THREE.BufferGeometry }, pulse!: THREE.Mesh;
    let currents: (THREE.Object3D & { geometry: THREE.BufferGeometry })[] = [];
    let paints = 0;
    const gl = { domElement: canvas, getPixelRatio: () => 1, setSize() {}, setPixelRatio() {},
      render(scene: THREE.Scene) {
        paints++; scene.updateMatrixWorld(true); currents = [];
        scene.traverse(object => {
          if (object.name === 'actual-body-root') bodyRoot = object as THREE.Group;
          if (object.name === 'actual-dock') dock = object as THREE.Group;
          if (object instanceof THREE.Points) field = object;
          if (testId(object) === 'cortex-posture-field') cue = object as THREE.Mesh;
          if (testId(object) === 'memory-cerebellar-field') memory = object as THREE.Mesh;
          if (testId(object) === 'verification-field') verification = object as THREE.Mesh;
          if (testId(object) === 'cortex-current') { inputLine = object as typeof inputLine; currents.push(inputLine); }
          if (object.name === 'cortex-attention-pulse') pulse = object as THREE.Mesh;
        });
      },
    } as unknown as RootState['gl'];
    await root.configure({ gl, scene: new THREE.Scene(), camera, frameloop: 'never', size: { width: 720, height: 720, left: 0, top: 0 } });
    function Body() {
      const ref = useRef<THREE.Group>(null); useBodyWorldFrame(ref);
      return <group position={[0.3, 0.1, -0.2]} rotation={[0.03, -0.4, 0.02]}>
        <group ref={ref} name="actual-body-root" position={[0.42, 0.18, -1.2]} rotation={[0.04, -0.78, 0.02]} scale={3.02}>
          <group name="actual-dock" scale={0.54}>
            <BrainPointField source={source} uniforms={uniforms} count={96} spineCount={256} spineScale={0.4} physical={physical} />
          </group>
        </group>
      </group>;
    }
    function ComposerOwner() { useFrame(({ gl: renderer, scene, camera: view }) => renderer.render(scene, view), 1); return null; }
    const step = (time: number) => act(() => advance(time, false, store.getState()));
    const renderScene = async (active: boolean) => act(async () => {
      root.render(<><Body /><SuperbrainReactiveEffects presentationOverride={being} inputAttentionActive={active} /><ComposerOwner /></>);
    });
    try {
      setBrainDockScale(0.54);
      if (seat !== null) act(() => { showContentSurface({ code: 'print("focused")', language: 'python', filepath: 'focused.py' }, { seatIndex: seat }); });
      await renderScene(seat === null);
      let time = 0;
      step(time);
      expect(cue && memory && verification && inputLine && field).toBeTruthy();
      const originalGeometry = field.geometry;
      const intakeContactError = () => {
        const fusion = getSpineFusion();
        const cauda = new THREE.Vector3(0, -2.85, -0.42).multiplyScalar(fusion.spineScale)
          .add(new THREE.Vector3(...fusion.weld)).applyMatrix4(field.matrixWorld);
        const last = inputLine.geometry.getAttribute('instanceEnd');
        return new THREE.Vector3().fromBufferAttribute(last, last.count - 1)
          .applyMatrix4(inputLine.matrixWorld).distanceTo(cauda);
      };
      if (seat === null) expect.soft(intakeContactError(), 'zero-delta first paint contact').toBeLessThan(1e-3);
      for (const [scale, dockScale, yaw, dockYaw] of [[3.02, 0.54, -0.78, 0.4], [1.9, 0.35, 0.8, -0.3], [3.45, 0.72, -1.6, 0.7]]) {
        bodyRoot.scale.setScalar(scale); bodyRoot.rotation.y = yaw;
        bodyRoot.position.x += 0.13; bodyRoot.parent!.position.y += 0.08;
        dock.scale.setScalar(dockScale); dock.rotation.y = dockYaw; setBrainDockScale(dockScale);
        if (seat === null) {
          let largestGap = 0;
          for (let frame = 0; frame < 24; frame++) {
            dock.scale.setScalar(dockScale * (1 + 0.08 * Math.sin(frame / 4)));
            dock.rotation.y = dockYaw + 0.07 * Math.sin(frame / 5);
            time += 1 / 60; step(time);
            largestGap = Math.max(largestGap, intakeContactError());
          }
          expect.soft(largestGap, `moving intake contact scale=${scale} dock=${dockScale}`).toBeLessThan(1e-3);
          dock.scale.setScalar(dockScale); dock.rotation.y = dockYaw;
        }
        for (let frame = 0; frame < 90; frame++) { time += 1 / 60; step(time); }
        const points = field.geometry.getAttribute('position');
        // The analytic cube occupies [-.5,.5]; its pre-existing cortex owner
        // targets the upper55% slice (cut=-.05), not the whole-head average.
        // Reconstruct that physical slice, not the new effect/frame helper.
        const head = new THREE.Vector3();
        let headCount = 0;
        for (let vertex = 0; vertex < 96; vertex++) if (points.getY(vertex) >= -0.05) {
          head.add(new THREE.Vector3().fromBufferAttribute(points, vertex)); headCount++;
        }
        expect(headCount).toBeGreaterThan(0);
        head.divideScalar(headCount).applyMatrix4(field.matrixWorld);
        const actual = cue.getWorldPosition(new THREE.Vector3());
        expect.soft(actual.distanceTo(head), `cue scale=${scale} dock=${dockScale}`).toBeLessThan(1e-5);
        expect.soft(cue.getWorldScale(new THREE.Vector3()).x).toBeCloseTo(0.24, 7);
        const poseRotation = bodyRoot.getWorldQuaternion(new THREE.Quaternion());
        expect.soft(memory.getWorldPosition(new THREE.Vector3()).distanceTo(head.clone().add(new THREE.Vector3(-0.16, -0.06, 0.035).applyQuaternion(poseRotation)))).toBeLessThan(1e-5);
        expect.soft(verification.getWorldPosition(new THREE.Vector3()).distanceTo(head.clone().add(new THREE.Vector3(0, 0, 0.02).applyQuaternion(poseRotation)))).toBeLessThan(1e-5);
        const fusion = getSpineFusion();
        // Literal top/bottom vertebrae, independent of the new target helper.
        const target = new THREE.Vector3(0, seat === 0 ? -0.92 : -2.85, -0.42)
          .multiplyScalar(fusion.spineScale).add(new THREE.Vector3(...fusion.weld)).applyMatrix4(field.matrixWorld);
        if (seat === null) {
          const last = inputLine.geometry.getAttribute('instanceEnd');
          const end = new THREE.Vector3().fromBufferAttribute(last, last.count - 1).applyMatrix4(inputLine.matrixWorld);
          expect.soft(end.distanceTo(target), `input endpoint scale=${scale} dock=${dockScale}`).toBeLessThan(1e-3);
        } else {
          expect(currents).toHaveLength(3);
          // The middle fan has zero lateral offset. Its rendered bearing must
          // point from the physical cortex to the selected physical seat,
          // even when the inner dock rotates independently of the body pose.
          const current = currents[1];
          const start = new THREE.Vector3().fromBufferAttribute(current.geometry.getAttribute('instanceStart'), 0).applyMatrix4(current.matrixWorld);
          const middle = new THREE.Vector3().fromBufferAttribute(current.geometry.getAttribute('instanceEnd'), 0).applyMatrix4(current.matrixWorld);
          const bearing = target.clone().sub(head).normalize();
          expect.soft(middle.clone().sub(start).normalize().dot(bearing), `seat=${seat} dockYaw=${dockYaw}`).toBeGreaterThan(0.99999);
          expect.soft(start.clone().sub(head).normalize().dot(bearing)).toBeGreaterThan(0.99999);
          expect.soft(middle.distanceTo(head)).toBeLessThan(0.79);
          expect(current.visible).toBe(true);
        }
        expect(field.geometry).toBe(originalGeometry);
        // The product's composer draws at1; this existing effect seam samples
        // diagnostics at2. This witness does not certify automatic-draw mode.
        expect(store.getState().internal.priority).toBe(2);
      }
      if (seat !== null) {
        expect((field.material as THREE.ShaderMaterial).uniforms.uSprayHide.value).toBeGreaterThan(0.999);
        expect(paints).toBe(271); return;
      }
      let retained!: ReturnType<typeof showContentSurface>;
      act(() => { retained = showContentSurface({ code: 'print("retained")', language: 'python', filepath: 'retained.py' }); });
      time += 10; step(time);
      expect((field.material as THREE.ShaderMaterial).uniforms.uSprayHide.value).toBeGreaterThan(0.999);
      expect(inputLine.visible).toBe(false); expect(pulse.visible).toBe(false);
      const inputPulse = pulse;
      await renderScene(false); time += 1 / 60; step(time);
      // A calm cortex current remains visible after blur, but an outbound
      // input pulse must not depart from an unavailable cauda junction.
      expect(inputLine.visible).toBe(true); expect(inputPulse.parent).not.toBeNull(); expect(inputPulse.visible).toBe(false);
      await renderScene(true); time += 1 / 60; step(time);
      expect(pulse).toBe(inputPulse);
      expect(inputLine.visible).toBe(false); expect(pulse.visible).toBe(false);
      act(() => { expect(beginRetractingMaterializedTab(retained.id)).toBe(true); });
      time += 10; step(time);
      expect((field.material as THREE.ShaderMaterial).uniforms.uSprayHide.value).toBeLessThan(0.001);
      expect(inputLine.visible).toBe(true); expect(pulse.visible).toBe(true);
      expect(field.geometry).toBe(originalGeometry);

      // The original input bead must return along the current anatomy, not
      // the path captured before blur. Zero delta keeps its elapsed progress;
      // independently reconstruct both endpoints from the physical head/tail.
      await renderScene(false);
      dock.scale.multiplyScalar(0.75); dock.rotation.y += 0.2;
      step(time);
      expect(inputPulse.parent).not.toBeNull();
      expect(inputPulse.visible).toBe(!reduced);
      const returnError = (progress: number) => {
        const points = field.geometry.getAttribute('position');
        const head = new THREE.Vector3(); let count = 0;
        for (let vertex = 0; vertex < 96; vertex++) if (points.getY(vertex) >= -0.05) {
          head.add(new THREE.Vector3().fromBufferAttribute(points, vertex)); count++;
        }
        head.divideScalar(count).applyMatrix4(field.matrixWorld);
        const fusion = getSpineFusion();
        const cauda = new THREE.Vector3(0, -2.85, -0.42).multiplyScalar(fusion.spineScale)
          .add(new THREE.Vector3(...fusion.weld)).applyMatrix4(field.matrixWorld);
        const start = head.clone().add(cauda.clone().sub(head).normalize().multiplyScalar(0.08));
        const eased = progress * progress * (3 - 2 * progress);
        return inputPulse.getWorldPosition(new THREE.Vector3()).distanceTo(start.lerp(cauda, eased));
      };
      if (!reduced) expect.soft(returnError(1), 'first outbound contact after docking').toBeLessThan(1e-3);
      let largestReturnGap = 0;
      for (let frame = 0; frame < 24; frame++) {
        dock.scale.setScalar(0.72 * (0.7 + 0.12 * Math.sin(frame / 4)));
        dock.rotation.y = 0.9 + 0.08 * Math.cos(frame / 5);
        time += 1 / 60; step(time);
        expect(inputPulse.visible).toBe(!reduced);
        if (!reduced) largestReturnGap = Math.max(largestReturnGap, returnError(1 - (frame + 1) / (60 * 0.72)));
      }
      if (!reduced) expect.soft(largestReturnGap, 'outbound follows moving physical path').toBeLessThan(1e-3);
      const returnPosition = inputPulse.getWorldPosition(new THREE.Vector3());
      const returnAnatomyMatrix = field.matrixWorld.clone();
      await renderScene(true); step(time);
      expect(pulse).toBe(inputPulse); expect(inputPulse.visible).toBe(true);
      expect(field.matrixWorld.equals(returnAnatomyMatrix)).toBe(true);
      if (!reduced) expect.soft(inputPulse.getWorldPosition(new THREE.Vector3()).distanceTo(returnPosition),
        'zero-delta reversal keeps spatial position as well as progress').toBeLessThan(1e-6);
      expect(inputPulse.scale.x).toBeCloseTo(0.036 + (reduced ? 1 : 1 - 24 / (60 * 0.72)) * 0.034, 7);
      const resumedPosition = inputPulse.getWorldPosition(new THREE.Vector3());
      await renderScene(false); step(time);
      expect(inputPulse.visible).toBe(!reduced);
      if (!reduced) expect.soft(inputPulse.getWorldPosition(new THREE.Vector3()).distanceTo(resumedPosition),
        'zero-delta release stays on the same physical path').toBeLessThan(1e-6);
      expect(field.geometry).toBe(originalGeometry);
      expect(paints).toBe(374);
    } finally {
      await act(async () => { root.unmount(); });
      source.geometry.dispose(); (source.material as THREE.Material).dispose();
    }
  });
