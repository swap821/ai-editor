import { act, cleanup, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createRef, type RefObject } from 'react';
import { Matrix4, PerspectiveCamera } from 'three';
import { WorkspaceConnectionOverlay, WorkspaceConnectionProjection } from './WorkspaceConnectionOverlay';
import { __resetSpineFusionForTests, setBodyGroupWorldMatrix, setCortexAnchor, setSpineFusion } from '../../superbrain/lib/spineFusionBus';
import { __resetTabStoreForTests, closeWorkspace, focusWorkspace, getTabStoreSnapshot, openWorkspacePanel,
  showContentSurface, showApprovalSurface, updateMaterializedTab, setMaterializedTabLifecycle,
  beginRetractingMaterializedTab } from '../../superbrain/lib/tabStore';
import ApprovalPanel from '../../superbrain/components/ui/ApprovalPanel';
import GuidedApprovalPanel from '../GuidedApprovalPanel';

let frame: (state: { camera: PerspectiveCamera; gl: { domElement: HTMLCanvasElement } }) => void;
// WebGL is external to this DOM integration test. Keep the real seat store,
// fusion/matrix publication, camera projection and resulting SVG geometry.
vi.mock('@react-three/fiber', () => ({ useFrame: (callback: typeof frame) => { frame = callback; } }));
const camera = new PerspectiveCamera(90, 1, 0.1, 100);
camera.position.set(0, 0, 10);
camera.updateMatrixWorld();
const overlayRef = createRef<SVGSVGElement>();

function Surface({ renderer = true, decision = false, guided = false, attentionTargetRef }: { renderer?: boolean; decision?: boolean; guided?: boolean;
  attentionTargetRef?: RefObject<{ targetId: string; lateral: number; vertical: number } | null> }) {
  const pending = { token: 'fixture-decision', prompt: 'Create a fixture', url: '', kind: 'create' as const, filepath: 'same.py',
    content: 'new proposal', diff: '+new proposal', command: '', summary: 'New proposal', explanation: '' };
  return <div className="lm-app">
    <canvas /><section className="lm-surface" data-workspace-id={getTabStoreSnapshot().focusId ?? undefined} />
    <div className="gagos-chrome" data-approval-pending={decision ? 'true' : 'false'}>
      {decision && (guided ? <GuidedApprovalPanel pending={pending} onSettled={() => {}} />
        : <ApprovalPanel pending={pending} onSettled={() => {}} />)}
    </div>
    <WorkspaceConnectionOverlay overlayRef={overlayRef} />
    {renderer && <WorkspaceConnectionProjection {...{ overlayRef, snapshot: getTabStoreSnapshot(), attentionTargetRef }} />}
  </div>;
}
function step() {
  act(() => frame({ camera, gl: { domElement: document.querySelector('canvas')! } }));
}
function path() { return overlayRef.current!.querySelector('path')!.getAttribute('d'); }

beforeEach(() => {
  __resetTabStoreForTests();
  __resetSpineFusionForTests();
  vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(function (this: Element) {
    const value = this.matches('canvas') ? { x: 100, y: 50, width: 400, height: 400 }
      : this.matches('.lm-surface') ? { x: 600, y: 100, width: 600, height: 600 }
        : { x: 20, y: 10, width: 1200, height: 800 };
    return { ...value, left: value.x, top: value.y, right: value.x + value.width, bottom: value.y + value.height, toJSON: () => value };
  });
  setSpineFusion(1, [0, 0, 0]);
  setBodyGroupWorldMatrix(new Matrix4());
  openWorkspacePanel('history', 'Recent observations');
});
afterEach(() => {
  cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); __resetTabStoreForTests(); __resetSpineFusionForTests();
});

