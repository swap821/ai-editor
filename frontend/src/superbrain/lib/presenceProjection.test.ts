import { describe, expect, it } from 'vitest';
import { PerspectiveCamera } from 'three';
import {
  createSettledPresenceProjection,
  setPresenceDestination,
  clearPresenceDestination,
  getPresenceDestination,
} from './presenceProjection';

describe('presence projection', () => {
  it('stores frames per camera and removes them independently', () => {
    const first = new PerspectiveCamera();
    const second = new PerspectiveCamera();
    const frame = {
      width: 1200,
      height: 800,
      x: 100,
      y: 50,
      stageWidth: 600,
      stageHeight: 400,
    };

    const secondFrame = {
      width: 640,
      height: 480,
      x: 0,
      y: 0,
      stageWidth: 320,
      stageHeight: 240,
    };

    setPresenceDestination(first, frame);
    expect(getPresenceDestination(first)).toBe(frame);
    expect(getPresenceDestination(second)).toBeUndefined();

    setPresenceDestination(second, secondFrame);
    expect(getPresenceDestination(second)).toBe(secondFrame);

    clearPresenceDestination(first);
    expect(getPresenceDestination(first)).toBeUndefined();
    expect(getPresenceDestination(second)).toBe(secondFrame);
  });

  it('returns the installed matrix when no destination is set', () => {
    const camera = new PerspectiveCamera();
    const project = createSettledPresenceProjection();

    expect(project(camera)).toBe(camera.projectionMatrix);
  });

  it('calculates destination framing while preserving the camera depth row', () => {
    const camera = new PerspectiveCamera(45, 1.5, 0.5, 500);
    camera.zoom = 1.25;
    camera.filmOffset = 3;
    camera.updateProjectionMatrix();
    const source = camera.projectionMatrix.elements;
    source[2] = 0.1;
    source[6] = 0.2;
    source[10] = 0.3;
    source[14] = 0.4;
    const original = source.slice();

    const frame = {
      width: 1200,
      height: 800,
      x: 100,
      y: 50,
      stageWidth: 600,
      stageHeight: 400,
    };
    setPresenceDestination(camera, frame);

    const expected = new PerspectiveCamera(45, 1, 0.5, 500);
    expected.zoom = camera.zoom;
    expected.filmGauge = camera.filmGauge;
    expected.filmOffset = camera.filmOffset;
    expected.coordinateSystem = camera.coordinateSystem;
    expected.setViewOffset(
      frame.width,
      frame.height,
      frame.x,
      frame.y,
      frame.stageWidth,
      frame.stageHeight,
    );
    const expectedElements = expected.projectionMatrix.elements.slice();
    for (const index of [2, 6, 10, 14]) {
      expectedElements[index] = original[index];
    }

    const result = createSettledPresenceProjection()(camera);
    expect(result.elements).toEqual(expectedElements);
    expect(result).not.toBe(camera.projectionMatrix);
    expect(camera.projectionMatrix.elements).toEqual(original);
  });
});
