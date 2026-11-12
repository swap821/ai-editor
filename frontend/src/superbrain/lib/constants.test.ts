import { describe, expect, it } from 'vitest';
import { CAMERA, POST_FX } from './constants';

describe('CAMERA', () => {
  it('places the camera on the z axis looking at the origin scene', () => {
    expect(CAMERA.position).toEqual([0, 0, 12]);
    expect(CAMERA.fov).toBe(45);
  });

  it('has a valid clipping range', () => {
    expect(CAMERA.near).toBe(0.1);
    expect(CAMERA.far).toBe(100);
    expect(CAMERA.far).toBeGreaterThan(CAMERA.near);
    expect(CAMERA.near).toBeGreaterThan(0);
  });
});

describe('POST_FX', () => {
  it('keeps tone mapping exposure within the documented tuning range', () => {
    expect(POST_FX.toneMappingExposure).toBe(1.45);
    expect(POST_FX.toneMappingExposure).toBeGreaterThanOrEqual(1.4);
    expect(POST_FX.toneMappingExposure).toBeLessThanOrEqual(1.9);
  });

  it('uses a gentler bloom intensity for points mode than mesh mode', () => {
    expect(POST_FX.bloom).toEqual({
      intensity: 2.5,
      luminanceThreshold: 1.0,
      luminanceSmoothing: 0.9,
    });
    expect(POST_FX.bloomPoints).toEqual({
      intensity: 0.72,
      luminanceThreshold: 1.08,
      luminanceSmoothing: 0.28,
    });
    expect(POST_FX.bloomPoints.intensity).toBeLessThan(POST_FX.bloom.intensity);
  });

  it('defines the film grade values', () => {
    expect(POST_FX.grade.contrast).toBe(1.06);
    expect(POST_FX.grade.shadowTint).toEqual([0.42, 0.52, 0.55]);
    expect(POST_FX.grade.highTint).toEqual([0.52, 0.5, 0.44]);
    expect(POST_FX.grade.balance).toBe(-0.08);
    expect(POST_FX.grade.vibrance).toBe(0.21);
  });

  it('keeps shadow and highlight tints luma-neutral (Rec.709 near 0.5)', () => {
    const luma = ([r, g, b]: [number, number, number]) =>
      0.2126 * r + 0.7152 * g + 0.0722 * b;
    expect(luma(POST_FX.grade.shadowTint)).toBeCloseTo(0.5, 2);
    expect(luma(POST_FX.grade.highTint)).toBeCloseTo(0.5, 2);
  });

  it('frames the void more strongly in points mode', () => {
    expect(POST_FX.vignette).toEqual({ offset: 0.28, darkness: 0.62 });
    expect(POST_FX.vignettePoints).toEqual({ offset: 0.32, darkness: 0.76 });
    expect(POST_FX.vignettePoints.darkness).toBeGreaterThan(POST_FX.vignette.darkness);
  });

  it('configures chromatic aberration and noise', () => {
    expect(POST_FX.chromaticAberration.offset).toEqual([0.00055, 0.00055]);
    expect(POST_FX.noise.opacity).toBe(0.025);
  });
});
