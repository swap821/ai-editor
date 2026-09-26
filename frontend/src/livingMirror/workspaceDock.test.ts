import { afterEach, describe, expect, it, vi } from 'vitest';
import { calculateWorkspaceDockClearance, installWorkspaceDockTracking } from './workspaceDock';

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('workspace dock clearance', () => {
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
