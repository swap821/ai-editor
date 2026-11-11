import { describe, it, expect } from 'vitest';
import * as THREE from 'three';
import { createSupervisedHaloMaterial, updateSupervisedHaloFrame } from './supervisedHalo';

describe('supervision halo lab material', () => {
  it('drives the actual rim shader opacity without replacing its material or uniform owner', () => {
    const material = createSupervisedHaloMaterial();
    const uniforms = (material as THREE.ShaderMaterial).uniforms;
    expect(uniforms?.uOpacity?.value).toBeCloseTo(0.06, 12);
    const opacity = uniforms.uOpacity;
    updateSupervisedHaloFrame(material, -Math.PI / 2 / 1.1, false);
    expect(opacity.value).toBeCloseTo(0.04, 12);
    updateSupervisedHaloFrame(material, Math.PI / 2 / 1.1, false);
    expect(opacity.value).toBeCloseTo(0.09, 12);
    expect((material as THREE.ShaderMaterial).uniforms).toBe(uniforms);
    expect(uniforms.uOpacity).toBe(opacity);
    material.dispose();
  });

  it('holds the same quiet halo under reduced motion across arbitrary frame times', () => {
    const material = createSupervisedHaloMaterial();
    const uniforms = (material as THREE.ShaderMaterial).uniforms;
    for (const elapsed of [0, 0.8, 10, 600]) {
      updateSupervisedHaloFrame(material, elapsed, true);
      expect(uniforms?.uOpacity?.value).toBeCloseTo(0.065, 12);
    }
    material.dispose();
  });

  it('preserves the authored green and transparent additive non-depth-writing boundary', () => {
    const material = createSupervisedHaloMaterial();
    expect((material as THREE.ShaderMaterial).uniforms?.uColor?.value.getHexString()).toBe('54f0a0');
    expect(material.transparent).toBe(true);
    expect(material.blending).toBe(THREE.AdditiveBlending);
    expect(material.depthWrite).toBe(false);
    expect(material.toneMapped).toBe(false);
    material.dispose();
  });
});
