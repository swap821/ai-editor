import { describe, it, expect } from 'vitest';
import { readGpuMode, hasWebGpu } from './gpuMode';

const navWith = (gpu: boolean) => (gpu ? ({ gpu: {} } as unknown as Navigator) : ({} as Navigator));

describe('gpuMode — flagged + capability-gated WebGPU spike', () => {
  it('defaults to webgl with no params (the shipping path)', () => {
    expect(readGpuMode('', navWith(true))).toBe('webgl');
    expect(readGpuMode('?being=points', navWith(true))).toBe('webgl');
  });

  it('opts into webgpu ONLY with ?gpu=webgpu AND a capable runtime', () => {
    expect(readGpuMode('?gpu=webgpu', navWith(true))).toBe('webgpu');
    expect(readGpuMode('?being=points&gpu=webgpu', navWith(true))).toBe('webgpu');
  });

  it('falls back to webgl when WebGPU is unavailable even if requested', () => {
    expect(readGpuMode('?gpu=webgpu', navWith(false))).toBe('webgl');
  });

  it('ignores any non-webgpu gpu value', () => {
    expect(readGpuMode('?gpu=webgl', navWith(true))).toBe('webgl');
    expect(readGpuMode('?gpu=1', navWith(true))).toBe('webgl');
  });

  it('hasWebGpu detects the navigator.gpu entry point', () => {
    expect(hasWebGpu(navWith(true))).toBe(true);
    expect(hasWebGpu(navWith(false))).toBe(false);
    expect(hasWebGpu(undefined)).toBe(false);
  });
});
