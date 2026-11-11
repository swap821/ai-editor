import { useCallback, useEffect } from 'react';
import { AdditiveBlending, DoubleSide, ShaderMaterial, type Mesh, type Points } from 'three';
import type { WorkspaceNerveState } from './workspaceNerveState';

const vertex = `
uniform vec3 p0, p1, p2, p3;
uniform float radius;
varying float vT; varying float vSide;
void main() {
  float t=position.x, q=1.0-t;
  vec3 p=q*q*q*p0+3.0*q*q*t*p1+3.0*q*t*t*p2+t*t*t*p3;
  vec3 tangent=3.0*q*q*(p1-p0)+6.0*q*t*(p2-p1)+3.0*t*t*(p3-p2);
  vec3 pview=(viewMatrix*vec4(p,1.0)).xyz;
  vec3 dir=normalize((viewMatrix*vec4(tangent,0.0)).xyz+vec3(0.000001));
  vec3 normal=normalize(cross(dir,vec3(0.0,0.0,1.0))+vec3(0.000001));
  vec3 binormal=normalize(cross(dir,normal));
  pview+=radius*(normal*position.y+binormal*position.z);
  vT=t; vSide=position.y;
  gl_Position=projectionMatrix*vec4(pview,1.0);
}`;
const fragment = `
uniform vec3 color; uniform float reach, breath, signal;
varying float vT; varying float vSide;
void main() {
  if (vT > reach) discard;
  float fade=smoothstep(0.0,.06,vT)*smoothstep(0.0,.06,reach-vT);
  float band=signal<0.0?0.0:1.0-smoothstep(.025,.14,abs(vT-signal));
  float fibers=(.08+.15*pow(abs(vSide),2.0))*(1.0+.55*band);
  gl_FragColor=vec4(color,fade*fibers*(.82+.36*breath));
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
}`;
const particleVertex = `
uniform vec3 p0,p1,p2,p3; uniform float radius,dpr,breath;
varying float vT; varying float vSeed;
void main() {
  // Reversible secondary motion shares the body's breath. Seeded particles
  // move both ways, so this cannot be mistaken for task progress.
  float restingT=position.x;
  float t=clamp(restingT+.07*(breath-.5)*sin(6.28318*position.z)*sin(3.14159*restingT),0.0,1.0);
  float q=1.0-t;
  vec3 p=q*q*q*p0+3.0*q*q*t*p1+3.0*q*t*t*p2+t*t*t*p3;
  vec3 tangent=3.0*q*q*(p1-p0)+6.0*q*t*(p2-p1)+3.0*t*t*(p3-p2);
  vec3 dir=normalize((viewMatrix*vec4(tangent,0.0)).xyz+vec3(0.000001));
  vec3 normal=normalize(cross(dir,vec3(0.0,0.0,1.0))+vec3(0.000001));
  vec3 binormal=normalize(cross(dir,normal));
  vec3 pview=(viewMatrix*vec4(p,1.0)).xyz;
  float spread=radius*(.6+position.z*3.6)*sin(3.14159*t)*(.82+.36*breath);
  float angle=position.y+.45*(breath-.5)*sin(6.28318*t);
  pview+=spread*(normal*cos(angle)+binormal*sin(angle));
  gl_Position=projectionMatrix*vec4(pview,1.0);
  gl_PointSize=(1.2+1.7*position.z)*dpr;
  vT=t;vSeed=position.z;
}`;
const particleFragment=`
uniform vec3 color; uniform float reach,breath,signal;
varying float vT; varying float vSeed;
void main(){
  if(vT>reach)discard;
  float d=length(gl_PointCoord-.5)*2.0;if(d>1.0)discard;
  float fade=smoothstep(0.0,.06,vT)*smoothstep(0.0,.06,reach-vT);
  float band=signal<0.0?0.0:1.0-smoothstep(.025,.14,abs(vT-signal));
  gl_FragColor=vec4(color,fade*(.20+.38*vSeed)*(1.0-smoothstep(.1,1.0,d))*(.82+.36*breath)*(1.0+.45*band));
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
}`;
function noRaycast() {}
export function WorkspaceNerve({ state }: {state:WorkspaceNerveState}) {
  const bindMesh=useCallback((mesh:Mesh|null)=>{state.mesh=mesh;if(mesh)mesh.visible=false;},[state]);
  const bindPoints=useCallback((points:Points|null)=>{state.points=points;if(points)points.visible=false;},[state]);
  const bindMaterial=useCallback((material:ShaderMaterial|null)=>{state.material=material;},[state]);
  const bindDustMaterial=useCallback((material:ShaderMaterial|null)=>{state.dustMaterial=material;},[state]);
  useEffect(()=>()=>{state.geometry.dispose();state.particles.dispose();},[state]);
  return <><mesh ref={bindMesh} geometry={state.geometry} name="workspace-nerve" frustumCulled={false} renderOrder={190} raycast={noRaycast}>
    <shaderMaterial ref={bindMaterial} uniforms={state.uniforms} vertexShader={vertex} fragmentShader={fragment}
      transparent depthTest={false} depthWrite={false} side={DoubleSide}/>
  </mesh><points ref={bindPoints} geometry={state.particles} name="workspace-nerve-fibers" frustumCulled={false} renderOrder={191} raycast={noRaycast}>
    <shaderMaterial ref={bindDustMaterial} uniforms={state.uniforms} vertexShader={particleVertex} fragmentShader={particleFragment}
      transparent depthTest={false} depthWrite={false} blending={AdditiveBlending}/>
  </points></>;
}
