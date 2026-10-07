import { describe, expect, it } from 'vitest';
import { Matrix4, PerspectiveCamera, Vector3 } from 'three';
import { projectWorkspaceConnection } from './workspaceConnection';

const camera = new PerspectiveCamera(90, 1, 0.1, 100);
camera.position.set(0, 0, 10);
camera.updateMatrixWorld();
const canvas = { left: 100, top: 50, width: 400, height: 400 };
const plane = { left: 600, top: 100, width: 600, height: 600 };
const overlay = { left: 20, top: 10, width: 1200, height: 800 };

describe('workspace connection projection', () => {
  it('joins the transformed body anchor to the outer workplane edge in CSS pixels', () => {
    // Removing either the live body transform or canvas offset must break this.
    const connection = projectWorkspaceConnection({
      origin: new Vector3(0, 0, 0),
      bodyWorld: new Matrix4().makeTranslation(2, 0, 0),
      dockScale: 0.5, camera, canvas, plane, overlay,
    });
    expect(connection?.source.x).toBeCloseTo(320);
    expect(connection?.source.y).toBeCloseTo(240);
    expect(connection?.target).toEqual({ x: 578, y: 240 });
    expect(connection?.path).toMatch(/^M 320 240 C /);
  });
  it('applies dock scale without moving the published body translation', () => {
    const connection = projectWorkspaceConnection({
      origin: new Vector3(2, 0, 0), bodyWorld: new Matrix4().makeTranslation(2, 0, 0),
      dockScale: 0.5, camera, canvas, plane, overlay,
    });
    expect(connection?.source).toEqual({ x: 340, y: 240 });
  });
  it('meets the mobile plane above its reading content, rather than drawing across it', () => {
    const connection = projectWorkspaceConnection({
      origin: new Vector3(0, 0, 0), bodyWorld: new Matrix4(), dockScale: 1, camera,
      canvas: { left: 0, top: 100, width: 320, height: 180 },
      plane: { left: 12, top: 300, width: 296, height: 200 },
      overlay: { left: 0, top: 0, width: 320, height: 568 },
    });
    expect(connection?.source).toEqual({ x: 160, y: 190 });
    expect(connection?.target).toEqual({ x: 160, y: 298 });
    expect(connection?.path).toBe('M 160 190 C 160 244, 160 244, 160 298');
  });
  it.each([
    ['behind the camera', new Vector3(0, 0, 20)],
    ['outside the scene', new Vector3(30, 0, 0)],
    ['invalid coordinates', new Vector3(NaN, 0, 0)],
  ])('hides an anchor %s instead of clamping it into a fake socket', (_label, origin) => {
    expect(projectWorkspaceConnection({ origin, bodyWorld: new Matrix4(), dockScale: 1, camera, canvas, plane, overlay })).toBeNull();
  });
  it('hides a socket occluded by the DOM plane or without a measured layout', () => {
    const input = { origin: new Vector3(), bodyWorld: new Matrix4(), dockScale: 1, camera, canvas, plane, overlay };
    expect(projectWorkspaceConnection({ ...input, plane: { left: 100, top: 100, width: 400, height: 400 } })).toBeNull();
    expect(projectWorkspaceConnection({ ...input, canvas: { ...canvas, height: 0 } })).toBeNull();
  });
});
