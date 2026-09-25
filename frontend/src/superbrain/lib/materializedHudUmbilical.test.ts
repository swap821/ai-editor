import * as THREE from 'three';
import { describe, expect, it } from 'vitest';
import {
  buildFocusedHudUmbilicalCurve,
  shouldUseFocusedHudUmbilical,
} from './materializedSurfaceAnchors';

describe('focused HUD umbilical', () => {
  it('ends just outside the focused panel lower rim instead of entering the slab', () => {
    const panelCenter = new THREE.Vector3(0, 0, 2);
    const panelUp = new THREE.Vector3(0, 4, 0);
    const lowerRim = panelCenter.clone().add(new THREE.Vector3(0, -0.5, 0));
    const curve = buildFocusedHudUmbilicalCurve(
      new THREE.Vector3(-0.2, -0.6, -0.5),
      lowerRim,
      panelUp,
    );
    const endpoint = curve.getPoint(1);

    expect(endpoint.y).toBeLessThan(lowerRim.y);
    expect(endpoint.x).toBeCloseTo(lowerRim.x);
    expect(endpoint.z).toBeCloseTo(lowerRim.z);
  });

  it('uses the direct rim route only for the attended content workspace', () => {
    expect(shouldUseFocusedHudUmbilical('content', true)).toBe(true);
    expect(shouldUseFocusedHudUmbilical('content', false)).toBe(false);
    expect(shouldUseFocusedHudUmbilical('approval', true)).toBe(false);
    expect(shouldUseFocusedHudUmbilical('input', true)).toBe(false);
  });
});
