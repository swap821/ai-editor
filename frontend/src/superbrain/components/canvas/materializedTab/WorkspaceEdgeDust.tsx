import { forwardRef, useEffect, useMemo } from 'react';
import { useThree } from '@react-three/fiber';
import * as THREE from 'three';

/** Sparse points outside a waiting workspace; they carry no activity state. */
export const WorkspaceEdgeDust = forwardRef<THREE.ShaderMaterial,{shape:THREE.Shape;depth:number;reach:THREE.Color;live:THREE.Color}>(({shape,depth,reach,live},ref)=>{
  const dpr=useThree(state=>state.viewport.dpr);
  const geometry=useMemo(()=>{
    const outline=shape.getSpacedPoints(143);
    const positions=new Float32Array(outline.length*3),weights=new Float32Array(outline.length);
    for(let i=0;i<outline.length;i++){
      const point=outline[i],jitter=1.014+((i*37)%11)*0.002;
      positions[i*3]=point.x*jitter;positions[i*3+1]=point.y*jitter;positions[i*3+2]=depth+0.018;
      weights[i]=0.35+((i*47)%17)/26;
    }
    const result=new THREE.BufferGeometry();
    result.setAttribute('position',new THREE.BufferAttribute(positions,3));
    result.setAttribute('weight',new THREE.BufferAttribute(weights,1));
    return result;
  },[shape,depth]);
  useEffect(()=>()=>geometry.dispose(),[geometry]);
  const uniforms=useMemo(()=>({uReach:{value:reach},uLive:{value:live},uDpr:{value:dpr},uGain:{value:0},uBreath:{value:0.5}}),[reach,live,dpr]);
  return <points name="waiting-workspace-edge" geometry={geometry} raycast={()=>undefined} renderOrder={10}>
    <shaderMaterial ref={ref} uniforms={uniforms} transparent depthWrite={false} blending={THREE.AdditiveBlending}
      vertexShader={`attribute float weight; varying float vWeight; uniform float uDpr; uniform float uGain;
        void main(){vWeight=weight;vec4 mv=modelViewMatrix*vec4(position,1.0);
          gl_Position=projectionMatrix*mv;gl_PointSize=(1.15+weight*0.85)*uDpr*sqrt(max(uGain,0.0));}`}
      fragmentShader={`varying float vWeight;uniform vec3 uReach;uniform vec3 uLive;uniform float uGain;uniform float uBreath;
        void main(){float d=length(gl_PointCoord-vec2(0.5));float alpha=(1.0-smoothstep(0.12,0.5,d))*vWeight*0.52*uGain*(0.94+0.12*clamp(uBreath,0.0,1.0));
          gl_FragColor=vec4(mix(uReach,uLive,0.24+vWeight*0.25),alpha);}`}/>
  </points>;
});
