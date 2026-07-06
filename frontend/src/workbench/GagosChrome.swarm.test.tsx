/**
 * The SWARM chip is the ONLY UI entry point to the adapter's swarm singleton —
 * this drives the real button and asserts the singleton flips with it, so a
 * refactor cannot leave the chip toggling visually while directives silently
 * keep (or never gain) the colony flag.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { getSwarmMode, setSwarmMode } from '../superbrain/lib/aiosAdapter';
import { __resetActiveBrainForTests } from '../superbrain/lib/activeBrain';
import { __resetTabStoreForTests } from '../superbrain/lib/tabStore';

vi.mock('../superbrain/SuperbrainApp', () => ({
  default: () => <div data-testid="mock-being">being</div>,
}));

// vi.hoisted: this file statically imports from the mocked module (the real
// swarm singleton is the unit under test), so the mock factory runs during
// import — plain consts would not be initialized yet.
const { sendDirective, previewIntent, fetchOnboardingState } = vi.hoisted(() => ({
  sendDirective: vi.fn().mockResolvedValue({ answer: 'ok', paused: false }),
  previewIntent: vi.fn().mockResolvedValue({ intent: 'chat', confidence: 0.9, tool: null }),
  fetchOnboardingState: vi.fn().mockResolvedValue({
    firstDirective: true,
    firstApproval: true,
    firstVerify: true,
    firstCloudRoute: true,
    firstAutonomy: true,
  }),
}));

vi.mock('../superbrain/lib/aiosAdapter', async () => {
  const actual = await vi.importActual<typeof import('../superbrain/lib/aiosAdapter')>(
    '../superbrain/lib/aiosAdapter',
  );
  // Keep the REAL swarm singleton (that is what's under test); fake the wire.
  return { ...actual, sendDirective, previewIntent, fetchOnboardingState };
});

describe('GagosChrome swarm chip', () => {
  beforeEach(() => {
    __resetActiveBrainForTests();
    __resetTabStoreForTests();
    setSwarmMode(false);
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

  it('toggles the adapter swarm singleton and aria-pressed together', async () => {
    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome />);

    const chip = screen.getByRole('button', { name: /swarm mode off/i });
    expect(chip).toHaveAttribute('aria-pressed', 'false');
    expect(getSwarmMode()).toBe(false);

    fireEvent.click(chip);
    expect(getSwarmMode()).toBe(true);
    expect(screen.getByRole('button', { name: /swarm mode on/i })).toHaveAttribute(
      'aria-pressed',
      'true',
    );

    fireEvent.click(screen.getByRole('button', { name: /swarm mode on/i }));
    expect(getSwarmMode()).toBe(false);
  });

  it('seeds the chip from the singleton so a remount cannot desync them', async () => {
    setSwarmMode(true);
    const { default: GagosChrome } = await import('./GagosChrome');
    render(<GagosChrome />);
    expect(screen.getByRole('button', { name: /swarm mode on/i })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });
});
