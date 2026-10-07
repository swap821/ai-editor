import { act } from 'react';
import { createRoot, extend, type RootState } from '@react-three/fiber';
import * as THREE from 'three';
import { afterEach, expect, it, vi } from 'vitest';
import MaterializedTab from '../../superbrain/components/canvas/MaterializedTab';
import { __resetTabStoreForTests, showContentSurface } from '../../superbrain/lib/tabStore';

// The real surface chooses its header through an actual R3F root. Substitute
// only WebGL and remote font shaping; inspect the text supplied to the font
// boundary, not a native glyph or GPU/visual acceptance claim.
vi.mock('@react-three/drei', async (original) => ({
  ...await original<typeof import('@react-three/drei')>(),
  Text: ({ children }: { children: string }) => <group name={`text:${children}`} />,
}));
extend({ Group: THREE.Group, Mesh: THREE.Mesh, Points: THREE.Points, LineSegments: THREE.LineSegments,
  BufferGeometry: THREE.BufferGeometry, SphereGeometry: THREE.SphereGeometry, PlaneGeometry: THREE.PlaneGeometry,
  BoxGeometry: THREE.BoxGeometry, TorusGeometry: THREE.TorusGeometry, TubeGeometry: THREE.TubeGeometry,
  CylinderGeometry: THREE.CylinderGeometry, ShapeGeometry: THREE.ShapeGeometry,
  MeshBasicMaterial: THREE.MeshBasicMaterial, MeshStandardMaterial: THREE.MeshStandardMaterial,
  PointsMaterial: THREE.PointsMaterial, LineBasicMaterial: THREE.LineBasicMaterial, ShaderMaterial: THREE.ShaderMaterial });

afterEach(() => { __resetTabStoreForTests(); vi.unstubAllGlobals(); });

it.each(['', '   '])('the actual 3D surface gives a nonblank local label to an unnamed result (%j)', async (filepath) => {
  __resetTabStoreForTests();
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
  const tab = showContentSurface({ code: '// fixture result', language: 'text', filepath, sourceEventId: 100 });
  const scene = new THREE.Scene();
  const canvas = document.createElement('canvas');
  const root = createRoot(canvas);
  const gl = { render() {}, setSize() {}, setPixelRatio() {} } as unknown as RootState['gl'];
  await root.configure({ gl, scene, camera: new THREE.PerspectiveCamera(42, 1, 0.1, 100),
    frameloop: 'never', size: { width: 500, height: 500, left: 0, top: 0 } });
  try {
    await act(async () => { root.render(<MaterializedTab tab={tab} reducedMotion focused={false} />); });
    expect(scene.getObjectByName('text:Generated result 1')).toBeDefined();
    expect(scene.getObjectByName('text:   ')).toBeUndefined();
  } finally { await act(async () => { root.unmount(); }); }
});
