import { TubeGeometry, Vector3, type Curve } from 'three';

// Sampling arithmetic follows Three.js TubeGeometry (MIT).
// Copyright © 2010-2026 three.js authors.
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the "Software"), to deal
// in the Software without restriction, including without limitation the rights
// to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
// copies of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:
// The above copyright notice and this permission notice shall be included in
// all copies or substantial portions of the Software.
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
// IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
// AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
// OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
// THE SOFTWARE.

const scratch = new WeakMap<TubeGeometry, { point: Vector3; normal: Vector3 }>();

/** Retarget one owned tube without replacing its topology or GPU buffers. */
export function retargetTubeGeometry(geometry: TubeGeometry, path: Curve<Vector3>, radius: number): void {
  const { tubularSegments, radialSegments, closed } = geometry.parameters;
  let vectors = scratch.get(geometry);
  if (!vectors) {
    vectors = { point: new Vector3(), normal: new Vector3() };
    scratch.set(geometry, vectors);
  }
  const frames = path.computeFrenetFrames(tubularSegments, closed);
  geometry.tangents = frames.tangents;
  geometry.normals = frames.normals;
  geometry.binormals = frames.binormals;
  const position = geometry.getAttribute('position');
  const normals = geometry.getAttribute('normal');
  let vertex = 0;
  for (let row = 0; row <= tubularSegments; row++) {
    const segment = closed && row === tubularSegments ? 0 : row;
    const point = path.getPointAt(segment / tubularSegments, vectors.point);
    const n = frames.normals[segment], b = frames.binormals[segment];
    for (let radial = 0; radial <= radialSegments; radial++, vertex++) {
      const angle = radial / radialSegments * Math.PI * 2;
      const sin = Math.sin(angle), cos = -Math.cos(angle);
      const normal = vectors.normal.set(cos * n.x + sin * b.x, cos * n.y + sin * b.y, cos * n.z + sin * b.z).normalize();
      normals.setXYZ(vertex, normal.x, normal.y, normal.z);
      position.setXYZ(vertex, point.x + radius * normal.x, point.y + radius * normal.y, point.z + radius * normal.z);
    }
  }
  // Keep the public path metadata used by beads/inspection accurate as well.
  Object.assign(geometry.parameters, { path, radius });
  position.needsUpdate = true;
  normals.needsUpdate = true;
  // Three caches these lazily. Existing raycast/culling bounds must follow the
  // changed vertices; leave unrequested bounds lazy, as a fresh tube would.
  if (geometry.boundingBox) geometry.computeBoundingBox();
  if (geometry.boundingSphere) geometry.computeBoundingSphere();
}