describe('body-to-workplane connection', () => {
  it('publishes the actual cortex-to-plane direction and retires only its own target on Conversation or renderer loss', () => {
    setCortexAnchor([0, 0, 0]); // declared external geometry, not the pre-publish fallback at y=.1
    const attentionTargetRef = createRef<{ targetId: string; lateral: number; vertical: number } | null>();
    const view = render(<Surface attentionTargetRef={attentionTargetRef} />); step();
    // Actual camera projects the cortex at (300,250), independently of the
    // lower vertebra feeding the cable. Measured plane centre is (900,400).
    expect.soft(attentionTargetRef.current).toEqual({ targetId: 'history', lateral: 1, vertical: 0.75 });
    const plane = view.container.querySelector('.lm-surface')!;
    let rect = new DOMRect(20, 100, 100, 300);
    // The inherited prototype method is already a shared mock. Spying on it
    // again changes the canvas/overlay too; supply only this plane's boundary.
    Object.defineProperty(plane, 'getBoundingClientRect', { configurable: true, value: () => rect });
    act(() => window.dispatchEvent(new Event('resize'))); step();
    expect.soft(attentionTargetRef.current).toEqual({ targetId: 'history', lateral: -1, vertical: 0 });
    rect = new DOMRect(100, 500, 400, 200);
    act(() => window.dispatchEvent(new Event('resize'))); step();
    expect.soft(attentionTargetRef.current).toEqual({ targetId: 'history', lateral: 0, vertical: 1 });
    const measurementCount = vi.mocked(Element.prototype.getBoundingClientRect).mock.calls.length;
    for (let n = 0; n < 30; n++) step();
    expect(vi.mocked(Element.prototype.getBoundingClientRect).mock.calls.length, 'frames reuse measured layout').toBe(measurementCount);
    act(() => focusWorkspace(null)); view.rerender(<Surface attentionTargetRef={attentionTargetRef} />); step();
    expect(attentionTargetRef.current).toBeNull();
    act(() => focusWorkspace('history')); view.rerender(<Surface attentionTargetRef={attentionTargetRef} />); step();
    expect.soft(attentionTargetRef.current?.targetId).toBe('history');
    view.rerender(<Surface renderer={false} attentionTargetRef={attentionTargetRef} />);
    expect(attentionTargetRef.current).toBeNull();
  });
  // Missing the pending-dialog target draws no connection (or the older
  // reader's seat). The independent oracle is seat 6's projected pixel and
  // the actual dialog edge, not the projection helper under test.
  it.each([[false, false], [false, true], [true, false], [true, true]])(
    'connects the owned decision, preserving same-path reading and immediate reduced motion (guided=%s, reduced=%s)',
    async (guided, reduced) => {
      vi.stubGlobal('matchMedia', (query: string) => ({ matches: reduced && query.includes('reduced-motion'),
        media: query, addEventListener: () => {}, removeEventListener: () => {} }) as MediaQueryList);
      __resetTabStoreForTests();
      const older = showContentSurface({ filepath: 'same.py', code: 'older result', language: 'python' }, { seatIndex: 2 });
      setMaterializedTabLifecycle(older.id, 'live');
      const newer = showContentSurface({ filepath: 'writing', code: '', language: 'python' }, { seatIndex: 5 });
      updateMaterializedTab(newer.id, { content: { filepath: 'same.py', code: 'new proposal', language: 'python', completion: 'awaiting-approval' } });
      const attentionTargetRef = createRef<{ targetId: string; lateral: number; vertical: number } | null>();
      const view = render(<Surface guided={guided} attentionTargetRef={attentionTargetRef} />); step();
      const readerPath = path();
      let decisionRect = new DOMRect(650, 160, 500, 300);
      vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(function (this: Element) {
        return this.matches('canvas') ? new DOMRect(100, 50, 400, 400)
          : this.matches('.approval-panel') ? decisionRect
            : this.matches('.lm-surface') ? new DOMRect(600, 100, 600, 600)
              : new DOMRect(20, 10, 1200, 800);
      });
      const approval = showApprovalSurface({ requestRef: 'conversation-approval', kindLabel: 'create',
        filepath: 'same.py', summary: 'New proposal', explanation: '', content: 'new proposal', diff: '+new proposal', command: '' }, { seatIndex: 6 });
      // A critical decision connects on the next frame, not after its old
      // materialization timer. The reader remains selected and selectable.
      view.rerender(<Surface guided={guided} decision attentionTargetRef={attentionTargetRef} />);
      await act(async () => {}); step();
      expect.soft(path()).toBe('M 280 278 C 454 278, 454 278, 628 278');
      expect.soft(attentionTargetRef.current?.targetId, 'body aim and cable own the same decision').toBe(approval.id);
      expect.soft(overlayRef.current!.querySelector('circle')).toHaveStyle({ visibility: 'visible' });
      expect.soft(overlayRef.current!.querySelector('path')).toHaveAttribute('stroke-dashoffset', '0');
      decisionRect = new DOMRect(100, 500, 400, 200);
      act(() => window.dispatchEvent(new Event('resize'))); step();
      expect.soft(path()).toBe('M 280 278 C 280 383, 280 383, 280 488');
      expect(getTabStoreSnapshot().focusId).toBe(older.id);
      expect(getTabStoreSnapshot().tabs.filter(tab => tab.kind === 'content').map(tab => [tab.id, tab.seatIndex, tab.content?.code]))
        .toEqual([[older.id, 2, 'older result'], [newer.id, 5, 'new proposal']]);
      expect(view.container.innerHTML).not.toContain('fixture-decision');
      act(() => focusWorkspace(null));
      view.rerender(<Surface guided={guided} decision />); await act(async () => {}); step();
      expect(path(), 'the owned decision also connects from explicit Conversation').toBe('M 280 278 C 280 383, 280 383, 280 488');
      expect(getTabStoreSnapshot().focusId).toBeNull();
      for (const seat of [null, 12, -1, 2.5]) {
        act(() => updateMaterializedTab(approval.id, { seatIndex: seat }));
        view.rerender(<Surface guided={guided} decision />); await act(async () => {}); step();
        expect(path(), 'no fabricated decision seat or older reader fallback').toBe('');
      }
      act(() => updateMaterializedTab(approval.id, { seatIndex: 6,
        approval: { ...approval.approval!, requestRef: 'dev-approval' } }));
      view.rerender(<Surface guided={guided} decision />); await act(async () => {}); step();
      expect(path(), 'a lab proposal does not own the operational dialog').toBe('');
      act(() => updateMaterializedTab(approval.id, { approval: approval.approval }));
      view.rerender(<Surface guided={guided} decision />); await act(async () => {}); step();
      expect(path()).toBe('M 280 278 C 280 383, 280 383, 280 488');
      act(() => beginRetractingMaterializedTab(approval.id));
      view.rerender(<Surface guided={guided} decision />); await act(async () => {}); step();
      expect(path(), 'a retiring record cannot attach to a lingering decision').toBe('');
      act(() => focusWorkspace(older.id));
      view.rerender(<Surface guided={guided} />); await act(async () => {}); step();
      expect(path()).toBe(readerPath);
    },
  );
  it('follows actual workspace focus and removes the connection on Conversation', () => {
    const view = render(<Surface />);
    step();
    const first = path();
    expect(first).toMatch(/^M 280 /);
    act(() => openWorkspacePanel('terminal', 'Terminal'));
    view.rerender(<Surface />); step();
    expect(path()).not.toBe(first);
    act(() => focusWorkspace('history'));
    view.rerender(<Surface />); step();
    expect(path()).toBe(first);
    act(() => focusWorkspace(null));
    view.rerender(<Surface />); step();
    expect(path()).toBe('');
    expect(overlayRef.current!.querySelector('circle')).toHaveStyle({ visibility: 'hidden' });
    expect(overlayRef.current).toHaveAttribute('aria-hidden', 'true');
  });
  it('does not draw from a fabricated pre-load body matrix or after explicit close', () => {
    __resetSpineFusionForTests();
    const view = render(<Surface />); step();
    expect(path()).toBe('');
    setSpineFusion(1, [0, 0, 0]); setBodyGroupWorldMatrix(new Matrix4()); step();
    expect(path()).not.toBe('');
    act(() => closeWorkspace('history'));
    view.rerender(<Surface />); step();
    expect(path()).toBe('');
  });
  it('clears the old geometry when the renderer unmounts, without touching workspace records', () => {
    const view = render(<Surface />); step();
    expect(path()).not.toBe('');
    view.rerender(<Surface renderer={false} />);
    expect(path()).toBe('');
    expect(overlayRef.current!.querySelector('circle')).toHaveStyle({ visibility: 'hidden' });
    expect(overlayRef.current).toHaveStyle({ visibility: 'hidden' });
    expect(getTabStoreSnapshot().focusId).toBe('history');
    expect(getTabStoreSnapshot().panels?.[0].open).toBe(true);
    view.rerender(<Surface />); step();
    expect(path()).not.toBe('');
  });
  it('refreshes the measured edge on resize, without changing the selected seat', () => {
    const view = render(<Surface />); step();
    const plane = view.container.querySelector('.lm-surface')!;
    Object.defineProperty(plane, 'getBoundingClientRect', { configurable: true,
      value: () => ({ left: 700, top: 100, width: 500, height: 600 }),
    });
    act(() => window.dispatchEvent(new Event('resize'))); step();
    expect(path()).toMatch(/, 678 [\d.]+$/);
    expect(getTabStoreSnapshot().panels?.[0].seatIndex).toBe(2);
  });
  it('draws no phantom connection for readable-only History and connects after a real seat is freed', () => {
    __resetTabStoreForTests();
    for (let n = 0; n < 12; n++) openWorkspacePanel(`panel-${n}`, `Panel ${n}`);
    openWorkspacePanel('history', 'Recent observations');
    const view = render(<Surface />); step();
    expect(getTabStoreSnapshot().panels?.find((panel) => panel.id === 'history')?.seatIndex).toBeNull();
    expect(path()).toBe('');
    act(() => { closeWorkspace('panel-0'); focusWorkspace('history'); });
    view.rerender(<Surface />); step();
    expect(path()).not.toBe('');
  });
  it.each([false, true])('retires an occluded older reader socket without attaching a same-path decision to that seat; reduced=%s', async reduced => {
    vi.stubGlobal('matchMedia', (query: string) => ({ matches: reduced && query.includes('reduced-motion'),
      media: query, addEventListener: () => {}, removeEventListener: () => {} }) as MediaQueryList);
    __resetTabStoreForTests();
    const older = showContentSurface({ filepath: 'same.py', code: 'older result', language: 'python' }, { seatIndex: 2 });
    setMaterializedTabLifecycle(older.id, 'live');
    const newer = showContentSurface({ filepath: 'writing', code: '', language: 'python' }, { seatIndex: 5 });
    updateMaterializedTab(newer.id, { content: { filepath: 'same.py', code: 'new proposal', language: 'python', completion: 'awaiting-approval' } });
    const view = render(<Surface />); step();
    const readerPath = path();
    expect(readerPath).not.toBe('');
    // The decision covers the reader's contact rim, as on the compact phone.
    // Real panel/store/projection; only external layout and WebGL are supplied.
    vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(function (this: Element) {
      const value = this.matches('canvas') ? { x: 100, y: 50, width: 400, height: 400 }
        : this.matches('.lm-surface, .approval-panel') ? { x: 600, y: 100, width: 600, height: 600 }
          : { x: 20, y: 10, width: 1200, height: 800 };
      return { ...value, left: value.x, top: value.y, right: value.x + value.width, bottom: value.y + value.height, toJSON: () => value };
    });
    view.rerender(<Surface decision />);
    await act(async () => {}); step();
    expect(path()).toBe('');
    expect(overlayRef.current!.querySelector('circle')).toHaveStyle({ visibility: 'hidden' });
    expect(getTabStoreSnapshot().focusId).toBe(older.id);
    expect(getTabStoreSnapshot().tabs.filter(tab => tab.kind === 'content').map(tab => [tab.id, tab.seatIndex, tab.content?.code]))
      .toEqual([[older.id, 2, 'older result'], [newer.id, 5, 'new proposal']]);
    view.rerender(<Surface />);
    await act(async () => {}); step();
    expect(path()).toBe(readerPath);
    expect(overlayRef.current!.querySelector('circle')).toHaveStyle({ visibility: 'visible' });
  });
});
