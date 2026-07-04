import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import TrustHalo, { computeTrustLevel } from './TrustHalo';

describe('TrustHalo', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders without crashing', () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({}), { status: 200 }),
    );
    const { container } = render(<TrustHalo />);
    expect(container.querySelector('.trust-halo')).toBeInTheDocument();
  });

  it('shows unknown initially before fetch resolves', () => {
    // Never-resolving fetch so the component stays in initial state
    vi.spyOn(globalThis, 'fetch').mockReturnValue(new Promise(() => {}));
    render(<TrustHalo />);
    expect(screen.getByText('unknown')).toBeInTheDocument();
    expect(screen.getByLabelText('System trust: unknown')).toBeInTheDocument();
  });

  it('shows healthy when metrics indicate low intervention and high verification', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({ human_intervention_rate: 0.1, verification_coverage: 0.9 }),
        { status: 200 },
      ),
    );
    render(<TrustHalo />);
    await waitFor(() => {
      expect(screen.getByText('healthy')).toBeInTheDocument();
    });
    expect(screen.getByLabelText('System trust: healthy')).toBeInTheDocument();
  });

  it('shows critical when metrics indicate high intervention', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({ human_intervention_rate: 0.8, verification_coverage: 0.5 }),
        { status: 200 },
      ),
    );
    render(<TrustHalo />);
    await waitFor(() => {
      expect(screen.getByText('critical')).toBeInTheDocument();
    });
    expect(screen.getByLabelText('System trust: critical')).toBeInTheDocument();
  });

  it('shows critical when verification coverage is very low', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({ human_intervention_rate: 0.2, verification_coverage: 0.2 }),
        { status: 200 },
      ),
    );
    render(<TrustHalo />);
    await waitFor(() => {
      expect(screen.getByText('critical')).toBeInTheDocument();
    });
  });

  it('shows attention for middle-ground metrics', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({ human_intervention_rate: 0.4, verification_coverage: 0.5 }),
        { status: 200 },
      ),
    );
    render(<TrustHalo />);
    await waitFor(() => {
      expect(screen.getByText('attention')).toBeInTheDocument();
    });
    expect(screen.getByLabelText('System trust: attention')).toBeInTheDocument();
  });

  it('stays unknown when fetch fails', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('network error'));
    render(<TrustHalo />);
    // Give it a tick to attempt the fetch
    await new Promise((r) => setTimeout(r, 10));
    expect(screen.getByText('unknown')).toBeInTheDocument();
  });

  it('stays unknown when fetch returns non-ok status', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('', { status: 500 }),
    );
    render(<TrustHalo />);
    await new Promise((r) => setTimeout(r, 10));
    expect(screen.getByText('unknown')).toBeInTheDocument();
  });
});

describe('computeTrustLevel', () => {
  it('returns unknown for null metrics', () => {
    expect(computeTrustLevel(null)).toBe('unknown');
  });

  it('returns unknown for undefined metrics', () => {
    expect(computeTrustLevel(undefined)).toBe('unknown');
  });

  it('returns healthy for low intervention and high verification', () => {
    expect(computeTrustLevel({ human_intervention_rate: 0.0, verification_coverage: 1.0 })).toBe('healthy');
    expect(computeTrustLevel({ human_intervention_rate: 0.29, verification_coverage: 0.71 })).toBe('healthy');
  });

  it('returns critical for high intervention rate', () => {
    expect(computeTrustLevel({ human_intervention_rate: 0.71, verification_coverage: 0.9 })).toBe('critical');
    expect(computeTrustLevel({ human_intervention_rate: 1.0, verification_coverage: 1.0 })).toBe('critical');
  });

  it('returns critical for very low verification coverage', () => {
    expect(computeTrustLevel({ human_intervention_rate: 0.1, verification_coverage: 0.29 })).toBe('critical');
    expect(computeTrustLevel({ human_intervention_rate: 0.0, verification_coverage: 0.0 })).toBe('critical');
  });

  it('returns attention for middle-ground values', () => {
    expect(computeTrustLevel({ human_intervention_rate: 0.5, verification_coverage: 0.5 })).toBe('attention');
    expect(computeTrustLevel({ human_intervention_rate: 0.3, verification_coverage: 0.7 })).toBe('attention');
    expect(computeTrustLevel({ human_intervention_rate: 0.4, verification_coverage: 0.8 })).toBe('attention');
  });

  it('treats missing fields as 0', () => {
    // Missing intervention_rate (0) + missing verification_coverage (0) -> critical (coverage < 0.3)
    expect(computeTrustLevel({})).toBe('critical');
    // Missing verification_coverage (0) -> critical
    expect(computeTrustLevel({ human_intervention_rate: 0.1 })).toBe('critical');
    // Missing intervention_rate (0) + high coverage -> healthy
    expect(computeTrustLevel({ verification_coverage: 0.9 })).toBe('healthy');
  });

  it('handles exact boundary at 0.3 intervention rate', () => {
    // 0.3 is NOT < 0.3, so not healthy even with high coverage
    expect(computeTrustLevel({ human_intervention_rate: 0.3, verification_coverage: 0.8 })).toBe('attention');
  });

  it('handles exact boundary at 0.7 intervention rate', () => {
    // 0.7 is NOT > 0.7, so not critical
    expect(computeTrustLevel({ human_intervention_rate: 0.7, verification_coverage: 0.5 })).toBe('attention');
  });

  it('handles exact boundary at 0.7 verification coverage', () => {
    // 0.7 is NOT > 0.7, so not healthy even with low intervention
    expect(computeTrustLevel({ human_intervention_rate: 0.1, verification_coverage: 0.7 })).toBe('attention');
  });

  it('handles exact boundary at 0.3 verification coverage', () => {
    // 0.3 is NOT < 0.3, so not critical from coverage alone
    expect(computeTrustLevel({ human_intervention_rate: 0.5, verification_coverage: 0.3 })).toBe('attention');
  });
});
