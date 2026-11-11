import { useCallback } from 'react';
import { AdditiveBlending, type BufferAttribute, type Points, type ShaderMaterial } from 'three';
import type { WorkspaceRimState } from './workspaceRim';

const vertexShader=`
  attribute vec2 aData; attribute vec2 aOutward; attribute float aReturnAlpha;
  uniform float uUnfurl; uniform float uOrigin; uniform float uVisible; uniform float uDpr;
  uniform vec2 uViewport;
  uniform float uReturning; uniform float uReturnTime;
  varying float vAlpha; varying float vTint;
  void main() {
    float separation=abs(aData.x-uOrigin);
    float travel=min(separation,1.0-separation)*2.0;
    float spread=1.0-pow(1.0-uUnfurl,3.0);
    float born=smoothstep(travel*.82,travel*.82+.18,spread);
    float settle=smoothstep(0.0,.20,spread-travel*.82);
    vec2 pixel=position.xy+aOutward*(1.0-settle)*10.0*(1.0-uReturning);
    gl_Position=vec4(pixel.x/uViewport.x*2.0-1.0,1.0-pixel.y/uViewport.y*2.0,0.0,1.0);
    gl_PointSize=(2.1+1.9*aData.y)*uDpr;
    vAlpha=uVisible*born*(.38+.46*aData.y+.32*(1.0-settle));
    if(uReturning>.5) vAlpha=uVisible*aReturnAlpha*(1.0-step(1.0,uReturnTime));
    vTint=aData.y;
  }
`;
const fragmentShader=`
  uniform vec3 uReachColor; uniform vec3 uLiveColor;
  varying float vAlpha; varying float vTint;
  void main() {
    float d=length(gl_PointCoord-.5)*2.0;
    if(d>1.0||vAlpha<.002) discard;
    float soft=.72*(1.0-smoothstep(.10,.58,d))+.28*pow(1.0-d,1.5);
    vec3 color=mix(uReachColor,uLiveColor,smoothstep(.68,1.0,vTint)*.68);
    gl_FragColor=vec4(color,vAlpha*soft);
    #include <tonemapping_fragment>
    #include <colorspace_fragment>
  }
`;
function skipRaycast() {}

/** Decorative tissue inside the existing canvas. R3F owns GPU disposal;
 * projection owns the reusable geometry/uniform slots and visibility. */
export function WorkspaceRimPoints({state}:{state:WorkspaceRimState}) {
  const bindPoints=useCallback((points:Points|null)=>{state.points=points;if(points)points.visible=false;},[state]);
  const bindPosition=useCallback((attribute:BufferAttribute|null)=>{state.positionAttribute=attribute;},[state]);
  const bindNormal=useCallback((attribute:BufferAttribute|null)=>{state.normalAttribute=attribute;},[state]);
  const bindMaterial=useCallback((material:ShaderMaterial|null)=>{state.material=material;},[state]);
  const bindReturnAlpha=useCallback((attribute:BufferAttribute|null)=>{state.returnAlphaAttribute=attribute;},[state]);
  return <points ref={bindPoints} name="workspace-contact-rim" frustumCulled={false} renderOrder={200} raycast={skipRaycast}>
    <bufferGeometry>
      <bufferAttribute ref={bindPosition} attach="attributes-position" args={[state.positions,3]} />
      <bufferAttribute ref={bindNormal} attach="attributes-aOutward" args={[state.normals,2]} />
      <bufferAttribute attach="attributes-aData" args={[state.data,2]} />
      <bufferAttribute ref={bindReturnAlpha} attach="attributes-aReturnAlpha" args={[state.returnAlpha,1]} />
    </bufferGeometry>
    <shaderMaterial ref={bindMaterial} uniforms={state.uniforms} vertexShader={vertexShader} fragmentShader={fragmentShader}
      transparent depthTest={false} depthWrite={false} blending={AdditiveBlending} />
  </points>;
}
