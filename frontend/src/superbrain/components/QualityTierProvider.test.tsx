// @vitest-environment jsdom
import { act, cleanup, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  QualityTierProvider,
  demoteTier,
  effectiveTier,
  isQualityTier,
  useQualityTier,
} from './QualityTierProvider';

const cognition = vi.hoisted(() => ({
  handler: null as ((event: { type: string }) => void) | null,
}));

vi.mock('@/lib/cognitionBus', () => ({
  subscribeCognition: vi.fn((handler: (event: { type: string }) => void) => {
    cognition.handler = handler;
    return () => {
      cognition.handler = null;
    };
  }),
}));

vi.mock('../lib/renderQualityPolicy', () => ({
  isQualityPreference: (value: unknown) =>
    value === 'auto' || value === 'low' || value === 'medium' || value === 'high',
  initialAutoQuality: (revision = 0) => ({ stage: 'calibrating', revision }),
  autoQualityProfile: (stage: string) => ({ stage }),
  startAutoQuality: vi.fn((runtime: { revision: number }) => ({
    stage: 'started',
    revision: runtime.revision,
  })),
  setAutoSampling: vi.fn((runtime: unknown) => runtime),
  advanceAutoQuality: vi.fn((runtime: unknown) => runtime),
}));

type Ctx = ReturnType<typeof useQualityTier>;
const seen: { ctx: Ctx | null } = { ctx: null };

function Probe() {
  seen.ctx = useQualityTier();
  return null;
}

function current(): NonNullable<Ctx> {
  if (!seen.ctx) throw new Error('context missing');
  return seen.ctx;
}

function mount(props: { defaultTier?: 'low' | 'medium' | 'high'; restorePreference?: boolean } = {}) {
  return render(
    <QualityTierProvider {...props}>
      <Probe />
    </QualityTierProvider>,
  );
}

beforeEach(() => {
  window.localStorage.clear();
  seen.ctx = null;
  cognition.handler = null;
});

afterEach(() => {
  cleanup();
});

describe('pure helpers', () => {
  it('validates tiers and demotes one step with low as the floor', () => {
    expect(isQualityTier('medium')).toBe(true);
    expect(isQualityTier('auto')).toBe(false);
    expect(isQualityTier(3)).toBe(false);
    expect(demoteTier('high')).toBe('medium');
    expect(demoteTier('medium')).toBe('low');
    expect(demoteTier('low')).toBe('low');
    expect(effectiveTier('high', true)).toBe('medium');
    expect(effectiveTier('high', false)).toBe('high');
  });
});

describe('QualityTierProvider', () => {
  it('defaults to auto reporting high, or to the supplied defaultTier', () => {
    mount();
    expect(current().preference).toBe('auto');
    expect(current().tier).toBe('high');
    cleanup();
    mount({ defaultTier: 'low' });
    expect(current().preference).toBe('low');
    expect(current().tier).toBe('low');
    expect(current().baseTier).toBe('low');
  });

  it('restores a stored preference, migrates v3 and removes legacy keys', () => {
    window.localStorage.setItem('gag-quality-tier', 'high');
    window.localStorage.setItem('gag-quality-tier-v2', 'high');
    window.localStorage.setItem('gag-quality-tier-v4', 'medium');
    mount();
    expect(current().preference).toBe('medium');
    expect(window.localStorage.getItem('gag-quality-tier')).toBeNull();
    expect(window.localStorage.getItem('gag-quality-tier-v2')).toBeNull();
    cleanup();

    window.localStorage.clear();
    window.localStorage.setItem('gag-quality-tier-v3', 'low');
    mount();
    expect(current().preference).toBe('low');
    cleanup();

    window.localStorage.setItem('gag-quality-tier-v4', 'medium');
    mount({ restorePreference: false, defaultTier: 'high' });
    expect(current().preference).toBe('high');
  });

  it('setTier updates the tier, bumps revision and persists', () => {
    mount();
    expect(current().autoRevision).toBe(0);
    act(() => current().setTier('medium'));
    expect(current().tier).toBe('medium');
    expect(current().perfTier).toBe('medium');
    expect(current().autoRevision).toBe(1);
    expect(window.localStorage.getItem('gag-quality-tier-v4')).toBe('medium');
    expect(window.localStorage.getItem('gag-quality-tier-v3')).toBe('medium');

    act(() => current().setTier('auto'));
    expect(current().preference).toBe('auto');
    expect(current().tier).toBe('high');
    expect(window.localStorage.getItem('gag-quality-tier-v4')).toBe('auto');
    expect(window.localStorage.getItem('gag-quality-tier-v3')).toBe('medium');
  });

  it('reaffirming the current choice does not reset the auto runtime', () => {
    mount();
    act(() => current().setTier('auto'));
    expect(current().autoRevision).toBe(0);
    expect(window.localStorage.getItem('gag-quality-tier-v4')).toBe('auto');
  });

  it('tracks cognition events as an advisory flag without dimming the tier', () => {
    mount();
    expect(current().generating).toBe(false);
    act(() => cognition.handler?.({ type: 'directive' }));
    expect(current().generating).toBe(true);
    expect(current().tier).toBe('high');
    act(() => cognition.handler?.({ type: 'synthesis' }));
    expect(current().generating).toBe(false);
    act(() => cognition.handler?.({ type: 'directive' }));
    act(() => cognition.handler?.({ type: 'approval-required' }));
    expect(current().generating).toBe(false);
  });

  it('only starts auto calibration while the preference is auto', () => {
    mount();
    act(() => current().beginAutoCalibration(5));
    expect(current().autoProfile).toEqual({ stage: 'started' });
    cleanup();

    mount({ defaultTier: 'low', restorePreference: false });
    act(() => current().beginAutoCalibration(5));
    expect(current().autoProfile).toEqual({ stage: 'calibrating' });
  });
});
