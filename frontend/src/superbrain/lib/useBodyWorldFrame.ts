import { useLayoutEffect, type RefObject } from 'react';
import type { Object3D } from 'three';
import { clearBodyGroupWorldMatrix, setBodyGroupWorldMatrix } from './spineFusionBus';

/** Publish scene identity, not a snapshot taken before the parent Float runs. */
export function useBodyWorldFrame(ref: RefObject<Object3D | null>): void {
  useLayoutEffect(() => {
    const body = ref.current;
    if (!body) return;
    setBodyGroupWorldMatrix(body.matrixWorld, body);
    return () => clearBodyGroupWorldMatrix(body);
  }, [ref]);
}
