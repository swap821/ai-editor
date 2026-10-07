import { act } from 'react';
import { _roots, advance, createRoot, extend, type RootState } from '@react-three/fiber';
import * as THREE from 'three';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import BrainPointField from '../../superbrain/components/canvas/BrainPointField';
import CosmicBackground from '../../superbrain/components/canvas/CosmicBackground';
import { SCENE_UNIFORMS } from '../../superbrain/components/canvas/SuperbrainScene.LEGACY';

// The scene module preloads its GLB as an import side effect. This fixture
// supplies a real mesh directly; do not issue that unrelated asset request.
vi.mock('../../superbrain/lib/brainScene', () => ({ preloadBrainScene() {} }));

extend({ Group: THREE.Group, Points: THREE.Points, PointsMaterial: THREE.PointsMaterial });

beforeEach(() => {
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
  vi.stubGlobal('matchMedia', () => Object.assign(new EventTarget(), { matches: false }));
  // Only Canvas2D rasterization and WebGL are substituted. Point sampling,
  // materials, mounted components and R3F resize/frame scheduling are real.
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({
    clearRect() {}, fillText() {},
  } as unknown as CanvasRenderingContext2D);
});
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it('fits body and backdrop point footprints to the compact canvas without resampling or changing palette', async () => {
  const canvas = document.createElement('canvas');
  const root = createRoot(canvas);
  const store = _roots.get(canvas)!.store;
  const renderer = { domElement: canvas, render() {}, setSize() {}, setPixelRatio() {}, getPixelRatio: () => 2 } as unknown as RootState['gl'];
  const source = new THREE.Mesh(new THREE.BoxGeometry(), new THREE.MeshBasicMaterial({ color: '#7bf5fb' }));
  await root.configure({ gl: renderer, scene: new THREE.Scene(), camera: new THREE.PerspectiveCamera(),
    frameloop: 'never', size: { width: 320, height: 168, top: 0, left: 0 } });
  try {
    await act(async () => { root.render(<>
      <BrainPointField source={source} uniforms={SCENE_UNIFORMS} count={96} spineCount={32} baseSize={2} />
      <CosmicBackground tier="low" reducedMotion />
    </>); });
    act(() => advance(1, false, store.getState()));
    let body!: THREE.Points;
    let sky!: THREE.Points;
    store.getState().scene.traverse((object) => {
      if (object instanceof THREE.Points) {
        if (object.material instanceof THREE.ShaderMaterial) body = object;
        else sky = object;
      }
    });
    const material = body.material as THREE.ShaderMaterial;
    const geometry = body.geometry;
    const colors = Array.from(geometry.getAttribute('aColor').array);
    // Use the installed renderer's template, not an invented GLSL shape.
    // This verifies registration against the real compile boundary. It still
    // does not execute GLSL; native captures supply separate visual evidence.
    const shader = { uniforms: THREE.UniformsUtils.clone(THREE.ShaderLib.points.uniforms),
      vertexShader: THREE.ShaderLib.points.vertexShader,
      fragmentShader: THREE.ShaderLib.points.fragmentShader,
    } as Parameters<THREE.PointsMaterial['onBeforeCompile']>[0];
    (sky.material as THREE.PointsMaterial).onBeforeCompile(shader, renderer);
    expect.soft(material.uniforms.uViewportScale?.value).toBe(1);
    expect.soft(shader.uniforms.uViewportScale?.value).toBe(1);

    await act(async () => { store.getState().setSize(320, 62, 0, 0); });
    act(() => advance(2, false, store.getState()));
    // Hand-derived: a 62px band has 62/168 of the normal phone band's
    // linear footprint. DPR remains independent; authored size is unchanged.
    expect.soft(material.uniforms.uViewportScale?.value).toBeCloseTo(0.369047619);
    expect.soft(shader.uniforms.uViewportScale?.value).toBeCloseTo(0.369047619);
    expect(material.uniforms.uPixelRatio.value).toBe(2);
    expect(material.uniforms.uSize.value).toBe(2);
    expect(body.geometry).toBe(geometry);
    expect(Array.from(geometry.getAttribute('aColor').array)).toEqual(colors);

    // Drawing the intake across a full phone stage must not reinflate the
    // puncta of the same 62px presence pane. Both mounted consumers are real.
    await act(async () => { store.getState().setSize(320, 568, 0, 0); });
    const camera = store.getState().camera as THREE.PerspectiveCamera;
    camera.setViewOffset(320, 62, 0, -164, 320, 568);
    act(() => advance(2.5, false, store.getState()));
    expect.soft(material.uniforms.uViewportScale?.value).toBeCloseTo(62 / 168);
    expect.soft(shader.uniforms.uViewportScale?.value).toBeCloseTo(62 / 168);
    expect(body.geometry).toBe(geometry);
    camera.clearViewOffset();

    await act(async () => { store.getState().setSize(1440, 900, 0, 0); });
    act(() => advance(3, false, store.getState()));
    expect.soft(material.uniforms.uViewportScale?.value).toBe(1);
    expect.soft(shader.uniforms.uViewportScale?.value).toBe(1);
    expect(body.geometry).toBe(geometry);
  } finally {
    await act(async () => { root.unmount(); });
    source.geometry.dispose(); (source.material as THREE.Material).dispose();
  }
});
