import * as THREE from 'three';
import { describe, expect, it } from 'vitest';
import { makeBrainMaterial } from './brainMaterial';
import type { BrainMaterialOptions } from './brainMaterial';

type CompileArgs = Parameters<THREE.Material['onBeforeCompile']>;

const leaves = {
  uTime: { value: 1 },
  uHold: { value: 0 },
  uArrival: { value: 0 },
  uIgnite: { value: 0 },
  uBreath: { value: 0.5 },
};

function opts(over: Partial<BrainMaterialOptions> = {}): BrainMaterialOptions {
  return {
    tier: 'high',
    uniforms: leaves as unknown as BrainMaterialOptions['uniforms'],
    ...over,
  };
}

function compile(over: Partial<BrainMaterialOptions> = {}) {
  const mat = makeBrainMaterial(opts(over));
  const shader = {
    uniforms: {} as Record<string, { value: unknown }>,
    vertexShader: '#include <common>\n#include <begin_vertex>',
    fragmentShader:
      '#include <common>\n#include <color_fragment>\n#include <emissivemap_fragment>',
  };
  mat.onBeforeCompile(
    shader as unknown as CompileArgs[0],
    {} as unknown as CompileArgs[1],
  );
  return { mat, shader };
}

describe('makeBrainMaterial material setup', () => {
  it('builds an opaque vertex-coloured glass material by default', () => {
    const mat = makeBrainMaterial(opts());
    expect(mat).toBeInstanceOf(THREE.MeshPhysicalMaterial);
    expect(mat.vertexColors).toBe(true);
    expect(mat.clearcoat).toBe(1);
    expect(mat.roughness).toBe(0.2);
    expect(mat.transparent).toBe(false);
  });

  it('turns the node-brain cortex into a translucent non-depth-writing cranium', () => {
    const mat = makeBrainMaterial(opts({ nodeBrain: true }));
    expect(mat.transparent).toBe(true);
    expect(mat.opacity).toBe(0.16);
    expect(mat.depthWrite).toBe(false);
  });
});

describe('onBeforeCompile on the cortex', () => {
  it('links the shared leaves by reference and defaults posture to rest', () => {
    const { shader } = compile();
    expect(shader.uniforms.uTime).toBe(leaves.uTime);
    expect(shader.uniforms.uHold).toBe(leaves.uHold);
    expect(shader.uniforms.uArrival).toBe(leaves.uArrival);
    expect(shader.uniforms.uIgnite).toBe(leaves.uIgnite);
    expect(shader.uniforms.uPostureTint.value).toBe(0);
    expect(shader.uniforms.uPostureCommit.value).toBe(0);
    const c = shader.uniforms.uPostureColor.value as THREE.Color;
    expect(c.r).toBeCloseTo(150 / 255, 5);
    expect(c.g).toBeCloseTo(120 / 255, 5);
    expect(c.b).toBeCloseTo(1, 5);
  });

  it('uses supplied posture leaves instead of the defaults', () => {
    const color = { value: new THREE.Color(0.1, 0.2, 0.3) };
    const tint = { value: 0.4 };
    const { shader } = compile({ postureColorUniform: color, postureTintUniform: tint });
    expect(shader.uniforms.uPostureColor).toBe(color);
    expect(shader.uniforms.uPostureTint).toBe(tint);
  });

  it('declares no nerve uniforms or attributes and uses the full 27-cell loop', () => {
    const { shader } = compile();
    expect(shader.uniforms.uBreath).toBeUndefined();
    expect(shader.uniforms.uNerveScale).toBeUndefined();
    expect(shader.vertexShader).not.toContain('aArc');
    expect(shader.fragmentShader).not.toContain('uNerveScale');
    expect(shader.fragmentShader).toContain('for(int k=-1; k<=1; k++)');
    expect(shader.fragmentShader).toContain('float scale = 0.6000;');
  });

  it('gates octaves and animation by tier and webOctaves', () => {
    const high = compile({ tier: 'high' }).shader.fragmentShader;
    expect(high).toContain('float v2 = voronoi');
    expect(high).toContain('sin(uTime * 1.2');

    const low = compile({ tier: 'low' }).shader.fragmentShader;
    expect(low).not.toContain('float v2 = voronoi');
    expect(low).toContain('vec3 anim = vec3(0.5);');

    const forced = compile({ tier: 'high', webOctaves: 1 }).shader.fragmentShader;
    expect(forced).not.toContain('float v2 = voronoi');
  });

  it('replaces microDetail with a zero return in node-brain mode', () => {
    const { shader } = compile({ nodeBrain: true });
    expect(shader.fragmentShader).toContain('return 0.0;');
    expect(shader.fragmentShader).not.toContain('float scale = 0.6000;');
  });
});

describe('onBeforeCompile on the nerve', () => {
  it('wires supplied leaves and falls back to defaults for the rest', () => {
    const breath = { value: 0.9 };
    const flow = { value: 0.3 };
    const { shader } = compile({
      bodyMode: 'nerve',
      breathUniform: breath,
      flowUniform: flow,
    });
    expect(shader.uniforms.uBreath).toBe(breath);
    expect(shader.uniforms.uFlow).toBe(flow);
    expect(shader.uniforms.uGrow.value).toBe(1);
    expect(shader.uniforms.uFlowGain.value).toBe(1);
    expect(shader.uniforms.uReduceMotion.value).toBe(0);
    expect(shader.uniforms.uIntakeGain.value).toBe(0);
  });

  it('falls back to the shared uBreath leaf when no breath uniform is given', () => {
    const { shader } = compile({ bodyMode: 'nerve' });
    expect(shader.uniforms.uBreath).toBe(leaves.uBreath);
  });

  it('adds nerve attributes and the 8-cell loop to the shaders', () => {
    const { shader } = compile({ bodyMode: 'nerve', webScale: 3 });
    expect(shader.vertexShader).toContain('attribute float aArc;');
    expect(shader.vertexShader).toContain('transformed = mix(aBirth, position, born);');
    expect(shader.fragmentShader).toContain('for(int k=-1; k<=0; k++)');
    expect(shader.fragmentShader).toContain('float scale = uNerveScale;');
    expect(shader.fragmentShader).toContain('float nerveBreath = 0.92 + 0.08 * uBreath;');
  });

  it('exposes live-tunable aesthetic leaves seeded from webScale', () => {
    const { mat, shader } = compile({ bodyMode: 'nerve', webScale: 3 });
    const nerveU = (mat as unknown as {
      __nerveU?: Record<string, { value: number }>;
    }).__nerveU;
    expect(nerveU?.uNerveScale.value).toBe(3);
    expect(nerveU?.uNerveContrastLo.value).toBe(0.24);
    expect(nerveU?.uNerveContrastHi.value).toBe(0.6);
    expect(nerveU?.uNerveCoreGlow.value).toBe(2.3);
    expect(nerveU?.uNerveFresnel.value).toBe(1.05);
    expect(shader.uniforms.uNerveScale).toBe(nerveU?.uNerveScale);
  });

  it('does not expose nerve leaves on the cortex', () => {
    const mat = makeBrainMaterial(opts());
    expect((mat as unknown as { __nerveU?: unknown }).__nerveU).toBeUndefined();
  });
});
