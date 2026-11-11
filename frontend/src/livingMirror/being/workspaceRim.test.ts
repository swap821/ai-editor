import { describe, expect, it } from 'vitest';
import { Vector2 } from 'three';
import { createWorkspaceRimState, sampleWorkspaceRim, writeWorkspaceRimState, writeWorkspaceRimReturn, type WorkspaceRimLayout } from './workspaceRim';

const layout: WorkspaceRimLayout = { canvas: { left:100,top:50,width:1200,height:800 },
  overlay: { left:20,top:10,width:1280,height:900 }, plane: { left:600,top:100,width:600,height:600 },
  radius:12,occluders:[],decision:false,targetId:'result-1' };
const owner = { id:'result-1',kind:'content' as const,lifecycle:'unfurling' as const,phaseStartedAt:2400 };
const contact = {x:578,y:268}; // actual left-2 edge, in overlay coordinates

describe('contact-fed readable workspace rim',()=>{
  it('refreshes captured live-edge paint when its real contact moves, including the original shader residual loft',()=>{
    const state=createWorkspaceRimState(),live={...owner,lifecycle:'live' as const};
    writeWorkspaceRimState(state,live,3000,false,layout,contact,1);
    const peak=Math.max(...state.birthLift),index=state.birthLift.indexOf(peak);
    expect(peak).toBeGreaterThan(.1);
    writeWorkspaceRimState(state,live,3016,false,layout,{x:768,y:88},1);
    expect(state.birthLift[index]).toBe(0);
    expect(Math.max(...state.birthLift)).toBeGreaterThan(.1);
    expect(state.paintedCount).toBe(2400);
  });
  it('returns the same seeded tissue around its perimeter and along the visible cubic, then restores it for Reopen',()=>{
    const state=createWorkspaceRimState();
    writeWorkspaceRimState(state,{...owner,lifecycle:'live'},2600,false,layout,contact,1);
    const positions=state.positions,base=positions.slice(),painted=base.slice(),revision=state.revision;
    // Even at full unfurl the original shader retains a small far-edge
    // loft. Compare painted positions, not only its unlifted CPU base buffer.
    for(let i=0;i<state.offset.length;i++) {
      const separation=Math.abs(state.data[i*2]-state.uniforms.uOrigin.value),travel=Math.min(separation,1-separation)*2;
      const t=Math.min(1,Math.max(0,(1-travel*.82)/.20)),lift=(1-t*t*(3-2*t))*10;
      painted[i*3]+=state.normals[i*2]*lift;painted[i*3+1]+=state.normals[i*2+1]*lift;
    }
    const retiring=Object.freeze({...owner,lifecycle:'retracting' as const,phaseStartedAt:3000});
    const connection={source:{x:280,y:200},target:contact,horizontal:true,middle:429,path:'M 280 200 C 429 180, 429 248, 578 268'};
    expect(writeWorkspaceRimReturn(state,retiring,3000,layout,connection)).toBe(true);
    for(let i=0;i<base.length;i++)expect(Math.abs(positions[i]-painted[i])).toBeLessThan(.0001);
    writeWorkspaceRimReturn(state,retiring,3650,layout,connection);
    expect(state.positions).toBe(positions);expect(state.revision).toBe(revision);
    let carriers=0,carrierAlpha=0;const outerReach=Math.max(...state.offset);
    for(let i=0;i<state.returnAlpha.length;i++) {
      const x=positions[i*3],y=positions[i*3+1];expect(Number.isFinite(x+y+positions[i*3+2])).toBe(true);
      expect(state.returnAlpha[i]).toBeGreaterThanOrEqual(0);expect(state.returnAlpha[i]).toBeLessThanOrEqual(1);
      // Interior of the socket-side gap can contain only points on the
      // actual visible cubic, never a straight chord from a distant edge.
      if(state.returnAlpha[i]>.01&&x<state.rect.x-outerReach-.01) {
        carriers++;carrierAlpha+=state.returnAlpha[i];let distance=Infinity;
        for(let n=0;n<=256;n++) {
          const t=n/256,q=1-t;
          const cx=q*q*q*200+3*q*q*t*349+3*q*t*t*349+t*t*t*498;
          const cy=q*q*q*160+3*q*q*t*140+3*q*t*t*208+t*t*t*228;
          distance=Math.min(distance,Math.hypot(x-cx,y-cy));
        }
        expect(distance,JSON.stringify({i,x,y,left:state.rect.x,offset:state.offset[i]})).toBeLessThan(1);
      }
    }
    expect(carriers).toBeGreaterThan(0);
    // Packing a broad envelope onto a short nerve must not multiply its
    // light density into a solid beam. Preserve all points, budget opacity.
    expect(carrierAlpha/Math.hypot(298,68)).toBeLessThanOrEqual(2);
    expect(retiring.phaseStartedAt).toBe(3000);
    writeWorkspaceRimState(state,{...owner,lifecycle:'reaching',phaseStartedAt:4000},4000,false,layout,contact,1);
    expect(state.uniforms.uReturning.value).toBe(0);expect(state.uniforms.uVisible.value).toBe(0);
    expect(state.positions).toBe(positions);expect(Array.from(positions)).toEqual(Array.from(base));
  });
  it.each([
    { ...layout,occluders:[{left:590,top:100,width:100,height:100}] },
    { ...layout,decision:true,targetId:'approval' },
    { ...layout,canvas:{...layout.canvas,width:0} },
    { ...layout,radius:NaN },
  ])('observes a new reaching epoch while paint is suppressed, then grows its own unfurl',hidden=>{
    const state=createWorkspaceRimState();
    writeWorkspaceRimState(state,{...owner,lifecycle:'reaching'},2410,true,layout,contact,1);
    writeWorkspaceRimState(state,{...owner,lifecycle:'reaching',phaseStartedAt:3000},3010,false,hidden,contact,1);
    expect(state.uniforms.uVisible.value).toBe(0);
    writeWorkspaceRimState(state,{...owner,phaseStartedAt:3900},4030,false,layout,contact,1);
    expect(state.uniforms.uUnfurl.value).toBe(.25);
  });
  it.each(['reaching','unfurling'] as const)('does not rewind the same %s gesture after a short presentation hold',lifecycle=>{
    const state=createWorkspaceRimState(), record=Object.freeze({...owner,lifecycle});
    writeWorkspaceRimState(state,record,2410,true,layout,contact,1);
    expect(state.uniforms.uUnfurl.value).toBe(1);
    writeWorkspaceRimState(state,record,2420,false,layout,contact,1);
    expect(state.uniforms.uUnfurl.value).toBe(1);
    expect(state.uniforms.uVisible.value).toBe(1);
    if(lifecycle==='reaching') {
      writeWorkspaceRimState(state,{...record,lifecycle:'unfurling',phaseStartedAt:2430},2440,false,layout,contact,1);
      expect(state.uniforms.uUnfurl.value).toBe(1);
    }
    expect(record.lifecycle).toBe(lifecycle);expect(record.phaseStartedAt).toBe(2400);
  });
  it('allows a new reaching epoch or different owner to grow after the previous gesture settled',()=>{
    const state=createWorkspaceRimState();
    writeWorkspaceRimState(state,{...owner,lifecycle:'reaching'},2400,true,layout,contact,1);
    writeWorkspaceRimState(state,owner,2410,false,layout,contact,1);
    expect(state.uniforms.uUnfurl.value).toBe(1);
    writeWorkspaceRimState(state,{...owner,lifecycle:'reaching',phaseStartedAt:3000},3000,false,layout,contact,1);
    expect(state.uniforms.uVisible.value).toBe(0);expect(state.uniforms.uUnfurl.value).toBe(0);
    writeWorkspaceRimState(state,{...owner,phaseStartedAt:3900},4030,false,layout,contact,1);
    expect(state.uniforms.uUnfurl.value).toBe(.25);
    writeWorkspaceRimState(state,owner,4040,true,layout,contact,1);
    writeWorkspaceRimState(state,{...owner,id:'result-2',phaseStartedAt:4000},4130,false,{...layout,targetId:'result-2'},contact,1);
    expect(state.uniforms.uUnfurl.value).toBe(.25);
  });
  it('uses the current unfurl epoch; a late phase transition and live timestamp never restart birth',()=>{
    const state=createWorkspaceRimState();
    writeWorkspaceRimState(state,{...owner,lifecycle:'reaching',phaseStartedAt:1000},2400,false,layout,contact,1);
    expect(state.uniforms.uVisible.value).toBe(0);
    writeWorkspaceRimState(state,owner,2400,false,layout,contact,1);
    expect(state.uniforms.uUnfurl.value).toBe(0);
    writeWorkspaceRimState(state,owner,2530,false,layout,contact,1);
    expect(state.uniforms.uUnfurl.value).toBe(.25);
    writeWorkspaceRimState(state,{...owner,lifecycle:'live',phaseStartedAt:7000},7000,false,layout,contact,1);
    expect(state.uniforms.uUnfurl.value).toBe(1);
    expect(state.uniforms.uVisible.value).toBe(1);
  });
  it.each([
    [{x:578,y:268},[498,228]], [{x:1182,y:468},[1102,428]],
    [{x:768,y:88},[688,48]], [{x:868,y:692},[788,652]],
  ])('starts at the real exposed edge, including a nonzero canvas/overlay origin: %j',(point,expected)=>{
    const state=createWorkspaceRimState();
    writeWorkspaceRimState(state,owner,2530,false,layout,point,1);
    const sampled=new Vector2(), normal=new Vector2();
    sampleWorkspaceRim(state,state.uniforms.uOrigin.value,sampled,normal);
    expect(sampled.x).toBeCloseTo(expected[0],5);
    expect(sampled.y).toBeCloseTo(expected[1],5);
    expect(normal.length()).toBeCloseTo(1);
  });
  it('keeps seeded points outside the reader, reusing buffers until actual bounds change',()=>{
    const state=createWorkspaceRimState();
    writeWorkspaceRimState(state,owner,2530,false,layout,contact,1);
    const position=state.positions,normal=state.normals,revision=state.revision;
    expect(position.length).toBeGreaterThan(0);
    for(let i=0;i<position.length;i+=3) {
      const x=position[i],y=position[i+1];
      // The DOM reader has rounded corners: its bounding box includes empty
      // corner pixels. Use the actual painted rounded rectangle as oracle.
      const cx=Math.max(512,Math.min(1088,x)),cy=Math.max(62,Math.min(638,y));
      expect(Math.hypot(x-cx,y-cy)>12).toBe(true);
      expect(Number.isFinite(x+y+position[i+2])).toBe(true);
    }
    writeWorkspaceRimState(state,owner,2600,false,layout,{x:578,y:368},1.5);
    expect(state.positions).toBe(position); expect(state.normals).toBe(normal); expect(state.revision).toBe(revision);
    writeWorkspaceRimState(state,owner,2600,false,{...layout,plane:{...layout.plane,left:610}}, {x:588,y:368},1.5);
    expect(state.positions).toBe(position); expect(state.revision).toBeGreaterThan(revision);
  });
  it('retires old-owner, decision, occluded, invalid and missing paints, including reduced motion',()=>{
    const state=createWorkspaceRimState();
    for(const reduced of [false,true]) for(const [record,geometry,point] of [
      [undefined,layout,contact], [{...owner,id:'another'},layout,contact],
      [{...owner,lifecycle:'retracting'},layout,contact], [owner,{...layout,decision:true},contact],
      [owner,{...layout,occluders:[{left:590,top:100,width:100,height:100}]},contact],
      [owner,{...layout,canvas:{...layout.canvas,width:0}},contact], [owner,layout,{x:NaN,y:0}],
    ] as const) {
      writeWorkspaceRimState(state,owner,2600,false,layout,contact,1);
      expect(state.uniforms.uVisible.value).toBe(1);
      writeWorkspaceRimState(state,record,2600,reduced,geometry,point,1);
      expect(state.uniforms.uVisible.value).toBe(0);
    }
  });
  it('settles reduced motion immediately without changing the owner or producing an independent clock',()=>{
    const state=createWorkspaceRimState(), record=Object.freeze({...owner,lifecycle:'reaching' as const});
    writeWorkspaceRimState(state,record,2400,true,layout,contact,1);
    expect(state.uniforms.uUnfurl.value).toBe(1); expect(state.uniforms.uVisible.value).toBe(1);
    expect(record.lifecycle).toBe('reaching'); expect(record.phaseStartedAt).toBe(2400);
  });
});
