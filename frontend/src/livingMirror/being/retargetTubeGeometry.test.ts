import { BufferAttribute, CatmullRomCurve3, TubeGeometry, Vector3 } from 'three';
import { expect, it } from 'vitest';
import { retargetTubeGeometry } from '../../superbrain/lib/retargetTubeGeometry';

it.each([
  [false, false], [false, true], [true, false], [true, true],
] as const)('matches fresh Three.js sampling while retaining buffers (closed=%s, cachedBounds=%s)', (closed, cachedBounds) => {
  const curve = (offset: number) => new CatmullRomCurve3([
    new Vector3(-1 + offset, -2, 0.2), new Vector3(0.3, -0.4 + offset, -0.6),
    new Vector3(1.1, 1.2, offset), new Vector3(-0.4, 2.1, 0.8),
  ], closed);
  const geometry = new TubeGeometry(curve(0), 32, 0.018, 10, closed);
  const attributes = ['position', 'normal', 'uv'].map(name => geometry.getAttribute(name));
  const buffers = attributes.map(attribute => attribute.array);
  const index = geometry.getIndex()!, indexBuffer = index.array;
  const uv = attributes[2];
  if (!(uv instanceof BufferAttribute)) throw new Error('TubeGeometry must own a non-interleaved UV buffer');
  const uvVersion = uv.version, indexVersion = index.version;
  if (cachedBounds) { geometry.computeBoundingBox(); geometry.computeBoundingSphere(); }
  try {
    for (const [offset, radius] of [[0.4, 0.029], [-0.7, 0.009], [0.2, 0.018]]) {
      const path = curve(offset);
      retargetTubeGeometry(geometry, path, radius);
      const reference = new TubeGeometry(path, 32, radius, 10, closed);
      try {
        expect(geometry.parameters.path).toBe(path);
        expect(geometry.parameters.radius).toBe(radius);
        for (const [at, name] of ['position', 'normal', 'uv'].entries()) {
          const actual = geometry.getAttribute(name);
          expect(actual).toBe(attributes[at]);
          expect(actual.array).toBe(buffers[at]);
          expect(Array.from(actual.array)).toEqual(Array.from(reference.getAttribute(name).array));
        }
        expect(geometry.getIndex()).toBe(index);
        expect(index.array).toBe(indexBuffer);
        expect(Array.from(index.array)).toEqual(Array.from(reference.getIndex()!.array));
        expect(geometry.tangents).toEqual(reference.tangents);
        expect(geometry.normals).toEqual(reference.normals);
        expect(geometry.binormals).toEqual(reference.binormals);
        expect(uv.version).toBe(uvVersion);
        expect(index.version).toBe(indexVersion);
        if (cachedBounds) {
          reference.computeBoundingBox(); reference.computeBoundingSphere();
          expect(geometry.boundingBox).toEqual(reference.boundingBox);
          expect(geometry.boundingSphere).toEqual(reference.boundingSphere);
        } else {
          expect(geometry.boundingBox).toBeNull(); expect(geometry.boundingSphere).toBeNull();
        }
      } finally { reference.dispose(); }
    }
  } finally { geometry.dispose(); }
});
