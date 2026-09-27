import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { __resetTabStoreForTests, openWorkspacePanel } from '../superbrain/lib/tabStore';
import { LivingWorkspaceShell } from './LivingWorkspaceShell';

afterEach(() => {
  __resetTabStoreForTests();
  vi.unstubAllGlobals();
});

function stubViewport(maxWidth: 360 | 767) {
  vi.stubGlobal('matchMedia', vi.fn().mockImplementation((query: string) => ({
    matches: query === '(max-width: 767px)' || (maxWidth === 360 && query === '(max-width: 360px)'),
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })));
}

describe('LivingWorkspaceShell compact Expert disclosure', () => {
  it('keeps a 320px work surface collapsed but mounted until requested, with focus-safe controls', () => {
    stubViewport(360);
    render(<LivingWorkspaceShell experienceMode="expert" />);
    act(() => openWorkspacePanel('history', 'Recent observations'));

    const workspace = screen.getByRole('region', { name: 'Selected workspace' });
    const expand = within(workspace).getByRole('button', { name: 'Expand workspace' });
    const content = workspace.querySelector('.lm-surface__content');
    expect(expand).toHaveAttribute('aria-expanded', 'false');
    expect(expand).toHaveAttribute('aria-controls', 'lm-surface-content');
    expect(content).toHaveAttribute('hidden');
    expect(within(workspace).getByRole('button', { name: 'Pin' })).toBeInTheDocument();
    expect(within(workspace).getByRole('button', { name: 'Close workspace' })).toBeInTheDocument();
    expect(expand).toHaveFocus();

    const mountedBody = content?.firstElementChild;
    fireEvent.click(expand);

    const collapse = within(workspace).getByRole('button', { name: 'Collapse workspace' });
    expect(collapse).toHaveAttribute('aria-expanded', 'true');
    expect(content).not.toHaveAttribute('hidden');
    expect(content?.firstElementChild).toBe(mountedBody);

    (content as HTMLElement).tabIndex = -1;
    (content as HTMLElement).focus();
    fireEvent.click(collapse);

    expect(expand).toHaveFocus();
    expect(content).toHaveAttribute('hidden');
    expect(content?.firstElementChild).toBe(mountedBody);
  });

  it('does not add the compact disclosure at 361px', () => {
    stubViewport(767);
    render(<LivingWorkspaceShell experienceMode="expert" />);
    act(() => openWorkspacePanel('history', 'Recent observations'));

    expect(screen.queryByRole('button', { name: 'Expand workspace' })).not.toBeInTheDocument();
    expect(document.querySelector('.lm-surface__content')).not.toHaveAttribute('hidden');
  });
});
