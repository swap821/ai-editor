import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import { act } from 'react';
import { markSwarmCloudSubtask, resetSwarmHUD, startSwarmPlan } from '../superbrain/lib/swarmHUDStore';
import {
  getSpineFlashState,
  __resetSpineFlashBridgeForTests,
} from './spineFlashBridge';

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

describe('GagosChrome cloud-route spine flash', () => {
  beforeEach(() => {
    fetchOnboardingState.mockReset();
    previewIntent.mockClear();
    resetSwarmHUD();
    __resetSpineFlashBridgeForTests();
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
    window.localStorage.removeItem('gagos-onboarded');
    window.localStorage.removeItem('gagos-cloudroute-flash-shown');
  });

  it('triggers the spine flash when the first cloud subtask is routed', async () => {
    fetchOnboardingState.mockResolvedValue({
      firstDirective: true,
      firstApproval: true,
      firstVerify: true,
      firstCloudRoute: false,
      firstAutonomy: false,
    });

    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome />);

    expect(getSpineFlashState().intensity).toBe(0);

    act(() => {
      startSwarmPlan(['cloud task', 'local task']);
      markSwarmCloudSubtask(0);
    });

    await waitFor(() => {
      expect(getSpineFlashState().intensity).toBe(1);
    });
  });
});
