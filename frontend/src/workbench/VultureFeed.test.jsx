import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import VultureFeed from './VultureFeed';

vi.mock('../components/HUDPanel', () => ({
  default: ({ title, children, tint }) => (
    <div data-testid="hud-panel" data-title={title} data-tint={tint}>
      {children}
    </div>
  ),
}));

const V10_STATUS = {
  vulture: {
    available: true,
    activation: 'proposal/evidence',
    localOnly: true,
    cloudCalls: 0,
    writesPerformed: false,
    lastScan: {
      findingCount: 2,
      cloudCalls: 0,
      writesPerformed: false,
      topFindings: [
        {
          kind: 'approval_bypass_phrase',
          severity: 'high',
          targetId: '.aios/state/RESUME.md',
          recommendation: 'Keep the approval gate explicit.',
        },
      ],
    },
  },
};

describe('VultureFeed', () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders loading state initially', () => {
    globalThis.fetch.mockImplementation(() => new Promise(() => {}));
    render(<VultureFeed onClose={vi.fn()} />);

    expect(screen.getByTestId('hud-panel')).toBeInTheDocument();
    expect(screen.getByText(/Reading immune scanner status.../i)).toBeInTheDocument();
  });

  it('renders v10 immune evidence on success', async () => {
    globalThis.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => V10_STATUS,
    });

    render(<VultureFeed onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText(/2 finding\(s\) · 0 cloud calls · no writes/i)).toBeInTheDocument();
      expect(screen.getByText(/approval_bypass_phrase/i)).toBeInTheDocument();
      expect(screen.getByText(/Keep the approval gate explicit/i)).toBeInTheDocument();
      expect(screen.getByText(/Source: \.aios\/state\/RESUME\.md/i)).toBeInTheDocument();
    });
  });

  it('renders an available-but-not-scanned state', async () => {
    globalThis.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ vulture: { available: true, lastScan: null } }),
    });

    render(<VultureFeed onClose={vi.fn()} />);

    expect(await screen.findByText(/Scanner available; no explicit vulture scan has run/i)).toBeInTheDocument();
  });
});