import { act } from 'react';
import { _roots, advance, createRoot, extend, useFrame, type RootState } from '@react-three/fiber';
import * as THREE from 'three';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import CommandNerve3D from '../../superbrain/components/canvas/CommandNerve3D';
import { __resetFunnelAnchorForTests, setFunnelAnchor } from '../../superbrain/lib/funnelAnchorBus';

extend({ Group: THREE.Group, Mesh: THREE.Mesh, BufferGeometry: THREE.BufferGeometry,
  SphereGeometry: THREE.SphereGeometry, MeshBasicMaterial: THREE.MeshBasicMaterial,
  MeshStandardMaterial: THREE.MeshStandardMaterial });

beforeEach(() => {
  __resetFunnelAnchorForTests();
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
});
afterEach(() => {
  __resetFunnelAnchorForTests();
  document.querySelector('.gagos-send')?.remove();
  vi.restoreAllMocks(); vi.unstubAllGlobals();
});

// An unchecked below-cauda control point must fail the actual painted-tube
// bounds, even when both attachment nodes remain on screen. Only WebGL is
// replaced: the existing publisher seam, R3F, tube, nodes and camera run.
// Endpoint pixels are independent fixtures, not a second curve implementation;
// this does not qualify GLB anatomy, GPU rendering or physical devices.
it.each([false, true])('keeps the complete receiving nerve in its canvas; reduced=%s', async reduced => {
  const canvas = document.createElement('canvas');
  const root = createRoot(canvas), store = _roots.get(canvas)!.store;
  const send = document.createElement('button'); send.className = 'gagos-send'; document.body.append(send);
  let sendBox = new DOMRect(229, 346.6, 44, 44);
  vi.spyOn(send, 'getBoundingClientRect').mockImplementation(() => sendBox);
  let socket = [780, 646];
  let fixedSocket: THREE.Vector3 | null = null;
  let bounds = { width: 1280, height: 659.2, left: 0, top: 60.8 };
  const camera = new THREE.PerspectiveCamera(26, bounds.width / bounds.height, 0.1, 100);
  camera.position.set(0, -0.5, 15); camera.lookAt(0, -0.5, 0); camera.updateMatrixWorld();
  const depth = new THREE.Vector3(0, 0, 0).project(camera).z;
  let painted = 0;
  let originalTube: THREE.Mesh | undefined;
  const captures: { overflow: number; socket: number; input: number; beadGap: number }[] = [];
  const gl = { domElement: canvas, getPixelRatio: () => 1, setSize() {}, setPixelRatio() {},
    render(scene: THREE.Scene, view: THREE.Camera) {
      scene.updateMatrixWorld(true); painted++;
      let tube!: THREE.Mesh<THREE.TubeGeometry>, bodyNode!: THREE.Group, inputNode!: THREE.Group, beads!: THREE.Group;
      scene.traverse(object => {
        if (!(object instanceof THREE.Mesh)) return;
        if (object.geometry instanceof THREE.TubeGeometry) tube = object as THREE.Mesh<THREE.TubeGeometry>;
        if (!(object.geometry instanceof THREE.SphereGeometry)) return;
        if (object.geometry.parameters.radius === 0.034) bodyNode = object.parent as THREE.Group;
        if (object.geometry.parameters.radius === 0.026) inputNode = object.parent as THREE.Group;
        if (object.geometry.parameters.radius === 0.02) beads = object.parent as THREE.Group;
      });
      expect(tube.visible && bodyNode.visible && inputNode.visible).toBe(true);
      originalTube ??= tube; expect(tube).toBe(originalTube);
      const screenPoint = (point: THREE.Vector3) => {
        const ndc = point.clone().project(view);
        return new THREE.Vector2(bounds.left + (ndc.x + 1) * bounds.width / 2,
          bounds.top + (1 - ndc.y) * bounds.height / 2);
      };
      let overflow = 0;
      const positions = tube.geometry.getAttribute('position');
      for (let vertex = 0; vertex < positions.count; vertex++) {
        const point = screenPoint(new THREE.Vector3().fromBufferAttribute(positions, vertex).applyMatrix4(tube.matrixWorld));
        overflow = Math.max(overflow, bounds.left - point.x, point.x - bounds.left - bounds.width,
          bounds.top - point.y, point.y - bounds.top - bounds.height);
      }
      // Independent centerline from the actual painted tube's radial rings,
      // not its mutable Curve or production timing/path helpers. Beads must
      // ride THIS frame's tube on first paint and after moving an endpoint.
      const centers: THREE.Vector3[] = [];
      for (let ring = 0; ring <= 48; ring++) {
        const center = new THREE.Vector3();
        for (let radial = 0; radial < 10; radial++) {
          center.add(new THREE.Vector3().fromBufferAttribute(positions, ring * 11 + radial));
        }
        centers.push(center.multiplyScalar(0.1).applyMatrix4(tube.matrixWorld));
      }
      let beadGap = 0;
      expect(beads.visible).toBe(!reduced);
      if (beads.visible) for (const bead of beads.children) {
        const point = bead.getWorldPosition(new THREE.Vector3());
        let nearest = Infinity;
        for (let segment = 1; segment < centers.length; segment++) {
          const closest = new THREE.Line3(centers[segment - 1], centers[segment]).closestPointToPoint(point, true, new THREE.Vector3());
          nearest = Math.min(nearest, point.distanceTo(closest));
        }
        beadGap = Math.max(beadGap, nearest);
      }
      captures.push({ overflow,
        beadGap,
        socket: screenPoint(bodyNode.getWorldPosition(new THREE.Vector3())).distanceTo(new THREE.Vector2(...socket)),
        input: screenPoint(inputNode.getWorldPosition(new THREE.Vector3())).distanceTo(new THREE.Vector2(sendBox.x + 22, sendBox.y + 22)),
      });
    },
  } as unknown as RootState['gl'];
  await root.configure({ gl, scene: new THREE.Scene(), camera, frameloop: 'never', size: bounds });
  function CurrentAnchor() {
    useFrame(() => {
      const point = fixedSocket?.clone() ?? new THREE.Vector3((socket[0] - bounds.left) / bounds.width * 2 - 1,
        1 - (socket[1] - bounds.top) / bounds.height * 2, depth).unproject(camera);
      setFunnelAnchor({ x: socket[0], y: socket[1], world: point.toArray(), visible: true,
        presence: 1, intake: 0.72, flow: reduced ? 0 : 0.32 });
    });
    return null;
  }
  function ComposerOwner() { useFrame(({ gl: renderer, scene, camera: view }) => renderer.render(scene, view), 1); return null; }
  const step = (time: number) => act(() => advance(time, false, store.getState()));
  try {
    await act(async () => { root.render(<><CurrentAnchor /><CommandNerve3D reducedMotion={reduced} /><ComposerOwner /></>); });
    step(100);
    // The short desktop corresponds to the measured 1280x720 fixture app;
    // subsequent independently chosen socket poses keep its nodes in view.
    for (const pose of [[812, 650], [775, 675], [785, 646]]) { socket = pose; step(101 + captures.length); }
    // Camera-only magnification: keep both WORLD contacts unchanged, move
    // their DOM/screen witnesses to the newly projected pixels. Both nodes
    // still fit; retaining controls from the old lens clips the painted tube.
    fixedSocket = new THREE.Vector3((socket[0] - bounds.left) / bounds.width * 2 - 1,
      1 - (socket[1] - bounds.top) / bounds.height * 2, depth).unproject(camera);
    const fixedInput = new THREE.Vector3((sendBox.x + 22 - bounds.left) / bounds.width * 2 - 1,
      1 - (sendBox.y + 22 - bounds.top) / bounds.height * 2, depth).unproject(camera);
    camera.zoom = 1.28; camera.updateProjectionMatrix();
    const socketNdc = fixedSocket.clone().project(camera), inputNdc = fixedInput.clone().project(camera);
    socket = [bounds.left + (socketNdc.x + 1) * bounds.width / 2,
      bounds.top + (1 - socketNdc.y) * bounds.height / 2];
    sendBox = new DOMRect(bounds.left + (inputNdc.x + 1) * bounds.width / 2 - 22,
      bounds.top + (1 - inputNdc.y) * bounds.height / 2 - 22, 44, 44);
    step(101 + captures.length);
    fixedSocket = null; camera.zoom = 1; camera.updateProjectionMatrix();
    bounds = { width: 390, height: 700, left: 0, top: 144 };
    camera.aspect = bounds.width / bounds.height; camera.updateProjectionMatrix();
    store.getState().setSize(bounds.width, bounds.height, bounds.top, bounds.left);
    sendBox = new DOMRect(308, 738, 44, 44);
    for (const pose of [[195, 450], [210, 454], [175, 466]]) { socket = pose; step(101 + captures.length); }
    expect(painted).toBe(8); expect(store.getState().internal.priority).toBe(1);
    for (const [frame, capture] of captures.entries()) {
      expect.soft(capture.socket, `frame ${frame} body contact`).toBeLessThan(1e-5);
      expect.soft(capture.input, `frame ${frame} input contact`).toBeLessThan(1e-5);
      expect.soft(capture.overflow, `frame ${frame} painted tube outside canvas (pixels)`).toBeLessThan(0.01);
      expect.soft(capture.beadGap, `frame ${frame} words outside their painted nerve (world units)`).toBeLessThan(0.026);
    }
    // The imperative replacement is not the JSX placeholder owned by R3F.
    // Removing this subtree while its renderer survives must release the final
    // actual generated geometry, once; no mocked disposal method is involved.
    const finalGeometry = originalTube!.geometry;
    let finalDisposals = 0;
    finalGeometry.addEventListener('dispose', () => { finalDisposals++; });
    await act(async () => { root.render(null); });
    expect(finalDisposals).toBe(1);
  } finally { await act(async () => { root.unmount(); }); }
});
