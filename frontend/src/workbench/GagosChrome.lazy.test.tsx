import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('../superbrain/SuperbrainApp', () => ({
  default: () => <div data-testid="mock-being">being</div>,
}));

// A Guided mount must not evaluate an Expert-only surface. If GagosChrome
// statically imports this module, the test fails before the component renders.
vi.mock('./CouncilDashboard', () => {
  throw new Error('Expert Council surface was evaluated during Guided startup');
});

describe('GagosChrome Expert surface loading', () => {
  beforeEach(() => {
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

  it('does not evaluate CouncilDashboard while Guided is mounted', async () => {
    const { default: GagosChrome } = await import('./GagosChrome');

    render(<GagosChrome experienceMode="beginner" />);

    expect(screen.getByLabelText('GAGOS conversation')).toBeInTheDocument();
    expect(screen.queryByText('Expert Council surface was evaluated during Guided startup')).toBeNull();
  });
});
