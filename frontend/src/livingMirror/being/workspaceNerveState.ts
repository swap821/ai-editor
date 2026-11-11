import { BufferAttribute, BufferGeometry, Color, Vector3, type Mesh, type Points, type ShaderMaterial } from 'three';
import { deriveOrganMaterialState } from '../../superbrain/lib/organMaterialState';

/** Bounded GPU resources owned by the existing connection projection. */
export function createWorkspaceNerve() {
  const radial = 8, segments = 48;
  const vertices = new Float32Array((segments + 1) * (radial + 1) * 3);
  const indices: number[] = [];
  for (let i = 0; i <= segments; i++) for (let j = 0; j <= radial; j++) {
    const index = (i * (radial + 1) + j) * 3, angle = j / radial * Math.PI * 2;
    vertices[index] = i / segments; vertices[index + 1] = Math.cos(angle); vertices[index + 2] = Math.sin(angle);
    if (i < segments && j < radial) {
      const a = i * (radial + 1) + j, b = a + radial + 1;
      indices.push(a, b, a + 1, b, b + 1, a + 1);
    }
  }
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new BufferAttribute(vertices, 3)); geometry.setIndex(indices);
  const dust = new Float32Array(600 * 3);
  let seed=8271;
  const random=()=>{seed=Math.imul(seed,1664525)+1013904223|0;return (seed>>>0)/4294967296;};
  for(let i=0;i<600;i++){dust[i*3]=random();dust[i*3+1]=random()*Math.PI*2;dust[i*3+2]=random();}
  const particles=new BufferGeometry(); particles.setAttribute('position',new BufferAttribute(dust,3));
  const palette = deriveOrganMaterialState({ kind: 'content', focused: true }).palette;
  return { geometry, particles, mesh: null as Mesh | null, points: null as Points | null, material: null as ShaderMaterial | null, dustMaterial:null as ShaderMaterial|null,
    uniforms: { p0: { value: new Vector3() }, p1: { value: new Vector3() }, p2: { value: new Vector3() }, p3: { value: new Vector3() },
      radius: { value: 0 }, reach: { value: 0 }, dpr:{value:1}, breath:{value:.5}, signal:{value:-1}, color: { value: new Color(palette.reach) } } };
}
export type WorkspaceNerveState = ReturnType<typeof createWorkspaceNerve>;
