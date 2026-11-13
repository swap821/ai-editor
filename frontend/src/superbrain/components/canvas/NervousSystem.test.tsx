import { cleanup, render } from '@testing-library/react';
import type { ComponentProps } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import NervousSystem from './NervousSystem';

const mocks = vi.hoisted(() => {
  const dispose = vi.fn();
  const unsubscribe = vi.fn();
  const makeMaterial = vi.fn((options: {
    tier: string;
    uniforms: unknown;
    bodyMode: string;
    webScale: number;
    webOctaves: string;
    breathUniform: unknown;
    intakeFlowUniform: { value: number };
    intakeGainUniform: { value: number };
    replyWarmUniform: { value: number };
  }) => ({ dispose, options }));
  const subscribe = vi.fn(
    (_listener: (event: {
      type: string;
      intensity?: number;
      source?: string;
      data?: { phase?: string };
    }) => void) => unsubscribe,
  );
  return { dispose, unsubscribe, makeMaterial, subscribe };
});

vi.mock('@react-three/fiber', () => ({ useFrame: vi.fn() }));
vi.mock('@/lib/seededRandom', () => ({
  createSeededRandom: () => () => 0.5,
}));
vi.mock('@/lib/brainMaterial', () => ({
  makeBrainMaterial: mocks.makeMaterial,
}));
vi.mock('@/lib/cognitionBus', () => ({
  subscribeCognition: mocks.subscribe,
}));
vi.mock('./VertebraeRepoMapOverlay', () => ({
  default: () => <div>Repository overlay</div>,
}));

type Props = ComponentProps<typeof NervousSystem>;

function makeProps(): Props {
  return {
    burst: { current: { intensity: 0 } } as Props['burst'],
    uniforms: {
      uBreath: { value: 0 },
      uFlow: { value: 0.16 },
    } as Props['uniforms'],
  };
}

describe('NervousSystem', () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('configures the shared nerve material and disposes it on unmount', () => {
    const props = makeProps();
    const { getByText, unmount } = render(
      <NervousSystem {...props} tier="high" />,
    );

    expect(getByText('Repository overlay')).toBeInTheDocument();
    expect(mocks.makeMaterial).toHaveBeenCalledWith(
      expect.objectContaining({
        tier: 'high',
        uniforms: props.uniforms,
        bodyMode: 'nerve',
        webScale: 24,
        webOctaves: 'tier',
        breathUniform: props.uniforms.uBreath,
      }),
    );

    unmount();
    expect(mocks.dispose).toHaveBeenCalledOnce();
    expect(mocks.unsubscribe).toHaveBeenCalledOnce();
  });

  it('responds to voice phases and clears intake and reply warmth on unmount', () => {
    const { unmount } = render(<NervousSystem {...makeProps()} />);
    const options = mocks.makeMaterial.mock.calls[0][0];
    const listener = mocks.subscribe.mock.calls[0][0];

    listener({ type: 'voice-speaking', intensity: 0.8, data: { phase: 'question' } });
    expect(options.intakeFlowUniform.value).toBe(0);
    expect(options.intakeGainUniform.value).toBe(0.8);

    listener({
      type: 'voice-speaking',
      source: 'reply',
      data: { phase: 'reply-start' },
    });
    expect(options.replyWarmUniform.value).toBe(1);

    unmount();
    expect(options.intakeGainUniform.value).toBe(0);
    expect(options.replyWarmUniform.value).toBe(0);
  });
});
