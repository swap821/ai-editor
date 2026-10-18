import { afterEach, describe, expect, it, vi } from 'vitest';
import { calculateWorkspaceDockClearance, installWorkspaceDockTracking } from './workspaceDock';

const disposers: (() => void)[] = [];
afterEach(() => {
  for (const dispose of disposers.splice(0)) dispose();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('workspace dock clearance', () => {
  it('selects compact geometry from the available app height and clears stale classification on resize and disposal', () => {
    const root = document.createElement('div');
    let height = 605.4;
    vi.spyOn(root, 'getBoundingClientRect').mockImplementation(() => new DOMRect(0, 144.6, 447, height));
    let frame: FrameRequestCallback | undefined;
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => { frame = callback; return 1; });
    let resize: ResizeObserverCallback | undefined;
    vi.stubGlobal('ResizeObserver', class {
      constructor(callback: ResizeObserverCallback) { resize = callback; }
      observe() {}
      unobserve() {}
      disconnect() {}
    });
    const stop = installWorkspaceDockTracking(root);
    disposers.push(stop);
    frame?.(0);
    expect(root.dataset.workspaceHeight).toBe('compact');
    for (const [nextHeight, expected] of [[739.99, 'compact'], [740, 'tall'], [844, 'tall'], [520, 'compact'], [0, undefined], [Number.NaN, undefined]] as const) {
      height = nextHeight;
      resize?.([], {} as ResizeObserver);
      frame?.(0);
      expect(root.dataset.workspaceHeight).toBe(expected);
    }
    height = 605.4;
    resize?.([], {} as ResizeObserver);
    frame?.(0);
    expect(root.dataset.workspaceHeight).toBe('compact');
    stop();
    frame?.(0);
    expect(root.dataset.workspaceHeight).toBeUndefined();
  });

  it('tracks the available app height, not the window height, through inset resize and disposal', () => {
    const root = document.createElement('div');
    let height = 699.4;
    vi.spyOn(root, 'getBoundingClientRect').mockImplementation(() => new DOMRect(0, 144.6, 390, height));
    let frame: FrameRequestCallback | undefined;
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => { frame = callback; return 1; });
    const stop = installWorkspaceDockTracking(root);
    disposers.push(stop);
    frame?.(0);
    // Round down: a menu must not overrun even a fractional available edge.
    expect(root.style.getPropertyValue('--lm-workspace-app-height')).toBe('699px');
    height = 520.8;
    window.dispatchEvent(new Event('resize'));
    frame?.(0);
    expect(root.style.getPropertyValue('--lm-workspace-app-height')).toBe('520px');
    height = Number.NaN;
    window.dispatchEvent(new Event('resize'));
    frame?.(0);
    expect(root.style.getPropertyValue('--lm-workspace-app-height')).toBe('');
    height = 844;
    window.dispatchEvent(new Event('resize'));
    frame?.(0);
    expect(root.style.getPropertyValue('--lm-workspace-app-height')).toBe('844px');
    stop();
    frame?.(0);
    expect(root.style.getPropertyValue('--lm-workspace-app-height')).toBe('');
  });

  it('keeps inset header and mode measurements current through actual resize notifications and clears them on disposal', () => {
    const root = document.createElement('div');
    root.innerHTML = '<header class="lm-header"></header><div class="gagos-chrome"><div class="gagos-experience-switch"></div><section class="gagos-chat"></section></div>';
    const header = root.querySelector('.lm-header')!;
    const mode = root.querySelector('.gagos-experience-switch')!;
    vi.spyOn(root, 'getBoundingClientRect').mockReturnValue(new DOMRect(0, 113, 768, 587));
    let headerHeight = 60.8, modeWidth = 438.15, modeHeight = 48;
    vi.spyOn(header, 'getBoundingClientRect').mockImplementation(() => new DOMRect(28, 133, 712, headerHeight));
    vi.spyOn(mode, 'getBoundingClientRect').mockImplementation(() => new DOMRect(28, 206, modeWidth, modeHeight));
    let frame: FrameRequestCallback | undefined;
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => { frame = callback; return 1; });
    const observers = new Map<ResizeObserverCallback, Set<Element>>();
    vi.stubGlobal('ResizeObserver', class {
      private targets = new Set<Element>();
      constructor(callback: ResizeObserverCallback) { observers.set(callback, this.targets); }
      observe(target: Element) { this.targets.add(target); }
      unobserve(target: Element) { this.targets.delete(target); }
      disconnect() { for (const [callback, targets] of observers) if (targets === this.targets) observers.delete(callback); }
    });
    const stop = installWorkspaceDockTracking(root);
    disposers.push(stop);
    frame?.(0);
    expect(root.style.getPropertyValue('--lm-header-bottom')).toBe('81px');
    expect(root.style.getPropertyValue('--lm-mode-switch-width')).toBe('439px');
    expect(root.style.getPropertyValue('--lm-mode-switch-height')).toBe('48px');
    headerHeight = 90.4; modeWidth = 480.25; modeHeight = 58.3;
    for (const [callback, targets] of observers) if (targets.has(header) && targets.has(mode)) callback([], {} as ResizeObserver);
    frame?.(0);
    expect(root.style.getPropertyValue('--lm-header-bottom')).toBe('111px');
    expect(root.style.getPropertyValue('--lm-mode-switch-width')).toBe('481px');
    expect(root.style.getPropertyValue('--lm-mode-switch-height')).toBe('59px');
    stop();
    for (const property of ['--lm-header-bottom', '--lm-mode-switch-width', '--lm-mode-switch-height']) {
      expect(root.style.getPropertyValue(property)).toBe('');
    }
    frame?.(0);
    expect(root.style.getPropertyValue('--lm-header-bottom')).toBe('');
  });

  it('removes obsolete control measurements when the measured header or switch becomes unavailable', () => {
    const root = document.createElement('div');
    root.innerHTML = '<header class="lm-header"></header><div class="gagos-experience-switch"></div>';
    const header = root.querySelector('.lm-header')!;
    const mode = root.querySelector('.gagos-experience-switch')!;
    vi.spyOn(root, 'getBoundingClientRect').mockReturnValue(new DOMRect(0, 113, 768, 587));
    let usable = true;
    vi.spyOn(header, 'getBoundingClientRect').mockImplementation(() => new DOMRect(28, 133, 712, usable ? 60.8 : 0));
    vi.spyOn(mode, 'getBoundingClientRect').mockImplementation(() => new DOMRect(28, 206, usable ? 438.15 : 0, usable ? 48 : 0));
    let frame: FrameRequestCallback | undefined;
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => { frame = callback; return 1; });
    disposers.push(installWorkspaceDockTracking(root));
    frame?.(0);
    expect(root.style.getPropertyValue('--lm-header-bottom')).toBe('81px');
    usable = false;
    window.dispatchEvent(new Event('resize'));
    frame?.(0);
    for (const property of ['--lm-header-bottom', '--lm-mode-switch-width', '--lm-mode-switch-height']) {
      expect(root.style.getPropertyValue(property)).toBe('');
    }
  });

  it('reserves the measured permission chrome plus readable proposal without borrowing body space', () => {
    const root = document.createElement('div');
    root.innerHTML = '<div class="gagos-chrome"><section class="gagos-chat"></section><section class="approval-panel" style="border:1px solid"><header class="approval-head"></header><div class="approval-actions"></div></section></div>';
    vi.spyOn(root, 'getBoundingClientRect').mockReturnValue({ bottom: 568, height: 568 } as DOMRect);
    vi.spyOn(root.querySelector('.gagos-chat')!, 'getBoundingClientRect').mockReturnValue({ top: 340, height: 138 } as DOMRect);
    vi.spyOn(root.querySelector('.approval-head')!, 'getBoundingClientRect').mockReturnValue({ height: 52.64 } as DOMRect);
    vi.spyOn(root.querySelector('.approval-actions')!, 'getBoundingClientRect').mockReturnValue({ height: 64 } as DOMRect);
    let frame: FrameRequestCallback | undefined;
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => { frame = callback; return 1; });
    const stop = installWorkspaceDockTracking(root);
    disposers.push(stop);
    frame?.(0);
    // 52.64 header +64 actions +2 borders +44 reading +8 separation, rounded up.
    expect(root.style.getPropertyValue('--lm-permission-work-reservation')).toBe('171px');
    stop();
    expect(root.style.getPropertyValue('--lm-permission-work-reservation')).toBe('');
  });

  it('tracks permission admission, taller action chrome and removal without retaining its reservation', async () => {
    const root = document.createElement('div');
    root.innerHTML = '<div class="gagos-chrome"><section class="gagos-chat"></section></div>';
    vi.spyOn(root, 'getBoundingClientRect').mockReturnValue({ bottom: 568, height: 568 } as DOMRect);
    vi.spyOn(root.querySelector('.gagos-chat')!, 'getBoundingClientRect').mockReturnValue({ top: 340, height: 138 } as DOMRect);
    let frame: FrameRequestCallback | undefined;
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => { frame = callback; return 1; });
    const stop = installWorkspaceDockTracking(root);
    disposers.push(stop);
    frame?.(0);
    expect(root.style.getPropertyValue('--lm-permission-work-reservation')).toBe('');
    const panel = document.createElement('section');
    panel.className = 'approval-panel';
    panel.style.border = '1px solid';
    panel.innerHTML = '<header class="approval-head"></header><div class="approval-actions"></div>';
    let actionHeight = 64;
    vi.spyOn(panel.querySelector('.approval-head')!, 'getBoundingClientRect').mockReturnValue({ height: 72 } as DOMRect);
    vi.spyOn(panel.querySelector('.approval-actions')!, 'getBoundingClientRect').mockImplementation(() => ({ height: actionHeight }) as DOMRect);
    root.querySelector('.gagos-chrome')!.append(panel);
    await Promise.resolve();
    frame?.(0);
    expect(root.style.getPropertyValue('--lm-permission-work-reservation')).toBe('190px');
    actionHeight = 108;
    window.dispatchEvent(new Event('resize'));
    frame?.(0);
    expect(root.style.getPropertyValue('--lm-permission-work-reservation')).toBe('234px');
    panel.remove();
    await Promise.resolve();
    frame?.(0);
    expect(root.style.getPropertyValue('--lm-permission-work-reservation')).toBe('');
    stop();
    root.querySelector('.gagos-chrome')!.append(panel);
    await Promise.resolve();
    frame?.(0);
    expect(root.style.getPropertyValue('--lm-permission-work-reservation')).toBe('');
  });

  it('keeps a fixed gap below fractional composer coordinates', () => {
    expect(calculateWorkspaceDockClearance(844, 620.5)).toBe(236);
  });

  it('rejects invalid measurements and clamps a composer below the root', () => {
    expect(calculateWorkspaceDockClearance(Number.NaN, 200)).toBeNull();
    expect(calculateWorkspaceDockClearance(100, 200)).toBe(0);
  });

  it('updates the CSS dock clearance when the composer moves and clears it on cleanup', () => {
    const root = document.createElement('div');
    const composer = document.createElement('section');
    composer.className = 'gagos-chat';
    root.append(composer);
    let rootBottom = 844;
    let composerTop = 620;
    vi.spyOn(root, 'getBoundingClientRect').mockImplementation(() => ({ bottom: rootBottom, height: 844 }) as DOMRect);
    vi.spyOn(composer, 'getBoundingClientRect').mockImplementation(() => ({ top: composerTop, height: 92 }) as DOMRect);
    let pendingFrame: FrameRequestCallback | undefined;
    let nextFrameId = 0;
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
      pendingFrame = callback;
      nextFrameId += 1;
      return nextFrameId;
    });
    const cancelFrame = vi.fn();
    vi.stubGlobal('cancelAnimationFrame', cancelFrame);

    const stop = installWorkspaceDockTracking(root);
    pendingFrame?.(0);
    expect(root.style.getPropertyValue('--lm-workspace-dock-clearance')).toBe('236px');

    rootBottom = 900;
    composerTop = 510;
    window.dispatchEvent(new Event('resize'));
    pendingFrame?.(0);
    expect(root.style.getPropertyValue('--lm-workspace-dock-clearance')).toBe('402px');

    window.dispatchEvent(new Event('resize'));
    stop();
    expect(root.style.getPropertyValue('--lm-workspace-dock-clearance')).toBe('');
    expect(cancelFrame).toHaveBeenCalledWith(3);
  });
});
