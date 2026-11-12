import { act, cleanup, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import PostFX from './PostFX';

const h = vi.hoisted(() => {
  const state = {
    lost: false,
    being: 'mesh' as string,
    quality: {
      perfTier: 'high' as 'high' | 'medium' | 'low',
      preference: 'manual' as string,
      autoProfile: { multisampling: 2 },
    },
  };
  const gl = {
    domElement: document.createElement('canvas'),
    getContext: () => ({
      isContextLost: () => state.lost,
      getContextAttributes: () => (state.lost ? null : {}),
    }),
  };
  return { state, gl };
});

vi.mock('@react-three/fiber', () => ({
  useThree: () => ({ gl: h.gl }),
}));

vi.mock('@/components/QualityTierProvider', () => ({
  useQualityTier: () => h.state.quality,
}));

vi.mock('@/lib/beingMode', () => ({
  readBeingMode: () => h.state.being,
}));

vi.mock('@/lib/constants', () => ({
  POST_FX: {
    bloom: { intensity: 2.5, luminanceThreshold: 1, luminanceSmoothing: 0.9 },
    bloomPoints: { intensity: 1.1, luminanceThreshold: 1, luminanceSmoothing: 0.5 },
    vignette: { offset: 0.3, darkness: 0.62 },
    vignettePoints: { offset: 0.4, darkness: 0.5 },
    chromaticAberration: { offset: [0.001, 0.002] },
    noise: { opacity: 0.05 },
    grade: {
      contrast: 1.1,
      shadowTint: [0.1, 0.2, 0.3],
      highTint: [0.4, 0.5, 0.6],
      balance: 0,
      vibrance: 0.2,
    },
  },
}));

vi.mock('postprocessing', () => {
  class Effect {
    name: string;
    constructor(name: string) {
      this.name = name;
    }
  }
  return {
    Effect,
    BlendFunction: { SRC: 0, NORMAL: 1, ADD: 2 },
    ToneMappingMode: { AGX: 'agx' },
  };
});

vi.mock('@react-three/postprocessing', () => ({
  EffectComposer: ({ children, multisampling }: { children?: ReactNode; multisampling?: number }) => (
    <div data-testid="composer" data-multisampling={multisampling}>
      {children}
    </div>
  ),
  Bloom: ({ intensity, mipmapBlur }: { intensity: number; mipmapBlur: boolean }) => (
    <i data-testid="bloom" data-intensity={intensity} data-mipmap={String(mipmapBlur)} />
  ),
  ChromaticAberration: () => <i data-testid="chromatic" />,
  ToneMapping: ({ mode }: { mode: string }) => <i data-testid="tonemapping" data-mode={mode} />,
  Vignette: ({ darkness }: { darkness: number }) => <i data-testid="vignette" data-darkness={darkness} />,
  Noise: () => <i data-testid="noise" />,
  wrapEffect: (Cls: new () => { name: string }) => () => <i data-testid={new Cls().name} />,
}));

function chainOrder(): Array<string | null> {
  return Array.from(screen.getByTestId('composer').children).map((el) => el.getAttribute('data-testid'));
}

describe('PostFX', () => {
  beforeEach(() => {
    h.state.lost = false;
    h.state.being = 'mesh';
    h.state.quality = { perfTier: 'high', preference: 'manual', autoProfile: { multisampling: 2 } };
  });
  afterEach(() => cleanup());

  it('renders the full chain in pass order with 4x MSAA on the high tier', () => {
    render(<PostFX />);
    expect(chainOrder()).toEqual([
      'bloom',
      'chromatic',
      'GradePreEffect',
      'tonemapping',
      'GradePostEffect',
      'vignette',
      'noise',
    ]);
    expect(screen.getByTestId('composer')).toHaveAttribute('data-multisampling', '4');
    expect(screen.getByTestId('bloom')).toHaveAttribute('data-mipmap', 'true');
    expect(screen.getByTestId('tonemapping')).toHaveAttribute('data-mode', 'agx');
  });

  it('drops bloom, aberration, noise and MSAA on the low tier but keeps grade and tonemap', () => {
    h.state.quality.perfTier = 'low';
    render(<PostFX />);
    expect(chainOrder()).toEqual(['GradePreEffect', 'tonemapping', 'GradePostEffect', 'vignette']);
    expect(screen.getByTestId('composer')).toHaveAttribute('data-multisampling', '0');
  });

  it('uses the auto profile multisampling and non-mipmap bloom on medium', () => {
    h.state.quality = { perfTier: 'medium', preference: 'auto', autoProfile: { multisampling: 2 } };
    render(<PostFX />);
    expect(screen.getByTestId('composer')).toHaveAttribute('data-multisampling', '2');
    expect(screen.getByTestId('bloom')).toHaveAttribute('data-mipmap', 'false');
    expect(screen.queryByTestId('chromatic')).toBeNull();
    expect(screen.queryByTestId('noise')).toBeNull();
  });

  it('uses the gentler point-field bloom and vignette in points mode', () => {
    h.state.being = 'points';
    render(<PostFX />);
    expect(screen.getByTestId('bloom')).toHaveAttribute('data-intensity', '1.1');
    expect(screen.getByTestId('vignette')).toHaveAttribute('data-darkness', '0.5');
  });

  it('renders nothing when the WebGL context is unavailable and tears down on context loss', () => {
    h.state.lost = true;
    const { unmount } = render(<PostFX />);
    expect(screen.queryByTestId('composer')).toBeNull();
    unmount();

    h.state.lost = false;
    render(<PostFX />);
    expect(screen.getByTestId('composer')).toBeInTheDocument();

    act(() => {
      h.state.lost = true;
      h.gl.domElement.dispatchEvent(new Event('webglcontextlost'));
    });
    expect(screen.queryByTestId('composer')).toBeNull();

    act(() => {
      h.state.lost = false;
      h.gl.domElement.dispatchEvent(new Event('webglcontextrestored'));
    });
    expect(screen.getByTestId('composer')).toBeInTheDocument();
  });
});
