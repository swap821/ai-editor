import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { __resetTabStoreForTests } from '../superbrain/lib/tabStore';
import { LivingWorkspaceShell } from './LivingWorkspaceShell';

afterEach(() => {
  __resetTabStoreForTests();
  vi.unstubAllGlobals();
});

describe('LivingWorkspaceShell mobile Expert menu handoff', () => {
  it('closes the mobile surface and category disclosures after selecting a workspace', () => {
    vi.stubGlobal('matchMedia', vi.fn().mockImplementation((query: string) => ({
      matches: query === '(max-width: 767px)' || query === '(max-width: 360px)',
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })));

    render(<LivingWorkspaceShell experienceMode="expert" />);

    const surfaceMenu = screen.getByText('Expert surfaces', { exact: true }).closest('details');
    fireEvent.click(screen.getByText('Expert surfaces', { exact: true }));
    const taskMenu = screen.getByText('Task', { exact: true }).closest('details');
    fireEvent.click(screen.getByText('Task', { exact: true }));
    fireEvent.click(screen.getByRole('button', { name: 'Recent observations' }));

    expect(surfaceMenu).not.toHaveAttribute('open');
    expect(taskMenu).not.toHaveAttribute('open');
    expect(screen.getByRole('region', { name: 'Selected workspace' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Expand workspace' })).toHaveFocus();
  });
});
