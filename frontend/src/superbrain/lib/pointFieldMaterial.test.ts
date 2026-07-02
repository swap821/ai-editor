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
    expect(m.blending).toBe(THREE.AdditiveBlending);
  });

  it('exposes the tunable + posture uniforms', () => {
    const m = createPointFieldMaterial();
    for (const key of ['uTime','uPixelRatio','uRefDist','uSize','uAttenK','uFogDensity','uGlowMul',
                        'uGrow','uFlow','uFlowSpeed','uCurlAmp','uArrival','uReabsorb','uIgnite','uAwaken','uStatePulse','uReabsorbGlow',
                        'uBodyOpacity','uBreath','uPostureColor','uPostureTint','uTension']) {
      expect(m.uniforms[key]).toBeDefined();
    }
  });

  it('defaults uBreath to the rest midpoint when not shared', () => {
    const m = createPointFieldMaterial();
    expect(m.uniforms.uBreath.value).toBe(0.5);
  });

  it('accepts shared posture + breath leaf uniforms by reference (phase-lock)', () => {
    const shared = {
      uTime: { value: 3 },
      uPosture: { value: new THREE.Color(1, 0, 0) },
      uPostureTint: { value: 0.5 },
      uBreath: { value: 0.8 },
    };
    const m = createPointFieldMaterial({
      uTime: shared.uTime, uPostureColor: shared.uPosture, uPostureTint: shared.uPostureTint, uBreath: shared.uBreath,
    });
    expect(m.uniforms.uTime).toBe(shared.uTime);
    expect(m.uniforms.uPostureColor).toBe(shared.uPosture);
    expect(m.uniforms.uBreath).toBe(shared.uBreath); // same object → live phase-lock
  });

  it('emits above 1.0 for bloom and has a versioned cache key', () => {
    const m = createPointFieldMaterial();
    expect(m.uniforms.uGlowMul.value).toBeGreaterThan(1.0);
    expect(m.customProgramCacheKey()).toContain('v20');
  });
});
