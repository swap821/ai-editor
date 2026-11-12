import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render } from '@testing-library/react';
import { createElement, useContext, type ContextType } from 'react';
import { QualityTierContext, useQualityTierOwner } from './qualityTierContext';

type OwnerValue = ContextType<typeof QualityTierContext>;

afterEach(() => {
  cleanup();
});

function readDefault(): OwnerValue {
  let seen: OwnerValue | undefined;
  function ReadDefault() {
    seen = useContext(QualityTierContext);
    return null;
  }
  render(createElement(ReadDefault));
  cleanup();
  if (seen === undefined) throw new Error('context default was not read');
  return seen;
}

function readOwner(provided?: OwnerValue): { result: ReturnType<typeof useQualityTierOwner> } {
  const out: { result: ReturnType<typeof useQualityTierOwner> } = { result: null };
  function Probe() {
    out.result = useQualityTierOwner();
    return null;
  }
  if (provided === undefined) {
    render(createElement(Probe));
  } else {
    render(createElement(QualityTierContext.Provider, { value: provided }, createElement(Probe)));
  }
  return out;
}

describe('QualityTierContext default', () => {
  it('exposes the high-quality, non-generating defaults', () => {
    const value = readDefault();
    expect(value.tier).toBe('high');
    expect(value.perfTier).toBe('high');
    expect(value.baseTier).toBe('high');
    expect(value.preference).toBe('high');
    expect(value.generating).toBe(false);
    expect(value.autoRevision).toBe(0);
  });
});

describe('useQualityTierOwner', () => {
  it('returns null when no provider supplies a value', () => {
    expect(readOwner().result).toBeNull();
  });

  it('returns null when the provided value is the default object itself', () => {
    const out = readOwner(readDefault());
    expect(out.result).toBeNull();
  });

  it('returns the exact provided owner and keeps its callbacks usable', () => {
    const setTier = vi.fn();
    const owner: OwnerValue = {
      ...readDefault(),
      generating: true,
      autoRevision: 7,
      setTier,
    };
    const out = readOwner(owner);
    expect(out.result).toBe(owner);
    expect(out.result?.generating).toBe(true);
    expect(out.result?.autoRevision).toBe(7);

    out.result?.setTier('high');
    expect(setTier).toHaveBeenCalledTimes(1);
    expect(setTier).toHaveBeenCalledWith('high');
  });
});
