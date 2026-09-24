/**
 * Update a Drei Line without replacing its geometry every frame.
 *
 * Drei's <Line> owns a LineGeometry, which stores each adjacent point pair in
 * interleaved instanceStart/instanceEnd attributes. Calling
 * BufferGeometry.setFromPoints() against that object makes Three warn and
 * reallocates a mismatched position buffer. The normal path mutates the
 * existing bounded segment pool and refreshes its bounds; the fallback is only
 * for a future line implementation with a different geometry contract.
 */
export function updateLineGeometryPoints(geometry, points) {
  const start = geometry?.attributes?.instanceStart;
  const end = geometry?.attributes?.instanceEnd;
  const segmentCount = Math.max(0, points.length - 1);
  if (start && end && start.count >= segmentCount && end.count >= segmentCount) {
    for (let index = 0; index < segmentCount; index += 1) {
      const from = points[index];
      const to = points[index + 1];
      start.setXYZ(index, from.x, from.y, from.z);
      end.setXYZ(index, to.x, to.y, to.z);
    }
    if (start.data) start.data.needsUpdate = true;
    if (end.data) end.data.needsUpdate = true;
    geometry.computeBoundingBox?.();
    geometry.computeBoundingSphere?.();
    return true;
  }

  // This branch is not used by the current Drei Line implementation. It
  // re-seeds a compatible LineGeometry once, so subsequent frames take the
  // pooled path above instead of repeatedly invoking setFromPoints().
  if (typeof geometry?.setPositions === 'function') {
    const flat = new Float32Array(points.length * 3);
    for (let index = 0; index < points.length; index += 1) {
      const point = points[index];
      const offset = index * 3;
      flat[offset] = point.x;
      flat[offset + 1] = point.y;
      flat[offset + 2] = point.z;
    }
    geometry.setPositions(flat);
    return true;
  }

  const position = geometry?.attributes?.position;
  if (position && position.count >= points.length) {
    for (let index = 0; index < points.length; index += 1) {
      const point = points[index];
      position.setXYZ(index, point.x, point.y, point.z);
    }
    position.needsUpdate = true;
    geometry.computeBoundingBox?.();
    geometry.computeBoundingSphere?.();
    return true;
  }

  return false;
}
