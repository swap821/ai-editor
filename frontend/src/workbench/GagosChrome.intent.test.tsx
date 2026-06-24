import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { act } from 'react';

vi.mock('../superbrain/SuperbrainApp', () => ({
  default: () => <div data-testid="mock-being">being</div>,
}));

const previewIntent = vi.fn();
const fetchOnboardingState = vi.fn().mockResolvedValue({
  firstDirective: false,
  firstApproval: false,
  firstVerify: false,
  firstCloudRoute: false,
  firstAutonomy: false,
});

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

describe('GagosChrome intent preview', () => {
  beforeEach(() => {
    previewIntent.mockReset();
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
  });

  it('shows a backend-driven intent icon when typing a code directive', async () => {
    previewIntent.mockResolvedValue({ intent: 'code', confidence: 0.95, tool: 'edit_file' });
    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome />);

    const input = screen.getByLabelText('Talk to GAGOS');
    await act(async () => {
      fireEvent.change(input, { target: { value: 'write a login page' } });
    });

    await waitFor(() => {
      expect(previewIntent).toHaveBeenCalled();
    });

    await waitFor(() => {
      expect(input.parentElement).toHaveClass('intent-code');
    });
  });
});
