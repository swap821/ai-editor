import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { act } from 'react';

vi.mock('../superbrain/SuperbrainApp', () => ({
  default: () => <div data-testid="mock-being">being</div>,
}));

const previewIntent = vi.fn().mockResolvedValue({ intent: 'chat', confidence: 0.5, tool: null });
const fetchOnboardingState = vi.fn();

vi.mock('../superbrain/lib/aiosAdapter', async () => {
  const actual = await vi.importActual<typeof import('../superbrain/lib/aiosAdapter')>(
    '../superbrain/lib/aiosAdapter',
  );
  return {
    ...actual,
    previewIntent,
    fetchOnboardingState,
  };
});

describe('GagosChrome onboarding coach', () => {
  beforeEach(() => {
    fetchOnboardingState.mockReset();
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });
    // Ensure the coach is not already dismissed.
    window.localStorage.removeItem('gagos-onboarded');
    window.localStorage.removeItem('gagos-onboarding-hint-dismissed');
  });

  it('shows the first directive card when no milestones are reached', async () => {
    fetchOnboardingState.mockResolvedValue({
      firstDirective: false,
      firstApproval: false,
      firstVerify: false,
      firstCloudRoute: false,
      firstAutonomy: false,
    });

    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome />);

    await waitFor(() => {
      expect(screen.getByText(/Type a goal and press Enter/i)).toBeInTheDocument();
    });
  });

  it('advances to the approval milestone card after firstDirective', async () => {
    fetchOnboardingState.mockResolvedValue({
      firstDirective: true,
      firstApproval: false,
      firstVerify: false,
      firstCloudRoute: false,
      firstAutonomy: false,
    });

    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome />);

    await waitFor(() => {
      expect(screen.getByText(/pause for your approval/i)).toBeInTheDocument();
    });
  });

  it('shows the example placeholder and organs hint after the coach is dismissed', async () => {
    // Coach already dismissed -> hint should appear.
    window.localStorage.setItem('gagos-onboarded', '1');
    fetchOnboardingState.mockResolvedValue({
      firstDirective: false,
      firstApproval: false,
      firstVerify: false,
      firstCloudRoute: false,
      firstAutonomy: false,
    });

    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome />);

    await waitFor(() => {
      expect(screen.getByPlaceholderText(/Try: 'scaffold a FastAPI \/health endpoint'/i)).toBeInTheDocument();
    });
    expect(screen.getByRole('note', { name: /Onboarding hint/i })).toBeInTheDocument();
    expect(screen.getByText(/▣ ORGANS · forge/i)).toBeInTheDocument();
  });

  it('hides the hint and writes the dismissal flag when the X is clicked', async () => {
    window.localStorage.setItem('gagos-onboarded', '1');
    fetchOnboardingState.mockResolvedValue({
      firstDirective: false,
      firstApproval: false,
      firstVerify: false,
      firstCloudRoute: false,
      firstAutonomy: false,
    });

    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome />);

    await waitFor(() => {
      expect(screen.getByRole('note', { name: /Onboarding hint/i })).toBeInTheDocument();
    });

    await act(async () => {
      screen.getByRole('button', { name: /Dismiss onboarding hint/i }).click();
    });

    await waitFor(() => {
      expect(screen.queryByRole('note', { name: /Onboarding hint/i })).not.toBeInTheDocument();
    });
    expect(window.localStorage.getItem('gagos-onboarding-hint-dismissed')).toBe('1');
  });

  it('does not show the hint if it was already dismissed', async () => {
    window.localStorage.setItem('gagos-onboarded', '1');
    window.localStorage.setItem('gagos-onboarding-hint-dismissed', '1');
    fetchOnboardingState.mockResolvedValue({
      firstDirective: false,
      firstApproval: false,
      firstVerify: false,
      firstCloudRoute: false,
      firstAutonomy: false,
    });

    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome />);

    await waitFor(() => {
      expect(screen.queryByRole('note', { name: /Onboarding hint/i })).not.toBeInTheDocument();
    });
    expect(screen.getByPlaceholderText(/talk to GAGOS/i)).toBeInTheDocument();
  });
});
