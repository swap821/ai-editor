import { act, createRef, type RefObject } from 'react';
import { _roots, advance, createRoot, extend, useFrame, type RootState } from '@react-three/fiber';
import { Float } from '@react-three/drei';
import { Group, Matrix4, PerspectiveCamera, Scene } from 'three';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useBodyWorldFrame } from '../../superbrain/lib/useBodyWorldFrame';
import { __resetSpineFusionForTests, copyBodyGroupWorldMatrix } from '../../superbrain/lib/spineFusionBus';

extend({ Group });

function Body({ bodyRef }: { bodyRef: RefObject<Group | null> }) {
  useBodyWorldFrame(bodyRef);
  useFrame(() => {
    bodyRef.current!.position.set(1, 2, 3);
    bodyRef.current!.scale.setScalar(3.02);
  });
  return <group ref={bodyRef} />;
}

beforeEach(() => {
  __resetSpineFusionForTests();
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
  vi.spyOn(Math, 'random').mockReturnValue(0);
});
afterEach(() => {
  __resetSpineFusionForTests();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('mounted body frame continuity', () => {
  it.each([
    { composer: false, speed: 0.46 },
    { composer: true, speed: 0.46 },
    { composer: false, speed: 0 },
  ])('uses the rendered Float pose with composer=$composer, speed=$speed', async ({ composer, speed }) => {
    const canvas = document.createElement('canvas');
    const root = createRoot(canvas);
    const store = _roots.get(canvas)!.store;
    const bodyRef = createRef<Group>();
    const sampled = new Matrix4();
    const rendered: number[][] = [];
    // Only WebGL is replaced. React mounting, the installed Drei Float,
    // production binding/query and installed R3F subscriptions/advance are real.
    const renderer = {
      render(scene: Scene) {
        scene.updateMatrixWorld(true);
        rendered.push(bodyRef.current!.matrixWorld.elements.slice());
      },
      setSize() {},
      setPixelRatio() {},
    } as unknown as RootState['gl'];
    await root.configure({
      gl: renderer,
      scene: new Scene(),
      camera: new PerspectiveCamera(),
      frameloop: 'never',
      size: { width: 400, height: 400, top: 0, left: 0 },
    });

    function ConnectionConsumer() {
      useFrame(() => expect(copyBodyGroupWorldMatrix(sampled)).toBe(true));
      return null;
    }
    function ComposerOwner() {
      useFrame(({ gl, scene, camera }) => gl.render(scene, camera), 1);
      return null;
    }

    try {
      await act(async () => {
        root.render(<>
          <Float speed={speed} rotationIntensity={0.025} floatIntensity={0.1}>
            <Body bodyRef={bodyRef} />
          </Float>
          <ConnectionConsumer />
          {composer && <ComposerOwner />}
        </>);
      });
      expect(bodyRef.current).toBeInstanceOf(Group);
      expect(store.getState().internal.priority).toBe(composer ? 1 : 0);
      const frames: number[][] = [];
      for (const time of [1, 2, 3]) {
        act(() => advance(time, false, store.getState()));
        expect(rendered).toHaveLength(time);
        expect(sampled.elements).toEqual(rendered[rendered.length - 1]);
        frames.push(sampled.elements.slice());
      }
      if (speed === 0) expect(frames[0]).toEqual(frames[2]);
      else expect(frames[0]).not.toEqual(frames[2]);

      await act(async () => { root.render(null); });
      expect(copyBodyGroupWorldMatrix(sampled)).toBe(false);
      expect(store.getState().internal.priority).toBe(0);
    } finally {
      await act(async () => { root.unmount(); });
    }
  });
});
