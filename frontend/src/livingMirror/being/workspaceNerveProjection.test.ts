import { describe, expect, it } from 'vitest';
import { PerspectiveCamera, Vector3 } from 'three';
import { createNerveProjection, projectNerveWorld, nerveVisibleReach } from './workspaceNerveProjection';

const canvas={left:100,top:50,width:400,height:400};
const overlay={left:20,top:10,width:1200,height:800};
const connection={source:{x:280,y:240},target:{x:578,y:240},horizontal:true,middle:429,
  path:'M 280 240 C 429 220, 429 220, 578 240'};
const camera=new PerspectiveCamera(55,1,.1,100);
camera.position.set(0,0,10);camera.updateMatrixWorld();camera.updateProjectionMatrix();
const z=new Vector3(0,0,0).project(camera).z;

describe('workspace nerve world projection',()=>{
  it('projects the same cubic as the live SVG, including on a different narrow canvas',()=>{
    for(const rect of [canvas,{left:0,top:80,width:320,height:240}]){
      const state=createNerveProjection();
      expect(projectNerveWorld(state,connection,rect,overlay,camera,z,1)).toBe(true);
      for(const t of [0,.15,.5,.85,1]){
        const q=1-t, v=new Vector3().addScaledVector(state.p0,q*q*q).addScaledVector(state.p1,3*q*q*t)
          .addScaledVector(state.p2,3*q*t*t).addScaledVector(state.p3,t*t*t).project(camera);
        const x=rect.left+(v.x+1)*rect.width/2-overlay.left;
        const y=rect.top+(1-v.y)*rect.height/2-overlay.top;
        expect(x).toBeCloseTo(q*q*q*280+3*q*q*t*429+3*q*t*t*429+t*t*t*578,5);
        expect(y).toBeCloseTo(q*q*q*240+3*q*q*t*220+3*q*t*t*220+t*t*t*240,5);
      }
      expect(state.radius).toBeGreaterThan(0);
    }
  });
  it('fails closed on invalid camera depth, viewport, DPR and degenerate endpoints',()=>{
    const s=createNerveProjection();
    expect(projectNerveWorld(s,connection,canvas,overlay,camera,NaN,1)).toBe(false);
    expect(projectNerveWorld(s,connection,{...canvas,width:0},overlay,camera,z,1)).toBe(false);
    expect(projectNerveWorld(s,connection,canvas,overlay,camera,z,0)).toBe(false);
    expect(projectNerveWorld(s,{...connection,target:connection.source},canvas,overlay,camera,z,1)).toBe(false);
  });
  it('matches the visible SVG extent during birth and retirement',()=>{
    expect(nerveVisibleReach(.25,false,0)).toBeGreaterThan(.25);
    expect(nerveVisibleReach(0,false,0)).toBe(.03);
    expect(nerveVisibleReach(1,false,0)).toBe(1);
    expect(nerveVisibleReach(1,true,.25)).toBe(.75);
    expect(nerveVisibleReach(1,true,1)).toBe(0);
    expect(nerveVisibleReach(1,true,0,.42)).toBe(.42);
    expect(nerveVisibleReach(1,true,.5,.42)).toBeCloseTo(.21);
    expect(nerveVisibleReach(1,true,1,.42)).toBe(0);
  });
});
