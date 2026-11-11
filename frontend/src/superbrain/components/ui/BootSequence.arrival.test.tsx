import { act, cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import BootSequence from '@/components/ui/BootSequence';
import { transitionToArriving } from '@/lib/lifecycleStateMachine';

const trackedAssets=vi.hoisted(()=>({ progress: 0 }));
vi.mock('@react-three/drei', () => ({ useProgress: { getState: () => trackedAssets } }));
vi.mock('@/lib/mirrorStore', () => ({ useMirrorStore: { subscribe: () => () => {} } }));
vi.mock('@/lib/lifecycleStateMachine', () => ({
  transitionToArriving: vi.fn(), ArrivalMode: { COALESCENCE: 'coalescence', AWAKENING: 'awakening' },
}));
afterEach(() => { cleanup(); trackedAssets.progress=0; window.localStorage.removeItem('gagos-pause-motion-v1'); vi.useRealTimers(); vi.clearAllMocks(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it('does not present timed visual growth as asset progress when loading is stalled', () => {
  vi.useFakeTimers();vi.stubGlobal('matchMedia', () => Object.assign(new EventTarget(), { matches: false }));
  let frame: FrameRequestCallback | undefined;
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => { frame = callback; return 1; });
  vi.stubGlobal('cancelAnimationFrame', () => {});
  vi.spyOn(performance, 'now').mockReturnValue(0);
  const complete=vi.fn(),view=render(<BootSequence onComplete={complete}/>);
  const fill=view.container.querySelector<HTMLElement>('[class*="fill"]')!;
  expect(fill).toBeTruthy();expect(fill.parentElement).toHaveAttribute('aria-hidden','true');
  const tick=(time:number)=>{ const callback=frame; expect(callback).toBeDefined(); act(()=>callback!(time)); };
  tick(100);const initial=fill.style.transform;
  tick(1000);expect(fill.style.transform).toBe(initial);
  tick(2400);expect(fill.style.transform).toBe(initial);
  expect(screen.getByRole('status',{name:'GAGOS boot sequence'})).toBeInTheDocument();
  tick(2480);act(()=>vi.advanceTimersByTime(420));act(()=>vi.advanceTimersByTime(500));
  expect(complete).toHaveBeenCalledOnce();
});

it('keeps keyboard skip independent of asset readiness', () => {
  vi.useFakeTimers();vi.stubGlobal('matchMedia', () => Object.assign(new EventTarget(), { matches: false }));
  let frame: FrameRequestCallback | undefined;
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => { frame=callback; return 1; });
  vi.stubGlobal('cancelAnimationFrame', () => {});
  vi.spyOn(performance,'now').mockReturnValue(0);
  const complete=vi.fn();render(<BootSequence onComplete={complete}/>);
  act(()=>window.dispatchEvent(new KeyboardEvent('keydown',{key:'a'})));
  act(()=>frame!(1));act(()=>vi.advanceTimersByTime(420));act(()=>vi.advanceTimersByTime(500));
  expect(complete).toHaveBeenCalledOnce();
});


it('responds to live OS and app motion preferences during arrival', () => {
  vi.useFakeTimers();
  const query=Object.assign(new EventTarget(),{matches:false});
  vi.stubGlobal('matchMedia',()=>query);
  vi.stubGlobal('requestAnimationFrame',()=>1);vi.stubGlobal('cancelAnimationFrame',()=>{});
  render(<BootSequence onComplete={()=>{}}/>);
  const overlay=screen.getByRole('status',{name:'GAGOS boot sequence'});
  expect(overlay).not.toHaveAttribute('data-reduced-motion','true');
  query.matches=true;act(()=>query.dispatchEvent(new Event('change')));
  expect(overlay).toHaveAttribute('data-reduced-motion','true');
  query.matches=false;act(()=>query.dispatchEvent(new Event('change')));
  expect(overlay).not.toHaveAttribute('data-reduced-motion','true');
  window.localStorage.setItem('gagos-pause-motion-v1','true');
  act(()=>window.dispatchEvent(new Event('gagos:motion-preference')));
  expect(overlay).toHaveAttribute('data-reduced-motion','true');
});


it('does not trigger the arrival twice when motion preference changes during fade', () => {
  vi.useFakeTimers();
  const query=Object.assign(new EventTarget(),{matches:false});vi.stubGlobal('matchMedia',()=>query);
  let frame: FrameRequestCallback | undefined;
  vi.stubGlobal('requestAnimationFrame',(callback:FrameRequestCallback)=>{frame=callback;return 1;});
  vi.stubGlobal('cancelAnimationFrame',()=>{});vi.spyOn(performance,'now').mockReturnValue(0);
  const complete=vi.fn();render(<BootSequence onComplete={complete}/>);
  act(()=>window.dispatchEvent(new KeyboardEvent('keydown',{key:'a'})));
  act(()=>frame!(1));act(()=>vi.advanceTimersByTime(420));
  expect(transitionToArriving).toHaveBeenCalledOnce();
  query.matches=true;act(()=>query.dispatchEvent(new Event('change')));
  expect(transitionToArriving).toHaveBeenCalledOnce();
  act(()=>vi.advanceTimersByTime(300));expect(complete).toHaveBeenCalledOnce();
});


it('finishes its optional presentation when the asset progress value is unavailable', () => {
  vi.useFakeTimers();vi.stubGlobal('matchMedia',()=>Object.assign(new EventTarget(),{matches:false}));
  let frame: FrameRequestCallback | undefined;
  vi.stubGlobal('requestAnimationFrame',(callback:FrameRequestCallback)=>{frame=callback;return 1;});
  vi.stubGlobal('cancelAnimationFrame',()=>{});vi.spyOn(performance,'now').mockReturnValue(0);
  trackedAssets.progress=Number.NaN;
  const complete=vi.fn();render(<BootSequence onComplete={complete}/>);
  act(()=>frame!(2480));act(()=>vi.advanceTimersByTime(420));act(()=>vi.advanceTimersByTime(500));
  expect(complete).toHaveBeenCalledOnce();
});


it('can finish the optional arrival early when tracked assets have settled', () => {
  vi.useFakeTimers();vi.stubGlobal('matchMedia',()=>Object.assign(new EventTarget(),{matches:false}));
  let frame: FrameRequestCallback | undefined;
  vi.stubGlobal('requestAnimationFrame',(callback:FrameRequestCallback)=>{frame=callback;return 1;});
  vi.stubGlobal('cancelAnimationFrame',()=>{});vi.spyOn(performance,'now').mockReturnValue(0);
  trackedAssets.progress=100;
  const complete=vi.fn();render(<BootSequence onComplete={complete}/>);
  act(()=>frame!(1699));expect(complete).not.toHaveBeenCalled();
  act(()=>frame!(1700));act(()=>vi.advanceTimersByTime(420));act(()=>vi.advanceTimersByTime(500));
  expect(complete).toHaveBeenCalledOnce();
});
