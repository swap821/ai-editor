import { act, cleanup, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import TierGovernor from './TierGovernor';

const h = vi.hoisted(() => {
  const gl = {
    domElement: {} as unknown,
    getPixelRatio: () => 1.25,
    getContext: () => ({ isContextLost: () => false }),
  };
  const three = {
    gl,
    frameloop: 'always',
    setDpr: (_dpr: number) => {},
    get: () => three as unknown,
  };
  return {
    gl,
    three,
    gate: { isSleeping: false },
    quality: {} as Record<string, unknown>,
    monitorProps: null as null | Record<string, (...args: never[]) => void>,
  };
});

vi.mock('@react-three/fiber', () => ({
  useThree: (selector: (s: unknown) => unknown) => selector(h.three),
  useFrame: () => {},
}));

vi.mock('@react-three/drei', () => ({
  PerformanceMonitor: (props: Record<string, (...args: never[]) => void>) => {
    h.monitorProps = props;
    return null;
  },
}));

vi.mock('@/components/QualityTierProvider', () => ({
  useQualityTier: () => h.quality,
}));

vi.mock('@/lib/perfBudget', () => ({
  dprForFactor: (_tier: string, factor: number) => 1 + factor,
  PERF_BOUNDS: [40, 55],
  DPR_WARMUP_MS: 1000,
  ADVISORY_WARMUP_MS: 5000,
}));

vi.mock('../../core/Performance/FeatureGate', () => ({
  FeatureGate: h.gate,
  useFeatureGate: () => h.gate.isSleeping,
}));

const setDpr = vi.fn();
const beginAutoCalibration = vi.fn();
const setAutoSamplingActive = vi.fn();
const reportAutoWindow = vi.fn();

function setQuality(preference: string) {
  h.quality = {
    baseTier: 'high',
    perfTier: 'high',
    generating: false,
    preference,
    autoProfile: { dpr: 0.9, stage: 2 },
    autoRevision: 3,
    beginAutoCalibration,
    setAutoSamplingActive,
    reportAutoWindow,
  };
}

function warmUp() {
  act(() => {
    vi.advanceTimersByTime(1000);
  });
}

describe('TierGovernor', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    h.gate.isSleeping = false;
    h.three.frameloop = 'always';
    h.three.setDpr = setDpr;
    h.monitorProps = null;
    setQuality('balanced');
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it('mounts the performance monitor only after the DPR warmup', () => {
    render(<TierGovernor />);
    expect(h.monitorProps).toBeNull();
    warmUp();
    expect(h.monitorProps).not.toBeNull();
    expect(h.monitorProps?.flipflops).toBe(Infinity);
    expect(h.monitorProps?.factor).toBe(1);
  });

  it('does not mount the monitor while sleeping or when frameloop is on demand', () => {
    h.gate.isSleeping = true;
    render(<TierGovernor />);
    warmUp();
    expect(h.monitorProps).toBeNull();
    cleanup();

    h.gate.isSleeping = false;
    h.three.frameloop = 'demand';
    render(<TierGovernor />);
    warmUp();
    expect(h.monitorProps).toBeNull();
  });

  it('applies the relief factor as DPR in manual mode and ignores it while sleeping', () => {
    render(<TierGovernor />);
    warmUp();
    const onChange = h.monitorProps?.onChange as unknown as (v: { fps: number; factor: number }) => void;

    onChange({ fps: 40, factor: 0.5 });
    expect(setDpr).toHaveBeenCalledTimes(1);
    expect(setDpr).toHaveBeenCalledWith(1.5);

    h.gate.isSleeping = true;
    onChange({ fps: 1, factor: 0 });
    expect(setDpr).toHaveBeenCalledTimes(1);
  });

  it('in auto mode sets the profile DPR once and reports windows with the current revision', () => {
    setQuality('auto');
    render(<TierGovernor />);
    expect(setDpr).toHaveBeenCalledTimes(1);
    expect(setDpr).toHaveBeenCalledWith(0.9);
    warmUp();

    const onChange = h.monitorProps?.onChange as unknown as (v: { fps: number; factor: number }) => void;
    onChange({ fps: 30, factor: 0.2 });
    expect(setDpr).toHaveBeenCalledTimes(1);

    (h.monitorProps?.onDecline as unknown as () => void)();
    (h.monitorProps?.onIncline as unknown as () => void)();
    expect(reportAutoWindow).toHaveBeenCalledTimes(2);
    expect(reportAutoWindow.mock.calls[0].slice(0, 3)).toEqual(['slow', 3, expect.any(Number)]);
    expect(reportAutoWindow.mock.calls[1].slice(0, 3)).toEqual(['healthy', 3, expect.any(Number)]);
  });

  it('does not report auto windows when the GL context is lost', () => {
    setQuality('auto');
    render(<TierGovernor />);
    warmUp();
    h.gl.getContext = () => ({ isContextLost: () => true });
    (h.monitorProps?.onDecline as unknown as () => void)();
    (h.monitorProps?.onIncline as unknown as () => void)();
    expect(reportAutoWindow).not.toHaveBeenCalled();
    h.gl.getContext = () => ({ isContextLost: () => false });
  });

  it('starts auto calibration only for a ready event from its own canvas', () => {
    setQuality('auto');
    render(<TierGovernor />);
    expect(beginAutoCalibration).not.toHaveBeenCalled();

    act(() => {
      window.dispatchEvent(new CustomEvent('gagos:ready', { detail: { canvas: {} } }));
    });
    expect(beginAutoCalibration).not.toHaveBeenCalled();

    act(() => {
      window.dispatchEvent(new CustomEvent('gagos:ready', { detail: { canvas: h.gl.domElement } }));
    });
    expect(beginAutoCalibration).toHaveBeenCalledTimes(1);
    expect(beginAutoCalibration).toHaveBeenCalledWith(expect.any(Number));
  });
});
