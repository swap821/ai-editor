import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import {
  __resetTabStoreForTests,
  closeWorkspace,
  focusWorkspace,
  openWorkspacePanel,
} from '../superbrain/lib/tabStore';
import { LivingWorkspaceShell } from './LivingWorkspaceShell';

beforeEach(() => {
  __resetTabStoreForTests();
});

afterEach(() => {
  __resetTabStoreForTests();
});

describe('LivingWorkspaceShell focus continuity', () => {
  it('returns focus to Conversation when a rail-selected workspace is dismissed', () => {
    render(<LivingWorkspaceShell experienceMode="expert" />);

    const navigation = screen.getByRole('navigation', { name: 'Workspaces' });
    const earlierLauncher = within(navigation).getByRole('button', { name: 'Recent observations' });
    earlierLauncher.focus();
    fireEvent.click(earlierLauncher);

    act(() => {
      openWorkspacePanel('test-workspace', 'Test workspace', 'fixture');
      focusWorkspace('history');
    });

    const rail = screen.getByRole('complementary', { name: 'Spinal workspace anchors' });
    const selectedAnchor = within(rail).getByRole('button', { name: 'Test workspace' });
    selectedAnchor.focus();
    fireEvent.click(selectedAnchor);

    expect(screen.getByRole('heading', { name: 'Test workspace' })).toHaveFocus();

    fireEvent.keyDown(screen.getByRole('region', { name: 'Selected workspace' }), { key: 'Escape' });

    expect(within(navigation).getByRole('button', { name: 'Conversation' })).toHaveFocus();
  });

  it('restores focus to the launcher when a workspace closes outside the shell controls', () => {
    render(<LivingWorkspaceShell experienceMode="expert" />);

    const navigation = screen.getByRole('navigation', { name: 'Workspaces' });
    const launcher = within(navigation).getByRole('button', { name: 'Recent observations' });
    launcher.focus();
    fireEvent.click(launcher);

    expect(within(screen.getByRole('region', { name: 'Selected workspace' }))
      .getByRole('heading', { name: 'Recent observations', level: 2 })).toHaveFocus();

    act(() => closeWorkspace('history'));

    expect(launcher).toHaveFocus();
  });

  it('keeps focus on Conversation when that control closes the selected workspace', () => {
    render(<LivingWorkspaceShell experienceMode="expert" />);

    const navigation = screen.getByRole('navigation', { name: 'Workspaces' });
    const launcher = within(navigation).getByRole('button', { name: 'Recent observations' });
    launcher.focus();
    fireEvent.click(launcher);

    const conversation = within(navigation).getByRole('button', { name: 'Conversation' });
    conversation.focus();
    fireEvent.click(conversation);

    expect(conversation).toHaveFocus();
  });

});
