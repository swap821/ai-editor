// frontend/src/superbrain/lib/pointFieldMaterial.test.ts
import { describe, it, expect } from 'vitest';
import * as THREE from 'three';
import { createPointFieldMaterial } from './pointFieldMaterial';

describe('createPointFieldMaterial', () => {
  it('is additive, depth-write-off, transparent, tone-map-off', () => {
    const m = createPointFieldMaterial();
    expect(m).toBeInstanceOf(THREE.ShaderMaterial);
    expect(m.depthWrite).toBe(false);
    expect(m.transparent).toBe(true);
    expect(m.toneMapped).toBe(false);
    expect(m.blending).toBe(THREE.CustomBlending);
    expect(m.premultipliedAlpha).toBe(true);
  });

  it('exposes the tunable + posture uniforms', () => {
    const m = createPointFieldMaterial();
    for (const key of ['uTime','uPixelRatio','uRefDist','uSize','uAttenK','uFogDensity','uGlowMul',
                        'uGrow','uFlow','uFlowSpeed','uCurlAmp','uArrival','uReabsorb',
                        'uPostureColor','uPostureTint']) {
      expect(m.uniforms[key]).toBeDefined();
    }
  });

  it('accepts shared posture leaf uniforms by reference', () => {
    const shared = { uTime: { value: 3 }, uPosture: { value: new THREE.Color(1, 0, 0) }, uPostureTint: { value: 0.5 } };
    const m = createPointFieldMaterial({
      uTime: shared.uTime, uPostureColor: shared.uPosture, uPostureTint: shared.uPostureTint,
    });
    expect(m.uniforms.uTime).toBe(shared.uTime);
    expect(m.uniforms.uPostureColor).toBe(shared.uPosture);
  });

  it('emits above 1.0 for bloom and has a versioned cache key', () => {
    const m = createPointFieldMaterial();
    expect(m.uniforms.uGlowMul.value).toBeGreaterThan(1.0);
    expect(m.customProgramCacheKey()).toContain('v4');
  });
});
