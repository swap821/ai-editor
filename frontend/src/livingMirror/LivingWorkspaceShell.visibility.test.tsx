import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { __resetTabStoreForTests, getTabStoreSnapshot, openWorkspacePanel } from '../superbrain/lib/tabStore';
import { LivingWorkspaceShell } from './LivingWorkspaceShell';
import { detectSystemReducedMotion } from './motionPreference';

afterEach(() => {
  __resetTabStoreForTests();
  window.localStorage.removeItem('gagos-pause-motion-v1');
  vi.unstubAllGlobals();
});

describe('LivingWorkspaceShell experience boundaries', () => {
  it('treats missing browser motion APIs as an unknown preference, not a render failure', () => {
    expect(detectSystemReducedMotion(undefined)).toBe(false);
    expect(detectSystemReducedMotion({
      matchMedia: () => ({ matches: true } as MediaQueryList),
    })).toBe(true);
  });

  it('does not mount an already-open Expert panel in Guided mode', () => {
    render(<LivingWorkspaceShell experienceMode="beginner" />);

    act(() => openWorkspacePanel('terminal', 'Terminal'));

    expect(screen.queryByRole('heading', { name: 'Terminal' })).not.toBeInTheDocument();
    expect(screen.queryByText('Loading Terminal…')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Terminal' })).not.toBeInTheDocument();
  });

  it('keeps the complete Guided workspace shell free of internal architecture terms', () => {
    render(<LivingWorkspaceShell experienceMode="beginner" />);

    const guidedEnvironment = document.body.textContent ?? '';
    expect(guidedEnvironment).not.toMatch(
      /\b(governance|stigmergy|council|workforce|hiring|vulture|ecosystem|terminal|provider|model|worker|organ|capability|policy|swarm|sovereign|operator|latch)\b/i,
    );
    expect(screen.getByRole('navigation', { name: 'Workspaces' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Tasks' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Project files' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Recent activity' })).toBeInTheDocument();
  });

  it('does not open the Expert terminal shortcut in Guided mode', () => {
    render(<LivingWorkspaceShell experienceMode="beginner" />);

    act(() => window.dispatchEvent(new KeyboardEvent('keydown', { key: '`', ctrlKey: true })));

    expect(getTabStoreSnapshot().panels ?? []).not.toEqual(expect.arrayContaining([
      expect.objectContaining({ kind: 'terminal' }),
    ]));
  });

  it('collapses Expert anatomy into progressive mobile surfaces on a narrow viewport', () => {
    vi.stubGlobal('matchMedia', vi.fn().mockImplementation(() => ({
      matches: true,
      media: '(max-width: 767px)',
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })));

    render(<LivingWorkspaceShell experienceMode="expert" />);

    const expertSurfaces = screen.getByText('Expert surfaces').closest('details');
    expect(expertSurfaces).toBeTruthy();
    expect(expertSurfaces).not.toHaveAttribute('open');
    act(() => fireEvent.click(screen.getByText('Expert surfaces')));
    expect(expertSurfaces).toHaveAttribute('open');
    const task = screen.getByText('Task', { exact: true }).closest('details');
    expect(task).toBeTruthy();
    expect(task).not.toHaveAttribute('open');
    act(() => fireEvent.click(screen.getByText('Task', { exact: true })));
    expect(screen.getByRole('button', { name: 'Missions' })).toBeInTheDocument();

    const evidence = screen.getByText('Evidence', { exact: true }).closest('details');
    expect(evidence).toBeTruthy();
    expect(evidence).not.toHaveAttribute('open');
    act(() => fireEvent.click(screen.getByText('Evidence', { exact: true })));
    expect(screen.getByRole('button', { name: 'Terminal' })).toBeInTheDocument();
  });

  it('uses the human Tasks projection instead of the technical Missions panel in Guided mode', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      if (String(input).includes('/api/v1/council/missions')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ count: 1, missions: [{
            family: 'council', missionId: 'mission-secret-42', mission: 'Prepare release notes', status: 'deliberating',
            risk: 'yellow', updatedAt: 1789400000, approvalNeeded: true, verificationPassed: null,
            verificationStrength: null, verificationMeetsFloor: null,
          }] }),
        } as Response);
      }
      return Promise.reject(new Error('offline'));
    }));

    render(<LivingWorkspaceShell experienceMode="beginner" />);
    act(() => openWorkspacePanel('missions', 'Tasks'));

    expect(await screen.findByText('Recorded tasks stay readable here. If a task needs your permission, GAGOS will ask before the action.')).toBeInTheDocument();
    expect(screen.queryByText(/Council reports|mission-secret-42/i)).not.toBeInTheDocument();
  });

  it('offers an accessible ambient-motion pause in Expert and persists the preference', () => {
    window.localStorage.removeItem('gagos-pause-motion-v1');
    render(<LivingWorkspaceShell experienceMode="expert" />);

    const pause = screen.getByRole('button', { name: 'Pause ambient motion' });
    expect(pause).toHaveAttribute('aria-pressed', 'false');

    act(() => fireEvent.click(pause));

    const resume = screen.getByRole('button', { name: 'Resume ambient motion' });
    expect(resume).toHaveAttribute('aria-pressed', 'true');
    expect(window.localStorage.getItem('gagos-pause-motion-v1')).toBe('true');
    expect(document.querySelector('.lm-shell')).toHaveAttribute('data-motion-reduced', 'true');
  });

  it('honors a measured system reduced-motion preference without removing the control surface', () => {
    vi.stubGlobal('matchMedia', vi.fn().mockImplementation((query: string) => ({
      matches: query === '(prefers-reduced-motion: reduce)',
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })));

    render(<LivingWorkspaceShell experienceMode="expert" />);

    const motionControl = screen.getByRole('button', { name: 'Motion reduced by system' });
    expect(motionControl).toBeDisabled();
    expect(motionControl).toHaveAttribute('aria-pressed', 'true');
    expect(document.querySelector('.lm-shell')).toHaveAttribute('data-motion-reduced', 'true');
    expect(screen.getByRole('button', { name: 'Conversation' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Emergency stop' })).toBeInTheDocument();
  });
});
