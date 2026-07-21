import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import EcosystemDashboard from './EcosystemDashboard';

vi.mock('../components/HUDPanel', () => ({
  default: ({ title, children, tint }) => (
    <div data-testid="hud-panel" data-title={title} data-tint={tint}>
      {children}
    </div>
  ),
}));

const V10_STATUS = {
  ecosystem: {
    available: true,
    lastScan: {
      findingCount: 3,
      networkCalls: 0,
    },
  },
  constitution: {
    casteCount: 7,
    frozenCoreProtected: true,
  },
  symbolRepoMap: {
    activation: 'proposal/evidence',
    lastScan: {
      symbolCount: 123,
      evidenceFileCount: 45,
    },
  },
  metaLoop: {
    safetyStatus: 'ok',
    proposalCount: 2,
  },
  councilMemory: {
    deliberationCount: 4,
  },
};

describe('EcosystemDashboard', () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders loading state initially', () => {
    globalThis.fetch.mockImplementation(() => new Promise(() => {}));
    render(<EcosystemDashboard onClose={vi.fn()} />);

    expect(screen.getByTestId('hud-panel')).toBeInTheDocument();
    expect(screen.getByText(/Reading ecosystem status.../i)).toBeInTheDocument();
  });

  it('renders v10 ecosystem status on success', async () => {
    globalThis.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => V10_STATUS,
    });

    render(<EcosystemDashboard onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText(/3 finding\(s\) · 0 network calls/i)).toBeInTheDocument();
      expect(screen.getByText(/7 castes · frozen protected/i)).toBeInTheDocument();
      expect(screen.getByText(/123 symbols · 45 files · proposal\/evidence/i)).toBeInTheDocument();
      expect(screen.getByText(/Meta-loop: ok · 2 proposal\(s\) \| Council memory: 4 deliberation\(s\)/i)).toBeInTheDocument();
    });
  });
});