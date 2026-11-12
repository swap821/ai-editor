import { render } from '@testing-library/react';
import { PerspectiveCamera } from 'three';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { getStemAnchor, setStemAnchor } from '@/lib/stemAnchorBus';
import { getFunnelAnchor, setFunnelAnchor } from '@/lib/funnelAnchorBus';
import BodyIntakeAnchors from './BodyIntakeAnchors';

type FrameState = {
  camera: PerspectiveCamera;
  size: { width: number; height: number; left: number; top: number };
};

const frame = vi.hoisted(() => ({ callback: null as ((state: FrameState) => void) | null }));

vi.mock('@react-three/fiber', () => ({
  useFrame: (cb: (state: FrameState) => void) => {
    frame.callback = cb;
  },
}));

const emptyStem = { x: 0, y: 0, visible: false };
const emptyFunnel = { x: 0, y: 0, visible: false, world: [0, 0, 0] as [number, number, number], intake: 0, flow: 0 };

function runFrame(width: number, height: number) {
  if (!frame.callback) throw new Error('useFrame callback was not registered');
  frame.callback({ camera: new PerspectiveCamera(), size: { width, height, left: 0, top: 0 } });
}

describe('BodyIntakeAnchors', () => {
  beforeEach(() => {
    frame.callback = null;
    setStemAnchor({ ...emptyStem });
    setFunnelAnchor({ ...emptyFunnel, world: [0, 0, 0] });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders nothing and registers a per-frame callback', () => {
    const { container } = render(<BodyIntakeAnchors reducedMotion={false} />);
    expect(container).toBeEmptyDOMElement();
    expect(frame.callback).toBeTypeOf('function');
  });

  it('reports hidden, idle anchors when the viewport has no size', () => {
    render(<BodyIntakeAnchors reducedMotion={false} />);
    runFrame(0, 0);

    expect(getStemAnchor().visible).toBe(false);
    const funnel = getFunnelAnchor();
    expect(funnel.visible).toBe(false);
    expect(funnel.intake).toBe(0);
    expect(funnel.flow).toBe(0);
    expect(funnel.presence).toBe(0);
  });

  it('clears the anchors it published when unmounted', () => {
    const { unmount } = render(<BodyIntakeAnchors reducedMotion={true} />);
    runFrame(0, 0);

    const stem = getStemAnchor();
    stem.x = 7;
    stem.visible = true;
    const funnel = getFunnelAnchor();
    funnel.intake = 0.5;
    funnel.visible = true;

    unmount();

    expect(getStemAnchor().x).toBe(0);
    expect(getStemAnchor().visible).toBe(false);
    expect(getFunnelAnchor().intake).toBe(0);
    expect(getFunnelAnchor().visible).toBe(false);
  });

  it('does not erase anchors published by a replacement renderer', () => {
    const { unmount } = render(<BodyIntakeAnchors reducedMotion={false} />);
    runFrame(0, 0);

    const replacementStem = { x: 11, y: 12, visible: true };
    const replacementFunnel = { x: 3, y: 4, visible: true, world: [1, 2, 3] as [number, number, number], intake: 1, flow: 1 };
    setStemAnchor(replacementStem);
    setFunnelAnchor(replacementFunnel);

    unmount();

    expect(getStemAnchor()).toBe(replacementStem);
    expect(getStemAnchor().x).toBe(11);
    expect(getFunnelAnchor()).toBe(replacementFunnel);
    expect(getFunnelAnchor().visible).toBe(true);
  });
});
